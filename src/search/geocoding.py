import json
import math
import sqlite3
import time
from contextlib import closing
from typing import Any

import requests

from ..common import utils as ut
from ..common import language as lang

ATTRIBUTION = "© OpenStreetMap contributors (ODbL 1.0): https://www.openstreetmap.org/copyright"


def resolve_location(location: str, timeout: float = 30, language: str = "en") -> dict[str, Any]:
    """To resolve a region using the first localized Nominatim candidate and a language-specific cache."""

    language = lang.normalize_language(language)
    location = location.strip()
    if not location:
        raise ValueError("location must not be empty")
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("timeout must be a finite number greater than zero")
    ut.NOMINATIM_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    cache_key = json.dumps([ut.NOMINATIM_URL, location, language], ensure_ascii=False)
    # SQLite serializes requests across processes sharing this cache, including failed requests.
    with closing(sqlite3.connect(ut.NOMINATIM_CACHE_PATH, timeout=max(30, timeout + 2))) as cache:
        cache.execute("CREATE TABLE IF NOT EXISTS locations (cache_key TEXT PRIMARY KEY, result TEXT NOT NULL)")
        cache.execute("CREATE TABLE IF NOT EXISTS requests (endpoint TEXT PRIMARY KEY, requested_at REAL NOT NULL)")
        cache.execute("BEGIN IMMEDIATE")
        try:
            cached = cache.execute("SELECT result FROM locations WHERE cache_key = ?", (cache_key,)).fetchone()
            if cached is not None:
                return json.loads(cached[0])
            previous = cache.execute("SELECT requested_at FROM requests WHERE endpoint = ?", (ut.NOMINATIM_URL,)).fetchone()
            if previous is not None:
                time.sleep(max(0, previous[0] + 1.1 - time.time()))
            cache.execute("INSERT OR REPLACE INTO requests VALUES (?, ?)", (ut.NOMINATIM_URL, time.time()))
            result = _request_location(location, timeout, language)
            cache.execute("INSERT OR REPLACE INTO locations VALUES (?, ?)", (cache_key, json.dumps(result, ensure_ascii=False)))
            return result
        finally:
            cache.commit()


def _request_location(location: str, timeout: float, language: str = "en") -> dict[str, Any]:
    """To select the first localized region candidate and reject missing results, failures, or invalid coordinates."""

    try:
        with requests.get(
            ut.NOMINATIM_URL,
            params={"q": location, "format": "jsonv2", "limit": 5, "accept-language": language, "layer": "address"},
            headers={"User-Agent": ut.NOMINATIM_USER_AGENT},
            timeout=timeout,
        ) as response:
            response.raise_for_status()
            candidates = response.json()
    except (requests.RequestException, ValueError) as error:
        raise RuntimeError(f"Nominatim lookup failed for {location!r}: {error}") from error
    if not isinstance(candidates, list) or any(not isinstance(item, dict) for item in candidates):
        raise ValueError("Nominatim returned an unsupported response")
    if not candidates:
        raise ValueError(f"No Nominatim location found for {location!r}")
    candidate = candidates[0]
    name = candidate.get("display_name")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("Nominatim returned a location without a name")
    try:
        latitude, longitude = float(candidate["lat"]), float(candidate["lon"])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("Nominatim returned invalid coordinates") from error
    if not math.isfinite(latitude) or not -90 <= latitude <= 90 or not math.isfinite(longitude) or not -180 <= longitude <= 180:
        raise ValueError("Nominatim returned coordinates outside latitude/longitude bounds")
    return {
        "query": location,
        "nominatim_name": name.strip(),
        "nominatim_latitude": latitude,
        "nominatim_longitude": longitude,
        "attribution": ATTRIBUTION,
    }
