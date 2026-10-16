import unittest
from urllib.parse import parse_qs, urlsplit
from unittest.mock import Mock

from src.place import collect as plc_clct
from src.place import parser as plc_par
from src.search import parser as ser_par
from test import fixtures as fx


class PlaceTests(unittest.TestCase):
    def setUp(self) -> None:
        """To select a fictional search card for independent detail-response tests."""

        self.entry = ser_par.parse_responses([fx.search_response(1)])["places"][0]

    def test_detail_review_and_photo_parsing(self) -> None:
        """To extract details and review attachments while removing duplicate and invalid photo URLs."""

        response = fx.place_response()
        result = plc_par.parse_responses([response, response], self.entry)
        self.assertEqual(result["place"]["name"], "Restaurant 1")
        self.assertEqual(result["details"]["price_range"], "$$")
        self.assertEqual(result["details"]["opening_hours"], [{"day": "Monday", "date": "2026-10-12", "hours": ["09:00-17:00"]}])
        self.assertEqual(result["details"]["opening_status"], "Open")
        self.assertEqual(result["details"]["rating_distribution"]["star_5"], 90)
        self.assertEqual(len(result["reviews"]), 1)
        review = result["reviews"][0]
        self.assertEqual(review["author_name"], "Example author")
        self.assertEqual(review["author_id"], "author-1")
        self.assertEqual(review["rating"], 5)
        self.assertEqual(review["timestamp_us"], 1700000000000000)
        self.assertEqual(review["text"], "Good food.\nFriendly service.")
        self.assertEqual(review["photo_urls"], ["https://example.com/photo.jpg"])
        self.assertEqual(result["raw_responses"], [response, response])

    def test_missing_detail_values_preserve_search_profile(self) -> None:
        """To retain known search fields when the detail response omits them while accepting an explicit zero."""

        record = [None] * 79
        record[10], record[11], record[78] = "0x1:0x1", "Restaurant 1", "place-1"
        record[4] = [None] * 8 + [0]
        result = plc_par.parse_responses([fx.captured([None] * 6 + [record])], self.entry)
        self.assertEqual(result["place"]["website"], "https://example.com")
        self.assertEqual(result["place"]["rating"], 4.5)
        self.assertEqual(result["place"]["review_count"], 0)
        self.assertEqual(result["reviews"], [])

    def test_identity_mismatch_and_bad_layout(self) -> None:
        """To reject a different place and unsupported response layouts instead of merging their data."""

        for responses in ([], [fx.place_response(2)], [fx.captured([])]):
            with self.subTest(responses=responses), self.assertRaises(ValueError):
                plc_par.parse_responses(responses, self.entry)

    def test_attribute_availability(self) -> None:
        """To preserve unavailable attributes rather than dropping their false availability value."""

        record = fx.place_record()
        record[100] = [None, [["access", "Accessibility", [["wheelchair", "Wheelchair access", [None, None, [0, "Unavailable"]]]]]]]
        result = plc_par.parse_responses([fx.captured([None] * 6 + [record])], self.entry)
        item = result["details"]["attributes"][0]["items"][0]
        self.assertIs(item["available"], False)
        self.assertEqual(item["description"], "Unavailable")

    def test_place_navigation_and_request_matching(self) -> None:
        """To navigate in English by place ID and capture only matching place-preview traffic."""

        browser = Mock()
        browser.capture.return_value = [fx.place_response()]
        result = plc_clct.collect_place(browser, self.entry)
        params = parse_qs(urlsplit(result["url"]).query)
        self.assertEqual(params["query_place_id"], ["place-1"])
        self.assertEqual(params["query"], ["Restaurant 1"])
        self.assertEqual(params["hl"], ["en"])
        matches = browser.capture.call_args.args[1]
        self.assertTrue(matches("https://www.google.com/maps/preview/place?pb=!1s0x1:0x1!2sother"))
        self.assertFalse(matches("https://www.google.com/maps/preview/place?pb=!1s0x1:0x2"))
        self.assertFalse(matches("https://example.com/maps/preview/place?pb=!1s0x1:0x1"))
        self.assertEqual(result["reviews"][0]["photo_urls"], ["https://example.com/photo.jpg"])

    def test_missing_place_identifiers(self) -> None:
        """To reject navigation without a usable name or place ID."""

        for place in ({}, {"name": "Restaurant"}, {"place_id": "place-1"}):
            with self.subTest(place=place), self.assertRaises(ValueError):
                plc_clct.build_place_url(place)


if __name__ == "__main__":
    unittest.main()
