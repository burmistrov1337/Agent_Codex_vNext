from __future__ import annotations

import json
import html
import os
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class CabinetWatchOverview:
    total_sku: int
    decline_count: int
    overstock_count: int
    dead_stock_count: int
    growth_count: int
    health_status: str
    health_summary: str
    priority_rows: list[dict[str, Any]]
    top_declines: list[dict[str, Any]]
    top_overstock: list[dict[str, Any]]
    top_growth: list[dict[str, Any]]
    today_actions: list[str]
    previous_snapshot_date: str | None
    previous_counts: dict[str, int]
    deltas_vs_previous: dict[str, int]
    history_points: list[dict[str, Any]]
    weekly_history_points: list[dict[str, Any]]
    monthly_history_points: list[dict[str, Any]]
    risk_stock_units: int
    risk_value_proxy: float
    risk_value_proxy_coverage: int
    top_subject_groups: list[dict[str, Any]]
    top_material_groups: list[dict[str, Any]]
    top_pack_groups: list[dict[str, Any]]


def build_watch_overview(
    rows: list[dict[str, Any]],
    *,
    top_limit: int = 10,
    snapshot_path: Path | None = None,
    today: date | None = None,
) -> CabinetWatchOverview:
    status_counts: dict[str, int] = {}
    for row in rows:
        status_counts[row["status"]] = status_counts.get(row["status"], 0) + 1

    decline_count = status_counts.get("decline", 0)
    overstock_count = status_counts.get("overstock", 0)
    dead_stock_count = status_counts.get("dead_stock", 0)
    growth_count = status_counts.get("growth", 0)
    risk_load = decline_count + overstock_count + dead_stock_count

    if risk_load == 0:
        health_status = "стабильно"
        health_summary = "Критичных сигналов не найдено, кабинет выглядит стабильно."
    elif dead_stock_count >= 20 or overstock_count >= 60 or decline_count >= 25:
        health_status = "требует внимания"
        health_summary = (
            "Есть заметные просадки продаж и избыточные остатки, поэтому кабинет требует управленческого внимания."
        )
    else:
        health_status = "нужен точечный контроль"
        health_summary = "Есть отдельные зоны риска, но ситуация пока выглядит управляемой."

    priority_rows = rows[:top_limit]
    top_declines = [row for row in rows if row["status"] == "decline"][:5]
    top_overstock = [row for row in rows if row["status"] in {"overstock", "dead_stock"}][:5]
    top_growth = [row for row in rows if row["status"] == "growth"][:5]

    today_actions: list[str] = []
    for row in priority_rows:
        for action in str(row.get("actions") or "").split(" | "):
            cleaned = action.strip()
            if cleaned and cleaned not in today_actions:
                today_actions.append(cleaned)
            if len(today_actions) >= 3:
                break
        if len(today_actions) >= 3:
            break

    history_points = _load_history_points(snapshot_path, today=today)
    weekly_history_points = _aggregate_history_points(history_points, period="week")
    monthly_history_points = _aggregate_history_points(history_points, period="month")
    previous_snapshot_date = None
    previous_counts = {"decline": 0, "overstock": 0, "dead_stock": 0, "growth": 0, "total_sku": 0}
    if len(history_points) >= 2:
        previous = history_points[-2]
        previous_snapshot_date = str(previous["snapshot_date"])
        previous_counts = {
            "decline": int(previous.get("decline", 0)),
            "overstock": int(previous.get("overstock", 0)),
            "dead_stock": int(previous.get("dead_stock", 0)),
            "growth": int(previous.get("growth", 0)),
            "total_sku": int(previous.get("total_sku", 0)),
        }
    deltas_vs_previous = {
        "decline": decline_count - previous_counts["decline"],
        "overstock": overstock_count - previous_counts["overstock"],
        "dead_stock": dead_stock_count - previous_counts["dead_stock"],
        "growth": growth_count - previous_counts["growth"],
        "total_sku": len(rows) - previous_counts["total_sku"],
    }
    risk_stock_units, risk_value_proxy, risk_value_proxy_coverage = _risk_metrics(rows)
    top_subject_groups = _group_rows(rows, _subject_group_label)
    top_material_groups = _group_rows(rows, _material_group_label)
    top_pack_groups = _group_rows(rows, _pack_group_label)

    return CabinetWatchOverview(
        total_sku=len(rows),
        decline_count=decline_count,
        overstock_count=overstock_count,
        dead_stock_count=dead_stock_count,
        growth_count=growth_count,
        health_status=health_status,
        health_summary=health_summary,
        priority_rows=priority_rows,
        top_declines=top_declines,
        top_overstock=top_overstock,
        top_growth=top_growth,
        today_actions=today_actions,
        previous_snapshot_date=previous_snapshot_date,
        previous_counts=previous_counts,
        deltas_vs_previous=deltas_vs_previous,
        history_points=history_points,
        weekly_history_points=weekly_history_points,
        monthly_history_points=monthly_history_points,
        risk_stock_units=risk_stock_units,
        risk_value_proxy=risk_value_proxy,
        risk_value_proxy_coverage=risk_value_proxy_coverage,
        top_subject_groups=top_subject_groups,
        top_material_groups=top_material_groups,
        top_pack_groups=top_pack_groups,
    )


def render_watch_summary_markdown(
    *,
    rows: list[dict[str, Any]],
    today: date,
    snapshot_path: Path,
    top_limit: int = 10,
    dashboard_filename: str = "cabinet_dashboard.html",
) -> str:
    overview = build_watch_overview(rows, top_limit=top_limit, snapshot_path=snapshot_path, today=today)
    lines = [
        f"# Регулярный мониторинг кабинета Wildberries {today.isoformat()}",
        "",
        f"- Статус: `{overview.health_status}`",
        f"- SKU в мониторинге: `{overview.total_sku}`",
        f"- Просадки: `{overview.decline_count}`",
        f"- Залеживание: `{overview.overstock_count}`",
        f"- Мёртвый остаток: `{overview.dead_stock_count}`",
        f"- Рост: `{overview.growth_count}`",
        f"- История снапшотов: `{snapshot_path}`",
        "",
        "## Короткий вывод",
        "",
        f"- {overview.health_summary}",
    ]

    if overview.previous_snapshot_date:
        lines.extend(
            [
                "",
                f"## Динамика к предыдущему снимку ({overview.previous_snapshot_date})",
                "",
                f"- Просадки: `{overview.decline_count}` ({_signed_delta(overview.deltas_vs_previous['decline'])})",
                f"- Залеживание: `{overview.overstock_count}` ({_signed_delta(overview.deltas_vs_previous['overstock'])})",
                f"- Мёртвый остаток: `{overview.dead_stock_count}` ({_signed_delta(overview.deltas_vs_previous['dead_stock'])})",
                f"- Рост: `{overview.growth_count}` ({_signed_delta(overview.deltas_vs_previous['growth'])})",
            ]
        )

    lines.extend(
        [
            "",
            "## Деньги и остатки под риском",
            "",
            f"- Единиц товара под риском: `{overview.risk_stock_units}`",
            f"- Прокси-оценка денег под риском: `{_money(overview.risk_value_proxy)}`",
            f"- Покрытие расчёта по SKU: `{overview.risk_value_proxy_coverage}`",
            "- Примечание: денежная оценка считается по фактической выручке на 1 шт. за последние 30 дней или по текущей цене, если она есть.",
        ]
    )

    if overview.priority_rows:
        lines.extend(
            [
                "",
                "## Главные приоритеты на сегодня",
                "",
                "| SKU | Статус | Продажи 30д | Остаток | Что делать |",
                "| --- | --- | --- | --- | --- |",
            ]
        )
        for row in overview.priority_rows[:5]:
            lines.append(
                f"| {_md(row['title'])} | {_md(row['status'])} | {row['sales_30d']} | {row['stock']} | {_md(row['actions'])} |"
            )

    if overview.top_growth:
        lines.extend(
            [
                "",
                "## Что растёт и что не стоит ломать",
                "",
                "| SKU | Продажи 30д | Дельта | Остаток |",
                "| --- | --- | --- | --- |",
            ]
        )
        for row in overview.top_growth[:5]:
            delta_value = f"{_cell(row['sales_delta_pct'])}%" if row["sales_delta_pct"] is not None else ""
            lines.append(
                f"| {_md(row['title'])} | {row['sales_30d']} | {delta_value} | {row['stock']} |"
            )

    if overview.today_actions:
        lines.extend(["", "## Следующее лучшее действие", ""])
        for action in overview.today_actions:
            lines.append(f"- {action}")

    lines.extend(
        [
            "",
            "## Drill-down по группам",
            "",
            "### Категории",
            "",
            "| Группа | SKU | Рисковые SKU | Остаток | Продажи 30д |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for row in overview.top_subject_groups[:5]:
        lines.append(
            f"| {_md(row['label'])} | {row['sku_count']} | {row['risk_count']} | {row['stock']} | {row['sales_30d']} |"
        )
    lines.extend(["", "### Тип сырья", "", "| Группа | SKU | Рисковые SKU | Остаток | Продажи 30д |", "| --- | --- | --- | --- | --- |"])
    for row in overview.top_material_groups[:5]:
        lines.append(
            f"| {_md(row['label'])} | {row['sku_count']} | {row['risk_count']} | {row['stock']} | {row['sales_30d']} |"
        )
    lines.extend(["", "### Фасовка", "", "| Группа | SKU | Рисковые SKU | Остаток | Продажи 30д |", "| --- | --- | --- | --- | --- |"])
    for row in overview.top_pack_groups[:5]:
        lines.append(
            f"| {_md(row['label'])} | {row['sku_count']} | {row['risk_count']} | {row['stock']} | {row['sales_30d']} |"
        )

    lines.extend(
        [
            "",
            "## Артефакты цикла",
            "",
            "- Подробный отчёт: `cabinet_monitor.md`",
            "- Таблица: `cabinet_monitor.xlsx`",
            f"- Визуальный дашборд: `{dashboard_filename}`",
        ]
    )
    return "\n".join(lines).strip() + "\n"


def render_watch_dashboard_html(
    *,
    rows: list[dict[str, Any]],
    today: date,
    snapshot_path: Path,
    top_limit: int = 10,
    summary_filename: str = "cabinet_watch_summary.md",
) -> str:
    overview = build_watch_overview(rows, top_limit=top_limit, snapshot_path=snapshot_path, today=today)
    max_metric = max(
        1,
        overview.decline_count,
        overview.overstock_count,
        overview.dead_stock_count,
        overview.growth_count,
    )
    focus_rows = overview.priority_rows[: min(top_limit, 10)]
    trend_cards = _trend_cards_html(overview)
    sparkline_rows = _sparkline_rows_html(overview.history_points)
    daily_table = _history_table_html(overview.history_points, "Дневная динамика")
    weekly_table = _history_table_html(overview.weekly_history_points, "Недельная динамика")
    monthly_table = _history_table_html(overview.monthly_history_points, "Месячная динамика")
    subject_table = _group_table_html(overview.top_subject_groups, "Категории")
    material_table = _group_table_html(overview.top_material_groups, "Тип сырья")
    pack_table = _group_table_html(overview.top_pack_groups, "Фасовка")
    risk_cards = _risk_cards_html(overview)

    return f"""<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>WB Cabinet Dashboard {today.isoformat()}</title>
  <style>
    :root {{
      --bg: #f4f1ea;
      --card: #fffdf9;
      --ink: #202020;
      --muted: #5b5b5b;
      --line: #ddd4c6;
      --danger: #d4513d;
      --warning: #c28a20;
      --info: #296f91;
      --success: #3d7a54;
      --accent: #1b4d3e;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      padding: 32px;
      background:
        radial-gradient(circle at top left, #fff7e5 0, transparent 30%),
        linear-gradient(180deg, #f7f3ec 0%, var(--bg) 100%);
      color: var(--ink);
      font-family: "Segoe UI", "Helvetica Neue", sans-serif;
    }}
    .shell {{ max-width: 1280px; margin: 0 auto; }}
    .hero {{
      background: linear-gradient(135deg, #1b4d3e, #296f91);
      color: white;
      border-radius: 24px;
      padding: 28px 32px;
      box-shadow: 0 14px 40px rgba(27, 77, 62, 0.18);
    }}
    .hero h1 {{ margin: 0 0 10px; font-size: 34px; }}
    .hero p {{ margin: 0; max-width: 780px; line-height: 1.55; }}
    .meta {{
      display: flex;
      gap: 16px;
      flex-wrap: wrap;
      margin-top: 18px;
      color: rgba(255, 255, 255, 0.92);
    }}
    .meta span {{
      background: rgba(255, 255, 255, 0.14);
      border: 1px solid rgba(255, 255, 255, 0.18);
      border-radius: 999px;
      padding: 8px 12px;
      font-size: 14px;
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 16px;
      margin-top: 22px;
    }}
    .card {{
      background: var(--card);
      border: 1px solid var(--line);
      border-radius: 20px;
      padding: 18px 18px 20px;
      box-shadow: 0 10px 24px rgba(60, 52, 38, 0.07);
    }}
    .metric-label {{ font-size: 14px; color: var(--muted); }}
    .metric-value {{ font-size: 34px; font-weight: 700; margin-top: 6px; }}
    .two-col {{
      display: grid;
      grid-template-columns: 1.05fr 0.95fr;
      gap: 18px;
      margin-top: 18px;
    }}
    .section-title {{
      margin: 0 0 14px;
      font-size: 20px;
    }}
    .bar-list {{ display: grid; gap: 14px; }}
    .bar-row {{ display: grid; gap: 8px; }}
    .bar-head {{
      display: flex;
      justify-content: space-between;
      font-size: 14px;
      color: var(--muted);
    }}
    .track {{
      height: 14px;
      background: #efe8dc;
      border-radius: 999px;
      overflow: hidden;
    }}
    .fill {{ height: 100%; border-radius: 999px; }}
    .fill-danger {{ background: linear-gradient(90deg, #f18a75, var(--danger)); }}
    .fill-warning {{ background: linear-gradient(90deg, #e5bb5f, var(--warning)); }}
    .fill-info {{ background: linear-gradient(90deg, #72b2cf, var(--info)); }}
    .fill-success {{ background: linear-gradient(90deg, #71b084, var(--success)); }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 14px;
    }}
    th, td {{
      padding: 10px 12px;
      text-align: left;
      border-bottom: 1px solid var(--line);
      vertical-align: top;
    }}
    th {{
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.04em;
      color: var(--muted);
    }}
    .footer-links {{
      margin-top: 18px;
      color: var(--muted);
      font-size: 14px;
      display: flex;
      gap: 16px;
      flex-wrap: wrap;
    }}
    .trend-grid {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 12px;
      margin-top: 14px;
    }}
    .trend-card {{
      background: #f7f2e9;
      border: 1px solid var(--line);
      border-radius: 16px;
      padding: 14px;
    }}
    .trend-card strong {{
      display: block;
      font-size: 22px;
      margin-top: 4px;
    }}
    .delta-up {{ color: var(--danger); }}
    .delta-down {{ color: var(--success); }}
    .delta-flat {{ color: var(--muted); }}
    .sparkline {{
      display: flex;
      align-items: flex-end;
      gap: 6px;
      min-height: 92px;
      margin-top: 12px;
    }}
    .spark-item {{
      display: grid;
      justify-items: center;
      gap: 6px;
      width: 100%;
    }}
    .spark-bar {{
      width: 100%;
      border-radius: 8px 8px 0 0;
      min-height: 8px;
      background: linear-gradient(180deg, #71b084, #296f91);
    }}
    .spark-label {{
      font-size: 11px;
      color: var(--muted);
    }}
    .footer-links code {{
      font-size: 13px;
      background: #f0ece4;
      border-radius: 8px;
      padding: 2px 6px;
    }}
    @media (max-width: 1000px) {{
      .grid, .two-col {{ grid-template-columns: 1fr; }}
      body {{ padding: 18px; }}
    }}
  </style>
</head>
<body>
  <div class="shell">
    <section class="hero">
      <h1>Регулярный мониторинг кабинета Wildberries</h1>
      <p>{html.escape(overview.health_summary)}</p>
      <div class="meta">
        <span>Дата: {today.isoformat()}</span>
        <span>Статус: {html.escape(overview.health_status)}</span>
        <span>SKU в мониторинге: {overview.total_sku}</span>
        <span>История: {html.escape(str(snapshot_path))}</span>
      </div>
    </section>

    <section class="grid">
      {_metric_card("Просадки", overview.decline_count)}
      {_metric_card("Залеживание", overview.overstock_count)}
      {_metric_card("Мёртвый остаток", overview.dead_stock_count)}
      {_metric_card("Рост", overview.growth_count)}
    </section>

    <section class="card">
      <h2 class="section-title">Динамика к предыдущему периоду</h2>
      <p class="muted">Сравнение идёт с последним доступным предыдущим снимком истории.</p>
      <div class="trend-grid">
        {trend_cards}
      </div>
    </section>

    <section class="grid">
      {risk_cards}
    </section>

    <section class="two-col">
      <div class="card">
        <h2 class="section-title">Сигналы кабинета</h2>
        <div class="bar-list">
          {_bar_row("Просадки", overview.decline_count, max_metric, "fill-danger")}
          {_bar_row("Залеживание", overview.overstock_count, max_metric, "fill-warning")}
          {_bar_row("Мёртвый остаток", overview.dead_stock_count, max_metric, "fill-info")}
          {_bar_row("Рост", overview.growth_count, max_metric, "fill-success")}
        </div>
      </div>
      <div class="card">
        <h2 class="section-title">Что делать сегодня</h2>
        <table>
          <thead>
            <tr><th>Действие</th></tr>
          </thead>
          <tbody>
            {_actions_rows(overview.today_actions)}
          </tbody>
        </table>
      </div>
    </section>

    <section class="two-col">
      <div class="card">
        <h2 class="section-title">Ключевые проблемные SKU</h2>
        <table>
          <thead>
            <tr><th>SKU</th><th>Статус</th><th>Продажи 30д</th><th>Остаток</th></tr>
          </thead>
          <tbody>
            {_priority_rows(focus_rows)}
          </tbody>
        </table>
      </div>
      <div class="card">
        <h2 class="section-title">Что растёт</h2>
        <table>
          <thead>
            <tr><th>SKU</th><th>Продажи 30д</th><th>Дельта</th><th>Остаток</th></tr>
          </thead>
          <tbody>
            {_growth_rows(overview.top_growth)}
          </tbody>
        </table>
      </div>
    </section>

    <section class="card">
      <h2 class="section-title">История сигналов</h2>
      {sparkline_rows}
    </section>

    <section class="two-col">
      <div class="card">
        {daily_table}
      </div>
      <div class="card">
        {weekly_table}
      </div>
    </section>

    <section class="card">
      {monthly_table}
    </section>

    <section class="two-col">
      <div class="card">
        {subject_table}
      </div>
      <div class="card">
        {material_table}
      </div>
    </section>

    <section class="card">
      {pack_table}
    </section>

    <div class="footer-links">
      <span>Подробный отчёт: <code>cabinet_monitor.md</code></span>
      <span>Таблица: <code>cabinet_monitor.xlsx</code></span>
      <span>Короткая сводка: <code>{html.escape(summary_filename)}</code></span>
      <span>HTML-дашборд: <code>cabinet_dashboard.html</code></span>
    </div>
  </div>
</body>
</html>
"""


def write_watch_summary_pdf(
    *,
    pdf_path: Path,
    today: date,
    rows: list[dict[str, Any]],
    top_limit: int = 10,
) -> None:
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Для PDF-сводки нужен пакет reportlab. Установи его командой: python -m pip install reportlab"
        ) from exc

    font_name = _register_pdf_font(pdfmetrics, TTFont)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "WatchTitle",
        parent=styles["Heading1"],
        fontName=font_name,
        fontSize=18,
        leading=22,
        textColor=colors.HexColor("#1b4d3e"),
        spaceAfter=10,
    )
    body_style = ParagraphStyle(
        "WatchBody",
        parent=styles["BodyText"],
        fontName=font_name,
        fontSize=10,
        leading=14,
        spaceAfter=6,
    )
    small_style = ParagraphStyle(
        "WatchSmall",
        parent=styles["BodyText"],
        fontName=font_name,
        fontSize=9,
        leading=12,
    )

    overview = build_watch_overview(rows, top_limit=top_limit)
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(pdf_path),
        pagesize=A4,
        leftMargin=14 * mm,
        rightMargin=14 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
        title=f"WB Cabinet Watch {today.isoformat()}",
    )

    story = [
        Paragraph("Регулярный мониторинг кабинета Wildberries", title_style),
        Paragraph(f"Дата: {today.isoformat()}", body_style),
        Paragraph(f"Статус: {overview.health_status}. {overview.health_summary}", body_style),
        Spacer(1, 6),
    ]

    metrics_table = Table(
        [
            ["SKU", "Просадки", "Залеживание", "Мёртвый остаток", "Рост"],
            [
                str(overview.total_sku),
                str(overview.decline_count),
                str(overview.overstock_count),
                str(overview.dead_stock_count),
                str(overview.growth_count),
            ],
        ],
        colWidths=[24 * mm, 32 * mm, 35 * mm, 38 * mm, 24 * mm],
    )
    metrics_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1b4d3e")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, -1), font_name),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#d7cfbf")),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("BACKGROUND", (0, 1), (-1, 1), colors.HexColor("#f4f1ea")),
            ]
        )
    )
    story.extend([metrics_table, Spacer(1, 10)])

    if overview.today_actions:
        story.append(Paragraph("Что делать сегодня", body_style))
        for action in overview.today_actions:
            story.append(Paragraph(f"- {action}", small_style))
        story.append(Spacer(1, 8))

    story.append(Paragraph("Ключевые проблемные SKU", body_style))
    story.append(_build_rows_table(overview.priority_rows[:5], font_name, colors))
    story.append(Spacer(1, 8))

    if overview.top_growth:
        story.append(Paragraph("Что растёт и что не стоит ломать", body_style))
        story.append(_build_growth_table(overview.top_growth[:5], font_name, colors))

    doc.build(story)


def build_watch_delivery_caption(summary_markdown: str) -> str:
    lines = [line.strip() for line in summary_markdown.splitlines() if line.strip()]
    bullets = [line[2:] for line in lines if line.startswith("- ")]
    caption_lines = ["Регулярный мониторинг кабинета Wildberries"]
    caption_lines.extend(bullets[:6])
    caption_lines.append("PDF-отчёт приложен.")
    caption = "\n".join(caption_lines)
    if len(caption) > 900:
        caption = caption[:897].rstrip() + "..."
    return caption


def _metric_card(label: str, value: int) -> str:
    return (
        '<div class="card">'
        f'<div class="metric-label">{html.escape(label)}</div>'
        f'<div class="metric-value">{value}</div>'
        "</div>"
    )


def _bar_row(label: str, value: int, max_metric: int, css_class: str) -> str:
    width = 8 if value <= 0 else max(8, round((value / max_metric) * 100))
    return (
        '<div class="bar-row">'
        f'<div class="bar-head"><span>{html.escape(label)}</span><strong>{value}</strong></div>'
        '<div class="track">'
        f'<div class="fill {css_class}" style="width:{width}%"></div>'
        "</div></div>"
    )


def _actions_rows(actions: list[str]) -> str:
    if not actions:
        return "<tr><td>Срочных действий не найдено.</td></tr>"
    return "".join(f"<tr><td>{html.escape(action)}</td></tr>" for action in actions)


def _priority_rows(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "<tr><td colspan='4'>Критичных SKU не найдено.</td></tr>"
    return "".join(
        "<tr>"
        f"<td>{html.escape(str(row['title']))}</td>"
        f"<td>{html.escape(str(row['status']))}</td>"
        f"<td>{row['sales_30d']}</td>"
        f"<td>{row['stock']}</td>"
        "</tr>"
        for row in rows
    )


def _growth_rows(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "<tr><td colspan='4'>Выраженных точек роста не найдено.</td></tr>"
    return "".join(
        "<tr>"
        f"<td>{html.escape(str(row['title']))}</td>"
        f"<td>{row['sales_30d']}</td>"
        f"<td>{_cell(row['sales_delta_pct'])}%</td>"
        f"<td>{row['stock']}</td>"
        "</tr>"
        for row in rows
    )


def _build_rows_table(rows: list[dict[str, Any]], font_name: str, colors) -> object:
    from reportlab.platypus import Table, TableStyle

    mm = 2.834645669
    data = [["SKU", "Статус", "Продажи 30д", "Остаток", "Что делать"]]
    for row in rows:
        data.append(
            [
                str(row["title"]),
                str(row["status"]),
                str(row["sales_30d"]),
                str(row["stock"]),
                str(row["actions"]),
            ]
        )
    table = Table(data, colWidths=[52 * mm, 22 * mm, 18 * mm, 16 * mm, 62 * mm])  # type: ignore[name-defined]
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#296f91")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, -1), font_name),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#d7cfbf")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#fffdf9")),
            ]
        )
    )
    return table


def _build_growth_table(rows: list[dict[str, Any]], font_name: str, colors) -> object:
    from reportlab.platypus import Table, TableStyle

    mm = 2.834645669
    data = [["SKU", "Продажи 30д", "Дельта", "Остаток"]]
    for row in rows:
        delta_value = f"{_cell(row['sales_delta_pct'])}%"
        data.append([str(row["title"]), str(row["sales_30d"]), delta_value, str(row["stock"])])
    table = Table(data, colWidths=[88 * mm, 24 * mm, 24 * mm, 24 * mm])  # type: ignore[name-defined]
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#3d7a54")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, -1), font_name),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#d7cfbf")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#fffdf9")),
            ]
        )
    )
    return table


def _register_pdf_font(pdfmetrics, ttfont_class) -> str:
    candidates = [
        ("AgentCodexArial", os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Fonts", "arial.ttf")),
        ("AgentCodexSegoe", os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Fonts", "segoeui.ttf")),
        ("AgentCodexDejaVu", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    ]
    for font_name, font_path in candidates:
        if not os.path.exists(font_path):
            continue
        if font_name not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(ttfont_class(font_name, font_path))
        return font_name
    raise RuntimeError("Не удалось найти системный шрифт с поддержкой кириллицы для PDF.")


def _md(value: Any) -> str:
    return str(value or "").replace("|", "\\|").replace("\n", " ").strip()


def _cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.1f}"
    return str(value)


def _signed_delta(value: int) -> str:
    if value > 0:
        return f"+{value}"
    return str(value)


def _load_history_points(snapshot_path: Path | None, *, today: date | None) -> list[dict[str, Any]]:
    if snapshot_path is None or not snapshot_path.exists():
        return []

    points: dict[str, dict[str, Any]] = {}
    with snapshot_path.open("r", encoding="utf-8") as fh:
        for raw_line in fh:
            line = raw_line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            snapshot_date = str(payload.get("snapshot_date") or "")
            if not snapshot_date:
                continue
            point = points.setdefault(
                snapshot_date,
                {"snapshot_date": snapshot_date, "decline": 0, "overstock": 0, "dead_stock": 0, "growth": 0, "total_sku": 0},
            )
            status = str(payload.get("status") or "stable")
            if status in {"decline", "overstock", "dead_stock", "growth"}:
                point[status] += 1
            point["total_sku"] += 1

    ordered = [points[key] for key in sorted(points)]
    if today is None:
        return ordered[-8:]
    current_key = today.isoformat()
    if current_key not in points:
        ordered.append(
            {
                "snapshot_date": current_key,
                "decline": 0,
                "overstock": 0,
                "dead_stock": 0,
                "growth": 0,
                "total_sku": 0,
            }
        )
    return ordered[-8:]


def _trend_cards_html(overview: CabinetWatchOverview) -> str:
    cards = [
        ("Просадки", overview.decline_count, overview.deltas_vs_previous["decline"]),
        ("Залеживание", overview.overstock_count, overview.deltas_vs_previous["overstock"]),
        ("Мёртвый остаток", overview.dead_stock_count, overview.deltas_vs_previous["dead_stock"]),
        ("Рост", overview.growth_count, overview.deltas_vs_previous["growth"]),
    ]
    return "".join(
        f'<div class="trend-card"><div class="metric-label">{html.escape(label)}</div><strong>{value}</strong><div class="{_delta_css(delta)}">{html.escape(_delta_label(delta, good_when_down=label != "Рост"))}</div></div>'
        for label, value, delta in cards
    )


def _sparkline_rows_html(history_points: list[dict[str, Any]]) -> str:
    if not history_points:
        return "<p class='muted'>Истории пока недостаточно для динамики.</p>"
    metrics = [
        ("Просадки", "decline"),
        ("Залеживание", "overstock"),
        ("Мёртвый остаток", "dead_stock"),
        ("Рост", "growth"),
    ]
    sections: list[str] = []
    for title, key in metrics:
        max_value = max(1, max(int(point.get(key, 0)) for point in history_points))
        bars = []
        for point in history_points:
            value = int(point.get(key, 0))
            height = max(8, round((value / max_value) * 72)) if value > 0 else 8
            bars.append(
                "<div class='spark-item'>"
                f"<div class='spark-bar' style='height:{height}px'></div>"
                f"<div>{value}</div>"
                f"<div class='spark-label'>{html.escape(str(point['snapshot_date'])[5:])}</div>"
                "</div>"
            )
        sections.append(f"<div class='card'><h3>{html.escape(title)}</h3><div class='sparkline'>{''.join(bars)}</div></div>")
    return "<div class='trend-grid'>" + "".join(sections) + "</div>"


def _history_table_html(history_points: list[dict[str, Any]], title: str) -> str:
    if not history_points:
        return f"<h2 class='section-title'>{html.escape(title)}</h2><p class='muted'>Истории пока недостаточно.</p>"
    rows = []
    for point in history_points[-6:]:
        rows.append(
            "<tr>"
            f"<td>{html.escape(str(point['snapshot_date']))}</td>"
            f"<td>{int(point.get('decline', 0))}</td>"
            f"<td>{int(point.get('overstock', 0))}</td>"
            f"<td>{int(point.get('dead_stock', 0))}</td>"
            f"<td>{int(point.get('growth', 0))}</td>"
            "</tr>"
        )
    return (
        f"<h2 class='section-title'>{html.escape(title)}</h2>"
        "<table><thead><tr><th>Период</th><th>Просадки</th><th>Залеживание</th><th>Мёртвый остаток</th><th>Рост</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
    )


def _group_table_html(groups: list[dict[str, Any]], title: str) -> str:
    if not groups:
        return f"<h2 class='section-title'>{html.escape(title)}</h2><p class='muted'>Данных пока недостаточно.</p>"
    rows = []
    for row in groups[:8]:
        rows.append(
            "<tr>"
            f"<td>{html.escape(str(row['label']))}</td>"
            f"<td>{row['sku_count']}</td>"
            f"<td>{row['risk_count']}</td>"
            f"<td>{row['stock']}</td>"
            f"<td>{row['sales_30d']}</td>"
            "</tr>"
        )
    return (
        f"<h2 class='section-title'>{html.escape(title)}</h2>"
        "<table><thead><tr><th>Группа</th><th>SKU</th><th>Рисковые SKU</th><th>Остаток</th><th>Продажи 30д</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
    )


def _risk_cards_html(overview: CabinetWatchOverview) -> str:
    cards = [
        _metric_card("Единиц под риском", overview.risk_stock_units),
        _metric_card("Прокси денег под риском", _money(overview.risk_value_proxy)),
        _metric_card("SKU с денежной оценкой", overview.risk_value_proxy_coverage),
        _metric_card("SKU в фокусе", len(overview.priority_rows)),
    ]
    return "".join(cards)


def _delta_css(delta: int) -> str:
    if delta > 0:
        return "delta-up"
    if delta < 0:
        return "delta-down"
    return "delta-flat"


def _delta_label(delta: int, *, good_when_down: bool) -> str:
    if delta == 0:
        return "без изменений"
    direction = "лучше" if (delta < 0 and good_when_down) or (delta > 0 and not good_when_down) else "хуже"
    return f"{_signed_delta(delta)} к прошлому снимку, {direction}"


def _risk_metrics(rows: list[dict[str, Any]]) -> tuple[int, float, int]:
    risk_stock_units = 0
    risk_value_proxy = 0.0
    covered_rows = 0
    for row in rows:
        if row.get("status") not in {"overstock", "dead_stock"}:
            continue
        stock = int(row.get("stock") or 0)
        risk_stock_units += stock
        unit_price = None
        discounted_price = row.get("discounted_price")
        if discounted_price not in {None, ""}:
            try:
                unit_price = float(discounted_price)
            except (TypeError, ValueError):
                unit_price = None
        if unit_price is None:
            sales_30d = int(row.get("sales_30d") or 0)
            revenue_30d = float(row.get("revenue_30d") or 0.0)
            if sales_30d > 0 and revenue_30d > 0:
                unit_price = revenue_30d / sales_30d
        if unit_price is not None and stock > 0:
            risk_value_proxy += unit_price * stock
            covered_rows += 1
    return risk_stock_units, round(risk_value_proxy, 2), covered_rows


def _group_rows(rows: list[dict[str, Any]], label_fn, limit: int = 8) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for row in rows:
        label = label_fn(row)
        item = grouped.setdefault(
            label,
            {"label": label, "sku_count": 0, "risk_count": 0, "stock": 0, "sales_30d": 0, "priority_score": 0},
        )
        item["sku_count"] += 1
        item["stock"] += int(row.get("stock") or 0)
        item["sales_30d"] += int(row.get("sales_30d") or 0)
        item["priority_score"] += int(row.get("priority_score") or 0)
        if row.get("status") in {"decline", "overstock", "dead_stock"}:
            item["risk_count"] += 1
    ordered = sorted(
        grouped.values(),
        key=lambda item: (-item["risk_count"], -item["priority_score"], -item["stock"], item["label"]),
    )
    return ordered[:limit]


def _subject_group_label(row: dict[str, Any]) -> str:
    return str(row.get("subject_name") or "Без категории")


def _material_group_label(row: dict[str, Any]) -> str:
    title = str(row.get("title") or "").lower()
    rules = [
        ("масла и баттеры", ("масло", "баттер", "jojoba", "макадам", "манго", "амлы")),
        ("экстракты", ("экстракт", "extract")),
        ("протеины и аминокислоты", ("протеин", "protein", "аминокис", "коллаген", "кератин")),
        ("ПАВы и база", ("бетаин", "glucoside", "глюкозид", "шампун", "пав", "sarcosinate", "taurate")),
        ("эмульгаторы и солюбилизаторы", ("эмульгатор", "полисорбат", "лецигель", "lecigel")),
        ("отдушки", ("отдушка",)),
        ("готовые продукты", ("шампунь", "бустер", "маска", "кондиционер")),
    ]
    for label, keywords in rules:
        if any(keyword in title for keyword in keywords):
            return label
    return "прочее сырьё"


def _pack_group_label(row: dict[str, Any]) -> str:
    title = str(row.get("title") or "").lower()
    match = re.search(r"(\d+(?:[.,]\d+)?)\s*(г|мл|kg|кг|л)\b", title)
    if not match:
        return "фасовка не распознана"
    value = float(match.group(1).replace(",", "."))
    unit = match.group(2)
    if unit in {"kg", "кг"}:
        value *= 1000
        unit = "г"
    if unit == "л":
        value *= 1000
        unit = "мл"
    if value <= 10:
        return f"до 10 {unit}"
    if value <= 30:
        return f"11-30 {unit}"
    if value <= 100:
        return f"31-100 {unit}"
    if value <= 250:
        return f"101-250 {unit}"
    if value <= 500:
        return f"251-500 {unit}"
    return f"500+ {unit}"


def _aggregate_history_points(history_points: list[dict[str, Any]], *, period: str) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for point in history_points:
        snapshot_date = str(point.get("snapshot_date") or "")
        if not snapshot_date:
            continue
        if period == "week":
            year, week, _ = date.fromisoformat(snapshot_date).isocalendar()
            key = f"{year}-W{week:02d}"
        else:
            key = snapshot_date[:7]
        bucket = grouped.setdefault(
            key,
            {"snapshot_date": key, "decline": 0, "overstock": 0, "dead_stock": 0, "growth": 0},
        )
        for metric in ("decline", "overstock", "dead_stock", "growth"):
            bucket[metric] += int(point.get(metric, 0))
    return [grouped[key] for key in sorted(grouped)][-6:]


def _money(value: float) -> str:
    return f"{value:,.0f} ₽".replace(",", " ")
