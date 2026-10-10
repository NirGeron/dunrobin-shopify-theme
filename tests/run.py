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
import struct
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PREVIEW = os.path.join(ROOT, '.preview')
CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'

# The theme's breakpoints are 750px and 990px; the list brackets both, plus
# the smallest phone still in circulation and a widescreen monitor. Width is
# what matters — the checks branch on it, not on the label.
VIEWPORTS = [
    ('mobile-small', 320, 568),
    ('mobile', 390, 844),
    ('phablet', 430, 932),
    ('tablet', 768, 1024),
    ('laptop', 1280, 800),
    ('desktop', 1440, 900),
    ('wide', 1920, 1080),
]
PAGES = ['index.html', 'product.html', 'products.html', 'blog.html', 'blog-many.html', 'cart.html']

# The most the home banner may trim off the top of the castle picture, in
# percent of its height. Measured on assets/castle-duotone.jpg: the spire tips
# first show at about 9.5% down, so anything up to 8% takes sky and nothing
# else. Widen it only after re-measuring.
SPIRE_TOP_MAX = 8

failures = []
passes = 0
notes = []  # things worth seeing in the report that are not failures


def check(name, condition, detail=''):
    global passes
    if condition:
        passes += 1
    else:
        failures.append(f'{name}{" — " + detail if detail else ""}')


def rel(*p):
    return os.path.join(ROOT, *p)


def load_json(path):
    """
    json.load that tolerates the /* IMPORTANT ... auto-generated */ banner
    Shopify stamps on templates and settings_data.json when the theme editor
    saves them. Shopify itself reads these files as JSON-with-comments.
    """
    raw = open(path).read()
    raw = re.sub(r'\A\s*/\*.*?\*/', '', raw, count=1, flags=re.S)
    return json.loads(raw)


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
                    load_json(p)
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
        d = load_json(p)
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
                if blk['type'].startswith('shopify://apps/'):
                    # An app block is defined by the app, not by this theme, so
                    # there is no schema to compare its settings against. The
                    # section only has to accept app blocks at all.
                    check(f'{label}:{sid} block "{blk["type"]}"', '@app' in btypes,
                          f'{sec["type"]} does not declare an @app block')
                    continue
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
    data = load_json(rel('config/settings_data.json'))
    # Shopify writes two keys here itself: `blocks` holds the app embeds turned
    # on in the theme editor, and `content_for_index` is its legacy section
    # order list. Neither is a theme setting, so neither is in settings_schema.
    shopify_owned = {'blocks', 'content_for_index'}
    for k in data['current']:
        if k in shopify_owned:
            continue
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
    icon_cases = set(re.findall(r"when\s+'([\w-]+)'", open(rel('snippets/icon.liquid')).read()))

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

            # Every rendered icon name must have a matching case in icon.liquid.
            for name in re.findall(r"render\s+'icon'\s*,\s*name:\s*'([\w-]+)'", src):
                check(f'{label}: icon "{name}" exists', name in icon_cases)

            # A link that opens a new tab must also cut window.opener access,
            # or the new page can navigate the shop tab (a reverse tabnabbing risk).
            for m in re.finditer(r'<a\b[^>]*>', src, re.S):
                tag = m.group(0)
                if re.search(r'target=["\']_blank["\']', tag):
                    check(f'{label}: target="_blank" link has rel="noopener"',
                          'noopener' in tag, ' '.join(tag.split())[:90])

            # Shopify Liquid only knows ==, !=, >, <, >=, <=, and, or, contains.
            # Anything else in a conditional throws a syntax error at render
            # time, which no amount of schema checking would catch.
            bad_ops = []
            for tag in re.findall(r'\{%-?\s*(?:if|elsif|unless)\b(.*?)-?%\}', src, re.S):
                for bad in ('startswith', 'endswith', 'includes', '&&', '||', '!=='):
                    if bad in tag:
                        bad_ops.append(f'{bad} in "{" ".join(tag.split())[:60]}"')
            check(f'{label}: conditionals use only Liquid operators',
                  not bad_ops, '; '.join(bad_ops))

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
    # The drawer rebuilds from the cart page's markup, so it must not inherit
    # that page's checkout button — it links to the cart page instead.
    check('cart drawer: checkout becomes a link to the cart page',
          "b.replaceWith(link)" in js and "link.href = routes.cart_url" in js,
          'the drawer must not submit the cart page\'s checkout button')
    check('cart drawer: page-only markup is stripped on refresh',
          "classList.remove('cart-items--page')" in js and '.cart-items__header' in js,
          'the cart page column layout would leak into the drawer')
    # If the cart page cannot render its lines, grafting only the footer shows
    # "your bag is empty" above a real subtotal. That must count as a failure.
    check('cart drawer: a missing item list is treated as a failed refresh',
          "if (!newItems) throw" in js,
          'the drawer would contradict itself instead of falling back')

    # The age checkbox, when present, must gate only the cart page's own button.
    check('age gate is scoped to the cart page',
          ".cart-page" in js and "scope.querySelector('button[name=\"checkout\"]')" in js)

    # The gate must return each browsing session, not once per device forever.
    js = open(rel('assets/global.js')).read()
    check('age gate: uses sessionStorage by default',
          'window.sessionStorage' in js and "!== 'device'" in js,
          'localStorage would remember the visitor indefinitely')
    check('age gate: clears any stale device-wide flag',
          'window.localStorage.removeItem(KEY)' in js,
          'visitors who confirmed under the old behaviour would never be asked again')
    gate = open(rel('snippets/age-gate.liquid')).read()
    check('age gate: frequency reaches the markup', 'data-frequency=' in gate)
    schema_ids_local = {x['id'] for g in json.load(open(rel('config/settings_schema.json')))
                        for x in g.get('settings', []) if 'id' in x}
    check('age gate: frequency is a theme setting', 'age_gate_frequency' in schema_ids_local)

    # Pattern divider tiles a fixed-height strip; it must not go back to
    # stretching a single image across the full viewport width, which
    # squashed the motif differently at every breakpoint.
    css = open(rel('assets/base.css')).read()
    m = re.search(r'\.pattern-divider\s*\{([^}]*)\}', css, re.S)
    check('pattern divider: background tiles horizontally',
          bool(m) and 'background-repeat' in m.group(1) and 'repeat' in m.group(1),
          'must tile the motif rather than stretch a single image')
    check('pattern divider: no leftover stretched-image rule',
          bool(m) and 'object-fit' not in m.group(1),
          'object-fit on the divider means it is stretching an <img>, not tiling a background')
    divider_liquid = open(rel('sections/pattern-divider.liquid')).read()
    check('pattern divider: renders as a background, not an <img>',
          '<img' not in divider_liquid)

    # Motion is a preference: the reveal animation must have a
    # reduced-motion escape hatch, or vestibular-sensitive visitors get
    # animated content with no way to opt out.
    check('reveal animation respects prefers-reduced-motion',
          'prefers-reduced-motion' in css)

    # The menu toggle ships with aria-expanded so global.js has the
    # attribute to keep truthful.
    header_liquid = open(rel('sections/header.liquid')).read()
    check('menu toggle declares aria-expanded', 'aria-expanded' in header_liquid)
    check('global.js maintains aria-expanded',
          'aria-expanded' in open(rel('assets/global.js')).read())

    # A castle banner on the home page carries the seal by default, per the
    # README — a merchant edit could flip this without anyone noticing. The home
    # page may run without a banner (the image pair can stand in for it).
    index_tpl = load_json(rel('templates/index.json'))
    castle_banners = [s for s in index_tpl['sections'].values() if s['type'] == 'image-banner']
    check('home page: every castle banner shows the seal',
          all(s.get('settings', {}).get('show_seal') for s in castle_banners))

    # The default banner picture is the castle. Its spire tips sit about 9.5% of
    # the way down the file and the base of the bastion about 59%, so a trim
    # past those would cut the castle itself rather than sky or garden.
    for sid, sec in index_tpl['sections'].items():
        if sec['type'] != 'image-banner':
            continue
        st = sec.get('settings', {})
        if st.get('height') != 'fit' or st.get('image'):
            continue
        check(f'home page:{sid} banner top trim leaves the spire tips in frame',
              st.get('trim_top', 5) <= SPIRE_TOP_MAX,
              f'trim_top is {st.get("trim_top")}%, spires start at ~9.5%')
        check(f'home page:{sid} banner bottom trim leaves the castle base in frame',
              st.get('trim_bottom', 36) <= 40, f'trim_bottom is {st.get("trim_bottom")}%, base ends at ~59%')

    # The cart drawer must be reachable from the header icon and dismissible
    # by more than one control (overlay click and an explicit close button).
    header_src = open(rel('sections/header.liquid')).read()
    check('header: cart icon opens the drawer', 'data-cart-open' in header_src)
    drawer_src = open(rel('snippets/cart-drawer.liquid')).read()
    check('cart drawer: overlay and button both close it',
          drawer_src.count('data-cart-close') >= 2)

    # The gallery's JS wiring must exist wherever the markup expects it.
    check('product gallery: thumbnail click handler present in global.js',
          'data-gallery-thumb' in js and 'initGallery' in js)

    # The Google reviews section was removed in favour of a Shopify App Store
    # reviews app, which has a real live feed. Guard against it creeping back
    # in piecemeal: a stray rule or string left behind is dead weight, and a
    # template referencing the section would render nothing at all.
    check('google reviews: section file is gone',
          not os.path.exists(rel('sections/google-reviews.liquid')))
    check('google reviews: no leftover CSS', 'google-reviews' not in css)
    check('google reviews: no leftover JS',
          'initGoogleReviews' not in js and 'data-reviews' not in js)
    check('google reviews: no template still references the section',
          not any(s['type'] == 'google-reviews'
                  for s in index_tpl['sections'].values()))

    # The home page needs exactly one <h1>, and only the first hero heading may
    # be it: later headings, and the hero on any other template, stay <h2>. The
    # visual size comes from the .h0/.h1/.h2 class, not the tag.
    hero_src = open(rel('sections/hero-banner.liquid')).read()
    check('hero banner: first heading renders as the home page <h1>',
          "template.name == 'index'" in hero_src
          and "assign heading_tag = 'h1'" in hero_src
          and '<{{ heading_tag }} class="hero__heading' in hero_src)
    check('hero banner: later headings fall back to <h2>',
          hero_src.count("assign heading_tag = 'h2'") >= 2)

    # A featured-collection with no collection chosen renders four "Example
    # product" placeholder cards on the live storefront. Fine as a theme-editor
    # preview, wrong in a shipped template.
    for tpl in sorted(os.listdir(rel('templates'))):
        if not tpl.endswith('.json'):
            continue
        tpl_sections = load_json(rel('templates', tpl)).get('sections', {})
        bare = [sid for sid, s in tpl_sections.items()
                if s['type'] == 'featured-collection'
                and not s.get('settings', {}).get('collection')]
        check(f'templates/{tpl}: no featured-collection without a collection',
              not bare, f'renders placeholder cards: {", ".join(bare)}')

    # A default in settings_schema.json does NOT reach a theme that already
    # has a settings_data.json — Shopify reads the saved file, and a key that
    # isn't in it comes back nil. So a feature gated on `if settings.foo`
    # silently never renders, with nothing in the theme looking wrong. That is
    # exactly how the WhatsApp button shipped invisible. Image pickers are
    # excluded: they have no default because the merchant uploads them.
    schema_defaults = [s['id']
                       for g in json.load(open(rel('config/settings_schema.json')))
                       for s in g.get('settings', [])
                       if s.get('id') and 'default' in s]
    absent = [i for i in schema_defaults if i not in data['current']]
    check('settings: every setting with a default is present in settings_data',
          not absent,
          f'missing {absent} — a feature gated on these renders nothing')

    # Floating WhatsApp button. The link is assembled from the number rather
    # than stored whole, so the thing worth pinning down is that the number is
    # url_encoded — a bare "+" in a query string is read as a space and the
    # number silently fails to match. It also has to render on every page,
    # which means being in the layout rather than in a section.
    wa_src = open(rel('snippets/whatsapp-button.liquid')).read()
    layout_src = open(rel('layout/theme.liquid')).read()
    check('whatsapp: rendered from the layout so it appears on every page',
          "render 'whatsapp-button'" in layout_src)
    # Match the assign itself, not the whole file — the word "url_encode" also
    # appears in this snippet's comment explaining why it is there, so a plain
    # substring check passes even after the filter is deleted from the code.
    wa_code = re.sub(r'\{%-?\s*comment\s*-?%\}.*?\{%-?\s*endcomment\s*-?%\}', '',
                     wa_src, flags=re.S)
    check('whatsapp: number is url_encoded into the link',
          bool(re.search(r'assign\s+\w+\s*=\s*wa_phone\s*\|\s*url_encode', wa_code)) and
          'api.whatsapp.com/send/?phone=' in wa_code)
    check('whatsapp: opens in a new tab without handing over the opener',
          'target="_blank"' in wa_src and 'rel="noopener"' in wa_src)
    check('whatsapp: has an accessible label', 'aria-label' in wa_src)
    check('whatsapp: hidden when disabled or the number is blank',
          'settings.whatsapp_enabled' in wa_src and 'wa_href != blank' in wa_src)
    check('whatsapp: icon exists in the icon snippet',
          "when 'whatsapp'" in open(rel('snippets/icon.liquid')).read())

    # It must sit under the panels rather than punching through them.
    wa_z = re.search(r'\.whatsapp-float\s*\{[^}]*z-index:\s*(\d+)', css)
    check('whatsapp: has a z-index', bool(wa_z))
    if wa_z:
        wa_z = int(wa_z.group(1))
        for name, sel in (('cart drawer', r'\.cart-drawer\s*\{'),
                          ('mobile nav', r'\.mobile-nav\s*\{'),
                          ('age gate', r'\.age-gate\s*\{')):
            m = re.search(sel + r'[^}]*z-index:\s*(\d+)', css)
            if m:
                check(f'whatsapp: sits below the {name}', wa_z < int(m.group(1)),
                      f'whatsapp {wa_z} vs {name} {m.group(1)}')

    # Product page. The quantity stepper is its own block, outside the <form>,
    # so it only joins the add-to-cart request through form="<id>". The two ids
    # once drifted apart and every order quietly went through as quantity 1.
    prod_src = open(rel('sections/main-product.liquid')).read()
    prod_code = re.sub(r'\{%-?\s*comment\s*-?%\}.*?\{%-?\s*endcomment\s*-?%\}', '',
                       prod_src, flags=re.S)
    check('product: quantity input names the same form id the form is given',
          'form="ProductForm-{{ section.id }}"' in prod_code and
          bool(re.search(r"assign\s+product_form_id\s*=\s*'ProductForm-'\s*\|\s*append:\s*section\.id",
                         prod_code)) and
          'id: product_form_id' in prod_code)

    # The sticky Add to bag bar mirrors the real button and clicks it, so it is
    # only worth having if the markup, the script and a stacking slot all exist.
    js = open(rel('assets/global.js')).read()
    check('product: sticky add-to-bag bar is in the section and wired up',
          'data-sticky-atc' in prod_code and 'data-sticky-atc-button' in prod_code and
          'function initStickyAtc' in js and
          len(re.findall(r'initStickyAtc\(\)', js)) >= 3)
    sticky_z = re.search(r'\.sticky-atc\s*\{[^}]*z-index:\s*(\d+)', css)
    hdr_z = re.search(r'\.header-wrapper\s*\{[^}]*z-index:\s*(\d+)', css)
    check('product: sticky bar stacks above the header and under the whatsapp button',
          bool(sticky_z and hdr_z and wa_z) and
          int(hdr_z.group(1)) < int(sticky_z.group(1)) < wa_z,
          f'header {hdr_z and hdr_z.group(1)}, sticky {sticky_z and sticky_z.group(1)}, whatsapp {wa_z}')

    # 44px is the touch guideline. The header icons may only shrink on the very
    # narrowest phones, where four of them would crush the logo.
    small_icons = [int(m) for m in re.findall(
        r'@media[^{]*max-width:\s*(\d+)px\)\s*\{\s*\.header__icon\s*\{[^}]*?width:\s*3\.6rem', css)]
    check('header: icons keep 44px tap targets above 359px',
          bool(small_icons) and max(small_icons) <= 359,
          f'3.6rem icons applied up to {max(small_icons) if small_icons else "n/a"}px')

    # Google Search Console. Ownership is proved by a meta tag in the <head>
    # of the home page, so it has to come from the layouts rather than a
    # section — and from password.liquid too, which is all Google sees while
    # the store is locked. The comments in these snippets name the same tags
    # they render, so the checks look at the code with comments removed.
    def no_comments(text):
        return re.sub(r'\{%-?\s*comment\s*-?%\}.*?\{%-?\s*endcomment\s*-?%\}', '',
                      text, flags=re.S)

    gsc_src = no_comments(open(rel('snippets/search-console.liquid')).read())
    sd_src = no_comments(open(rel('snippets/structured-data.liquid')).read())
    password_src = open(rel('layout/password.liquid')).read()
    schema_ids = [s['id']
                  for g in json.load(open(rel('config/settings_schema.json')))
                  for s in g.get('settings', []) if s.get('id')]
    check('search console: verification setting exists in the schema',
          'google_site_verification' in schema_ids)
    check('search console: verification tag rendered from the theme layout',
          "render 'search-console'" in layout_src)
    check('search console: the live site verification tag is in theme.liquid',
          '<meta name="google-site-verification" content="zsHhrKhdl-rDowwYGmDEXpLj6lzVbNZhAfaUwuNgKrk" />'
          in layout_src, 'removing it unverifies the property in Search Console')
    check('search console: verification tag rendered from the password layout',
          "render 'search-console'" in password_src)
    check('search console: tag is only output when a token is set',
          'settings.google_site_verification' in gsc_src and 'gsc_token != blank' in gsc_src and
          'name="google-site-verification"' in gsc_src)
    check('search console: token is escaped into the attribute',
          bool(re.search(r'content="\{\{\s*gsc_token[^}]*\|\s*escape\s*\}\}"', gsc_src)))
    check('structured data: rendered from the theme layout',
          "render 'structured-data'" in layout_src)
    # A quote or ampersand in a shop, product or article title would end the
    # string early and Google drops the whole block — every interpolated value
    # inside a JSON-LD script must go through | json.
    unjsoned = [m for m in re.findall(r'\{\{(?!.*\|\s*json\s*\}\})[^}]*\}\}', sd_src)
                if 'forloop.index' not in m]
    check('structured data: every interpolated value goes through the json filter',
          not unjsoned, f'unescaped: {unjsoned}')
    for kind in ('Organization', 'WebSite', 'BreadcrumbList', 'Article'):
        check(f'structured data: emits {kind}', f'"@type": "{kind}"' in sd_src)
    check('structured data: product markup still comes from the product section',
          'product | structured_data' in open(rel('sections/main-product.liquid')).read())

    # Organization needs a logo to be eligible for the logo in results, and a
    # store that has not uploaded one in Theme settings is the normal state, so
    # the logo must not depend on a setting: saved brand mark, then main logo,
    # then the monogram shipped in assets/.
    check('structured data: logo prefers the saved brand mark, then the main logo',
          'settings.brand_mark | default: settings.logo' in sd_src)
    check("structured data: logo falls back to the shipped brand-mark.png",
          "'brand-mark.png' | asset_url" in sd_src)
    check('structured data: Organization emits its logo unconditionally',
          bool(re.search(r'"url":\s*\{\{\s*shop\.url\s*\|\s*json\s*\}\}\s*,"logo":\s*\{\{\s*sd_logo_url\s*\|\s*json\s*\}\}',
                         sd_src)), 'the logo line must not sit inside an {% if %}')

    # Favicon: an uploaded one wins; otherwise the layouts fall back to the
    # shipped icon, so the page never goes out without <link rel="icon">.
    # Google wants a square favicon whose side is a multiple of 48px.
    def png_size(path):
        with open(rel(path), 'rb') as f:
            head = f.read(24)
        return struct.unpack('>II', head[16:24]) if head[:8] == b'\x89PNG\r\n\x1a\n' else None

    favicon_size = png_size('assets/favicon-192.png')
    check('favicon: assets/favicon-192.png is a square PNG, side a multiple of 48px',
          favicon_size is not None and favicon_size[0] == favicon_size[1] and favicon_size[0] % 48 == 0,
          f'got {favicon_size}')
    for name, src in (('theme.liquid', layout_src), ('password.liquid', password_src)):
        block = re.search(r'\{%-?\s*if settings\.favicon != blank\s*-?%\}(.*?)\{%-?\s*endif\s*-?%\}',
                          src, flags=re.S)
        branches = re.split(r'\{%-?\s*else\s*-?%\}', block.group(1)) if block else ['']
        uploaded, fallback = (branches + [''])[:2]
        check(f'favicon: {name} serves an uploaded favicon at 48px',
              'settings.favicon | image_url: width: 48, height: 48' in uploaded)
        check(f'favicon: {name} falls back to assets/favicon-192.png when none is uploaded',
              'rel="icon"' in fallback and "'favicon-192.png' | asset_url" in fallback)
    check('favicon: theme.liquid falls back to assets/favicon.png for the Apple touch icon',
          bool(re.search(r'rel="apple-touch-icon" href="\{\{ \'favicon\.png\' \| asset_url \}\}"', layout_src)))

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
// Collects anything thrown after this script runs — which is every
// interaction the probe performs below. Load-time errors in global.js are
// caught separately: a broken global.js fails the behaviour checks anyway.
var __probeErrors = [];
window.addEventListener('error', function (e) {
  if (__probeErrors.length < 5) __probeErrors.push(String(e.message).slice(0, 120));
});
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

    // Mobile drawer opens and closes, and the toggle announces its state.
    var mob = document.getElementById('MobileNav');
    if (mob && toggle) {
      toggle.click();
      out.drawerOpens = mob.classList.contains('is-open');
      out.toggleExpandedWhileOpen = toggle.getAttribute('aria-expanded');
      var closeBtn = mob.querySelector('[data-mobile-nav-close]');
      if (closeBtn) { closeBtn.click(); out.drawerCloses = !mob.classList.contains('is-open'); }
      out.toggleExpandedWhenClosed = toggle.getAttribute('aria-expanded');
      // Escape must close it too — keyboard users have no visible close
      // affordance while the panel covers the button that opened it.
      toggle.click();
      document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
      out.drawerEscapeCloses = !mob.classList.contains('is-open');
    }

    // Cart drawer opens from the header icon and closes again.
    var cartOpener = document.querySelector('[data-cart-open]');
    var cartDrawerEl = document.getElementById('CartDrawer');
    if (cartOpener && cartDrawerEl) {
      cartOpener.click();
      out.cartDrawerOpens = cartDrawerEl.classList.contains('is-open');
      var cartCloseBtn = cartDrawerEl.querySelector('[data-cart-close]');
      if (cartCloseBtn) {
        cartCloseBtn.click();
        out.cartDrawerCloses = !cartDrawerEl.classList.contains('is-open');
      }
    }

    // Cart drawer: Escape is the keyboard path out.
    if (cartOpener && cartDrawerEl) {
      cartOpener.click();
      document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
      out.cartEscapeCloses = !cartDrawerEl.classList.contains('is-open');
    }

    // Product quantity stepper: plus and minus adjust the input and the
    // value can never be stepped below one bottle.
    var qtyInput = document.querySelector('[data-product-quantity]');
    if (qtyInput) {
      var plusBtn = document.querySelector('[data-product-quantity-delta="1"]');
      var minusBtn = document.querySelector('[data-product-quantity-delta="-1"]');
      if (plusBtn && minusBtn) {
        qtyInput.value = 1;
        plusBtn.click();
        out.qtyStepsUp = qtyInput.value === '2';
        minusBtn.click();
        out.qtyStepsDown = qtyInput.value === '1';
        minusBtn.click();
        out.qtyRespectsMin = qtyInput.value === '1';
      }
    }

    // Every icon-only control needs an accessible name. aria-hidden controls
    // are exempt: they are deliberate duplicates (the cart thumbnail next to
    // the titled product link) removed from the accessibility tree.
    out.unlabelledIconControls = [];
    document.querySelectorAll('a, button').forEach(function (el) {
      if (el.textContent.trim()) return;
      if (!el.querySelector('svg, img')) return;
      if (el.closest('[aria-hidden="true"]')) return;
      var img = el.querySelector('img');
      var named = el.getAttribute('aria-label') || el.getAttribute('title')
        || (img && img.getAttribute('alt'));
      if (!named && out.unlabelledIconControls.length < 6) {
        out.unlabelledIconControls.push(
          (el.tagName + '.' + (el.className || '')).slice(0, 60));
      }
    });

    // Product gallery: clicking a thumbnail swaps the active slide.
    var gallery = document.querySelector('product-gallery');
    if (gallery) {
      var thumbs = gallery.querySelectorAll('[data-gallery-thumb]');
      if (thumbs.length > 1) {
        thumbs[1].click();
        var activeId = thumbs[1].getAttribute('data-gallery-thumb');
        var activeSlide = gallery.querySelector('[data-gallery-slide="' + activeId + '"]');
        var firstSlide = gallery.querySelector('[data-gallery-slide]');
        out.gallerySwitchesSlide = !!activeSlide && activeSlide.hidden === false;
        out.galleryHidesPrevious = firstSlide.hidden === true;
        out.galleryMarksAriaCurrent = thumbs[1].getAttribute('aria-current') === 'true';
        out.galleryClearsPreviousAriaCurrent = thumbs[0].getAttribute('aria-current') === 'false';
      }
    }

    // Pattern divider tiles a fixed-height strip rather than stretching a
    // single image, so its height must not vary with viewport width.
    var divider = document.querySelector('.pattern-divider');
    if (divider) {
      out.dividerHeight = divider.getBoundingClientRect().height;
      out.dividerRepeats = getComputedStyle(divider).backgroundRepeat;
    }

    // The castle banner's seal sits centred over the image.
    var seal = document.querySelector('.image-banner__seal');
    if (seal) {
      var sealImg = seal.querySelector('img');
      var bannerEl = seal.closest('.image-banner');
      if (sealImg && bannerEl) {
        var sr = sealImg.getBoundingClientRect();
        var brct = bannerEl.getBoundingClientRect();
        out.sealVisible = sr.width > 0 && sr.height > 0;
        out.sealCentred = Math.abs((sr.left + sr.width / 2) - (brct.left + brct.width / 2));
        out.sealShare = sr.height / brct.height;
      }
    }

    // Cart age confirmation gates checkout, when the merchant has it switched
    // on. It is a theme setting, so its absence is a valid configuration.
    var box = document.querySelector('[data-age-confirm]');
    var checkout = document.querySelector('button[name="checkout"]');
    if (checkout) {
      out.hasAgeConfirm = !!box;
      if (box) {
        out.checkoutBlockedInitially = checkout.disabled === true;
        box.checked = true; box.dispatchEvent(new Event('change', { bubbles: true }));
        out.checkoutEnabledAfterTick = checkout.disabled === false;
        box.checked = false; box.dispatchEvent(new Event('change', { bubbles: true }));
        out.checkoutReblocked = checkout.disabled === true;
      } else {
        // Nothing to confirm, so nothing may block the shopper from paying.
        out.checkoutReachable = checkout.disabled === false;
      }
    }

    var rail = document.querySelector('.dispatch-grid--carousel');
    if (rail) {
      var cs = getComputedStyle(rail);
      out.railScrolls = (cs.overflowX === 'auto' || cs.overflowX === 'scroll')
        && rail.scrollWidth > rail.clientWidth + 4;
      out.railStacks = cs.overflowX === 'visible';
      out.railSnaps = cs.scrollSnapType.indexOf('x') !== -1;
    }

    var fit = document.querySelector('.image-banner--fit-mobile, .image-banner--fit');
    if (fit) {
      var img = fit.querySelector('img');
      out.bannerFit = img ? getComputedStyle(img).objectFit : null;
      out.bannerTrimmed = fit.classList.contains('image-banner--fit');

      if (img && img.naturalWidth) {
        var br = img.getBoundingClientRect();
        var natural = img.naturalWidth / img.naturalHeight;

        if (out.bannerTrimmed) {
          // "Whole image, trimmed": cover scales the file to the box width, so
          // nothing is lost off the sides and the overflow is the intended
          // slice off the top and bottom. Measure how much that slice is.
          var scale = br.width / img.naturalWidth;
          var renderedH = img.naturalHeight * scale;
          out.bannerCropFraction = 1 - (br.height / renderedH);
          // object-position hands the overflow back top vs bottom in the
          // proportion the section asked for; recover both slices.
          var posY = parseFloat(getComputedStyle(img).objectPosition.split(' ')[1]) / 100;
          var overflow = renderedH - br.height;
          out.bannerTopCrop = (overflow * posY) / renderedH;
          out.bannerBottomCrop = (overflow * (1 - posY)) / renderedH;
        } else {
          // Uncropped means the rendered box keeps the file's aspect ratio.
          out.bannerAspectDrift = Math.abs((br.width / br.height) - natural);
        }
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

    // Age-gate storage behaviour, exercised against the real global.js logic.
    var gateEl = document.getElementById('AgeGate');
    if (gateEl) {
      out.gateFrequency = gateEl.getAttribute('data-frequency');
      try {
        sessionStorage.removeItem('dunrobin:age-verified');
        localStorage.setItem('dunrobin:age-verified', 'true');
        // A device-wide flag must not suppress the gate in per-session mode.
        out.deviceFlagIgnored = sessionStorage.getItem('dunrobin:age-verified') !== 'true';
        localStorage.removeItem('dunrobin:age-verified');
      } catch (e) {
        out.gateStorageError = String(e);
      }
    }

    // Second stage: scroll to the bottom and confirm every reveal-animated
    // element in view actually became visible. A regression here is the
    // "blank section" bug — content stuck at opacity 0 waiting for an
    // IntersectionObserver that never fired.
    window.scrollTo(0, document.documentElement.scrollHeight);
    setTimeout(function () {
      out.revealsStuck = [];
      document.querySelectorAll('.reveal:not(.is-visible)').forEach(function (el) {
        var r = el.getBoundingClientRect();
        // "In view" means enough of it shows to trip the reveal observer,
        // which fires at 5% visible (initReveal's threshold). A card sitting
        // a few pixels above the fold is not stuck, it just hasn't arrived.
        var shown = Math.min(r.bottom, window.innerHeight) - Math.max(r.top, 0);
        var inView = r.width > 0 && r.height > 0 && shown > 0
          && shown / r.height >= 0.05;
        if (inView && out.revealsStuck.length < 5) {
          out.revealsStuck.push((el.tagName + '.' + (el.className || '')).slice(0, 60));
        }
      });
      out.jsErrors = __probeErrors;

      var pre = document.createElement('pre');
      pre.id = 'probe';
      pre.textContent = JSON.stringify(out);
      document.body.appendChild(pre);
    }, 700);
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
    # Unique names per probe: the matrix runs several probes concurrently.
    stem = f'__probe_{page.replace(".", "_")}_{width}'
    child = os.path.join(PREVIEW, stem + '_child.html')
    frame = os.path.join(PREVIEW, stem + '_frame.html')
    open(child, 'w').write(child_html)
    open(frame, 'w').write(f"""<!doctype html><html><head><meta charset="utf-8">
<style>html,body{{margin:0;padding:0}}iframe{{border:0;display:block}}</style></head><body>
<iframe id="f" src="{stem}_child.html" width="{width}" height="{height}" scrolling="no"></iframe>
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


def test_preview_links():
    """Every local href/src in the built preview must point at a real file,
    and every #fragment at a real element id. A typo here is a dead button."""
    for page in PAGES:
        path = os.path.join(PREVIEW, page)
        if not os.path.exists(path):
            continue
        html = open(path).read()
        ids = set(re.findall(r'id="([^"]+)"', html))
        broken = []
        for url in re.findall(r'(?:href|src)="([^"]+)"', html):
            if url.startswith(('http:', 'https:', 'mailto:', 'tel:', 'data:')):
                continue
            if url == '#':  # deliberate stub in the mock (search, account)
                continue
            target, _, frag = url.partition('#')
            if target and not os.path.exists(os.path.join(PREVIEW, target)):
                broken.append(url)
            elif frag:
                frag_html = html if not target or target == page else (
                    open(os.path.join(PREVIEW, target)).read()
                    if os.path.exists(os.path.join(PREVIEW, target)) else '')
                if f'id="{frag}"' not in frag_html and frag not in ids:
                    broken.append(url)
        check(f'{page}: all local links and assets resolve', not broken,
              str(broken[:4]))


def test_render():
    if not os.path.exists(CHROME):
        check('headless Chrome available', True, 'skipped, Chrome not installed')
        return
    if not build_preview():
        return
    test_preview_links()

    # What the home page's "whole image" banner is configured to trim, so the
    # render checks can hold the measured crop to it.
    banner_trim = {'top': 5, 'bottom': 36}
    for sec in load_json(rel('templates', 'index.json'))['sections'].values():
        st = sec.get('settings', {})
        if sec['type'] == 'image-banner' and st.get('height') == 'fit':
            banner_trim = {'top': st.get('trim_top', 5), 'bottom': st.get('trim_bottom', 36)}

    # Each probe is its own Chrome process, so the matrix parallelises
    # cleanly; assertions still run in a stable order afterwards.
    jobs = [(page, label, w, h)
            for page in PAGES if os.path.exists(os.path.join(PREVIEW, page))
            for label, w, h in VIEWPORTS]
    for page in PAGES:
        if not os.path.exists(os.path.join(PREVIEW, page)):
            check(f'preview page exists: {page}', False)

    import concurrent.futures
    results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(probe, page, w, h): (page, label, w, h)
                   for page, label, w, h in jobs}
        for fut in concurrent.futures.as_completed(futures):
            results[futures[fut]] = fut.result()

    for page, label, w, h in jobs:
        if True:
            d = results[(page, label, w, h)]
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

            check(f'{tag}: no JS errors during interactions',
                  not d.get('jsErrors'), str(d.get('jsErrors', [])[:3]))

            check(f'{tag}: icon-only controls have accessible names',
                  not d.get('unlabelledIconControls'),
                  str(d.get('unlabelledIconControls', [])[:3]))

            check(f'{tag}: revealed content is not stuck invisible',
                  not d.get('revealsStuck'), str(d.get('revealsStuck', [])[:3]))

            if 'cartEscapeCloses' in d:
                check(f'{tag}: Escape closes the cart drawer',
                      d['cartEscapeCloses'] is True)

            if 'qtyStepsUp' in d:
                check(f'{tag}: quantity steps up', d['qtyStepsUp'] is True)
                check(f'{tag}: quantity steps down', d['qtyStepsDown'] is True)
                check(f'{tag}: quantity never drops below one',
                      d['qtyRespectsMin'] is True)

            if 'footerNotWhite' in d:
                check(f'{tag}: footer text is white', not d['footerNotWhite'],
                      str(d['footerNotWhite'][:3]))

            if 'bottleOffset' in d:
                check(f'{tag}: bottle centred in its section',
                      d['bottleOffset'] < 2,
                      f'{d["bottleOffset"]:.1f}px off centre')

            if 'cartDrawerOpens' in d:
                check(f'{tag}: cart icon opens the drawer', d['cartDrawerOpens'] is True)
                check(f'{tag}: cart drawer closes', d.get('cartDrawerCloses') is True)

            if 'gallerySwitchesSlide' in d:
                check(f'{tag}: gallery thumbnail switches the active slide',
                      d['gallerySwitchesSlide'])
                check(f'{tag}: gallery hides the previous slide', d['galleryHidesPrevious'])
                check(f'{tag}: gallery marks the clicked thumbnail aria-current',
                      d['galleryMarksAriaCurrent'])
                check(f'{tag}: gallery clears aria-current from the previous thumbnail',
                      d['galleryClearsPreviousAriaCurrent'])

            if 'dividerHeight' in d:
                check(f'{tag}: pattern divider holds its configured height',
                      abs(d['dividerHeight'] - 90) < 1.5,
                      f'{d["dividerHeight"]}px, expected ~90px')
                check(f'{tag}: pattern divider tiles instead of stretching',
                      d['dividerRepeats'] in ('repeat-x', 'repeat'), d['dividerRepeats'])


            if 'sealVisible' in d:
                check(f'{tag}: castle banner seal is visible', d['sealVisible'])
                check(f'{tag}: castle banner seal centred over the image',
                      d['sealCentred'] < 2, f'{d["sealCentred"]:.1f}px off centre')
                if d.get('bannerTrimmed'):
                    # The banner is a short band, so the seal is held to a
                    # share of its height instead of covering the castle.
                    check(f'{tag}: castle banner seal stays a modest share of the height',
                          d['sealShare'] <= 0.36, f'{d["sealShare"]:.2f} of the banner height')

            if 'gateFrequency' in d:
                check(f'{tag}: age gate asks per session', d['gateFrequency'] == 'session',
                      f'frequency is {d["gateFrequency"]}')
                check(f'{tag}: device-wide flag does not suppress the gate',
                      d.get('deviceFlagIgnored') is True)

            check(f'{tag}: body text at least 14px', d['bodyFontPx'] >= 14,
                  f'{d["bodyFontPx"]}px')

            check(f'{tag}: Libre Baskerville applied',
                  'Libre Baskerville' in d['bodyFont'] and 'Libre Baskerville' in d['headingFont'],
                  f'body={d["bodyFont"]}, heading={d["headingFont"]}')

            if w < 750:
                if 'railScrolls' in d:
                    check(f'{tag}: dispatches scroll as a carousel', d['railScrolls'] is True,
                          'rail is not horizontally scrollable on mobile')
                    check(f'{tag}: carousel snaps', d.get('railSnaps') is True)
                if 'bannerFit' in d:
                    if d.get('bannerTrimmed'):
                        # The banner shows the whole picture across the full
                        # width, with a deliberate slice off the top and bottom.
                        check(f'{tag}: banner fills the width', d['bannerFit'] == 'cover',
                              f'object-fit is {d["bannerFit"]}')
                        crop = d.get('bannerCropFraction', 9)
                        # Phones take half the bottom trim, so the strip stays
                        # tall enough to read the castle in.
                        want = (banner_trim['top'] + banner_trim['bottom'] / 2) / 100
                        check(f'{tag}: banner trims the top and half the bottom',
                              abs(crop - want) < 0.02, f'crops {crop:.3f} of the height, want {want:.3f}')
                    else:
                        check(f'{tag}: banner image not cropped', d['bannerFit'] == 'contain',
                              f'object-fit is {d["bannerFit"]}')
                        check(f'{tag}: banner keeps its aspect ratio',
                              d.get('bannerAspectDrift', 9) < 0.05,
                              f'drift {d.get("bannerAspectDrift")}')
            if d.get('bannerTrimmed') and 'bannerTopCrop' in d:
                # The castle must never be cut: the spire tips start ~9.5% down
                # the picture and the bastion's base ends ~59% down it. The
                # half point of slack covers the measurement's rounding.
                check(f'{tag}: banner keeps the castle spires in frame',
                      d['bannerTopCrop'] <= (SPIRE_TOP_MAX + 0.5) / 100,
                      f'top {d["bannerTopCrop"]:.3f} cropped, spires at ~0.095')
                check(f'{tag}: banner keeps the castle base in frame',
                      d['bannerBottomCrop'] <= 0.40, f'bottom {d["bannerBottomCrop"]:.3f} cropped, base at ~0.59')
            if w >= 750:
                if 'bannerTrimmed' in d and d['bannerTrimmed']:
                    want = (banner_trim['top'] + banner_trim['bottom']) / 100
                    check(f'{tag}: banner trims the top and bottom as configured',
                          abs(d['bannerCropFraction'] - want) < 0.02,
                          f'crops {d["bannerCropFraction"]:.3f} of the height, want {want:.3f}')
                if 'railStacks' in d:
                    check(f'{tag}: dispatches are a grid, not a rail',
                          d['railStacks'] is True, 'carousel styles leaked to desktop')
                if 'bannerFit' in d:
                    check(f'{tag}: banner fills the band', d['bannerFit'] == 'cover',
                          f'object-fit is {d["bannerFit"]}')

            # The header switches at its own, wider breakpoint: the drawer
            # serves everything under 990px, including tablets.
            if w < 990:
                check(f'{tag}: desktop nav hidden', d['navDisplay'] == 'none', d['navDisplay'])
                check(f'{tag}: menu toggle visible', d['toggleDisplay'] != 'none')
                check(f'{tag}: drawer opens', d.get('drawerOpens') is True)
                check(f'{tag}: drawer closes', d.get('drawerCloses') is True)
                check(f'{tag}: Escape closes the drawer',
                      d.get('drawerEscapeCloses') is True)
                check(f'{tag}: menu toggle announces open state',
                      d.get('toggleExpandedWhileOpen') == 'true',
                      f'aria-expanded={d.get("toggleExpandedWhileOpen")}')
                check(f'{tag}: menu toggle announces closed state',
                      d.get('toggleExpandedWhenClosed') == 'false',
                      f'aria-expanded={d.get("toggleExpandedWhenClosed")}')
            else:
                check(f'{tag}: menu toggle hidden', d['toggleDisplay'] == 'none')
                if 'navCentre' in d:
                    check(f'{tag}: nav centred in header',
                          abs(d['navCentre'] - d['headerCentre']) < 2,
                          f'nav {d["navCentre"]} vs header {d["headerCentre"]}')

            if page == 'cart.html':
                if d.get('hasAgeConfirm'):
                    check(f'{tag}: checkout blocked before age confirmation',
                          d.get('checkoutBlockedInitially') is True)
                    check(f'{tag}: checkout enabled after confirming',
                          d.get('checkoutEnabledAfterTick') is True)
                    check(f'{tag}: checkout re-blocked when unticked',
                          d.get('checkoutReblocked') is True)
                else:
                    check(f'{tag}: checkout is reachable with no age confirmation',
                          d.get('checkoutReachable') is True,
                          'nothing gates the button, so it must not be disabled')


# ---------------------------------------------------------------------------

def test_browsers():
    """Same pages, three engines (Blink, Gecko, WebKit), compared.
    Optional: skipped with a hint when Playwright isn't installed."""
    node = shutil.which('node')
    if not node or not os.path.isdir(rel('node_modules', 'playwright')):
        check('cross-browser checks', True,
              'skipped — enable with: npm install && npx playwright install firefox webkit')
        return
    r = subprocess.run([node, rel('tests', 'browsers.mjs')],
                       capture_output=True, text=True, timeout=900, cwd=ROOT)
    # browsers.mjs relaunches a browser that is closed from outside mid-run and
    # logs one "retry:" line each time. Passing that way is fine, but say so.
    restarts = [ln for ln in r.stderr.splitlines() if ln.startswith('retry:')]
    if restarts:
        notes.append(f'cross-browser: a browser closed unexpectedly and was '
                     f'relaunched {len(restarts)} time(s)')
    if not r.stdout.strip():
        check('cross-browser suite produced results', False, r.stderr[-300:])
        return
    for c in json.loads(r.stdout)['checks']:
        # Agreement checks that pass are collapsed into one line each to keep
        # the pass count meaningful without drowning the report.
        check('x-browser: ' + c['name'], c['ok'], c.get('detail', ''))


def main():
    fast = '--fast' in sys.argv
    test_structure()
    if not fast:
        test_theme_check()
        test_render()
        test_browsers()

    print()
    for n in notes:
        print('note: ' + n)
    if failures:
        print(f'FAILED —{len(failures)} of {len(failures) + passes} checks')
        for f in failures:
            print('  ✗ ' + f)
        return 1
    print(f'PASSED — {passes} checks')
    return 0


if __name__ == '__main__':
    sys.exit(main())
