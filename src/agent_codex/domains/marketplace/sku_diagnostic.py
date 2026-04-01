from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from .api import WildberriesApiClient, WildberriesApiError
from .supply_planner import _extract_primary_barcode, _fetch_all_cards, _write_xlsx
from .tnved_catalog import _extract_inci


@dataclass(slots=True)
class SkuDiagnosticConfig:
    nm_id: int
    output_root: Path
    sales_days: int = 90
    compare_days: int = 30
    query_days: int = 7


@dataclass(slots=True)
class SkuDiagnosticResult:
    output_dir: Path
    markdown_path: Path
    xlsx_path: Path
    nm_id: int
    title: str


def build_sku_diagnostic(
    client: WildberriesApiClient,
    config: SkuDiagnosticConfig,
    today: date | None = None,
) -> SkuDiagnosticResult:
    today = today or date.today()
    cards_by_nm_id, _ = _fetch_all_cards(client)
    if config.nm_id not in cards_by_nm_id:
        raise WildberriesApiError(f"Карточка с nmID={config.nm_id} не найдена в текущем кабинете.")

    card = cards_by_nm_id[config.nm_id]
    title = str(card.get("title") or "")
    barcode = _extract_primary_barcode(card)
    inci = _extract_inci(str(card.get("description") or ""))

    sales_from = (today - timedelta(days=config.sales_days - 1)).isoformat()
    compare_start = today - timedelta(days=config.compare_days - 1)
    compare_past_start = compare_start - timedelta(days=config.compare_days)
    query_start = today - timedelta(days=config.query_days - 1)
    feedback_from_ts = int(datetime.combine(today - timedelta(days=config.sales_days - 1), datetime.min.time()).timestamp())
    feedback_to_ts = int(datetime.combine(today, datetime.max.time().replace(microsecond=0)).timestamp())

    seller_stock_total, seller_stock_rows = _fetch_seller_inventory(client, barcode)
    price_rows = _safe_call(
        client.get_prices_goods_filter_by_nm_ids,
        [config.nm_id],
        default={"data": {"listGoods": []}},
    )
    wb_stock_rows = _safe_call(
        client.get_wb_warehouses_inventory,
        {"nmIds": [config.nm_id], "limit": 250000, "offset": 0},
        default={"data": {"items": []}},
    )
    search_groups = _safe_call(
        client.get_search_report_table_groups,
        {
            "currentPeriod": {"start": compare_start.isoformat(), "end": today.isoformat()},
            "pastPeriod": {"start": compare_past_start.isoformat(), "end": (compare_start - timedelta(days=1)).isoformat()},
            "nmIds": [config.nm_id],
            "positionCluster": "all",
            "orderBy": {"field": "orders", "mode": "desc"},
            "includeSubstitutedSKUs": True,
            "includeSearchTexts": True,
            "limit": 100,
            "offset": 0,
        },
        default={"data": {"groups": []}},
    )
    search_texts = _safe_call(
        client.get_search_report_product_search_texts,
        {
            "currentPeriod": {"start": compare_start.isoformat(), "end": today.isoformat()},
            "pastPeriod": {"start": compare_past_start.isoformat(), "end": (compare_start - timedelta(days=1)).isoformat()},
            "nmIds": [config.nm_id],
            "topOrderBy": "orders",
            "includeSubstitutedSKUs": True,
            "includeSearchTexts": True,
            "orderBy": {"field": "orders", "mode": "desc"},
            "limit": 15,
        },
        default={"data": {"items": []}},
    )

    top_texts = [
        str(item.get("text") or "").strip()
        for item in (search_texts.get("data") or {}).get("items") or []
        if str(item.get("text") or "").strip()
    ][:10]
    query_positions = {"data": {"items": [], "total": []}}
    if top_texts:
        query_positions = _safe_call(
            client.get_search_report_product_orders,
            {
                "period": {"start": query_start.isoformat(), "end": today.isoformat()},
                "nmId": config.nm_id,
                "searchTexts": top_texts,
            },
            default={"data": {"items": [], "total": []}},
        )

    sales = _safe_call(client.get_supplier_sales, sales_from, default=[])
    orders = _safe_call(client.get_supplier_orders, sales_from, default=[])
    promotion_counts = _safe_call(
        client.get_promotion_campaign_counts,
        default={"adverts": [], "all": 0},
    )
    promotion_adverts = _fetch_promotion_adverts(client, promotion_counts)
    calendar_promotions = _safe_call(
        client.get_promotion_calendar_promotions,
        start_datetime=_format_promo_dt(today - timedelta(days=1)),
        end_datetime=_format_promo_dt(today + timedelta(days=30)),
        all_promo=False,
        limit=100,
        offset=0,
        default={"data": {"promotions": []}},
    )
    feedbacks_answered = _safe_call(
        client.get_feedbacks,
        is_answered=True,
        take=100,
        skip=0,
        nm_id=config.nm_id,
        order="dateDesc",
        date_from=feedback_from_ts,
        date_to=feedback_to_ts,
        default={"data": {"feedbacks": []}},
    )
    feedbacks_unanswered = _safe_call(
        client.get_feedbacks,
        is_answered=False,
        take=100,
        skip=0,
        nm_id=config.nm_id,
        order="dateDesc",
        date_from=feedback_from_ts,
        date_to=feedback_to_ts,
        default={"data": {"feedbacks": []}},
    )
    questions_answered = _safe_call(
        client.get_questions,
        is_answered=True,
        take=100,
        skip=0,
        nm_id=config.nm_id,
        order="dateDesc",
        date_from=feedback_from_ts,
        date_to=feedback_to_ts,
        default={"data": {"questions": []}},
    )
    questions_unanswered = _safe_call(
        client.get_questions,
        is_answered=False,
        take=100,
        skip=0,
        nm_id=config.nm_id,
        order="dateDesc",
        date_from=feedback_from_ts,
        date_to=feedback_to_ts,
        default={"data": {"questions": []}},
    )
    sales_windows = _build_sales_windows(sales, nm_id=config.nm_id, today=today)
    order_windows = _build_order_windows(orders, nm_id=config.nm_id, today=today)
    price_summary = _extract_price_summary(price_rows, config.nm_id)
    promotion_summary, promotion_rows, calendar_rows = _extract_promotion_data(
        promotion_counts=promotion_counts,
        promotion_adverts=promotion_adverts,
        calendar_promotions=calendar_promotions,
        nm_id=config.nm_id,
    )
    feedback_summary, feedback_rows = _extract_feedback_data(
        feedbacks_answered=feedbacks_answered,
        feedbacks_unanswered=feedbacks_unanswered,
    )
    question_summary, question_rows = _extract_question_data(
        questions_answered=questions_answered,
        questions_unanswered=questions_unanswered,
    )
    search_group_metrics = _extract_search_group_metrics(search_groups, config.nm_id)
    search_text_rows = _extract_search_text_rows(search_texts)
    query_position_rows = _extract_query_position_rows(query_positions)
    diagnosis = _build_diagnosis(
        seller_stock_total=seller_stock_total,
        sales_windows=sales_windows,
        order_windows=order_windows,
        price_summary=price_summary,
        promotion_summary=promotion_summary,
        feedback_summary=feedback_summary,
        question_summary=question_summary,
        search_group_metrics=search_group_metrics,
    )
    wb_stock_items = (wb_stock_rows.get("data") or {}).get("items") or []

    output_dir = config.output_root / f"sku_diagnostic_{config.nm_id}_{today.isoformat()}"
    output_dir.mkdir(parents=True, exist_ok=True)
    markdown_path = output_dir / "sku_diagnostic.md"
    xlsx_path = output_dir / "sku_diagnostic.xlsx"

    markdown_path.write_text(
        _render_markdown_v2(
            card=card,
            barcode=barcode,
            inci=inci,
            seller_stock_total=seller_stock_total,
            seller_stock_rows=seller_stock_rows,
            price_summary=price_summary,
            wb_stock_items=wb_stock_items,
            sales_windows=sales_windows,
            order_windows=order_windows,
            promotion_summary=promotion_summary,
            promotion_rows=promotion_rows,
            calendar_rows=calendar_rows,
            feedback_summary=feedback_summary,
            feedback_rows=feedback_rows,
            question_summary=question_summary,
            question_rows=question_rows,
            search_group_metrics=search_group_metrics,
            search_text_rows=search_text_rows,
            query_position_rows=query_position_rows,
            diagnosis=diagnosis,
            compare_days=config.compare_days,
            query_days=config.query_days,
        ),
        encoding="utf-8",
    )
    _write_xlsx(
        xlsx_path,
        headers=[
            "section",
            "key",
            "value_1",
            "value_2",
            "value_3",
            "value_4",
        ],
        rows=_build_xlsx_rows_v2(
            card=card,
            barcode=barcode,
            inci=inci,
            seller_stock_total=seller_stock_total,
            seller_stock_rows=seller_stock_rows,
            price_summary=price_summary,
            wb_stock_items=wb_stock_items,
            sales_windows=sales_windows,
            order_windows=order_windows,
            promotion_summary=promotion_summary,
            promotion_rows=promotion_rows,
            calendar_rows=calendar_rows,
            feedback_summary=feedback_summary,
            feedback_rows=feedback_rows,
            question_summary=question_summary,
            question_rows=question_rows,
            search_group_metrics=search_group_metrics,
            search_text_rows=search_text_rows,
            query_position_rows=query_position_rows,
            diagnosis=diagnosis,
        ),
    )

    return SkuDiagnosticResult(
        output_dir=output_dir,
        markdown_path=markdown_path,
        xlsx_path=xlsx_path,
        nm_id=config.nm_id,
        title=title,
    )


def _safe_call(func, *args, default, **kwargs):
    for attempt in range(5):
        try:
            return func(*args, **kwargs)
        except WildberriesApiError as exc:
            if "429" not in str(exc) or attempt == 4:
                return default
            time.sleep(8 * (attempt + 1))
    return default


def _fetch_seller_inventory(
    client: WildberriesApiClient,
    barcode: str,
) -> tuple[int, list[dict[str, Any]]]:
    warehouses = client.get_seller_warehouses()
    rows: list[dict[str, Any]] = []
    total = 0
    for warehouse in warehouses or []:
        warehouse_id = int(warehouse.get("id") or 0)
        if not warehouse_id:
            continue
        response = {"stocks": []}
        for attempt in range(5):
            try:
                response = client.get_warehouse_inventory(warehouse_id, skus=[barcode])
                break
            except WildberriesApiError as exc:
                if "429" not in str(exc) or attempt == 4:
                    response = {"stocks": []}
                    break
                time.sleep(8 * (attempt + 1))
        stocks = response.get("stocks") or []
        amount = sum(int(item.get("amount") or 0) for item in stocks)
        total += amount
        rows.append(
            {
                "warehouse_name": str(warehouse.get("name") or ""),
                "warehouse_id": warehouse_id,
                "amount": amount,
            }
        )
    rows.sort(key=lambda item: (-item["amount"], item["warehouse_name"]))
    return total, rows


def _fetch_promotion_adverts(
    client: WildberriesApiClient,
    promotion_counts: dict[str, Any],
) -> list[dict[str, Any]]:
    campaign_ids: list[int] = []
    for group in promotion_counts.get("adverts") or []:
        for advert in group.get("advert_list") or []:
            advert_id = int(advert.get("advertId") or 0)
            if advert_id:
                campaign_ids.append(advert_id)
    adverts: list[dict[str, Any]] = []
    for chunk_start in range(0, min(len(campaign_ids), 150), 50):
        chunk = campaign_ids[chunk_start : chunk_start + 50]
        response = _safe_call(
            client.get_promotion_adverts,
            ids=chunk,
            default={"adverts": []},
        )
        adverts.extend(response.get("adverts") or [])
    return adverts


def _format_promo_dt(value: date) -> str:
    return value.strftime("%Y-%m-%dT00:00:00Z")


def _extract_price_summary(price_rows: dict[str, Any], nm_id: int) -> dict[str, Any]:
    summary = {
        "price": None,
        "discount": None,
        "discounted_price": None,
        "club_discount": None,
        "club_price": None,
        "editable_size_price": None,
        "is_bad_turnover": None,
    }
    items = (price_rows.get("data") or {}).get("listGoods") or price_rows.get("data") or []
    for item in items or []:
        if int(item.get("nmID") or item.get("nmId") or 0) != nm_id:
            continue
        summary.update(
            {
                "price": item.get("price"),
                "discount": item.get("discount"),
                "discounted_price": item.get("discountedPrice") or item.get("discountPrice"),
                "club_discount": item.get("clubDiscount"),
                "club_price": item.get("clubDiscountedPrice") or item.get("clubPrice"),
                "editable_size_price": item.get("editableSizePrice"),
                "is_bad_turnover": item.get("isBadTurnover"),
            }
        )
        sizes = item.get("sizes") or []
        if sizes and summary["price"] is None:
            first_size = sizes[0]
            summary["price"] = first_size.get("price")
            summary["discounted_price"] = first_size.get("discountedPrice") or first_size.get("discountPrice")
            summary["club_price"] = first_size.get("clubDiscountedPrice") or first_size.get("clubPrice")
        break
    return summary


def _extract_promotion_data(
    *,
    promotion_counts: dict[str, Any],
    promotion_adverts: list[dict[str, Any]],
    calendar_promotions: dict[str, Any],
    nm_id: int,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    status_counts = defaultdict(int)
    for group in promotion_counts.get("adverts") or []:
        status_counts[int(group.get("status") or 0)] += int(group.get("count") or 0)

    promotion_rows: list[dict[str, Any]] = []
    for advert in promotion_adverts:
        matched = False
        for setting in advert.get("nm_settings") or []:
            if int(setting.get("nm_id") or 0) == nm_id:
                matched = True
                break
        if not matched:
            continue
        settings = advert.get("settings") or {}
        placements = settings.get("placements") or {}
        placement_names = [name for name, enabled in placements.items() if enabled]
        promotion_rows.append(
            {
                "campaign_id": advert.get("id"),
                "status": advert.get("status"),
                "payment_type": settings.get("payment_type"),
                "bid_type": advert.get("bid_type"),
                "name": settings.get("name"),
                "placements": ", ".join(placement_names),
                "updated_at": ((advert.get("timestamps") or {}).get("updated")),
            }
        )
    promotion_rows.sort(key=lambda row: str(row.get("updated_at") or ""), reverse=True)

    calendar_rows = []
    for item in ((calendar_promotions.get("data") or {}).get("promotions") or [])[:10]:
        calendar_rows.append(
            {
                "promotion_id": item.get("id"),
                "name": item.get("name"),
                "type": item.get("type"),
                "start": item.get("startDateTime"),
                "end": item.get("endDateTime"),
            }
        )

    summary = {
        "campaigns_total": promotion_counts.get("all"),
        "campaigns_active": status_counts.get(9, 0),
        "campaigns_paused": status_counts.get(11, 0),
        "campaigns_ready": status_counts.get(4, 0),
        "campaigns_completed": status_counts.get(7, 0),
        "sku_campaigns_total": len(promotion_rows),
        "sku_campaigns_active": sum(1 for row in promotion_rows if int(row.get("status") or 0) == 9),
        "sku_campaigns_paused": sum(1 for row in promotion_rows if int(row.get("status") or 0) == 11),
        "calendar_available_promotions": len((calendar_promotions.get("data") or {}).get("promotions") or []),
    }
    return summary, promotion_rows, calendar_rows


def _extract_feedback_data(
    *,
    feedbacks_answered: dict[str, Any],
    feedbacks_unanswered: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    answered_rows = ((feedbacks_answered.get("data") or {}).get("feedbacks") or [])
    unanswered_rows = ((feedbacks_unanswered.get("data") or {}).get("feedbacks") or [])
    combined = list(unanswered_rows) + list(answered_rows)
    combined.sort(key=lambda item: str(item.get("createdDate") or ""), reverse=True)
    valuations = [int(item.get("productValuation") or 0) for item in combined if item.get("productValuation") is not None]
    summary = {
        "feedbacks_total": len(combined),
        "feedbacks_unanswered": len(unanswered_rows),
        "feedbacks_answered": len(answered_rows),
        "avg_rating": round(sum(valuations) / len(valuations), 2) if valuations else None,
        "rating_5": sum(1 for score in valuations if score == 5),
        "rating_4": sum(1 for score in valuations if score == 4),
        "rating_3": sum(1 for score in valuations if score == 3),
        "rating_2": sum(1 for score in valuations if score == 2),
        "rating_1": sum(1 for score in valuations if score == 1),
    }
    rows: list[dict[str, Any]] = []
    for item in combined[:10]:
        rows.append(
            {
                "created_at": item.get("createdDate"),
                "rating": item.get("productValuation"),
                "answered": bool(item.get("answer")),
                "text": _truncate(str(item.get("text") or ""), 140),
            }
        )
    return summary, rows


def _extract_question_data(
    *,
    questions_answered: dict[str, Any],
    questions_unanswered: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    answered_rows = ((questions_answered.get("data") or {}).get("questions") or [])
    unanswered_rows = ((questions_unanswered.get("data") or {}).get("questions") or [])
    combined = list(unanswered_rows) + list(answered_rows)
    combined.sort(key=lambda item: str(item.get("createdDate") or ""), reverse=True)
    summary = {
        "questions_total": len(combined),
        "questions_unanswered": len(unanswered_rows),
        "questions_answered": len(answered_rows),
    }
    rows: list[dict[str, Any]] = []
    for item in combined[:10]:
        rows.append(
            {
                "created_at": item.get("createdDate"),
                "answered": bool(item.get("answer")),
                "text": _truncate(str(item.get("text") or ""), 140),
            }
        )
    return summary, rows


def _build_diagnosis(
    *,
    seller_stock_total: int,
    sales_windows: list[dict[str, Any]],
    order_windows: list[dict[str, Any]],
    price_summary: dict[str, Any],
    promotion_summary: dict[str, Any],
    feedback_summary: dict[str, Any],
    question_summary: dict[str, Any],
    search_group_metrics: dict[str, Any],
) -> dict[str, Any]:
    recent_sales = _window_value(sales_windows, "0_30", "qty")
    prev_sales = _window_value(sales_windows, "31_60", "qty")
    old_sales = _window_value(sales_windows, "61_90", "qty")
    recent_orders = _window_value(order_windows, "0_30", "qty")
    prev_orders = _window_value(order_windows, "31_60", "qty")

    baseline_sales = prev_sales or old_sales or 0
    baseline_orders = prev_orders or 0
    sales_delta_pct = _delta_pct(recent_sales, baseline_sales) if baseline_sales else None
    orders_delta_pct = _delta_pct(recent_orders, baseline_orders) if baseline_orders else None

    recent_daily_sales = recent_sales / 30 if recent_sales else 0.0
    stock_cover_days = round(seller_stock_total / recent_daily_sales, 1) if recent_daily_sales > 0 else None

    strengths: list[str] = []
    issues: list[str] = []
    actions: list[str] = []

    if recent_sales > 0 and sales_delta_pct is not None and sales_delta_pct <= -35:
        issues.append(
            f"Продажи за последние 30 дней просели на {abs(sales_delta_pct):.0f}% к предыдущему сопоставимому окну."
        )
        actions.append("Проверить цену, CTR карточки и попадание SKU в акции: просадка уже заметна в динамике продаж.")
    elif recent_sales > 0 and sales_delta_pct is not None and sales_delta_pct >= 20:
        strengths.append(f"Продажи в последние 30 дней растут на {sales_delta_pct:.0f}% к прошлому окну.")

    if recent_orders > 0 and orders_delta_pct is not None and orders_delta_pct <= -35:
        issues.append(
            f"Заказы за последние 30 дней просели на {abs(orders_delta_pct):.0f}% к предыдущему окну."
        )
    elif recent_orders > 0 and orders_delta_pct is not None and orders_delta_pct >= 20:
        strengths.append(f"Заказы в последние 30 дней растут на {orders_delta_pct:.0f}% к прошлому окну.")

    if stock_cover_days is not None and stock_cover_days > 120:
        issues.append(f"Текущий остаток покрывает примерно {stock_cover_days} дней спроса: есть риск залеживания.")
        actions.append("Снизить цену/подключить акцию или перераспределить остаток: запас уже слишком длинный.")
    elif stock_cover_days is not None and stock_cover_days < 14 and recent_sales > 0:
        issues.append(f"Текущий остаток покрывает всего около {stock_cover_days} дней спроса: есть риск потерять продажи.")
        actions.append("Подготовить пополнение: остаток короткий относительно текущего темпа продаж.")
    elif stock_cover_days is not None and 14 <= stock_cover_days <= 90:
        strengths.append(f"Запас выглядит рабочим: около {stock_cover_days} дней покрытия спроса.")
    elif seller_stock_total > 0 and recent_sales == 0:
        issues.append("Есть остаток, но за последние 30 дней нет продаж.")
        actions.append("Проверить карточку, цену и видимость в поиске: остаток есть, но товар не двигается.")

    avg_rating = feedback_summary.get("avg_rating")
    if avg_rating is not None and feedback_summary.get("feedbacks_total", 0) >= 5:
        if float(avg_rating) < 4.5:
            issues.append(f"Средний рейтинг {avg_rating} при заметном числе отзывов: это может бить по конверсии.")
            actions.append("Разобрать негативные отзывы и исправить главую причину недовольства покупателей.")
        elif float(avg_rating) >= 4.8:
            strengths.append(f"Сильный рейтинг {avg_rating}: карточка не выглядит проблемной по качеству.")

    if feedback_summary.get("feedbacks_unanswered", 0) > 0:
        issues.append(f"Есть неотвеченные отзывы: {feedback_summary['feedbacks_unanswered']}.")
        actions.append("Закрыть неотвеченные отзывы: это быстрый способ снизить репутационный риск.")
    if question_summary.get("questions_unanswered", 0) > 0:
        issues.append(f"Есть неотвеченные вопросы: {question_summary['questions_unanswered']}.")
        actions.append("Ответить на вопросы в карточке: незакрытые вопросы режут доверие и конверсию.")

    visibility_dynamics = search_group_metrics.get("visibility_dynamics")
    position_dynamics = search_group_metrics.get("avg_position_dynamics")
    orders_from_search = search_group_metrics.get("orders_current")
    if visibility_dynamics is not None and float(visibility_dynamics) <= -20:
        issues.append(f"Видимость в поиске падает на {abs(float(visibility_dynamics)):.1f}% к прошлому окну.")
        actions.append("Перепроверить релевантность названия, ключевые фразы и участие в промо: поиск проседает.")
    if position_dynamics is not None and float(position_dynamics) > 5:
        issues.append(f"Средняя позиция в поиске ухудшилась на {float(position_dynamics):.1f} пункта.")
    elif position_dynamics is not None and float(position_dynamics) < -3:
        strengths.append(f"Средняя позиция в поиске улучшилась на {abs(float(position_dynamics)):.1f} пункта.")
    if recent_sales > 0 and (orders_from_search or 0) == 0:
        issues.append("Поиск WB почти не приводит заказы по данным seller analytics.")
        actions.append("Нужен аудит поисковых запросов и фраз в карточке: сейчас поиск почти не продаёт.")

    if promotion_summary.get("sku_campaigns_active", 0) > 0:
        strengths.append("SKU сейчас поддерживается активными рекламными кампаниями WB.")
    elif promotion_summary.get("calendar_available_promotions", 0) > 0 and recent_sales > 0:
        actions.append("Проверить календарь промо WB: для SKU есть доступные акции, а активной поддержки сейчас нет.")

    if price_summary.get("is_bad_turnover"):
        issues.append("WB помечает SKU как проблемный по оборачиваемости.")
        actions.append("Скорректировать цену и промо-механику: WB уже видит проблему с оборачиваемостью.")

    if not issues:
        verdict = "SKU выглядит стабильным: явных красных флагов по продажам, запасу и качеству не видно."
        status = "stable"
    else:
        verdict = issues[0]
        status = "attention"

    unique_actions = []
    for action in actions:
        if action not in unique_actions:
            unique_actions.append(action)

    unique_strengths = []
    for strength in strengths:
        if strength not in unique_strengths:
            unique_strengths.append(strength)

    return {
        "status": status,
        "verdict": verdict,
        "sales_delta_pct": sales_delta_pct,
        "orders_delta_pct": orders_delta_pct,
        "stock_cover_days": stock_cover_days,
        "issues": issues,
        "strengths": unique_strengths,
        "actions": unique_actions[:5],
    }


def _window_value(rows: list[dict[str, Any]], bucket: str, key: str) -> Any:
    for row in rows:
        if row.get("bucket") == bucket:
            return row.get(key)
    return None


def _delta_pct(current: int | float, previous: int | float) -> float | None:
    if previous in (None, 0):
        return None
    return round(((float(current) - float(previous)) / float(previous)) * 100, 1)


def _build_sales_windows(sales: list[dict[str, Any]], nm_id: int, today: date) -> list[dict[str, Any]]:
    windows = _empty_windows(today)
    for row in sales:
        if int(row.get("nmId") or 0) != nm_id:
            continue
        bucket = _bucket_name(row, today)
        if bucket is None:
            continue
        qty = max(1, int(float(row.get("quantity") or 1)))
        windows[bucket]["qty"] += qty
        windows[bucket]["revenue"] += float(row.get("forPay") or row.get("finishedPrice") or row.get("priceWithDisc") or 0.0)
        if row.get("discountPercent") is not None:
            windows[bucket]["discounts"].append(float(row.get("discountPercent") or 0))
        if row.get("spp") is not None:
            windows[bucket]["spp"].append(float(row.get("spp") or 0))
    return _finalize_windows(windows)


def _build_order_windows(orders: list[dict[str, Any]], nm_id: int, today: date) -> list[dict[str, Any]]:
    windows = _empty_windows(today)
    for row in orders:
        if int(row.get("nmId") or 0) != nm_id:
            continue
        bucket = _bucket_name(row, today)
        if bucket is None:
            continue
        qty = max(1, int(float(row.get("quantity") or 1)))
        windows[bucket]["qty"] += qty
    result = _finalize_windows(windows)
    for item in result:
        item.pop("avg_price", None)
        item.pop("avg_discount", None)
        item.pop("avg_spp", None)
    return result


def _empty_windows(today: date) -> dict[str, dict[str, Any]]:
    return {
        "0_30": {"label": f"{today - timedelta(days=29):%Y-%m-%d} .. {today:%Y-%m-%d}", "qty": 0, "revenue": 0.0, "discounts": [], "spp": []},
        "31_60": {"label": f"{today - timedelta(days=59):%Y-%m-%d} .. {today - timedelta(days=30):%Y-%m-%d}", "qty": 0, "revenue": 0.0, "discounts": [], "spp": []},
        "61_90": {"label": f"{today - timedelta(days=89):%Y-%m-%d} .. {today - timedelta(days=60):%Y-%m-%d}", "qty": 0, "revenue": 0.0, "discounts": [], "spp": []},
    }


def _finalize_windows(windows: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for key in ("61_90", "31_60", "0_30"):
        item = windows[key]
        qty = int(item["qty"])
        rows.append(
            {
                "bucket": key,
                "label": item["label"],
                "qty": qty,
                "revenue": round(float(item["revenue"]), 2),
                "avg_price": round(float(item["revenue"]) / qty, 2) if qty else None,
                "avg_discount": round(sum(item["discounts"]) / len(item["discounts"]), 2) if item["discounts"] else None,
                "avg_spp": round(sum(item["spp"]) / len(item["spp"]), 2) if item["spp"] else None,
            }
        )
    return rows


def _bucket_name(row: dict[str, Any], today: date) -> str | None:
    dt = _parse_dt(row)
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
        pass
    for fmt, length in (("%Y-%m-%dT%H:%M:%S", 19), ("%Y-%m-%d %H:%M:%S", 19), ("%Y-%m-%d", 10)):
        try:
            return datetime.strptime(raw[:length], fmt)
        except ValueError:
            continue
    return None


def _extract_search_group_metrics(search_groups: dict[str, Any], nm_id: int) -> dict[str, Any]:
    default = {
        "avg_position_current": None,
        "avg_position_dynamics": None,
        "visibility_current": None,
        "visibility_dynamics": None,
        "open_card_current": None,
        "open_card_dynamics": None,
        "add_to_cart_current": None,
        "add_to_cart_dynamics": None,
        "orders_current": None,
        "orders_dynamics": None,
        "cart_to_order_current": None,
        "cart_to_order_dynamics": None,
    }
    for group in (search_groups.get("data") or {}).get("groups") or []:
        for item in group.get("items") or []:
            if int(item.get("nmId") or 0) != nm_id:
                continue
            default.update(
                {
                    "avg_position_current": _metric_value(item, "avgPosition", "current"),
                    "avg_position_dynamics": _metric_value(item, "avgPosition", "dynamics"),
                    "visibility_current": _metric_value(item, "visibility", "current"),
                    "visibility_dynamics": _metric_value(item, "visibility", "dynamics"),
                    "open_card_current": _metric_value(item, "openCard", "current"),
                    "open_card_dynamics": _metric_value(item, "openCard", "dynamics"),
                    "add_to_cart_current": _metric_value(item, "addToCart", "current"),
                    "add_to_cart_dynamics": _metric_value(item, "addToCart", "dynamics"),
                    "orders_current": _metric_value(item, "orders", "current"),
                    "orders_dynamics": _metric_value(item, "orders", "dynamics"),
                    "cart_to_order_current": _metric_value(item, "cartToOrder", "current"),
                    "cart_to_order_dynamics": _metric_value(item, "cartToOrder", "dynamics"),
                }
            )
            return default
    return default


def _metric_value(item: dict[str, Any], metric_key: str, value_key: str) -> Any:
    metric = item.get(metric_key) or {}
    return metric.get(value_key)


def _extract_search_text_rows(search_texts: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in (search_texts.get("data") or {}).get("items") or []:
        rows.append(
            {
                "text": str(item.get("text") or ""),
                "week_frequency": item.get("weekFrequency"),
                "avg_position_current": _metric_value(item, "avgPosition", "current"),
                "avg_position_dynamics": _metric_value(item, "avgPosition", "dynamics"),
                "orders_current": _metric_value(item, "orders", "current"),
                "orders_dynamics": _metric_value(item, "orders", "dynamics"),
                "open_card_current": _metric_value(item, "openCard", "current"),
                "open_card_dynamics": _metric_value(item, "openCard", "dynamics"),
                "cart_to_order_current": _metric_value(item, "cartToOrder", "current"),
                "cart_to_order_dynamics": _metric_value(item, "cartToOrder", "dynamics"),
            }
        )
    return rows


def _extract_query_position_rows(query_positions: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in (query_positions.get("data") or {}).get("items") or []:
        date_items = item.get("dateItems") or []
        if not date_items:
            continue
        avg_position = sum(float(entry.get("avgPosition") or 0) for entry in date_items) / len(date_items)
        orders = sum(int(entry.get("orders") or 0) for entry in date_items)
        rows.append(
            {
                "text": str(item.get("text") or ""),
                "frequency": item.get("frequency"),
                "avg_position_7d": round(avg_position, 2),
                "orders_7d": orders,
            }
        )
    rows.sort(key=lambda row: (row["avg_position_7d"] if row["avg_position_7d"] is not None else 10**9, -row["orders_7d"]))
    return rows


def _render_markdown(
    *,
    card: dict[str, Any],
    barcode: str,
    inci: str,
    seller_stock_total: int,
    seller_stock_rows: list[dict[str, Any]],
    wb_stock_items: list[dict[str, Any]],
    sales_windows: list[dict[str, Any]],
    order_windows: list[dict[str, Any]],
    search_group_metrics: dict[str, Any],
    search_text_rows: list[dict[str, Any]],
    query_position_rows: list[dict[str, Any]],
    compare_days: int,
    query_days: int,
) -> str:
    lines = [
        f"# SKU Diagnostic: {card.get('title') or ''}",
        "",
        f"- `nmID`: `{card.get('nmID')}`",
        f"- `Артикул продавца`: `{card.get('vendorCode') or ''}`",
        f"- `Баркод`: `{barcode}`",
        f"- `Предмет`: `{card.get('subjectName') or ''}`",
        f"- `Бренд`: `{card.get('brand') or ''}`",
        f"- `INCI`: `{inci}`" if inci else "- `INCI`: не найден",
        f"- `Текущий остаток продавца (seller inventory API)`: `{seller_stock_total}`",
        "",
        "## Остатки продавца",
        "",
        "| Склад | ID | Остаток |",
        "| --- | --- | --- |",
    ]
    for row in seller_stock_rows:
        lines.append(f"| {_md(row['warehouse_name'])} | {row['warehouse_id']} | {row['amount']} |")

    lines.extend(
        [
            "",
            "## Остатки WB",
            "",
            "| Склад WB | Регион | Остаток | В пути к клиенту | В пути от клиента |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for row in wb_stock_items:
        lines.append(
            f"| {_md(str(row.get('warehouseName') or ''))} | {_md(str(row.get('regionName') or ''))} | "
            f"{row.get('quantity') or 0} | {row.get('inWayToClient') or 0} | {row.get('inWayFromClient') or 0} |"
        )

    lines.extend(
        [
            "",
            "## Продажи",
            "",
            "| Окно | Шт | Выручка | Средняя цена | Средняя скидка | Средний SPP |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    for row in sales_windows:
        lines.append(
            f"| {_md(row['label'])} | {row['qty']} | {_money(row['revenue'])} | {_money(row['avg_price'])} | "
            f"{_percent(row['avg_discount'])} | {_percent(row['avg_spp'])} |"
        )

    lines.extend(
        [
            "",
            "## Заказы",
            "",
            "| Окно | Шт |",
            "| --- | --- |",
        ]
    )
    for row in order_windows:
        lines.append(f"| {_md(row['label'])} | {row['qty']} |")

    lines.extend(
        [
            "",
            f"## Поиск и видимость WB за последние {compare_days} дней",
            "",
            "| Метрика | Текущее значение | Динамика к прошлому окну |",
            "| --- | --- | --- |",
            f"| Средняя позиция | {_cell(search_group_metrics['avg_position_current'])} | {_cell(search_group_metrics['avg_position_dynamics'])} |",
            f"| Видимость | {_cell(search_group_metrics['visibility_current'])} | {_cell(search_group_metrics['visibility_dynamics'])} |",
            f"| Открытия карточки | {_cell(search_group_metrics['open_card_current'])} | {_cell(search_group_metrics['open_card_dynamics'])} |",
            f"| Добавления в корзину | {_cell(search_group_metrics['add_to_cart_current'])} | {_cell(search_group_metrics['add_to_cart_dynamics'])} |",
            f"| Заказы из поиска | {_cell(search_group_metrics['orders_current'])} | {_cell(search_group_metrics['orders_dynamics'])} |",
            f"| Конверсия корзина -> заказ | {_cell(search_group_metrics['cart_to_order_current'])} | {_cell(search_group_metrics['cart_to_order_dynamics'])} |",
            "",
            f"## Топ поисковых фраз WB за последние {compare_days} дней",
            "",
            "| Фраза | Частота за неделю | Средняя позиция | Динамика позиции | Заказы | Динамика заказов | Открытия | Конверсия корзина->заказ |",
            "| --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for row in search_text_rows[:10]:
        lines.append(
            f"| {_md(row['text'])} | {_cell(row['week_frequency'])} | {_cell(row['avg_position_current'])} | "
            f"{_cell(row['avg_position_dynamics'])} | {_cell(row['orders_current'])} | {_cell(row['orders_dynamics'])} | "
            f"{_cell(row['open_card_current'])} | {_cell(row['cart_to_order_current'])} |"
        )

    lines.extend(
        [
            "",
            f"## Позиции и заказы по фразам за последние {query_days} дней",
            "",
            "| Фраза | Частота | Средняя позиция | Заказы |",
            "| --- | --- | --- | --- |",
        ]
    )
    for row in query_position_rows[:10]:
        lines.append(
            f"| {_md(row['text'])} | {_cell(row['frequency'])} | {_cell(row['avg_position_7d'])} | {_cell(row['orders_7d'])} |"
        )

    lines.extend(
        [
            "",
            "## Итог",
            "",
            f"- Статус: `{diagnosis['status']}`",
            f"- Ключевой вывод: {diagnosis['verdict']}",
            (
                f"- Покрытие остатком: `{diagnosis['stock_cover_days']} дней`"
                if diagnosis.get("stock_cover_days") is not None
                else "- Покрытие остатком: недостаточно данных для расчёта"
            ),
        ]
    )
    if diagnosis.get("issues"):
        lines.extend(["", "### Что не так", ""])
        for issue in diagnosis["issues"]:
            lines.append(f"- {issue}")
    if diagnosis.get("strengths"):
        lines.extend(["", "### Что работает", ""])
        for strength in diagnosis["strengths"]:
            lines.append(f"- {strength}")
    if diagnosis.get("actions"):
        lines.extend(["", "### Что сделать", ""])
        for index, action in enumerate(diagnosis["actions"], start=1):
            lines.append(f"{index}. {action}")

    lines.extend(
        [
            "",
            "## Примечания",
            "",
            "- Остатки продавца считаются только через `seller inventory API`.",
            "- Поисковая аналитика берётся из `seller analytics API`; для публичной доставки до Москвы нужен отдельный внешний мониторинг выдачи.",
            "- Если часть поисковых данных не показана, это значит, что метод не вернул данные или доступ ограничен.",
        ]
    )
    return "\n".join(lines).strip() + "\n"


def _build_xlsx_rows(
    *,
    card: dict[str, Any],
    barcode: str,
    inci: str,
    seller_stock_total: int,
    seller_stock_rows: list[dict[str, Any]],
    wb_stock_items: list[dict[str, Any]],
    sales_windows: list[dict[str, Any]],
    order_windows: list[dict[str, Any]],
    search_group_metrics: dict[str, Any],
    search_text_rows: list[dict[str, Any]],
    query_position_rows: list[dict[str, Any]],
) -> list[list[Any]]:
    rows: list[list[Any]] = [
        ["summary", "nmID", card.get("nmID"), "", "", ""],
        ["summary", "title", card.get("title"), "", "", ""],
        ["summary", "vendor_code", card.get("vendorCode"), "", "", ""],
        ["summary", "barcode", barcode, "", "", ""],
        ["summary", "subject", card.get("subjectName"), "", "", ""],
        ["summary", "brand", card.get("brand"), "", "", ""],
        ["summary", "inci", inci, "", "", ""],
        ["summary", "seller_stock_total", seller_stock_total, "", "", ""],
    ]
    for row in seller_stock_rows:
        rows.append(["seller_stock", row["warehouse_name"], row["warehouse_id"], row["amount"], "", ""])
    for row in wb_stock_items:
        rows.append(
            [
                "wb_stock",
                row.get("warehouseName"),
                row.get("regionName"),
                row.get("quantity"),
                row.get("inWayToClient"),
                row.get("inWayFromClient"),
            ]
        )
    for row in sales_windows:
        rows.append(
            [
                "sales_window",
                row["label"],
                row["qty"],
                row["revenue"],
                row["avg_price"],
                row["avg_discount"],
            ]
        )
    for row in order_windows:
        rows.append(["order_window", row["label"], row["qty"], "", "", ""])
    for key, value in search_group_metrics.items():
        rows.append(["search_metric", key, value, "", "", ""])
    for row in search_text_rows:
        rows.append(
            [
                "search_text",
                row["text"],
                row["week_frequency"],
                row["avg_position_current"],
                row["orders_current"],
                row["cart_to_order_current"],
            ]
        )
    for row in query_position_rows:
        rows.append(
            [
                "query_position",
                row["text"],
                row["frequency"],
                row["avg_position_7d"],
                row["orders_7d"],
                "",
            ]
        )
    return rows


def _render_markdown_v2(
    *,
    card: dict[str, Any],
    barcode: str,
    inci: str,
    seller_stock_total: int,
    seller_stock_rows: list[dict[str, Any]],
    price_summary: dict[str, Any],
    wb_stock_items: list[dict[str, Any]],
    sales_windows: list[dict[str, Any]],
    order_windows: list[dict[str, Any]],
    promotion_summary: dict[str, Any],
    promotion_rows: list[dict[str, Any]],
    calendar_rows: list[dict[str, Any]],
    feedback_summary: dict[str, Any],
    feedback_rows: list[dict[str, Any]],
    question_summary: dict[str, Any],
    question_rows: list[dict[str, Any]],
    search_group_metrics: dict[str, Any],
    search_text_rows: list[dict[str, Any]],
    query_position_rows: list[dict[str, Any]],
    diagnosis: dict[str, Any],
    compare_days: int,
    query_days: int,
) -> str:
    lines = [
        f"# SKU Diagnostic: {card.get('title') or ''}",
        "",
        f"- `nmID`: `{card.get('nmID')}`",
        f"- `Артикул продавца`: `{card.get('vendorCode') or ''}`",
        f"- `Баркод`: `{barcode}`",
        f"- `Предмет`: `{card.get('subjectName') or ''}`",
        f"- `Бренд`: `{card.get('brand') or ''}`",
        f"- `INCI`: `{inci}`" if inci else "- `INCI`: не найден",
        f"- `Текущий остаток продавца (seller inventory API)`: `{seller_stock_total}`",
        "",
        "## Цены WB",
        "",
        "| Метрика | Значение |",
        "| --- | --- |",
        f"| Базовая цена | {_money(price_summary['price'])} |",
        f"| Скидка | {_percent(price_summary['discount'])} |",
        f"| Цена со скидкой | {_money(price_summary['discounted_price'])} |",
        f"| Скидка WB Club | {_percent(price_summary['club_discount'])} |",
        f"| Цена WB Club | {_money(price_summary['club_price'])} |",
        f"| Редактируемые цены по размерам | {_cell(price_summary['editable_size_price'])} |",
        f"| Флаг плохой оборачиваемости WB | {_cell(price_summary['is_bad_turnover'])} |",
        "",
        "## Остатки продавца",
        "",
        "| Склад | ID | Остаток |",
        "| --- | --- | --- |",
    ]
    for row in seller_stock_rows:
        lines.append(f"| {_md(row['warehouse_name'])} | {row['warehouse_id']} | {row['amount']} |")

    lines.extend(
        [
            "",
            "## Остатки WB",
            "",
            "| Склад WB | Регион | Остаток | В пути к клиенту | В пути от клиента |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for row in wb_stock_items:
        lines.append(
            f"| {_md(str(row.get('warehouseName') or ''))} | {_md(str(row.get('regionName') or ''))} | "
            f"{row.get('quantity') or 0} | {row.get('inWayToClient') or 0} | {row.get('inWayFromClient') or 0} |"
        )

    lines.extend(
        [
            "",
            "## Продажи",
            "",
            "| Окно | Шт | Выручка | Средняя цена | Средняя скидка | Средний SPP |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    for row in sales_windows:
        lines.append(
            f"| {_md(row['label'])} | {row['qty']} | {_money(row['revenue'])} | {_money(row['avg_price'])} | "
            f"{_percent(row['avg_discount'])} | {_percent(row['avg_spp'])} |"
        )

    lines.extend(
        [
            "",
            "## Заказы",
            "",
            "| Окно | Шт |",
            "| --- | --- |",
        ]
    )
    for row in order_windows:
        lines.append(f"| {_md(row['label'])} | {row['qty']} |")

    lines.extend(
        [
            "",
            "## Реклама и промо",
            "",
            "| Метрика | Значение |",
            "| --- | --- |",
            f"| Всего рекламных кампаний | {_cell(promotion_summary['campaigns_total'])} |",
            f"| Активных кампаний | {_cell(promotion_summary['campaigns_active'])} |",
            f"| Пауза | {_cell(promotion_summary['campaigns_paused'])} |",
            f"| Готовы к запуску | {_cell(promotion_summary['campaigns_ready'])} |",
            f"| Завершены | {_cell(promotion_summary['campaigns_completed'])} |",
            f"| Кампаний с этим SKU | {_cell(promotion_summary['sku_campaigns_total'])} |",
            f"| Активных кампаний с этим SKU | {_cell(promotion_summary['sku_campaigns_active'])} |",
            f"| Пауза по этому SKU | {_cell(promotion_summary['sku_campaigns_paused'])} |",
            f"| Доступных промо-календарей на 30 дней | {_cell(promotion_summary['calendar_available_promotions'])} |",
            "",
            "| Campaign ID | Статус | Тип оплаты | Bid type | Плейсменты | Название | Обновлено |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for row in promotion_rows[:10]:
        lines.append(
            f"| {_cell(row['campaign_id'])} | {_cell(row['status'])} | {_md(row['payment_type'])} | {_md(row['bid_type'])} | "
            f"{_md(row['placements'])} | {_md(row['name'])} | {_md(row['updated_at'])} |"
        )
    if calendar_rows:
        lines.extend(
            [
                "",
                "| Доступная промо | Тип | Старт | Финиш |",
                "| --- | --- | --- | --- |",
            ]
        )
        for row in calendar_rows[:10]:
            lines.append(
                f"| {_md(row['name'])} | {_md(row['type'])} | {_md(row['start'])} | {_md(row['end'])} |"
            )

    lines.extend(
        [
            "",
            "## Отзывы и вопросы",
            "",
            "| Метрика | Значение |",
            "| --- | --- |",
            f"| Отзывов по SKU за 90 дней | {_cell(feedback_summary['feedbacks_total'])} |",
            f"| Неотвеченных отзывов | {_cell(feedback_summary['feedbacks_unanswered'])} |",
            f"| Средний рейтинг | {_cell(feedback_summary['avg_rating'])} |",
            f"| Оценка 5 | {_cell(feedback_summary['rating_5'])} |",
            f"| Оценка 4 | {_cell(feedback_summary['rating_4'])} |",
            f"| Оценка 3 | {_cell(feedback_summary['rating_3'])} |",
            f"| Оценка 2 | {_cell(feedback_summary['rating_2'])} |",
            f"| Оценка 1 | {_cell(feedback_summary['rating_1'])} |",
            f"| Вопросов по SKU | {_cell(question_summary['questions_total'])} |",
            f"| Неотвеченных вопросов | {_cell(question_summary['questions_unanswered'])} |",
            "",
            "| Дата | Рейтинг | Есть ответ | Текст отзыва |",
            "| --- | --- | --- | --- |",
        ]
    )
    for row in feedback_rows[:10]:
        lines.append(
            f"| {_md(row['created_at'])} | {_cell(row['rating'])} | {_cell(row['answered'])} | {_md(row['text'])} |"
        )
    if question_rows:
        lines.extend(
            [
                "",
                "| Дата вопроса | Есть ответ | Текст вопроса |",
                "| --- | --- | --- |",
            ]
        )
        for row in question_rows[:10]:
            lines.append(
                f"| {_md(row['created_at'])} | {_cell(row['answered'])} | {_md(row['text'])} |"
            )

    lines.extend(
        [
            "",
            f"## Поиск и видимость WB за последние {compare_days} дней",
            "",
            "| Метрика | Текущее значение | Динамика к прошлому окну |",
            "| --- | --- | --- |",
            f"| Средняя позиция | {_cell(search_group_metrics['avg_position_current'])} | {_cell(search_group_metrics['avg_position_dynamics'])} |",
            f"| Видимость | {_cell(search_group_metrics['visibility_current'])} | {_cell(search_group_metrics['visibility_dynamics'])} |",
            f"| Открытия карточки | {_cell(search_group_metrics['open_card_current'])} | {_cell(search_group_metrics['open_card_dynamics'])} |",
            f"| Добавления в корзину | {_cell(search_group_metrics['add_to_cart_current'])} | {_cell(search_group_metrics['add_to_cart_dynamics'])} |",
            f"| Заказы из поиска | {_cell(search_group_metrics['orders_current'])} | {_cell(search_group_metrics['orders_dynamics'])} |",
            f"| Конверсия корзина -> заказ | {_cell(search_group_metrics['cart_to_order_current'])} | {_cell(search_group_metrics['cart_to_order_dynamics'])} |",
            "",
            f"## Топ поисковых фраз WB за последние {compare_days} дней",
            "",
            "| Фраза | Частота за неделю | Средняя позиция | Динамика позиции | Заказы | Динамика заказов | Открытия | Конверсия корзина->заказ |",
            "| --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for row in search_text_rows[:10]:
        lines.append(
            f"| {_md(row['text'])} | {_cell(row['week_frequency'])} | {_cell(row['avg_position_current'])} | "
            f"{_cell(row['avg_position_dynamics'])} | {_cell(row['orders_current'])} | {_cell(row['orders_dynamics'])} | "
            f"{_cell(row['open_card_current'])} | {_cell(row['cart_to_order_current'])} |"
        )

    lines.extend(
        [
            "",
            f"## Позиции и заказы по фразам за последние {query_days} дней",
            "",
            "| Фраза | Частота | Средняя позиция | Заказы |",
            "| --- | --- | --- | --- |",
        ]
    )
    for row in query_position_rows[:10]:
        lines.append(
            f"| {_md(row['text'])} | {_cell(row['frequency'])} | {_cell(row['avg_position_7d'])} | {_cell(row['orders_7d'])} |"
        )

    lines.extend(
        [
            "",
            "## Итог",
            "",
            f"- Статус: `{diagnosis['status']}`",
            f"- Ключевой вывод: {diagnosis['verdict']}",
            (
                f"- Покрытие остатком: `{diagnosis['stock_cover_days']} дней`"
                if diagnosis.get("stock_cover_days") is not None
                else "- Покрытие остатком: недостаточно данных для расчёта"
            ),
        ]
    )
    if diagnosis.get("issues"):
        lines.extend(["", "### Что не так", ""])
        for issue in diagnosis["issues"]:
            lines.append(f"- {issue}")
    if diagnosis.get("strengths"):
        lines.extend(["", "### Что работает", ""])
        for strength in diagnosis["strengths"]:
            lines.append(f"- {strength}")
    if diagnosis.get("actions"):
        lines.extend(["", "### Что сделать", ""])
        for index, action in enumerate(diagnosis["actions"], start=1):
            lines.append(f"{index}. {action}")

    lines.extend(
        [
            "",
            "## Примечания",
            "",
            "- Остатки продавца считаются только через `seller inventory API`.",
            "- Блок `Цены WB` берётся из `Prices and Discounts API`.",
            "- Блок `Реклама и промо` собирается из рекламных кампаний WB и календаря промоакций.",
            "- Отзывы и вопросы берутся из `feedbacks-api`; если данных нет, это может означать нулевую активность или ограничения токена.",
            "- Поисковая аналитика берётся из `seller analytics API`; для публичной доставки до Москвы нужен отдельный внешний мониторинг выдачи.",
        ]
    )
    return "\n".join(lines).strip() + "\n"


def _build_xlsx_rows_v2(
    *,
    card: dict[str, Any],
    barcode: str,
    inci: str,
    seller_stock_total: int,
    seller_stock_rows: list[dict[str, Any]],
    price_summary: dict[str, Any],
    wb_stock_items: list[dict[str, Any]],
    sales_windows: list[dict[str, Any]],
    order_windows: list[dict[str, Any]],
    promotion_summary: dict[str, Any],
    promotion_rows: list[dict[str, Any]],
    calendar_rows: list[dict[str, Any]],
    feedback_summary: dict[str, Any],
    feedback_rows: list[dict[str, Any]],
    question_summary: dict[str, Any],
    question_rows: list[dict[str, Any]],
    search_group_metrics: dict[str, Any],
    search_text_rows: list[dict[str, Any]],
    query_position_rows: list[dict[str, Any]],
    diagnosis: dict[str, Any],
) -> list[list[Any]]:
    rows: list[list[Any]] = [
        ["summary", "nmID", card.get("nmID"), "", "", ""],
        ["summary", "title", card.get("title"), "", "", ""],
        ["summary", "vendor_code", card.get("vendorCode"), "", "", ""],
        ["summary", "barcode", barcode, "", "", ""],
        ["summary", "subject", card.get("subjectName"), "", "", ""],
        ["summary", "brand", card.get("brand"), "", "", ""],
        ["summary", "inci", inci, "", "", ""],
        ["summary", "seller_stock_total", seller_stock_total, "", "", ""],
    ]
    for key, value in price_summary.items():
        rows.append(["price", key, value, "", "", ""])
    for row in seller_stock_rows:
        rows.append(["seller_stock", row["warehouse_name"], row["warehouse_id"], row["amount"], "", ""])
    for row in wb_stock_items:
        rows.append(
            [
                "wb_stock",
                row.get("warehouseName"),
                row.get("regionName"),
                row.get("quantity"),
                row.get("inWayToClient"),
                row.get("inWayFromClient"),
            ]
        )
    for row in sales_windows:
        rows.append(
            [
                "sales_window",
                row["label"],
                row["qty"],
                row["revenue"],
                row["avg_price"],
                row["avg_discount"],
            ]
        )
    for row in order_windows:
        rows.append(["order_window", row["label"], row["qty"], "", "", ""])
    for key, value in promotion_summary.items():
        rows.append(["promotion_summary", key, value, "", "", ""])
    for row in promotion_rows:
        rows.append(
            [
                "promotion_campaign",
                row["campaign_id"],
                row["status"],
                row["payment_type"],
                row["bid_type"],
                row["placements"],
            ]
        )
    for row in calendar_rows:
        rows.append(
            [
                "promotion_calendar",
                row["promotion_id"],
                row["name"],
                row["type"],
                row["start"],
                row["end"],
            ]
        )
    for key, value in feedback_summary.items():
        rows.append(["feedback_summary", key, value, "", "", ""])
    for row in feedback_rows:
        rows.append(["feedback_row", row["created_at"], row["rating"], row["answered"], row["text"], ""])
    for key, value in question_summary.items():
        rows.append(["question_summary", key, value, "", "", ""])
    for row in question_rows:
        rows.append(["question_row", row["created_at"], row["answered"], row["text"], "", ""])
    for key, value in search_group_metrics.items():
        rows.append(["search_metric", key, value, "", "", ""])
    for row in search_text_rows:
        rows.append(
            [
                "search_text",
                row["text"],
                row["week_frequency"],
                row["avg_position_current"],
                row["orders_current"],
                row["cart_to_order_current"],
            ]
        )
    for row in query_position_rows:
        rows.append(
            [
                "query_position",
                row["text"],
                row["frequency"],
                row["avg_position_7d"],
                row["orders_7d"],
                "",
            ]
        )
    rows.append(["diagnosis", "status", diagnosis.get("status"), "", "", ""])
    rows.append(["diagnosis", "verdict", diagnosis.get("verdict"), "", "", ""])
    rows.append(["diagnosis", "stock_cover_days", diagnosis.get("stock_cover_days"), "", "", ""])
    for issue in diagnosis.get("issues") or []:
        rows.append(["diagnosis_issue", issue, "", "", "", ""])
    for strength in diagnosis.get("strengths") or []:
        rows.append(["diagnosis_strength", strength, "", "", "", ""])
    for action in diagnosis.get("actions") or []:
        rows.append(["diagnosis_action", action, "", "", "", ""])
    return rows


def _md(value: Any) -> str:
    return str(value or "").replace("|", "\\|").replace("\n", " ").strip()


def _truncate(value: str, max_len: int) -> str:
    value = " ".join(value.split())
    if len(value) <= max_len:
        return value
    return value[: max_len - 3].rstrip() + "..."


def _money(value: Any) -> str:
    if value is None or value == "":
        return ""
    return f"{float(value):.2f}"


def _percent(value: Any) -> str:
    if value is None or value == "":
        return ""
    return f"{float(value):.2f}%"


def _cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)
