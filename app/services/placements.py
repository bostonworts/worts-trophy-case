from __future__ import annotations


PLACE_LABELS = {
    1: "1st",
    2: "2nd",
    3: "3rd",
    4: "HM",
}


def place_label(place: int | None) -> str:
    if place is None:
        return ""
    return PLACE_LABELS.get(place, str(place))


def parse_place_value(value: object) -> int | None:
    if value is None:
        return None
    cleaned = str(value).strip().lower()
    if not cleaned:
        return None
    if cleaned in {"hm", "honorable mention", "honourable mention"}:
        return 4
    if cleaned in {"1st", "first"}:
        return 1
    if cleaned in {"2nd", "second"}:
        return 2
    if cleaned in {"3rd", "third"}:
        return 3
    try:
        return int(cleaned)
    except ValueError:
        return None
