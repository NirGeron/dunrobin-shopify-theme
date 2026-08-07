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
| Heading typeface | Cormorant Garamond | Nearest Shopify-hosted match for **Junicode Condensed** |
| Body typeface | Work Sans | Brand secondary typeface |

All of the above are theme settings, so they can be changed in the editor.

> The guidelines specify **Junicode Condensed** for headings. It is not in Shopify's
> font library, so the theme ships with Cormorant Garamond as the default. To use the
> real typeface, upload the Junicode woff2 files to `assets/` and add an `@font-face`
> rule at the top of `assets/base.css`.

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

Hero banner · Rich text · Image with text · Featured product · Featured collection ·
Collection list · Multi-column · Quote · Pattern divider · Newsletter ·
Collapsible content · Video · Contact form · Apps

Each has its own settings and, where it makes sense, reorderable blocks. The product
page is block-based too: title, price, spec bar, variant picker, quantity, buy buttons,
collapsible rows and detail rows can all be reordered or removed in the editor.

## Brand imagery in `assets/`

Derived from the brand guideline deck and the supplied logo files.

- `logo.png`, `logo-white.png` — the horizontal wordmark lockup
- `logo-stacked.png`, `logo-stacked-white.png` — wordmark + monogram + tagline
- `brand-mark.png`, `favicon.png` — the four-tile monogram
- `seal-sans-peur.png`, `seal-sans-peur-navy.png` — the Sans Peur wildcat seal
- `pattern-navy.jpg`, `pattern-white.jpg` — the arch-and-wave pattern
- `castle.jpg`, `castle-duotone.jpg`, `highlands.jpg`, `landscape-storr.jpg`, `cocktail.jpg`
- `bottle-gin.png` and the other bottle renders, cut out on transparency

## Connecting to Shopify

1. **Online Store → Themes → Add theme → Connect from GitHub**
2. Pick this repository and the `main` branch.
3. Shopify creates an unpublished theme. Use **Customize** to preview it.
4. In **Theme settings → Brand assets**, upload the logo, white logo, pattern and
   favicon so they live in Shopify's CDN rather than the theme's `assets/` folder.
5. Publish when you are happy.

Once connected, commits pushed to `main` sync to the theme automatically, and edits
made in the theme editor are committed back to the branch.

## Age verification

On by default, configured under **Theme settings → Age verification**. The visitor's
choice is stored in `localStorage`, and the gate is suppressed inside the theme editor
so it does not block previewing.

## Legal

Footer carries the UK Chief Medical Officers' drinking guidance and the Highland
Council licence numbers. Check these are current before publishing.
