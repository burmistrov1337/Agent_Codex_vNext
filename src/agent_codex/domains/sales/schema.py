from __future__ import annotations

from dataclasses import dataclass


PANEL_SHEET = "Панель"
MASTER_SHEET = "Товары"
CALC_SHEET = "РАСЧЕТ"
ACTIONS_SHEET = "ДЕЙСТВИЯ"
ERRORS_SHEET = "ЛОГ_ОШИБОК"

SHEET_TITLES = (
    PANEL_SHEET,
    MASTER_SHEET,
    "WB_RAW",
    "WB_TARIFFS_RAW",
    "SITE_RAW",
    CALC_SHEET,
    ACTIONS_SHEET,
    ERRORS_SHEET,
)

PANEL_HEADERS = ("section", "key", "value", "notes")
PANEL_DEFAULT_ROWS = (
    ("system", "spreadsheet_id", "", "Workbook id. Filled by init command."),
    ("system", "workbook_url", "", "Direct link to the Google Sheet."),
    ("sync", "last_full_refresh_at", "", "Updated by sales-sheet-refresh --scope all."),
    ("sync", "last_wb_refresh_at", "", "Updated by sales-sheet-refresh --scope wb/all."),
    ("sync", "last_site_refresh_at", "", "Updated by sales-sheet-refresh --scope site/all."),
    ("sync", "refresh_cron", "0 8 * * *", "Planned cadence in Asia/Novosibirsk."),
    ("sync", "last_status", "not_started", "ok | warning | error | not_started."),
    ("sync", "last_error_count", "0", "How many log rows were produced on the last refresh."),
    ("economics", "site_commission_pct", "0.14", "Site operating/commercial percent."),
    ("economics", "default_ad_pct_cap", "0.10", "Used when manual_ad_pct_cap is empty."),
    ("economics", "wb_default_commission_pct", "0.15", "Fallback if subject tariff is missing."),
    ("economics", "wb_default_logistics_rub", "65", "Fallback WB logistics cost per unit."),
    ("economics", "wb_default_return_rub", "35", "Fallback WB return cost per unit."),
    ("economics", "wb_default_buyout_pct", "0.90", "Used to scale WB return burden."),
    ("economics", "default_tax_pct", "0.06", "Default unit tax share."),
    ("economics", "tax_profile_usn6", "0.06", "Optional named tax profile."),
    ("economics", "tax_profile_usn15", "0.15", "Optional named tax profile."),
    ("economics", "stale_after_hours", "48", "Data older than this becomes stale."),
    ("webhook", "webhook_secret_configured", "", "yes/no, informative only."),
    ("webhook", "apps_script_template_artifact", "", "Local artifact with Apps Script stub."),
)

MANUAL_HEADERS = (
    "product_key",
    "active",
    "product_name",
    "category",
    "brand",
    "wb_nm_id",
    "wb_vendor_code",
    "site_product_id",
    "site_offer_id",
    "pack_type",
    "pack_weight_g",
    "length_cm",
    "width_cm",
    "height_cm",
    "purchase_cost_rub",
    "packaging_cost_rub",
    "other_unit_cost_rub",
    "manual_site_price",
    "manual_wb_price",
    "manual_ad_pct_cap",
    "tax_profile",
    "notes",
)

COMPUTED_HEADERS = (
    "site_live_price_rub",
    "wb_live_price_rub",
    "site_profit_rub",
    "wb_profit_rub",
    "site_margin_pct",
    "wb_margin_pct",
    "site_status",
    "wb_status",
    "primary_action",
    "mapping_status",
)

MASTER_HEADERS = MANUAL_HEADERS + COMPUTED_HEADERS

WB_RAW_HEADERS = (
    "fetched_at",
    "product_key",
    "nm_id",
    "vendor_code",
    "title",
    "brand",
    "subject_name",
    "current_price_rub",
    "discounted_price_rub",
    "club_discounted_price_rub",
    "discount_pct",
    "stocks_qty",
    "sales_30d_units",
    "orders_30d_units",
    "revenue_30d_rub",
    "promos_count",
    "error",
)

WB_TARIFFS_HEADERS = (
    "fetched_at",
    "tariff_type",
    "subject_name",
    "subject_id",
    "warehouse_name",
    "commission_pct",
    "delivery_base_rub",
    "delivery_liter_rub",
    "return_base_rub",
    "return_liter_rub",
    "storage_base_rub",
    "raw_json",
)

SITE_RAW_HEADERS = (
    "fetched_at",
    "product_key",
    "product_id",
    "offer_id",
    "art_no",
    "title",
    "category_name",
    "enabled",
    "current_price_rub",
    "old_price_rub",
    "discounted_price_rub",
    "stock_qty",
    "orders_30d_units",
    "revenue_30d_rub",
    "error",
)

CALC_HEADERS = (
    "product_key",
    "product_name",
    "channel",
    "active",
    "base_cost_rub",
    "target_price_rub",
    "live_price_rub",
    "discounted_price_rub",
    "commission_rub",
    "logistics_rub",
    "returns_rub",
    "ads_rub",
    "taxes_rub",
    "net_payout_rub",
    "profit_rub",
    "margin_pct",
    "roi_pct",
    "price_gap_rub",
    "sales_30d_units",
    "revenue_30d_rub",
    "stocks_qty",
    "issue_flags",
    "data_status",
    "updated_at",
)

ACTION_HEADERS = (
    "priority",
    "severity",
    "product_key",
    "product_name",
    "channel",
    "action_type",
    "headline",
    "details",
    "suggested_action",
    "metric_value",
    "metric_context",
    "updated_at",
)

ERROR_HEADERS = (
    "severity",
    "code",
    "product_key",
    "sheet",
    "message",
    "details",
    "detected_at",
)

MANUAL_COLUMN_COUNT = len(MANUAL_HEADERS)
MASTER_COLUMN_COUNT = len(MASTER_HEADERS)
COMPUTED_START_COLUMN_INDEX = MANUAL_COLUMN_COUNT


@dataclass(frozen=True, slots=True)
class SheetLayout:
    title: str
    headers: tuple[str, ...]
    row_count: int
    column_count: int


SHEET_LAYOUTS = {
    PANEL_SHEET: SheetLayout(PANEL_SHEET, PANEL_HEADERS, 100, len(PANEL_HEADERS)),
    MASTER_SHEET: SheetLayout(MASTER_SHEET, MASTER_HEADERS, 5000, len(MASTER_HEADERS)),
    "WB_RAW": SheetLayout("WB_RAW", WB_RAW_HEADERS, 5000, len(WB_RAW_HEADERS)),
    "WB_TARIFFS_RAW": SheetLayout("WB_TARIFFS_RAW", WB_TARIFFS_HEADERS, 2000, len(WB_TARIFFS_HEADERS)),
    "SITE_RAW": SheetLayout("SITE_RAW", SITE_RAW_HEADERS, 5000, len(SITE_RAW_HEADERS)),
    CALC_SHEET: SheetLayout(CALC_SHEET, CALC_HEADERS, 10000, len(CALC_HEADERS)),
    ACTIONS_SHEET: SheetLayout(ACTIONS_SHEET, ACTION_HEADERS, 5000, len(ACTION_HEADERS)),
    ERRORS_SHEET: SheetLayout(ERRORS_SHEET, ERROR_HEADERS, 5000, len(ERROR_HEADERS)),
}


def build_panel_rows(
    *,
    spreadsheet_id: str,
    workbook_url: str,
    cron: str,
    webhook_configured: bool,
    apps_script_artifact: str,
) -> list[list[str]]:
    rows = [list(PANEL_HEADERS)]
    for section, key, value, notes in PANEL_DEFAULT_ROWS:
        final_value = value
        if key == "spreadsheet_id":
            final_value = spreadsheet_id
        elif key == "workbook_url":
            final_value = workbook_url
        elif key == "refresh_cron":
            final_value = cron
        elif key == "webhook_secret_configured":
            final_value = "yes" if webhook_configured else "no"
        elif key == "apps_script_template_artifact":
            final_value = apps_script_artifact
        rows.append([section, key, final_value, notes])
    return rows


def build_master_formula_rows(max_rows: int = 5000) -> list[list[str]]:
    rows: list[list[str]] = []
    for row_number in range(2, max_rows + 1):
        rows.append(
            [
                _sumifs_or_blank("G", row_number, "site"),
                _sumifs_or_blank("G", row_number, "wb"),
                _sumifs_or_blank("O", row_number, "site"),
                _sumifs_or_blank("O", row_number, "wb"),
                _sumifs_or_blank("P", row_number, "site"),
                _sumifs_or_blank("P", row_number, "wb"),
                _first_calc_value("W", row_number, "site"),
                _first_calc_value("W", row_number, "wb"),
                (
                    f'=IF($A{row_number}="";"";'
                    f'IFERROR(INDEX(FILTER({ACTIONS_SHEET}!$G:$G;{ACTIONS_SHEET}!$C:$C=$A{row_number});1);""))'
                ),
                (
                    f'=IF($A{row_number}="";"";TEXTJOIN(", ";TRUE;'
                    f'IF($F{row_number}<>"";"wb ok";"wb missing");'
                    f'IF(OR($H{row_number}<>"";$I{row_number}<>"");"site ok";"site missing")))'
                ),
            ]
        )
    return rows


def build_setup_requests(sheet_ids: dict[str, int]) -> list[dict]:
    requests: list[dict] = []
    for title, layout in SHEET_LAYOUTS.items():
        sheet_id = sheet_ids[title]
        requests.extend(
            [
                {
                    "updateSheetProperties": {
                        "properties": {
                            "sheetId": sheet_id,
                            "gridProperties": {
                                "rowCount": layout.row_count,
                                "columnCount": layout.column_count,
                                "frozenRowCount": 1,
                            },
                        },
                        "fields": "gridProperties(rowCount,columnCount,frozenRowCount)",
                    }
                },
                {
                    "repeatCell": {
                        "range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": 1},
                        "cell": {
                            "userEnteredFormat": {
                                "backgroundColor": {"red": 0.11, "green": 0.16, "blue": 0.27},
                                "textFormat": {
                                    "bold": True,
                                    "foregroundColor": {"red": 1, "green": 1, "blue": 1},
                                },
                            }
                        },
                        "fields": "userEnteredFormat(backgroundColor,textFormat)",
                    }
                },
            ]
        )
        if title != PANEL_SHEET:
            requests.append(
                {
                    "setBasicFilter": {
                        "filter": {
                            "range": {
                                "sheetId": sheet_id,
                                "startRowIndex": 0,
                                "startColumnIndex": 0,
                                "endColumnIndex": layout.column_count,
                            }
                        }
                    }
                }
            )
    master_sheet_id = sheet_ids[MASTER_SHEET]
    requests.extend(
        [
            {
                "addProtectedRange": {
                    "protectedRange": {
                        "range": {
                            "sheetId": master_sheet_id,
                            "startRowIndex": 1,
                            "startColumnIndex": COMPUTED_START_COLUMN_INDEX,
                            "endColumnIndex": MASTER_COLUMN_COUNT,
                        },
                        "description": f"Computed columns on {MASTER_SHEET}",
                        "warningOnly": True,
                    }
                }
            },
            {
                "repeatCell": {
                    "range": {
                        "sheetId": master_sheet_id,
                        "startColumnIndex": COMPUTED_START_COLUMN_INDEX,
                        "endColumnIndex": MASTER_COLUMN_COUNT,
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "backgroundColor": {"red": 0.95, "green": 0.96, "blue": 0.98}
                        }
                    },
                    "fields": "userEnteredFormat(backgroundColor)",
                }
            },
            {
                "addConditionalFormatRule": {
                    "index": 0,
                    "rule": {
                        "ranges": [{"sheetId": master_sheet_id, "startRowIndex": 1, "endColumnIndex": MASTER_COLUMN_COUNT}],
                        "booleanRule": {
                            "condition": {
                                "type": "CUSTOM_FORMULA",
                                "values": [{"userEnteredValue": '=AND($A2<>"";COUNTIF($A:$A;$A2)>1)'}],
                            },
                            "format": {"backgroundColor": {"red": 0.98, "green": 0.82, "blue": 0.82}},
                        },
                    },
                }
            },
            {
                "addConditionalFormatRule": {
                    "index": 1,
                    "rule": {
                        "ranges": [{"sheetId": master_sheet_id, "startRowIndex": 1, "endColumnIndex": MANUAL_COLUMN_COUNT}],
                        "booleanRule": {
                            "condition": {
                                "type": "CUSTOM_FORMULA",
                                "values": [{"userEnteredValue": '=AND($A2="";COUNTA($B2:$V2)>0)'}],
                            },
                            "format": {"backgroundColor": {"red": 0.99, "green": 0.93, "blue": 0.75}},
                        },
                    },
                }
            },
            {
                "addConditionalFormatRule": {
                    "index": 2,
                    "rule": {
                        "ranges": [{"sheetId": master_sheet_id, "startRowIndex": 1, "endColumnIndex": MASTER_COLUMN_COUNT}],
                        "booleanRule": {
                            "condition": {
                                "type": "CUSTOM_FORMULA",
                                "values": [{"userEnteredValue": '=AND($B2=TRUE;$F2="";$H2="";$I2="")'}],
                            },
                            "format": {"backgroundColor": {"red": 0.96, "green": 0.89, "blue": 0.75}},
                        },
                    },
                }
            },
        ]
    )
    return requests


def _sumifs_or_blank(calc_column: str, row_number: int, channel: str) -> str:
    return (
        f'=IF($A{row_number}="";"";'
        f'IF(COUNTIFS({CALC_SHEET}!$A:$A;$A{row_number};{CALC_SHEET}!$C:$C;"{channel}")=0;"";'
        f'SUMIFS({CALC_SHEET}!${calc_column}:${calc_column};{CALC_SHEET}!$A:$A;$A{row_number};{CALC_SHEET}!$C:$C;"{channel}")))'
    )


def _first_calc_value(calc_column: str, row_number: int, channel: str) -> str:
    return (
        f'=IF($A{row_number}="";"";'
        f'IFERROR(INDEX(FILTER({CALC_SHEET}!${calc_column}:${calc_column};{CALC_SHEET}!$A:$A=$A{row_number};{CALC_SHEET}!$C:$C="{channel}");1);""))'
    )

