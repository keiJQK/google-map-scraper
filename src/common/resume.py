import json
from datetime import datetime
from typing import Any

from . import export as expt


def load_result(search_conditions: dict[str, Any]) -> dict[str, Any] | None:
    """To restore one unfinished matching result or the latest completed result with its separate raw bodies."""

    directory = expt.result_directory(search_conditions["query"], search_conditions["location"])
    matches = []
    for path in sorted(directory.glob("result_*.json")):
        try:
            with path.open(encoding="utf-8") as stream:
                result = json.load(stream)
            if not isinstance(result, dict) or not isinstance(result.get("search"), dict):
                raise ValueError("missing search data")
            if "conditions" not in result["search"]:
                continue
            if result["search"]["conditions"] != search_conditions:
                continue
            _validate_result(result)
            started_at = datetime.fromisoformat(result["search"]["started_at"])
            if expt.result_paths(result, started_at)[0] != path:
                raise ValueError("filename does not match search metadata")
            matches.append((path, result, started_at))
        except (ValueError, TypeError, KeyError) as error:
            raise ValueError(f"Invalid result file {path}: {error}") from error
    unfinished = [item for item in matches if any(not entry["completed"] for entry in item[1]["places"])]
    if len(unfinished) > 1:
        raise ValueError("Multiple unfinished results match these conditions: " + ", ".join(str(item[0]) for item in unfinished))
    if not matches:
        return None
    path, result, started_at = unfinished[0] if unfinished else matches[-1]
    _, search_path, place_path = expt.result_paths(result, started_at)
    search_raw = expt.read_raw_responses(search_path)
    if any(index != -1 for index, _ in search_raw):
        raise ValueError(f"Invalid search response index in {search_path}")
    result["search"]["raw_responses"] = [response for _, response in search_raw]
    for entry in result["places"]:
        entry["raw_responses"] = []
    for index, response in expt.read_raw_responses(place_path):
        if not 0 <= index < len(result["places"]):
            raise ValueError(f"Invalid place response index in {place_path}")
        result["places"][index]["raw_responses"].append(response)
    return result


def _validate_result(result: dict[str, Any]) -> None:
    """To reject incomplete resume metadata or nonboolean card completion flags."""

    search = result["search"]
    if not {"query", "url", "location", "zoom", "center", "conditions", "started_at"} <= search.keys():
        raise ValueError("incomplete search metadata")
    datetime.fromisoformat(search["started_at"])
    if not isinstance(result["places"], list):
        raise ValueError("places must be a list")
    for entry in result["places"]:
        if not isinstance(entry, dict) or not {"rank", "place", "details", "reviews", "url", "completed"} <= entry.keys():
            raise ValueError("incomplete place entry")
        if type(entry["completed"]) is not bool or not isinstance(entry["place"], dict) or not isinstance(entry["reviews"], list):
            raise ValueError("invalid place state")
