# Open-Source Integration Candidates

Version scope: `v0.1.3-bundled-open-source-runtime`

This document records project-level evaluation for open-source/no-key integrations. Exact license and packaging impact should be rechecked before each formal release because upstream packages can change.

| Project | Purpose | License / packaging note | Decision | Default | Risk |
|---|---|---|---|---|---|
| FinanceDatabase | Build-time source for global equities symbol universe metadata | MIT; package has sizable dependency surface | Used to generate bundled `symbol_universe.sqlite`; normal runtime does not import it | Build-time only | Generated index is not realtime data; regeneration requires build environment |
| RapidFuzz | Fuzzy matching, alias matching, ranking, deduplication, news title similarity | MIT; already a lightweight dependency in this project | Core fuzzy matcher | Enabled | Chinese short strings need conservative scoring |
| cleanco | English company-name suffix cleaning | Lightweight open-source dependency | Added as core dependency with fallback | Enabled if installed | English-focused; Chinese suffixes handled internally |
| AKShare | China A-share / Hong Kong public symbol/name fallback | Not bundled in this release; broader dependency surface; recheck upstream license before distribution | Optional experimental provider, not required by main runtime | Optional | Public interfaces can change; no login/cookie/token endpoints allowed |
| name_matching | Specialized company-name matching | Optional; not required for current ranking layer | Evaluated only | No | Extra dependency not justified for v0.1.3 |
| pygleif | GLEIF wrapper | Optional wrapper | Not added | No | Current direct GLEIF implementation is lighter |
| leipy | LEI helper/wrapper | Optional wrapper | Not added | No | Current direct GLEIF implementation is sufficient |
| yfinance | Yahoo Finance data access | Public unofficial source; terms and stability concerns | Not added to core | No | Not an official data contract; may be brittle |
| yahooquery | Yahoo Finance query wrapper | Public unofficial source; dependency and terms concerns | Not added to core | No | Not needed for no-key search fallback |
| OpenBB | Broad financial data platform | Heavy dependency surface and broader licensing/packaging concerns | Not added | No | Too large for current desktop MVP |

## v0.1.3 Inclusion

Included in code path:

- RapidFuzz, with difflib fallback.
- cleanco, with internal suffix fallback.
- FinanceDatabase-generated bundled symbol index through `SymbolUniverseProvider`.
- AKShare provider, optional dependency.

Not included in runtime:

- name_matching.
- pygleif / leipy.
- yfinance / yahooquery.
- OpenBB.

## Compliance Notes

- Optional providers must fail gracefully with `dependency_missing`.
- Optional providers must not block Nasdaq, Wikidata, GLEIF, or RSS fallback.
- AKShare integration must not use login-gated, cookie, token, captcha, or anti-bot bypass interfaces.
- Xueqiu remains external link only and is not part of this candidate provider list.
