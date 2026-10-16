import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

import requests

from src.search import geocoding as geo


class GeocodingTests(unittest.TestCase):
    def setUp(self) -> None:
        """To isolate the SQLite cache and replace all HTTP requests and real waiting."""

        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.cache = Path(directory.name) / "cache.sqlite3"
        for setting in (patch.object(geo.ut, "NOMINATIM_CACHE_PATH", self.cache),
                        patch.object(geo.time, "time", return_value=100), patch.object(geo.time, "sleep")):
            mock = setting.start()
            self.addCleanup(setting.stop)
            if setting.attribute == "sleep":
                self.sleep = mock
        setting = patch.object(geo.requests, "get")
        self.request = setting.start()
        self.addCleanup(setting.stop)
        self.response = self.request.return_value.__enter__.return_value
        self.response.json.return_value = [{"display_name": "New York, USA", "lat": "40.7", "lon": "-74.0"}]

    def test_resolve_and_cache(self) -> None:
        """To request English location names and reuse the persistent cache without another HTTP request."""

        result = geo.resolve_location(" New York ")
        self.assertEqual(result["query"], "New York")
        self.assertEqual(result["nominatim_name"], "New York, USA")
        self.assertEqual(result["nominatim_latitude"], 40.7)
        self.assertEqual(result["nominatim_longitude"], -74.0)
        self.assertIn("OpenStreetMap", result["attribution"])
        self.assertEqual(geo.resolve_location("New York"), result)
        self.request.assert_called_once()
        self.assertTrue(self.request.call_args.kwargs["headers"]["User-Agent"])
        self.assertEqual(self.request.call_args.kwargs["params"]["accept-language"], "en")

    def test_japanese_cache_is_preserved_but_not_reused(self) -> None:
        """To keep old Japanese cache rows while fetching and reusing an independent English result."""

        old_key = json.dumps([geo.ut.NOMINATIM_URL, "New York", "ja"], ensure_ascii=False)
        old_result = {"query": "New York", "nominatim_name": "Old localized name"}
        with closing(sqlite3.connect(self.cache)) as cache:
            cache.execute("CREATE TABLE locations (cache_key TEXT PRIMARY KEY, result TEXT NOT NULL)")
            cache.execute("INSERT INTO locations VALUES (?, ?)", (old_key, json.dumps(old_result)))
            cache.commit()
        result = geo.resolve_location("New York")
        self.assertEqual(result["nominatim_name"], "New York, USA")
        self.assertEqual(geo.resolve_location("New York"), result)
        self.request.assert_called_once()
        with closing(sqlite3.connect(self.cache)) as cache:
            rows = dict(cache.execute("SELECT cache_key, result FROM locations"))
        self.assertEqual(json.loads(rows[old_key]), old_result)
        new_key = json.dumps([geo.ut.NOMINATIM_URL, "New York", "en"], ensure_ascii=False)
        self.assertEqual(json.loads(rows[new_key]), result)

    def test_uncached_queries_respect_interval(self) -> None:
        """To enforce spacing between uncached lookups using the persisted request timestamp."""

        geo.resolve_location("New York")
        geo.resolve_location("Paris")
        self.assertEqual(self.request.call_count, 2)
        self.assertGreaterEqual(self.sleep.call_args.args[0], 1)

    def test_multiple_candidates_use_first_and_cache_it(self) -> None:
        """To select and cache the first valid result without sorting or rejecting multiple candidates."""

        self.response.json.return_value = [
            {"display_name": "Shinjuku, Tokyo, 160-8484, Japan", "lat": "35.6937632", "lon": "139.7036319"},
            {"display_name": "Shinjuku, Tokyo, 160-0022, Japan", "lat": "35.6942679", "lon": "139.7086541"},
        ]
        result = geo.resolve_location("Shinjuku")
        self.assertEqual(result["query"], "Shinjuku")
        self.assertEqual(result["nominatim_name"], "Shinjuku, Tokyo, 160-8484, Japan")
        self.assertEqual(result["nominatim_latitude"], 35.6937632)
        self.assertEqual(result["nominatim_longitude"], 139.7036319)
        self.assertEqual(geo.resolve_location("Shinjuku"), result)
        self.request.assert_called_once()

    def test_zero_candidates_report_no_location(self) -> None:
        """To reject an empty result list with an explicit no-location error."""

        self.response.json.return_value = []
        with self.assertRaisesRegex(ValueError, "No Nominatim location found"):
            geo.resolve_location("Missing region")

    def test_invalid_first_candidate_is_not_replaced_by_later_results(self) -> None:
        """To validate the selected first candidate rather than silently switching to another region."""

        self.response.json.return_value = [
            {"display_name": "First", "lat": "nan", "lon": "0"},
            {"display_name": "Second", "lat": "40.7", "lon": "-74.0"},
        ]
        with self.assertRaisesRegex(ValueError, "coordinates"):
            geo.resolve_location("Example region")

    def test_endpoint_changes_do_not_reuse_results(self) -> None:
        """To avoid sharing geocoded results between different provider endpoints."""

        geo.resolve_location("New York")
        with patch.object(geo.ut, "NOMINATIM_URL", "https://example.com/search"):
            geo.resolve_location("New York")
        self.assertEqual(self.request.call_count, 2)

    def test_missing_ambiguous_and_invalid_coordinates(self) -> None:
        """To reject uncertain locations and malformed coordinates rather than starting a wrong-region search."""

        cases = [[], [{"display_name": "A"}, {"display_name": "B"}], {}, [None],
                 [{"display_name": "A", "lat": "nan", "lon": "0"}],
                 [{"display_name": "A", "lat": "91", "lon": "0"}],
                 [{"display_name": "A", "lat": "40", "lon": "181"}]]
        for candidates in cases:
            with self.subTest(candidates=candidates):
                self.response.json.return_value = candidates
                with self.assertRaises(ValueError):
                    geo.resolve_location("New York")

    def test_failed_requests_are_not_cached_and_still_throttled(self) -> None:
        """To retain rate-limit state across an HTTP failure without caching failed location data."""

        self.response.raise_for_status.side_effect = requests.HTTPError("429")
        with self.assertRaisesRegex(RuntimeError, "429"):
            geo.resolve_location("New York")
        self.response.raise_for_status.side_effect = None
        geo.resolve_location("New York")
        self.assertEqual(self.request.call_count, 2)
        self.assertGreaterEqual(self.sleep.call_args.args[0], 1)

    def test_timeout_and_invalid_json(self) -> None:
        """To report HTTP timeouts and invalid response JSON with lookup context."""

        self.request.side_effect = requests.Timeout("network timeout")
        with self.assertRaisesRegex(RuntimeError, "network timeout"):
            geo.resolve_location("New York")
        self.request.side_effect = None
        self.response.json.side_effect = ValueError("bad JSON")
        with self.assertRaisesRegex(RuntimeError, "bad JSON"):
            geo.resolve_location("New York")

    def test_invalid_input_does_not_request(self) -> None:
        """To reject empty regions and invalid timeouts before using the cache or network."""

        for name, timeout in ((" ", 30), ("New York", 0), ("New York", float("inf"))):
            with self.subTest(name=name, timeout=timeout), self.assertRaises(ValueError):
                geo.resolve_location(name, timeout)
        self.request.assert_not_called()
        self.assertFalse(self.cache.exists())


if __name__ == "__main__":
    unittest.main()
