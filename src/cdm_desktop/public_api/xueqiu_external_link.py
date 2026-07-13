from __future__ import annotations

from cdm_desktop.public_api.models import ExternalSourceLink
from cdm_desktop.public_api.provider_health import utc_timestamp

XUEQIU_HOME_URL = "https://xueqiu.com/"
XUEQIU_STOCK_BASE_URL = "https://xueqiu.com/S/"
XUEQIU_COMPLIANCE_NOTE = (
    "External link only. This app does not scrape, cache, index, or summarize Xueqiu content."
)


class XueqiuCommunityLinkProvider:
    provider_id = "xueqiu_external"
    display_name = "Xueqiu Community Link"
    provider_type = "external_link"
    requires_api_key = False

    def build_link(
        self,
        *,
        symbol: str = "",
        exchange: str = "",
        market: str = "",
        company_name: str = "",
    ) -> ExternalSourceLink:
        return build_xueqiu_external_link(
            symbol=symbol,
            exchange=exchange,
            market=market,
            company_name=company_name,
        )

    def search(self, query: str, limit: int = 10) -> tuple[list[object], list[object], None]:
        _ = (query, limit)
        return [], [], None


def build_xueqiu_external_link(
    *,
    symbol: str = "",
    exchange: str = "",
    market: str = "",
    company_name: str = "",
) -> ExternalSourceLink:
    normalized_symbol = normalize_xueqiu_symbol(symbol=symbol, exchange=exchange, market=market)
    if normalized_symbol:
        return ExternalSourceLink(
            id=f"xueqiu:{normalized_symbol}",
            title="雪球社区入口",
            description="可在雪球查看该公司的行情页面、投资者讨论和社区动态。本应用仅提供外部链接。",
            url=f"{XUEQIU_STOCK_BASE_URL}{normalized_symbol}",
            symbol=normalized_symbol,
            market=_market_label(normalized_symbol),
            provider="xueqiu",
            provider_type="external_link",
            open_mode="system_browser",
            compliance_note=XUEQIU_COMPLIANCE_NOTE,
            created_at=_now(),
            is_direct_stock_link=True,
        )

    prompt = company_name or symbol or "company"
    return ExternalSourceLink(
        id="xueqiu:home",
        title="雪球社区入口",
        description=f"暂无可直接跳转的雪球股票代码。可手动打开雪球并搜索：{prompt}",
        url=XUEQIU_HOME_URL,
        symbol=symbol.strip().upper(),
        market="unknown",
        provider="xueqiu",
        provider_type="external_link",
        open_mode="system_browser",
        compliance_note=XUEQIU_COMPLIANCE_NOTE,
        created_at=_now(),
        is_direct_stock_link=False,
    )


def normalize_xueqiu_symbol(*, symbol: str = "", exchange: str = "", market: str = "") -> str:
    raw = _compact(symbol).upper()
    exchange_hint = f"{exchange} {market}".upper()
    if not raw:
        return ""

    if raw.startswith(("SH", "SZ")) and len(raw) == 8 and raw[2:].isdigit():
        return raw
    if raw.startswith("HK") and raw[2:].isdigit():
        return f"HK{int(raw[2:]):05d}"

    if raw.isdigit():
        if _is_hk_hint(exchange_hint) or len(raw) <= 5:
            return f"HK{int(raw):05d}"
        if len(raw) == 6 and raw.startswith("6"):
            return f"SH{raw}"
        if len(raw) == 6 and raw.startswith(("0", "3")):
            return f"SZ{raw}"
        return ""

    if raw.isalpha() and 1 <= len(raw) <= 6:
        return raw

    return ""


def _compact(value: str) -> str:
    return value.strip().replace(".", "").replace("-", "").replace("_", "").replace(" ", "")


def _is_hk_hint(value: str) -> bool:
    return any(token in value for token in ("HK", "HKEX", "HONG KONG", "港股", "香港"))


def _market_label(symbol: str) -> str:
    if symbol.startswith(("SH", "SZ")):
        return "A-share"
    if symbol.startswith("HK"):
        return "HK"
    return "US"


def _now() -> str:
    return utc_timestamp()
