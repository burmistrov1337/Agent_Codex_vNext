from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from .api import WildberriesApiClient
from .supply_planner import _fetch_all_cards, _normalize, _write_xlsx

TRANSIENT_MARKERS = (
    "timeout",
    "timed out",
    "target closed",
    "navigation",
    "detached",
    "intercept",
    "net::",
)

CODE_RE = re.compile(r"\b\d{10}\b")

DEFAULT_CARD_URL_TEMPLATE = "https://seller.wildberries.ru/content-management/cards/card?nmID={nm_id}"
DEFAULT_SELLER_URL = "https://seller.wildberries.ru"

OPEN_TNVED_SELECTORS = (
    "button[data-testid='tnved-select-button-interface']",
    "[data-testid='tnved-select-button-interface']",
    "button:has-text('ТН ВЭД')",
    "button:has-text('Выберите ТН ВЭД')",
    "[role='button']:has-text('ТН ВЭД')",
    "input[placeholder*='Введите код ТН ВЭД']",
    "[placeholder*='Введите код ТН ВЭД']",
    "[data-testid*='tnved']",
)

MODAL_SELECTORS = (
    "[class*='Tnved-select__select']",
    "[class*='Tnved-field-view__tnved-select']",
    "[role='dialog']",
    "[data-testid*='modal']",
    "[data-testid*='drawer']",
    "[class*='modal']",
    "[class*='drawer']",
)

DESCRIPTION_SELECTORS = (
    "[class*='Tnved-select__description']",
    "[data-testid*='description']",
    "[data-testid*='tnved-description']",
    "[class*='description']",
    "[class*='right']",
)

OPEN_TNVED_TEXT_PATTERNS = (
    "ТН ВЭД",
    "Выберите ТН ВЭД",
    "Введите код ТН ВЭД",
)


@dataclass(slots=True)
class TnvedUiCatalogConfig:
    output_root: Path
    browser_user_data_dir: Path
    browser_profile_directory: str = "Default"
    browser_channel: str = "chrome"
    browser_executable_path: str | None = None
    browser_cdp_url: str | None = None
    seller_url: str = DEFAULT_SELLER_URL
    card_url_template: str = DEFAULT_CARD_URL_TEMPLATE
    action_timeout_ms: int = 15000
    navigation_timeout_ms: int = 45000
    retries: int = 3
    retry_backoff_seconds: tuple[float, ...] = (2.0, 5.0, 10.0)


@dataclass(slots=True)
class TnvedUiCatalogResult:
    output_dir: Path
    markdown_path: Path
    xlsx_path: Path
    errors_dir: Path
    category_count: int
    unique_code_count: int
    row_count: int
    error_count: int


def build_tnved_ui_catalog(
    client: WildberriesApiClient,
    config: TnvedUiCatalogConfig,
    *,
    today: date | None = None,
) -> TnvedUiCatalogResult:
    today = today or date.today()
    output_dir = config.output_root / f"tnved_ui_catalog_{today.isoformat()}"
    errors_dir = output_dir / "errors"
    output_dir.mkdir(parents=True, exist_ok=True)
    errors_dir.mkdir(parents=True, exist_ok=True)

    markdown_path = output_dir / "tnved_ui_catalog.md"
    xlsx_path = output_dir / "tnved_ui_catalog.xlsx"

    categories = _collect_categories(client)
    rows: list[dict[str, Any]] = []
    category_errors: list[dict[str, Any]] = []

    collector = _build_collector(config=config, errors_dir=errors_dir)
    try:
        collector.open()
        for category in categories:
            subject_id = category["subject_id"]
            category_name = category["category_name"]
            nm_id = category["nm_id"]
            try:
                records = collector.collect_category_tnved(
                    subject_id=subject_id,
                    category_name=category_name,
                    nm_id=nm_id,
                )
            except Exception as exc:  # pragma: no cover - defensive
                category_errors.append(
                    {
                        "subject_id": subject_id,
                        "category_name": category_name,
                        "nm_id": nm_id,
                        "error": str(exc),
                    }
                )
                collector.capture_error_state(f"category_{subject_id}_{_slugify(category_name)}")
                continue

            collected_at = datetime.now(timezone.utc).isoformat()
            for code, description in records:
                rows.append(
                    {
                        "subject_id": subject_id,
                        "category_name": category_name,
                        "tnved_code": code,
                        "tnved_description": description,
                        "source": "WB_UI",
                        "collected_at": collected_at,
                    }
                )
    finally:
        collector.close()

    deduped_rows = _dedupe_rows(rows)
    grouped = _group_by_category(deduped_rows)

    markdown_path.write_text(_render_markdown(grouped, category_errors), encoding="utf-8")
    _write_xlsx(
        xlsx_path,
        headers=[
            "Subject ID",
            "Категория WB",
            "ТН ВЭД",
            "Расшифровка",
            "Source",
            "CollectedAt",
        ],
        rows=[
            [
                row["subject_id"],
                row["category_name"],
                row["tnved_code"],
                row["tnved_description"],
                row["source"],
                row["collected_at"],
            ]
            for row in deduped_rows
        ],
    )

    unique_code_count = len({row["tnved_code"] for row in deduped_rows})
    category_count = len({(row["subject_id"], row["category_name"]) for row in deduped_rows})

    if category_errors:
        (errors_dir / "errors.json").write_text(
            json.dumps(category_errors, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    return TnvedUiCatalogResult(
        output_dir=output_dir,
        markdown_path=markdown_path,
        xlsx_path=xlsx_path,
        errors_dir=errors_dir,
        category_count=category_count,
        unique_code_count=unique_code_count,
        row_count=len(deduped_rows),
        error_count=len(category_errors),
    )


def _build_collector(*, config: TnvedUiCatalogConfig, errors_dir: Path) -> "WbTnvedUiCollector":
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except ImportError as exc:  # pragma: no cover - runtime dependency
        raise RuntimeError(
            "Playwright is not installed. Install dependencies and run: python -m playwright install chromium"
        ) from exc

    return WbTnvedUiCollector(
        config=config,
        errors_dir=errors_dir,
        sync_playwright=sync_playwright,
        playwright_error_type=PlaywrightError,
        playwright_timeout_type=PlaywrightTimeoutError,
    )


def _collect_categories(client: WildberriesApiClient) -> list[dict[str, Any]]:
    cards_by_nm_id, _ = _fetch_all_cards(client)
    by_subject: dict[int, dict[str, Any]] = {}

    for card in cards_by_nm_id.values():
        subject_id = int(card.get("subjectID") or 0)
        if not subject_id:
            continue
        subject_name = str(card.get("subjectName") or "").strip() or "Без категории"
        nm_id = int(card.get("nmID") or 0)
        current = by_subject.get(subject_id)
        if current is None:
            by_subject[subject_id] = {
                "subject_id": subject_id,
                "category_name": subject_name,
                "nm_id": nm_id,
            }
            continue
        if nm_id and (not current["nm_id"] or nm_id < current["nm_id"]):
            current["nm_id"] = nm_id

    return sorted(by_subject.values(), key=lambda item: (_normalize(item["category_name"]), item["subject_id"]))


def _dedupe_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[int, str, str]] = set()
    deduped: list[dict[str, Any]] = []
    for row in rows:
        key = (
            int(row["subject_id"]),
            str(row["tnved_code"]),
            _clean_text(str(row["tnved_description"])),
        )
        if key in seen:
            continue
        seen.add(key)
        row["tnved_description"] = key[2]
        deduped.append(row)
    deduped.sort(key=lambda item: (item["category_name"], item["tnved_code"]))
    return deduped


def _group_by_category(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[int, str], list[dict[str, Any]]] = {}
    for row in rows:
        key = (int(row["subject_id"]), str(row["category_name"]))
        grouped.setdefault(key, []).append(row)
    payload: list[dict[str, Any]] = []
    for (subject_id, category_name), group_rows in sorted(grouped.items(), key=lambda item: (_normalize(item[0][1]), item[0][0])):
        payload.append(
            {
                "subject_id": subject_id,
                "category_name": category_name,
                "rows": sorted(group_rows, key=lambda row: row["tnved_code"]),
            }
        )
    return payload


def _render_markdown(grouped: list[dict[str, Any]], errors: list[dict[str, Any]]) -> str:
    lines = [
        "# Каталог ТН ВЭД из UI WB",
        "",
        f"Собрано категорий: `{len(grouped)}`",
        f"Собрано уникальных кодов: `{len({row['tnved_code'] for item in grouped for row in item['rows']})}`",
        "",
    ]

    for category in grouped:
        lines.extend(
            [
                f"## {category['category_name']} (Subject ID: {category['subject_id']})",
                "",
                "| ТН ВЭД | Расшифровка |",
                "| --- | --- |",
            ]
        )
        for row in category["rows"]:
            lines.append(f"| {row['tnved_code']} | {_md(row['tnved_description'])} |")
        lines.append("")

    if errors:
        lines.extend(["## Ошибки сбора", ""])
        for err in errors:
            lines.append(
                f"- Subject `{err['subject_id']}` / `{_md(err['category_name'])}` / nmID `{err['nm_id']}`: {_md(err['error'])}"
            )

    return "\n".join(lines).strip() + "\n"


def _clean_text(text: str) -> str:
    return " ".join((text or "").replace("\u00a0", " ").split())


def _md(text: str) -> str:
    return str(text or "").replace("|", "\\|").replace("\n", "<br>")


def _slugify(value: str) -> str:
    cleaned = re.sub(r"[^0-9A-Za-zА-Яа-я_-]+", "_", value.strip())
    return cleaned.strip("_") or "unknown"


def get_open_tnved_text_patterns() -> tuple[str, ...]:
    return OPEN_TNVED_TEXT_PATTERNS


class WbTnvedUiCollector:
    def __init__(
        self,
        *,
        config: TnvedUiCatalogConfig,
        errors_dir: Path,
        sync_playwright: Any,
        playwright_error_type: type,
        playwright_timeout_type: type,
    ) -> None:
        self.config = config
        self.errors_dir = errors_dir
        self._sync_playwright = sync_playwright
        self._playwright_error_type = playwright_error_type
        self._playwright_timeout_type = playwright_timeout_type
        self._playwright_cm: Any | None = None
        self._playwright: Any | None = None
        self._context: Any | None = None
        self._page: Any | None = None

    def open(self) -> None:
        self._playwright_cm = self._sync_playwright()
        self._playwright = self._playwright_cm.start()
        if self.config.browser_cdp_url:
            browser = self._playwright.chromium.connect_over_cdp(self.config.browser_cdp_url)
            self._context = browser.contexts[0] if browser.contexts else browser.new_context()
        else:
            launch_args: dict[str, Any] = {
                "user_data_dir": str(self.config.browser_user_data_dir),
                "headless": False,
                "args": [f"--profile-directory={self.config.browser_profile_directory}"] if self.config.browser_profile_directory else [],
            }
            if self.config.browser_executable_path:
                launch_args["executable_path"] = self.config.browser_executable_path
                self._context = self._playwright.chromium.launch_persistent_context(**launch_args)
            else:
                if self.config.browser_channel:
                    launch_args["channel"] = self.config.browser_channel
                    try:
                        self._context = self._playwright.chromium.launch_persistent_context(**launch_args)
                    except Exception:
                        launch_args.pop("channel", None)
                if self._context is None:
                    self._context = self._playwright.chromium.launch_persistent_context(**launch_args)

        self._context.set_default_timeout(self.config.action_timeout_ms)
        self._context.set_default_navigation_timeout(self.config.navigation_timeout_ms)
        self._page = self._context.pages[0] if self._context.pages else self._context.new_page()
        self._page.goto(self.config.seller_url, wait_until="domcontentloaded", timeout=self.config.navigation_timeout_ms)

    def close(self) -> None:
        if self._context is not None:
            self._context.close()
        if self._playwright is not None:
            self._playwright.stop()

    def collect_category_tnved(self, *, subject_id: int, category_name: str, nm_id: int) -> list[tuple[str, str]]:
        if self._page is None:
            raise RuntimeError("Collector is not opened")

        card_url = self.config.card_url_template.format(nm_id=nm_id, subject_id=subject_id)
        self._with_retry(lambda: self._page.goto(card_url, wait_until="domcontentloaded", timeout=self.config.navigation_timeout_ms))
        self._with_retry(self._wait_card_ready)
        self._with_retry(self._open_tnved_modal)
        modal = self._resolve_modal()

        codes = self._extract_codes(modal)
        result: list[tuple[str, str]] = []
        for code in codes:
            description = self._with_retry(lambda code_value=code: self._read_description(modal, code_value))
            result.append((code, _clean_text(description)))

        if not result:
            raise RuntimeError(f"No TN VED codes found for category '{category_name}' / subject {subject_id}")

        return result

    def capture_error_state(self, prefix: str) -> None:
        if self._page is None:
            return
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base = self.errors_dir / f"{prefix}_{stamp}"
        screenshot_path = base.with_suffix(".png")
        html_path = base.with_suffix(".html")
        try:
            self._page.screenshot(path=str(screenshot_path), full_page=True)
        except Exception:
            pass
        try:
            html_path.write_text(self._page.content(), encoding="utf-8")
        except Exception as exc:
            html_path.write_text(f"<html><body>Failed to capture content: {exc}</body></html>", encoding="utf-8")

    def _with_retry(self, fn: Any) -> Any:
        last_error: Exception | None = None
        attempts = max(1, self.config.retries)
        for attempt in range(1, attempts + 1):
            try:
                return fn()
            except Exception as exc:  # pragma: no cover - runtime-heavy
                last_error = exc
                if not self._is_transient(exc) or attempt >= attempts:
                    raise
                delay = self.config.retry_backoff_seconds[min(attempt - 1, len(self.config.retry_backoff_seconds) - 1)]
                time.sleep(delay)
        if last_error:
            raise last_error
        raise RuntimeError("Retry loop exited unexpectedly")

    def _is_transient(self, exc: Exception) -> bool:
        if isinstance(exc, self._playwright_timeout_type):
            return True
        if isinstance(exc, self._playwright_error_type):
            lowered = str(exc).lower()
            return any(marker in lowered for marker in TRANSIENT_MARKERS)
        lowered = str(exc).lower()
        return any(marker in lowered for marker in TRANSIENT_MARKERS)

    def _open_tnved_modal(self) -> None:
        if self._page is None:
            raise RuntimeError("Page is not available")
        if self._modal_is_visible():
            return
        frame = self._select_working_frame()

        for selector in OPEN_TNVED_SELECTORS:
            locator = frame.locator(selector)
            if locator.count() > 0:
                locator.first.click()
                if self._page is not None:
                    self._page.wait_for_timeout(300)
                if self._modal_is_visible():
                    return

        for pattern in get_open_tnved_text_patterns():
            locator = frame.get_by_text(pattern, exact=False)
            if locator.count() > 0:
                locator.first.click()
                if self._page is not None:
                    self._page.wait_for_timeout(300)
                if self._modal_is_visible():
                    return

        # WB form sometimes renders a generic "Выбрать" control in the certificate section.
        section = frame.get_by_text("Сертификат или декларация соответствия", exact=False)
        if section.count() > 0:
            section.first.scroll_into_view_if_needed()
            frame.wait_for_timeout(300)
            choose_buttons = frame.get_by_role("button", name="Выбрать", exact=False)
            for idx in range(min(choose_buttons.count(), 6)):
                choose_buttons.nth(idx).click()
                if self._page is not None:
                    self._page.wait_for_timeout(300)
                if self._modal_is_visible():
                    return
        any_choose = frame.get_by_text("Выбрать", exact=False)
        for idx in range(min(any_choose.count(), 8)):
            any_choose.nth(idx).click()
            if self._page is not None:
                self._page.wait_for_timeout(300)
            if self._modal_is_visible():
                return

        current_code = frame.get_by_text(re.compile(r"\b\d{10}\b"))
        for idx in range(min(current_code.count(), 8)):
            current_code.nth(idx).click()
            if self._page is not None:
                self._page.wait_for_timeout(300)
            if self._modal_is_visible():
                return

        raise RuntimeError("Unable to open TN VED selector modal")

    def _wait_card_ready(self) -> None:
        if self._page is None:
            raise RuntimeError("Page is not available")
        anchors = (
            "Сертификат или декларация соответствия",
            "Требования к модели",
            "Баркод и цена",
            "Редактирование",
        )
        deadline = time.time() + 60
        while time.time() < deadline:
            if self._modal_is_visible():
                return
            for anchor in anchors:
                for frame in self._candidate_frames():
                    locator = frame.get_by_text(anchor, exact=False)
                    if locator.count() > 0 and locator.first.is_visible():
                        return
            self._page.wait_for_timeout(1000)
        raise RuntimeError("Card page did not become ready within 60 seconds")

    def _modal_is_visible(self) -> bool:
        if self._page is None:
            return False
        for frame in self._candidate_frames():
            body_text = _clean_text(frame.locator("body").inner_text()).lower()
            codes = CODE_RE.findall(body_text)
            if ("введите код тн вэд" in body_text and "тн вэд" in body_text) or len(set(codes)) >= 5:
                return True
            for selector in MODAL_SELECTORS:
                locator = frame.locator(selector)
                if locator.count() > 0 and locator.first.is_visible():
                    text = _clean_text(locator.first.inner_text())
                    if "тн вэд" in text.lower() or "введите код тн вэд" in text.lower() or "выберите тн вэд" in text.lower():
                        return True
        return False

    def _resolve_modal(self) -> Any:
        if self._page is None:
            raise RuntimeError("Page is not available")
        for frame in self._candidate_frames():
            for selector in MODAL_SELECTORS:
                locator = frame.locator(selector)
                if locator.count() > 0 and locator.first.is_visible():
                    return locator.first
            body = frame.locator("body")
            body_text = _clean_text(body.inner_text()).lower()
            codes = CODE_RE.findall(body_text)
            if ("введите код тн вэд" in body_text and "тн вэд" in body_text) or len(set(codes)) >= 5:
                return body
        raise RuntimeError("Unable to resolve TN VED modal")

    def _candidate_frames(self) -> list[Any]:
        if self._page is None:
            return []
        frames = [self._page.main_frame]
        for frame in self._page.frames:
            if frame is not self._page.main_frame:
                frames.append(frame)
        return frames

    def _select_working_frame(self) -> Any:
        if self._page is None:
            raise RuntimeError("Page is not available")
        anchors = (
            "Сертификат или декларация соответствия",
            "ТН ВЭД",
            "Введите код ТН ВЭД",
        )
        for frame in self._candidate_frames():
            for anchor in anchors:
                locator = frame.get_by_text(anchor, exact=False)
                if locator.count() > 0:
                    return frame
        return self._page.main_frame

    def _extract_codes(self, modal: Any) -> list[str]:
        direct_codes = modal.locator("[class*='Tnved-list'] [class*='label']")
        codes: set[str] = set()
        if direct_codes.count() > 0:
            for idx in range(direct_codes.count()):
                value = _clean_text(direct_codes.nth(idx).inner_text())
                if CODE_RE.fullmatch(value):
                    codes.add(value)
        if not codes:
            text = _clean_text(modal.inner_text())
            codes = set(CODE_RE.findall(text))
        codes = sorted(codes)
        return codes

    def _read_description(self, modal: Any, code: str) -> str:
        code_locator = modal.get_by_text(code, exact=False)
        if code_locator.count() > 0:
            code_locator.first.click()

        for selector in DESCRIPTION_SELECTORS:
            locator = modal.locator(selector)
            if locator.count() == 0:
                continue
            candidate = _clean_text(locator.first.inner_text())
            if candidate and code not in candidate:
                return candidate

        text = _clean_text(modal.inner_text())
        line_match = re.search(rf"{re.escape(code)}\s*[-–—:]?\s*([^\n]+)", text)
        if line_match:
            return _clean_text(line_match.group(1))

        chunks = [chunk.strip() for chunk in re.split(r"(?<=\.)\s+", text) if chunk.strip()]
        for chunk in chunks:
            if code in chunk:
                candidate = chunk.replace(code, "").strip(" -–—:")
                if len(candidate) > 10:
                    return _clean_text(candidate)

        return ""
