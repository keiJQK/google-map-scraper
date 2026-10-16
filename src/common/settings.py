import math
import tomllib
from pathlib import Path
from typing import Any

from . import utils as ut
from . import language as lang
from ..search import collect as ser_clct

SECTION_KEYS = {
    "search": {"query", "location", "zoom", "max_places", "max_place_details"},
    "output": {"format"},
    "browser": {"headless", "timeout", "chrome_binary", "language"},
}


def load_settings(path: str | Path | None = None) -> dict[str, Any]:
    """To load and validate TOML settings as run arguments, leaving omitted options to run defaults."""

    path = Path(path) if path is not None else ut.CONFIG_DIR / "settings.toml"
    if not path.is_file():
        raise FileNotFoundError(
            f"Settings file not found: {path}. Copy config/settings.example.toml to config/settings.toml "
            "and edit it, or select an existing file with --config."
        )
    try:
        with path.open("rb") as stream:
            document = tomllib.load(stream)
    except tomllib.TOMLDecodeError as error:
        raise ValueError(f"Invalid TOML in {path}: {error}") from error
    unknown = document.keys() - SECTION_KEYS.keys()
    if unknown:
        raise ValueError(f"Unknown settings sections: {', '.join(sorted(unknown))}")
    options: dict[str, Any] = {}
    for section, allowed in SECTION_KEYS.items():
        values = document.get(section, {})
        if not isinstance(values, dict):
            raise ValueError(f"{section} must be a TOML table")
        unknown = values.keys() - allowed
        if unknown:
            raise ValueError(f"Unknown {section} settings: {', '.join(sorted(unknown))}")
        options.update({"file_format" if key == "format" else key: value for key, value in values.items()})
    _validate_options(options)
    return options


def _validate_options(options: dict[str, Any]) -> None:
    """To validate configured values and normalize output formats and language tags."""

    query = options.get("query")
    if "language" in options:
        options["language"] = lang.normalize_language(options["language"])
    if not isinstance(query, str) or not query.strip():
        raise ValueError("search.query must be a nonempty string")
    for key in ("query", "location", "chrome_binary"):
        if key in options:
            if not isinstance(options[key], str) or not options[key].strip():
                raise ValueError(f"{key} must be a nonempty string; omit optional values instead of leaving them blank")
            options[key] = options[key].strip()
    if "max_places" in options:
        ser_clct.validate_max_places(options["max_places"])
    if "zoom" in options:
        ser_clct.validate_zoom(options["zoom"])
    if "max_place_details" in options:
        limit = options["max_place_details"]
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 0:
            raise ValueError("search.max_place_details must be a nonnegative integer; omit it to fetch all places")
    if "headless" in options and not isinstance(options["headless"], bool):
        raise ValueError("browser.headless must be true or false")
    if "timeout" in options:
        timeout = options["timeout"]
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("browser.timeout must be a finite number greater than zero")
    if "file_format" in options:
        value = options["file_format"]
        formats = {"json": "json", "csv": "csv", "text": "txt", "txt": "txt"}
        if not isinstance(value, str) or value.strip().lower() not in formats:
            raise ValueError("output.format must be json, csv, or text (txt is also accepted)")
        options["file_format"] = formats[value.strip().lower()]
