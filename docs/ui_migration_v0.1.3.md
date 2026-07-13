# UI Migration v0.1.3

## Removed visual debt

- Removed the monolithic `styles.qss`; light and dark themes now live under `ui/theme/`.
- Removed the company-detail item from persistent navigation.
- Removed Dashboard metric-card grids, provider diagnostics, and duplicate navigation buttons.
- Removed search result card nesting, visible match scores, raw source actions, and the permanent diagnostics side column.
- Removed multiple text actions from each watchlist row; refresh is compact and destructive/secondary actions use a context menu.
- Removed provider ID pills from advanced settings rows.

## Rebuilt components

- Main application shell, navigation, top bar, global search field, page headers, section styling, status pills, empty/loading/error states, company rows, watchlist rows, news rows, avatars, metric cells, and theme switching.

## New components

- `ThemeManager`, centralized theme tokens, `CompanyAvatar`, `IconButton`, `ListRow`, `NewsRow`, `MetricCell`, `InlineError`, and `Divider`.

## Page migration

- Dashboard: search-first entry, compact watchlist preview, real empty news state, and one-line data status.
- Search: single-column rows and collapsed diagnostics while preserving incremental local/background results.
- Company detail: identity-led header, metrics only when values exist, tab-based information, and row-based news.
- Watchlist: searchable/sortable list, row navigation, compact refresh, and context actions.
- Settings: appearance and theme controls plus user-facing source groups; advanced provider and crawlergo settings remain separated.

## Preserved business behavior

Symbol Universe/SQLite/FTS5 search, RapidFuzz shortlist, 350 ms debounce, request IDs, cancellation, QThreadPool workers, public background enrichment, on-demand profiles/news, cache fallback, local watchlist persistence/refresh, API-key masking/redaction, Xueqiu external-link-only behavior, and frozen SQLite self-test were not replaced.

## Known limitations

- Global search suggestions use only the bundled local index; public enrichment begins after opening the full search page.
- Recent global searches are session-local and are not yet persisted across restarts.
- Some advanced provider forms remain dense because their configuration fields are preserved for compatibility.
- Automatic screenshot validation uses deterministic local data and offscreen Qt; final font rendering and DPI should also be checked on a physical Windows display.
