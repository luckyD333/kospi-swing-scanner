---
version: alpha
name: Signal
description: An austere editorial-commerce interface for trading signals that uses near-pure black canvas, white uppercase letterspaced display, and giant monospace ticker codes as the only voltage. The system runs three custom Signal typefaces — Signal Display, Signal Text Regular, and Signal Mono — and combines them at modest weights with wide tracking to feel European-engineered, hyper-minimal, and quietly precise. There is no accent color, no decorative element, no chrome — only typography, numerical data, and the brand wordmark. Stocks are displayed as products in a fashion-editorial catalog, with the ticker code performing the role that automotive photography performs on Bugatti.com.

colors:
  primary: "#ffffff"
  ink: "#ffffff"
  body: "#cccccc"
  body-strong: "#e6e6e6"
  muted: "#999999"
  muted-soft: "#666666"
  hairline: "#262626"
  hairline-strong: "#3a3a3a"
  canvas: "#000000"
  surface-soft: "#0d0d0d"
  surface-card: "#141414"
  surface-elevated: "#1f1f1f"
  on-primary: "#000000"
  on-dark: "#ffffff"
  on-data: "#ffffff"
  link: "#c3d9f3"
  warning: "#d4a017"
  loss: "#c97064"
  gain: "#5fa657"

typography:
  display-xl:
    fontFamily: "Signal Display, sans-serif"
    fontSize: 64px
    fontWeight: 400
    lineHeight: 1.1
    letterSpacing: 4px
  display-lg:
    fontFamily: "Signal Display, sans-serif"
    fontSize: 48px
    fontWeight: 400
    lineHeight: 1.15
    letterSpacing: 3px
  display-md:
    fontFamily: "Signal Display, sans-serif"
    fontSize: 32px
    fontWeight: 400
    lineHeight: 1.2
    letterSpacing: 2px
  display-sm:
    fontFamily: "Signal Display, sans-serif"
    fontSize: 24px
    fontWeight: 400
    lineHeight: 1.3
    letterSpacing: 1.5px
  ticker-hero:
    fontFamily: "Signal Mono, ui-monospace, monospace"
    fontSize: 240px
    fontWeight: 400
    lineHeight: 1
    letterSpacing: -2px
  ticker-lg:
    fontFamily: "Signal Mono, ui-monospace, monospace"
    fontSize: 96px
    fontWeight: 400
    lineHeight: 1
    letterSpacing: 0px
  ticker-md:
    fontFamily: "Signal Mono, ui-monospace, monospace"
    fontSize: 56px
    fontWeight: 400
    lineHeight: 1
    letterSpacing: 0px
  ticker-sm:
    fontFamily: "Signal Mono, ui-monospace, monospace"
    fontSize: 32px
    fontWeight: 400
    lineHeight: 1
    letterSpacing: 0px
  numeric-lg:
    fontFamily: "Signal Mono, ui-monospace, monospace"
    fontSize: 28px
    fontWeight: 400
    lineHeight: 1.1
    letterSpacing: 0px
  numeric-md:
    fontFamily: "Signal Mono, ui-monospace, monospace"
    fontSize: 18px
    fontWeight: 400
    lineHeight: 1.2
    letterSpacing: 0px
  wordmark:
    fontFamily: "Signal Display, sans-serif"
    fontSize: 14px
    fontWeight: 400
    lineHeight: 1
    letterSpacing: 6px
  title-md:
    fontFamily: "Signal Display, sans-serif"
    fontSize: 20px
    fontWeight: 400
    lineHeight: 1.3
    letterSpacing: 1px
  title-sm:
    fontFamily: "Signal Display, sans-serif"
    fontSize: 16px
    fontWeight: 400
    lineHeight: 1.3
    letterSpacing: 1.5px
  caption-uppercase:
    fontFamily: "Signal Mono, ui-monospace, monospace"
    fontSize: 11px
    fontWeight: 400
    lineHeight: 1.4
    letterSpacing: 2px
  body-md:
    fontFamily: "Signal Text Regular, serif"
    fontSize: 16px
    fontWeight: 400
    lineHeight: 1.5
    letterSpacing: 0
  body-sm:
    fontFamily: "Signal Text Regular, serif"
    fontSize: 14px
    fontWeight: 400
    lineHeight: 1.5
    letterSpacing: 0
  button:
    fontFamily: "Signal Mono, ui-monospace, monospace"
    fontSize: 14px
    fontWeight: 400
    lineHeight: 1
    letterSpacing: 2.5px
  nav-link:
    fontFamily: "Signal Mono, ui-monospace, monospace"
    fontSize: 12px
    fontWeight: 400
    lineHeight: 1.4
    letterSpacing: 2px

rounded:
  none: 0px
  pill: 9999px
  full: 9999px

spacing:
  xxs: 4px
  xs: 8px
  sm: 12px
  md: 16px
  lg: 24px
  xl: 40px
  xxl: 64px
  section: 120px

components:
  button-primary:
    backgroundColor: transparent
    textColor: "{colors.on-dark}"
    typography: "{typography.button}"
    rounded: "{rounded.pill}"
    padding: 14px 32px
    height: 44px
  button-icon:
    backgroundColor: transparent
    textColor: "{colors.on-dark}"
    rounded: "{rounded.full}"
    size: 40px
  text-link:
    backgroundColor: transparent
    textColor: "{colors.link}"
    typography: "{typography.button}"
  top-nav:
    backgroundColor: transparent
    textColor: "{colors.on-dark}"
    typography: "{typography.nav-link}"
    height: 56px
  wordmark-display:
    backgroundColor: transparent
    textColor: "{colors.on-dark}"
    typography: "{typography.wordmark}"
  hero-ticker-band:
    backgroundColor: "{colors.canvas}"
    textColor: "{colors.on-dark}"
    typography: "{typography.ticker-hero}"
    padding: 96px
  caption-overlay:
    backgroundColor: transparent
    textColor: "{colors.on-dark}"
    typography: "{typography.caption-uppercase}"
  ticker-card:
    backgroundColor: "{colors.canvas}"
    textColor: "{colors.on-dark}"
    typography: "{typography.ticker-md}"
    rounded: "{rounded.none}"
    padding: 40px 24px
  signal-card:
    backgroundColor: "{colors.surface-card}"
    textColor: "{colors.on-dark}"
    typography: "{typography.numeric-md}"
    rounded: "{rounded.none}"
    padding: 24px
  candidate-row:
    backgroundColor: transparent
    textColor: "{colors.on-dark}"
    typography: "{typography.title-md}"
    padding: 24px 0
  spec-cell:
    backgroundColor: transparent
    textColor: "{colors.on-dark}"
    typography: "{typography.numeric-lg}"
    padding: 24px 0
  rr-band-tag:
    backgroundColor: transparent
    textColor: "{colors.muted}"
    typography: "{typography.caption-uppercase}"
    padding: 4px 0
  strategy-tag:
    backgroundColor: transparent
    textColor: "{colors.muted}"
    typography: "{typography.caption-uppercase}"
  date-pill:
    backgroundColor: transparent
    textColor: "{colors.muted}"
    typography: "{typography.caption-uppercase}"
  text-input:
    backgroundColor: transparent
    textColor: "{colors.on-dark}"
    typography: "{typography.body-md}"
    rounded: "{rounded.none}"
    padding: 12px 0
    height: 44px
  cta-band:
    backgroundColor: "{colors.canvas}"
    textColor: "{colors.on-dark}"
    typography: "{typography.display-md}"
    padding: 80px
  footer:
    backgroundColor: "{colors.canvas}"
    textColor: "{colors.muted}"
    typography: "{typography.body-sm}"
    padding: 64px
---

## Overview

Signal's surface is the most austere interface in editorial commerce: a near-pure black canvas (`{colors.canvas}` — #000000) holding white uppercase **letterspaced** display type and giant monospace ticker codes. The system has no accent color, no surface card decoration, no shadows, no gradients, no chrome — only **typography, numerical data, and the brand wordmark**. Every other trading or stock-listing interface in this category (Toss, Naver Finance, KIS Trading, Bloomberg) uses chart color, semantic red/green saturation, gradient panels, or some form of dashboard chrome; Signal uses nothing. The empty space, the giant monospace ticker, and the precisely-tracked Signal Display headline ARE the brand.

Stocks are not "rows in a table" — they are **products in an editorial catalog**. The ticker code performs the role that automotive photography performs on Bugatti.com: it is the dominant visual element on every product surface. A single ticker like `001390` rendered at 240px in Signal Mono on a black canvas is the page's hero. Numerical metrics (entry, stop, target, RR ratio, score) are not data-visualization fodder; they are read as **product specs**, in the same register as engine displacement on a Bugatti model page.

The system runs **three custom Signal typefaces**: **Signal Display** (display headlines, the "SIGNAL" wordmark, section heads — uppercase, wide tracking), **Signal Text Regular** (body paragraphs, signal descriptions, a serif text face), and **Signal Mono** (ticker codes, prices, every numerical value, button labels, navigation, captions, dates — anywhere precision and machined feel matters). The split is deliberate and unbreakable: never use Signal Text in a button, never use Signal Mono in a paragraph, never use Signal Display for a numerical value.

Display sizes use weight 400 (regular) — never bold. Visual emphasis comes from **size and tracking**, not weight. Letter-spacing on the wordmark is 6px; on display headlines 2-4px; on uppercase labels 2-2.5px. Tight tracking is a brand violation. The wide spacing creates the "engineered precision" feel that no other trading or commerce surface matches.

**Key Characteristics:**
- Pure black canvas (`{colors.canvas}` — #000000) with white type. The system does not have a light mode.
- Three custom Signal typefaces: **Display** (uppercase headlines + wordmark), **Text Regular** (body serif), **Mono** (tickers, all numerics, buttons, captions, nav).
- All display headlines are UPPERCASE with wide letter-spacing (2-4px). Body copy stays sentence-case at standard tracking. Ticker codes and numerical values are always Signal Mono at native casing.
- No accent color on marketing surfaces. The only non-monochrome colors anywhere on the site are `{colors.link}` (#c3d9f3) on inline anchor links and the muted semantic pair `{colors.gain}` (#5fa657) / `{colors.loss}` (#c97064) — the latter two reserved for actual realized P&L states only, never for decoration, never for category styling.
- Buttons are pill-shaped (`{rounded.pill}`) with **transparent background** and a 1px white outline. Signal is the only commerce surface in this category whose primary CTA is fully transparent.
- The ticker code is the only depth element. No drop shadows. No gradients. No card surfaces beyond `{colors.surface-card}` (#141414) — a barely-different-from-black tone.
- Section rhythm is generous — `{spacing.section}` (120px) between major bands, longer than most commerce sites because Signal's pages are mostly typography with minimal density. The empty space frames the data.

## Colors

### Brand & Accent
- **Primary** (`{colors.primary}` — #ffffff): The single brand color. White type and white CTA outlines on the black canvas.
- **Link** (`{colors.link}` — #c3d9f3): The only non-monochrome color in the marketing-surface vocabulary — a desaturated ice-blue used on inline anchor links and rarely on focus states. Signal's brand discipline is so tight that this single token is essentially the entire chromatic vocabulary outside black-and-white-and-semantic.

### Surface
- **Canvas** (`{colors.canvas}` — #000000): The default page floor across every surface. Pure black.
- **Surface Soft** (`{colors.surface-soft}` — #0d0d0d): A barely-different-from-black tone used for spec-row banding and dense data sections (only when alternating-row legibility demands it).
- **Surface Card** (`{colors.surface-card}` — #141414): Used for `{component.signal-card}` and the rare data card. Even card surfaces stay nearly-black — no contrast jump.
- **Surface Elevated** (`{colors.surface-elevated}` — #1f1f1f): One step further from black, used for nested cards on rare dense pages (e.g., a signal card that holds a sub-signal annotation).
- **Hairline** (`{colors.hairline}` — #262626): The 1px divider tone. Visible but quiet. Used between candidate-row entries, between spec-cell columns, around card outlines.
- **Hairline Strong** (`{colors.hairline-strong}` — #3a3a3a): A heavier divider used on the underside of input fields (input fields have no border — only an underline hairline).

### Text
- **Ink / On Dark** (`{colors.on-dark}` — #ffffff): All headline, ticker, and primary text on dark canvas.
- **Body** (`{colors.body}` — #cccccc): Default running-text color (slightly cooler than pure white). Used in body paragraphs.
- **Body Strong** (`{colors.body-strong}` — #e6e6e6): Emphasized body / lead paragraph.
- **Muted** (`{colors.muted}` — #999999): Strategy tags, RR-band labels, dates, captions, secondary metadata. The "category-tag-without-a-tag" register.
- **Muted Soft** (`{colors.muted-soft}` — #666666): A second-tier muted for very-secondary text (legal disclaimer, data-source attribution, "this is not investment advice" line).

### Semantic
- **Gain** (`{colors.gain}` — #5fa657): Reserved for realized-positive P&L on backtest result surfaces. Never used on candidate listings, never used as a "buy" signal indicator. The desaturated tone is intentional — saturated brokerage-green breaks the editorial voice instantly.
- **Loss** (`{colors.loss}` — #c97064): Realized-negative P&L only. Never used to indicate stop-loss levels or risk metrics — those stay white. The terracotta-leaning red is intentional; full-red signals "alert" and breaks the calm voice.
- **Warning** (`{colors.warning}` — #d4a017): Reserved for data-quality warnings (e.g., flagged candidates with breakout_pct < 0.5%, or signals where current_price is null). Almost never appears on the primary catalog.

The semantic trio is documented but used **rarely**. The first instinct on any new surface should be monochrome; the semantic colors are an emergency exit, not a starting point.

## Typography

### Font Family
The system runs **three custom Signal typefaces** as a rigid trinity:
1. **Signal Display** — All display headlines (h1, h2, h3), the "SIGNAL" wordmark, section heads, stock-name plates. Uppercase, wide-tracked. The default for any visual emphasis that is not numerical.
2. **Signal Text Regular** — A serif text face used exclusively for running body copy, signal descriptions, strategy explanations, the "what does breakout mean" footer text. Standard sentence-case, no letter-spacing.
3. **Signal Mono** — All ticker codes, all prices, all numerical values (entry, stop, target, ATR, RR, score, market-cap, volume), button labels, navigation, captions, dates, monospace-precision contexts. Always uppercase with 2-2.5px tracking when used as a label; native casing when used as a numerical value.

The split is functional and absolute. Signal Display in a button breaks the "machined precision" voice; Signal Mono in a paragraph breaks the "engineered elegance" voice; Signal Display in a price reads as marketing copy rather than data. The Mono face carries the entire numerical surface — this is non-negotiable, because monospaced figures align vertically across rows and let the eye scan a column of prices the way a serif paragraph cannot.

The fallback stack walks `-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Pretendard, sans-serif` for Signal Display, `Garamond, "Times New Roman", "Noto Serif KR", serif` for Signal Text Regular, and `ui-monospace, "SF Mono", "Cascadia Mono", "JetBrains Mono", monospace` for Signal Mono.

### Hierarchy

| Token | Size | Weight | Line Height | Letter Spacing | Use |
|---|---|---|---|---|---|
| `{typography.ticker-hero}` | 240px | 400 | 1.0 | -2px | The single hero ticker on a stock detail page (e.g., `001390`) — Signal Mono, native casing, slight negative tracking to lock the digits |
| `{typography.display-xl}` | 64px | 400 | 1.1 | 4px | Hero h1 ("THIS WEEK'S SIGNALS", "MULTI-STRATEGY PICKS") — Signal Display, uppercase, wide-tracked |
| `{typography.display-lg}` | 48px | 400 | 1.15 | 3px | Section heads — Signal Display, uppercase |
| `{typography.display-md}` | 32px | 400 | 1.2 | 2px | Sub-section heads, stock-name plates — Signal Display |
| `{typography.display-sm}` | 24px | 400 | 1.3 | 1.5px | Card titles — Signal Display |
| `{typography.ticker-lg}` | 96px | 400 | 1.0 | 0px | Editorial-variant card ticker (e.g., featured pick row) — Signal Mono |
| `{typography.ticker-md}` | 56px | 400 | 1.0 | 0px | Standard grid-card ticker — Signal Mono |
| `{typography.ticker-sm}` | 32px | 400 | 1.0 | 0px | Compact list-row ticker — Signal Mono |
| `{typography.numeric-lg}` | 28px | 400 | 1.1 | 0px | Spec-cell value (entry / stop / target / RR) — Signal Mono |
| `{typography.numeric-md}` | 18px | 400 | 1.2 | 0px | Inline numerical metric inside body or signal card — Signal Mono |
| `{typography.wordmark}` | 14px | 400 | 1.0 | 6px | The "SIGNAL" brand wordmark in the top nav — Signal Display, the widest tracking in the system |
| `{typography.title-md}` | 20px | 400 | 1.3 | 1px | Stock name (Korean / English), candidate-row labels — Signal Display |
| `{typography.title-sm}` | 16px | 400 | 1.3 | 1.5px | Mid-tier headlines, callout cards |
| `{typography.caption-uppercase}` | 11px | 400 | 1.4 | 2px | Spec labels, strategy tags, RR-band labels, "GENERATED 2026-05-02 22:15 KST" — Signal Mono, uppercase |
| `{typography.body-md}` | 16px | 400 | 1.5 | 0 | Default body — Signal Text Regular (a serif face), sentence case, no tracking |
| `{typography.body-sm}` | 14px | 400 | 1.5 | 0 | Footer body, fine-print legal — Signal Text Regular |
| `{typography.button}` | 14px | 400 | 1.0 | 2.5px | All button labels — Signal Mono, uppercase, 2.5px tracking |
| `{typography.nav-link}` | 12px | 400 | 1.4 | 2px | Top-nav menu items ("STRATEGIES", "TIMEFRAMES", "ABOUT") — Signal Mono |

### Principles
The system NEVER uses bold weight. Every Signal typeface is set at weight 400 (regular). Visual emphasis comes from:
1. **Size** — 240px hero ticker vs 16px body is a 15× hierarchy
2. **Letter-spacing** — 6px wordmark vs 0px ticker vs 0px body
3. **Case** — Uppercase display vs sentence-case body vs native-case Mono numerics
4. **Family contrast** — Display vs Text Regular vs Mono

Going to weight 700 anywhere would break the "modest engineering" feel and make Signal read like a generic trading template.

The serif Signal Text Regular sets the brand apart from the all-sans trading-platform crowd (Toss, Bloomberg Terminal, Naver Finance all use sans-serif body type, and most use Pretendard or Noto Sans KR specifically). Signal's serif body voice signals literary, considered, slow-reading prose — which is the brand's editorial philosophy. A signal report should read like a wine note, not a P&L statement.

### Note on Font Substitutes
If Signal Display, Signal Text Regular, and Signal Mono are unavailable, the closest open-source substitutes are:
- **Signal Display** → **Saira Condensed** (variable, weight 400) at +0.05em letter-spacing, or **Pretendard** for Korean coverage
- **Signal Text Regular** → **Cormorant Garamond** (regular) or **EB Garamond**; for Korean body, **Noto Serif KR** (regular)
- **Signal Mono** → **JetBrains Mono** or **IBM Plex Mono** (regular weight). Both have excellent figure spacing and tabular numerics, which is the entire point of using Mono for prices.

The substitution preserves the three-family split, which is more important than exact typeface match.

## Layout

### Spacing System
- **Base unit:** 4px.
- **Tokens:** `{spacing.xxs}` 4px · `{spacing.xs}` 8px · `{spacing.sm}` 12px · `{spacing.md}` 16px · `{spacing.lg}` 24px · `{spacing.xl}` 40px · `{spacing.xxl}` 64px · `{spacing.section}` 120px.
- **Section padding:** `{spacing.section}` (120px) — longer than most commerce sites because Signal's bands are mostly typography with minimal density. The empty space frames the tickers.
- **Card internal padding:** `{spacing.lg}` (24px) for signal cards and content cards; `{spacing.md}` (16px) for compact list rows; `{spacing.xxl}` (64px) inside hero ticker bands; `{spacing.xl}` (40px) vertical inside grid ticker-cards.
- **Gutters:** `{spacing.xl}` (40px) between cards in 2-up and 3-up grids — wider than typical because Signal's grids are sparse and ticker cards need visual breathing room around the giant Mono characters.

### Grid & Container
- **Max content width:** ~1280px centered. Hero ticker bands bleed full-width with no max.
- **Editorial body:** Single 12-column grid; ticker bands and CTA bands are full-bleed.
- **Catalog layout:** 3-up ticker-card grid at desktop, 2-up at tablet, 1-up at mobile.
- **Candidate-row listings:** Single column with 80px row spacing, hairline divider between rows.
- **Spec cells (stock detail):** 4-up at desktop, 2-up at tablet, 1-up at mobile.

### Whitespace Philosophy
Signal uses whitespace more aggressively than any trading or commerce surface in this category. The homepage hero is mostly a giant ticker code + huge whitespace + a single sentence + a single button. The empty black space below the ticker is intentional — it lets the data breathe. Compressing the whitespace to "fit more candidates above the fold" breaks the brand's fundamental contract: that less is more, and that one well-presented signal beats twenty crowded ones.

This is the single biggest tension between Signal's editorial discipline and the commodity trading-screen instinct. The discipline wins.

## Elevation & Depth

| Level | Treatment | Use |
|---|---|---|
| Flat | No shadow, no border | Body, top nav, footer, ticker bands |
| Soft hairline | 1px `{colors.hairline}` border | Section dividers, row separators, spec-cell dividers |
| Card surface | `{colors.surface-card}` background — no shadow | Signal cards, occasional metric callout |
| Typographic depth | Giant ticker + Mono numerals on black — depth via type weight + scale, not chrome | Hero ticker bands, stock-detail headers |

The system uses no shadows, no glassmorphism, no gradients. Depth comes entirely from typography (size, family contrast, the negative-space drama of a 240px Mono ticker on a black field) and from the contrast between black canvas and minimally-elevated `{colors.surface-card}`.

### Decorative Depth
- None. Signal is the only stock-listing surface without a single decorative element. There is no stripe, no badge, no gradient, no chart sparkline glyph next to a ticker on the marketing surface outside the wordmark itself. The data IS the decoration.

## Shapes

### Border Radius Scale

| Token | Value | Use |
|---|---|---|
| `{rounded.none}` | 0px | All cards, ticker containers, inputs, spec cells, signal cards — the dominant radius |
| `{rounded.pill}` | 9999px | All buttons (the only rounded element in the system) |
| `{rounded.full}` | 9999px / 50% | Circular icon buttons |

The radius hierarchy is binary: rectangular for everything except buttons, which are pills. No 4px, no 8px, no 12px in between — those would feel "designed" rather than "engineered." A 12px rounded card reads as fintech-app; a 0px card reads as Swiss-monograph.

### Ticker Geometry
The ticker code occupies the role automotive photography occupies on Bugatti.com — full-width hero treatment at the top of every detail page. There are no avatars, no logos, no thumbnails, no sparkline previews. The ticker IS the visual. Ticker cards in the catalog grid retain `{rounded.none}` (0px) corners, edge-to-edge type. Signal cards (the dark-card variant carrying entry/stop/target) keep 0px corners. The only curve in the system is the pill button.

## Components

### Top Navigation

**`top-nav`** — A 56px-tall transparent nav bar at the top of every page. No fill, no border. Carries "STRATEGIES" / "TIMEFRAMES" at left, the centered **wordmark-display** ("SIGNAL" in 14px Signal Display with 6px tracking), and "ABOUT" / a small search icon at right. All labels in `{typography.nav-link}` (Signal Mono, 12px, 2px tracking, uppercase).

**`wordmark-display`** — The "SIGNAL" wordmark itself. Signal Display at 14px, weight 400, 6px letter-spacing. The widest tracking in the system. Centered in the nav bar at every breakpoint.

### Buttons

**`button-primary`** — The signature primary CTA ("VIEW SIGNAL", "OPEN IN NAVER", "DISCOVER"). Background **transparent**, text `{colors.on-dark}` (white), 1px white outline, rounded `{rounded.pill}` (9999px), padding 14px × 32px, height 44px. Type `{typography.button}` — Signal Mono, uppercase, 14px, 2.5px tracking. The transparent fill is unique to Signal — every other trading or commerce surface uses a filled or outlined-with-text-shift button. Signal's transparent pill IS the button.

**`button-icon`** — Circular icon buttons (filter toggle, sort dropdown trigger, share). 40 × 40px, transparent background, white outline 1px, rounded `{rounded.full}`. Same outline-only treatment as the primary button.

**`text-link`** — Inline body links in `{colors.link}` (#c3d9f3, the only non-monochrome color in the marketing-surface vocabulary). Underlined by default. Type inherits `{typography.body-md}` (Signal Text Regular, serif).

### Cards & Containers

**`hero-ticker-band`** — Full-width black band with a single giant ticker code as the hero element. The ticker (e.g., `001390`) sits centered in `{typography.ticker-hero}` (240px Signal Mono), often paired with the stock name below in `{typography.display-md}` (e.g., "KG케미칼" in Signal Display 32px, 2px tracking, uppercase) and a small Signal Mono caption (`{typography.caption-uppercase}`) above the ticker carrying generation metadata ("STRATEGY THREE · 1H · 2026-05-02 22:15 KST"). A single `{component.button-primary}` sits below. Vertical padding 96px-200px depending on layout.

**`ticker-card`** — The catalog-grid product card. Background `{colors.canvas}` (no card surface — just type on black), rounded `{rounded.none}`. Top: ticker code in `{typography.ticker-md}` (56px Signal Mono), left-aligned. Below: stock name in `{typography.display-sm}` (24px Signal Display, 1.5px tracking, uppercase). Below that: market-cap in `{typography.numeric-md}` (e.g., "₩4,753억"). Bottom row: strategy tags and RR-band tag in `{typography.caption-uppercase}` (Signal Mono 11px). No border, no fill — just type with `{spacing.xl}` (40px) vertical padding to give the ticker visual room. On hover, a 1px `{colors.hairline}` outline appears (200ms ease-out) — no scale, no transform, no fill.

**`signal-card`** — Used inside stock-detail pages to represent a single (strategy, timeframe) signal. Background `{colors.surface-card}` (#141414, the only "card surface" in the system), rounded `{rounded.none}`, padding `{spacing.lg}` (24px). Carries: a strategy tag at top in `{typography.caption-uppercase}` ("STRATEGY THREE · TREND FOLLOWING · 1H"), a row of four numeric specs (entry / stop / target1 / target2) each in `{typography.numeric-lg}` with a `{typography.caption-uppercase}` label below, and a final row with RR ratio + RR band + score in muted caption type.

**`candidate-row`** — Each row of a strategy-collection or catalog-list view. Transparent background, padding 24px vertical, hairline divider between rows. Ticker in `{typography.ticker-sm}` (32px Signal Mono) at left; stock name in `{typography.title-md}` (Signal Display 20px) immediately right of the ticker; a row of 3-4 inline numeric metrics in `{typography.numeric-md}` (Mono 18px) at center; chevron arrow (→) at far right. The row is a horizontal editorial line, not a table cell — no vertical column borders, only the bottom hairline.

**`spec-cell`** — Vehicle-spec analog for a stock's trading parameters on the detail page. Transparent background with hairline dividers between cells (vertical hairlines only at desktop; horizontal hairlines on mobile when the grid collapses). Each spec shows a value in `{typography.numeric-lg}` (28px Signal Mono) at top and a label in `{typography.caption-uppercase}` below ("ENTRY", "STOP LOSS", "TARGET 1", "TARGET 2", "ATR(14)", "RR RATIO"). Padding 24px vertical.

### Inputs & Forms

**`text-input`** — Standard text input on dark canvas (used on the search page). Background **transparent**, text `{colors.on-dark}`, 1px hairline-strong bottom border only (no top, left, right border), padding 12px × 0px, height 44px. Type `{typography.body-md}` (Signal Text Regular). Placeholder in `{colors.muted}`. Focus thickens the bottom border to white. Search inputs that accept ticker codes optionally render the typed value in Signal Mono — but only after the user has typed at least one digit.

### Tags & Captions

**`caption-overlay`** — Type-overlay caption above or below the hero ticker (e.g., "STRATEGY THREE · TREND FOLLOWING · 1H · 2026-04-30"). Centered or left-aligned in `{typography.caption-uppercase}` (Signal Mono, 11px, 2px tracking, white).

**`strategy-tag`** + **`rr-band-tag`** + **`date-pill`** — All render as transparent inline labels in `{typography.caption-uppercase}`, color `{colors.muted}`. No background fill, no border, no chip. The "tag" is the type itself. The RR band specifically reads "RR · SWEET" / "RR · OVER" / "RR · UNDER" with the band name uppercased in the same Mono caption — never colored, never highlighted. Signal trusts that the discerning user will read the word "OVER" as a soft warning without needing it tinted yellow.

### CTA / Footer

**`cta-band`** — A pre-footer "Discover today's full catalog" band with a centered headline in `{typography.display-md}` and a `{component.button-primary}` below. Vertical padding 80px. No photography (we don't have any), so the band leans on negative space and the headline-button-only construction. Inherits the editorial gravity of the hero through scale and quietness.

**`footer`** — Black footer that closes every page. Background `{colors.canvas}`, text `{colors.muted}`. 4-column link list at desktop covering Signal / Strategies / Timeframes / Data Sources. Vertical padding 64px. Bottom row carries the data-source attribution and a "this is not investment advice" line in `{typography.body-sm}` (Signal Text Regular). The wordmark sits center-aligned at the very bottom. The footer never inverts. The generation timestamp ("DATA AS OF 2026-05-02 22:15 KST") sits in `{typography.caption-uppercase}` at the top-right corner of the footer.

## Do's and Don'ts

### Do
- Anchor every detail page with a giant Mono ticker code as the hero. The ticker IS the brand voltage; chrome backs off entirely.
- Keep all display headlines in UPPERCASE Signal Display with 2-4px letter-spacing. The wordmark gets 6px.
- Use Signal Display for headlines and stock names, Signal Text Regular (serif!) for body, Signal Mono for tickers, all numerical values, buttons, captions, nav. The trinity is unbreakable.
- Render every numerical value (price, ATR, RR, score, market-cap, volume) in Signal Mono. Tabular numerics are non-negotiable; a column of prices must align character-for-character down the page.
- Keep `{component.button-primary}` transparent with a 1px white outline. The transparent pill IS the brand button.
- Use weight 400 everywhere. Bold breaks the brand voice — the system has no bold weight role.
- Use `{spacing.section}` (120px) between major editorial bands. The whitespace is part of the brand.
- Reserve `{colors.link}` (#c3d9f3) for inline anchor links only.
- Reserve `{colors.gain}` and `{colors.loss}` for realized P&L states only — never for candidate rows, never for "this signal is bullish."

### Don't
- Don't introduce any accent color outside `{colors.link}` and the muted semantic pair. Adding a brand-blue, brand-red, or brokerage-green breaks the contract immediately.
- Don't bold any type. The system has no bold weight — every typeface stays at 400.
- Don't fill primary buttons. Transparent + outline only. A solid white button reads as off-brand.
- Don't compress whitespace to fit more candidates above the fold. The 120px rhythm is part of the editorial pacing.
- Don't use rounded corners outside buttons. Cards, ticker containers, inputs all stay at 0px. Rounded cards read as consumer fintech, not editorial-engineered.
- Don't tighten letter-spacing on display headlines. 2-4px tracking on Signal Display is non-negotiable.
- Don't use Signal Display for a numerical value (use Signal Mono), Signal Mono in a paragraph (use Signal Text Regular), or Signal Display in a button (use Signal Mono). The trinity split is the brand voice.
- Don't add chart sparklines, candlestick previews, or any decorative chart glyph to candidate cards. The catalog is editorial, not analytical. Charts live one click deeper.
- Don't tint stop-loss values red or target values green. Those are not realized P&L — they are parameters. Parameters stay white.

## Responsive Behavior

### Breakpoints

| Name | Width | Key Changes |
|---|---|---|
| Mobile | < 768px | Hamburger nav; hero ticker 240→120px; ticker-card grid collapses to 1-up; spec cells reflow to 1-up with horizontal hairlines |
| Tablet | 768–1024px | Top nav stays minimal (STRATEGIES + wordmark + search); 2-up ticker-card grid; spec cells 2-up |
| Desktop | 1024–1440px | Full minimal top-nav; 3-up ticker-card grid; spec cells 4-up; signal cards 2-up inside detail page |
| Wide | > 1440px | Same as desktop with more breathing room; max content 1280px; ticker-hero stays 240px (does not scale up) |

### Touch Targets
- `{component.button-primary}` renders at minimum 44 × 44px (matches WCAG AAA).
- `{component.button-icon}` is exactly 40 × 40px.
- `{component.text-input}` height is 44px.
- Candidate rows have 24px vertical padding; effective tap area meets 44px+ with surrounding spacing.

### Collapsing Strategy
- Top nav stays minimal at all breakpoints (one or two labels + wordmark + one icon). On mobile the labels hide behind a hamburger but the wordmark stays centered.
- Hero ticker scales down via `clamp()`: `clamp(120px, 18vw, 240px)`. The negative tracking (-2px) holds at all sizes.
- Ticker-card grid collapses 3-up → 2-up → 1-up.
- Spec cells reflow from 4-up to 2-up to 1-up; values stay at the same `{typography.numeric-lg}` display size regardless of column count. The labels stay 11px Mono at every breakpoint.
- Signal cards (detail page) stack vertically on mobile; the 24px internal padding remains.

### Numerical Behavior
- Ticker codes are always rendered in Signal Mono and never line-break or truncate. A 6-digit Korean ticker (`001390`) and a 6-character ETF code (`0101N0`) occupy the same character grid — this is the entire point of using a monospaced face.
- Price values use thousand-separators with `\u2009` (thin space) rather than commas, to preserve the figure-rhythm of the Mono face: `7 070` not `7,070`. (Korean stock convention often uses comma — accept comma if the team prefers, but never both within a single page.)
- Negative values for RR ratios or breakout percentages are rendered with a minus sign, never with parentheses. Parentheses break the figure rhythm.

## Iteration Guide

1. Focus on ONE component at a time. Reference its YAML key (`{component.hero-ticker-band}`, `{component.ticker-card}`, `{component.signal-card}`).
2. New components default to `{rounded.none}` (0px). Only `{component.button-primary}` and `{component.button-icon}` use pill / full radius.
3. Variants live as separate entries in `components:`.
4. Use `{token.refs}` everywhere — never inline hex.
5. Never document hover beyond a single hairline appearance. Default and Active/Pressed states only.
6. Display headlines stay UPPERCASE Signal Display 400 with 2-4px tracking. Body stays sentence-case Signal Text Regular (serif). Numerical values stay Signal Mono. The trinity does not blur.
7. When in doubt about emphasis: bigger ticker before bigger headline.
8. When the data tempts you to add color (a green RR-sweet badge, a red over-channel warning), resist. Type-only.

## Known Gaps

- The chart-detail surface (interactive candlestick view of a selected ticker) is not in scope for this version of the system. When introduced, it will live one click below the catalog and adopt a separate "analytical surface" sub-system that may permit chart color (gain/loss line tinting). The marketing/editorial surface documented here remains monochrome.
- Animation and transition timings (page transitions, ticker-card hover hairline appearance) are documented as "200ms ease-out" but specific easing curves and orchestrated multi-element transitions are not extracted.
- Form validation states beyond the underline-only `{component.text-input}` are not extracted — error / success states will follow the muted-semantic pair (`{colors.loss}` for error, `{colors.gain}` for success) but exact treatment is TBD.
- The portfolio / watchlist surface (where a user saves tickers across sessions) is not in scope; how a saved-ticker indicator reads on a `{component.ticker-card}` without breaking the no-decoration rule remains an open design question.
- The Korean-language and English-language renderings are assumed to share the system 1:1, with Pretendard as the Display fallback for Korean glyphs and Noto Serif KR as the body fallback. Mixed-script rendering (Korean stock name beside Mono ticker) has not been stress-tested at all sizes.
- The data-quality warning surface (flagged candidates: breakout_pct < 0.5%, ATR/entry < 0.5%, current_price null) uses `{colors.warning}` (#d4a017) as a token but specific component placement (a tag? a card border? a section in the detail page?) is not finalized.
- Empty-state surfaces (e.g., a strategy that produced 0 candidates today, like `strategy_one_d_v2`) are not documented — the current expectation is a single Signal Text Regular sentence centered in the band, but typographic treatment of zero-state still needs definition.
