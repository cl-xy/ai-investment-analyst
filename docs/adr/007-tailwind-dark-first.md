# ADR-007: Tailwind 3 with Dark-First Design Tokens

**Status:** Accepted
**Date:** 2026-07-15
**Deciders:** cl-xy

## Context

The application targets developers and finance professionals. Both audiences tend to prefer dark interfaces, especially for data-heavy dashboards they spend extended time viewing. The UI needs to feel polished in dark mode first, with light mode as a secondary option.

I also wanted consistent theming without CSS-in-JS overhead or runtime style generation.

## Decision

Use Tailwind 3 with CSS custom properties for theming, dark mode as the default, and Lucide React for icons.

Implementation:
- Design tokens defined as CSS custom properties on `:root` (which is dark).
- Light mode tokens on `[data-theme="light"]`.
- Tailwind classes reference these tokens via `var()` in arbitrary value syntax or through the tailwind config.
- Lucide icons exclusively (no emoji in the production UI) for visual consistency.

Reasons:

- CSS custom properties give runtime theme switching without re-rendering the component tree.
- Dark-first means the default experience is polished for the primary audience. Light mode is an accommodation, not an afterthought.
- Tailwind's utility classes eliminate naming debates and keep styles co-located with markup.
- Lucide provides a consistent icon set with proper SVG accessibility attributes.
- No CSS-in-JS means no runtime overhead, no hydration mismatches, and simpler build output.

## Consequences

**Easier:**
- Theme switching is a single data attribute change on the root element.
- Consistent visual language via constrained token palette.
- Icons are uniform in size, stroke weight, and style.
- No runtime style computation.

**Harder:**
- CSS custom properties don't work with Tailwind's JIT opacity modifier (use rgba tokens instead).
- Must manually ensure both themes maintain contrast ratios (WCAG AA).
- Lucide doesn't cover every possible icon need (acceptable tradeoff for consistency).
