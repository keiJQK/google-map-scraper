import json
import math
import re
from typing import Any


def decode_payloads(body: str) -> list[list[Any]]:
    """To decode JSON envelopes, anti-XSSI prefixes, and comment-separated response chunks without evaluation."""

    text = body.lstrip("\ufeff \t\r\n")
    text = re.sub(r"^\)\s*\]\s*\}\s*'\s*", "", text, count=1)
    decoder = json.JSONDecoder()
    payloads = []
    while text:
        if text.startswith("/*"):
            end = text.find("*/", 2)
            if end == -1:
                raise ValueError("Unterminated response comment")
            text = text[end + 2:].lstrip()
            continue
        value, end = decoder.raw_decode(text)
        text = text[end:].lstrip()
        if isinstance(value, dict) and isinstance(value.get("d"), str):
            payloads.extend(decode_payloads(value["d"]))
        elif isinstance(value, list):
            payloads.append(value)
        else:
            raise ValueError("Expected a JSON array or an envelope containing a string d field")
    if not payloads:
        raise ValueError("Response contains no JSON payload")
    return payloads


def normalize_place(record: list[Any]) -> dict[str, Any]:
    """To extract shared place fields without search-rank metadata, retaining nullable scalars and category lists."""

    categories = array_value(record, 13)
    review_count = number_value(array_value(record, 4, 8))
    return {
        "place_id": text_value(array_value(record, 78)),
        "feature_id": text_value(array_value(record, 10)),
        "name": text_value(array_value(record, 11)),
        "address": text_value(array_value(record, 39)),
        "categories": [item for value in categories if (item := text_value(value))] if isinstance(categories, list) else [],
        "latitude": number_value(array_value(record, 9, 2)),
        "longitude": number_value(array_value(record, 9, 3)),
        "rating": number_value(array_value(record, 4, 7)),
        "review_count": int(review_count) if review_count is not None and review_count >= 0 and review_count.is_integer() else None,
        "website": text_value(array_value(record, 7, 0)),
        "phone": text_value(array_value(record, 178, 0, 0)),
    }


def build_place_entry(place: dict[str, Any], rank: int | None) -> dict[str, Any]:
    """To initialize a place entry with incomplete detail state and independent collection defaults."""

    return {
        "rank": rank,
        "completed": False,
        "place": {key: value for key, value in place.items() if key != "rank"},
        "details": None,
        "reviews": [],
        "url": None,
        "raw_responses": [],
    }


def array_value(value: Any, *indices: int) -> Any:
    """To read optional nested array fields without assuming that missing entries exist."""

    for index in indices:
        if not isinstance(value, list) or index >= len(value):
            return None
        value = value[index]
    return value


def text_value(value: Any) -> str | None:
    """To retain nonempty strings and normalize missing or incompatible values to None."""

    return value.strip() if isinstance(value, str) and value.strip() else None


def number_value(value: Any) -> float | None:
    """To normalize finite JSON numbers while excluding booleans and incompatible values."""

    if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
        return float(value)
    return None
