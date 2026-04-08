from __future__ import annotations

from typing import TYPE_CHECKING

from ..config import Settings

if TYPE_CHECKING:
    from ..domains.marketplace.api import WildberriesApiClient


def build_wildberries_client(settings: Settings) -> WildberriesApiClient:
    if not settings.wb_api_token:
        raise RuntimeError("WB_API_TOKEN is not configured.")
    from ..domains.marketplace.api import WildberriesApiClient

    return WildberriesApiClient(
        token=settings.wb_api_token,
        timeout_seconds=settings.wb_api_timeout_seconds,
    )
