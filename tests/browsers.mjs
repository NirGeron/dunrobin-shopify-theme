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

// Blink comes from the installed Google Chrome, so this exercises the browser
// people actually run; Gecko and WebKit are Playwright builds.
const launch = (engineName) => engineName === 'chromium'
  ? ENGINES.chromium.launch({ channel: 'chrome' }).catch(() => ENGINES.chromium.launch())
  : ENGINES[engineName].launch();

async function openSession(engineName) {
  const browser = await launch(engineName);
  const page = await (await browser.newContext()).newPage();
  return { browser, page };
}

// The Chrome that Playwright drives is sometimes closed from outside, at a
// random page, by the OS or a managed-device policy. That is a fault in the
// machine, not in the theme, so a browser that disappears is relaunched and
// only the page it died on is measured again. Anything else still fails the
// run, and an engine that dies MAX_ATTEMPTS times on one page is reported as
// a failure rather than skipped, so a real crash on a page cannot hide here.
const BROWSER_GONE = /has been closed|Target closed|Page crashed|browser has disconnected/i;
const MAX_ATTEMPTS = 3;

const results = {}; // engine -> "page@label" -> metrics
for (const engineName of Object.keys(ENGINES)) {
  let session;
  try {
    session = await openSession(engineName);
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
  let gaveUpOn = null;
  measuring:
  for (const [label, w, h] of VIEWPORTS) {
    for (const file of PAGES) {
      const key = `${file}@${label}`;
      for (let attempt = 1; ; attempt++) {
        let relaunching = false;
        try {
          if (!session) {
            relaunching = true;
            session = await openSession(engineName);
            relaunching = false;
          }
          await session.page.setViewportSize({ width: w, height: h });
          await session.page.goto('file://' + path.join(PREVIEW, file));
          await session.page.waitForTimeout(500);
          results[engineName][key] = await measure(session.page);
          break;
        } catch (e) {
          if (!relaunching && !BROWSER_GONE.test(String(e.message))) throw e;
          await session?.browser.close().catch(() => {});
          session = null;
          // run.py reads these lines so a flaky machine shows up in its report.
          console.error(`retry: ${engineName} closed on ${key} (attempt ${attempt} of ${MAX_ATTEMPTS})`);
          if (attempt === MAX_ATTEMPTS) {
            gaveUpOn = key;
            break measuring;
          }
        }
      }
    }
  }
  if (session) await session.browser.close().catch(() => {});
  if (gaveUpOn) {
    // Partial results would turn into spurious "no result" failures in the
    // comparison below, so this engine drops out of it.
    delete results[engineName];
    ok(`${engineName}: browser stays open`, false,
       `closed ${MAX_ATTEMPTS} times in a row on ${gaveUpOn}`);
    continue;
  }
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
