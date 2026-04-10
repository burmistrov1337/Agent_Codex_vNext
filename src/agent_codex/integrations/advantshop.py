from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib import error, parse, request

from ..config import Settings
from ..errors import ApiError, ConfigError


class AdvantShopApiError(ApiError):
    pass


@dataclass(slots=True)
class AdvantShopClient:
    base_url: str
    api_key: str
    auth_api_key: str | None = None
    timeout_seconds: int = 30

    def request_json(
        self,
        path: str,
        *,
        method: str = "GET",
        data: Any | None = None,
        query: dict[str, Any] | None = None,
        use_auth: bool = False,
    ) -> Any:
        params = {key: value for key, value in (query or {}).items() if value is not None}
        params["apikey"] = self.auth_api_key if use_auth and self.auth_api_key else self.api_key
        url = f"{self.base_url.rstrip('/')}/{path.lstrip('/')}"
        if params:
            url = f"{url}?{parse.urlencode(params, doseq=True)}"

        payload = None
        headers = {"Accept": "application/json"}
        if data is not None:
            payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"

        req = request.Request(url=url, method=method.upper(), data=payload, headers=headers)
        try:
            with request.urlopen(req, timeout=self.timeout_seconds) as response:
                body = response.read().decode("utf-8")
                return json.loads(body) if body else {}
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise AdvantShopApiError(f"AdvantShop API HTTP {exc.code}: {detail}") from exc
        except error.URLError as exc:
            raise AdvantShopApiError(f"AdvantShop API connection error: {exc.reason}") from exc

    def get_catalog_all(self) -> Any:
        return self.request_json("/api/catalog/all", method="POST", data={}, use_auth=True)

    def get_orders_list(
        self,
        *,
        page: int = 1,
        items_per_page: int = 50,
        load_items: bool = True,
        date_from: str | None = None,
        date_to: str | None = None,
        modified_date_from: str | None = None,
        modified_date_to: str | None = None,
    ) -> Any:
        return self.request_json(
            "/api/order/getlist",
            method="POST",
            data={
                "Page": page,
                "ItemsPerPage": items_per_page,
                "LoadItems": load_items,
                "DateFrom": date_from,
                "DateTo": date_to,
                "ModifiedDateFrom": modified_date_from,
                "ModifiedDateTo": modified_date_to,
            },
        )

    def get_product_stocks(self, product_id: int, *, offer_id: int | None = None) -> Any:
        query = {"offerId": offer_id} if offer_id is not None else None
        return self.request_json(
            f"/api/products/{product_id}/stocks",
            query=query,
            use_auth=True,
        )


def build_advantshop_client(settings: Settings) -> AdvantShopClient:
    if not settings.advantshop_api_url:
        raise ConfigError("ADVANTSHOP_API_URL is not configured.")
    api_key = settings.advantshop_api or settings.advantshop_api_auth
    if not api_key:
        raise ConfigError("ADVANTSHOP_API or ADVANTSHOP_API_AUTH is not configured.")
    return AdvantShopClient(
        base_url=settings.advantshop_api_url,
        api_key=api_key,
        auth_api_key=settings.advantshop_api_auth,
        timeout_seconds=settings.wb_api_timeout_seconds,
    )
