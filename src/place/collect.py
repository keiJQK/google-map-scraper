import re
from typing import Any
from urllib.parse import parse_qs, urlencode, urlsplit

from .. import browser as br
from ..common import response as resp
from ..common import language as lang
from . import parser as plc_par


def collect_place(browser: br.Browser, entry: dict[str, Any], quiet_period: float = 1.5, language: str = "en") -> dict[str, Any]:
    """To enrich a shared place entry with verified details, reviews, and raw responses without closing the browser."""

    place_url = build_place_url(entry["place"], language)
    raw_responses = browser.capture(place_url, lambda url: _is_place_url(url, entry["place"]), quiet_period)
    parsed = plc_par.parse_responses(raw_responses, entry)
    parsed["url"] = place_url
    return parsed


def _is_place_url(url: str, card: dict[str, Any]) -> bool:
    """To select place-preview traffic by feature ID when available, deferring final identity checks to parsing."""

    parts = urlsplit(url)
    if (
        parts.scheme != "https"
        or parts.hostname not in {"www.google.com", "google.com", "www.google.co.jp", "google.co.jp"}
        or parts.path.rstrip("/") != "/maps/preview/place"
    ):
        return False
    params = parse_qs(parts.query)
    tokens = re.findall(r"!\d+s([^!]*)", params.get("pb", [""])[0])
    feature_id = resp.text_value(card.get("feature_id"))
    if feature_id is not None:
        return feature_id.lower() in {token.lower() for token in tokens}
    # Some requests encode only a feature ID, which cannot be inferred from a place ID.
    # Without one on the card, accept the endpoint and verify the response's place ID.
    return True


def build_place_url(card: dict[str, Any], language: str = "en") -> str:
    """To build a localized public Maps URL from the selected card's name and place ID."""

    language = lang.normalize_language(language)
    name = resp.text_value(card.get("name"))
    place_id = resp.text_value(card.get("place_id"))
    if name is None or place_id is None:
        raise ValueError("The selected card must contain a nonempty name and place_id")
    return "https://www.google.com/maps/search/?" + urlencode({
        "api": 1, "query": name, "query_place_id": place_id, "hl": language,
    })


