# Third-Party Open-Source Notices

Company Decision Monitor v0.1.5 includes or references the following open-source components for Open-Source Data Mode. These components do not require ordinary users to apply for API keys.

| Component | Project URL | Purpose | License | Distributed with app | Notes |
|---|---|---|---|---|---|
| RapidFuzz | https://github.com/rapidfuzz/RapidFuzz | Fuzzy matching, alias matching, result ranking, deduplication, and news-title similarity. | MIT | Yes | Runtime dependency bundled by PyInstaller. License text: `third_party/licenses/RapidFuzz_LICENSE.txt`. |
| cleanco | https://github.com/psolin/cleanco | Company name cleaning and legal suffix removal for English company names. | MIT | Yes | Runtime dependency bundled by PyInstaller. License text: `third_party/licenses/cleanco_LICENSE.txt`. |
| FinanceDatabase | https://github.com/JerBouma/FinanceDatabase | Build-time source for the generated local symbol universe index. | MIT | Generated index only | The Python package is used to generate `symbol_universe.sqlite`; the normal runtime reads the bundled SQLite index and does not require users to install FinanceDatabase. License text: `third_party/licenses/FinanceDatabase_LICENSE.txt`. |
| AKShare 1.18.64 | https://github.com/akfamily/akshare | Build-time China/HK security lists and experimental, on-demand company-profile enrichment. | MIT | Yes | Bundled and lazy-loaded. No login, cookie, token, captcha bypass, Xueqiu interface, or article-body scraping. License: `third_party/licenses/AKShare_LICENSE.txt`. |
| pandas / NumPy | https://pandas.pydata.org/ / https://numpy.org/ | Data-frame and numerical runtime required by AKShare. | BSD-3-Clause / BSD-3-Clause | Yes | Transitive AKShare runtime dependencies collected by PyInstaller. |
| curl_cffi | https://github.com/lexiforest/curl_cffi | HTTP runtime required by current AKShare releases. | MIT | Yes | Used only through supported AKShare public interfaces; no browser impersonation is configured by this application. |
| html5lib / xlrd / openpyxl | https://github.com/html5lib/html5lib-python / https://github.com/python-excel/xlrd / https://openpyxl.readthedocs.io/ | Public table/document parsing required by AKShare. | MIT / BSD-3-Clause / MIT | Yes | Transitive runtime dependencies. |
| Beautiful Soup 4 | https://www.crummy.com/software/BeautifulSoup/ | Parse public HTML and extract metadata, JSON-LD, headings, links, and cleaned evidence text. | MIT | Yes | Direct Web Evidence dependency. License text: `third_party/licenses/BeautifulSoup_LICENSE.txt`. Raw HTML is not persisted by default. |
| lxml | https://lxml.de/ | HTML parser backend used by Beautiful Soup. | BSD-3-Clause with documented bundled-resource exceptions | Yes | Direct Web Evidence parser dependency. License text and upstream exception notice: `third_party/licenses/lxml_LICENSE.txt`. |
| crawlergo | https://github.com/Qianlitp/crawlergo | Optional external runtime detection and diagnostics for Web Evidence. | GPL-3.0 | No | Not bundled or executed for production discovery in v0.1.5. The audited upstream runtime cannot disable form submission and DOM-event triggering, so active collection uses the app's bounded GET-only pipeline. No crawlergo or Chromium binary is downloaded or distributed. |

The bundled symbol universe index is metadata only. It is not realtime market data, not a financial statement database, and not investment advice.
