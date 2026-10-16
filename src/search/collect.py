import logging
import math
from typing import Any
from urllib.parse import parse_qs, quote, urlsplit

from .. import browser as br
from ..common import language as lang
from . import parser as ser_par

logger = logging.getLogger(__name__)
SCROLL_DISTANCE = 1000
MAX_STALLED_SCROLLS = 3
MAX_SCROLLS = 200


def collect_search(
    browser: br.Browser, 
    query: str, 
    quiet_period: float = 1.5, 
    max_places: int = 30,
    location: dict[str, Any] | None = None,
    zoom: int = 14,
    language: str = "en",
    ) -> dict[str, Any]:
    """To capture search batches around an optional resolved region and retain their location metadata."""

    validate_max_places(max_places)
    query = query.strip()
    search_url = build_search_url(query, location, zoom, language)
    raw_responses = browser.capture(search_url, lambda url: _is_search_url(url, query), quiet_period)
    parsed = ser_par.parse_responses(raw_responses)
    stalled_scrolls = 0
    for _ in range(MAX_SCROLLS):
        if len(parsed["places"]) >= max_places:
            break
        at_bottom = browser.scroll_search(query, SCROLL_DISTANCE)
        additional = browser.capture_responses(
            lambda url: _is_search_url(url, query), quiet_period, required=False
            )
        previous_count = len(parsed["places"])
        if additional:
            raw_responses.extend(additional)
            parsed = ser_par.parse_responses(raw_responses)
        stalled_scrolls = stalled_scrolls + 1 if at_bottom and len(parsed["places"]) == previous_count else 0
        if stalled_scrolls >= MAX_STALLED_SCROLLS:
            logger.info("Search stopped at the feed bottom after %s attempts without new places; collected %s",
                        stalled_scrolls, len(parsed["places"]))
            break
    else:
        if len(parsed["places"]) < max_places:
            logger.warning("Search reached the scroll limit (%s); collected %s places", MAX_SCROLLS, len(parsed["places"]))
    return {
        "search": {
            "query": query,
            "url": search_url,
            "location": dict(location) if location is not None else None,
            "zoom": zoom if location is not None else None,
            "center": parsed["center"],
            "raw_responses": raw_responses,
        },
        "places": parsed["places"],
    }


def validate_max_places(max_places: int) -> None:
    """To require a positive integer target before opening a browser or collecting search responses."""

    if isinstance(max_places, bool) or not isinstance(max_places, int) or max_places <= 0:
        raise ValueError("max_places must be a positive integer")


def build_search_url(query: str, location: dict[str, Any] | None = None, zoom: int = 14, language: str = "en") -> str:
    """To build a localized Maps search URL with an optional Nominatim center and validated zoom."""

    language = lang.normalize_language(language)
    validate_zoom(zoom)
    if not query.strip():
        raise ValueError("query must not be empty")
    url = "https://www.google.com/maps/search/" + quote(query.strip(), safe="")
    if location is not None:
        latitude, longitude = location["nominatim_latitude"], location["nominatim_longitude"]
        for value, bound in ((latitude, 90), (longitude, 180)):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not -bound <= value <= bound:
                raise ValueError("location must contain valid numeric latitude and longitude")
        url += f"/@{latitude},{longitude},{zoom}z"
    return url + "?hl=" + language


def validate_zoom(zoom: int) -> None:
    """To require an integer Maps zoom level between zero and twenty-one."""

    if isinstance(zoom, bool) or not isinstance(zoom, int) or not 0 <= zoom <= 21:
        raise ValueError("zoom must be an integer between 0 and 21")


def _is_search_url(url: str, query: str) -> bool:
    """To identify Google map-search requests for the current query while allowing dynamic parameters."""

    parts = urlsplit(url)
    params = parse_qs(parts.query)
    return (
        parts.scheme == "https"
        and parts.hostname in {"www.google.com", "google.com", "www.google.co.jp", "google.co.jp"}
        and parts.path == "/search"
        and params.get("tbm") == ["map"]
        and params.get("q") == [query]
    )
