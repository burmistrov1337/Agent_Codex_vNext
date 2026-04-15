from __future__ import annotations

import argparse
import time
from datetime import date
from pathlib import Path

from agent_codex.domains.marketplace.api import WildberriesApiClient, WildberriesApiError
from agent_codex.domains.marketplace.supply_planner import (
    _extract_primary_barcode,
    _fetch_all_cards,
    _write_xlsx,
)

COSMETIC_ACTIVE_TNVED_DESCRIPTIONS: dict[str, str] = {
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


EXTRA_TNVED_DESCRIPTIONS: dict[str, str] = {
    "3301909000": "Смеси душистых веществ и прочие ароматические композиции, прочие.",
    "3304200000": "Средства для макияжа глаз.",
    "3304300000": "Средства для маникюра и педикюра.",
    "3305100000": "Шампуни.",
    "3305900001": "Лаки для волос.",
    "3307100000": "Средства, используемые до, во время или после бритья.",
    "3906909007": "Прочие акриловые полимеры в первичных формах.",
    "3926909709": "Изделия из пластмасс прочие.",
}


def _load_wb_token(project_root: Path) -> str:
    env_path = project_root / ".env"
    if not env_path.exists():
        raise RuntimeError(f"Файл .env не найден: {env_path}")
    for line in env_path.read_text(encoding="utf-8").splitlines():
        if line.startswith("WB_API_TOKEN="):
            token = line.split("=", 1)[1].strip()
            if token:
                return token
    raise RuntimeError("WB_API_TOKEN не найден в .env")


def _fetch_hs_codes_with_retry(client: WildberriesApiClient, subject_id: int) -> list[str]:
    for attempt in range(1, 8):
        try:
            data = client.get_hs_codes(subject_id, locale="ru").get("data") or []
            return [str(row.get("tnved") or "").strip() for row in data if str(row.get("tnved") or "").strip()]
        except WildberriesApiError as exc:
            if "429" in str(exc):
                time.sleep(1.1 * attempt)
                continue
            raise
    return []


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate allowed TN VED list by SKU from WB API")
    parser.add_argument("--project-root", default=".", help="Project root path")
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    output_dir = project_root / "generated" / "marketplace" / f"tnved_sku_allowed_{date.today().isoformat()}"
    output_dir.mkdir(parents=True, exist_ok=True)

    token = _load_wb_token(project_root)
    client = WildberriesApiClient(token=token)
    cards_by_nm_id, _ = _fetch_all_cards(client)

    subject_ids = sorted({int(card.get("subjectID") or 0) for card in cards_by_nm_id.values() if int(card.get("subjectID") or 0)})
    hs_codes_by_subject: dict[int, list[str]] = {}
    for subject_id in subject_ids:
        hs_codes_by_subject[subject_id] = _fetch_hs_codes_with_retry(client, subject_id)
        time.sleep(0.35)

    tnved_descriptions = dict(COSMETIC_ACTIVE_TNVED_DESCRIPTIONS)
    tnved_descriptions.update(EXTRA_TNVED_DESCRIPTIONS)

    rows: list[list[str | int]] = []
    for card in sorted(cards_by_nm_id.values(), key=lambda item: (str(item.get("subjectName") or ""), str(item.get("title") or ""))):
        nm_id = int(card.get("nmID") or 0)
        subject_id = int(card.get("subjectID") or 0)
        subject_name = str(card.get("subjectName") or "")
        for code in hs_codes_by_subject.get(subject_id, []):
            rows.append(
                [
                    nm_id,
                    str(card.get("vendorCode") or ""),
                    _extract_primary_barcode(card),
                    str(card.get("title") or ""),
                    subject_id,
                    subject_name,
                    code,
                    tnved_descriptions.get(code, ""),
                ]
            )

    md_path = output_dir / "tnved_sku_allowed.md"
    xlsx_path = output_dir / "tnved_sku_allowed.xlsx"

    lines = [
        "# Доступные ТН ВЭД по каждому SKU (WB)",
        "",
        "- Источник кодов: WB API `/content/v2/directory/tnved` по subject каждой карточки.",
        "- Примечание: WB API в текущем ответе отдает поля `tnved` и `isKiz` без текстовой расшифровки.",
        "- В колонке `Расшифровка` использованы формулировки WB по этим кодам.",
        f"- SKU: `{len(cards_by_nm_id)}`",
        f"- Строк SKU×код: `{len(rows)}`",
        "",
        "| Артикул WB | Артикул продавца | Баркод | Товар | Subject ID | Категория WB | ТН ВЭД | Расшифровка |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        safe = [str(value).replace("|", "\\|") for value in row]
        lines.append("| " + " | ".join(safe) + " |")
    md_path.write_text("\n".join(lines), encoding="utf-8")

    _write_xlsx(
        xlsx_path,
        headers=[
            "Артикул WB",
            "Артикул продавца",
            "Баркод",
            "Товар",
            "Subject ID",
            "Категория WB",
            "ТН ВЭД",
            "Расшифровка",
        ],
        rows=rows,
    )

    print(
        {
            "sku": len(cards_by_nm_id),
            "rows": len(rows),
            "md": str(md_path.relative_to(project_root)),
            "xlsx": str(xlsx_path.relative_to(project_root)),
        }
    )


if __name__ == "__main__":
    main()
