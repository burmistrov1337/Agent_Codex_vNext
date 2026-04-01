from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from .api import WildberriesApiClient, WildberriesApiError
from .artifacts import (
    render_watch_dashboard_html,
    render_watch_summary_markdown,
)
from .supply_planner import _extract_primary_barcode, _fetch_all_cards, _write_xlsx


@dataclass(slots=True)
class CabinetMonitorConfig:
    output_root: Path
    sales_days: int = 90
    top_limit: int = 50


@dataclass(slots=True)
class CabinetMonitorResult:
    output_dir: Path
    markdown_path: Path
    xlsx_path: Path
    summary_markdown_path: Path
    dashboard_html_path: Path
    snapshot_path: Path
    row_count: int


def build_cabinet_monitor(
    client: WildberriesApiClient,
    config: CabinetMonitorConfig,
    today: date | None = None,
) -> CabinetMonitorResult:
    today = today or date.today()
    date_from = (today - timedelta(days=config.sales_days - 1)).isoformat()

    cards_by_nm_id, _ = _fetch_all_cards(client)
    sales = _safe_call(client.get_supplier_sales, date_from, default=[])
    orders = _safe_call(client.get_supplier_orders, date_from, default=[])
    seller_inventory = _fetch_seller_inventory_safe(client, cards_by_nm_id)

    sales_stats = _build_sales_stats(sales, today=today)
    order_stats = _build_order_stats(orders, today=today)
    relevant_nm_ids = set(cards_by_nm_id) & (set(sales_stats) | set(seller_inventory))
    price_by_nm_id = _fetch_prices(client, sorted(relevant_nm_ids))

    rows: list[dict[str, Any]] = []
    for nm_id in sorted(relevant_nm_ids):
        card = cards_by_nm_id.get(nm_id)
        if not card:
            continue
        sales_item = sales_stats.get(nm_id, _empty_sales_item())
        order_item = order_stats.get(nm_id, _empty_order_item())
        stock = int((seller_inventory.get(nm_id) or {}).get("amount") or 0)
        if stock <= 0 and sales_item["sales_90d"] <= 0:
            continue
        price_item = price_by_nm_id.get(nm_id, {})
        row = _build_row(
            nm_id=nm_id,
            card=card,
            sales_item=sales_item,
            order_item=order_item,
            stock=stock,
            barcode=str((seller_inventory.get(nm_id) or {}).get("barcode") or _extract_primary_barcode(card)),
            price_item=price_item,
        )
        rows.append(row)

    rows.sort(key=lambda item: (-item["priority_score"], -item["revenue_30d"], item["title"]))
    output_dir = config.output_root / f"cabinet_monitor_{today.isoformat()}"
    output_dir.mkdir(parents=True, exist_ok=True)
    markdown_path = output_dir / "cabinet_monitor.md"
    xlsx_path = output_dir / "cabinet_monitor.xlsx"
    summary_markdown_path = output_dir / "cabinet_watch_summary.md"
    dashboard_html_path = output_dir / "cabinet_dashboard.html"
    legacy_pdf_path = output_dir / "cabinet_watch_summary.pdf"
    snapshot_path = _append_history_snapshot(config.output_root, today, rows)
    if legacy_pdf_path.exists():
        legacy_pdf_path.unlink()

    markdown_path.write_text(
        _render_markdown(rows=rows, today=today, top_limit=config.top_limit, snapshot_path=snapshot_path),
        encoding="utf-8",
    )
    _write_xlsx(
        xlsx_path,
        headers=[
            "nm_id",
            "vendor_code",
            "barcode",
            "title",
            "status",
            "priority_score",
            "sales_30d",
            "sales_prev_30d",
            "sales_90d",
            "sales_delta_pct",
            "orders_30d",
            "stock",
            "stock_cover_days",
            "discounted_price",
            "discount_pct",
            "bad_turnover",
            "issues",
            "actions",
        ],
        rows=[
            [
                row["nm_id"],
                row["vendor_code"],
                row["barcode"],
                row["title"],
                row["status"],
                row["priority_score"],
                row["sales_30d"],
                row["sales_prev_30d"],
                row["sales_90d"],
                row["sales_delta_pct"],
                row["orders_30d"],
                row["stock"],
                row["stock_cover_days"],
                row["discounted_price"],
                row["discount_pct"],
                row["bad_turnover"],
                row["issues"],
                row["actions"],
            ]
            for row in rows
        ],
    )
    summary_markdown_path.write_text(
        render_watch_summary_markdown(
            rows=rows,
            today=today,
            snapshot_path=snapshot_path,
            top_limit=config.top_limit,
            dashboard_filename=dashboard_html_path.name,
        ),
        encoding="utf-8",
    )
    dashboard_html_path.write_text(
        render_watch_dashboard_html(
            rows=rows,
            today=today,
            snapshot_path=snapshot_path,
            top_limit=config.top_limit,
            summary_filename=summary_markdown_path.name,
        ),
        encoding="utf-8",
    )

    return CabinetMonitorResult(
        output_dir=output_dir,
        markdown_path=markdown_path,
        xlsx_path=xlsx_path,
        summary_markdown_path=summary_markdown_path,
        dashboard_html_path=dashboard_html_path,
        snapshot_path=snapshot_path,
        row_count=len(rows),
    )


def _build_sales_stats(sales: list[dict[str, Any]], today: date) -> dict[int, dict[str, Any]]:
    stats: dict[int, dict[str, Any]] = {}
    for row in sales:
        nm_id = int(row.get("nmId") or 0)
        if not nm_id:
            continue
        item = stats.setdefault(nm_id, _empty_sales_item())
        qty = max(1, int(float(row.get("quantity") or 1)))
        revenue = float(row.get("forPay") or row.get("finishedPrice") or row.get("priceWithDisc") or 0.0)
        bucket = _sales_bucket(_parse_dt(row), today)
        item["sales_90d"] += qty
        item["revenue_90d"] += revenue
        if bucket == "0_30":
            item["sales_30d"] += qty
            item["revenue_30d"] += revenue
        elif bucket == "31_60":
            item["sales_prev_30d"] += qty
        elif bucket == "61_90":
            item["sales_old_30d"] += qty
    return stats


def _build_order_stats(orders: list[dict[str, Any]], today: date) -> dict[int, dict[str, Any]]:
    stats: dict[int, dict[str, Any]] = {}
    for row in orders:
        nm_id = int(row.get("nmId") or 0)
        if not nm_id:
            continue
        item = stats.setdefault(nm_id, _empty_order_item())
        qty = max(1, int(float(row.get("quantity") or 1)))
        bucket = _sales_bucket(_parse_dt(row), today)
        item["orders_90d"] += qty
        if bucket == "0_30":
            item["orders_30d"] += qty
        elif bucket == "31_60":
            item["orders_prev_30d"] += qty
    return stats


def _fetch_prices(client: WildberriesApiClient, nm_ids: list[int]) -> dict[int, dict[str, Any]]:
    result: dict[int, dict[str, Any]] = {}
    for start in range(0, len(nm_ids), 100):
        chunk = nm_ids[start : start + 100]
        if not chunk:
            continue
        response = _safe_call(client.get_prices_goods_filter_by_nm_ids, chunk, default={"data": {"listGoods": []}})
        items = (response.get("data") or {}).get("listGoods") or response.get("data") or []
        for item in items or []:
            nm_id = int(item.get("nmID") or item.get("nmId") or 0)
            if nm_id:
                result[nm_id] = {
                    "price": item.get("price"),
                    "discount": item.get("discount"),
                    "discounted_price": item.get("discountedPrice") or item.get("discountPrice"),
                    "is_bad_turnover": item.get("isBadTurnover"),
                }
    return result


def _build_row(
    *,
    nm_id: int,
    card: dict[str, Any],
    sales_item: dict[str, Any],
    order_item: dict[str, Any],
    stock: int,
    barcode: str,
    price_item: dict[str, Any],
) -> dict[str, Any]:
    sales_30d = int(sales_item["sales_30d"])
    sales_prev_30d = int(sales_item["sales_prev_30d"])
    sales_90d = int(sales_item["sales_90d"])
    revenue_30d = round(float(sales_item["revenue_30d"]), 2)
    orders_30d = int(order_item["orders_30d"])
    sales_delta_pct = _delta_pct(sales_30d, sales_prev_30d) if sales_prev_30d else None
    stock_cover_days = round(stock / (sales_30d / 30), 1) if sales_30d > 0 else None

    issues: list[str] = []
    actions: list[str] = []
    status = "stable"
    priority_score = 0

    if sales_30d == 0 and stock > 0:
        status = "dead_stock"
        priority_score += 60
        issues.append("Есть остаток, но продаж за последние 30 дней нет.")
        actions.append("Проверить карточку, цену и участие в акциях: остаток зависает без движения.")

    if sales_prev_30d >= 5 and sales_delta_pct is not None and sales_delta_pct <= -35:
        status = "decline"
        priority_score += 50
        issues.append(f"Продажи просели на {abs(sales_delta_pct):.0f}% к предыдущим 30 дням.")
        actions.append("Проверить цену, выдачу, акции и конкурентов: падение уже системное.")

    if stock_cover_days is not None and stock_cover_days > 120:
        status = "overstock"
        priority_score += 45
        issues.append(f"Остаток покрывает примерно {stock_cover_days} дней спроса.")
        actions.append("Снизить цену, подключить промо или сократить новое пополнение по SKU.")
    elif stock_cover_days is not None and stock_cover_days < 14 and sales_30d > 0:
        priority_score += 35
        issues.append(f"Остаток покрывает только {stock_cover_days} дней спроса.")
        actions.append("Подготовить пополнение, чтобы не потерять текущий спрос.")

    if price_item.get("is_bad_turnover"):
        priority_score += 20
        issues.append("WB помечает товар как проблемный по оборачиваемости.")
        actions.append("Пересмотреть цену и промо-механику: WB уже видит риск по оборачиваемости.")

    if sales_30d > sales_prev_30d >= 5:
        priority_score += 10
        if not issues:
            status = "growth"
        actions.append("Сохранить доступность и не ухудшать карточку: SKU сейчас растёт.")

    priority_score += min(int(revenue_30d // 1000), 20)

    unique_actions: list[str] = []
    for action in actions:
        if action not in unique_actions:
            unique_actions.append(action)

    return {
        "nm_id": nm_id,
        "vendor_code": str(card.get("vendorCode") or ""),
        "barcode": barcode,
        "title": str(card.get("title") or ""),
        "subject_name": str(card.get("subjectName") or ""),
        "brand": str(card.get("brand") or ""),
        "status": status,
        "priority_score": priority_score,
        "sales_30d": sales_30d,
        "sales_prev_30d": sales_prev_30d,
        "sales_90d": sales_90d,
        "sales_delta_pct": sales_delta_pct,
        "orders_30d": orders_30d,
        "revenue_30d": revenue_30d,
        "stock": stock,
        "stock_cover_days": stock_cover_days,
        "discounted_price": price_item.get("discounted_price"),
        "discount_pct": price_item.get("discount"),
        "bad_turnover": price_item.get("is_bad_turnover"),
        "issues": " | ".join(issues),
        "actions": " | ".join(unique_actions[:3]),
    }


def _append_history_snapshot(output_root: Path, today: date, rows: list[dict[str, Any]]) -> Path:
    history_dir = output_root / "history"
    history_dir.mkdir(parents=True, exist_ok=True)
    snapshot_path = history_dir / "cabinet_monitor_history.jsonl"
    with snapshot_path.open("a", encoding="utf-8") as fh:
        for row in rows:
            payload = {"snapshot_date": today.isoformat(), **row}
            fh.write(json.dumps(payload, ensure_ascii=False) + "\n")
    return snapshot_path


def _fetch_seller_inventory_safe(
    client: WildberriesApiClient,
    cards_by_nm_id: dict[int, dict[str, Any]],
    chunk_size: int = 500,
) -> dict[int, dict[str, Any]]:
    inventory: dict[int, dict[str, Any]] = {}
    sku_to_nm: dict[str, int] = {}
    for nm_id, card in cards_by_nm_id.items():
        for size in card.get("sizes") or []:
            for sku in size.get("skus") or []:
                sku_str = str(sku or "").strip()
                if sku_str:
                    sku_to_nm[sku_str] = nm_id
    if not sku_to_nm:
        return inventory

    warehouses = _safe_call(client.get_seller_warehouses, default=[])
    warehouse_ids = [int(item.get("id") or 0) for item in warehouses if int(item.get("id") or 0)]
    all_skus = list(sku_to_nm.keys())
    for warehouse_id in warehouse_ids:
        for start in range(0, len(all_skus), chunk_size):
            chunk = all_skus[start : start + chunk_size]
            response = _safe_call(client.get_warehouse_inventory, warehouse_id, skus=chunk, default={"stocks": []})
            for row in response.get("stocks") or []:
                sku = str(row.get("sku") or "").strip()
                nm_id = sku_to_nm.get(sku)
                if not nm_id:
                    continue
                item = inventory.setdefault(nm_id, {"amount": 0, "barcode": ""})
                item["amount"] += int(row.get("amount") or 0)
                if not item["barcode"]:
                    item["barcode"] = sku
    return inventory


def _safe_call(func, *args, default, **kwargs):
    for attempt in range(5):
        try:
            return func(*args, **kwargs)
        except WildberriesApiError as exc:
            if "429" not in str(exc) or attempt == 4:
                return default
            time.sleep(8 * (attempt + 1))
    return default


def _render_markdown(
    *,
    rows: list[dict[str, Any]],
    today: date,
    top_limit: int,
    snapshot_path: Path,
) -> str:
    focus_rows = rows[:top_limit]
    status_counts: dict[str, int] = {}
    for row in rows:
        status_counts[row["status"]] = status_counts.get(row["status"], 0) + 1

    top_declines = [row for row in rows if row["status"] == "decline"][:10]
    top_overstock = [row for row in rows if row["status"] in {"overstock", "dead_stock"}][:10]
    top_growth = [row for row in rows if row["status"] == "growth"][:10]

    lines = [
        f"# WB Cabinet Monitor {today.isoformat()}",
        "",
        f"- SKU в мониторинге: `{len(rows)}`",
        f"- История снапшотов: `{snapshot_path}`",
        f"- `decline`: `{status_counts.get('decline', 0)}`",
        f"- `overstock`: `{status_counts.get('overstock', 0)}`",
        f"- `dead_stock`: `{status_counts.get('dead_stock', 0)}`",
        f"- `growth`: `{status_counts.get('growth', 0)}`",
        "",
        "## Главный вывод",
        "",
        "- Этот отчёт показывает не просто цифры, а список SKU, где уже есть риск потерять прибыль или, наоборот, можно ускорить рост.",
        "- Приоритет выше у позиций с сочетанием падения продаж, большого остатка и проблемной оборачиваемости.",
        "",
    ]

    if top_declines:
        lines.extend(
            [
                "## Самые заметные просадки",
                "",
                "| SKU | Продажи 30д | Пред. 30д | Дельта | Остаток | Что не так | Что делать |",
                "| --- | --- | --- | --- | --- | --- | --- |",
            ]
        )
        for row in top_declines:
            lines.append(
                f"| {_md(row['title'])} | {row['sales_30d']} | {row['sales_prev_30d']} | {_cell(row['sales_delta_pct'])}% | "
                f"{row['stock']} | {_md(row['issues'])} | {_md(row['actions'])} |"
            )
        lines.append("")

    if top_overstock:
        lines.extend(
            [
                "## Что рискует залежаться",
                "",
                "| SKU | Остаток | Покрытие, дни | Продажи 30д | Статус | Что делать |",
                "| --- | --- | --- | --- | --- | --- |",
            ]
        )
        for row in top_overstock:
            lines.append(
                f"| {_md(row['title'])} | {row['stock']} | {_cell(row['stock_cover_days'])} | {row['sales_30d']} | "
                f"{_md(row['status'])} | {_md(row['actions'])} |"
            )
        lines.append("")

    if top_growth:
        lines.extend(
            [
                "## Что растёт и что стоит не потерять",
                "",
                "| SKU | Продажи 30д | Пред. 30д | Дельта | Остаток | Что делать |",
                "| --- | --- | --- | --- | --- | --- |",
            ]
        )
        for row in top_growth:
            lines.append(
                f"| {_md(row['title'])} | {row['sales_30d']} | {row['sales_prev_30d']} | {_cell(row['sales_delta_pct'])}% | "
                f"{row['stock']} | {_md(row['actions'])} |"
            )
        lines.append("")

    lines.extend(
        [
            f"## Основной список SKU (топ {top_limit})",
            "",
            "| nmID | SKU | Статус | Приоритет | Продажи 30д | Пред. 30д | Остаток | Покрытие, дни | Цена со скидкой | Что не так | Что делать |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for row in focus_rows:
        delta_value = f"{_cell(row['sales_delta_pct'])}%" if row["sales_delta_pct"] is not None else ""
        lines.append(
            f"| {row['nm_id']} | {_md(row['title'])} | {_md(row['status'])} | {row['priority_score']} | "
            f"{row['sales_30d']} ({delta_value}) | {row['sales_prev_30d']} | {row['stock']} | {_cell(row['stock_cover_days'])} | "
            f"{_cell(row['discounted_price'])} | {_md(row['issues'])} | {_md(row['actions'])} |"
        )

    return "\n".join(lines).strip() + "\n"


def _empty_sales_item() -> dict[str, Any]:
    return {
        "sales_30d": 0,
        "sales_prev_30d": 0,
        "sales_old_30d": 0,
        "sales_90d": 0,
        "revenue_30d": 0.0,
        "revenue_90d": 0.0,
    }


def _empty_order_item() -> dict[str, Any]:
    return {
        "orders_30d": 0,
        "orders_prev_30d": 0,
        "orders_90d": 0,
    }


def _sales_bucket(dt: datetime | None, today: date) -> str | None:
    if dt is None:
        return None
    delta = (today - dt.date()).days
    if 0 <= delta <= 29:
        return "0_30"
    if 30 <= delta <= 59:
        return "31_60"
    if 60 <= delta <= 89:
        return "61_90"
    return None


def _parse_dt(row: dict[str, Any]) -> datetime | None:
    raw = str(row.get("date") or row.get("lastChangeDate") or "")
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def _delta_pct(current: int | float, previous: int | float) -> float | None:
    if previous in (None, 0):
        return None
    return round(((float(current) - float(previous)) / float(previous)) * 100, 1)


def _md(value: Any) -> str:
    return str(value or "").replace("|", "\\|").replace("\n", " ").strip()


def _cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.1f}"
    return str(value)
