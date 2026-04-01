from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile

from .api import WildberriesApiClient

MOSCOW_WAREHOUSE_KEYWORDS = (
    "коледино",
    "электросталь",
    "тула",
    "белые столбы",
    "внуково",
    "истра",
    "москва",
)
KRASNODAR_WAREHOUSE_KEYWORDS = ("краснодар",)
LOCAL_WAREHOUSE_KEYWORDS = ("новосибирск",)
SURFACTANT_KEYWORDS = (
    "глюкозид",
    "glucoside",
    "бетаин",
    "betaine",
    "sarcosinate",
    "taurate",
    "glutamate",
    "isethionate",
    "sulfate",
    "sulfoacetate",
    "cocamidopropyl",
    "лаурил",
    "лаурет",
    "пав",
)
PACKAGING_PLASTIC_KEYWORDS = ("пластик", "plastic", "pet", "pe", "pp", "hdpe", "пэт")
PACKAGING_GLASS_KEYWORDS = ("стекл", "glass")


@dataclass(slots=True)
class SupplyPlanConfig:
    date_from: str
    output_root: Path
    turnover_days_limit: int = 90
    min_sales_units: int = 5
    min_sale_days: int = 5
    min_sale_weeks: int = 4
    max_single_week_share: float = 0.65


@dataclass(slots=True)
class SupplyPlanResult:
    output_dir: Path
    markdown_path: Path
    xlsx_path: Path
    row_count: int
    manual_tnved_count: int
    moscow_share: float
    krasnodar_share: float
    assumptions: list[str]


def build_supply_plan(
    client: WildberriesApiClient,
    config: SupplyPlanConfig,
    today: date | None = None,
) -> SupplyPlanResult:
    today = today or date.today()
    date_from = date.fromisoformat(config.date_from)
    period_days = max(1, (today - date_from).days + 1)
    period_weeks = max(1, math.ceil(period_days / 7))

    sales = client.get_supplier_sales(config.date_from)
    orders = client.get_supplier_orders(config.date_from)
    stocks = client.get_supplier_stocks(config.date_from)

    sales_stats = _build_sales_stats(sales)
    order_stats, cluster_orders = _build_order_stats(orders)

    total_cluster_orders = cluster_orders["moscow"] + cluster_orders["krasnodar"]
    if total_cluster_orders:
        default_moscow_share = cluster_orders["moscow"] / total_cluster_orders
    else:
        default_moscow_share = 0.5
    default_krasnodar_share = 1 - default_moscow_share

    cards_by_nm_id, cards_by_vendor_code = _fetch_all_cards(client)
    stock_stats = _build_stock_stats(
        marketplace_stocks=stocks,
        seller_inventory=_fetch_seller_inventory(client, cards_by_nm_id, nm_ids=set(sales_stats)),
    )
    hs_codes_cache: dict[int, list[str]] = {}
    rows: list[dict[str, Any]] = []

    for nm_id, sale_item in sales_stats.items():
        net_sales_units = sale_item["net_sales_units"]
        sale_days = len(sale_item["sale_days"])
        sale_weeks = len(sale_item["sale_weeks"])
        if net_sales_units < config.min_sales_units:
            continue
        if sale_days < config.min_sale_days or sale_weeks < config.min_sale_weeks:
            continue
        max_week_share = _safe_div(max(sale_item["sale_weeks"].values(), default=0), net_sales_units)
        if max_week_share > config.max_single_week_share:
            continue

        stock_item = stock_stats.get(nm_id, {})
        total_stock = int(stock_item.get("total_stock", 0))
        local_stock = int(stock_item.get("local_stock", 0))
        wb_stock = int(stock_item.get("wb_stock", 0))
        total_in_way_to_client = int(stock_item.get("in_way_to_client", 0))
        total_in_way_from_client = int(stock_item.get("in_way_from_client", 0))
        if total_stock <= 0:
            continue
        avg_daily_sales = net_sales_units / period_days
        if avg_daily_sales <= 0:
            continue
        turnover_days = total_stock / avg_daily_sales if total_stock > 0 else 0
        if turnover_days > config.turnover_days_limit:
            continue

        ship_candidate = local_stock // 2
        target_wb_stock = math.floor(avg_daily_sales * config.turnover_days_limit)
        max_safe_ship = max(0, target_wb_stock - wb_stock)
        ship_total = min(ship_candidate, max_safe_ship)

        card = _get_card(cards_by_nm_id, cards_by_vendor_code, nm_id, sale_item["vendor_code"])
        if not card:
            continue
        if not _has_required_card_content(card):
            continue

        subject_id = int(card.get("subjectID") or 0)
        hs_codes = hs_codes_cache.get(subject_id)
        if hs_codes is None:
            hs_codes = _fetch_hs_codes(client, subject_id)
            hs_codes_cache[subject_id] = hs_codes

        tnved_code, tnved_status, tnved_note = _suggest_tnved(card, hs_codes)

        item_orders = order_stats.get(nm_id, {})
        moscow_orders = int(item_orders.get("moscow_orders", 0))
        krasnodar_orders = int(item_orders.get("krasnodar_orders", 0))
        target_orders = moscow_orders + krasnodar_orders
        if target_orders:
            moscow_share = moscow_orders / target_orders
            share_note = "По заказам позиции"
        else:
            moscow_share = default_moscow_share
            share_note = "По общей доле спроса целевых складов"
        krasnodar_share = 1 - moscow_share

        moscow_qty = int(round(ship_total * moscow_share))
        moscow_qty = min(max(moscow_qty, 0), ship_total)
        krasnodar_qty = ship_total - moscow_qty

        rows.append(
            {
                "nm_id": nm_id,
                "vendor_code": sale_item["vendor_code"],
                "barcode": sale_item["barcode"]
                or str(stock_item.get("barcode") or "")
                or _extract_primary_barcode(card),
                "title": str(card.get("title") or sale_item["title"] or ""),
                "subject_name": str(card.get("subjectName") or sale_item["subject"] or ""),
                "brand": str(card.get("brand") or sale_item["brand"] or ""),
                "sales_units_90d": net_sales_units,
                "sale_days_90d": sale_days,
                "sale_weeks_90d": sale_weeks,
                "avg_daily_sales": round(avg_daily_sales, 3),
                "turnover_days": round(turnover_days, 1),
                "total_stock": total_stock,
                "local_stock_estimated": local_stock,
                "wb_stock_estimated": wb_stock,
                "in_way_to_client": total_in_way_to_client,
                "in_way_from_client": total_in_way_from_client,
                "ship_total": ship_total,
                "ship_moscow": moscow_qty,
                "ship_krasnodar": krasnodar_qty,
                "moscow_share": round(moscow_share * 100, 1),
                "krasnodar_share": round(krasnodar_share * 100, 1),
                "tnved": tnved_code,
                "tnved_status": tnved_status,
                "tnved_note": tnved_note,
                "share_note": share_note,
                "description": _clean_multiline(str(card.get("description") or "")),
            }
        )

    rows.sort(key=lambda row: (-row["sales_units_90d"], row["turnover_days"], row["title"]))
    stamp = today.isoformat()
    output_dir = config.output_root / f"supply_plan_{stamp}"
    output_dir.mkdir(parents=True, exist_ok=True)
    markdown_path = output_dir / "supply_plan.md"
    xlsx_path = output_dir / "supply_plan.xlsx"

    assumptions = [
        f"Период анализа: с {config.date_from} по {today.isoformat()} ({period_days} дней).",
        f"Предел оборачиваемости: не более {config.turnover_days_limit} дней.",
        (
            "Регулярными считаются позиции с минимум "
            f"{config.min_sales_units} чистыми продажами, {config.min_sale_days} днями продаж "
            f"и {config.min_sale_weeks} активными неделями за период."
        ),
        (
            "Фактический остаток для поставки берётся из `Управления остатками` продавца "
            "(seller warehouse inventory API WB)."
        ),
        (
            "Дополнительно в отчёт вынесены поля движения из statistics API (`inWayToClient`, "
            "`inWayFromClient`) как справочная информация."
        ),
        (
            "В модель `кандидаты на поставку` попадают все позиции с остатком, регулярными продажами и "
            f"оборачиваемостью не более {config.turnover_days_limit} дней. Если по правилу деления пополам "
            "рекомендуемая отгрузка округляется в 0, позиция всё равно остаётся в списке кандидатов."
        ),
        (
            "Рекомендованная отгрузка ограничена двумя условиями одновременно: "
            "не больше половины локального остатка и не больше безопасного пополнения WB до 90 дней спроса."
        ),
        (
            "ТН ВЭД определяется по каждой позиции отдельно на основе названия, описания, subject карточки "
            "и допустимых кодов WB; при недостаточной уверенности позиция помечается на ручную проверку."
        ),
        (
            "Базовые источники для проверки ТН ВЭД: WB Content API, Alta.ru и TKS.ru. "
            "Для спорных случаев нужна ручная верификация."
        ),
    ]
    markdown_path.write_text(
        _render_markdown(
            rows=rows,
            assumptions=assumptions,
            config=config,
            period_days=period_days,
            period_weeks=period_weeks,
            default_moscow_share=default_moscow_share,
            default_krasnodar_share=default_krasnodar_share,
        ),
        encoding="utf-8",
    )
    _write_xlsx(
        xlsx_path,
        headers=[
            "nmID",
            "Баркод",
            "Артикул",
            "Товар",
            "Предмет",
            "Бренд",
            "Продажи 90д",
            "Дни продаж 90д",
            "Активные недели",
            "Средние продажи/день",
            "Оборачиваемость, дней",
            "Остаток факт",
            "Остаток наш склад",
            "Остаток WB сейчас",
            "В пути к клиенту",
            "В пути от клиента",
            "К отгрузке всего",
            "Москва",
            "Краснодар",
            "Доля Москва, %",
            "Доля Краснодар, %",
            "ТН ВЭД",
            "Статус ТН ВЭД",
            "Комментарий по ТН ВЭД",
            "Комментарий по распределению",
            "Описание",
        ],
        rows=[
            [
                row["nm_id"],
                row["barcode"],
                row["vendor_code"],
                row["title"],
                row["subject_name"],
                row["brand"],
                row["sales_units_90d"],
                row["sale_days_90d"],
                row["sale_weeks_90d"],
                row["avg_daily_sales"],
                row["turnover_days"],
                row["total_stock"],
                row["local_stock_estimated"],
                row["wb_stock_estimated"],
                row["in_way_to_client"],
                row["in_way_from_client"],
                row["ship_total"],
                row["ship_moscow"],
                row["ship_krasnodar"],
                row["moscow_share"],
                row["krasnodar_share"],
                row["tnved"],
                row["tnved_status"],
                row["tnved_note"],
                row["share_note"],
                row["description"],
            ]
            for row in rows
        ],
    )

    manual_count = sum(1 for row in rows if row["tnved_status"] != "auto")
    return SupplyPlanResult(
        output_dir=output_dir,
        markdown_path=markdown_path,
        xlsx_path=xlsx_path,
        row_count=len(rows),
        manual_tnved_count=manual_count,
        moscow_share=default_moscow_share,
        krasnodar_share=default_krasnodar_share,
        assumptions=assumptions,
    )


def _build_sales_stats(sales: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    stats: dict[int, dict[str, Any]] = {}
    for row in sales:
        nm_id = int(row.get("nmId") or 0)
        if not nm_id:
            continue
        item = stats.setdefault(
            nm_id,
            {
                "vendor_code": str(row.get("supplierArticle") or ""),
                "barcode": str(row.get("barcode") or ""),
                "title": "",
                "brand": str(row.get("brand") or ""),
                "subject": str(row.get("subject") or ""),
                "category": str(row.get("category") or ""),
                "sale_days": set(),
                "sale_weeks": Counter(),
                "net_sales_units": 0,
                "gross_sales_units": 0,
                "returns_units": 0,
            },
        )
        sale_id = str(row.get("saleID") or "")
        sale_day = _parse_dt(str(row.get("date") or ""))
        if sale_id.startswith("S"):
            item["net_sales_units"] += 1
            item["gross_sales_units"] += 1
            if sale_day is not None:
                item["sale_days"].add(sale_day.date())
                item["sale_weeks"][_week_key(sale_day.date())] += 1
        elif sale_id.startswith("R"):
            item["returns_units"] += 1
            item["net_sales_units"] = max(0, item["net_sales_units"] - 1)
    return stats


def _build_order_stats(
    orders: list[dict[str, Any]]
) -> tuple[dict[int, dict[str, int]], Counter[str]]:
    stats: dict[int, dict[str, int]] = defaultdict(lambda: {"moscow_orders": 0, "krasnodar_orders": 0})
    cluster_orders: Counter[str] = Counter()
    for row in orders:
        if row.get("isCancel"):
            continue
        nm_id = int(row.get("nmId") or 0)
        if not nm_id:
            continue
        cluster = _classify_target_cluster(str(row.get("warehouseName") or ""))
        if not cluster:
            continue
        key = f"{cluster}_orders"
        stats[nm_id][key] += 1
        cluster_orders[cluster] += 1
    return dict(stats), cluster_orders


def _fetch_seller_inventory(
    client: WildberriesApiClient,
    cards_by_nm_id: dict[int, dict[str, Any]],
    nm_ids: set[int] | None = None,
    chunk_size: int = 500,
) -> dict[int, dict[str, Any]]:
    inventory: dict[int, dict[str, Any]] = defaultdict(lambda: {"amount": 0, "barcode": ""})
    sku_to_nm: dict[str, int] = {}

    for nm_id, card in cards_by_nm_id.items():
        if nm_ids is not None and nm_id not in nm_ids:
            continue
        for size in card.get("sizes") or []:
            for sku in size.get("skus") or []:
                sku_str = str(sku or "").strip()
                if sku_str:
                    sku_to_nm[sku_str] = nm_id

    if not sku_to_nm:
        return {}

    warehouses = client.get_seller_warehouses()
    warehouse_ids = [int(item.get("id") or 0) for item in warehouses if int(item.get("id") or 0)]
    all_skus = list(sku_to_nm.keys())

    for warehouse_id in warehouse_ids:
        for sku_chunk in _chunked(all_skus, chunk_size):
            response = client.get_warehouse_inventory(warehouse_id, skus=sku_chunk)
            for row in response.get("stocks") or []:
                sku = str(row.get("sku") or "").strip()
                nm_id = sku_to_nm.get(sku)
                if not nm_id:
                    continue
                inventory[nm_id]["amount"] += int(row.get("amount") or 0)
                if not inventory[nm_id]["barcode"]:
                    inventory[nm_id]["barcode"] = sku

    return dict(inventory)


def _build_stock_stats(
    marketplace_stocks: list[dict[str, Any]],
    seller_inventory: dict[int, dict[str, Any]],
) -> dict[int, dict[str, Any]]:
    stats: dict[int, dict[str, Any]] = defaultdict(
        lambda: {
            "total_stock": 0,
            "local_stock": 0,
            "wb_stock": 0,
            "in_way_to_client": 0,
            "in_way_from_client": 0,
            "barcode": "",
        }
    )
    for nm_id, item in seller_inventory.items():
        stats[nm_id]["total_stock"] += int(item.get("amount", 0))
        stats[nm_id]["local_stock"] += int(item.get("amount", 0))
        if item.get("barcode"):
            stats[nm_id]["barcode"] = str(item.get("barcode") or "")

    for row in marketplace_stocks:
        nm_id = int(row.get("nmId") or 0)
        if not nm_id:
            continue
        quantity = int(row.get("quantity") or 0)
        in_way_to_client = int(row.get("inWayToClient") or 0)
        in_way_from_client = int(row.get("inWayFromClient") or 0)
        if quantity <= 0 and in_way_to_client <= 0 and in_way_from_client <= 0:
            continue
        stats[nm_id]["wb_stock"] += quantity
        stats[nm_id]["in_way_to_client"] += in_way_to_client
        stats[nm_id]["in_way_from_client"] += in_way_from_client
        if not stats[nm_id]["barcode"] and row.get("barcode"):
            stats[nm_id]["barcode"] = str(row.get("barcode") or "")
    return dict(stats)


def _fetch_all_cards(
    client: WildberriesApiClient,
    limit: int = 100,
) -> tuple[dict[int, dict[str, Any]], dict[str, dict[str, Any]]]:
    cards_by_nm_id: dict[int, dict[str, Any]] = {}
    cards_by_vendor_code: dict[str, dict[str, Any]] = {}
    cursor_nm_id: int | None = None
    cursor_updated_at: str | None = None
    seen_cursors: set[tuple[int | None, str | None]] = set()

    while True:
        response = client.get_content_cards(
            limit=limit,
            with_photo=-1,
            cursor_nm_id=cursor_nm_id,
            cursor_updated_at=cursor_updated_at,
        )
        cards = response.get("cards") or []
        if not cards:
            break
        for card in cards:
            nm_id = int(card.get("nmID") or 0)
            vendor_code = str(card.get("vendorCode") or "").strip().lower()
            if nm_id:
                cards_by_nm_id[nm_id] = card
            if vendor_code:
                cards_by_vendor_code[vendor_code] = card

        cursor = response.get("cursor") or {}
        next_cursor = (cursor.get("nmID"), cursor.get("updatedAt"))
        if len(cards) < limit or next_cursor in seen_cursors:
            break
        seen_cursors.add(next_cursor)
        cursor_nm_id = cursor.get("nmID")
        cursor_updated_at = cursor.get("updatedAt")

    return cards_by_nm_id, cards_by_vendor_code


def _get_card(
    cards_by_nm_id: dict[int, dict[str, Any]],
    cards_by_vendor_code: dict[str, dict[str, Any]],
    nm_id: int,
    vendor_code: str,
) -> dict[str, Any] | None:
    card = cards_by_nm_id.get(nm_id)
    if card:
        return card
    return cards_by_vendor_code.get(vendor_code.strip().lower())


def _fetch_hs_codes(client: WildberriesApiClient, subject_id: int) -> list[str]:
    if not subject_id:
        return []
    response = client.get_hs_codes(subject_id)
    return [str(row.get("tnved") or "") for row in response.get("data") or [] if row.get("tnved")]


def _has_required_card_content(card: dict[str, Any]) -> bool:
    description = str(card.get("description") or "").strip()
    photos = card.get("photos") or []
    return bool(description and photos)


def _suggest_tnved(card: dict[str, Any], hs_codes: list[str]) -> tuple[str, str, str]:
    allowed_codes = [code for code in hs_codes if code]
    title = str(card.get("title") or "")
    description = str(card.get("description") or "")
    subject_name = str(card.get("subjectName") or "")
    title_lower = _normalize(title)
    combined = _normalize(" ".join([title, description, subject_name, _characteristics_text(card)]))

    if len(allowed_codes) == 1:
        return allowed_codes[0], "auto", "Единственный допустимый код по WB для этого subject."

    subject_lower = _normalize(subject_name)

    if "шампун" in subject_lower or ("шампун" in title_lower and "косметическ актив" not in subject_lower):
        code = _pick_allowed_code(allowed_codes, "3305100000", "3305")
        if code:
            return code, "auto", "Шампунь: проверка по subject и типовой группе 3305."

    if "маск" in subject_lower or "крем" in subject_lower:
        code = _pick_allowed_code(allowed_codes, "3304990000", "3304")
        if code:
            return code, "auto", "Средство по уходу за кожей: типовая группа 3304."

    if "свеч" in subject_lower:
        code = _pick_allowed_code(allowed_codes, "3406000000", "3406")
        if code:
            return code, "auto", "Свечи: типовая группа 3406."

    if "отдуш" in subject_lower:
        code = _pick_allowed_code(allowed_codes, "3302909000", "3302")
        if code:
            return code, "manual_review", "Отдушка: выбран базовый код группы 3302, нужна ручная проверка состава."

    if "флакон" in subject_lower or "дозатор" in subject_lower:
        if any(keyword in combined for keyword in PACKAGING_GLASS_KEYWORDS):
            code = _pick_allowed_code(allowed_codes, prefix="7010")
            if code:
                return code, "manual_review", "Упаковка из стекла: код подобран по материалу, нужна ручная проверка."
        if any(keyword in combined for keyword in PACKAGING_PLASTIC_KEYWORDS):
            code = _pick_allowed_code(allowed_codes, prefix="3923", fallback_prefix="3926")
            if code:
                return code, "manual_review", "Упаковка из пластика: код подобран по материалу, нужна ручная проверка."
        return "", "manual_review", "Для упаковки не хватает точного материала или конструкции."

    if "косметическ актив" in subject_lower:
        if any(token in title_lower for token in ("шампун", "маск", "крем", "сыворот", "лосьон", "тоник")):
            return (
                "",
                "manual_review",
                "В названии есть готовый косметический продукт, но subject карточки = косметический актив; нужна ручная проверка.",
            )
        if any(keyword in combined for keyword in SURFACTANT_KEYWORDS):
            code = _pick_allowed_code(allowed_codes, prefix="3402")
            if code:
                return code, "manual_review", "Похоже на ПАВ/моющее сырьё: код группы 3402 требует ручной проверки."
        return "", "manual_review", "Косметический актив: без точного состава и статуса товара код нельзя ставить автоматически."

    return "", "manual_review", "Не найден надёжный сценарий автоопределения ТН ВЭД."


def _pick_allowed_code(
    allowed_codes: list[str],
    exact_code: str | None = None,
    prefix: str | None = None,
    fallback_prefix: str | None = None,
) -> str:
    if exact_code and exact_code in allowed_codes:
        return exact_code
    if prefix:
        for code in allowed_codes:
            if code.startswith(prefix):
                return code
    if fallback_prefix:
        for code in allowed_codes:
            if code.startswith(fallback_prefix):
                return code
    return ""


def _chunked(values: list[str], size: int) -> list[list[str]]:
    return [values[index : index + size] for index in range(0, len(values), size)]


def _characteristics_text(card: dict[str, Any]) -> str:
    values: list[str] = []
    for characteristic in card.get("characteristics") or []:
        name = str(characteristic.get("name") or "")
        values_list = characteristic.get("value") or []
        if isinstance(values_list, list):
            rendered = ", ".join(str(item) for item in values_list if item is not None)
        else:
            rendered = str(values_list)
        if name or rendered:
            values.append(f"{name}: {rendered}")
    return " | ".join(values)


def _extract_primary_barcode(card: dict[str, Any]) -> str:
    for size in card.get("sizes") or []:
        skus = size.get("skus") or []
        if isinstance(skus, list):
            for sku in skus:
                if sku:
                    return str(sku)
        elif skus:
            return str(skus)
    return ""


def _render_markdown(
    rows: list[dict[str, Any]],
    assumptions: list[str],
    config: SupplyPlanConfig,
    period_days: int,
    period_weeks: int,
    default_moscow_share: float,
    default_krasnodar_share: float,
) -> str:
    lines = [
        "# План поставки WB",
        "",
        f"- Период анализа: `{config.date_from}` и далее `{period_days}` дней (~`{period_weeks}` недель).",
        f"- Предел оборачиваемости: `{config.turnover_days_limit}` дней.",
        f"- Базовое распределение спроса целевых складов: Москва `{default_moscow_share * 100:.1f}%`, Краснодар `{default_krasnodar_share * 100:.1f}%`.",
        f"- Кандидатов к поставке после фильтров: `{len(rows)}`.",
        "",
        "## Допущения",
        "",
    ]
    for assumption in assumptions:
        lines.append(f"- {assumption}")

    lines.extend(
        [
            "",
            "## Таблица",
            "",
            "| nmID | Баркод | Артикул | Товар | Предмет | Продажи 90д | Дни продаж | Активные недели | Оборачиваемость, дней | Локальный остаток | На WB сейчас | В пути к клиенту | В пути от клиента | К отгрузке | Москва | Краснодар | ТН ВЭД | Статус ТН ВЭД | Комментарий |",
            "| --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- | --- |",
        ]
    )
    for row in rows:
        comment = " / ".join(part for part in [row["tnved_note"], row["share_note"]] if part)
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row["nm_id"]),
                    _md(row["barcode"]),
                    _md(row["vendor_code"]),
                    _md(row["title"]),
                    _md(row["subject_name"]),
                    str(row["sales_units_90d"]),
                    str(row["sale_days_90d"]),
                    str(row["sale_weeks_90d"]),
                    str(row["turnover_days"]),
                    str(row["local_stock_estimated"]),
                    str(row["wb_stock_estimated"]),
                    str(row["in_way_to_client"]),
                    str(row["in_way_from_client"]),
                    str(row["ship_total"]),
                    str(row["ship_moscow"]),
                    str(row["ship_krasnodar"]),
                    _md(row["tnved"]),
                    _md(row["tnved_status"]),
                    _md(comment),
                ]
            )
            + " |"
        )

    manual_rows = [row for row in rows if row["tnved_status"] != "auto"]
    if manual_rows:
        lines.extend(
            [
                "",
                "## Позиции с ручной проверкой ТН ВЭД",
                "",
            ]
        )
        for row in manual_rows:
            lines.append(
                f"- `{row['nm_id']}` / `{row['vendor_code']}` / {row['title']} — {row['tnved_note']}"
            )

    return "\n".join(lines).strip() + "\n"


def _write_xlsx(path: Path, headers: list[str], rows: list[list[Any]]) -> None:
    column_widths = [len(header) for header in headers]
    for row in rows:
        for index, value in enumerate(row):
            rendered = "" if value is None else str(value)
            column_widths[index] = min(80, max(column_widths[index], len(rendered) + 2))

    sheet_rows: list[str] = []
    sheet_rows.append(_render_sheet_row(1, headers, style_id=1))
    for index, row in enumerate(rows, start=2):
        sheet_rows.append(_render_sheet_row(index, row, style_id=0))

    cols_xml = "".join(
        f'<col min="{idx}" max="{idx}" width="{width}" customWidth="1"/>'
        for idx, width in enumerate(column_widths, start=1)
    )
    sheet_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f"<cols>{cols_xml}</cols>"
        f"<sheetData>{''.join(sheet_rows)}</sheetData>"
        "</worksheet>"
    )

    with ZipFile(path, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr(
            "[Content_Types].xml",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
  <Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
  <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
  <Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
</Types>""",
        )
        archive.writestr(
            "_rels/.rels",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>""",
        )
        archive.writestr(
            "docProps/app.xml",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"
 xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">
  <Application>Agent_Codex</Application>
</Properties>""",
        )
        archive.writestr(
            "docProps/core.xml",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
 xmlns:dc="http://purl.org/dc/elements/1.1/"
 xmlns:dcterms="http://purl.org/dc/terms/"
 xmlns:dcmitype="http://purl.org/dc/dcmitype/"
 xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <dc:creator>Agent_Codex</dc:creator>
  <cp:lastModifiedBy>Agent_Codex</cp:lastModifiedBy>
</cp:coreProperties>""",
        )
        archive.writestr(
            "xl/workbook.xml",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
 xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets>
    <sheet name="Поставка WB" sheetId="1" r:id="rId1"/>
  </sheets>
</workbook>""",
        )
        archive.writestr(
            "xl/_rels/workbook.xml.rels",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>""",
        )
        archive.writestr(
            "xl/styles.xml",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <fonts count="2">
    <font><sz val="11"/><name val="Calibri"/></font>
    <font><b/><sz val="11"/><name val="Calibri"/></font>
  </fonts>
  <fills count="2">
    <fill><patternFill patternType="none"/></fill>
    <fill><patternFill patternType="gray125"/></fill>
  </fills>
  <borders count="1">
    <border><left/><right/><top/><bottom/><diagonal/></border>
  </borders>
  <cellStyleXfs count="1">
    <xf numFmtId="0" fontId="0" fillId="0" borderId="0"/>
  </cellStyleXfs>
  <cellXfs count="2">
    <xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>
    <xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/>
  </cellXfs>
  <cellStyles count="1">
    <cellStyle name="Normal" xfId="0" builtinId="0"/>
  </cellStyles>
</styleSheet>""",
        )
        archive.writestr("xl/worksheets/sheet1.xml", sheet_xml)


def _render_sheet_row(row_index: int, values: list[Any], style_id: int) -> str:
    cells: list[str] = []
    for col_index, value in enumerate(values, start=1):
        ref = f"{_column_name(col_index)}{row_index}"
        if value is None or value == "":
            cells.append(f'<c r="{ref}" s="{style_id}"/>')
            continue
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            cells.append(f'<c r="{ref}" s="{style_id}"><v>{value}</v></c>')
            continue
        text = escape(str(value)).replace("\r\n", "\n").replace("\r", "\n")
        cells.append(
            f'<c r="{ref}" s="{style_id}" t="inlineStr"><is><t xml:space="preserve">{text}</t></is></c>'
        )
    return f'<row r="{row_index}">{"".join(cells)}</row>'


def _column_name(index: int) -> str:
    name = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        name = chr(65 + remainder) + name
    return name


def _classify_target_cluster(warehouse_name: str) -> str | None:
    normalized = _normalize(warehouse_name)
    if any(keyword in normalized for keyword in KRASNODAR_WAREHOUSE_KEYWORDS):
        return "krasnodar"
    if any(keyword in normalized for keyword in MOSCOW_WAREHOUSE_KEYWORDS):
        return "moscow"
    return None


def _is_local_stock_warehouse(warehouse_name: str) -> bool:
    normalized = _normalize(warehouse_name)
    return any(keyword in normalized for keyword in LOCAL_WAREHOUSE_KEYWORDS)


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def _parse_dt(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _week_key(day: date) -> str:
    iso = day.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def _safe_div(left: float, right: float) -> float:
    if not right:
        return 0.0
    return left / right


def _clean_multiline(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _md(value: Any) -> str:
    if value is None:
        return ""
    return str(value).replace("|", "\\|").replace("\n", " ").strip()
