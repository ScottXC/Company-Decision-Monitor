# UI Design System

Version scope: `v0.1.3`

## Principles

- Search and watchlist are the primary workflows.
- Lists, whitespace, typography, and dividers establish hierarchy before containers do.
- One page has one dominant action; secondary actions use compact controls or context menus.
- Technical diagnostics remain collapsed or live in Settings and the company Sources tab.
- Status color communicates state only. The product uses one green accent and no decorative gradients.
- No fake prices, charts, market values, risk levels, or trading controls are rendered.

The interface is inspired by the simplicity of modern financial tools, but it does not copy Robinhood trademarks, logos, proprietary assets, icons, or page compositions.

## Tokens

Tokens are defined in `src/cdm_desktop/ui/theme/tokens.py`. The spacing scale uses 4/8 px increments, page margins are 28 px, controls are 42-44 px high, content width is capped at 1240 px, and the navigation rail is 196 px wide.

Light mode uses an off-white application background, white primary surfaces, low-contrast gray dividers, near-black text, and a custom forest-green accent. Dark mode uses near-black backgrounds, dark neutral surfaces, near-white text, and a brighter green accent. Status colors remain readable in both themes.

## Typography

The preferred stack is Segoe UI Variable, Segoe UI, Microsoft YaHei UI, and the platform sans-serif fallback. Display text is 32 px, page titles 28 px, section headings 19 px, list titles 15 px, body text 14 px, and captions 12 px. Chinese and English use the same hierarchy.

## Components

- `PageHeader`: consistent title, subtitle, and page-level actions.
- `ListRow`: company/watchlist row with avatar, identity, metadata, one contextual action, and detail navigation.
- `NewsRow`: title-first news presentation with source/time metadata and an external-link action.
- `MetricCell`: borderless key-value summary used in company detail.
- `StatusBadge`: compact state pill; it is not decorative.
- `EmptyState`, `LoadingState`, `InlineError`: unified feedback states.
- `CollapsibleSection`: diagnostics and advanced information hidden by default.
- `ThemeManager`: persisted light/dark/system preference and live theme switching.

## Page layouts

Dashboard presents company search, a maximum of six watchlist rows, a real empty news state, and a single-line data status. Search uses a single-column result list. Company detail uses identity, real metrics only, and tabs for overview, news, registration, sources, securities, and web evidence. Watchlist uses rows plus a context menu. Settings separates appearance, sources, search, privacy, advanced providers, web evidence, and about information.

## Accessibility

- `Ctrl+K` focuses global search; Enter submits; Escape dismisses focus.
- Icon buttons have tooltips and accessible names.
- Focus rings are visible in both themes.
- Statuses include text and do not depend only on color.
- Minimum window size is 1100 x 700 and content uses scroll areas without horizontal scrolling.
- Font sizes remain readable at Windows 125% and 150% scaling.

## Feedback

Page-local failures use `InlineError`; loading uses lightweight skeleton/state rows; destructive actions use confirmation dialogs; successful watchlist additions use a non-blocking status message. Raw exceptions, tracebacks, JSON, API keys, and provider class names are not normal UI content.

## Prohibited patterns

- Card inside card, card grids for every status, thick borders, decorative gradients, neon effects, emoji icons, fake charts, raw URLs in primary content, multiple equal-weight buttons per row, and visible provider diagnostics on Dashboard.
- Robinhood trademarks or branded assets.
- Trading, order, portfolio, P&L, target-price, or return-forecast interfaces.
