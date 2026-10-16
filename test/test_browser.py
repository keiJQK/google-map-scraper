import base64
import itertools
import json
import unittest
from typing import Any
from unittest.mock import MagicMock, patch

from src import browser as br


def _event(method: str, request_id: str = "r1", **params: Any) -> dict[str, str]:
    """To encode a fictional Chrome performance-log event."""

    return {"message": json.dumps({"message": {"method": "Network." + method,
                                             "params": {"requestId": request_id, **params}}})}


def _events(request_id: str = "r1", status: int = 200) -> list[dict[str, str]]:
    """To provide an ordered request, response, and completion sequence."""

    url = "https://example.com/search"
    return [_event("requestWillBeSent", request_id, request={"url": url}),
            _event("responseReceived", request_id, response={"url": url, "status": status}),
            _event("loadingFinished", request_id)]


class BrowserTests(unittest.TestCase):
    def setUp(self) -> None:
        """To prepare a fake driver and advancing clock without launching Chrome or sleeping."""

        self.browser = br.Browser(timeout=5)
        self.driver = MagicMock()
        self.driver.current_url = "https://example.com"
        self.driver.find_elements.return_value = []
        self.driver.get_log.return_value = []
        self.driver.execute_cdp_cmd.return_value = {"body": "response body"}
        self.browser.driver = self.driver
        for setting in (patch.object(br.time, "monotonic", side_effect=itertools.count(0, 0.1)),
                        patch.object(br.time, "sleep")):
            setting.start()
            self.addCleanup(setting.stop)

    def test_start_and_idempotent_cleanup(self) -> None:
        """To configure English preferences and CDP logging before use and close Chrome only once."""

        browser = br.Browser(headless=True, chrome_binary="custom-chrome")
        with patch.object(br.webdriver, "Chrome", return_value=self.driver) as chrome:
            browser.start()
            options = chrome.call_args.kwargs["options"]
            self.assertEqual(options.capabilities["goog:loggingPrefs"], {"performance": "ALL"})
            self.assertIn("--headless=new", options.arguments)
            self.assertIn("--lang=en-US", options.arguments)
            self.assertEqual(options.experimental_options["prefs"]["intl.accept_languages"], "en-US,en")
            self.assertEqual(options.binary_location, "custom-chrome")
            self.assertEqual(self.driver.execute_cdp_cmd.call_args_list[0].args[0], "Network.enable")
            with self.assertRaises(RuntimeError):
                browser.start()
            browser.close()
            browser.close()
        self.driver.quit.assert_called_once()

    def test_failed_startup_releases_driver(self) -> None:
        """To release Chrome when CDP setup fails."""

        browser = br.Browser()
        self.driver.execute_cdp_cmd.side_effect = RuntimeError("CDP unavailable")
        with patch.object(br.webdriver, "Chrome", return_value=self.driver), self.assertRaises(RuntimeError):
            browser.start()
        self.driver.quit.assert_called_once()
        self.assertIsNone(browser.driver)

    def test_navigation_capture_resets_old_events(self) -> None:
        """To discard previous-navigation events and capture the newly completed request."""

        self.browser._completed_requests.add("r1")
        self.driver.get_log.side_effect = [[], _events()]
        result = self.browser.capture("https://example.com", lambda url: url.endswith("/search"), 0)
        self.assertEqual(result, [{"request_id": "r1", "url": "https://example.com/search",
                                  "status": 200, "body": "response body"}])
        self.driver.get.assert_called_once_with("https://example.com")

    def test_scroll_capture_preserves_queue_and_deduplicates(self) -> None:
        """To capture queued prefetches once without navigating between batches."""

        self.driver.get_log.return_value = _events()
        self.assertEqual(len(self.browser.capture_responses(lambda _: True, 0)), 1)
        self.assertEqual(self.browser.capture_responses(lambda _: True, 0, required=False), [])
        self.driver.get_log.return_value = _events("r2")
        self.assertEqual(len(self.browser.capture_responses(lambda _: True, 0)), 1)
        self.assertEqual(self.driver.execute_cdp_cmd.call_count, 2)
        self.driver.get.assert_not_called()

    def test_base64_body(self) -> None:
        """To decode response text when CDP reports a Base64 body."""

        self.driver.get_log.return_value = _events()
        self.driver.execute_cdp_cmd.return_value = {"body": base64.b64encode(b"example").decode(), "base64Encoded": True}
        self.assertEqual(self.browser.capture_responses(lambda _: True, 0)[0]["body"], "example")

    def test_http_and_network_errors(self) -> None:
        """To report rejected and failed requests even when additional traffic is optional."""

        for batch in (_events(status=429), [_events()[0], _event("loadingFailed", errorText="disconnected")]):
            with self.subTest(batch=batch):
                self.browser._completed_requests.clear()
                self.driver.get_log.return_value = batch
                with self.assertRaises(RuntimeError):
                    self.browser.capture_responses(lambda _: True, 0, required=False)

    def test_pending_request_timeout(self) -> None:
        """To distinguish unfinished requests from a feed without additional traffic."""

        self.driver.get_log.return_value = [_events()[0]]
        with self.assertRaisesRegex(TimeoutError, "did not finish"):
            self.browser.capture_responses(lambda _: True, 0, required=False)

    def test_optional_and_required_missing_responses(self) -> None:
        """To allow empty scroll captures but reject missing initial responses."""

        self.assertEqual(self.browser.capture_responses(lambda _: True, 0, required=False), [])
        with self.assertRaisesRegex(TimeoutError, "No matching response"):
            self.browser.capture_responses(lambda _: True, 0)

    def test_visible_feed_and_ambiguity(self) -> None:
        """To use visibility and query labels to select one feed and reject ambiguous candidates."""

        first, second, hidden = MagicMock(), MagicMock(), MagicMock()
        first.get_attribute.return_value = "Other results"
        second.get_attribute.return_value = "Results for restaurants"
        hidden.is_displayed.return_value = False
        self.driver.find_elements.side_effect = lambda _, selector: [first, second, hidden] if selector == '[role="feed"]' else []
        self.driver.execute_script.return_value = True
        self.assertTrue(self.browser.scroll_search("restaurants"))
        self.assertIs(self.driver.execute_script.call_args.args[1], second)
        first.get_attribute.return_value = "restaurants"
        with self.assertRaisesRegex(RuntimeError, "uniquely"):
            self.browser.scroll_search("restaurants")

    def test_blocking_and_invalid_timeout(self) -> None:
        """To reject known blocking pages and invalid startup timeouts."""

        self.driver.current_url = "https://www.google.com/sorry/index"
        with self.assertRaisesRegex(RuntimeError, "blocked"):
            self.browser.capture_responses(lambda _: True, 0, required=False)
        for value in (0, -1, float("nan"), float("inf")):
            with self.subTest(value=value), self.assertRaises(ValueError):
                br.Browser(timeout=value)


if __name__ == "__main__":
    unittest.main()
