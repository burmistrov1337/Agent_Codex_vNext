from __future__ import annotations

from datetime import datetime, timedelta, timezone


class SampleWildberriesClient:
    def __init__(self) -> None:
        self._now = datetime(2026, 4, 1, tzinfo=timezone.utc)

    def get_content_cards(self, limit: int = 100, **_: object) -> dict:
        cards = [
            {
                "nmID": 1001,
                "vendorCode": "SKU-1001",
                "title": "Бромелаин 5г",
                "subjectName": "Косметические активы",
                "subjectID": 2926,
                "brand": "ADK",
                "description": "Актив для косметических формул.",
                "sizes": [{"skus": ["1001001"]}],
            },
            {
                "nmID": 1002,
                "vendorCode": "SKU-1002",
                "title": "Церамиды 30г",
                "subjectName": "Косметические активы",
                "subjectID": 2926,
                "brand": "ADK",
                "description": "Восстановление барьера кожи.",
                "sizes": [{"skus": ["1002001"]}],
            },
            {
                "nmID": 1003,
                "vendorCode": "SKU-1003",
                "title": "Шампунь глубокого очищения 300 мл",
                "subjectName": "Средства для волос",
                "subjectID": 5000,
                "brand": "ADK",
                "description": "Шампунь для глубокого очищения.",
                "sizes": [{"skus": ["1003001"]}],
            },
        ]
        return {"cards": cards, "cursor": {"total": len(cards)}}

    def get_supplier_sales(self, date_from: str) -> list[dict]:
        start = datetime.fromisoformat(date_from)
        sales = []
        for day in range(15):
            dt = start + timedelta(days=day)
            sales.append({"nmId": 1001, "quantity": 1, "forPay": 1200, "date": dt.isoformat()})
        for day in range(30):
            dt = start + timedelta(days=day)
            sales.append({"nmId": 1002, "quantity": 2, "forPay": 1800, "date": dt.isoformat()})
        for day in range(5):
            dt = start + timedelta(days=day)
            sales.append({"nmId": 1003, "quantity": 1, "forPay": 900, "date": dt.isoformat()})
        return sales

    def get_supplier_orders(self, date_from: str) -> list[dict]:
        start = datetime.fromisoformat(date_from)
        return [
            {"nmId": 1001, "quantity": 1, "date": (start + timedelta(days=2)).isoformat()},
            {"nmId": 1002, "quantity": 3, "date": (start + timedelta(days=6)).isoformat()},
            {"nmId": 1003, "quantity": 1, "date": (start + timedelta(days=9)).isoformat()},
        ]

    def get_supplier_stocks(self, date_from: str) -> list[dict]:
        return [
            {"nmId": 1001, "quantity": 24, "barcode": "1001001", "inWayToClient": 0, "inWayFromClient": 0},
            {"nmId": 1002, "quantity": 12, "barcode": "1002001", "inWayToClient": 0, "inWayFromClient": 0},
            {"nmId": 1003, "quantity": 45, "barcode": "1003001", "inWayToClient": 0, "inWayFromClient": 0},
        ]

    def get_seller_warehouses(self) -> list[dict]:
        return [{"id": 1, "name": "Новосибирск"}]

    def get_warehouse_inventory(self, warehouse_id: int, *, skus=None, chrt_ids=None) -> dict:
        items = [
            {"sku": "1001001", "amount": 24, "barcode": "1001001"},
            {"sku": "1002001", "amount": 12, "barcode": "1002001"},
            {"sku": "1003001", "amount": 45, "barcode": "1003001"},
        ]
        return {"stocks": items}

    def get_prices_goods_filter_by_nm_ids(self, nm_ids: list[int]) -> dict:
        prices = {
            1001: {"nmID": 1001, "price": 1400, "discount": 10, "discountedPrice": 1260, "isBadTurnover": False},
            1002: {"nmID": 1002, "price": 1900, "discount": 5, "discountedPrice": 1805, "isBadTurnover": False},
            1003: {"nmID": 1003, "price": 950, "discount": 0, "discountedPrice": 950, "isBadTurnover": True},
        }
        return {"data": {"listGoods": [prices[nm_id] for nm_id in nm_ids if nm_id in prices]}}

    def get_hs_codes(self, subject_id: int, search: str | None = None, locale: str = "ru") -> list[str]:
        if subject_id == 2926:
            return ["3304990000", "3824999307"]
        return ["3305900009"]

    def __getattr__(self, name: str):
        def _fallback(*args, **kwargs):
            if name.startswith("get_feedbacks") or name.startswith("get_questions"):
                return {"data": {"feedbacks": [], "questions": []}}
            if "promotion" in name:
                return {"data": {"promotions": [], "items": []}, "adverts": [], "all": 0}
            if "search_report" in name or "stocks_report" in name or "wb_warehouses" in name:
                return {"data": {"items": [], "groups": [], "total": []}}
            return {}
        return _fallback
