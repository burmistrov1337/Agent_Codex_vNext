from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib import error, request
from urllib.parse import urlencode


class WildberriesApiError(RuntimeError):
    pass


@dataclass(slots=True)
class WildberriesApiClient:
    token: str
    timeout_seconds: int = 30

    def request_json(self, url: str, method: str = "GET", data: Any | None = None) -> Any:
        payload = None
        if data is not None:
            payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
        req = request.Request(
            url=url,
            headers={
                "Authorization": self.token,
                "Content-Type": "application/json",
            },
            data=payload,
            method=method,
        )
        try:
            with request.urlopen(req, timeout=self.timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise WildberriesApiError(f"WB API HTTP {exc.code}: {detail}") from exc
        except error.URLError as exc:
            raise WildberriesApiError(f"WB API connection error: {exc.reason}") from exc

    def get(self, url: str) -> Any:
        return self.request_json(url=url, method="GET")

    def post(self, url: str, data: Any) -> Any:
        return self.request_json(url=url, method="POST", data=data)

    def _append_query(self, url: str, params: dict[str, Any]) -> str:
        query_params: list[tuple[str, Any]] = []
        for key, value in params.items():
            if value is None:
                continue
            if isinstance(value, (list, tuple)):
                for item in value:
                    if item is not None:
                        query_params.append((key, item))
                continue
            query_params.append((key, value))
        if not query_params:
            return url
        return f"{url}?{urlencode(query_params, doseq=True)}"

    def get_supplier_sales(self, date_from: str) -> Any:
        return self.get(
            f"https://statistics-api.wildberries.ru/api/v1/supplier/sales?dateFrom={date_from}"
        )

    def get_supplier_orders(self, date_from: str) -> Any:
        return self.get(
            f"https://statistics-api.wildberries.ru/api/v1/supplier/orders?dateFrom={date_from}"
        )

    def get_supplier_stocks(self, date_from: str) -> Any:
        return self.get(
            f"https://statistics-api.wildberries.ru/api/v1/supplier/stocks?dateFrom={date_from}"
        )

    def get_seller_warehouses(self) -> Any:
        return self.get("https://marketplace-api.wildberries.ru/api/v3/warehouses")

    def get_warehouse_inventory(
        self,
        warehouse_id: int,
        *,
        skus: list[str] | None = None,
        chrt_ids: list[int] | None = None,
    ) -> Any:
        payload: dict[str, Any] = {}
        if skus:
            payload["skus"] = skus
        if chrt_ids:
            payload["chrtIds"] = chrt_ids
        return self.post(
            f"https://marketplace-api.wildberries.ru/api/v3/stocks/{warehouse_id}",
            payload,
        )

    def get_content_cards(
        self,
        limit: int = 100,
        text_search: str | None = None,
        with_photo: int | None = -1,
        cursor_nm_id: int | None = None,
        cursor_updated_at: str | None = None,
    ) -> Any:
        payload: dict[str, Any] = {
            "settings": {
                "cursor": {
                    "limit": limit,
                }
            }
        }
        if cursor_nm_id is not None:
            payload["settings"]["cursor"]["nmID"] = cursor_nm_id
        if cursor_updated_at:
            payload["settings"]["cursor"]["updatedAt"] = cursor_updated_at

        filter_payload: dict[str, Any] = {}
        if with_photo is not None:
            filter_payload["withPhoto"] = with_photo
        if text_search:
            filter_payload["textSearch"] = text_search
        if filter_payload:
            payload["settings"]["filter"] = filter_payload
        return self.post(
            "https://content-api.wildberries.ru/content/v2/get/cards/list",
            payload,
        )

    def get_hs_codes(self, subject_id: int, search: str | None = None, locale: str = "ru") -> Any:
        url = (
            "https://content-api.wildberries.ru/content/v2/directory/tnved"
            f"?subjectID={subject_id}&locale={locale}"
        )
        if search:
            url += f"&search={search}"
        return self.get(url)

    def get_sales_funnel_products(self, data: Any) -> Any:
        return self.post(
            "https://seller-analytics-api.wildberries.ru/api/analytics/v3/sales-funnel/products",
            data,
        )

    def get_sales_funnel_products_history(self, data: Any) -> Any:
        return self.post(
            "https://seller-analytics-api.wildberries.ru/api/analytics/v3/sales-funnel/products/history",
            data,
        )

    def get_search_report_product_search_texts(self, data: Any) -> Any:
        return self.post(
            "https://seller-analytics-api.wildberries.ru/api/v2/search-report/product/search-texts",
            data,
        )

    def get_search_report_table_groups(self, data: Any) -> Any:
        return self.post(
            "https://seller-analytics-api.wildberries.ru/api/v2/search-report/table/groups",
            data,
        )

    def get_search_report_product_orders(self, data: Any) -> Any:
        return self.post(
            "https://seller-analytics-api.wildberries.ru/api/v2/search-report/product/orders",
            data,
        )

    def get_stocks_report_products(self, data: Any) -> Any:
        return self.post(
            "https://seller-analytics-api.wildberries.ru/api/v2/stocks-report/products/products",
            data,
        )

    def get_wb_warehouses_inventory(self, data: Any) -> Any:
        return self.post(
            "https://seller-analytics-api.wildberries.ru/api/analytics/v1/stocks-report/wb-warehouses",
            data,
        )

    def get_prices_goods_filter(
        self,
        *,
        limit: int = 1000,
        offset: int = 0,
        filter_nm_id: int | None = None,
    ) -> Any:
        url = self._append_query(
            "https://discounts-prices-api.wildberries.ru/api/v2/list/goods/filter",
            {
                "limit": limit,
                "offset": offset,
                "filterNmID": filter_nm_id,
            },
        )
        return self.get(url)

    def get_prices_goods_filter_by_nm_ids(self, nm_ids: list[int]) -> Any:
        return self.post(
            "https://discounts-prices-api.wildberries.ru/api/v2/list/goods/filter",
            {"nmList": nm_ids},
        )

    def get_promotion_campaign_counts(self) -> Any:
        return self.get("https://advert-api.wildberries.ru/adv/v1/promotion/count")

    def get_promotion_adverts(
        self,
        *,
        ids: list[int] | None = None,
        statuses: list[int] | None = None,
        payment_type: str | None = None,
    ) -> Any:
        url = self._append_query(
            "https://advert-api.wildberries.ru/api/advert/v2/adverts",
            {
                "ids": ",".join(str(item) for item in ids) if ids else None,
                "statuses": ",".join(str(item) for item in statuses) if statuses else None,
                "payment_type": payment_type,
            },
        )
        return self.get(url)

    def get_promotion_calendar_promotions(
        self,
        *,
        start_datetime: str,
        end_datetime: str,
        all_promo: bool = False,
        limit: int = 1000,
        offset: int = 0,
    ) -> Any:
        url = self._append_query(
            "https://dp-calendar-api.wildberries.ru/api/v1/calendar/promotions",
            {
                "startDateTime": start_datetime,
                "endDateTime": end_datetime,
                "allPromo": str(all_promo).lower(),
                "limit": limit,
                "offset": offset,
            },
        )
        return self.get(url)

    def get_promotion_calendar_details(self, promotion_ids: list[int]) -> Any:
        url = self._append_query(
            "https://dp-calendar-api.wildberries.ru/api/v1/calendar/promotions/details",
            {"promotionIDs": promotion_ids},
        )
        return self.get(url)

    def get_promotion_calendar_nomenclatures(
        self,
        *,
        promotion_id: int,
        in_action: bool,
        limit: int = 1000,
        offset: int = 0,
    ) -> Any:
        url = self._append_query(
            "https://dp-calendar-api.wildberries.ru/api/v1/calendar/promotions/nomenclatures",
            {
                "promotionID": promotion_id,
                "inAction": str(in_action).lower(),
                "limit": limit,
                "offset": offset,
            },
        )
        return self.get(url)

    def get_new_feedbacks_questions(self) -> Any:
        return self.get("https://feedbacks-api.wildberries.ru/api/v1/new-feedbacks-questions")

    def get_questions_count_unanswered(self) -> Any:
        return self.get("https://feedbacks-api.wildberries.ru/api/v1/questions/count-unanswered")

    def get_questions_count(
        self,
        *,
        date_from: int | None = None,
        date_to: int | None = None,
        is_answered: bool | None = None,
    ) -> Any:
        url = self._append_query(
            "https://feedbacks-api.wildberries.ru/api/v1/questions/count",
            {
                "dateFrom": date_from,
                "dateTo": date_to,
                "isAnswered": str(is_answered).lower() if is_answered is not None else None,
            },
        )
        return self.get(url)

    def get_questions(
        self,
        *,
        is_answered: bool,
        take: int,
        skip: int,
        nm_id: int | None = None,
        order: str = "dateDesc",
        date_from: int | None = None,
        date_to: int | None = None,
    ) -> Any:
        url = self._append_query(
            "https://feedbacks-api.wildberries.ru/api/v1/questions",
            {
                "isAnswered": str(is_answered).lower(),
                "nmId": nm_id,
                "take": take,
                "skip": skip,
                "order": order,
                "dateFrom": date_from,
                "dateTo": date_to,
            },
        )
        return self.get(url)

    def get_feedbacks_count_unanswered(self) -> Any:
        return self.get("https://feedbacks-api.wildberries.ru/api/v1/feedbacks/count-unanswered")

    def get_feedbacks_count(
        self,
        *,
        date_from: int | None = None,
        date_to: int | None = None,
        is_answered: bool | None = None,
    ) -> Any:
        url = self._append_query(
            "https://feedbacks-api.wildberries.ru/api/v1/feedbacks/count",
            {
                "dateFrom": date_from,
                "dateTo": date_to,
                "isAnswered": str(is_answered).lower() if is_answered is not None else None,
            },
        )
        return self.get(url)

    def get_feedbacks(
        self,
        *,
        is_answered: bool,
        take: int,
        skip: int,
        nm_id: int | None = None,
        order: str = "dateDesc",
        date_from: int | None = None,
        date_to: int | None = None,
    ) -> Any:
        url = self._append_query(
            "https://feedbacks-api.wildberries.ru/api/v1/feedbacks",
            {
                "isAnswered": str(is_answered).lower(),
                "nmId": nm_id,
                "take": take,
                "skip": skip,
                "order": order,
                "dateFrom": date_from,
                "dateTo": date_to,
            },
        )
        return self.get(url)
