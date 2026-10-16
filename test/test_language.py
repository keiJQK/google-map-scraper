import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlsplit

from src import browser as br
from src.common import language as lang
from src import main
from src.common import settings as cfg
from src.place import collect as plc_clct
from src.search import collect as ser_clct
from src.search import geocoding as geo
from test import fixtures as fx


class LanguageTests(unittest.TestCase):
    def setUp(self) -> None:
        """To isolate incrementally saved workflow results from the user's data directory."""

        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.enterContext(patch.object(main.ut, "DATA_DIR", Path(directory.name)))

    def test_tag_normalization_and_invalid_values(self) -> None:
        """To normalize common tags and reject malformed or multiple language preferences."""

        for supplied, expected in ((" JA ", "ja"), ("pt-br", "pt-BR"), ("zh-hant-tw", "zh-Hant-TW"), ("en", "en")):
            with self.subTest(supplied=supplied):
                self.assertEqual(lang.normalize_language(supplied), expected)
        for value in (None, True, 1, "", " ", "Japanese", "ja_JP", "en,ja", "ja?hl=en", "-ja"):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "language"):
                lang.normalize_language(value)

    def test_toml_language_and_omitted_default(self) -> None:
        """To load a normalized language from TOML while leaving omitted settings to run defaults."""

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.toml"
            for text, expected in (('[browser]\nlanguage = " JA "\n', "ja"), ("", None)):
                path.write_text('[search]\nquery = "cafes"\n' + text, encoding="utf-8")
                self.assertEqual(cfg.load_settings(path).get("language"), expected)
            for value in ('""', '"ja_JP"', "12", "false", '["en", "ja"]'):
                path.write_text('[search]\nquery = "cafes"\n[browser]\nlanguage = ' + value, encoding="utf-8")
                with self.subTest(value=value), self.assertRaisesRegex(ValueError, "language"):
                    cfg.load_settings(path)

    def test_browser_language_preferences(self) -> None:
        """To apply base and regional languages to Chrome without starting a real browser."""

        for language, locale, preferences in (("ja", "ja", "ja"), ("pt-br", "pt-BR", "pt-BR,pt"),
                                               ("en", "en-US", "en-US,en")):
            with self.subTest(language=language), patch.object(br.webdriver, "Chrome") as chrome:
                browser = br.Browser(language=language)
                browser.start()
                options = chrome.call_args.kwargs["options"]
                self.assertIn("--lang=" + locale, options.arguments)
                self.assertEqual(options.experimental_options["prefs"]["intl.accept_languages"], preferences)
                browser.close()

    def test_collection_uses_localized_navigation_urls(self) -> None:
        """To use the selected language in actual search and place collection navigation."""

        browser = Mock()
        browser.capture.return_value = [fx.search_response(1)]
        result = ser_clct.collect_search(browser, "restaurants", max_places=1, language="ja")
        self.assertEqual(parse_qs(urlsplit(result["search"]["url"]).query)["hl"], ["ja"])
        self.assertEqual(browser.capture.call_args.args[0], result["search"]["url"])
        browser.capture.return_value = [fx.place_response(1)]
        entry = plc_clct.collect_place(browser, result["places"][0], language="pt-br")
        self.assertEqual(parse_qs(urlsplit(entry["url"]).query)["hl"], ["pt-BR"])
        self.assertEqual(browser.capture.call_args.args[0], entry["url"])

    def test_geocoding_language_cache_isolation_and_reuse(self) -> None:
        """To request localized names and reuse only matching-language cache entries."""

        with tempfile.TemporaryDirectory() as directory, \
                patch.object(geo.ut, "NOMINATIM_CACHE_PATH", Path(directory) / "cache.sqlite3"), \
                patch.object(geo.time, "sleep"), patch.object(geo.requests, "get") as request:
            response = request.return_value.__enter__.return_value
            response.json.return_value = [{"display_name": "English name", "lat": "35", "lon": "139"}]
            english = geo.resolve_location("Example", language="en")
            self.assertEqual(request.call_args.kwargs["params"]["accept-language"], "en")
            response.json.return_value = [{"display_name": "Localized name", "lat": "35", "lon": "139"}]
            localized = geo.resolve_location("Example", language="ja")
            self.assertEqual(request.call_args.kwargs["params"]["accept-language"], "ja")
            self.assertEqual(geo.resolve_location("Example", language=" JA "), localized)
            self.assertEqual(geo.resolve_location("Example"), english)
            self.assertNotEqual(localized["nominatim_name"], english["nominatim_name"])
            self.assertEqual(request.call_count, 2)

    def test_run_passes_language_to_all_components(self) -> None:
        """To propagate one normalized setting through browser startup, geocoding, search, and place details."""

        with patch.object(main.br, "Browser") as constructor, \
                patch.object(main.geo, "resolve_location", return_value={}) as resolve, \
                patch.object(main.ser_clct, "collect_search", return_value=fx.result(1)) as search, \
                patch.object(main.plc_clct, "collect_place", return_value={}) as place, \
                patch.object(main.expt, "save_results"), contextlib.redirect_stdout(io.StringIO()):
            main.run("cafes", location="Tokyo", language=" JA ")
            constructor.assert_called_once_with(False, 30, None, "ja")
            resolve.assert_called_once_with("Tokyo", 30, "ja")
            self.assertEqual(search.call_args.kwargs["language"], "ja")
            self.assertEqual(place.call_args.args[-1], "ja")
            constructor.return_value.close.assert_called_once()

    def test_invalid_run_language_prevents_external_work(self) -> None:
        """To reject invalid language settings before browser construction or geocoding."""

        with patch.object(main.br, "Browser") as constructor, patch.object(main.geo, "resolve_location") as resolve:
            with self.assertRaisesRegex(ValueError, "language"):
                main.run("cafes", location="Tokyo", language="ja_JP")
            constructor.assert_not_called()
            resolve.assert_not_called()


if __name__ == "__main__":
    unittest.main()
