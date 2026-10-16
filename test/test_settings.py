import contextlib
import io
import tempfile
import tomllib
import unittest
from pathlib import Path
from unittest.mock import patch

from src import main
from src.common import settings as cfg


class SettingsTests(unittest.TestCase):
    def setUp(self) -> None:
        """To isolate settings files and avoid changing the user's personal configuration."""

        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.enterContext(patch.object(cfg.ut, "CONFIG_DIR", self.directory))

    def _write(self, text: str, name: str = "settings.toml") -> Path:
        """To write one temporary TOML file for a settings scenario."""

        path = self.directory / name
        path.write_text(text, encoding="utf-8")
        return path

    def test_minimal_settings_leave_defaults_to_run(self) -> None:
        """To require only the query and avoid duplicating optional run defaults in the loader."""

        self._write('[search]\nquery = " restaurants "\n')
        self.assertEqual(cfg.load_settings(), {"query": "restaurants"})

    def test_all_sections_map_to_run_arguments(self) -> None:
        """To convert a complete TOML file into supported Python keyword arguments."""

        path = self._write(
            '[search]\nquery = "cafes"\nlocation = "Paris, France"\nzoom = 13\n'
            'max_places = 20\nmax_place_details = 2\n[output]\nformat = "csv"\n'
            '[browser]\nheadless = false\ntimeout = 12.5\nchrome_binary = \'C:\\Chrome\\chrome.exe\'\n'
        )
        self.assertEqual(cfg.load_settings(path), {
            "query": "cafes", "location": "Paris, France", "zoom": 13, "max_places": 20,
            "max_place_details": 2, "file_format": "csv", "headless": False,
            "timeout": 12.5, "chrome_binary": "C:\\Chrome\\chrome.exe",
        })

    def test_output_format_names(self) -> None:
        """To accept documented format names and convert text to the existing txt exporter format."""

        for value, expected in (("json", "json"), ("csv", "csv"), ("text", "txt"), ("txt", "txt"), (" TEXT ", "txt")):
            with self.subTest(value=value):
                path = self._write(f'[search]\nquery = "cafes"\n[output]\nformat = "{value}"\n')
                self.assertEqual(cfg.load_settings(path)["file_format"], expected)

    def test_detail_limit_zero_or_above_search_target(self) -> None:
        """To allow search-only runs and limits above the card target without cross-limit rejection."""

        for limit in (0, 50):
            with self.subTest(limit=limit):
                path = self._write(f'[search]\nquery = "cafes"\nmax_places = 30\nmax_place_details = {limit}\n')
                self.assertEqual(cfg.load_settings(path)["max_place_details"], limit)

    def test_missing_file_explains_setup(self) -> None:
        """To stop with setup guidance rather than falling back to example searches."""

        with self.assertRaisesRegex(FileNotFoundError, "settings.example.toml"):
            cfg.load_settings()
        self.assertEqual(list(self.directory.iterdir()), [])

    def test_malformed_toml_mentions_the_file(self) -> None:
        """To identify syntax errors and the selected file in the reported error."""

        path = self._write('[search\nquery = "cafes"\n')
        with self.assertRaisesRegex(ValueError, "Invalid TOML.*settings.toml"):
            cfg.load_settings(path)

    def test_unknown_sections_keys_and_non_tables(self) -> None:
        """To reject misspelled settings and incorrectly shaped sections instead of silently ignoring them."""

        for text in ('[serach]\nquery = "cafes"', '[search]\nquery = "cafes"\nmax_place = 2',
                     'search = "cafes"', '[search]\nquery = "cafes"\n[output]\nfile_format = "csv"'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                cfg.load_settings(self._write(text))

    def test_required_and_optional_strings(self) -> None:
        """To require a nonempty search query and reject empty optional strings rather than guessing intent."""

        for text in ('', '[search]', '[search]\nquery = 2', '[search]\nquery = " "',
                     '[search]\nquery = "cafes"\nlocation = ""',
                     '[search]\nquery = "cafes"\n[browser]\nchrome_binary = 1'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                cfg.load_settings(self._write(text))

    def test_invalid_search_values(self) -> None:
        """To reject negative limits, boolean integers, invalid zoom levels, and zero card targets."""

        for setting in ('max_places = 0', 'max_places = true', 'zoom = 22', 'zoom = 1.5',
                        'max_place_details = -1', 'max_place_details = true', 'max_place_details = "2"'):
            with self.subTest(setting=setting), self.assertRaises(ValueError):
                cfg.load_settings(self._write('[search]\nquery = "cafes"\n' + setting))

    def test_invalid_browser_values_and_formats(self) -> None:
        """To validate browser types and finite timeouts before accepting an output format."""

        for setting in ('[browser]\nheadless = "false"', '[browser]\nheadless = 1',
                        '[browser]\ntimeout = 0', '[browser]\ntimeout = true',
                        '[browser]\ntimeout = inf', '[browser]\ntimeout = nan',
                        '[output]\nformat = "xml"', '[output]\nformat = 1'):
            with self.subTest(setting=setting), self.assertRaises(ValueError):
                cfg.load_settings(self._write('[search]\nquery = "cafes"\n' + setting))

    def test_explicit_relative_path(self) -> None:
        """To resolve explicit relative paths from the current directory rather than the default config directory."""

        self._write('[search]\nquery = "cafes"', "paris.toml")
        with contextlib.chdir(self.directory):
            self.assertEqual(cfg.load_settings("paris.toml"), {"query": "cafes"})

    def test_public_example_is_valid_and_uses_optional_comments(self) -> None:
        """To keep the published example executable while leaving regional and detail limits optional."""

        path = Path(__file__).resolve().parents[1] / "config" / "settings.example.toml"
        with path.open("rb") as stream:
            document = tomllib.load(stream)
        options = cfg.load_settings(path)
        self.assertEqual(document["search"]["query"], "Italian restaurants")
        self.assertEqual(options["file_format"], "json")
        self.assertNotIn("location", options)
        self.assertNotIn("max_place_details", options)


class CliSettingsTests(unittest.TestCase):
    def test_default_config_calls_run_with_loaded_arguments(self) -> None:
        """To use the default configuration without retaining positional or search-specific CLI options."""

        options = {"query": "cafes", "max_place_details": 0, "file_format": "txt"}
        with patch.object(main.cfg, "load_settings", return_value=options) as load, patch.object(main, "run") as run:
            main.main_cli([])
            load.assert_called_once_with(None)
            run.assert_called_once_with(**options)

    def test_explicit_config(self) -> None:
        """To pass an explicitly selected file path to the loader before starting collection."""

        with patch.object(main.cfg, "load_settings", return_value={"query": "cafes"}) as load, patch.object(main, "run") as run:
            main.main_cli(["--config", "config/paris.toml"])
            load.assert_called_once_with(Path("config/paris.toml"))
            run.assert_called_once_with(query="cafes")

    def test_config_error_never_calls_run(self) -> None:
        """To report invalid or missing configuration as CLI errors without starting the collector."""

        for error in (FileNotFoundError("missing settings"), ValueError("bad settings")):
            with self.subTest(error=error), patch.object(main.cfg, "load_settings", side_effect=error), \
                    patch.object(main, "run") as run, contextlib.redirect_stderr(io.StringIO()) as stderr:
                with self.assertRaises(SystemExit) as stopped:
                    main.main_cli([])
                self.assertEqual(stopped.exception.code, 2)
                self.assertIn(str(error), stderr.getvalue())
                run.assert_not_called()

    def test_actual_settings_file_to_run(self) -> None:
        """To connect real TOML parsing to CLI dispatch while replacing collection with a mock."""

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.toml"
            path.write_text('[search]\nquery = "cafes"\nmax_place_details = 0\n[output]\nformat = "text"', encoding="utf-8")
            with patch.object(main, "run") as run:
                main.main_cli(["--config", str(path)])
                run.assert_called_once_with(query="cafes", max_place_details=0, file_format="txt")


if __name__ == "__main__":
    unittest.main()
