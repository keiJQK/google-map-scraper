import copy
import csv
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from src.common import export as expt
from test import fixtures as fx


class ExportTests(unittest.TestCase):
    def setUp(self) -> None:
        """To direct every exported file to a temporary directory with a fixed execution timestamp."""

        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.enterContext(patch.object(expt.ut, "DATA_DIR", self.root))
        self.started_at = datetime(2026, 10, 16, 14, 30, 5, tzinfo=timezone.utc)
        self.folder = self.root / "New York_restaurants"

    def test_json_and_separate_raw_files(self) -> None:
        """To save three matching filenames and remove raw fields without modifying the input result."""

        result = fx.result()
        original = copy.deepcopy(result)
        self.assertIsNone(expt.save_results(result, self.started_at))
        self.assertEqual({path.name for path in self.folder.iterdir()}, {
            "result_2026-10-16_14-30-05.json", "raw_response_search_2026-10-16_14-30-05.txt",
            "raw_response_place_2026-10-16_14-30-05.txt",
        })
        saved = json.loads((self.folder / "result_2026-10-16_14-30-05.json").read_text(encoding="utf-8"))
        self.assertNotIn("raw_responses", saved["search"])
        self.assertTrue(all("raw_responses" not in entry for entry in saved["places"]))
        self.assertEqual(saved["places"][0]["reviews"], result["places"][0]["reviews"])
        self.assertEqual(result, original)
        search = (self.folder / "raw_response_search_2026-10-16_14-30-05.txt").read_text(encoding="utf-8")
        places = (self.folder / "raw_response_place_2026-10-16_14-30-05.txt").read_text(encoding="utf-8")
        self.assertIn("RAW SEARCH\nsecond line", search)
        self.assertIn("RAW PLACE 1\nsecond line", places)
        self.assertIn("RAW PLACE 2\nsecond line", places)
        self.assertIn("place_id: place-2", places)
        self.assertIn("https://example.com/preview/2", places)

    def test_csv_round_trip_and_bom(self) -> None:
        """To preserve nested reviews, newlines, metadata, and categories in one CSV row per place."""

        result = fx.result()
        expt.save_results(result, self.started_at, "csv")
        path = self.folder / "result_2026-10-16_14-30-05.csv"
        self.assertTrue(path.read_bytes().startswith(b"\xef\xbb\xbf"))
        with path.open(encoding="utf-8-sig", newline="") as stream:
            rows = list(csv.DictReader(stream))
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["place_name"], "Restaurant 1")
        self.assertEqual(rows[0]["location_query"], "New York")
        self.assertEqual(json.loads(rows[0]["reviews"]), result["places"][0]["reviews"])
        self.assertEqual(json.loads(rows[0]["place_categories"]), ["Italian restaurant"])
        self.assertFalse(any("raw_responses" in key for key in rows[0]))

    def test_text_output(self) -> None:
        """To retain readable search and place sections without copying raw response bodies."""

        expt.save_results(fx.result(), self.started_at, "txt")
        text = (self.folder / "result_2026-10-16_14-30-05.txt").read_text(encoding="utf-8")
        self.assertIn("Place 1: Restaurant 1", text)
        self.assertIn("https://example.com/photo.jpg", text)
        self.assertNotIn("raw_responses", text)
        self.assertNotIn("RAW SEARCH", text)

    def test_query_only_folder_and_empty_raw_responses(self) -> None:
        """To omit the region prefix when absent and explicitly mark missing response bodies."""

        result = fx.result(location=False)
        result["search"]["raw_responses"] = []
        result["places"][0]["raw_responses"] = []
        expt.save_results(result, self.started_at)
        directory = self.root / "restaurants"
        self.assertTrue(directory.is_dir())
        self.assertIn("No captured responses.", next(directory.glob("raw_response_search_*.txt")).read_text())
        self.assertIn("No captured responses.", next(directory.glob("raw_response_place_*.txt")).read_text())

    def test_empty_csv_keeps_columns(self) -> None:
        """To create a valid header and all three files when a search contains no places."""

        expt.save_results(fx.result(0), self.started_at, "csv")
        with next(self.folder.glob("result_*.csv")).open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            self.assertIn("place_name", reader.fieldnames)
            self.assertEqual(list(reader), [])
        self.assertEqual(len(list(self.folder.iterdir())), 3)

    def test_collision_preserves_existing_files(self) -> None:
        """To reject a duplicate execution timestamp without overwriting previously saved results."""

        expt.save_results(fx.result(), self.started_at)
        before = {path: path.read_bytes() for path in self.folder.iterdir()}
        with self.assertRaises(FileExistsError):
            expt.save_results(fx.result(), self.started_at)
        self.assertEqual(before, {path: path.read_bytes() for path in self.folder.iterdir()})

    def test_unsafe_folder_names_stay_inside_data_directory(self) -> None:
        """To handle traversal text, forbidden characters, reserved names, and long folder names safely."""

        for index, query in enumerate(("../outside", "..\\outside", "a:b?c*", "CON", "NUL.txt", "..", "a" * 400)):
            with self.subTest(query=query), patch.object(expt.ut, "DATA_DIR", self.root / f"case-{index}"):
                result = fx.result(location=False)
                result["search"]["query"] = query
                expt.save_results(result, self.started_at)
        for path in self.root.rglob("result_*.json"):
            self.assertEqual(path.parent.parent.parent, self.root)
            self.assertNotIn(path.parent.name, ("CON", "NUL.txt"))
            self.assertLessEqual(len(path.parent.name), 161)

    def test_format_validation_precedes_file_creation(self) -> None:
        """To normalize supported format names and reject unsupported values without creating files."""

        self.assertEqual(expt.validate_file_format(" CSV "), "csv")
        for value in ("xml", "", None, True):
            with self.subTest(value=value), self.assertRaises(ValueError):
                expt.save_results(fx.result(), self.started_at, value)
        self.assertEqual(list(self.root.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
