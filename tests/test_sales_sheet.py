from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stdout
from tempfile import TemporaryDirectory
from unittest.mock import patch

from agent_codex.apps.cli.main import main
from agent_codex.domains.sales.schema import build_master_formula_rows
from agent_codex.domains.sales.service import (
    build_calculated_rows,
    parse_master_rows,
    validate_master_rows,
)
from agent_codex.domains.sales.models import SiteRawRow, WbRawRow
from agent_codex.integrations.advantshop import AdvantShopClient


class SalesSheetTests(unittest.TestCase):
    def test_parse_and_validate_master_rows(self) -> None:
        rows = parse_master_rows(
            [
                [
                    "sku-1",
                    "TRUE",
                    "Товар 1",
                    "Категория",
                    "Brand",
                    "101",
                    "VC-1",
                    "501",
                    "601",
                    "box",
                    "100",
                    "10",
                    "10",
                    "10",
                    "200",
                    "30",
                    "20",
                    "690",
                    "590",
                    "10%",
                    "usn6",
                    "",
                ],
                [
                    "sku-1",
                    "TRUE",
                    "Товар 2",
                    "",
                    "",
                    "102",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                ],
                [
                    "",
                    "TRUE",
                    "Товар без ключа",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                ],
            ]
        )
        self.assertEqual(len(rows), 3)
        errors = validate_master_rows(rows)
        codes = {item["code"] for item in errors}
        self.assertIn("duplicate_product_key", codes)
        self.assertIn("missing_product_key", codes)

    def test_build_calculated_rows_prefers_manual_prices(self) -> None:
        master_rows = parse_master_rows(
            [
                [
                    "sku-1",
                    "TRUE",
                    "Товар 1",
                    "Категория",
                    "Brand",
                    "101",
                    "VC-1",
                    "501",
                    "601",
                    "box",
                    "100",
                    "10",
                    "10",
                    "10",
                    "200",
                    "30",
                    "20",
                    "890",
                    "790",
                    "12%",
                    "usn6",
                    "",
                ]
            ]
        )
        site_rows = {
            "sku-1": SiteRawRow(
                product_key="sku-1",
                fetched_at="2026-04-06T00:00:00+00:00",
                product_id=501,
                offer_id=601,
                current_price_rub=650,
                discounted_price_rub=620,
                stock_qty=12,
                orders_30d_units=3,
                revenue_30d_rub=1860,
            )
        }
        wb_rows = {
            "sku-1": WbRawRow(
                product_key="sku-1",
                fetched_at="2026-04-06T00:00:00+00:00",
                nm_id=101,
                current_price_rub=700,
                discounted_price_rub=680,
                subject_name="косметика",
                stocks_qty=8,
                sales_30d_units=5,
                revenue_30d_rub=3400,
            )
        }
        calculated = build_calculated_rows(
            master_rows,
            wb_rows=wb_rows,
            wb_commissions={"косметика": 0.18},
            wb_logistics_rub=65,
            wb_return_rub=35,
            wb_buyout_pct=0.9,
            site_rows=site_rows,
            settings_map={
                "site_commission_pct": "0.14",
                "default_ad_pct_cap": "0.1",
                "default_tax_pct": "0.06",
                "tax_profile_usn6": "0.06",
                "wb_default_commission_pct": "0.15",
            },
        )
        by_channel = {item.channel: item for item in calculated}
        self.assertEqual(by_channel["site"].target_price_rub, 890)
        self.assertEqual(by_channel["wb"].target_price_rub, 790)
        self.assertGreater(by_channel["site"].live_price_rub, 0)
        self.assertGreater(by_channel["wb"].live_price_rub, 0)

    def test_master_formula_rows_reference_calc_and_actions(self) -> None:
        formulas = build_master_formula_rows(3)
        self.assertEqual(len(formulas), 2)
        self.assertEqual(len(formulas[0]), 10)
        self.assertIn("РАСЧЕТ", formulas[0][0])
        self.assertIn("ДЕЙСТВИЯ", formulas[0][8])

    def test_sales_sheet_diagnose_cli_without_config(self) -> None:
        with TemporaryDirectory() as tmp:
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                rc = main(["sales-sheet-diagnose", "--project-root", tmp, "--json"])
            self.assertEqual(rc, 0)
            payload = json.loads(buffer.getvalue())
            self.assertEqual(payload["status"], "warning")
            self.assertIn("config", payload)

    def test_sales_sheet_init_cli_without_config_returns_error_payload(self) -> None:
        with TemporaryDirectory() as tmp:
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                rc = main(["sales-sheet-init", "--project-root", tmp, "--json"])
            self.assertEqual(rc, 0)
            payload = json.loads(buffer.getvalue())
            self.assertEqual(payload["status"], "error")
            self.assertIn("google_sheets_spreadsheet_id", payload)

    def test_advantshop_catalog_uses_auth_key(self) -> None:
        client = AdvantShopClient(
            base_url="https://example.com",
            api_key="api-key",
            auth_api_key="auth-key",
        )
        with patch.object(AdvantShopClient, "request_json", return_value={}) as request_json:
            client.get_catalog_all()
        request_json.assert_called_once_with(
            "/api/catalog/all",
            method="POST",
            data={},
            use_auth=True,
        )

    def test_advantshop_orders_use_primary_key(self) -> None:
        client = AdvantShopClient(
            base_url="https://example.com",
            api_key="api-key",
            auth_api_key="auth-key",
        )
        with patch.object(AdvantShopClient, "request_json", return_value={}) as request_json:
            client.get_orders_list(page=1, items_per_page=10)
        request_json.assert_called_once()
        _, kwargs = request_json.call_args
        self.assertNotIn("use_auth", kwargs)


if __name__ == "__main__":
    unittest.main()
