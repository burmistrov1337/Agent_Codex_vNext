from __future__ import annotations

from ..config import Settings
from ..domains.marketplace.api import WildberriesApiClient


def build_wildberries_client(settings: Settings) -> WildberriesApiClient:
    if not settings.wb_api_token:
        raise RuntimeError("WB_API_TOKEN is not configured.")
    return WildberriesApiClient(token=settings.wb_api_token)
