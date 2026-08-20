// Cross-browser render checks: the same preview pages, measured in three
// engines (Blink, Gecko, WebKit — i.e. Chrome, Firefox, Safari), at phone,
// tablet and laptop widths. Engines never render text identically, so this
// compares only metrics that must agree: fixed dimensions, breakpoint
// behaviour, and whether the core interactions work at all.
//
// Run via tests/run.py (which skips gracefully when Playwright is absent)
// or directly: node tests/browsers.mjs
//
// Output: one JSON object on stdout — { checks: [{ name, ok, detail }] }.

import { chromium, firefox, webkit } from 'playwright';
import { fileURLToPath } from 'url';
import path from 'path';
import fs from 'fs';
import { execFileSync } from 'child_process';

const ROOT = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const PREVIEW = path.join(ROOT, '.preview');
const PAGES = ['index.html', 'product.html', 'products.html', 'cart.html'];
const VIEWPORTS = [['phone', 390, 844], ['tablet', 768, 1024], ['laptop', 1280, 800]];
const ENGINES = { chromium, firefox, webkit };

const checks = [];
const ok = (name, cond, detail = '') =>
  checks.push({ name, ok: !!cond, detail: cond ? '' : String(detail) });

// Rebuild so the preview matches the working tree.
execFileSync('python3', ['build.py'], { cwd: PREVIEW });

// What one engine sees on one page at one width. Everything here is either
// a fixed dimension, a breakpoint outcome, or a did-it-work boolean.
async function measure(page) {
  return page.evaluate(() => {
    const style = (sel, prop) => {
      const el = document.querySelector(sel);
      return el ? getComputedStyle(el)[prop] : null;
    };
    const rectH = (sel) => {
      const el = document.querySelector(sel);
      return el ? Math.round(el.getBoundingClientRect().height) : null;
    };
    const out = {
      overflow: document.documentElement.scrollWidth - window.innerWidth,
      dividerH: rectH('.pattern-divider'),
      headerH: rectH('.header'),
      heroBtn: !!document.querySelector('.hero__buttons a'),
      toggleShown: style('.header__menu-toggle', 'display') !== 'none',
      navShown: style('.header__nav', 'display') !== 'none',
      railScrolls: (() => {
        const r = document.querySelector('.dispatch-grid--carousel');
        if (!r) return null;
        const o = getComputedStyle(r).overflowX;
        return (o === 'auto' || o === 'scroll') && r.scrollWidth > r.clientWidth + 4;
      })(),
      bodyFontPx: parseFloat(getComputedStyle(document.body).fontSize),
    };
    const toggle = document.querySelector('[data-mobile-nav-open]');
    const nav = document.getElementById('MobileNav');
    if (toggle && nav && out.toggleShown) {
      toggle.click();
      out.drawerOpens = nav.classList.contains('is-open');
      document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
      out.drawerCloses = !nav.classList.contains('is-open');
    }
    return out;
  });
}

const results = {}; // engine -> "page@label" -> metrics
for (const [engineName, engine] of Object.entries(ENGINES)) {
  let browser;
  try {
    // Blink comes from the installed Google Chrome, so this exercises the
    // browser people actually run; Gecko and WebKit are Playwright builds.
    browser = engineName === 'chromium'
      ? await engine.launch({ channel: 'chrome' }).catch(() => engine.launch())
      : await engine.launch();
  } catch (e) {
    // Not installed, or blocked by the machine's security policy (managed
    // Macs commonly kill Playwright's unsigned Firefox nightly on launch).
    // An engine that cannot start here is a gap in coverage, not a defect
    // in the theme — report it as a visible skip, not a failure.
    checks.push({
      name: `${engineName}: engine launches`, ok: true,
      detail: `skipped — could not launch (install with: npx playwright install ${engineName})`,
    });
    continue;
  }
  results[engineName] = {};
  const context = await browser.newContext();
  const page = await context.newPage();
  for (const [label, w, h] of VIEWPORTS) {
    await page.setViewportSize({ width: w, height: h });
    for (const file of PAGES) {
      await page.goto('file://' + path.join(PREVIEW, file));
      await page.waitForTimeout(500);
      results[engineName][`${file}@${label}`] = await measure(page);
    }
  }
  await browser.close();
  ok(`${engineName}: engine launches`, true);
}

// Every engine must agree with every other: booleans exactly, fixed
// dimensions within 2px (sub-pixel rounding differs per engine).
const engines = Object.keys(results);
if (engines.length >= 2) {
  const base = engines[0];
  for (const other of engines.slice(1)) {
    for (const key of Object.keys(results[base])) {
      const a = results[base][key];
      const b = results[other][key];
      if (!b) { ok(`${other} rendered ${key}`, false, 'no result'); continue; }
      for (const metric of Object.keys(a)) {
        const [va, vb] = [a[metric], b[metric]];
        if (va === null || vb === null) continue;
        const agree = typeof va === 'number'
          ? Math.abs(va - vb) <= 2
          : va === vb;
        ok(`${key} · ${metric}: ${base} agrees with ${other}`, agree,
           `${base}=${va} ${other}=${vb}`);
      }
    }
  }
} else if (engines.length === 1) {
  ok('cross-engine comparison', true,
     'only one engine installed — nothing to compare against');
}

// Per-engine sanity, independent of agreement: no page may overflow
// horizontally in any engine at any width.
for (const engineName of engines) {
  for (const [key, m] of Object.entries(results[engineName])) {
    ok(`${engineName} ${key}: no horizontal overflow`, m.overflow <= 2,
       `scrollWidth exceeds viewport by ${m.overflow}px`);
  }
}

process.stdout.write(JSON.stringify({ checks }));
process.exit(checks.every(c => c.ok) ? 0 : 1);
