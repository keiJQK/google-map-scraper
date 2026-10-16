import unittest
from unittest.mock import Mock, patch

from src.search import collect as ser_clct
from src.search import parser as ser_par
from test import fixtures as fx


class SearchTests(unittest.TestCase):
    def test_url_with_and_without_region(self) -> None:
        """To request English search results and encode search terms with optional center and zoom."""

        self.assertEqual(ser_clct.build_search_url("a/b c"), "https://www.google.com/maps/search/a%2Fb%20c?hl=en")
        location = {"nominatim_latitude": 40.7, "nominatim_longitude": -74.0}
        self.assertIn("/@40.7,-74.0,14z?", ser_clct.build_search_url("restaurants", location))
        self.assertIn(",13z?", ser_clct.build_search_url("restaurants", location, 13))

    def test_invalid_inputs(self) -> None:
        """To reject invalid target counts, zoom levels, queries, and coordinates."""

        for value in (0, -1, True, 1.5):
            with self.subTest(count=value), self.assertRaises(ValueError):
                ser_clct.validate_max_places(value)
        for value in (-1, 22, True, 1.5):
            with self.subTest(zoom=value), self.assertRaises(ValueError):
                ser_clct.validate_zoom(value)
        with self.assertRaises(ValueError):
            ser_clct.build_search_url(" ")
        with self.assertRaises(ValueError):
            ser_clct.build_search_url("restaurants", {"nominatim_latitude": 91, "nominatim_longitude": 0})

    def test_parse_and_deduplicate_batches(self) -> None:
        """To extract profiles, skip advertisements, and rank unique places across overlapping batches."""

        result = ser_par.parse_responses([fx.search_response(1, 2), fx.search_response(2, 3)])
        self.assertEqual(result["center"], {"latitude": 40.7, "longitude": -74.0})
        self.assertEqual([entry["place"]["name"] for entry in result["places"]], ["Restaurant 1", "Restaurant 2", "Restaurant 3"])
        self.assertEqual([entry["rank"] for entry in result["places"]], [1, 2, 3])
        self.assertIsNone(result["places"][0]["details"])
        self.assertEqual(result["places"][0]["reviews"], [])

    def test_unsupported_responses(self) -> None:
        """To fail explicitly on empty input, malformed bodies, and unsupported layouts."""

        for responses in ([], [fx.captured([])], [{"body": "invalid", "url": "example"}]):
            with self.subTest(responses=responses), self.assertRaises(ValueError):
                ser_par.parse_responses(responses)

    def test_scroll_collects_whole_batches(self) -> None:
        """To combine parsed batches while retaining over-target places and all raw responses."""

        browser = Mock()
        browser.capture.return_value = [fx.search_response(1, 2)]
        browser.capture_responses.return_value = [fx.search_response(2, 3, 4)]
        result = ser_clct.collect_search(browser, "restaurants", max_places=3)
        self.assertEqual(len(result["places"]), 4)
        self.assertEqual(len(result["search"]["raw_responses"]), 2)
        browser.scroll_search.assert_called_once()
        matches = browser.capture.call_args.args[1]
        self.assertTrue(matches("https://www.google.com/search?tbm=map&q=restaurants&pb=!8i20"))
        self.assertFalse(matches("https://example.com/search?tbm=map&q=restaurants"))

    def test_sufficient_initial_batch(self) -> None:
        """To skip scrolling when initial results suffice and retain supplied location metadata."""

        browser = Mock()
        browser.capture.return_value = [fx.search_response(1, 2)]
        location = fx.result()["search"]["location"]
        result = ser_clct.collect_search(browser, "restaurants", max_places=1, location=location, zoom=13)
        self.assertEqual(result["search"]["location"], location)
        self.assertEqual(result["search"]["zoom"], 13)
        browser.scroll_search.assert_not_called()

    def test_bottom_retries(self) -> None:
        """To return partial results after repeated bottom attempts without unique additions."""

        browser = Mock()
        browser.capture.return_value = [fx.search_response(1)]
        browser.capture_responses.side_effect = [[fx.search_response(1)], [], []]
        browser.scroll_search.return_value = True
        self.assertEqual(len(ser_clct.collect_search(browser, "restaurants")["places"]), 1)
        self.assertEqual(browser.scroll_search.call_count, 3)

    def test_silent_midfeed_scrolls(self) -> None:
        """To keep scrolling through cards when intermediate movements issue no requests."""

        browser = Mock()
        browser.capture.return_value = [fx.search_response(1)]
        browser.scroll_search.side_effect = [False] * 4 + [True]
        browser.capture_responses.side_effect = [[], [], [], [], [fx.search_response(2)]]
        self.assertEqual(len(ser_clct.collect_search(browser, "restaurants", max_places=2)["places"]), 2)

    def test_scroll_limit_and_capture_failure(self) -> None:
        """To bound stalled searches while propagating actual capture errors."""

        browser = Mock()
        browser.capture.return_value = [fx.search_response(1)]
        browser.scroll_search.return_value = False
        browser.capture_responses.return_value = []
        with patch.object(ser_clct, "MAX_SCROLLS", 2), self.assertLogs(ser_clct.logger, level="WARNING"):
            self.assertEqual(len(ser_clct.collect_search(browser, "restaurants")["places"]), 1)
        browser.capture_responses.side_effect = RuntimeError("HTTP 429")
        with self.assertRaisesRegex(RuntimeError, "429"):
            ser_clct.collect_search(browser, "restaurants")


if __name__ == "__main__":
    unittest.main()
