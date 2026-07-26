# Design System

This documents the visual language for the AI Investment Analyst frontend. I maintain it alongside the implementation to keep decisions visible and consistent.

## Color Tokens

Colors are defined as CSS custom properties in `frontend/src/index.css`. The system supports four dark themes selected via `data-theme` attribute: petroleum (default), plum, moss, and graphite.

### Surface and Background

| Token | Petroleum (default) | Usage |
|-------|---------------------|-------|
| `--bg` | `#0d1317` | Page background |
| `--surface` | `#131b21` | Card backgrounds, containers |
| `--surface-elevated` | `#1a242c` | Modals, dropdowns, popovers |

### Text

| Token | Petroleum (default) | Usage |
|-------|---------------------|-------|
| `--text-primary` | `#e8edef` | Headings, body text |
| `--text-secondary` | `#8fa3b0` | Labels, descriptions |
| `--text-muted` | `#4d6472` | Timestamps, metadata |

### Border

| Token | Petroleum (default) | Usage |
|-------|---------------------|-------|
| `--border` | `#253340` | Card borders, dividers |
| `--border-subtle` | `#1c2830` | Soft separators, nested boundaries |

### Signal Colors

| Token | Petroleum (default) | Usage |
|-------|---------------------|-------|
| `--bullish` | `#2dd4a8` | Positive signals, gains |
| `--bullish-bg` | `rgba(45, 212, 168, 0.1)` | Bullish badges, backgrounds |
| `--bearish` | `#e07060` | Negative signals, losses |
| `--bearish-bg` | `rgba(224, 112, 96, 0.1)` | Bearish badges, backgrounds |
| `--neutral` | `#d4a853` | Hold/neutral signals |
| `--neutral-bg` | `rgba(212, 168, 83, 0.1)` | Neutral badges, backgrounds |

### Accent and UI

| Token | Petroleum (default) | Usage |
|-------|---------------------|-------|
| `--accent` | `#f0a030` | Primary actions, links |
| `--accent-bg` | `rgba(240, 160, 48, 0.08)` | Active states, selection |
| `--ring` | `#f0a030` | Focus rings |
| `--ring-offset` | `#0d1317` | Focus ring offset (matches bg) |
| `--cached` | `#2dd4a8` | Cached data indicator |
| `--live` | `#40b0e0` | Live/streaming indicator |

### Multi-Theme System

Four dark themes are available. Each uses the same token names with different palettes:

| Theme | Character | Accent |
|-------|-----------|--------|
| petroleum | Cool, oceanic blues | Warm amber `#f0a030` |
| plum | Purple, evening tones | Gold `#d4af37` |
| moss | Forest greens | Yellow-gold `#e6b801` |
| graphite | Warm earth tones | Burnt orange `#c2703d` |

All themes are dark-first. The target audience (developers, analysts) spends hours in the interface, often in low-light environments.

---

## Signal Encoding

Investment signals (buy, sell, hold) MUST use icon + color together. Color alone is insufficient because approximately 8% of men have some form of color vision deficiency.

### Required Pattern

| Signal | Icon | Color | Token |
|--------|------|-------|-------|
| Bullish / Buy | `TrendingUp` (Lucide) | Green | `--bullish` |
| Bearish / Sell | `TrendingDown` (Lucide) | Red | `--bearish` |
| Neutral / Hold | `Minus` (Lucide) | Amber | `--neutral` |

Shape carries meaning independently of color. A user who cannot distinguish red from green can still differentiate an upward arrow from a downward arrow from a horizontal line.

### Implementation Rules

- Always render the icon alongside the signal text or badge.
- Never rely on color alone to communicate signal direction.
- Icon size: 16px (inline with text) or 20px (standalone badge).
- Include `aria-label` on signal badges (e.g., `aria-label="Bullish signal"`).

---

## Motion Tokens

All motion uses CSS `transition`. Framer Motion is only introduced if CSS cannot achieve the effect (e.g., layout animations, exit animations with unmounting).

| Token | Duration | Usage |
|-------|----------|-------|
| instant | 0ms | Immediate state changes (checkbox, toggle) |
| fast | 100ms | Micro-interactions (button press feedback) |
| micro | 150ms | Trace events appearing, tooltip show/hide |
| normal | 200ms | Fade-in animations, panel transitions |
| slow | 350ms | Modal open/close, page transitions |

### Easing

- Default: `ease-out` for enters, `ease-in` for exits.
- `linear` only for progress bars and loading indicators.

### Reduced Motion

The system respects `prefers-reduced-motion: reduce`. When active:
- All animations are disabled (`animation: none`).
- All transitions collapse to near-zero duration (`0.01ms`).
- No content is hidden behind animation (content appears immediately).

This is implemented globally in `index.css` via the media query.

---

## Typography

### Font Stack

- **Body:** `'Inter', system-ui, sans-serif`
- **Monospace:** `'JetBrains Mono', monospace` (prices, percentages, tabular data)

Monospace text uses `font-variant-numeric: tabular-nums` so columns of numbers align properly. Applied via the `.font-mono-tabular` utility class.

### Size Scale

| Name | Size | Line Height | Usage |
|------|------|-------------|-------|
| xs | 0.75rem (12px) | 1rem | Metadata, timestamps |
| sm | 0.875rem (14px) | 1.25rem | Labels, secondary text |
| base | 1rem (16px) | 1.5rem | Body text |
| lg | 1.125rem (18px) | 1.75rem | Card titles |
| xl | 1.25rem (20px) | 1.75rem | Section headings |
| 2xl | 1.5rem (24px) | 2rem | Page titles |

### Weight Scale

| Name | Weight | Usage |
|------|--------|-------|
| normal | 400 | Body text, descriptions |
| medium | 500 | Labels, navigation items |
| semibold | 600 | Card titles, emphasis |
| bold | 700 | Page titles, key metrics |

---

## Spacing and Radius

### Spacing

Follow Tailwind's 4px grid. Common spacing values:

- `4px` (p-1) - Tight internal padding
- `8px` (p-2) - Icon gaps, compact elements
- `12px` (p-3) - Input padding, small card padding
- `16px` (p-4) - Standard card padding
- `24px` (p-6) - Section spacing
- `32px` (p-8) - Page-level gaps

### Border Radius Zones

I use two radius scales depending on the content type:

**Instrument zones (tight):** 4-6px radius
- Data cards, chart containers, table cells, metric badges
- These feel precise and technical, matching the data-heavy content

**Editorial zones (soft):** 10-14px radius
- Modals, empty states, onboarding cards, feature callouts
- These feel approachable and inviting

**Buttons and inputs:** 6-8px radius (between the two zones)

---

## Component Patterns

### Card Anatomy

```
+--[border: var(--border)]--+
|  [surface background]      |
|  +-- Header (optional) --+ |
|  |  Title + Action       | |
|  +------------------------+ |
|  +-- Body ---------------+ |
|  |  Content              | |
|  +------------------------+ |
|  +-- Footer (optional) --+ |
|  |  Metadata / Actions   | |
|  +------------------------+ |
+----------------------------+
```

- Background: `var(--surface)`
- Border: `1px solid var(--border)`
- Radius: 4-6px (instrument zone)
- Padding: 16px standard, 12px compact

---

## Loading States

### Skeleton Cards

Skeleton placeholders communicate layout structure during loading, reducing perceived wait time.

- Use the `.animate-shimmer` class (left-to-right gradient sweep, not pulse).
- Match skeleton dimensions to the expected content layout exactly.
- Render 3 skeleton cards on initial page load.
- Background gradient: `var(--surface)` to `var(--surface-elevated)` and back.
- With `prefers-reduced-motion`, skeletons render as static gray blocks (no animation).

```html
<div class="animate-shimmer rounded h-4 w-3/4"></div>
<div class="animate-shimmer rounded h-4 w-1/2 mt-2"></div>
```

### Streaming Text Indicator

When the LLM is actively generating analysis text:

- Show a blinking cursor (`|`) at the end of streamed text.
- Cursor blinks at 530ms interval using CSS animation.
- Disappears when the stream completes or errors.
- Pair with `aria-live="polite"` on the text container so screen readers announce updates.

### Tool Call Progress

During the fetch-data phase, each MCP tool call shows inline progress:

- Spinner icon (Lucide `Loader2`, 14px) rotating next to the tool name.
- On completion: spinner replaced by check icon (`Check`, green) or error icon (`X`, red).
- Duration badge appears after completion (e.g., "890ms").
- Use `animate-spin` for the spinner. Reduced motion: show static "..." text instead.

### Full-Page Loading

For initial app load or route transitions:

- Centered vertically and horizontally in the viewport.
- Spinner (Lucide `Loader2`, 24px) with a text label below (e.g., "Loading analysis...").
- Text uses `--text-secondary` color.
- Container uses `flex items-center justify-center min-h-screen`.

---

## Error States

### Inline Error

For component-level failures (failed data fetch, parse error):

- Red left border: `border-l-4 border-[var(--bearish)]`
- Error icon: Lucide `AlertCircle` (16px, `--bearish` color)
- Message: plain language describing what went wrong
- Retry button: secondary style, right-aligned
- Background: `var(--bearish-bg)`
- Padding: `p-4`, radius: instrument zone (4-6px)

```html
<div class="border-l-4 border-[var(--bearish)] bg-[var(--bearish-bg)] p-4 rounded">
  <div class="flex items-center gap-2">
    <AlertCircle size={16} class="text-[var(--bearish)]" />
    <span>Failed to fetch price data for NVDA</span>
  </div>
  <button class="mt-2 text-sm underline">Retry</button>
</div>
```

### Network Error

For connectivity loss or server unreachable:

- Full-width banner at the top of the page (below header).
- Background: `var(--bearish-bg)` with `--bearish` left accent.
- Message: "Connection lost. Retrying in 12s..." with countdown.
- Auto-retry with exponential backoff (3s, 6s, 12s, 30s cap).
- Dismiss button (X) to hide, but retry continues in background.

### Partial Failure

When some data sources succeed but others fail:

- Yellow warning badge on the analysis card header.
- Icon: Lucide `AlertTriangle` (14px, `--neutral` color).
- Tooltip or expandable section listing which data sources failed.
- The `data_gaps` field from the analysis output drives the list.
- Analysis still renders, with a note about reduced confidence.

### Rate Limit Error

When the Groq API or other external service returns 429:

- Inline error format (same as above) but with specific messaging.
- Message: "Rate limit reached. Please try again in a few minutes."
- No auto-retry (user must manually trigger).
- Icon: Lucide `Clock` (16px, `--neutral` color).

---

## Empty States

### No Analyses Yet

First-time user experience, no analysis history:

- Icon: Lucide `LineChart` (48px, `--text-muted`)
- Heading: "No analyses yet"
- Subtext: "Enter a ticker above to run your first analysis."
- CTA button: primary style, "Analyze a ticker"
- Centered in the main content area, soft radius (editorial zone)

### No Search Results

When a ticker search returns nothing:

- Icon: Lucide `SearchX` (48px, `--text-muted`)
- Heading: "No results found"
- Subtext: "Try a different ticker symbol (e.g., AAPL, MSFT, NVDA)."
- No CTA button needed (user can just type again)

### Empty Portfolio

When the portfolio view has no saved tickers:

- Icon: Lucide `Briefcase` (48px, `--text-muted`)
- Heading: "Your portfolio is empty"
- Subtext: "Add tickers to track their performance over time."
- CTA button: "Add your first ticker"

### General Pattern

All empty states follow this structure:

```html
<div class="flex flex-col items-center justify-center py-16 text-center">
  <Icon size={48} class="text-[var(--text-muted)] mb-4" />
  <h3 class="text-lg font-medium text-[var(--text-primary)]">Heading</h3>
  <p class="text-sm text-[var(--text-secondary)] mt-1 max-w-sm">Subtext</p>
  <button class="mt-4 ...">CTA</button>
</div>
```

---

## Accessibility Checklist

### Focus Indicators

- All interactive elements: visible focus ring on `:focus-visible`.
- Ring style: `ring-2 ring-offset-2 ring-[var(--ring)]`
- Ring offset color matches page background: `ring-offset-[var(--ring-offset)]`
- Implemented via the `.focus-ring` utility class.
- Never remove focus indicators.

### Icon Buttons

- Every icon-only button requires `aria-label` describing the action.
- Example: `<button aria-label="Close modal"><X size={16} /></button>`
- Decorative icons (next to visible text) use `aria-hidden="true"`.

### Color Independence

- Never convey meaning through color alone.
- Always pair color with an icon, text label, or pattern.
- Signal badges: icon + color + text (TrendingUp + green + "Buy").
- Status indicators: icon shape differs per state (circle, check, X).

### Motion

- Respect `prefers-reduced-motion: reduce` globally.
- When active: all animations disabled, transitions near-zero.
- No content gated behind animation. Everything appears immediately.
- Shimmer skeletons fall back to static blocks.

### Contrast

- Body text: minimum 4.5:1 ratio against background (WCAG AA).
- Large text (18px+ or 14px bold): minimum 3:1 ratio.
- Interactive UI elements: minimum 3:1 against adjacent colors.
- All four themes must independently meet these requirements.

### Semantic HTML

Use proper elements to convey document structure:

- `<main>`: primary content area (one per page)
- `<header>`: page header with nav
- `<nav>`: navigation links
- `<section>`: thematic grouping with heading
- `<article>`: self-contained analysis card
- `<footer>`: metadata, timestamps, source attribution

### Tab Order

- Logical order follows visual layout (left-to-right, top-to-bottom).
- Modal traps focus within while open.
- Escape closes modals and dropdowns.
- No tabindex values above 0 (rely on DOM order).

### Screen Readers

- `sr-only` class for visually hidden but readable labels.
- `aria-live="polite"` on streaming text containers.
- Signal badges include `aria-label` (e.g., "Bullish signal").
- Loading states announced via `aria-busy="true"` on container.
- Error messages linked to inputs via `aria-describedby`.

Note: full WCAG compliance requires manual testing with assistive technologies and expert accessibility review. This documents the implemented baseline.

---

## Component Naming Conventions

### File Naming

| Category | Pattern | Examples |
|----------|---------|----------|
| Pages | `*Page.tsx` | `StreamingAnalysisPage.tsx`, `DashboardPage.tsx` |
| Layouts | `*Layout.tsx` | `AppLayout.tsx`, `AnalysisLayout.tsx` |
| Cards | `*Card/index.tsx` | `AnalysisCard/index.tsx` with sub-components in same dir |
| Shared UI | `components/*.tsx` | `LoadingSpinner.tsx`, `DataFreshness.tsx`, `SignalBadge.tsx` |
| Hooks | `use*.ts` | `useAnalysisStream.ts`, `useTheme.ts` |
| Stores | `*Store.ts` | `themeStore.ts`, `analysisStore.ts` |

### Directory Structure

```
frontend/src/
  components/        # Shared, reusable UI components
    Header.tsx
    LoadingSpinner.tsx
    ThemeSwitcher.tsx
  components/__tests__/  # Component tests (co-located)
  hooks/             # Custom React hooks
    useAnalysisStream.ts
  hooks/__tests__/
  stores/            # Zustand stores
    themeStore.ts
  stores/__tests__/
  pages/             # Route-level page components
  test/              # Test utilities, setup, mocks
```

### Naming Rules

- Components: PascalCase, noun-first (`AnalysisCard`, not `CardAnalysis`).
- Hooks: camelCase, verb-first (`useTheme`, `useAnalysisStream`).
- Stores: camelCase, noun + "Store" (`themeStore`, `analysisStore`).
- Utilities: camelCase (`formatCurrency`, `parseTicker`).
- Constants: SCREAMING_SNAKE_CASE (`MAX_TICKERS`, `API_BASE_URL`).
- Test files: `*.test.ts` or `*.test.tsx`, mirror source structure.
