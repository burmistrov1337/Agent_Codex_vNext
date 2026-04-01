from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from .api import WildberriesApiClient
from .supply_planner import (
    _extract_primary_barcode,
    _fetch_all_cards,
    _fetch_hs_codes,
    _normalize,
    _write_xlsx,
)

COSMETIC_ACTIVE_SUBJECT_ID = 2926
COSMETIC_ACTIVE_SUBJECT_NAME = "Косметические активы"
COSMETIC_ACTIVE_TNVED_DESCRIPTIONS = {
    "1505009000": "Ланолин и прочие жировые вещества животного происхождения, прочие.",
    "2811220000": "Диоксид кремния.",
    "2905320000": "Пропиленгликоль и прочие диолы данной группы.",
    "2905450009": "Глицерин, прочий.",
    "2918110000": "Молочная кислота, ее соли и сложные эфиры.",
    "2933210000": "Аллантоин и соединения данной группы.",
    "2936240000": "D- или DL-пантотенол (провитамин B5) и производные.",
    "2942000000": "Прочие органические соединения.",
    "3304990000": "Прочие косметические средства или средства для макияжа и средства для ухода за кожей.",
    "3305200000": "Средства для перманентной завивки или распрямления волос.",
    "3305900009": "Прочие средства для волос.",
    "3307900008": "Прочие косметические или туалетные средства.",
    "3401300000": "Средства для мытья кожи в виде жидкости или крема, расфасованные для розничной продажи.",
    "3402310000": "Органические поверхностно-активные вещества анионные.",
    "3402390000": "Органические поверхностно-активные вещества прочие данной подгруппы.",
    "3402410000": "Органические поверхностно-активные вещества катионные.",
    "3402420000": "Органические поверхностно-активные вещества неионогенные.",
    "3402490000": "Органические поверхностно-активные вещества прочие.",
    "3808948000": "Дезинфицирующие средства прочие.",
    "3823700000": "Жирные спирты промышленного назначения.",
    "3824999307": "Прочие химические продукты и препараты, используемые в косметическом сырье и смесях.",
    "3912398500": "Эфиры целлюлозы прочие.",
}

HAIR_KEYWORDS = ("волос", "hair", "шампун", "бальзам", "кондиционер", "маска")
SKIN_KEYWORDS = ("кожа", "лицо", "face", "body", "крем", "лосьон", "сыворот")
ANIONIC_SURFACTANT_KEYWORDS = (
    "sulfate",
    "sulfonate",
    "sarcosinate",
    "glutamate",
    "isethionate",
    "sulfoacetate",
    "taurate",
    "cocosulfate",
)
CATIONIC_SURFACTANT_KEYWORDS = (
    "quaternium",
    "behentrimonium",
    "cetrimonium",
    "ammonium methosulfate",
    "hydroxyethylmonium",
    "dipalmitoylethyl",
)
NONIONIC_SURFACTANT_KEYWORDS = (
    "glucoside",
    "sorbitan",
    "ceteareth",
    "peg-40 hydrogenated castor oil",
    "peg 40 hydrogenated castor oil",
    "olivate",
    "laureth",
    "polysorbate",
)
AMPHOTERIC_SURFACTANT_KEYWORDS = ("betaine",)
PLASTIC_KEYWORDS = ("plastic", "пластик", "pet", "пэт", "pp", "hdpe", "polypropylene")
GLASS_KEYWORDS = ("glass", "стекл")
BOTANICAL_LATIN_MARKERS = (
    "extract",
    "leaf extract",
    "root extract",
    "flower extract",
    "fruit extract",
    "seed oil",
    "leaf oil",
    "bark extract",
    "ferment filtrate",
)
RAW_MATERIAL_MARKERS = (
    "актив",
    "сырье",
    "сырьё",
    "эмульгатор",
    "загустител",
    "консервант",
    "экстракт",
    "воск",
    "пав",
    "компонент",
    "polymer",
)


@dataclass(slots=True)
class TnvedCatalogConfig:
    output_root: Path


@dataclass(slots=True)
class TnvedCatalogResult:
    output_dir: Path
    markdown_path: Path
    xlsx_path: Path
    row_count: int
    confidence_counts: dict[str, int]


MARKING_TRUE_CODES = {
    "3305200000",
    "3305900009",
    "3307900008",
    "3401300000",
}
MARKING_CONDITIONAL_CODES = {
    "3304990000",
    "3808948000",
}
MARKING_SOURCE_NOTE = (
    "Оценка маркировки сделана по перечню Честного Знака для парфюмерно-косметической продукции "
    "и бытовой химии. Для применения перечня нужно учитывать не только ТН ВЭД, но и ОКПД2, "
    "а также наименование и назначение товара."
)


def build_tnved_catalog(
    client: WildberriesApiClient,
    config: TnvedCatalogConfig,
    today: date | None = None,
) -> TnvedCatalogResult:
    today = today or date.today()
    cards_by_nm_id, _ = _fetch_all_cards(client)
    hs_codes_cache: dict[int, list[str]] = {}
    rows: list[dict[str, Any]] = []

    for card in sorted(cards_by_nm_id.values(), key=lambda item: (_normalize(str(item.get("subjectName") or "")), _normalize(str(item.get("title") or "")))):
        subject_id = int(card.get("subjectID") or 0)
        hs_codes = hs_codes_cache.get(subject_id)
        if hs_codes is None:
            hs_codes = _fetch_hs_codes(client, subject_id)
            hs_codes_cache[subject_id] = hs_codes

        inci = _extract_inci(str(card.get("description") or ""))
        tnved, confidence, note = _suggest_tnved(card, inci, hs_codes)
        wb_allows = "n/a"
        if hs_codes:
            wb_allows = "yes" if tnved in hs_codes else "no"

        rows.append(
            {
                "nm_id": int(card.get("nmID") or 0),
                "vendor_code": str(card.get("vendorCode") or ""),
                "barcode": _extract_primary_barcode(card),
                "title": str(card.get("title") or ""),
                "subject_name": str(card.get("subjectName") or ""),
                "inci": inci,
                "tnved": tnved,
                "confidence": confidence,
                "wb_allows": wb_allows,
                "note": note,
                "description": _clean_text(str(card.get("description") or "")),
            }
        )

    output_dir = config.output_root / f"tnved_catalog_{today.isoformat()}"
    output_dir.mkdir(parents=True, exist_ok=True)
    markdown_path = output_dir / "tnved_catalog.md"
    xlsx_path = output_dir / "tnved_catalog.xlsx"

    confidence_counts = Counter(row["confidence"] for row in rows)
    markdown_path.write_text(_render_markdown(rows, confidence_counts), encoding="utf-8")
    _write_xlsx(
        xlsx_path,
        headers=[
            "Артикул WB",
            "Артикул продавца",
            "Баркод",
            "Товар",
            "Предмет",
            "INCI",
            "ТН ВЭД",
            "Уверенность",
            "WB subject допускает код",
            "Комментарий",
            "Описание",
        ],
        rows=[
            [
                row["nm_id"],
                row["vendor_code"],
                row["barcode"],
                row["title"],
                row["subject_name"],
                row["inci"],
                row["tnved"],
                row["confidence"],
                row["wb_allows"],
                row["note"],
                row["description"],
            ]
            for row in rows
        ],
    )

    return TnvedCatalogResult(
        output_dir=output_dir,
        markdown_path=markdown_path,
        xlsx_path=xlsx_path,
        row_count=len(rows),
        confidence_counts=dict(confidence_counts),
    )


def build_cosmetic_actives_tnved_catalog(
    client: WildberriesApiClient,
    config: TnvedCatalogConfig,
    today: date | None = None,
) -> TnvedCatalogResult:
    today = today or date.today()
    cards_by_nm_id, _ = _fetch_all_cards(client)
    allowed_codes = [row.get("tnved") for row in (client.get_hs_codes(COSMETIC_ACTIVE_SUBJECT_ID).get("data") or [])]
    allowed_codes = [str(code) for code in allowed_codes if code]

    rows: list[dict[str, Any]] = []
    for card in sorted(cards_by_nm_id.values(), key=lambda item: _normalize(str(item.get("title") or ""))):
        if int(card.get("subjectID") or 0) != COSMETIC_ACTIVE_SUBJECT_ID:
            continue
        inci = _extract_inci(str(card.get("description") or ""))
        chosen_code, candidate_codes, confidence, note = _suggest_cosmetic_active_tnved(card, inci, allowed_codes)
        wb_card_tnved = _extract_card_tnved(card)
        rows.append(
            {
                "nm_id": int(card.get("nmID") or 0),
                "vendor_code": str(card.get("vendorCode") or ""),
                "barcode": _extract_primary_barcode(card),
                "title": str(card.get("title") or ""),
                "subject_name": str(card.get("subjectName") or ""),
                "inci": inci,
                "wb_card_tnved": wb_card_tnved,
                "chosen_tnved": chosen_code,
                "chosen_description": COSMETIC_ACTIVE_TNVED_DESCRIPTIONS.get(chosen_code, ""),
                "candidate_codes": ", ".join(candidate_codes),
                "confidence": confidence,
                "note": note,
                "matches_card": "yes" if wb_card_tnved and wb_card_tnved == chosen_code else "no" if wb_card_tnved else "n/a",
            }
        )

    output_dir = config.output_root / f"tnved_cosmetic_actives_{today.isoformat()}"
    output_dir.mkdir(parents=True, exist_ok=True)
    markdown_path = output_dir / "tnved_cosmetic_actives.md"
    xlsx_path = output_dir / "tnved_cosmetic_actives.xlsx"

    confidence_counts = Counter(row["confidence"] for row in rows)
    markdown_path.write_text(_render_cosmetic_actives_markdown(rows, confidence_counts, allowed_codes), encoding="utf-8")
    _write_xlsx(
        xlsx_path,
        headers=[
            "Артикул WB",
            "Артикул продавца",
            "Баркод",
            "Товар",
            "INCI",
            "ТН ВЭД в карточке",
            "Рекомендуемый ТН ВЭД",
            "Описание выбранного кода",
            "Альтернативные коды",
            "Уверенность",
            "Совпадает с карточкой",
            "Почему выбран",
        ],
        rows=[
            [
                row["nm_id"],
                row["vendor_code"],
                row["barcode"],
                row["title"],
                row["inci"],
                row["wb_card_tnved"],
                row["chosen_tnved"],
                row["chosen_description"],
                row["candidate_codes"],
                row["confidence"],
                row["matches_card"],
                row["note"],
            ]
            for row in rows
        ],
    )

    return TnvedCatalogResult(
        output_dir=output_dir,
        markdown_path=markdown_path,
        xlsx_path=xlsx_path,
        row_count=len(rows),
        confidence_counts=dict(confidence_counts),
    )


def build_cosmetic_actives_marking_report(
    client: WildberriesApiClient,
    config: TnvedCatalogConfig,
    today: date | None = None,
) -> TnvedCatalogResult:
    today = today or date.today()
    cards_by_nm_id, _ = _fetch_all_cards(client)
    allowed_codes = [row.get("tnved") for row in (client.get_hs_codes(COSMETIC_ACTIVE_SUBJECT_ID).get("data") or [])]
    allowed_codes = [str(code) for code in allowed_codes if code]

    rows: list[dict[str, Any]] = []
    for card in sorted(cards_by_nm_id.values(), key=lambda item: _normalize(str(item.get("title") or ""))):
        if int(card.get("subjectID") or 0) != COSMETIC_ACTIVE_SUBJECT_ID:
            continue
        inci = _extract_inci(str(card.get("description") or ""))
        chosen_code, candidate_codes, confidence, tnved_note = _suggest_cosmetic_active_tnved(card, inci, allowed_codes)
        wb_card_tnved = _extract_card_tnved(card)
        marking_status, marking_reason, chestny_sign = _assess_cosmetic_active_marking(
            card=card,
            inci=inci,
            tnved_code=chosen_code,
        )
        rows.append(
            {
                "nm_id": int(card.get("nmID") or 0),
                "vendor_code": str(card.get("vendorCode") or ""),
                "barcode": _extract_primary_barcode(card),
                "title": str(card.get("title") or ""),
                "inci": inci,
                "wb_card_tnved": wb_card_tnved,
                "chosen_tnved": chosen_code,
                "chosen_description": COSMETIC_ACTIVE_TNVED_DESCRIPTIONS.get(chosen_code, ""),
                "candidate_codes": ", ".join(candidate_codes),
                "confidence": confidence,
                "tnved_note": tnved_note,
                "marking_status": marking_status,
                "marking_reason": marking_reason,
                "chestny_sign": chestny_sign,
            }
        )

    output_dir = config.output_root / f"tnved_marking_cosmetic_actives_{today.isoformat()}"
    output_dir.mkdir(parents=True, exist_ok=True)
    markdown_path = output_dir / "tnved_marking_cosmetic_actives.md"
    xlsx_path = output_dir / "tnved_marking_cosmetic_actives.xlsx"

    confidence_counts = Counter(row["marking_status"] for row in rows)
    markdown_path.write_text(_render_cosmetic_actives_marking_markdown(rows, confidence_counts), encoding="utf-8")
    _write_xlsx(
        xlsx_path,
        headers=[
            "Артикул WB",
            "Артикул продавца",
            "Баркод",
            "Товар",
            "INCI",
            "ТН ВЭД в карточке",
            "Рекомендуемый ТН ВЭД",
            "Описание кода",
            "Альтернативные коды",
            "Подлежит маркировке",
            "Нужен Честный Знак",
            "Почему",
            "Комментарий по ТН ВЭД",
        ],
        rows=[
            [
                row["nm_id"],
                row["vendor_code"],
                row["barcode"],
                row["title"],
                row["inci"],
                row["wb_card_tnved"],
                row["chosen_tnved"],
                row["chosen_description"],
                row["candidate_codes"],
                row["marking_status"],
                row["chestny_sign"],
                row["marking_reason"],
                row["tnved_note"],
            ]
            for row in rows
        ],
    )

    return TnvedCatalogResult(
        output_dir=output_dir,
        markdown_path=markdown_path,
        xlsx_path=xlsx_path,
        row_count=len(rows),
        confidence_counts=dict(confidence_counts),
    )


def _extract_inci(description: str) -> str:
    match = re.search(r"INCI(?:\s+Name)?\s*[:\-–]\s*([^\n\r]+)", description, flags=re.IGNORECASE)
    if not match:
        return ""
    return _clean_text(match.group(1))


def _extract_card_tnved(card: dict[str, Any]) -> str:
    for characteristic in card.get("characteristics") or []:
        if str(characteristic.get("name") or "").strip().lower() != "тнвэд":
            continue
        value = characteristic.get("value") or []
        if isinstance(value, list):
            for item in value:
                if item:
                    return str(item)
        elif value:
            return str(value)
    return ""


def _suggest_cosmetic_active_tnved(
    card: dict[str, Any],
    inci: str,
    allowed_codes: list[str],
) -> tuple[str, list[str], str, str]:
    text = _normalize(
        " ".join(
            [
                str(card.get("title") or ""),
                str(card.get("description") or ""),
                inci,
                _characteristics_blob(card),
            ]
        )
    )
    scores: dict[str, int] = {code: 0 for code in allowed_codes}
    reasons: dict[str, list[str]] = {code: [] for code in allowed_codes}

    def bump(code: str, score: int, reason: str) -> None:
        if code not in scores:
            return
        scores[code] += score
        reasons[code].append(reason)

    def any_token(*tokens: str) -> bool:
        return any(token in text for token in tokens)

    is_hair = any_token("волос", "hair", "шампун", "кондиционер", "маск", "бальзам")
    is_skin = any_token("кожа", "лицо", "face", "body", "крем", "сыворот", "лосьон")
    is_extract = any_token("extract", "экстракт")
    is_oil = any_token("oil", "масло", "squalane", "сквалан", "tocopherol", "витамин е")
    is_protein = any_token("keratin", "шелк", "silk", "protein", "протеин", "collagen", "peptide")
    is_polymer = any_token("polyquaternium", "polymer", "аристофлекс", "aristoflex", "cellulose", "hydroxyethyl cellulose")
    is_shampoo_like = any_token("шампун", "chelating shampoo", "хелатный шампунь", "моющая основа", "cleansing")

    if any_token("lanolin", "ланолин"):
        bump("1505009000", 100, "Ланолин выделен в названии/INCI.")
    if any_token("silica", "silicon dioxide", "hydrated silica", "диоксид кремния"):
        bump("2811220000", 100, "Диоксид кремния / silica.")
    if any_token("pentylene glycol", "propylene glycol", "butylene glycol", "isopentyldiol", "гликоль"):
        bump("2905320000", 90, "Гликоль / диол.")
    if _contains_regex(text, r"\bglycerin\b|\bglycerol\b|глицерин"):
        bump("2905450009", 100, "Глицерин.")
    if any_token("lactic acid", "молочная кислота", "lactate"):
        bump("2918110000", 100, "Молочная кислота.")
    if any_token("allantoin", "аллантоин"):
        bump("2933210000", 100, "Аллантоин.")
    if any_token("panthenol", "d-panthenol", "пантенол", "провитамин в5", "provitamin b5"):
        bump("2936240000", 100, "Пантенол / провитамин B5.")
    if any_token("betaine", "бетаин") and "cocamidopropyl betaine" not in text:
        bump("2942000000", 85, "Бетаин как отдельное органическое соединение.")

    if any_token("cetearyl alcohol", "cetyl alcohol", "behenyl alcohol", "жирный спирт", "fatty alcohol"):
        bump("3823700000", 85, "Жирные спирты.")
    if any_token("hydroxyethyl cellulose", "hydroxypropyl cellulose", "cellulose gum", "cellulose", "целлюлоз"):
        bump("3912398500", 90, "Эфиры целлюлозы / целлюлозные загустители.")

    if any_token("quaternium", "polyquaternium", "behentrimonium", "cetrimonium", "guar hydroxypropyltrimonium", "amodimethicone", "amino silicone", "aminosilicone"):
        bump("3402410000", 75, "Катионный кондиционирующий компонент / кват.")
        bump("3305900009", 45, "Компонент явно для волос.")
        bump("3824999307", 25, "Возможен как косметическая смесь/комплекс.")
    if any_token("sarcosinate", "glutamate", "isethionate", "taurate", "sulfoacetate", "sulfate", "sulfonate"):
        bump("3402310000", 75, "Анионный ПАВ.")
        bump("3402390000", 35, "Близкая группа прочих ПАВ.")
    if any_token("glucoside", "polysorbate", "peg-40 hydrogenated castor oil", "peg 40 hydrogenated castor oil", "laureth", "ceteareth", "olivate", "solubilizer", "эмульгатор"):
        bump("3402420000", 75, "Неионогенный ПАВ / солюбилизатор / эмульгатор.")
    if any_token("cocamidopropyl betaine", "амфотер", "amphoteric"):
        bump("3402490000", 70, "Амфотерный ПАВ.")

    if is_shampoo_like:
        bump("3401300000", 45, "Средство/база для мытья кожи или шампуня.")
        bump("3305900009", 35, "Готовое средство/основа для волос.")
    if any_token("перманент", "выпрямлен", "straightening", "perming"):
        bump("3305200000", 80, "Средство для завивки/выпрямления волос.")
    if any_token("disinfect", "антисеп", "chlorhexidine", "benzalkonium chloride", "biocide", "дезинфиц"):
        bump("3808948000", 60, "Консервирующее/дезинфицирующее назначение.")

    if is_hair and not is_shampoo_like:
        bump("3305900009", 55, "Актив/комплекс для волос.")
    if is_skin:
        bump("3304990000", 55, "Уходовый косметический актив для кожи.")
    if is_extract or is_oil or is_protein or is_polymer:
        bump("3824999307", 50, "Смесь/комплекс/экстракт/масло/полимерное косметическое сырьё.")
    if is_extract and (is_hair or is_skin):
        bump("3304990000", 35, "Экстракт в косметическом применении.")

    if not any(scores.values()):
        if is_hair:
            bump("3305900009", 40, "Базовый выбор для волос.")
            bump("3824999307", 30, "Альтернатива как химическая смесь.")
        elif is_skin:
            bump("3304990000", 40, "Базовый выбор для ухода за кожей.")
            bump("3824999307", 30, "Альтернатива как химическая смесь.")
        else:
            bump("3824999307", 40, "Базовый fallback для косметического сырья.")
            bump("3304990000", 20, "Альтернатива как косметический актив общего назначения.")

    ranked = sorted(allowed_codes, key=lambda code: (-scores.get(code, 0), code))
    ranked = [code for code in ranked if scores.get(code, 0) > 0] or allowed_codes[:1]
    chosen_code = ranked[0]
    alternatives = ranked[:3]
    top_score = scores.get(chosen_code, 0)
    second_score = scores.get(ranked[1], 0) if len(ranked) > 1 else 0
    if top_score >= 90 and top_score - second_score >= 30:
        confidence = "high"
    elif top_score >= 50:
        confidence = "medium"
    else:
        confidence = "low"
    note = "; ".join(reasons.get(chosen_code) or ["Выбор по ближайшему совпадению с разрешёнными кодами WB."])
    if len(alternatives) > 1:
        note += f" Альтернативы: {', '.join(alternatives[1:])}."
    return chosen_code, alternatives, confidence, note


def _characteristics_blob(card: dict[str, Any]) -> str:
    parts: list[str] = []
    for characteristic in card.get("characteristics") or []:
        name = str(characteristic.get("name") or "")
        value = characteristic.get("value") or []
        if isinstance(value, list):
            rendered = ", ".join(str(item) for item in value if item)
        else:
            rendered = str(value or "")
        if name or rendered:
            parts.append(f"{name}: {rendered}")
    return " | ".join(parts)


def _assess_cosmetic_active_marking(
    card: dict[str, Any],
    inci: str,
    tnved_code: str,
) -> tuple[str, str, str]:
    text = _normalize(
        " ".join(
            [
                str(card.get("title") or ""),
                str(card.get("description") or ""),
                inci,
                _characteristics_blob(card),
            ]
        )
    )
    is_raw_material = True
    is_ready_skin_product = _contains_any(text, ("крем", "сыворот", "лосьон", "тоник", "face cream", "serum"))
    is_ready_hair_product = _contains_any(
        text,
        ("шампун", "маска", "бальзам", "кондиционер", "hair spray", "hair tonic", "chelating shampoo"),
    )
    is_disinfectant = _contains_any(
        text,
        ("антисеп", "дезинфиц", "chlorhexidine", "benzalkonium chloride", "sanitizer", "disinfect"),
    )
    is_hand_hygiene = _contains_any(text, ("гигиен", "для рук", "hand hygiene", "hand wash", "для мытья рук"))

    if tnved_code == "3304990000":
        if is_hand_hygiene and is_disinfectant:
            return (
                "спорно",
                "Для 3304990000 есть оговорки по товарам для гигиены рук с антимикробным действием; "
                "нужно проверить точное наименование и ОКПД2.",
                "проверить",
            )
        return (
            "спорно",
            "Код 3304990000 входит в маркируемую группу, но в категории косметических активов такие товары обычно "
            "нужно дополнительно проверять по ОКПД2 и назначению, чтобы отличить сырьё от готовой продукции.",
            "проверить",
        )

    if tnved_code in MARKING_TRUE_CODES:
        if is_raw_material and not (is_ready_skin_product or is_ready_hair_product):
            return (
                "спорно",
                "Код входит в маркируемые группы, но карточка больше похожа на косметическое сырьё/актив. "
                "Для точного вывода нужно сверить ОКПД2 и фактическое назначение товара.",
                "проверить",
            )
        return (
            "да",
            "Код входит в маркируемые группы Честного Знака для косметики, бытовой химии и товаров личной гигиены.",
            "да",
        )

    if tnved_code == "3808948000":
        if is_disinfectant:
            return (
                "спорно",
                "Код может попадать под маркировку только для отдельных дезинфицирующих/антисептических товаров; "
                "нужно проверять назначение и ОКПД2.",
                "проверить",
            )
        return (
            "нет",
            "Сам по себе код 3808948000 не означает обязательную маркировку для косметического сырья; "
            "в перечне важен конкретный тип товара.",
            "нет",
        )

    return (
        "нет",
        "Код не входит в перечень основных ТН ВЭД, маркируемых в товарной группе косметики, бытовой химии и товаров личной гигиены.",
        "нет",
    )


def _suggest_tnved(card: dict[str, Any], inci: str, hs_codes: list[str]) -> tuple[str, str, str]:
    title = str(card.get("title") or "")
    subject_name = str(card.get("subjectName") or "")
    description = str(card.get("description") or "")
    subject_lower = _normalize(subject_name)
    title_subject = _normalize(f"{title} {subject_name}")
    text = _normalize(" ".join([title, subject_name, inci, description]))
    is_raw_material = "косметические активы" in subject_lower or _contains_any(title_subject, RAW_MATERIAL_MARKERS)

    if "шампуни" in subject_lower:
        return "3305100000", "high", "Готовый шампунь по subject карточки."

    if "маски косметические" in subject_lower:
        if _contains_any(text, HAIR_KEYWORDS):
            return "3305900009", "high", "Маска для волос / прочие средства для волос."
        return "3304990000", "medium", "Косметическая маска без явной привязки к волосам."

    if "кремы" in subject_lower:
        if _contains_any(text, HAIR_KEYWORDS):
            return "3305900009", "medium", "Крем/уход для волос."
        return "3304990000", "high", "Крем / средство по уходу за кожей."

    if "свечи" in subject_lower:
        return "3406000000", "high", "Свечи и аналогичные изделия."

    if "отдушки косметические" in subject_lower:
        return "3302909000", "high", "Смесь душистых веществ / отдушка."

    if "флаконы косметические" in subject_lower:
        if _contains_any(text, GLASS_KEYWORDS):
            return "7010905000", "medium", "Флакон из стекла."
        return "3923301000", "medium", "Флакон из пластика / полимерной тары."

    if "дозаторы косметические" in subject_lower:
        if "спрей" in text or "spray" in text:
            return "9616101000", "medium", "Распылительная насадка / спрей."
        return "3926909709", "medium", "Косметический дозатор как прочее изделие из пластмасс."

    if _contains_any(text, ("lanolin", "ланолин")):
        return "1505009000", "high", "Ланолин."
    if _contains_any(text, BOTANICAL_LATIN_MARKERS):
        return "1302199000", "medium", "Растительный экстракт / ботаническое сырьё."
    if _contains_any(text, ("dimethicone", "cyclomethicone", "amodimethicone", "silicone quaternium", "phenyltrimethicone")):
        return "3910000009", "medium", "Силиконы в первичных формах."
    if _contains_any(text, ("silica", "silicon dioxide", "hydrated silica")):
        return "2811220000", "high", "Диоксид кремния / силика."
    if _contains_regex(text, r"\bglycerin\b|\bglycerol\b|глицерин"):
        return "2905450009", "high", "Глицерин."
    if _contains_any(text, ("propylene glycol", "butylene glycol", "pentylene glycol", "isopentyldiol", "1,2-hexanediol")):
        return "2905320000", "medium", "Гликоль / диол, близкая группа 2905."
    if _contains_any(text, ("lactic acid", "молочная кислота")):
        return "2918110000", "high", "Молочная кислота."
    if _contains_any(text, ("panthenol", "pantothenic", "пантенол")):
        return "2936240000", "high", "Провитамин B5 / пантенол."
    if _contains_any(text, ("allantoin", "аллантоин")):
        return "2933210000", "high", "Аллантоин."
    if _contains_regex(text, r"\btocopher[a-z]*\b|витамин е|vitamin e"):
        return "2936280000", "medium", "Токоферол / витамин E."
    if _contains_regex(text, r"\bretin[a-z]*\b|витамин а|vitamin a"):
        return "2936210000", "medium", "Ретиноиды / витамин A."
    if _contains_any(text, ("niacinamide", "nicotinamide", "ниацинамид")):
        return "2936290009", "medium", "Ниацинамид / прочие витамины."
    if _contains_any(text, ("caffeine", "кофеин")):
        return "2939300000", "medium", "Кофеин."
    if _contains_any(text, ("urea", "мочевина")):
        return "2924190000", "medium", "Мочевина / производные амидов."
    if _contains_any(text, ("hyaluronic", "hyaluronate", "гиалурон")):
        return "3913900000", "medium", "Гиалуроновая кислота / природный полимер."
    if _contains_any(text, ("betaine", "бетаин")) and "cocamidopropyl betaine" not in text:
        return "2942000000", "medium", "Бетаин / иное органическое соединение."

    if _contains_any(text, CATIONIC_SURFACTANT_KEYWORDS):
        return _prefer_wb_code(hs_codes, "3402410000"), "medium", "Катионный ПАВ / кватернизованный кондиционирующий агент."
    if _contains_any(text, ANIONIC_SURFACTANT_KEYWORDS):
        return _prefer_wb_code(hs_codes, "3402310000"), "medium", "Анионное поверхностно-активное вещество."
    if _contains_any(text, NONIONIC_SURFACTANT_KEYWORDS):
        return _prefer_wb_code(hs_codes, "3402420000"), "medium", "Неионогенный ПАВ / эмульгатор."
    if _contains_any(text, AMPHOTERIC_SURFACTANT_KEYWORDS):
        return _prefer_wb_code(hs_codes, "3402490000"), "medium", "Амфотерный / амфолитный ПАВ."

    if _contains_any(text, ("cetearyl alcohol", "cetyl alcohol", "behenyl alcohol", "myristyl alcohol")):
        return "3823700000", "medium", "Жирные спирты промышленного назначения."
    if _contains_any(text, ("hydrolyzed keratin", "hydrolyzed silk", "hydrolyzed collagen", "collagen", "keratin", "protein", "proteins", "papain", "peptide")):
        return "3504009000", "medium", "Белковые вещества / гидролизаты / пептиды."
    if _contains_any(text, ("phospholipids", "glycolipids", "sterols", "ceramide", "ceramides")):
        return "3824999307", "medium", "Косметический липидный или многокомпонентный комплекс."
    if _contains_any(text, ("wax", "воск", "squalane", "масло", "oil", "butter")):
        return "3824999307", "low", "Липидное или восковое косметическое сырьё; поставлен best-effort код смеси/сырья."
    if _contains_any(text, ("polyquaternium", "polymer", "copolymer", "aristoflex", "polyacrylate", "cellulose", "hydroxyethyl cellulose")):
        if _contains_any(text, ("cellulose", "hydroxyethyl cellulose")):
            return "3912398500", "medium", "Эфиры целлюлозы / загуститель."
        return "3824999307", "low", "Полимерное косметическое сырьё / смесь."
    if _contains_any(text, ("distilled water", "дистиллированная вода")):
        return "2853901000", "low", "Дистиллированная вода / специальная вода."

    if not is_raw_material:
        if _contains_any(title_subject, ("шампун",)):
            return "3305100000", "medium", "По названию это готовый шампунь."
        if _contains_any(title_subject, ("маска для волос", "hair mask", "бальзам", "кондиционер")):
            return "3305900009", "medium", "Готовое средство для волос."
        if _contains_any(title_subject, ("крем", "сыворот", "лосьон", "тоник")) and _contains_any(title_subject, SKIN_KEYWORDS):
            return "3304990000", "medium", "Готовое уходовое средство для кожи."

    if hs_codes:
        fallback = hs_codes[0]
        return fallback, "low", "Best-effort: выбран первый допустимый код WB для текущего subject."
    return "3824999307", "low", "Best-effort: прочее химическое / косметическое сырьё."


def _prefer_wb_code(hs_codes: list[str], default_code: str) -> str:
    if default_code in hs_codes:
        return default_code
    return default_code


def _contains_any(text: str, patterns: tuple[str, ...]) -> bool:
    return any(pattern in text for pattern in patterns)


def _contains_regex(text: str, pattern: str) -> bool:
    return bool(re.search(pattern, text, flags=re.IGNORECASE))


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _render_markdown(rows: list[dict[str, Any]], confidence_counts: Counter[str]) -> str:
    lines = [
        "# Каталог ТН ВЭД по всем товарам",
        "",
        f"- Всего карточек: `{len(rows)}`.",
        f"- High confidence: `{confidence_counts.get('high', 0)}`.",
        f"- Medium confidence: `{confidence_counts.get('medium', 0)}`.",
        f"- Low confidence: `{confidence_counts.get('low', 0)}`.",
        "",
        "Коды определены best-effort по названию, предмету, INCI и описанию.",
        "Отдельно показано, допускает ли текущий `WB subject` выбранный код.",
        "",
        "| Артикул WB | Артикул продавца | Баркод | Товар | Предмет | INCI | ТН ВЭД | Уверенность | WB допускает | Комментарий |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]

    for row in rows:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row["nm_id"]),
                    _md(row["vendor_code"]),
                    _md(row["barcode"]),
                    _md(row["title"]),
                    _md(row["subject_name"]),
                    _md(_trim(row["inci"], 120)),
                    _md(row["tnved"]),
                    _md(row["confidence"]),
                    _md(row["wb_allows"]),
                    _md(row["note"]),
                ]
            )
            + " |"
        )

    return "\n".join(lines).strip() + "\n"


def _render_cosmetic_actives_markdown(
    rows: list[dict[str, Any]],
    confidence_counts: Counter[str],
    allowed_codes: list[str],
) -> str:
    lines = [
        "# ТН ВЭД: Косметические Активы",
        "",
        f"- Всего карточек: `{len(rows)}`.",
        f"- High confidence: `{confidence_counts.get('high', 0)}`.",
        f"- Medium confidence: `{confidence_counts.get('medium', 0)}`.",
        f"- Low confidence: `{confidence_counts.get('low', 0)}`.",
        "",
        "Разметка сделана только внутри списка допустимых кодов WB для subject `Косметические активы`.",
        "",
        "## Допустимые Коды WB",
        "",
        "| Код | Описание |",
        "| --- | --- |",
    ]
    for code in allowed_codes:
        lines.append(f"| {code} | {_md(COSMETIC_ACTIVE_TNVED_DESCRIPTIONS.get(code, 'Описание не добавлено'))} |")

    lines.extend(
        [
            "",
            "## Таблица",
            "",
            "| Артикул WB | Артикул продавца | Баркод | Товар | INCI | ТН ВЭД в карточке | Рекомендуемый ТН ВЭД | Альтернативы | Уверенность | Совпадает | Почему выбран |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for row in rows:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row["nm_id"]),
                    _md(row["vendor_code"]),
                    _md(row["barcode"]),
                    _md(row["title"]),
                    _md(_trim(row["inci"], 120)),
                    _md(row["wb_card_tnved"]),
                    _md(row["chosen_tnved"]),
                    _md(row["candidate_codes"]),
                    _md(row["confidence"]),
                    _md(row["matches_card"]),
                    _md(row["note"]),
                ]
            )
            + " |"
        )
    return "\n".join(lines).strip() + "\n"


def _render_cosmetic_actives_marking_markdown(
    rows: list[dict[str, Any]],
    status_counts: Counter[str],
) -> str:
    lines = [
        "# Маркировка: Косметические Активы",
        "",
        f"- Всего карточек: `{len(rows)}`.",
        f"- `да`: `{status_counts.get('да', 0)}`.",
        f"- `нет`: `{status_counts.get('нет', 0)}`.",
        f"- `спорно`: `{status_counts.get('спорно', 0)}`.",
        "",
        MARKING_SOURCE_NOTE,
        "",
        "| Артикул WB | Артикул продавца | Баркод | Товар | ТН ВЭД в карточке | Рекомендуемый ТН ВЭД | Подлежит маркировке | Нужен Честный Знак | Почему |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row["nm_id"]),
                    _md(row["vendor_code"]),
                    _md(row["barcode"]),
                    _md(row["title"]),
                    _md(row["wb_card_tnved"]),
                    _md(row["chosen_tnved"]),
                    _md(row["marking_status"]),
                    _md(row["chestny_sign"]),
                    _md(row["marking_reason"]),
                ]
            )
            + " |"
        )
    return "\n".join(lines).strip() + "\n"


def _trim(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[: limit - 1].rstrip() + "…"


def _md(value: Any) -> str:
    return str(value or "").replace("|", "\\|").replace("\n", " ").strip()
