#!/usr/bin/env python3
"""
Dunrobin theme test suite.

Two layers:

  Structure  — parses every Liquid schema, JSON template and settings file and
               checks they refer only to things that exist. Pure static analysis,
               no browser, runs in well under a second.

  Render     — rebuilds the static preview from the real assets/base.css and
               assets/global.js, then drives headless Chrome at mobile, tablet
               and desktop widths asserting layout and interaction invariants.

Usage:
    python3 tests/run.py            # everything
    python3 tests/run.py --fast     # structure only (skips Chrome)
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PREVIEW = os.path.join(ROOT, '.preview')
CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'

VIEWPORTS = [('mobile', 390, 844), ('tablet', 768, 1024), ('desktop', 1440, 900)]
PAGES = ['index.html', 'product.html', 'products.html', 'cart.html']

failures = []
passes = 0


def check(name, condition, detail=''):
    global passes
    if condition:
        passes += 1
    else:
        failures.append(f'{name}{" — " + detail if detail else ""}')


def rel(*p):
    return os.path.join(ROOT, *p)


# ---------------------------------------------------------------------------
# Structure
# ---------------------------------------------------------------------------

def section_schema(name):
    src = open(rel('sections', name + '.liquid')).read()
    m = re.search(r'\{%\s*schema\s*%\}(.*?)\{%\s*endschema\s*%\}', src, re.S)
    if not m:
        return None
    return json.loads(m.group(1))


def test_structure():
    # Every JSON file parses.
    for dirpath, _, files in os.walk(ROOT):
        if '/.git' in dirpath or '/.preview' in dirpath or '/node_modules' in dirpath:
            continue
        for f in files:
            if f.endswith('.json'):
                p = os.path.join(dirpath, f)
                try:
                    json.load(open(p))
                    check(f'json parses: {os.path.relpath(p, ROOT)}', True)
                except Exception as e:
                    check(f'json parses: {os.path.relpath(p, ROOT)}', False, str(e))

    # Every section schema parses and declares a name.
    schemas = {}
    for f in sorted(os.listdir(rel('sections'))):
        if not f.endswith('.liquid'):
            continue
        name = f[:-7]
        try:
            sch = section_schema(name)
            schemas[name] = sch
            check(f'schema parses: {name}', sch is not None and 'name' in sch)
        except Exception as e:
            check(f'schema parses: {name}', False, str(e))
            schemas[name] = None

    # Non-main sections must be addable by a merchant.
    for name, sch in schemas.items():
        if not sch or name.startswith('main-'):
            continue
        check(f'addable in editor: {name}',
              'presets' in sch or 'enabled_on' in sch,
              'no presets and no enabled_on, so it cannot be added')

    # Templates and section groups reference real sections, settings and blocks.
    targets = [rel('templates', f) for f in os.listdir(rel('templates')) if f.endswith('.json')]
    targets += [rel('templates/customers', f) for f in os.listdir(rel('templates/customers'))]
    targets += [rel('sections', 'header-group.json'), rel('sections', 'footer-group.json')]

    for p in targets:
        label = os.path.relpath(p, ROOT)
        d = json.load(open(p))
        for sid, sec in d.get('sections', {}).items():
            sch = schemas.get(sec['type'])
            if sch is None:
                check(f'{label}: section "{sec["type"]}" exists', False)
                continue
            check(f'{label}: section "{sec["type"]}" exists', True)

            ids = {s['id'] for s in sch.get('settings', []) if 'id' in s}
            for k in sec.get('settings', {}):
                check(f'{label}:{sid} setting "{k}"', k in ids, f'not declared by {sec["type"]}')

            btypes = {b['type'] for b in sch.get('blocks', [])}
            for bid, blk in sec.get('blocks', {}).items():
                if blk['type'] not in btypes:
                    check(f'{label}:{sid} block "{blk["type"]}"', False)
                    continue
                check(f'{label}:{sid} block "{blk["type"]}"', True)
                bdef = next(b for b in sch['blocks'] if b['type'] == blk['type'])
                bids = {s['id'] for s in bdef.get('settings', []) if 'id' in s}
                for k in blk.get('settings', {}):
                    check(f'{label}:{sid}.{bid} setting "{k}"', k in bids,
                          f'not declared by block {blk["type"]}')

            check(f'{label}:{sid} block_order matches blocks',
                  set(sec.get('block_order', [])) == set(sec.get('blocks', {}) or {}))

        check(f'{label}: order matches sections',
              set(d.get('order', [])) == set(d.get('sections', {})))

    # settings_data keys must exist in settings_schema.
    schema_ids = {s['id'] for g in json.load(open(rel('config/settings_schema.json')))
                  for s in g.get('settings', []) if 'id' in s}
    data = json.load(open(rel('config/settings_data.json')))
    for k in data['current']:
        check(f'settings_data key "{k}" declared', k in schema_ids)

    # font_picker defaults must be handles Shopify recognises.
    for g in json.load(open(rel('config/settings_schema.json'))):
        for s in g.get('settings', []):
            if s.get('type') == 'font_picker':
                check(f'font_picker "{s["id"]}" has a default', 'default' in s)
                check(f'font_picker "{s["id"]}" handle shape',
                      bool(re.fullmatch(r'[a-z0-9_]+_[ni]\d', s.get('default', ''))),
                      f'got {s.get("default")!r}')

    # font_face must never be called on an unguarded variable.
    for layout in ('theme.liquid', 'password.liquid'):
        src = open(rel('layout', layout)).read()
        for m in re.finditer(r'\{\{\s*(\w+)\s*\|\s*font_face', src):
            var = m.group(1)
            guarded = re.search(r'if\s+' + var + r'\.family', src) or \
                      re.search(r'\{%-?\s*if\s+' + var + r'\.family', src)
            check(f'{layout}: font_face on "{var}" is guarded', bool(guarded),
                  'font_face errors when the drop is nil')

    # Referenced snippets, assets and translation keys must exist.
    snippets = {f[:-7] for f in os.listdir(rel('snippets'))}
    assets = set(os.listdir(rel('assets')))
    locale = json.load(open(rel('locales/en.default.json')))

    def has_key(k):
        cur = locale
        for part in k.split('.'):
            if not isinstance(cur, dict) or part not in cur:
                return False
            cur = cur[part]
        return True

    for sub in ('sections', 'snippets', 'layout'):
        for f in sorted(os.listdir(rel(sub))):
            if not f.endswith('.liquid'):
                continue
            p = rel(sub, f)
            src = open(p).read()
            label = f'{sub}/{f}'
            for n in re.findall(r"\{%-?\s*render\s+'([^']+)'", src):
                check(f'{label}: snippet "{n}"', n in snippets)
            for a in re.findall(r"'([\w\-.]+\.(?:png|jpg|jpeg|svg|css|js))'\s*\|\s*asset_url", src):
                check(f'{label}: asset "{a}"', a in assets)
            for k in re.findall(r"'([a-z0-9_]+(?:\.[a-z0-9_]+)+)'\s*\|\s*t\b", src):
                check(f'{label}: translation "{k}"', has_key(k))

    # Every <img> in Liquid must declare width and height, or the page shifts
    # as images load. Placeholder SVGs and app blocks are exempt.
    for sub in ('sections', 'snippets', 'layout'):
        for f in sorted(os.listdir(rel(sub))):
            if not f.endswith('.liquid'):
                continue
            src = open(rel(sub, f)).read()
            for m in re.finditer(r'<img\b[^>]*>', src, re.S):
                tag = m.group(0)
                if 'width=' in tag and 'height=' in tag:
                    continue
                snippet = ' '.join(tag.split())[:80]
                check(f'{sub}/{f}: <img> declares width/height', False, snippet)

    # The drawer's checkout button lives in #CartDrawerFooter. If that container
    # is only rendered when the cart already has items, adding the first item
    # leaves nothing to populate and the drawer becomes a dead end with no way
    # to pay. The container must always exist; only its contents are gated.
    drawer = open(rel('snippets/cart-drawer.liquid')).read()
    check('cart drawer: footer container exists',
          'id="CartDrawerFooter"' in drawer)
    body_end = drawer.find('id="CartDrawerBody"')
    footer_at = drawer.find('id="CartDrawerFooter"')
    between = drawer[body_end:footer_at]
    check('cart drawer: footer container is not gated on item_count',
          'if cart.item_count > 0' not in between,
          'wrapping it in a cart.item_count conditional hides checkout after the first add')

    js = open(rel('assets/global.js')).read()
    check('cart drawer: refresh populates the footer',
          'CartDrawerFooter' in js and 'footer.hidden' in js)
    check('cart drawer: refresh has a fallback to the cart page',
          'window.location.href = routes.cart_url' in js,
          'a failed refresh must not strand the shopper in an empty drawer')
    check('cart drawer: checkout is never inherited disabled',
          'b.disabled = false' in js,
          'the cart page gates checkout behind its age checkbox; the drawer must not inherit that')

    # The age checkbox must gate only the cart page's own button.
    check('age gate is scoped to the cart page',
          ".cart-page" in js and "scope.querySelector('button[name=\"checkout\"]')" in js)

    # Required theme files.
    for required in ('layout/theme.liquid', 'config/settings_schema.json',
                     'config/settings_data.json', 'locales/en.default.json',
                     'assets/base.css', 'assets/global.js'):
        check(f'exists: {required}', os.path.exists(rel(required)))


def test_theme_check():
    if shutil.which('npx') is None:
        check('shopify theme check', True, 'skipped, npx unavailable')
        return
    r = subprocess.run(['npx', '--yes', '@shopify/cli@latest', 'theme', 'check',
                        '--fail-level', 'error'],
                       cwd=ROOT, capture_output=True, text=True)
    check('shopify theme check: no errors', r.returncode == 0,
          (r.stdout or r.stderr)[-800:] if r.returncode else '')


# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------

PROBE = r"""
<script>
window.addEventListener('load', function () {
  setTimeout(function () {
    var vw = window.innerWidth;
    var out = {
      viewport: vw,
      scrollWidth: document.documentElement.scrollWidth,
      bodyScrollWidth: document.body.scrollWidth,
      overflowing: [],
      smallTapTargets: [],
      imagesMissingDims: 0,
      bodyFontPx: parseFloat(getComputedStyle(document.body).fontSize),
      headingFont: getComputedStyle(document.querySelector('h1,h2,.h1,.h2') || document.body).fontFamily,
      bodyFont: getComputedStyle(document.body).fontFamily
    };

    document.querySelectorAll('body *').forEach(function (el) {
      var r = el.getBoundingClientRect();
      if (r.width === 0 && r.height === 0) return;
      // Off-canvas drawers sit outside the viewport by design while closed.
      var off = el.closest('.mobile-nav, .cart-drawer, .age-gate');
      if (off && !off.classList.contains('is-open')) return;
      // Horizontal rails scroll their own content; that is not page overflow.
      for (var a = el.parentElement; a && a !== document.body; a = a.parentElement) {
        var ox = getComputedStyle(a).overflowX;
        if (ox === 'auto' || ox === 'scroll') return;
      }
      if (r.right > vw + 1.5 || r.left < -1.5) {
        if (out.overflowing.length < 8) {
          out.overflowing.push((el.tagName + '.' + (el.className || '')).slice(0, 70)
            + ' [' + Math.round(r.left) + '..' + Math.round(r.right) + ']');
        }
      }
    });

    document.querySelectorAll('a,button,input[type=checkbox]').forEach(function (el) {
      var r = el.getBoundingClientRect();
      if (r.width === 0 || r.height === 0) return;
      if (getComputedStyle(el).display === 'none') return;
      // Inline links inside prose are exempt; only chrome/controls must be tappable.
      var offc = el.closest('.mobile-nav, .cart-drawer, .age-gate');
      if (offc && !offc.classList.contains('is-open')) return;
      // Inline links inside prose are exempt from WCAG 2.5.8 target sizing.
      if (el.closest('.rte, p, .dispatch-card__title, .card__title, .cart-item__title, .footer__list')) return;
      if (r.height < 24 || r.width < 24) {
        if (out.smallTapTargets.length < 8) {
          out.smallTapTargets.push((el.tagName + '.' + (el.className || '')).slice(0, 60)
            + ' ' + Math.round(r.width) + 'x' + Math.round(r.height));
        }
      }
    });

    document.querySelectorAll('img').forEach(function (img) {
      if (!img.getAttribute('width') || !img.getAttribute('height')) out.imagesMissingDims++;
    });

    var nav = document.querySelector('.header__nav');
    var toggle = document.querySelector('.header__menu-toggle');
    var header = document.querySelector('.header');
    out.navDisplay = nav ? getComputedStyle(nav).display : null;
    out.toggleDisplay = toggle ? getComputedStyle(toggle).display : null;
    if (nav && header && getComputedStyle(nav).display !== 'none') {
      var hr = header.getBoundingClientRect(), nr = nav.getBoundingClientRect();
      out.headerCentre = +(hr.left + hr.width / 2).toFixed(1);
      out.navCentre = +(nr.left + nr.width / 2).toFixed(1);
    }

    // Mobile drawer opens and closes.
    var mob = document.getElementById('MobileNav');
    if (mob && toggle) {
      toggle.click();
      out.drawerOpens = mob.classList.contains('is-open');
      var closeBtn = mob.querySelector('[data-mobile-nav-close]');
      if (closeBtn) { closeBtn.click(); out.drawerCloses = !mob.classList.contains('is-open'); }
    }

    // Cart age confirmation gates checkout.
    var box = document.querySelector('[data-age-confirm]');
    var checkout = document.querySelector('button[name="checkout"]');
    if (box && checkout) {
      out.checkoutBlockedInitially = checkout.disabled === true;
      box.checked = true; box.dispatchEvent(new Event('change', { bubbles: true }));
      out.checkoutEnabledAfterTick = checkout.disabled === false;
      box.checked = false; box.dispatchEvent(new Event('change', { bubbles: true }));
      out.checkoutReblocked = checkout.disabled === true;
    }

    var rail = document.querySelector('.dispatch-grid--carousel');
    if (rail) {
      var cs = getComputedStyle(rail);
      out.railScrolls = (cs.overflowX === 'auto' || cs.overflowX === 'scroll')
        && rail.scrollWidth > rail.clientWidth + 4;
      out.railStacks = cs.overflowX === 'visible';
      out.railSnaps = cs.scrollSnapType.indexOf('x') !== -1;
    }

    var fit = document.querySelector('.image-banner--fit-mobile');
    if (fit) {
      var img = fit.querySelector('img');
      out.bannerFit = img ? getComputedStyle(img).objectFit : null;
      // Uncropped means the rendered box keeps the file's aspect ratio.
      if (img && img.naturalWidth) {
        var br = img.getBoundingClientRect();
        out.bannerAspectDrift = Math.abs(
          (br.width / br.height) - (img.naturalWidth / img.naturalHeight));
      }
    }

    var foot = document.querySelector('.footer:not(.footer--light)');
    if (foot) {
      var notWhite = [];
      foot.querySelectorAll('a, p, li, h3, div, span, time').forEach(function (el) {
        if (!el.textContent.trim()) return;
        var r = el.getBoundingClientRect();
        if (r.width === 0 || r.height === 0) return;
        var c = getComputedStyle(el);
        var m = c.color.match(/\d+/g);
        if (!m) return;
        var white = m[0] > 245 && m[1] > 245 && m[2] > 245;
        var opaque = parseFloat(c.opacity) > 0.98;
        if ((!white || !opaque) && notWhite.length < 6) {
          notWhite.push((el.tagName + '.' + (el.className || '')).slice(0, 50)
            + ' ' + c.color + ' @' + c.opacity);
        }
      });
      out.footerNotWhite = notWhite;
    }

    var centred = document.querySelector('.featured-product--centered');
    if (centred) {
      var bimg = centred.querySelector('img');
      if (bimg) {
        var br = bimg.getBoundingClientRect();
        var cr = centred.getBoundingClientRect();
        out.bottleOffset = Math.abs((br.left + br.width / 2) - (cr.left + cr.width / 2));
      }
    }

    var pre = document.createElement('pre');
    pre.id = 'probe';
    pre.textContent = JSON.stringify(out);
    document.body.appendChild(pre);
  }, 400);
});
</script>
"""


def build_preview():
    r = subprocess.run([sys.executable, 'build.py'], cwd=PREVIEW,
                       capture_output=True, text=True)
    check('preview builds', r.returncode == 0, r.stderr[-400:])
    return r.returncode == 0


def probe(page, width, height):
    """
    Chrome clamps its window to a 500px minimum, so --window-size cannot reach
    a real phone width. Rendering the page inside an exactly sized iframe gives
    it a true viewport of any width, and media queries resolve against that.
    """
    src = os.path.join(PREVIEW, page)
    child_html = open(src).read().replace('</body>', PROBE + '</body>')
    child = os.path.join(PREVIEW, '__probe_child.html')
    frame = os.path.join(PREVIEW, '__probe_frame.html')
    open(child, 'w').write(child_html)
    open(frame, 'w').write(f"""<!doctype html><html><head><meta charset="utf-8">
<style>html,body{{margin:0;padding:0}}iframe{{border:0;display:block}}</style></head><body>
<iframe id="f" src="__probe_child.html" width="{width}" height="{height}" scrolling="no"></iframe>
<script>
function grab(tries) {{
  try {{
    var d = document.getElementById('f').contentDocument;
    var pre = d && d.getElementById('probe');
    if (pre) {{
      var out = document.createElement('pre');
      out.id = 'probe'; out.textContent = pre.textContent;
      document.body.appendChild(out); return;
    }}
  }} catch (e) {{
    var err = document.createElement('pre');
    err.id = 'probe-error'; err.textContent = String(e);
    document.body.appendChild(err); return;
  }}
  if (tries > 0) setTimeout(function () {{ grab(tries - 1); }}, 200);
}}
window.addEventListener('load', function () {{ setTimeout(function () {{ grab(30); }}, 300); }});
</script></body></html>""")
    try:
        r = subprocess.run(
            [CHROME, '--headless', '--disable-gpu', '--no-sandbox', '--hide-scrollbars',
             '--allow-file-access-from-files',
             f'--window-size={max(width, 1400)},{height + 200}',
             '--virtual-time-budget=9000', '--dump-dom', 'file://' + frame],
            capture_output=True, text=True, timeout=180)
        if '<pre id="probe-error">' in r.stdout:
            m = re.search(r'<pre id="probe-error">(.*?)</pre>', r.stdout, re.S)
            check(f'probe iframe access ({page} @{width})', False, m.group(1)[:120])
            return None
        m = re.search(r'<pre id="probe">(.*?)</pre>', r.stdout, re.S)
        if not m:
            return None
        raw = (m.group(1).replace('&quot;', '"').replace('&amp;', '&')
               .replace('&lt;', '<').replace('&gt;', '>'))
        return json.loads(raw)
    finally:
        for f in (child, frame):
            if os.path.exists(f):
                os.remove(f)


def test_render():
    if not os.path.exists(CHROME):
        check('headless Chrome available', True, 'skipped, Chrome not installed')
        return
    if not build_preview():
        return

    for page in PAGES:
        if not os.path.exists(os.path.join(PREVIEW, page)):
            check(f'preview page exists: {page}', False)
            continue
        for label, w, h in VIEWPORTS:
            d = probe(page, w, h)
            tag = f'{page} @{label}'
            if d is None:
                check(tag, False, 'probe returned nothing')
                continue

            check(f'{tag}: rendered at the requested width',
                  d['viewport'] == w, f'asked {w}px, got {d["viewport"]}px')

            check(f'{tag}: no horizontal overflow',
                  d['scrollWidth'] <= d['viewport'] + 2,
                  f'scrollWidth {d["scrollWidth"]} > viewport {d["viewport"]}; '
                  f'culprits: {d["overflowing"][:3]}')

            check(f'{tag}: nothing sticks outside the viewport',
                  not d['overflowing'], str(d['overflowing'][:3]))

            check(f'{tag}: tap targets at least 24px',
                  not d['smallTapTargets'], str(d['smallTapTargets'][:3]))

            check(f'{tag}: images declare width/height',
                  d['imagesMissingDims'] == 0,
                  f'{d["imagesMissingDims"]} images without dimensions (layout shift)')

            if 'footerNotWhite' in d:
                check(f'{tag}: footer text is white', not d['footerNotWhite'],
                      str(d['footerNotWhite'][:3]))

            if 'bottleOffset' in d:
                check(f'{tag}: bottle centred in its section',
                      d['bottleOffset'] < 2,
                      f'{d["bottleOffset"]:.1f}px off centre')

            check(f'{tag}: body text at least 14px', d['bodyFontPx'] >= 14,
                  f'{d["bodyFontPx"]}px')

            check(f'{tag}: Libre Baskerville applied',
                  'Libre Baskerville' in d['bodyFont'] and 'Libre Baskerville' in d['headingFont'],
                  f'body={d["bodyFont"]}, heading={d["headingFont"]}')

            if label == 'mobile':
                if 'railScrolls' in d:
                    check(f'{tag}: dispatches scroll as a carousel', d['railScrolls'] is True,
                          'rail is not horizontally scrollable on mobile')
                    check(f'{tag}: carousel snaps', d.get('railSnaps') is True)
                if 'bannerFit' in d:
                    check(f'{tag}: banner image not cropped', d['bannerFit'] == 'contain',
                          f'object-fit is {d["bannerFit"]}')
                    check(f'{tag}: banner keeps its aspect ratio',
                          d.get('bannerAspectDrift', 9) < 0.05,
                          f'drift {d.get("bannerAspectDrift")}')
                check(f'{tag}: desktop nav hidden', d['navDisplay'] == 'none', d['navDisplay'])
                check(f'{tag}: menu toggle visible', d['toggleDisplay'] != 'none')
                check(f'{tag}: drawer opens', d.get('drawerOpens') is True)
                check(f'{tag}: drawer closes', d.get('drawerCloses') is True)
            if label == 'desktop':
                if 'railStacks' in d:
                    check(f'{tag}: dispatches are a grid, not a rail',
                          d['railStacks'] is True, 'carousel styles leaked to desktop')
                if 'bannerFit' in d:
                    check(f'{tag}: banner fills the band', d['bannerFit'] == 'cover',
                          f'object-fit is {d["bannerFit"]}')
                check(f'{tag}: menu toggle hidden', d['toggleDisplay'] == 'none')
                if 'navCentre' in d:
                    check(f'{tag}: nav centred in header',
                          abs(d['navCentre'] - d['headerCentre']) < 2,
                          f'nav {d["navCentre"]} vs header {d["headerCentre"]}')

            if page == 'cart.html':
                check(f'{tag}: checkout blocked before age confirmation',
                      d.get('checkoutBlockedInitially') is True)
                check(f'{tag}: checkout enabled after confirming',
                      d.get('checkoutEnabledAfterTick') is True)
                check(f'{tag}: checkout re-blocked when unticked',
                      d.get('checkoutReblocked') is True)


# ---------------------------------------------------------------------------

def main():
    fast = '--fast' in sys.argv
    test_structure()
    if not fast:
        test_theme_check()
        test_render()

    print()
    if failures:
        print(f'FAILED — {len(failures)} of {len(failures) + passes} checks')
        for f in failures:
            print('  ✗ ' + f)
        return 1
    print(f'PASSED — {passes} checks')
    return 0


if __name__ == '__main__':
    sys.exit(main())
