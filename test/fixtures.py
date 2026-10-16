"""To provide fictional responses independent of runtime files and external services."""

import json
from typing import Any


def place_record(index: int = 1) -> list[Any]:
    """To provide a representative Maps place record with fictional profile fields."""

    record: list[Any] = [None] * 204
    record[4] = [None, None, "$$", None, None, None, None, 4.5, 100]
    record[7], record[9] = ["https://example.com"], [None, None, 40.7, -74.0]
    record[10], record[11] = f"0x1:0x{index:x}", f"Restaurant {index}"
    record[13], record[39], record[78] = ["Italian restaurant"], "Example address", f"place-{index}"
    record[178] = [["+1 555 0100"]]
    return record


def captured(payload: list[Any], request_id: str = "search-1") -> dict[str, Any]:
    """To wrap a payload in a JSON envelope resembling a captured Maps response."""

    return {"request_id": request_id, "url": "https://www.google.com/search?tbm=map&q=restaurants",
            "status": 200, "body": json.dumps({"d": ")]}'\n" + json.dumps(payload)})}


def search_response(*indices: int) -> dict[str, Any]:
    """To provide a search batch with an advertisement header and fictional places."""

    payload: list[Any] = [None] * 65
    payload[1] = [[123, -74.0, 40.7]]
    payload[64] = [[None, None, None, None, None, []], *[[None, place_record(index)] for index in indices]]
    return captured(payload, "search-" + "-".join(map(str, indices)))


def place_response(index: int = 1) -> dict[str, Any]:
    """To provide details with an embedded review, duplicate photos, and opening hours."""

    record = place_record(index)
    photos = [[None, [None] * 6 + [[url]]] for url in (
        "https://example.com/photo.jpg", "https://example.com/photo.jpg", "javascript:invalid",
    )]
    content: list[Any] = [None] * 16
    content[0], content[2], content[6], content[15] = [5], photos, [], [["Good food."], ["Friendly service."]]
    author = [
        None, None, 1700000000000000, None,[None, None, None, None, None, ["Example author", None, None, "author-1"]], None, "a week ago"
        ]
    core = ["review-1", author, content]
    record[175] = [None] * 10
    record[175][3], record[175][9] = [1, 2, 3, 4, 90], [[[[core]]]]
    record[203] = [[["Monday", None, [2026, 10, 12], [["09:00-17:00"]]]], None, ["Open"]]
    payload: list[Any] = [None] * 7
    payload[6] = record
    return captured(payload, f"detail-{index}")


def result(count: int = 2, location: bool = True) -> dict[str, Any]:
    """To provide parsed results with recognizable raw bodies for workflow and export tests."""

    places = []
    for index in range(1, count + 1):
        places.append({
            "rank": index,
            "place": {
                "place_id": f"place-{index}", 
                "feature_id": f"0x1:0x{index:x}", 
                "name": f"Restaurant {index}", 
                "address": "Example address", 
                "categories": ["Italian restaurant"], 
                "latitude": 40.7,
                "longitude": -74.0, 
                "rating": 4.5, 
                "review_count": 100, 
                "website": None, 
                "phone": None},
                "details": {"opening_hours": []},
                "reviews": [
                    {
                        "review_id": "review-1", 
                        "text": "Good food,\nfriendly service.",
                        "photo_urls": ["https://example.com/photo.jpg"]
                        }
                    ],
            "url": f"https://example.com/place/{index}",
            "raw_responses": [
                {
                    "request_id": f"detail-{index}", 
                    "url": f"https://example.com/preview/{index}",
                    "status": 200, 
                    "body": f"RAW PLACE {index}\nsecond line"
                    }
                ],
        })
    return {
        "search": {
        "query": "restaurants", 
        "url": "https://example.com/search",
        "location": {
            "query": "New York", 
            "nominatim_name": "New York, USA", 
            "nominatim_latitude": 40.7,
            "nominatim_longitude": -74.0, 
            "attribution": "OpenStreetMap contributors"
            } if location else None,
        "zoom": 14 if location else None, 
        "center": {"latitude": 40.7, "longitude": -74.0},
        "raw_responses": [
            {
                "request_id": "search-1", 
                "url": "https://example.com/search", 
                "status": 200,
                "body": "RAW SEARCH\nsecond line"
                }
            ],
            },
        "places": places
        }
