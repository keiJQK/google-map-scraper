import contextlib
import io
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from src import main
from test import fixtures as fx


class WorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        """To isolate incremental results and replace external operations and final saving."""

        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.enterContext(patch.object(main.ut, "DATA_DIR", Path(directory.name)))
        self.enterContext(patch.object(main.resu, "load_result", return_value=None))
        self.enterContext(patch.object(main.expt, "save_progress"))
        self.constructor = self.enterContext(patch.object(main.br, "Browser"))
        self.browser = self.constructor.return_value
        self.search = self.enterContext(patch.object(main.ser_clct, "collect_search", return_value=fx.result(4)))
        self.place = self.enterContext(patch.object(main.plc_clct, "collect_place", return_value={}))
        self.resolve = self.enterContext(patch.object(main.geo, "resolve_location", return_value=fx.result()["search"]["location"]))
        self.save = self.enterContext(patch.object(main.expt, "save_results"))
        self.sleep = self.enterContext(patch.object(main.time, "sleep"))
        self.log_error = self.enterContext(patch.object(main.ut, "logging_error"))
        self.clock = self.enterContext(patch.object(main, "datetime"))
        self.started_at = datetime(2026, 10, 16, 14, 30, 5, tzinfo=timezone.utc)
        self.clock.now.return_value.astimezone.return_value = self.started_at
        self.enterContext(contextlib.redirect_stdout(io.StringIO()))

    def test_workflow_order_and_shared_timestamp(self) -> None:
        """To resolve before startup, close before saving, and share the original execution timestamp."""

        events = []
        location = self.resolve.return_value
        result = self.search.return_value
        self.resolve.side_effect = lambda *args: events.append("resolve") or location
        self.browser.start.side_effect = lambda: events.append("start")
        self.search.side_effect = lambda *args, **kwargs: events.append("search") or result
        self.place.side_effect = lambda *args: events.append("place") or {}
        self.browser.close.side_effect = lambda: events.append("close")
        self.save.side_effect = lambda *args, **kwargs: events.append("save")
        self.assertIsNone(main.run("restaurants", location="New York", file_format="csv"))
        self.assertEqual(events, ["resolve", "start", "search", "place", "place", "place", "place", "close", "save"])
        self.save.assert_called_once_with(result, self.started_at, "csv", overwrite=True)
        self.clock.now.assert_called_once()
        self.assertEqual(len(result["places"]), 4)

    def test_wait_only_between_detail_targets(self) -> None:
        """To fetch all places by default and wait only between actual detail requests."""

        for count in (0, 1, 2, 5):
            with self.subTest(count=count):
                self.search.return_value = fx.result(count, location=False)
                self.place.reset_mock()
                self.sleep.reset_mock()
                main.run("restaurants")
                self.assertEqual(self.place.call_count, count)
                self.assertEqual(self.sleep.call_count, max(0, count - 1))
        self.resolve.assert_not_called()

    def test_detail_limit_preserves_all_search_cards(self) -> None:
        """To limit detail requests or skip them while saving every captured search card."""

        for limit in (0, 1, 2, 10):
            with self.subTest(limit=limit):
                result = fx.result(4, location=False)
                self.search.return_value = result
                self.place.reset_mock()
                self.sleep.reset_mock()
                self.save.reset_mock()
                main.run("restaurants", max_place_details=limit)
                expected = min(limit, 4)
                self.assertEqual(self.place.call_count, expected)
                self.assertEqual(self.sleep.call_count, max(0, expected - 1))
                self.assertEqual([call.args[1] for call in self.place.call_args_list], result["places"][:limit])
                self.assertEqual(len(self.save.call_args.args[0]["places"]), 4)

    def test_failures_close_browser_and_skip_saving(self) -> None:
        """To release browser state and propagate failures from initialization, search, or place collection."""

        for operation in (self.resolve, self.browser.start, self.search, self.place):
            with self.subTest(operation=operation):
                self.browser.close.reset_mock()
                self.save.reset_mock()
                operation.side_effect = RuntimeError("failed")
                with self.assertRaisesRegex(RuntimeError, "failed"):
                    main.run("restaurants", location="New York")
                self.browser.close.assert_called_once()
                self.save.assert_not_called()
                operation.side_effect = None

    def test_save_failure_is_propagated_after_cleanup(self) -> None:
        """To report output failures after closing Chrome rather than leaving the browser active."""

        self.save.side_effect = OSError("disk unavailable")
        with self.assertRaisesRegex(OSError, "disk unavailable"):
            main.run("restaurants")
        self.browser.close.assert_called_once()
        self.log_error.assert_called_once()

    def test_invalid_inputs_prevent_browser_construction(self) -> None:
        """To validate formats, counts, zoom levels, and search terms before external operations."""

        for kwargs in ({"file_format": "xml"}, {"max_places": 0}, {"zoom": 22}, {"query": " "},
                       *({"max_place_details": value} for value in (-1, True, False, 1.5, "2"))):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                main.run(**{"query": "restaurants", **kwargs})
        self.constructor.assert_not_called()
        self.resolve.assert_not_called()
        self.save.assert_not_called()


if __name__ == "__main__":
    unittest.main()
