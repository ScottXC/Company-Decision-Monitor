# External Sources

## Xueqiu External Source

### Positioning

The Xueqiu integration is an `external_link` provider, a community-source entry point, and a manual browser handoff. It is not a news crawler, API connector, content provider, RAG source, or AI summary source.

### Compliance Boundaries

- No scraping.
- No unofficial API.
- No user cookies or tokens.
- No login bypass, captcha bypass, anti-bot bypass, or risk-control bypass.
- No content cache.
- No indexing.
- No AI or RAG ingestion.
- No post, comment, body text, or user speech extraction.
- No content summary.

The application only generates a safe external URL and opens it in the system browser after the user clicks the button.

### Supported Link Types

- A-share links, for example `600519 -> https://xueqiu.com/S/SH600519`.
- Hong Kong links, for example `700 -> https://xueqiu.com/S/HK00700`.
- U.S. stock links, for example `AAPL -> https://xueqiu.com/S/AAPL`.
- Homepage fallback, `https://xueqiu.com/`, when the market cannot be determined.

The app does not construct unstable search endpoints and does not request `/query/`, `/v5/stock/`, or JSON endpoints.

### Future Expansion Conditions

Deeper Xueqiu integration should only be considered with explicit Xueqiu authorization, an official API or partnership, user-visible compliance notices, source attribution, and a documented privacy/security review.
