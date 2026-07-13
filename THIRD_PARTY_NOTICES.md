# Third-Party Open-Source Notices

Company Decision Monitor v0.1.3-bundled-open-source-runtime includes or references the following open-source components for Open-Source Data Mode. These components do not require ordinary users to apply for API keys.

| Component | Project URL | Purpose | License | Distributed with app | Notes |
|---|---|---|---|---|---|
| RapidFuzz | https://github.com/rapidfuzz/RapidFuzz | Fuzzy matching, alias matching, result ranking, deduplication, and news-title similarity. | MIT | Yes | Runtime dependency bundled by PyInstaller. License text: `third_party/licenses/RapidFuzz_LICENSE.txt`. |
| cleanco | https://github.com/psolin/cleanco | Company name cleaning and legal suffix removal for English company names. | MIT | Yes | Runtime dependency bundled by PyInstaller. License text: `third_party/licenses/cleanco_LICENSE.txt`. |
| FinanceDatabase | https://github.com/JerBouma/FinanceDatabase | Build-time source for the generated local symbol universe index. | MIT | Generated index only | The Python package is used to generate `symbol_universe.sqlite`; the normal runtime reads the bundled SQLite index and does not require users to install FinanceDatabase. License text: `third_party/licenses/FinanceDatabase_LICENSE.txt`. |
| AKShare | https://github.com/akfamily/akshare | Optional experimental China/HK provider for public no-key interfaces. | Not distributed in this package; recheck upstream before bundling | No | Not bundled as a core runtime dependency in this release because of dependency size and public-source stability risk. Provider reports `dependency_missing` unless an advanced runtime includes it. |
| crawlergo | https://github.com/Qianlitp/crawlergo | Optional external binary for user-triggered webpage evidence discovery on authorized public sites. | GPL-3.0 | No | Not bundled. Users may configure their own crawlergo path in advanced settings. The app does not vendor crawlergo, does not bypass robots/login/captcha, and does not crawl Xueqiu content. |

The bundled symbol universe index is metadata only. It is not realtime market data, not a financial statement database, and not investment advice.
