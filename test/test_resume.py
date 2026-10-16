import contextlib
import csv
import io
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch

from src.common import export as expt
from src import main
from src.common import resume as resu
from test import fixtures as fx


class ResumeTests(unittest.TestCase):
    def setUp(self) -> None:
        """To test real result and raw files while replacing browser and network operations."""

        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.enterContext(patch.object(main.ut, "DATA_DIR", self.root))
        self.constructor = self.enterContext(patch.object(main.br, "Browser"))
        self.resolve = self.enterContext(patch.object(main.geo, "resolve_location"))
        self.search = self.enterContext(patch.object(main.ser_clct, "collect_search"))
        self.search.return_value = fx.result(3, location=False)
        for entry in self.search.return_value["places"]:
            entry.update(completed=False, details=None, reviews=[], url=None, raw_responses=[])
        self.place = self.enterContext(patch.object(main.plc_clct, "collect_place"))
        self.place.side_effect = self._details
        self.sleep = self.enterContext(patch.object(main.time, "sleep"))
        self.enterContext(patch.object(main.ut, "logging_error"))
        self.enterContext(contextlib.redirect_stdout(io.StringIO()))
        self.clock = self.enterContext(patch.object(main, "datetime"))
        self.started_at = datetime(2026, 10, 16, 14, 30, 5, tzinfo=timezone.utc)
        self.clock.now.return_value.astimezone.return_value = self.started_at
        self.clock.fromisoformat.side_effect = datetime.fromisoformat
        self.conditions = {"query": "restaurants", "location": None, "zoom": 14, "language": "en", "max_places": 30}

    def _details(self, browser: Mock, entry: dict, quiet_period: float, language: str) -> dict:
        """To provide empty reviews and recognizable raw bodies for successfully fetched details."""

        return {"details": {"opening_status": "Open"}, "reviews": [], "url": "https://example.com/place",
                "raw_responses": [{"body": "RAW DETAIL " + entry["place"]["place_id"], "status": 200}]}

    def _path(self, location: str | None = None) -> Path:
        """To locate the canonical JSON file using the original execution timestamp."""

        return expt.result_directory("restaurants", location) / "result_2026-10-16_14-30-05.json"

    def _read(self, location: str | None = None) -> dict:
        """To inspect the normal result file without a separate checkpoint wrapper."""

        return json.loads(self._path(location).read_text(encoding="utf-8"))

    def test_normal_run_saves_search_and_each_completed_card(self) -> None:
        """To persist per-card states in the result itself and retain all completed data."""

        snapshots = []
        original = expt.save_progress

        def save(result: dict, started_at: datetime, **kwargs: object) -> None:
            """To capture states while preserving real incremental file updates."""

            original(result, started_at, **kwargs)
            snapshots.append(self._read())

        with patch.object(expt, "save_progress", side_effect=save):
            main.run("restaurants")
        self.assertEqual([[entry["completed"] for entry in result["places"]] for result in snapshots],
                         [[False, False, False], [True, False, False], [True, True, False], [True, True, True]])
        result = self._read()
        self.assertEqual(set(result), {"search", "places"})
        self.assertTrue(all(entry["completed"] for entry in result["places"]))
        self.assertNotIn("raw_responses", result["search"])
        self.assertTrue(all("raw_responses" not in entry for entry in result["places"]))
        self.assertFalse(list(self.root.rglob("checkpoint_*.json")))
        self.assertEqual(len(list(self._path().parent.iterdir())), 3)

    def test_failure_then_resume_skips_search_and_finished_cards(self) -> None:
        """To recover completed cards, raw bodies, and original filenames after a detail failure."""

        self.place.side_effect = [self._details(None, self.search.return_value["places"][0], 1.5, "en"), RuntimeError("blocked")]
        with self.assertRaisesRegex(RuntimeError, "blocked"):
            main.run("restaurants")
        self.assertEqual([entry["completed"] for entry in self._read()["places"]], [True, False, False])
        self.clock.now.return_value.astimezone.return_value = self.started_at + timedelta(days=1)
        self.search.reset_mock()
        self.place.reset_mock()
        self.sleep.reset_mock()
        self.place.side_effect = self._details
        main.run(" restaurants ", timeout=10, headless=True)
        self.search.assert_not_called()
        self.resolve.assert_not_called()
        self.assertEqual([call.args[1]["place"]["place_id"] for call in self.place.call_args_list], ["place-2", "place-3"])
        self.sleep.assert_called_once_with(5)
        loaded = resu.load_result(self.conditions)
        self.assertEqual(loaded["search"]["raw_responses"][0]["body"], "RAW SEARCH\nsecond line")
        self.assertEqual([entry["raw_responses"][0]["body"] for entry in loaded["places"]],
                         [f"RAW DETAIL place-{index}" for index in (1, 2, 3)])
        self.assertEqual(len(list(self._path().parent.glob("result_*.json"))), 1)

    def test_increasing_detail_limit_resumes_remaining_cards(self) -> None:
        """To continue an experimental limited run by increasing the limit and then requesting all cards."""

        main.run("restaurants", max_place_details=1)
        self.assertEqual([entry["completed"] for entry in self._read()["places"]], [True, False, False])
        self.place.reset_mock()
        main.run("restaurants", max_place_details=2)
        self.assertEqual(self.place.call_count, 1)
        self.assertEqual(self.place.call_args.args[1]["place"]["place_id"], "place-2")
        self.assertEqual([entry["completed"] for entry in self._read()["places"]], [True, True, False])
        self.place.reset_mock()
        main.run("restaurants")
        self.assertEqual(self.place.call_count, 1)
        self.assertEqual(self.place.call_args.args[1]["place"]["place_id"], "place-3")
        self.assertEqual(self.search.call_count, 1)

    def test_lower_limit_does_not_reset_completion(self) -> None:
        """To preserve finished cards when rerunning with a lower experimental limit."""

        main.run("restaurants", max_place_details=2)
        self.place.reset_mock()
        main.run("restaurants", max_place_details=1)
        self.place.assert_not_called()
        self.assertEqual([entry["completed"] for entry in self._read()["places"]], [True, True, False])

    def test_zero_limit_preserves_result_for_later_details(self) -> None:
        """To save search-only results and later fetch details without repeating search."""

        main.run("restaurants", max_place_details=0)
        self.place.assert_not_called()
        self.assertTrue(all(not entry["completed"] for entry in self._read()["places"]))
        main.run("restaurants", max_place_details=50)
        self.assertEqual(self.place.call_count, 3)
        self.assertEqual(self.search.call_count, 1)

    def test_empty_search_result_can_be_reloaded(self) -> None:
        """To retain valid empty results and raw sidecars without creating unnecessary browser requests."""

        self.search.return_value["places"] = []
        main.run("restaurants")
        self.assertEqual(resu.load_result(self.conditions)["places"], [])
        main.run("restaurants")
        self.place.assert_not_called()
        self.assertEqual(self.search.call_count, 1)

    def test_complete_result_is_reused_without_browser_start(self) -> None:
        """To retain completed results and avoid repeated browser requests on matching reruns."""

        main.run("restaurants")
        self.constructor.return_value.start.reset_mock()
        self.place.reset_mock()
        main.run("restaurants")
        self.constructor.return_value.start.assert_not_called()
        self.place.assert_not_called()
        self.assertEqual(self.search.call_count, 1)
        self.assertTrue(all(entry["completed"] for entry in self._read()["places"]))

    def test_search_failure_creates_no_result(self) -> None:
        """To create no resumable file when search itself fails."""

        self.search.side_effect = RuntimeError("search failed")
        with self.assertRaisesRegex(RuntimeError, "search failed"):
            main.run("restaurants")
        self.assertFalse(self._path().exists())
        self.place.assert_not_called()

    def test_keyboard_interrupt_keeps_last_success(self) -> None:
        """To retain saved cards and close the browser after a user interruption."""

        self.place.side_effect = [{}, KeyboardInterrupt()]
        with self.assertRaises(KeyboardInterrupt):
            main.run("restaurants")
        self.constructor.return_value.close.assert_called_once()
        self.assertEqual([entry["completed"] for entry in self._read()["places"]], [True, False, False])

    def test_empty_details_are_completed_by_success(self) -> None:
        """To mark successful empty details complete instead of inferring state from content."""

        self.place.side_effect = [{"details": None, "reviews": []}, RuntimeError("stop")]
        with self.assertRaisesRegex(RuntimeError, "stop"):
            main.run("restaurants")
        self.assertTrue(self._read()["places"][0]["completed"])

    def test_region_lookup_is_skipped_on_resume(self) -> None:
        """To reuse the saved region coordinates while matching normalized input region names."""

        self.resolve.return_value = fx.result()["search"]["location"]
        self.search.return_value["search"]["location"] = self.resolve.return_value
        self.place.side_effect = RuntimeError("stop")
        with self.assertRaises(RuntimeError):
            main.run("restaurants", location=" New York ")
        self.resolve.reset_mock()
        self.place.side_effect = self._details
        main.run("restaurants", location="New York")
        self.resolve.assert_not_called()
        self.assertTrue(all(entry["completed"] for entry in self._read("New York")["places"]))

    def test_csv_and_text_keep_canonical_json_and_completion(self) -> None:
        """To keep a resumable JSON alongside optional CSV or TXT exports without recollecting."""

        main.run("restaurants", max_place_details=1, file_format="csv")
        path = self._path().with_suffix(".csv")
        with path.open(encoding="utf-8-sig", newline="") as stream:
            self.assertEqual([row["completed"] for row in csv.DictReader(stream)], ["True", "False", "False"])
        main.run("restaurants", file_format="txt")
        self.assertEqual(self.search.call_count, 1)
        self.assertTrue(all(entry["completed"] for entry in self._read()["places"]))
        self.assertIn("completed: True", self._path().with_suffix(".txt").read_text(encoding="utf-8"))

    def test_failed_final_export_retries_without_refetching(self) -> None:
        """To recover optional final export failures after all card states have been persisted."""

        original = expt.save_results

        def fail_csv(result: dict, started_at: datetime, file_format: str = "json", **kwargs: object) -> None:
            """To fail CSV output while leaving normal JSON progress writes operational."""

            if file_format == "csv":
                raise OSError("export failed")
            original(result, started_at, file_format, **kwargs)

        with patch.object(expt, "save_results", side_effect=fail_csv), self.assertRaisesRegex(OSError, "export failed"):
            main.run("restaurants", file_format="csv")
        self.assertTrue(all(entry["completed"] for entry in self._read()["places"]))
        self.place.reset_mock()
        main.run("restaurants", file_format="csv")
        self.place.assert_not_called()
        self.assertTrue(self._path().with_suffix(".csv").exists())

    def test_failed_result_update_preserves_previous_json(self) -> None:
        """To retain the last valid JSON if publishing a newer card state fails."""

        main.run("restaurants", max_place_details=0)
        before = self._path().read_bytes()
        original = expt.os.replace

        def fail_json(source: Path, destination: Path) -> None:
            """To fail result replacement after staging raw responses."""

            if Path(destination).suffix == ".json":
                raise OSError("replace failed")
            original(source, destination)

        with patch.object(expt.os, "replace", side_effect=fail_json), self.assertRaisesRegex(OSError, "replace failed"):
            main.run("restaurants", max_place_details=1)
        self.assertEqual(self._path().read_bytes(), before)
        self.assertFalse(list(self._path().parent.glob(".export_*")))
        main.run("restaurants")
        self.assertTrue(all(entry["completed"] for entry in self._read()["places"]))

    def test_serialization_failure_preserves_saved_files(self) -> None:
        """To leave all published files unchanged when rendering a newer result fails."""

        main.run("restaurants", max_place_details=0)
        paths = expt.result_paths(self.search.return_value, self.started_at)
        before = {path: path.read_bytes() for path in paths}
        result = resu.load_result(self.conditions)
        result["places"][0]["details"] = object()
        with self.assertRaises(TypeError):
            expt.save_progress(result, self.started_at, overwrite=True)
        self.assertEqual(before, {path: path.read_bytes() for path in paths})
        self.assertFalse(list(self._path().parent.glob(".export_*")))

    def test_partial_raw_publish_can_resume(self) -> None:
        """To resume from the last JSON if a later raw-file replacement is interrupted."""

        main.run("restaurants", max_place_details=0)
        original = expt.os.replace

        def fail_place(source: Path, destination: Path) -> None:
            """To fail publication of a place raw file before the result commit."""

            if Path(destination).name.startswith("raw_response_place_"):
                raise OSError("raw failure")
            original(source, destination)

        with patch.object(expt.os, "replace", side_effect=fail_place), self.assertRaisesRegex(OSError, "raw failure"):
            main.run("restaurants", max_place_details=1)
        self.assertFalse(any(entry["completed"] for entry in self._read()["places"]))
        main.run("restaurants")
        self.assertTrue(all(entry["completed"] for entry in self._read()["places"]))

    def test_unrelated_existing_output_is_not_overwritten(self) -> None:
        """To preserve existing raw files on a fresh run that collides with their timestamp."""

        path = self._path().with_name("raw_response_search_2026-10-16_14-30-05.txt")
        path.parent.mkdir()
        path.write_text("unrelated", encoding="utf-8")
        with self.assertRaises(FileExistsError):
            main.run("restaurants")
        self.assertEqual(path.read_text(), "unrelated")
        self.assertFalse(self._path().exists())

    def test_original_error_survives_cleanup_failure(self) -> None:
        """To retain the collection error when closing Chrome also fails."""

        original = RuntimeError("collection failed")
        self.place.side_effect = original
        self.constructor.return_value.close.side_effect = OSError("close failed")
        with self.assertRaises(RuntimeError) as caught:
            main.run("restaurants")
        self.assertIs(caught.exception, original)
        self.assertFalse(any(entry["completed"] for entry in self._read()["places"]))

    def test_conditions_distinguish_search_but_not_limits_or_formats(self) -> None:
        """To match search identity independently of detail limits and requested export format."""

        main.run("restaurants", max_place_details=0)
        self.assertEqual(self._read()["search"]["conditions"], self.conditions)
        for changes in ({"query": "cafes"}, {"location": "Tokyo"}, {"zoom": 13}, {"language": "ja"}, {"max_places": 40}):
            with self.subTest(changes=changes):
                self.assertIsNone(resu.load_result({**self.conditions, **changes}))
        self.assertIsNotNone(resu.load_result(dict(reversed(list(self.conditions.items())))))

    def test_corrupt_result_prevents_new_search(self) -> None:
        """To stop with the damaged result path instead of replacing saved work with a fresh search."""

        self._path().parent.mkdir()
        for text in ("{", "null", json.dumps({"search": {"conditions": self.conditions}})):
            with self.subTest(text=text):
                self._path().write_text(text, encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "Invalid result file.*result_"):
                    main.run("restaurants")
        self.constructor.assert_not_called()
        self.search.assert_not_called()

    def test_old_result_without_resume_metadata_is_not_overwritten(self) -> None:
        """To leave pre-resume result files untouched and start new searches at a new timestamp."""

        self._path().parent.mkdir()
        self._path().write_text(json.dumps(fx.result(location=False)), encoding="utf-8")
        before = self._path().read_bytes()
        self.clock.now.return_value.astimezone.return_value = self.started_at + timedelta(seconds=1)
        main.run("restaurants", max_place_details=0)
        self.assertEqual(self._path().read_bytes(), before)
        self.assertEqual(self.search.call_count, 1)

    def test_multiple_unfinished_results_report_both_paths(self) -> None:
        """To reject ambiguous unfinished executions rather than choosing one silently."""

        main.run("restaurants", max_place_details=0)
        result = resu.load_result(self.conditions)
        later = self.started_at + timedelta(seconds=1)
        result["search"]["started_at"] = later.isoformat()
        expt.save_progress(result, later)
        with self.assertRaisesRegex(ValueError, "Multiple unfinished results") as caught:
            resu.load_result(self.conditions)
        self.assertIn(self._path().name, str(caught.exception))
        self.assertIn("result_2026-10-16_14-30-06.json", str(caught.exception))

    def test_latest_complete_result_is_selected(self) -> None:
        """To reuse the latest completed execution when no unfinished matching result remains."""

        main.run("restaurants")
        result = resu.load_result(self.conditions)
        later = self.started_at + timedelta(seconds=1)
        result["search"]["started_at"] = later.isoformat()
        expt.save_progress(result, later)
        self.assertEqual(resu.load_result(self.conditions)["search"]["started_at"], later.isoformat())

    def test_raw_round_trip_preserves_unicode_crlf_and_delimiters(self) -> None:
        """To restore exact raw bodies even when they contain line endings and apparent record delimiters."""

        body = "\u65e5\u672c\u8a9e\r\nEntry-Index: 99\n--- End response ---\nMetadata: {}\n"
        self.search.return_value["search"]["raw_responses"][0]["body"] = body
        main.run("restaurants", max_place_details=0)
        loaded = resu.load_result(self.conditions)
        self.assertEqual(loaded["search"]["raw_responses"][0]["body"], body)

    def test_missing_or_corrupt_raw_file_is_reported(self) -> None:
        """To stop without dropping saved response data when a sidecar is missing or damaged."""

        main.run("restaurants", max_place_details=0)
        path = self._path().with_name("raw_response_search_2026-10-16_14-30-05.txt")
        original = path.read_bytes()
        path.unlink()
        with self.assertRaises(FileNotFoundError):
            resu.load_result(self.conditions)
        path.write_bytes(original[:-10])
        with self.assertRaisesRegex(ValueError, "Invalid raw response file"):
            resu.load_result(self.conditions)

    def test_boolean_completion_flags_are_required(self) -> None:
        """To reject incompatible completion values rather than treating arbitrary truthy values as complete."""

        main.run("restaurants", max_place_details=0)
        result = self._read()
        result["places"][0]["completed"] = "true"
        self._path().write_text(json.dumps(result), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Invalid result file"):
            resu.load_result(self.conditions)


if __name__ == "__main__":
    unittest.main()
