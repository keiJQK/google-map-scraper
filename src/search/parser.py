"""To parse Google Maps search-list responses captured through CDP."""

import re
from typing import Any

from ..common import response as resp


def parse_responses(raw_responses: list[dict[str, Any]]) -> dict[str, Any]:
    """To normalize raw search responses into a map center and unique place entries with detail defaults."""

    if not raw_responses:
        raise ValueError("At least one captured response is required")
    center = {"latitude": None, "longitude": None}
    places: list[dict[str, Any]] = []
    seen: set[str] = set()
    for response in raw_responses:
        try:
            for payload in resp.decode_payloads(response["body"]):
                coordinates = resp.array_value(payload, 1, 0)
                latitude = resp.number_value(resp.array_value(coordinates, 2))
                longitude = resp.number_value(resp.array_value(coordinates, 1))
                if latitude is not None and longitude is not None:
                    center = {"latitude": latitude, "longitude": longitude}
                for record in _get_place_records(payload):
                    place = resp.normalize_place(record)
                    identifiers = {value for value in (place["place_id"], place["feature_id"]) if value}
                    duplicate = bool(seen.intersection(identifiers))
                    seen.update(identifiers)
                    if not duplicate:
                        places.append(resp.build_place_entry(place, len(places) + 1))
        except (ValueError, TypeError, KeyError) as error:
            raise ValueError(f"Cannot parse search response {response.get('url', '<unknown>')}: {error}") from error
    return {"center": center, "places": places}


def _get_place_records(payload: list[Any]) -> list[list[Any]]:
    """To select organic place records from the sample's result section and skip its advertising header."""

    rows = resp.array_value(payload, 64)
    if not isinstance(rows, list):
        raise ValueError("Unsupported search layout: expected a result list at payload[64]")
    records = []
    for row in rows:
        record = resp.array_value(row, 1)
        if record is None and isinstance(row, list) and len(row) > 5 and isinstance(row[5], list):
            continue
        feature_id = resp.array_value(record, 10)
        if (
            not isinstance(record, list)
            or not isinstance(feature_id, str)
            or re.fullmatch(r"0x[0-9a-fA-F]+:0x[0-9a-fA-F]+", feature_id) is None
            or resp.text_value(resp.array_value(record, 11)) is None
        ):
            raise ValueError("Unsupported place record in payload[64]")
        records.append(record)
    return records
