from __future__ import annotations

import unittest

from agent_codex.domains.marketplace.tnved_ui_catalog import (
    _dedupe_rows,
    _render_markdown,
    get_open_tnved_text_patterns,
)


class TnvedUiCatalogTests(unittest.TestCase):
    def test_dedupe_rows_normalizes_description(self) -> None:
        rows = [
            {
                "subject_id": 1,
                "category_name": "Категория",
                "tnved_code": "3304990000",
                "tnved_description": "  Описание   кода ",
                "source": "WB_UI",
                "collected_at": "2026-04-15T00:00:00+00:00",
            },
            {
                "subject_id": 1,
                "category_name": "Категория",
                "tnved_code": "3304990000",
                "tnved_description": "Описание кода",
                "source": "WB_UI",
                "collected_at": "2026-04-15T00:00:01+00:00",
            },
        ]
        deduped = _dedupe_rows(rows)
        self.assertEqual(len(deduped), 1)
        self.assertEqual(deduped[0]["tnved_description"], "Описание кода")

    def test_render_markdown_with_category_table(self) -> None:
        markdown = _render_markdown(
            grouped=[
                {
                    "subject_id": 10,
                    "category_name": "Косметика",
                    "rows": [
                        {"tnved_code": "3304990000", "tnved_description": "Средства по уходу за кожей"},
                    ],
                }
            ],
            errors=[],
        )
        self.assertIn("| ТН ВЭД | Расшифровка |", markdown)
        self.assertIn("3304990000", markdown)
        self.assertIn("Косметика", markdown)

    def test_open_tnved_text_patterns_include_required_fallbacks(self) -> None:
        patterns = get_open_tnved_text_patterns()
        self.assertIn("ТН ВЭД", patterns)
        self.assertIn("Выберите ТН ВЭД", patterns)
        self.assertIn("Введите код ТН ВЭД", patterns)


if __name__ == "__main__":
    unittest.main()

