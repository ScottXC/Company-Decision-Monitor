from __future__ import annotations

from cdm_desktop.connectors.manual_url import ManualUrlConnector


class WebPageConnector(ManualUrlConnector):
    source_type = "webpage"
