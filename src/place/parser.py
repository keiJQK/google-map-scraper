from datetime import date
from typing import Any
from urllib.parse import urlsplit

from ..common import response as resp


def parse_responses(raw_responses: list[dict[str, Any]], entry: dict[str, Any]) -> dict[str, Any]:
    """To enrich a verified place entry without erasing known basic fields with missing detail values."""

    if not raw_responses:
        raise ValueError("At least one captured place response is required")
    reviews: dict[str, dict[str, Any]] = {}
    result = resp.build_place_entry(entry["place"], entry["rank"])
    result["url"] = entry["url"]
    for response in raw_responses:
        try:
            for payload in resp.decode_payloads(response["body"]):
                record = resp.array_value(payload, 6)
                if not isinstance(record, list) or resp.text_value(resp.array_value(record, 11)) is None:
                    raise ValueError("Unsupported place layout: expected a place record at payload[6]")
                place = resp.normalize_place(record)
                _verify_identity(place, entry["place"])
                result["place"].update({
                    key: value for key, value in place.items() if value is not None and value != "" and value != []
                })
                result["details"] = {
                    "price_range": resp.text_value(resp.array_value(record, 4, 2)),
                    "opening_hours": _opening_hours(record),
                    "opening_status": resp.text_value(resp.array_value(record, 203, 2, 0)),
                    "attributes": _attributes(record),
                    "rating_distribution": {
                        f"star_{star}": _integer(resp.array_value(record, 175, 3, star - 1)) for star in range(1, 6)
                    },
                }
                for review in _reviews(record):
                    reviews.setdefault(review["review_id"], review)
        except (ValueError, TypeError, KeyError) as error:
            raise ValueError(f"Cannot parse place response {response.get('url', '<unknown>')}: {error}") from error
    result["reviews"] = list(reviews.values())
    result["raw_responses"] = raw_responses
    return result


def _verify_identity(place: dict[str, Any], card: dict[str, Any]) -> None:
    """To reject conflicting identifiers and require at least one matching place or feature ID."""

    matched = False
    for key in ("place_id", "feature_id"):
        expected = resp.text_value(card.get(key))
        actual = resp.text_value(place.get(key))
        if expected is not None and actual is not None:
            if key == "feature_id":
                expected, actual = expected.lower(), actual.lower()
            if actual != expected:
                raise ValueError(f"Selected card {key} {expected!r} does not match response {actual!r}")
            matched = True
    if not matched:
        raise ValueError("Response has no identifier matching the selected card")


def _opening_hours(record: list[Any]) -> list[dict[str, Any]]:
    """To retain the response's day labels, calendar dates, and displayed opening periods."""

    days = resp.array_value(record, 203, 0)
    if days is None:
        return []
    if not isinstance(days, list):
        raise ValueError("Unsupported opening-hours layout")
    result = []
    for day in days:
        calendar = resp.array_value(day, 2)
        calendar_date = None
        if isinstance(calendar, list) and len(calendar) == 3:
            try:
                calendar_date = date(*calendar).isoformat()
            except (TypeError, ValueError):
                pass
        periods = resp.array_value(day, 3)
        result.append({
            "day": resp.text_value(resp.array_value(day, 0)),
            "date": calendar_date,
            "hours": [label for period in periods if (label := resp.text_value(resp.array_value(period, 0)))]
            if isinstance(periods, list) else [],
        })
    return result


def _attributes(record: list[Any]) -> list[dict[str, Any]]:
    """To group place attributes while preserving explicit positive, negative, and unknown availability."""

    groups = resp.array_value(record, 100, 1)
    if groups is None:
        return []
    if not isinstance(groups, list):
        raise ValueError("Unsupported place-attribute layout")
    result = []
    for group in groups:
        items = []
        for item in resp.array_value(group, 2) or []:
            flag = resp.array_value(item, 2, 2, 0)
            items.append({
                "id": resp.text_value(resp.array_value(item, 0)),
                "label": resp.text_value(resp.array_value(item, 1)),
                "available": bool(flag) if type(flag) is int and flag in (0, 1) else None,
                "description": resp.text_value(resp.array_value(item, 2, 2, 1)),
            })
        result.append({
            "id": resp.text_value(resp.array_value(group, 0)), "label": resp.text_value(resp.array_value(group, 1)), "items": items,
        })
    return result


def _reviews(record: list[Any]) -> list[dict[str, Any]]:
    """To retain embedded review text, ratings, structured answers, and attached photo URLs."""

    groups = resp.array_value(record, 175, 9)
    if groups is None:
        return []
    if not isinstance(groups, list):
        raise ValueError("Unsupported embedded-review layout")
    result = []
    for group in groups:
        rows = resp.array_value(group, 0)
        if not isinstance(rows, list):
            raise ValueError("Unsupported embedded-review group")
        for row in rows:
            core = resp.array_value(row, 0)
            review_id = resp.text_value(resp.array_value(core, 0))
            if review_id is None:
                raise ValueError("Embedded review has no review ID")
            segments = resp.array_value(core, 2, 15)
            comments = (
                [comment for part in segments if (comment := resp.text_value(resp.array_value(part, 0)))]
                if isinstance(segments, list) else []
            )
            result.append({
                "review_id": review_id,
                "author_name": resp.text_value(resp.array_value(core, 1, 4, 5, 0)),
                "author_id": resp.text_value(resp.array_value(core, 1, 4, 5, 3)),
                "rating": resp.number_value(resp.array_value(core, 2, 0, 0)),
                "timestamp_us": _integer(resp.array_value(core, 1, 2)),
                "time_text": resp.text_value(resp.array_value(core, 1, 6)),
                "text": "\n".join(comments) if comments else None,
                "photo_urls": _review_photo_urls(resp.array_value(core, 2, 2)),
                "aspects": _review_aspects(resp.array_value(core, 2, 6)),
            })
    return result


def _review_photo_urls(photos: Any) -> list[str]:
    """To extract unique HTTP photo URLs in attachment order, skipping missing or malformed entries."""

    if not isinstance(photos, list):
        return []
    urls = []
    seen = set()
    for photo in photos:
        url = resp.text_value(resp.array_value(photo, 1, 6, 0))
        if url is None or url in seen or any(character.isspace() for character in url):
            continue
        try:
            parts = urlsplit(url)
            if parts.scheme not in ("http", "https") or not parts.hostname:
                continue
        except ValueError:
            continue
        seen.add(url)
        urls.append(url)
    return urls


def _review_aspects(aspects: Any) -> list[dict[str, Any]]:
    """To normalize review aspect scores and selected answer labels without mixing them into the review text."""

    if aspects is None:
        return []
    if not isinstance(aspects, list):
        raise ValueError("Unsupported review-aspect layout")
    result = []
    for aspect in aspects:
        values = []
        for index in (2, 3):
            for choice in resp.array_value(aspect, index, 0) or []:
                label = resp.text_value(resp.array_value(choice, 1))
                if label is not None and label not in values:
                    values.append(label)
        result.append({
            "id": resp.text_value(resp.array_value(aspect, 0, 0)),
            "label": resp.text_value(resp.array_value(aspect, 5)) or resp.text_value(resp.array_value(aspect, 1)),
            "rating": resp.number_value(resp.array_value(aspect, 11, 0)),
            "values": values,
        })
    return result


def _integer(value: Any) -> int | None:
    """To retain nonnegative integer counts and timestamps without treating booleans as numbers."""

    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    numeric = resp.number_value(value)
    return int(numeric) if numeric is not None and numeric >= 0 and numeric.is_integer() else None
