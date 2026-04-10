from __future__ import annotations

import json
from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from ...config import Settings
from ...contracts import utc_now_iso
from ...errors import ConfigError
from ...integrations.advantshop import build_advantshop_client
from ...integrations.google_sheets import build_google_sheets_client
from ...integrations.wildberries import build_wildberries_client
from ..marketplace.api import WildberriesApiError
from .models import (
    ActionRow,
    CalculatedEconomicsRow,
    ProductMasterRow,
    SiteRawRow,
    SyncStatus,
    WbRawRow,
)
from .schema import (
    ACTION_HEADERS,
    CALC_HEADERS,
    ERROR_HEADERS,
    MANUAL_COLUMN_COUNT,
    MASTER_HEADERS,
    PANEL_DEFAULT_ROWS,
    SHEET_TITLES,
    SITE_RAW_HEADERS,
    WB_RAW_HEADERS,
    WB_TARIFFS_HEADERS,
    build_master_formula_rows,
    build_panel_rows,
    build_setup_requests,
)


class SalesSheetConfigurationError(ConfigError):
    pass


def parse_master_rows(values: list[list[str]]) -> list[ProductMasterRow]:
    rows: list[ProductMasterRow] = []
    for index, raw in enumerate(values, start=2):
        raw = raw[:MANUAL_COLUMN_COUNT]
        if not any(_text(item) for item in raw):
            continue
        rows.append(
            ProductMasterRow(
                row_number=index,
                product_key=_text(_cell(raw, 0)),
                active=_bool(_cell(raw, 1), default=True),
                product_name=_text(_cell(raw, 2)),
                category=_text(_cell(raw, 3)),
                brand=_text(_cell(raw, 4)),
                wb_nm_id=_int(_cell(raw, 5)),
                wb_vendor_code=_text(_cell(raw, 6)),
                site_product_id=_int(_cell(raw, 7)),
                site_offer_id=_int(_cell(raw, 8)),
                pack_type=_text(_cell(raw, 9)),
                pack_weight_g=_float(_cell(raw, 10)),
                length_cm=_float(_cell(raw, 11)),
                width_cm=_float(_cell(raw, 12)),
                height_cm=_float(_cell(raw, 13)),
                purchase_cost_rub=_float(_cell(raw, 14)),
                packaging_cost_rub=_float(_cell(raw, 15)),
                other_unit_cost_rub=_float(_cell(raw, 16)),
                manual_site_price=_float(_cell(raw, 17)),
                manual_wb_price=_float(_cell(raw, 18)),
                manual_ad_pct_cap=_float(_cell(raw, 19)),
                tax_profile=_text(_cell(raw, 20)),
                notes=_text(_cell(raw, 21)),
            )
        )
    return rows


def validate_master_rows(rows: list[ProductMasterRow]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    detected_at = utc_now_iso()
    seen_product_keys: dict[str, int] = {}
    seen_wb: dict[int, str] = {}
    seen_site: dict[int, str] = {}
    for row in rows:
        if not row.product_key:
            errors.append(
                _error_row(
                    severity="high",
                    code="missing_product_key",
                    product_key="",
                    sheet="Товары",
                    message="У заполненной строки отсутствует product_key.",
                    details=f"Строка {row.row_number}: заполните уникальный ключ товара.",
                    detected_at=detected_at,
                )
            )
        elif row.product_key in seen_product_keys:
            errors.append(
                _error_row(
                    severity="high",
                    code="duplicate_product_key",
                    product_key=row.product_key,
                    sheet="Товары",
                    message="Дублирующийся product_key.",
                    details=f"Строки {seen_product_keys[row.product_key]} и {row.row_number}.",
                    detected_at=detected_at,
                )
            )
        else:
            seen_product_keys[row.product_key] = row.row_number
        if row.wb_nm_id:
            if row.wb_nm_id in seen_wb and seen_wb[row.wb_nm_id] != row.product_key:
                errors.append(
                    _error_row(
                        severity="medium",
                        code="duplicate_wb_nm_id",
                        product_key=row.product_key,
                        sheet="Товары",
                        message="Повторяется wb_nm_id у разных product_key.",
                        details=f"wb_nm_id={row.wb_nm_id} уже используется для {seen_wb[row.wb_nm_id]}.",
                        detected_at=detected_at,
                    )
                )
            seen_wb[row.wb_nm_id] = row.product_key
        if row.site_product_id:
            if row.site_product_id in seen_site and seen_site[row.site_product_id] != row.product_key:
                errors.append(
                    _error_row(
                        severity="medium",
                        code="duplicate_site_product_id",
                        product_key=row.product_key,
                        sheet="Товары",
                        message="Повторяется site_product_id у разных product_key.",
                        details=f"site_product_id={row.site_product_id} уже используется для {seen_site[row.site_product_id]}.",
                        detected_at=detected_at,
                    )
                )
            seen_site[row.site_product_id] = row.product_key
        if row.active and not row.wb_nm_id and not row.site_product_id and not row.site_offer_id:
            errors.append(
                _error_row(
                    severity="medium",
                    code="no_channel_mapping",
                    product_key=row.product_key,
                    sheet="Товары",
                    message="Активный товар не привязан ни к WB, ни к сайту.",
                    details=f"Строка {row.row_number}.",
                    detected_at=detected_at,
                )
            )
    return errors


def build_calculated_rows(
    master_rows: list[ProductMasterRow],
    *,
    wb_rows: dict[str, WbRawRow],
    wb_commissions: dict[str, float],
    wb_logistics_rub: float,
    wb_return_rub: float,
    wb_buyout_pct: float,
    site_rows: dict[str, SiteRawRow],
    settings_map: dict[str, str],
    updated_at: str | None = None,
) -> list[CalculatedEconomicsRow]:
    updated_at = updated_at or utc_now_iso()
    calculated: list[CalculatedEconomicsRow] = []
    site_commission_pct = _bounded_pct(settings_map.get("site_commission_pct"), default=0.14)
    default_ad_pct = _bounded_pct(settings_map.get("default_ad_pct_cap"), default=0.10)
    for row in master_rows:
        if not row.product_key:
            continue
        tax_pct = _resolve_tax_pct(row.tax_profile, settings_map)
        ad_pct = _bounded_pct(row.manual_ad_pct_cap, default=default_ad_pct)
        if row.site_product_id or row.site_offer_id or row.manual_site_price is not None:
            site_raw = site_rows.get(row.product_key)
            calculated.append(
                _calculate_channel_row(
                    row,
                    channel="site",
                    live_price=site_raw.current_price_rub if site_raw else None,
                    discounted_price=site_raw.discounted_price_rub if site_raw else None,
                    target_price=row.manual_site_price or (site_raw.current_price_rub if site_raw else None),
                    commission_pct=site_commission_pct,
                    logistics_rub=0.0,
                    return_rub=0.0,
                    tax_pct=tax_pct,
                    ad_pct=ad_pct,
                    sales_units=site_raw.orders_30d_units if site_raw else None,
                    revenue_rub=site_raw.revenue_30d_rub if site_raw else None,
                    stock_qty=site_raw.stock_qty if site_raw else None,
                    updated_at=updated_at,
                )
            )
        if row.wb_nm_id or row.manual_wb_price is not None:
            wb_raw = wb_rows.get(row.product_key)
            subject_name = (wb_raw.subject_name if wb_raw else "").strip().lower()
            commission_pct = wb_commissions.get(subject_name) or _bounded_pct(
                settings_map.get("wb_default_commission_pct"),
                default=0.15,
            )
            calculated.append(
                _calculate_channel_row(
                    row,
                    channel="wb",
                    live_price=wb_raw.current_price_rub if wb_raw else None,
                    discounted_price=(wb_raw.discounted_price_rub or wb_raw.current_price_rub) if wb_raw else None,
                    target_price=row.manual_wb_price
                    or (wb_raw.discounted_price_rub if wb_raw and wb_raw.discounted_price_rub else None)
                    or (wb_raw.current_price_rub if wb_raw else None),
                    commission_pct=commission_pct,
                    logistics_rub=wb_logistics_rub,
                    return_rub=wb_return_rub * max(0.0, 1.0 - wb_buyout_pct),
                    tax_pct=tax_pct,
                    ad_pct=ad_pct,
                    sales_units=wb_raw.sales_30d_units if wb_raw else None,
                    revenue_rub=wb_raw.revenue_30d_rub if wb_raw else None,
                    stock_qty=wb_raw.stocks_qty if wb_raw else None,
                    updated_at=updated_at,
                )
            )
    return calculated


def build_action_rows(
    master_rows: list[ProductMasterRow],
    calculated_rows: list[CalculatedEconomicsRow],
    error_rows: list[dict[str, str]],
) -> list[ActionRow]:
    updated_at = utc_now_iso()
    actions: list[ActionRow] = []
    by_key = {row.product_key: row for row in master_rows if row.product_key}
    for calc in calculated_rows:
        if calc.profit_rub < 0:
            actions.append(
                ActionRow(
                    priority=100,
                    severity="high",
                    product_key=calc.product_key,
                    product_name=calc.product_name,
                    channel=calc.channel,
                    action_type="negative_profit",
                    headline="Товар убыточен.",
                    details=f"Прибыль {calc.profit_rub:.2f} руб. Маржа {calc.margin_pct or 0:.2%}.",
                    suggested_action="Пересчитать цену, себестоимость, рекламу и тарифы.",
                    metric_value=calc.profit_rub,
                    metric_context="profit_rub",
                    updated_at=updated_at,
                )
            )
        if calc.data_status != "ok":
            actions.append(
                ActionRow(
                    priority=85,
                    severity="medium",
                    product_key=calc.product_key,
                    product_name=calc.product_name,
                    channel=calc.channel,
                    action_type="data_gap",
                    headline="Нет актуальных live-данных.",
                    details=calc.issue_flags or calc.data_status,
                    suggested_action="Проверить маппинг и свежесть API-выгрузки.",
                    metric_context="data_status",
                    updated_at=updated_at,
                )
            )
        if calc.price_gap_rub is not None and abs(calc.price_gap_rub) >= 1:
            actions.append(
                ActionRow(
                    priority=70,
                    severity="low",
                    product_key=calc.product_key,
                    product_name=calc.product_name,
                    channel=calc.channel,
                    action_type="price_gap",
                    headline="Плановая и live цена расходятся.",
                    details=f"Расхождение {calc.price_gap_rub:.2f} руб.",
                    suggested_action="Проверить, что в канале выставлена актуальная цена.",
                    metric_value=calc.price_gap_rub,
                    metric_context="price_gap_rub",
                    updated_at=updated_at,
                )
            )
    for error in error_rows:
        master = by_key.get(error["product_key"])
        actions.append(
            ActionRow(
                priority=90 if error["severity"] == "high" else 75,
                severity=error["severity"],
                product_key=error["product_key"],
                product_name=master.product_name if master else "",
                channel="system",
                action_type=error["code"],
                headline=error["message"],
                details=error["details"],
                suggested_action="Исправить строку или конфигурацию источника данных.",
                updated_at=updated_at,
            )
        )
    actions.sort(key=lambda item: (-item.priority, item.product_key, item.channel))
    return actions


class SalesSheetService:
    def __init__(
        self,
        settings: Settings,
        *,
        wb_client_factory=build_wildberries_client,
        site_client_factory=build_advantshop_client,
        sheets_client_factory=build_google_sheets_client,
    ) -> None:
        self.settings = settings
        self._wb_client_factory = wb_client_factory
        self._site_client_factory = site_client_factory
        self._sheets_client_factory = sheets_client_factory

    def init_workbook(self) -> dict[str, Any]:
        client = self._sheets_client()
        apps_script_path = self._write_apps_script_template()
        sheet_ids = client.ensure_sheets(SHEET_TITLES)
        client.batch_update(build_setup_requests(sheet_ids))
        client.batch_update_values(
            [
                {
                    "range": "Панель!A1:D21",
                    "majorDimension": "ROWS",
                    "values": build_panel_rows(
                        spreadsheet_id=client.spreadsheet_id,
                        workbook_url=client.spreadsheet_url,
                        cron=self.settings.sales_sheet_refresh_cron,
                        webhook_configured=bool(self.settings.sales_sheet_webhook_secret),
                        apps_script_artifact=str(apps_script_path),
                    ),
                },
                {"range": "Товары!A1:AF1", "majorDimension": "ROWS", "values": [list(MASTER_HEADERS)]},
                {"range": "WB_RAW!A1:Q1", "majorDimension": "ROWS", "values": [list(WB_RAW_HEADERS)]},
                {"range": "WB_TARIFFS_RAW!A1:L1", "majorDimension": "ROWS", "values": [list(WB_TARIFFS_HEADERS)]},
                {"range": "SITE_RAW!A1:O1", "majorDimension": "ROWS", "values": [list(SITE_RAW_HEADERS)]},
                {"range": "РАСЧЕТ!A1:X1", "majorDimension": "ROWS", "values": [list(CALC_HEADERS)]},
                {"range": "ДЕЙСТВИЯ!A1:L1", "majorDimension": "ROWS", "values": [list(ACTION_HEADERS)]},
                {"range": "ЛОГ_ОШИБОК!A1:G1", "majorDimension": "ROWS", "values": [list(ERROR_HEADERS)]},
                {"range": "Товары!W2:AF5000", "majorDimension": "ROWS", "values": build_master_formula_rows()},
            ],
            user_entered=True,
        )
        payload = {
            "status": "ok",
            "spreadsheet_id": client.spreadsheet_id,
            "spreadsheet_url": client.spreadsheet_url,
            "sheets": list(sheet_ids),
            "apps_script_template": str(apps_script_path),
        }
        self._persist_json("sales_sheet_init.json", payload)
        return payload

    def diagnose(self) -> dict[str, Any]:
        config = {
            "spreadsheet_id_configured": bool(self.settings.google_sheets_spreadsheet_id),
            "google_credentials_configured": bool(
                self.settings.google_service_account_file or self.settings.google_service_account_json
            ),
            "wb_configured": bool(self.settings.wb_api_token),
            "advantshop_url_configured": bool(self.settings.advantshop_api_url),
            "advantshop_key_configured": bool(self.settings.advantshop_api or self.settings.advantshop_api_auth),
            "refresh_cron": self.settings.sales_sheet_refresh_cron,
        }
        report: dict[str, Any] = {"status": "ok", "config": config}
        if not config["spreadsheet_id_configured"] or not config["google_credentials_configured"]:
            report["status"] = "warning"
            report["message"] = "Google Sheets config is incomplete."
            return report
        client = self._sheets_client()
        metadata = client.get_spreadsheet()
        master_rows = parse_master_rows(client.get_values("Товары!A2:V5000"))
        errors = validate_master_rows(master_rows)
        report.update(
            {
                "spreadsheet_id": client.spreadsheet_id,
                "spreadsheet_url": client.spreadsheet_url,
                "sheet_titles": [item.get("properties", {}).get("title") for item in metadata.get("sheets", [])],
                "master_row_count": len(master_rows),
                "error_count": len(errors),
            }
        )
        if errors:
            report["status"] = "warning"
            report["top_errors"] = errors[:10]
        self._persist_json("sales_sheet_diagnose.json", report)
        return report

    def refresh(self, *, scope: str = "all") -> dict[str, Any]:
        if scope not in {"all", "wb", "site"}:
            raise SalesSheetConfigurationError("scope must be one of: all, wb, site")
        client = self._sheets_client()
        master_rows = parse_master_rows(client.get_values("Товары!A2:V5000"))
        panel_settings = self._read_panel_settings(client)
        errors = validate_master_rows(master_rows)
        started_at = utc_now_iso()
        wb_rows: dict[str, WbRawRow] = {}
        wb_tariff_rows: list[list[Any]] = []
        wb_commissions: dict[str, float] = {}
        site_rows: dict[str, SiteRawRow] = {}
        if scope in {"all", "wb"}:
            wb_rows, wb_tariff_rows, wb_commissions, wb_errors = self._fetch_wb_snapshot(master_rows)
            errors.extend(wb_errors)
        if scope in {"all", "site"}:
            site_rows, site_errors = self._fetch_site_snapshot(master_rows)
            errors.extend(site_errors)
        calculated_rows = build_calculated_rows(
            master_rows,
            wb_rows=wb_rows,
            wb_commissions=wb_commissions,
            wb_logistics_rub=_float(panel_settings.get("wb_default_logistics_rub")) or 65.0,
            wb_return_rub=_float(panel_settings.get("wb_default_return_rub")) or 35.0,
            wb_buyout_pct=_bounded_pct(panel_settings.get("wb_default_buyout_pct"), default=0.90),
            site_rows=site_rows,
            settings_map=panel_settings,
        )
        action_rows = build_action_rows(master_rows, calculated_rows, errors)
        clear_ranges: list[str] = []
        values: list[dict[str, Any]] = []
        rows_written = 0
        if scope in {"all", "wb"}:
            clear_ranges.extend(["WB_RAW!A2:Q", "WB_TARIFFS_RAW!A2:L"])
            values.extend(
                [
                    {"range": f"WB_RAW!A2:Q{max(2, len(wb_rows) + 1)}", "majorDimension": "ROWS", "values": [_wb_row_to_values(item) for item in wb_rows.values()]},
                    {"range": f"WB_TARIFFS_RAW!A2:L{max(2, len(wb_tariff_rows) + 1)}", "majorDimension": "ROWS", "values": wb_tariff_rows},
                ]
            )
            rows_written += len(wb_rows) + len(wb_tariff_rows)
        if scope in {"all", "site"}:
            clear_ranges.append("SITE_RAW!A2:O")
            values.append(
                {"range": f"SITE_RAW!A2:O{max(2, len(site_rows) + 1)}", "majorDimension": "ROWS", "values": [_site_row_to_values(item) for item in site_rows.values()]}
            )
            rows_written += len(site_rows)
        if scope == "all":
            clear_ranges.extend(["РАСЧЕТ!A2:X", "ДЕЙСТВИЯ!A2:L", "ЛОГ_ОШИБОК!A2:G"])
            values.extend(
                [
                    {"range": f"РАСЧЕТ!A2:X{max(2, len(calculated_rows) + 1)}", "majorDimension": "ROWS", "values": [_calc_row_to_values(item) for item in calculated_rows]},
                    {"range": f"ДЕЙСТВИЯ!A2:L{max(2, len(action_rows) + 1)}", "majorDimension": "ROWS", "values": [_action_row_to_values(item) for item in action_rows]},
                    {"range": f"ЛОГ_ОШИБОК!A2:G{max(2, len(errors) + 1)}", "majorDimension": "ROWS", "values": [[item[key] for key in ("severity", "code", "product_key", "sheet", "message", "details", "detected_at")] for item in errors]},
                ]
            )
            rows_written += len(calculated_rows) + len(action_rows) + len(errors)
        if clear_ranges:
            client.batch_clear(clear_ranges)
        if values:
            client.batch_update_values(values, user_entered=False)
        finished_at = utc_now_iso()
        self._write_panel_status(
            client,
            scope=scope,
            status="warning" if errors else "ok",
            error_count=len(errors),
            timestamp=finished_at,
        )
        payload = asdict(
            SyncStatus(
                scope=scope,
                status="warning" if errors else "ok",
                started_at=started_at,
                finished_at=finished_at,
                spreadsheet_id=client.spreadsheet_id,
                rows_written=rows_written,
                message=f"Refreshed scope={scope}.",
                error_count=len(errors),
            )
        )
        payload["spreadsheet_url"] = client.spreadsheet_url
        payload["master_rows"] = len(master_rows)
        self._persist_json(f"sales_sheet_refresh_{scope}.json", payload | {"errors": errors})
        return payload

    def _fetch_wb_snapshot(
        self,
        master_rows: list[ProductMasterRow],
    ) -> tuple[dict[str, WbRawRow], list[list[Any]], dict[str, float], list[dict[str, str]]]:
        detected_at = utc_now_iso()
        try:
            client = self._wb_client_factory(self.settings)
        except Exception as exc:
            return {}, [], {}, [_system_error("wb_not_configured", str(exc), detected_at)]
        nm_to_key = {row.wb_nm_id: row.product_key for row in master_rows if row.wb_nm_id and row.product_key}
        if not nm_to_key:
            return {}, [], {}, []
        today = date.today()
        since = (today - timedelta(days=30)).isoformat()
        prices_by_nm: dict[int, dict[str, Any]] = {}
        sales_by_nm: dict[int, dict[str, float]] = {}
        orders_by_nm: dict[int, float] = {}
        stocks_by_nm: dict[int, float] = {}
        cards_by_nm: dict[int, dict[str, Any]] = {}
        commissions: dict[str, float] = {}
        tariff_rows: list[list[Any]] = []
        errors: list[dict[str, str]] = []
        try:
            for chunk in _chunked(sorted(nm_to_key), 1000):
                for item in _extract_wb_goods(client.get_prices_goods_filter_by_nm_ids(chunk)):
                    nm_id = _int(item.get("nmID") or item.get("nmId"))
                    if nm_id:
                        prices_by_nm[nm_id] = item
            for item in client.get_supplier_sales(since):
                nm_id = _int(item.get("nmId"))
                if nm_id not in nm_to_key:
                    continue
                bucket = sales_by_nm.setdefault(nm_id, {"units": 0.0, "revenue": 0.0})
                bucket["units"] += _float(item.get("saleQty") or item.get("quantity") or 1) or 0.0
                bucket["revenue"] += _float(item.get("finishedPrice") or item.get("forPay") or item.get("priceWithDisc")) or 0.0
            for item in client.get_supplier_orders(since):
                nm_id = _int(item.get("nmId"))
                if nm_id not in nm_to_key:
                    continue
                orders_by_nm[nm_id] = orders_by_nm.get(nm_id, 0.0) + (_float(item.get("quantity") or 1) or 0.0)
            for item in client.get_supplier_stocks(since):
                nm_id = _int(item.get("nmId"))
                if nm_id not in nm_to_key:
                    continue
                stocks_by_nm[nm_id] = stocks_by_nm.get(nm_id, 0.0) + (_float(item.get("quantity") or 0) or 0.0)
            cards_by_nm = self._fetch_wb_cards(client, list(nm_to_key))
            commission_response = client.get_tariffs_commission(locale="ru")
            commissions = _extract_wb_commissions(commission_response)
            tariff_rows = _extract_wb_tariff_rows(
                commission_response=commission_response,
                box_response=client.get_tariffs_box(date=today.isoformat()),
                pallet_response=client.get_tariffs_pallet(date=today.isoformat()),
                return_response=client.get_tariffs_return(date=today.isoformat()),
                fetched_at=detected_at,
            )
        except WildberriesApiError as exc:
            errors.append(_system_error("wb_api_error", str(exc), detected_at))
        rows: dict[str, WbRawRow] = {}
        for nm_id, product_key in nm_to_key.items():
            price = prices_by_nm.get(nm_id, {})
            card = cards_by_nm.get(nm_id, {})
            sales = sales_by_nm.get(nm_id, {})
            rows[product_key] = WbRawRow(
                product_key=product_key,
                fetched_at=detected_at,
                nm_id=nm_id,
                vendor_code=_text(price.get("vendorCode") or card.get("vendorCode")),
                title=_text(price.get("name") or card.get("title") or card.get("name")),
                brand=_text(price.get("brand") or card.get("brand")),
                subject_name=_text(price.get("subjectName") or card.get("subjectName")),
                current_price_rub=_float(price.get("price")),
                discounted_price_rub=_float(price.get("discountedPrice")),
                club_discounted_price_rub=_float(price.get("clubDiscountedPrice")),
                discount_pct=_float(price.get("discount")),
                stocks_qty=stocks_by_nm.get(nm_id),
                sales_30d_units=sales.get("units"),
                orders_30d_units=orders_by_nm.get(nm_id),
                revenue_30d_rub=sales.get("revenue"),
                promos_count=_int(price.get("promoID") or price.get("promotionsCount")),
            )
        return rows, tariff_rows, commissions, errors

    def _fetch_wb_cards(self, client, nm_ids: list[int]) -> dict[int, dict[str, Any]]:
        remaining = set(nm_ids)
        cards_by_nm: dict[int, dict[str, Any]] = {}
        cursor_nm_id: int | None = None
        cursor_updated_at: str | None = None
        while remaining:
            response = client.get_content_cards(
                limit=100,
                cursor_nm_id=cursor_nm_id,
                cursor_updated_at=cursor_updated_at,
            )
            cards = response.get("cards") or response.get("data") or response.get("cardsList") or []
            if not cards:
                break
            for card in cards:
                nm_id = _int(card.get("nmID") or card.get("nmId"))
                if nm_id and nm_id in remaining:
                    cards_by_nm[nm_id] = card
                    remaining.discard(nm_id)
            cursor = response.get("cursor") or {}
            cursor_nm_id = _int(cursor.get("nmID") or cursor.get("nmId"))
            cursor_updated_at = _text(cursor.get("updatedAt"))
            if cursor_nm_id is None and not cursor_updated_at:
                break
        return cards_by_nm

    def _fetch_site_snapshot(
        self,
        master_rows: list[ProductMasterRow],
    ) -> tuple[dict[str, SiteRawRow], list[dict[str, str]]]:
        detected_at = utc_now_iso()
        try:
            client = self._site_client_factory(self.settings)
        except Exception as exc:
            return {}, [_system_error("site_not_configured", str(exc), detected_at)]
        mapping_by_product_id = {
            row.site_product_id: row.product_key
            for row in master_rows
            if row.site_product_id and row.product_key
        }
        mapping_by_offer_id = {
            row.site_offer_id: row.product_key
            for row in master_rows
            if row.site_offer_id and row.product_key
        }
        if not mapping_by_product_id and not mapping_by_offer_id:
            return {}, []
        try:
            catalog = client.get_catalog_all()
            date_from = (
                datetime.now(timezone.utc) - timedelta(days=30)
            ).replace(microsecond=0).isoformat()
            orders_payload = client.get_orders_list(
                page=1,
                items_per_page=50,
                load_items=True,
                date_from=date_from,
            )
        except Exception as exc:
            return {}, [_system_error("site_api_error", str(exc), detected_at)]
        catalog_items = _extract_site_catalog_items(catalog)
        orders_by_artno = _extract_site_order_stats(orders_payload)
        rows: dict[str, SiteRawRow] = {}
        for item in catalog_items:
            product_id = _int(item.get("product_id"))
            offer_id = _int(item.get("offer_id"))
            product_key = mapping_by_offer_id.get(offer_id) or mapping_by_product_id.get(product_id)
            if not product_key:
                continue
            art_no = _text(item.get("art_no"))
            stats = orders_by_artno.get(art_no.lower(), {"units": None, "revenue": None})
            rows[product_key] = SiteRawRow(
                product_key=product_key,
                fetched_at=detected_at,
                product_id=product_id,
                offer_id=offer_id,
                art_no=art_no,
                title=_text(item.get("title")),
                category_name=_text(item.get("category_name")),
                enabled=_bool(item.get("enabled"), default=True),
                current_price_rub=_float(item.get("current_price_rub")),
                old_price_rub=_float(item.get("old_price_rub")),
                discounted_price_rub=_float(item.get("discounted_price_rub")),
                stock_qty=_float(item.get("stock_qty")),
                orders_30d_units=stats.get("units"),
                revenue_30d_rub=stats.get("revenue"),
            )
        return rows, []

    def _read_panel_settings(self, client) -> dict[str, str]:
        values = client.get_values("Панель!A2:D30")
        mapping = {row[1]: row[2] for row in values if len(row) >= 3 and row[1]}
        for _, key, value, _ in PANEL_DEFAULT_ROWS:
            mapping.setdefault(key, value)
        return mapping

    def _write_panel_status(
        self,
        client,
        *,
        scope: str,
        status: str,
        error_count: int,
        timestamp: str,
    ) -> None:
        updates = [
            {
                "range": "Панель!C7",
                "majorDimension": "ROWS",
                "values": [[self.settings.sales_sheet_refresh_cron]],
            },
            {"range": "Панель!C8", "majorDimension": "ROWS", "values": [[status]]},
            {"range": "Панель!C9", "majorDimension": "ROWS", "values": [[str(error_count)]]},
        ]
        if scope in {"all", "wb"}:
            updates.append({"range": "Панель!C5", "majorDimension": "ROWS", "values": [[timestamp]]})
        if scope in {"all", "site"}:
            updates.append({"range": "Панель!C6", "majorDimension": "ROWS", "values": [[timestamp]]})
        if scope == "all":
            updates.append({"range": "Панель!C4", "majorDimension": "ROWS", "values": [[timestamp]]})
        client.batch_update_values(updates, user_entered=False)

    def _write_apps_script_template(self) -> Path:
        path = self.settings.sales_artifact_root / "google_apps_script_refresh.gs"
        secret = self.settings.sales_sheet_webhook_secret or "SET_ME"
        path.write_text(
            "\n".join(
                [
                    "function onOpen() {",
                    "  SpreadsheetApp.getUi().createMenu('Sales Sync').addItem('Refresh Sales Data', 'triggerSalesRefresh').addToUi();",
                    "}",
                    "",
                    "function triggerSalesRefresh() {",
                    "  var response = UrlFetchApp.fetch('https://YOUR-WEBHOOK-ENDPOINT/sales-sheet-refresh', {",
                    "    method: 'post',",
                    "    contentType: 'application/json',",
                    "    payload: JSON.stringify({ scope: 'all', secret: '" + secret + "' })",
                    "  });",
                    "  SpreadsheetApp.getActive().toast(response.getContentText(), 'Sales Sync', 5);",
                    "}",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        return path

    def _persist_json(self, file_name: str, payload: dict[str, Any]) -> None:
        self.settings.sales_artifact_root.mkdir(parents=True, exist_ok=True)
        (self.settings.sales_artifact_root / file_name).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _sheets_client(self):
        try:
            return self._sheets_client_factory(self.settings)
        except Exception as exc:
            raise SalesSheetConfigurationError(str(exc)) from exc


def _calculate_channel_row(
    row: ProductMasterRow,
    *,
    channel: str,
    live_price: float | None,
    discounted_price: float | None,
    target_price: float | None,
    commission_pct: float,
    logistics_rub: float,
    return_rub: float,
    tax_pct: float,
    ad_pct: float,
    sales_units: float | None,
    revenue_rub: float | None,
    stock_qty: float | None,
    updated_at: str,
) -> CalculatedEconomicsRow:
    comparable_price = discounted_price or live_price or target_price or 0.0
    target = target_price or live_price or discounted_price
    commission_rub = comparable_price * commission_pct if comparable_price else 0.0
    ads_rub = comparable_price * ad_pct if comparable_price else 0.0
    taxes_rub = comparable_price * tax_pct if comparable_price else 0.0
    net_payout_rub = comparable_price - commission_rub - logistics_rub - return_rub - ads_rub - taxes_rub
    profit_rub = net_payout_rub - row.unit_cost_rub
    margin_pct = (profit_rub / target) if target else None
    roi_pct = (profit_rub / row.unit_cost_rub) if row.unit_cost_rub else None
    price_gap = (target - live_price) if target is not None and live_price is not None else None
    issue_flags: list[str] = []
    data_status = "ok"
    if live_price is None:
        issue_flags.append("missing_live_price")
        data_status = "warning"
    if profit_rub < 0:
        issue_flags.append("negative_profit")
    if not row.active:
        issue_flags.append("inactive")
    return CalculatedEconomicsRow(
        product_key=row.product_key,
        product_name=row.product_name,
        channel=channel,
        active=row.active,
        base_cost_rub=row.unit_cost_rub,
        target_price_rub=target,
        live_price_rub=live_price,
        discounted_price_rub=discounted_price,
        commission_rub=round(commission_rub, 2),
        logistics_rub=round(logistics_rub, 2),
        returns_rub=round(return_rub, 2),
        ads_rub=round(ads_rub, 2),
        taxes_rub=round(taxes_rub, 2),
        net_payout_rub=round(net_payout_rub, 2),
        profit_rub=round(profit_rub, 2),
        margin_pct=round(margin_pct, 4) if margin_pct is not None else None,
        roi_pct=round(roi_pct, 4) if roi_pct is not None else None,
        price_gap_rub=round(price_gap, 2) if price_gap is not None else None,
        sales_30d_units=sales_units,
        revenue_30d_rub=revenue_rub,
        stocks_qty=stock_qty,
        issue_flags=";".join(issue_flags),
        data_status=data_status,
        updated_at=updated_at,
    )


def _extract_wb_goods(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        if isinstance(payload.get("data"), dict) and isinstance(payload["data"].get("listGoods"), list):
            return payload["data"]["listGoods"]
        if isinstance(payload.get("data"), list):
            return payload["data"]
        if isinstance(payload.get("listGoods"), list):
            return payload["listGoods"]
    return []


def _extract_wb_commissions(payload: Any) -> dict[str, float]:
    report = payload.get("report") if isinstance(payload, dict) else None
    if not isinstance(report, list):
        return {}
    result: dict[str, float] = {}
    for item in report:
        subject = _text(item.get("subjectName")).lower()
        if subject:
            result[subject] = _bounded_pct(
                item.get("kgvpSupplier") or item.get("kgvpMarketplace"),
                default=0.15,
            )
    return result


def _extract_wb_tariff_rows(
    *,
    commission_response: Any,
    box_response: Any,
    pallet_response: Any,
    return_response: Any,
    fetched_at: str,
) -> list[list[Any]]:
    rows: list[list[Any]] = []
    for item in commission_response.get("report", []) if isinstance(commission_response, dict) else []:
        rows.append(
            [
                fetched_at,
                "commission",
                _text(item.get("subjectName")),
                _int(item.get("subjectID")),
                "",
                _float(item.get("kgvpSupplier")),
                None,
                None,
                None,
                None,
                None,
                json.dumps(item, ensure_ascii=False),
            ]
        )
    for items, tariff_type in [
        (_warehouse_list(box_response), "box"),
        (_warehouse_list(pallet_response), "pallet"),
        (_warehouse_list(return_response), "return"),
    ]:
        for warehouse in items:
            rows.append(
                [
                    fetched_at,
                    tariff_type,
                    "",
                    None,
                    _text(warehouse.get("warehouseName")),
                    None,
                    _float(
                        warehouse.get("boxDeliveryBase")
                        or warehouse.get("palletDeliveryValueBase")
                    ),
                    _float(
                        warehouse.get("boxDeliveryLiter")
                        or warehouse.get("palletDeliveryValueLiter")
                    ),
                    _float(warehouse.get("deliveryDumpSupOfficeBase")),
                    _float(warehouse.get("deliveryDumpSupOfficeLiter")),
                    _float(
                        warehouse.get("boxStorageBase")
                        or warehouse.get("palletStorageValueExpr")
                    ),
                    json.dumps(warehouse, ensure_ascii=False),
                ]
            )
    return rows


def _warehouse_list(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    return payload.get("response", {}).get("data", {}).get("warehouseList", [])


def _extract_site_catalog_items(payload: Any) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []

    def walk(node: Any, category_name: str = "") -> None:
        if isinstance(node, list):
            for child in node:
                walk(child, category_name)
            return
        if not isinstance(node, dict):
            return
        next_category = category_name
        if "products" in node or "children" in node or "categories" in node:
            next_category = _text(node.get("name") or node.get("categoryName") or category_name)
        product_id = _int(node.get("productId") or node.get("productID") or node.get("id"))
        offer_id = _int(node.get("offerId") or node.get("offerID"))
        name = _text(node.get("name") or node.get("title"))
        if (product_id or offer_id) and name:
            items.append(
                {
                    "product_id": product_id,
                    "offer_id": offer_id,
                    "art_no": _text(node.get("artNo") or node.get("offerArtNo") or node.get("artno")),
                    "title": name,
                    "category_name": _text(node.get("categoryName") or next_category),
                    "enabled": node.get("enabled", node.get("Enabled", True)),
                    "current_price_rub": _float(
                        node.get("price")
                        or node.get("Price")
                        or node.get("priceWithDiscount")
                        or node.get("discountPrice")
                    ),
                    "old_price_rub": _float(node.get("oldPrice") or node.get("OldPrice")),
                    "discounted_price_rub": _float(
                        node.get("priceWithDiscount") or node.get("discountPrice") or node.get("price")
                    ),
                    "stock_qty": _float(node.get("amount") or node.get("Amount") or node.get("stock")),
                }
            )
        for child_key in ("products", "children", "categories", "items", "dataItems", "obj"):
            if child_key in node:
                walk(node[child_key], next_category)

    walk(payload)
    deduped: dict[tuple[int | None, int | None], dict[str, Any]] = {}
    for item in items:
        deduped[(item.get("product_id"), item.get("offer_id"))] = item
    return list(deduped.values())


def _extract_site_order_stats(payload: Any) -> dict[str, dict[str, float]]:
    data_items = payload.get("obj", {}).get("DataItems", []) if isinstance(payload, dict) else []
    stats: dict[str, dict[str, float]] = {}
    for order in data_items:
        for item in order.get("Items", []) or []:
            art_no = _text(item.get("ArtNo")).lower()
            if not art_no:
                continue
            bucket = stats.setdefault(art_no, {"units": 0.0, "revenue": 0.0})
            amount = _float(item.get("Amount")) or 0.0
            price = _float(item.get("Price")) or 0.0
            bucket["units"] += amount
            bucket["revenue"] += amount * price
    return stats


def _wb_row_to_values(row: WbRawRow) -> list[Any]:
    return [
        row.fetched_at,
        row.product_key,
        row.nm_id,
        row.vendor_code,
        row.title,
        row.brand,
        row.subject_name,
        row.current_price_rub,
        row.discounted_price_rub,
        row.club_discounted_price_rub,
        row.discount_pct,
        row.stocks_qty,
        row.sales_30d_units,
        row.orders_30d_units,
        row.revenue_30d_rub,
        row.promos_count,
        row.error,
    ]


def _site_row_to_values(row: SiteRawRow) -> list[Any]:
    return [
        row.fetched_at,
        row.product_key,
        row.product_id,
        row.offer_id,
        row.art_no,
        row.title,
        row.category_name,
        row.enabled,
        row.current_price_rub,
        row.old_price_rub,
        row.discounted_price_rub,
        row.stock_qty,
        row.orders_30d_units,
        row.revenue_30d_rub,
        row.error,
    ]


def _calc_row_to_values(row: CalculatedEconomicsRow) -> list[Any]:
    return [
        row.product_key,
        row.product_name,
        row.channel,
        row.active,
        row.base_cost_rub,
        row.target_price_rub,
        row.live_price_rub,
        row.discounted_price_rub,
        row.commission_rub,
        row.logistics_rub,
        row.returns_rub,
        row.ads_rub,
        row.taxes_rub,
        row.net_payout_rub,
        row.profit_rub,
        row.margin_pct,
        row.roi_pct,
        row.price_gap_rub,
        row.sales_30d_units,
        row.revenue_30d_rub,
        row.stocks_qty,
        row.issue_flags,
        row.data_status,
        row.updated_at,
    ]


def _action_row_to_values(row: ActionRow) -> list[Any]:
    return [
        row.priority,
        row.severity,
        row.product_key,
        row.product_name,
        row.channel,
        row.action_type,
        row.headline,
        row.details,
        row.suggested_action,
        row.metric_value,
        row.metric_context,
        row.updated_at,
    ]


def _error_row(
    *,
    severity: str,
    code: str,
    product_key: str,
    sheet: str,
    message: str,
    details: str,
    detected_at: str,
) -> dict[str, str]:
    return {
        "severity": severity,
        "code": code,
        "product_key": product_key,
        "sheet": sheet,
        "message": message,
        "details": details,
        "detected_at": detected_at,
    }


def _system_error(code: str, details: str, detected_at: str) -> dict[str, str]:
    return _error_row(
        severity="high",
        code=code,
        product_key="",
        sheet="SYSTEM",
        message=code.replace("_", " "),
        details=details,
        detected_at=detected_at,
    )


def _cell(row: list[Any], index: int) -> Any:
    return row[index] if len(row) > index else ""


def _chunked(items: Iterable[int], size: int) -> list[list[int]]:
    chunk: list[int] = []
    chunks: list[list[int]] = []
    for item in items:
        chunk.append(item)
        if len(chunk) >= size:
            chunks.append(chunk)
            chunk = []
    if chunk:
        chunks.append(chunk)
    return chunks


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _bool(value: Any, *, default: bool = False) -> bool:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "да", "активен"}


def _int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(float(str(value).replace(" ", "").replace(",", ".")))
    except (TypeError, ValueError):
        return None


def _float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        cleaned = str(value).replace("\u00a0", "").replace(" ", "").replace("%", "").replace(",", ".")
        return float(cleaned)
    except ValueError:
        return None


def _bounded_pct(value: Any, *, default: float) -> float:
    parsed = _float(value)
    if parsed is None:
        return default
    if parsed > 1:
        parsed /= 100
    return max(0.0, min(parsed, 1.0))


def _resolve_tax_pct(profile: str, settings_map: dict[str, str]) -> float:
    if not (profile or "").strip():
        return _bounded_pct(settings_map.get("default_tax_pct"), default=0.06)
    normalized = profile.strip().lower().replace(" ", "")
    named = settings_map.get(f"tax_profile_{normalized}")
    if named is not None:
        return _bounded_pct(named, default=0.06)
    return _bounded_pct(
        profile,
        default=_bounded_pct(settings_map.get("default_tax_pct"), default=0.06),
    )
