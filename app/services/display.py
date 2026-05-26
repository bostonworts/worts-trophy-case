from __future__ import annotations

from enum import Enum
import re


ACRONYM_WORDS = {
    "aha": "AHA",
    "bjcp": "BJCP",
    "bos": "BOS",
    "csv": "CSV",
    "id": "ID",
    "ipa": "IPA",
    "mcab": "MCAB",
    "nhc": "NHC",
    "url": "URL",
}
SPECIAL_WORDS = {
    "paypal": "PayPal",
}
LOWERCASE_WORDS = {
    "a",
    "an",
    "and",
    "as",
    "at",
    "by",
    "for",
    "from",
    "in",
    "of",
    "on",
    "or",
    "the",
    "to",
    "with",
}


def humanize_label(value: Enum | str | None) -> str:
    if value is None:
        return ""
    raw_value = value.value if isinstance(value, Enum) else str(value)
    words = re.sub(r"[_-]+", " ", raw_value.strip()).split()
    return " ".join(format_label_word(word, index=index) for index, word in enumerate(words))


def format_label_word(word: str, *, index: int) -> str:
    normalized = word.lower()
    if normalized in ACRONYM_WORDS:
        return ACRONYM_WORDS[normalized]
    if normalized in SPECIAL_WORDS:
        return SPECIAL_WORDS[normalized]
    if index > 0 and normalized in LOWERCASE_WORDS:
        return normalized
    return normalized[:1].upper() + normalized[1:]
