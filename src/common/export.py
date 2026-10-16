import csv
import json
import logging
import os
import re
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, TextIO

from . import utils as ut

logger = logging.getLogger("google_map_cdp")
PLACE_FIELDS = (
    "place_id", "feature_id", "name", "address", "categories", "latitude", "longitude",
    "rating", "review_count", "website", "phone",
)


def save_results(result: dict[str, Any], started_at: datetime, file_format: str = "json", *, overwrite: bool = False) -> None:
    """To atomically publish raw files before the result, preserving per-place completion flags."""

    file_format = validate_file_format(file_format)
    paths = result_paths(result, started_at, file_format)
    directory = paths[0].parent
    directory.mkdir(parents=True, exist_ok=True)
    if not overwrite:
        for path in paths:
            if path.exists():
                raise FileExistsError(f"Output already exists: {path}")
    with tempfile.TemporaryDirectory(prefix=".export_", dir=directory) as temporary:
        staged = tuple(Path(temporary) / path.name for path in paths)
        _write_results(result, staged, file_format)
        for index in (1, 2, 0):
            source, destination = staged[index], paths[index]
            if not overwrite and destination.exists():
                raise FileExistsError(f"Output already exists: {destination}")
            os.replace(source, destination)
    for path in paths:
        logger.info("Saved: %s", path)


def save_progress(result: dict[str, Any], started_at: datetime, *, overwrite: bool = False) -> None:
    """To persist the normal JSON result and separate raw files after search or a completed detail request."""

    save_results(result, started_at, "json", overwrite=overwrite)


def _write_results(result: dict[str, Any], paths: tuple[Path, Path, Path], file_format: str) -> None:
    """To write staged results with completion flags and separately recoverable literal raw bodies."""

    result_path, search_path, place_path = paths
    search = result["search"]
    cleaned = {
        **result,
        "search": {
            key: value 
            for key, value in search.items() 
            if key != "raw_responses"
            },
        "places": [
            {key: value for key, value in entry.items() if key != "raw_responses"}
            for entry in result["places"]
            ],
    }

    with search_path.open("x", encoding="utf-8", newline="") as stream:
        stream.write("Search\n")
        _write_fields(stream, {"query": search["query"], "url": search["url"]})
        _write_raw_responses(stream, search.get("raw_responses", []))

    with place_path.open("x", encoding="utf-8", newline="") as stream:
        if not result["places"]:
            stream.write("No captured responses.\n")
        for index, entry in enumerate(result["places"]):
            stream.write(f"\n{'=' * 60}\nPlace {entry['rank']}: {entry['place'].get('name')}\n")
            _write_fields(stream, {
                "rank": entry["rank"], "place_id": entry["place"].get("place_id"),
                "feature_id": entry["place"].get("feature_id"), "name": entry["place"].get("name"), "url": entry["url"],
            })
            _write_raw_responses(stream, entry.get("raw_responses", []), index)

    if file_format == "csv":
        _save_csv(result_path, cleaned)
    elif file_format == "txt":
        _save_text(result_path, cleaned)
    else:
        with result_path.open("x", encoding="utf-8") as stream:
            json.dump(cleaned, stream, ensure_ascii=False, indent=2)


def result_paths(result: dict[str, Any], started_at: datetime, file_format: str = "json") -> tuple[Path, Path, Path]:
    """To determine the three final paths for an execution without creating or changing files."""

    file_format = validate_file_format(file_format)
    search = result["search"]
    location = search.get("location")
    directory = result_directory(search["query"], location["query"] if location is not None else None)
    timestamp = started_at.strftime("%Y-%m-%d_%H-%M-%S")
    return (
        directory / f"result_{timestamp}.{file_format}",
        directory / f"raw_response_search_{timestamp}.txt",
        directory / f"raw_response_place_{timestamp}.txt",
    )


def result_directory(query: str, location: str | None = None) -> Path:
    """To determine the shared query folder for result files without creating it."""

    folder_name = f"{location}_{query}" if location is not None else query
    return ut.DATA_DIR / _folder_name(folder_name)



def validate_file_format(file_format: str) -> str:
    """To normalize the requested result extension and reject unsupported formats before collection."""

    if not isinstance(file_format, str) or file_format.strip().lower() not in {"json", "csv", "txt"}:
        raise ValueError("file_format must be json, csv, or txt")
    return file_format.strip().lower()


def _folder_name(value: str) -> str:
    """To replace unsafe Windows folder characters and keep output inside the configured data directory."""

    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value).strip().rstrip(". ")[:160].rstrip(". ")
    if not name:
        return "search"
    if re.fullmatch(r"CON|PRN|AUX|NUL|COM[1-9¹²³]|LPT[1-9¹²³]", name.split(".")[0], re.IGNORECASE):
        name = "_" + name
    return name


def _write_raw_responses(stream: TextIO, responses: list[dict[str, Any]], entry_index: int = -1) -> None:
    """To write readable raw bodies with lengths and metadata for lossless resume loading."""

    if not responses:
        stream.write("No captured responses.\n")
    for index, response in enumerate(responses, start=1):
        stream.write(f"\n--- Response {index} ---\n")
        _write_fields(stream, {key: value for key, value in response.items() if key != "body"})
        stream.write(f"Entry-Index: {entry_index}\n")
        stream.write("Metadata: " + json.dumps({key: value for key, value in response.items() if key != "body"}, ensure_ascii=False) + "\n")
        stream.write(f"Body-Length: {len(response['body'])}\n")
        stream.write("Body:\n")
        stream.write(response["body"])
        stream.write("\n--- End response ---\n")


def read_raw_responses(path: Path) -> list[tuple[int, dict[str, Any]]]:
    """To restore literal response bodies and their place indexes without splitting on body contents."""

    with path.open(encoding="utf-8", newline="") as stream:
        text = stream.read()
    responses = []
    offset = 0
    header = re.compile(r"^Entry-Index: ", re.MULTILINE)
    pattern = re.compile(r"Entry-Index: (-?\d+)\nMetadata: ([^\n]+)\nBody-Length: (\d+)\nBody:\n")
    ending = "\n--- End response ---\n"
    try:
        while (start := header.search(text, offset)) is not None:
            match = pattern.match(text, start.start())
            if match is None:
                raise ValueError("invalid raw response header")
            metadata = json.loads(match[2])
            if not isinstance(metadata, dict) or "body" in metadata:
                raise ValueError("invalid raw response metadata")
            end = match.end() + int(match[3])
            if text[end:end + len(ending)] != ending:
                raise ValueError("incomplete raw response body")
            responses.append((int(match[1]), {**metadata, "body": text[match.end():end]}))
            offset = end + len(ending)
        if not responses and "No captured responses.\n" not in text:
            raise ValueError("no recoverable raw response records")
    except (ValueError, TypeError) as error:
        raise ValueError(f"Invalid raw response file {path}: {error}") from error
    return responses


def _write_fields(stream: TextIO, fields: dict[str, Any]) -> None:
    """To render named values while retaining structured fields as readable JSON text."""

    for key, value in fields.items():
        rendered = json.dumps(value, ensure_ascii=False, indent=2) if isinstance(value, (dict, list)) else str(value)
        stream.write(f"{key}: {rendered}\n")


def _save_csv(path: Path, result: dict[str, Any]) -> None:
    """To write one row per place with repeated search metadata and JSON-encoded nested fields."""

    search = result["search"]
    location = search.get("location") or {}
    center = search.get("center") or {}
    metadata = {
        "search_query": search["query"], 
        "search_url": search["url"], 
        "location_query": location.get("query"),
        **{key: location.get(key) for key in ("nominatim_name", "nominatim_latitude", "nominatim_longitude", "attribution")},
        "zoom": search.get("zoom"), 
        "center_latitude": center.get("latitude"), 
        "center_longitude": center.get("longitude"),
    }
    columns = [*metadata, "rank", "completed", *(f"place_{key}" for key in PLACE_FIELDS), "details", "reviews", "url"]
    with path.open("x", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, columns)
        writer.writeheader()
        for entry in result["places"]:
            row = {
                **metadata, 
                "rank": entry["rank"], 
                "completed": entry.get("completed", False),
                **{f"place_{key}": entry["place"].get(key) for key in PLACE_FIELDS},
                "details": entry["details"], 
                "reviews": entry["reviews"], 
                "url": entry["url"],
            }
            writer.writerow({
                key: json.dumps(value, ensure_ascii=False) 
                if isinstance(value, (dict, list)) else value
                for key, value in row.items()
                })


def _save_text(path: Path, result: dict[str, Any]) -> None:
    """To write search information and separate readable sections for every parsed place."""

    with path.open("x", encoding="utf-8") as stream:
        stream.write("Search\n======\n")
        _write_fields(stream, result["search"])
        for entry in result["places"]:
            stream.write(f"\n{'=' * 60}\nPlace {entry['rank']}: {entry['place'].get('name')}\n")
            _write_fields(stream, entry)
