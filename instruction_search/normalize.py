from __future__ import annotations

import re
import unicodedata


_MULTISPACE_RE = re.compile(r"\s+")
_PUNCT_RE = re.compile(r"[^\w\s]+", re.UNICODE)
_SPACE_RE = re.compile(r"\s+")

_CYR_TO_LAT = str.maketrans(
    {
        "а": "a",
        "б": "b",
        "в": "v",
        "г": "g",
        "д": "d",
        "е": "e",
        "ё": "e",
        "ж": "zh",
        "з": "z",
        "и": "i",
        "й": "i",
        "к": "k",
        "л": "l",
        "м": "m",
        "н": "n",
        "о": "o",
        "п": "p",
        "р": "r",
        "с": "s",
        "т": "t",
        "у": "u",
        "ф": "f",
        "х": "h",
        "ц": "c",
        "ч": "ch",
        "ш": "sh",
        "щ": "sh",
        "ы": "y",
        "э": "e",
        "ю": "yu",
        "я": "ya",
    }
)

_MANUAL_ALIASES = {
    "баад": "badd",
    "бадд": "badd",
    "б а а д": "badd",
}


def normalize_query(value: str) -> str:
    text = unicodedata.normalize("NFKC", value or "").casefold().strip()
    text = _PUNCT_RE.sub(" ", text)
    text = _MULTISPACE_RE.sub(" ", text).strip()
    return _MANUAL_ALIASES.get(text, text)


def compact_query(value: str) -> str:
    compact = _SPACE_RE.sub("", normalize_query(value))
    return _MANUAL_ALIASES.get(compact, compact)


def translit_query(value: str) -> str:
    translit = compact_query(value).translate(_CYR_TO_LAT)
    return _MANUAL_ALIASES.get(translit, translit)


def normalize_token_list(values: list[str] | tuple[str, ...] | None) -> tuple[str, ...]:
    if not values:
        return ()
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        item = normalize_query(value)
        if item and item not in seen:
            normalized.append(item)
            seen.add(item)
    return tuple(normalized)
