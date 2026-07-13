# Company Profile Enrichment

## Loading stages

Company details are loaded independently from ordinary search and news. Opening a company first creates an immediate profile from the selected search result and the bundled symbol universe. Public sources then enrich that profile in background workers. Website evidence is only collected after an explicit user action.

## Immediate local profile

`SymbolUniverseProvider.profile()` opens the bundled SQLite index read-only and resolves the selected normalized symbol. It returns only fields present in the generated FinanceDatabase index: company name, symbol, exchange, market, country, currency, sector, industry, and instrument type. It does not provide price, market capitalization, a company description, or an official website.

## Public enrichment

- **Wikidata:** When no QID is available, the provider searches company names and aliases, scores candidates, and accepts only high-confidence matches. It can supplement labels, aliases, descriptions, website, ticker, inception date, QID, and Wikipedia URL. It is not a financial authority.
- **GLEIF:** When no LEI is available, the provider searches a sufficiently specific legal/full company name. Country and jurisdiction improve candidate scores. Ambiguous candidates are not adopted. Accepted records can supply legal name, LEI, jurisdiction, entity/registration status, and legal address.
- **AKShare:** Optional and experimental. For China/Hong Kong companies it can map public, no-login symbol-list fields and stable metadata returned by installed AKShare interfaces. Failure is isolated and never blocks local details.
- **Advanced API providers:** FMP and Alpha Vantage remain disabled by default and run only when advanced providers are explicitly enabled.

## Website evidence

The company detail page can use the optional crawlergo integration only after a user clicks the website-evidence action. Collection remains same-domain, bounded, robots-compliant, and excludes Xueqiu. Extracted evidence is shown separately; it is not automatically allowed to overwrite profile fields. A future confirmation flow may map high-confidence Organization JSON-LD fields to `official_website_evidence` while retaining the original URL.

## Merge priorities

- Security identity: bundled symbol universe, AKShare for China/Hong Kong, then explicitly enabled advanced market sources.
- Description and website: official website evidence, AKShare, Wikidata, then advanced providers.
- Industry: AKShare for China/Hong Kong, bundled symbol universe, advanced providers, then Wikidata.
- Legal fields: official registry, GLEIF, then confirmed official website evidence.
- Price and market capitalization: reliable enabled market provider or stable AKShare field only. Otherwise the fields remain absent.

Empty strings, placeholder text, string nulls, and semantically meaningless zero market fields never overwrite a meaningful value. Conflicting lower-priority candidates are retained in diagnostics instead of being displayed as authoritative values.

## Field sources and coverage

`field_sources` records the selected provider for each populated field. `field_candidates` stores conflicting alternatives for diagnostics. `ProfileCoverage` reports identity, market, classification, legal, contact, and total field coverage. Coverage indicates field presence only and is not an accuracy or authority score.

## Cache schema

Profile cache keys include normalized symbol, exchange/market, LEI, Wikidata ID, normalized company name, provider mode, and `PROFILE_SCHEMA_VERSION`. Cache entries from older schemas are not returned as current profile results. Compatible old dictionaries remain readable through `CompanyProfile.from_dict()`.

## Limitations

- The bundled index is not a real-time market source.
- Public entity and legal-name matching is best-effort and confidence-gated.
- AKShare is optional and depends on changing public upstream interfaces.
- Many companies have no reliable no-key price, market capitalization, registry record, or news coverage.
- No field is fabricated to improve visual completeness.
