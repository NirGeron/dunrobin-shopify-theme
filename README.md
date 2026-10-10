# Dunrobin Highland Distillery — Shopify theme

An Online Store 2.0 theme built to the Dunrobin Highland Distillery brand guidelines.
Every page is composed from sections and blocks, so the whole site is editable from
**Online Store → Themes → Customize** without touching code.

## Brand

| Token | Value | Source |
| --- | --- | --- |
| Royal Blue (primary) | `#1C348F` | Brand guidelines, colour page |
| Deep Blue | `#101C50` | Brand guidelines |
| Forest Green (secondary) | `#123620` | Brand guidelines |
| Heading typeface | Libre Baskerville | Set site-wide |
| Body typeface | Libre Baskerville | Set site-wide |

All of the above are theme settings, so they can be changed in the editor.

> The site uses **Libre Baskerville** throughout, for both headings and body copy.
> The guidelines specify **Junicode Condensed**, which is not in Shopify's font
> library — to use it, upload the Junicode woff2 files to `assets/` and add an
> `@font-face` rule at the top of `assets/base.css`.

## Layout

```
assets/       base.css, global.js, and the brand imagery pulled from the guidelines
config/       settings_schema.json (editor controls) and settings_data.json (defaults)
layout/       theme.liquid, password.liquid
locales/      en.default.json
sections/     every section, plus the header and footer section groups
snippets/     reusable partials (product card, price, cart, age gate, icons)
templates/    JSON templates — the section order for each page type
```

## Sections a merchant can add

Hero banner · Rich text · Image with text · Image pair · Gallery · Featured product ·
Featured collection · Collection list · Multi-column · Quote · Pattern divider ·
Newsletter · Collapsible content · Video · Contact form · Apps

Each has its own settings and, where it makes sense, reorderable blocks. The product
page is block-based too: title, price, spec bar, variant picker, quantity, buy buttons,
collapsible rows and detail rows can all be reordered or removed in the editor.

## Brand imagery in `assets/`

Derived from the brand guideline deck and the supplied logo files.

- `logo.png`, `logo-white.png` — the horizontal wordmark lockup
- `logo-stacked.png`, `logo-stacked-white.png` — wordmark + monogram + tagline
- `brand-mark.png`, `favicon.png`, `favicon-192.png` — the four-tile monogram
  (`favicon-192.png` is the 192px square Google wants for its search-result icon)
- `seal-sans-peur.png`, `seal-sans-peur-navy.png` — the Sans Peur wildcat seal
- `pattern-navy.jpg`, `pattern-white.jpg` — the arch-and-wave pattern
- `castle.jpg`, `castle-duotone.jpg`, `landscape-storr.jpg`, `cocktail.jpg`
- `mood-*.jpg` — the cropped photographs from the brand deck, shown by the Gallery
  and Image pair sections until the originals are uploaded in the editor. They were
  supplied small, so swap in the full-size files before relying on them
- `bottle-gin.png` and the other bottle renders, cut out on transparency

## Connecting to Shopify

1. **Online Store → Themes → Add theme → Connect from GitHub**
2. Pick this repository and the `main` branch.
3. Shopify creates an unpublished theme. Use **Customize** to preview it.
4. In **Theme settings → Brand assets**, upload the logo, white logo, pattern and
   favicon so they live in Shopify's CDN rather than the theme's `assets/` folder.
   Until you do, the theme falls back to the files in `assets/` (see below), so the
   site never ships without a favicon or an Organization logo.
5. Publish when you are happy.

Once connected, commits pushed to `main` sync to the theme automatically, and edits
made in the theme editor are committed back to the branch.

## Age verification

On by default, configured under **Theme settings → Age verification**. It asks once
per browsing session — the confirmation is kept in `sessionStorage`, so a visitor
returning in a fresh session is asked again. Switch to **Once per device** in the
settings to use `localStorage` instead.

Declining swaps the panel for an apology, counts down, and then sends the visitor to
the **Decline redirects to** URL (Google by default). The heading, message, delay and
destination are all theme settings. Without JavaScript the decline button is a plain
link and goes straight there.

The gate is suppressed inside the theme editor so it does not block previewing.

## Google Search Console

Search Console itself is Google's tool and lives at search.google.com/search-console.
The theme does its half: it carries the ownership tag and publishes the structured
data that the Search Console reports read.

**Verify the site** (once)

1. In Search Console choose **Add property → URL prefix** and enter the store's
   primary domain, e.g. `https://dunrobin.example`.
2. Pick the **HTML tag** verification method and copy the tag Google shows.
3. In **Theme settings → Google Search Console**, paste it into *Verification tag*
   (the whole tag or just the `content` value both work) and save.
4. Back in Search Console, click **Verify**.

This store's own tag is written directly under `<head>` in `layout/theme.liquid`
(a test fails if it is removed — deleting it unverifies the property), so leave the
setting empty unless you are verifying a different property or token. Whatever is
in the setting is rendered on every page, including the password page, so it is
found whether or not the store is locked. Use the primary domain, not `*.myshopify.com`.
To cover subdomains too, add a **Domain** property and verify it with the DNS TXT
record at the domain registrar instead — that needs no theme change.

**Submit the sitemap** (once, after verifying)

Shopify generates it automatically. In Search Console → **Sitemaps**, submit
`sitemap.xml`. Don't add a `robots.txt` override unless it's really needed;
Shopify's default already points crawlers at the sitemap and keeps cart,
checkout and search out of the index.

**Structured data the theme outputs** (`snippets/structured-data.liquid`)

| Page | Markup | Search Console report |
| --- | --- | --- |
| Home | Organization, WebSite | Site name and logo in results |
| Product | Product (from the product section), BreadcrumbList | Merchant listings, Product snippets, Breadcrumbs |
| Collection | BreadcrumbList | Breadcrumbs |
| Article | Article, BreadcrumbList | Breadcrumbs |

Organization always carries a logo: the *Brand mark* from Brand assets, else the
main logo, else `assets/brand-mark.png`. The social links from Theme settings become
`sameAs`. Check the live pages with Google's Rich Results Test once the theme is
published.

**Favicon** — Google shows the site's favicon beside results and asks for a square
image whose side is a multiple of 48px. An uploaded *Favicon* is served at 48px
(and 180px for the Apple touch icon). With none uploaded, `layout/theme.liquid` and
`layout/password.liquid` fall back to `assets/favicon-192.png`, and the Apple touch
icon to `assets/favicon.png`. Google refreshes favicons on its own schedule, so a
change can take days to appear.

## Legal

Footer carries the UK Chief Medical Officers' drinking guidance and the Highland
Council licence numbers. Check these are current before publishing.

## Tests

```bash
python3 tests/run.py          # everything (~1 min, drives headless Chrome)
python3 tests/run.py --fast   # structure only, under a second
```

**Structure** — parses every Liquid schema, JSON template and settings file and
checks they only refer to things that exist: sections, block types, setting ids,
snippets, assets and translation keys. Also asserts that every non-`main-`
section is addable in the editor, that `font_face` is never called on an
unguarded variable, and that every `<img>` in Liquid declares width and height.

**Render** — rebuilds the static preview from the real `assets/base.css` and
`assets/global.js`, then drives headless Chrome over the home, product, shop and
cart pages at **390px, 768px and 1440px**, asserting:

- no horizontal overflow and nothing positioned outside the viewport
- tap targets at least 24×24px (WCAG 2.5.8), excluding inline prose links
- every image declares dimensions, so nothing shifts as the page loads
- body text at least 14px, and Libre Baskerville actually applied
- mobile: desktop nav hidden, menu toggle visible, drawer opens and closes
- desktop: menu toggle hidden, nav centred on the header's midpoint
- cart: checkout blocked until age is confirmed, and re-blocked if unticked

A `pre-commit` hook runs the suite automatically:

```bash
git config core.hooksPath .githooks   # already set in this clone
```

Bypass once with `git commit --no-verify`.
