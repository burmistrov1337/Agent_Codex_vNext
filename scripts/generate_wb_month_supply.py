from __future__ import annotations

import argparse
import math
from collections import Counter
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from agent_codex.config import load_settings
from agent_codex.domains.marketplace.api import WildberriesApiClient
from agent_codex.domains.marketplace.supply_planner import (
    _build_sales_stats,
    _build_stock_stats,
    _extract_primary_barcode,
    _fetch_all_cards,
    _fetch_seller_inventory,
    _has_required_card_content,
    _write_xlsx,
)


@dataclass(slots=True)
class SupplyRow:
    nm_id: int
    vendor_code: str
    barcode: str
    title: str
    subject: str
    price: float | None
    sales_30d: int
    sale_days_30d: int
    avg_daily_sales: float
    seller_stock: int
    wb_stock: int
    coverage_days: float | None
    demand_30d: int
    need_30d: int
    safe_available: int
    recommended_qty: int
    priority: str
    problem: str
    action: str


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate WB monthly supply dashboard")
    parser.add_argument("--project-root", default="d:/Agent_Codex_vNext")
    parser.add_argument("--days", type=int, default=30)
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    settings = load_settings(project_root)
    if not settings.wb_api_token:
        raise RuntimeError("WB_API_TOKEN is not configured")

    today = date.today()
    date_from = today - timedelta(days=args.days - 1)
    client = WildberriesApiClient(token=settings.wb_api_token, timeout_seconds=settings.wb_api_timeout_seconds)

    cards_by_nm_id, _ = _fetch_all_cards(client)
    sales = client.get_supplier_sales(date_from.isoformat())
    stocks = client.get_supplier_stocks(date_from.isoformat())
    sales_stats = _build_sales_stats(sales)
    seller_inventory = _fetch_seller_inventory(client, cards_by_nm_id, nm_ids=set(sales_stats))
    stock_stats = _build_stock_stats(stocks, seller_inventory)
    prices = _fetch_prices_by_nm(client)

    rows: list[SupplyRow] = []
    for nm_id, sale_item in sales_stats.items():
        sales_units = int(sale_item.get("net_sales_units") or 0)
        if sales_units <= 0:
            continue

        card = cards_by_nm_id.get(nm_id)
        if not card or not _has_required_card_content(card):
            continue

        stock_item = stock_stats.get(nm_id, {})
        seller_stock = int(stock_item.get("local_stock") or 0)
        wb_stock = int(stock_item.get("wb_stock") or 0)
        if seller_stock <= 0:
            continue

        avg_daily = sales_units / args.days
        demand_30d = max(1, math.ceil(avg_daily * 30))
        need_30d = max(0, demand_30d - wb_stock)
        safe_available = seller_stock // 2
        recommended = min(need_30d, safe_available)
        coverage_days = (wb_stock / avg_daily) if avg_daily > 0 else None

        priority, problem, action = _decision(
            sales_units=sales_units,
            sale_days=len(sale_item.get("sale_days") or []),
            wb_stock=wb_stock,
            coverage_days=coverage_days,
            recommended=recommended,
            safe_available=safe_available,
        )

        rows.append(
            SupplyRow(
                nm_id=nm_id,
                vendor_code=str(card.get("vendorCode") or sale_item.get("vendor_code") or ""),
                barcode=str(stock_item.get("barcode") or sale_item.get("barcode") or _extract_primary_barcode(card)),
                title=str(card.get("title") or ""),
                subject=str(card.get("subjectName") or sale_item.get("subject") or ""),
                price=prices.get(nm_id),
                sales_30d=sales_units,
                sale_days_30d=len(sale_item.get("sale_days") or []),
                avg_daily_sales=avg_daily,
                seller_stock=seller_stock,
                wb_stock=wb_stock,
                coverage_days=coverage_days,
                demand_30d=demand_30d,
                need_30d=need_30d,
                safe_available=safe_available,
                recommended_qty=recommended,
                priority=priority,
                problem=problem,
                action=action,
            )
        )

    rows.sort(key=lambda row: (row.recommended_qty <= 0, -row.recommended_qty, -row.sales_30d, row.title.lower()))

    output_dir = project_root / "generated" / "marketplace" / f"month_supply_{today.isoformat()}"
    output_dir.mkdir(parents=True, exist_ok=True)
    md_path = output_dir / "month_supply.md"
    xlsx_path = output_dir / "month_supply.xlsx"
    html_path = output_dir / "month_supply_dashboard.html"

    _write_markdown(md_path, rows, today=today, date_from=date_from, days=args.days)
    _write_excel(xlsx_path, rows)
    html_path.write_text(_render_html(rows, today=today, date_from=date_from, days=args.days), encoding="utf-8")

    summary = Counter(row.priority for row in rows)
    print(f"output_dir={output_dir}")
    print(f"html={html_path}")
    print(f"xlsx={xlsx_path}")
    print(f"md={md_path}")
    print(f"sku={len(rows)}")
    print(f"recommended_sku={sum(1 for row in rows if row.recommended_qty > 0)}")
    print(f"recommended_total={sum(row.recommended_qty for row in rows)}")
    print(f"priority_counts={dict(summary)}")


def _fetch_prices_by_nm(client: WildberriesApiClient) -> dict[int, float]:
    prices: dict[int, float] = {}
    offset = 0
    while True:
        response = client.get_prices_goods_filter(limit=1000, offset=offset)
        goods = ((response.get("data") or {}).get("listGoods") or response.get("listGoods") or [])
        if not goods:
            break
        for item in goods:
            nm_id = int(item.get("nmID") or item.get("nmId") or 0)
            if not nm_id:
                continue
            sizes = item.get("sizes") or []
            discounted = None
            if sizes:
                discounted = sizes[0].get("discountedPrice") or sizes[0].get("price")
            value = discounted or item.get("discountedPrice") or item.get("price")
            if value is not None:
                try:
                    prices[nm_id] = float(value)
                except (TypeError, ValueError):
                    pass
        if len(goods) < 1000:
            break
        offset += 1000
    return prices


def _decision(
    *,
    sales_units: int,
    sale_days: int,
    wb_stock: int,
    coverage_days: float | None,
    recommended: int,
    safe_available: int,
) -> tuple[str, str, str]:
    if recommended > 0 and (coverage_days is None or coverage_days <= 21):
        return "Отгрузить", "WB-остаток не закрывает месяц спроса.", "Везти рекомендованное количество."
    if recommended > 0:
        return "Наблюдать", "Потребность есть, но дефицит не критичный.", "Можно везти после приоритетных SKU."
    if safe_available <= 0:
        return "Не отгружать", "Локального остатка недостаточно для безопасной отгрузки.", "Не трогать складской остаток."
    if coverage_days is not None and coverage_days >= 30:
        return "Не отгружать", "WB-остаток уже покрывает месяц или больше.", "Не пополнять сейчас."
    if sales_units < 3 or sale_days < 2:
        return "Наблюдать", "Спрос слабый или нерегулярный.", "Проверить повторно через неделю."
    return "Наблюдать", "Расчетная потребность на месяц закрыта.", "Держать под контролем остаток WB."


def _write_markdown(path: Path, rows: list[SupplyRow], *, today: date, date_from: date, days: int) -> None:
    recommended = [row for row in rows if row.recommended_qty > 0]
    lines = [
        "# Поставка WB на месяц",
        "",
        f"- Дата отчета: `{today.isoformat()}`",
        f"- Период продаж: `{date_from.isoformat()} .. {today.isoformat()}` ({days} дней)",
        f"- SKU с продажами и локальным остатком: `{len(rows)}`",
        f"- SKU к отгрузке: `{len(recommended)}`",
        f"- Всего к отгрузке: `{sum(row.recommended_qty for row in recommended)}` шт.",
        "",
        "## Приоритет к отгрузке",
        "",
        "| SKU | Артикул WB | Артикул продавца | Баркод | Остаток | WB-остаток | Продажи 30д | К отгрузке | Что делать |",
        "| --- | --- | --- | --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in recommended:
        lines.append(
            "| "
            + " | ".join(
                [
                    _md(row.title),
                    str(row.nm_id),
                    _md(row.vendor_code),
                    _md(row.barcode),
                    str(row.seller_stock),
                    str(row.wb_stock),
                    str(row.sales_30d),
                    str(row.recommended_qty),
                    _md(row.action),
                ]
            )
            + " |"
        )
    path.write_text("\n".join(lines), encoding="utf-8")


def _write_excel(path: Path, rows: list[SupplyRow]) -> None:
    headers = [
        "SKU",
        "Артикул WB",
        "Артикул продавца",
        "Баркод",
        "Цена WB после скидки продавца",
        "Продажи 30д",
        "Дни продаж 30д",
        "Средние продажи в день",
        "Остаток продавца",
        "WB-остаток",
        "Покрытие WB, дни",
        "Потребность на 30 дней",
        "Безопасно доступно к отгрузке",
        "К отгрузке",
        "Приоритет",
        "Что не так",
        "Что делать",
    ]
    data = [
        [
            row.title,
            row.nm_id,
            row.vendor_code,
            row.barcode,
            row.price if row.price is not None else "",
            row.sales_30d,
            row.sale_days_30d,
            round(row.avg_daily_sales, 2),
            row.seller_stock,
            row.wb_stock,
            round(row.coverage_days, 1) if row.coverage_days is not None else "",
            row.demand_30d,
            row.safe_available,
            row.recommended_qty,
            row.priority,
            row.problem,
            row.action,
        ]
        for row in rows
    ]
    _write_xlsx(path, headers=headers, rows=data)


def _render_html(rows: list[SupplyRow], *, today: date, date_from: date, days: int) -> str:
    recommended = [row for row in rows if row.recommended_qty > 0]
    table_rows = "\n".join(
        f"""
        <tr>
          <td>{_html(row.title)}</td>
          <td>{row.nm_id}</td>
          <td>{_html(row.vendor_code)}</td>
          <td>{_html(row.barcode)}</td>
          <td>{_money(row.price)}</td>
          <td>{row.seller_stock}</td>
          <td>{row.wb_stock}</td>
          <td>{row.sales_30d}</td>
          <td>{row.demand_30d}</td>
          <td><input value="{row.recommended_qty}" /></td>
          <td></td>
        </tr>
        """
        for row in recommended
    )
    priority_rows = "\n".join(
        f"""
        <tr>
          <td>{_html(row.title)}</td>
          <td>{row.nm_id}</td>
          <td>{_html(row.vendor_code)}</td>
          <td>{row.sales_30d}</td>
          <td>{row.seller_stock}</td>
          <td>{row.wb_stock}</td>
          <td>{row.recommended_qty}</td>
          <td>{_html(row.problem)}</td>
          <td>{_html(row.action)}</td>
        </tr>
        """
        for row in recommended
    )
    total_qty = sum(row.recommended_qty for row in recommended)
    return f"""<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8" />
  <title>Поставка WB на месяц</title>
  <style>
    :root {{ color-scheme: dark; --bg:#101418; --panel:#18202a; --line:#2c3948; --text:#f4f7fb; --muted:#9fb0c3; --accent:#19a974; }}
    * {{ box-sizing: border-box; }}
    body {{ margin:0; font:14px/1.45 "Segoe UI", sans-serif; background:var(--bg); color:var(--text); }}
    main {{ padding:28px; max-width:1800px; margin:auto; }}
    h1 {{ margin:0 0 8px; font-size:30px; }}
    h2 {{ margin:32px 0 12px; font-size:20px; }}
    .meta {{ color:var(--muted); margin-bottom:20px; }}
    .cards {{ display:grid; grid-template-columns:repeat(4,minmax(180px,1fr)); gap:12px; margin:20px 0; }}
    .card {{ background:var(--panel); border:1px solid var(--line); border-radius:8px; padding:16px; }}
    .card b {{ display:block; font-size:26px; margin-top:6px; }}
    table {{ width:100%; border-collapse:collapse; background:var(--panel); border:1px solid var(--line); }}
    th,td {{ padding:10px 12px; border-bottom:1px solid var(--line); vertical-align:top; }}
    th {{ text-align:left; color:#dfe8f5; position:sticky; top:0; background:#202a36; }}
    td:nth-child(n+2), th:nth-child(n+2) {{ text-align:center; }}
    td:first-child, th:first-child {{ text-align:left; min-width:320px; }}
    input {{ width:82px; padding:7px 8px; border-radius:6px; border:1px solid #536171; background:#101820; color:var(--text); text-align:center; }}
    button {{ border:0; border-radius:7px; padding:10px 14px; background:var(--accent); color:#062016; font-weight:700; cursor:pointer; }}
    @media print {{
      body {{ background:white; color:black; }}
      main > *:not(.printable) {{ display:none !important; }}
      .printable, .printable table {{ display:block; color:black; background:white; }}
      th,td {{ color:black; border-color:#999; }}
      input {{ border:0; color:black; background:white; }}
      .no-print, .hide-print {{ display:none !important; }}
      td:nth-child(6), th:nth-child(6), td:nth-child(7), th:nth-child(7) {{ display:none; }}
    }}
  </style>
</head>
<body>
<main>
  <h1>Поставка WB на месяц</h1>
  <div class="meta">Период продаж: {date_from.isoformat()} .. {today.isoformat()} ({days} дней). Расчет без деления по городам.</div>
  <section class="cards">
    <div class="card">SKU с продажами и остатком<b>{len(rows)}</b></div>
    <div class="card">SKU к отгрузке<b>{len(recommended)}</b></div>
    <div class="card">Всего к отгрузке<b>{total_qty}</b></div>
    <div class="card">Горизонт<b>30 дней</b></div>
  </section>
  <h2>Приоритет к отгрузке</h2>
  <table>
    <thead><tr><th>SKU</th><th>Артикул WB</th><th>Артикул продавца</th><th>Продажи 30д</th><th>Остаток</th><th>WB</th><th>К отгрузке</th><th>Что не так</th><th>Что делать</th></tr></thead>
    <tbody>{priority_rows}</tbody>
  </table>
  <section class="printable">
    <h2>Таблица для склада</h2>
    <p class="no-print"><button onclick="window.print()">Печать складской таблицы</button></p>
    <table>
      <thead><tr><th>SKU</th><th>Артикул WB</th><th>Артикул продавца</th><th>Баркод</th><th>Цена WB</th><th class="hide-print">Остаток</th><th class="hide-print">WB-остаток</th><th>Продажи 30д</th><th>Потребность</th><th>Количество</th><th>Срок годности</th></tr></thead>
      <tbody>{table_rows}</tbody>
    </table>
  </section>
</main>
</body>
</html>"""


def _money(value: float | None) -> str:
    return "" if value is None else f"{value:.2f}"


def _md(value: str) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def _html(value: str) -> str:
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


if __name__ == "__main__":
    main()
