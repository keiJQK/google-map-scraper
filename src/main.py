import argparse
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from . import browser as br
from .common import export as expt
from .common import settings as cfg
from .common import language as lang
from .common import resume as resu
from .place import collect as plc_clct
from .search import collect as ser_clct
from .search import geocoding as geo
from .common import utils as ut

logger = ut.get_logger("google_map_cdp")

def run(
    query: str, 
    location: str | None = None,
    zoom: int = 14,
    max_places: int = 30,
    max_place_details: int | None = None,
    language: str = "en",
    headless: bool = False, 
    timeout: float = 30, 
    chrome_binary: str | Path | None = None,
    file_format: str = "json",
    ) -> None:
    """To resume saved result cards by completion flags or search and persist new results incrementally."""

    # Initialize
    started_at = datetime.now().astimezone()
    file_format = expt.validate_file_format(file_format)
    conditions = _prepare_conditions(
        query, location, zoom, 
        max_places, max_place_details, language
        )
    language = conditions["language"]
    logger.info("Start with search conditions=%s", conditions)
    
    try:
        result = resu.load_result(conditions)
        resumed = result is not None
        browser = br.Browser(headless, timeout, chrome_binary, language)
        try:
            # Search query
            if result is None:
                result = _collect_new_result(browser, conditions, started_at, timeout, file_format)
            else:
                started_at = datetime.fromisoformat(result["search"]["started_at"])
                logger.info("Resuming saved result from %s", started_at.isoformat())

            # Fetch place info
            target_places = [entry for entry in result["places"][:max_place_details] if not entry["completed"]]
            if resumed and target_places:
                browser.start()

            _collect_place_details(browser, result, target_places, started_at, language)
        finally:
            _close_browser(browser)
        
        # Save results
        expt.save_results(result, started_at, file_format, overwrite=True)

    except Exception as e:
        ut.logging_error(logger, ut.SRC_DIR, e)
        raise

def _prepare_conditions(
    query: str, location: str | None, zoom: int, max_places: int, max_place_details: int | None, language: str,
    ) -> dict[str, Any]:
    """To validate collection inputs and build normalized search conditions used for resume matching."""

    language = lang.normalize_language(language)
    ser_clct.validate_max_places(max_places)
    ser_clct.validate_zoom(zoom)
    if max_place_details is not None and (
        isinstance(max_place_details, bool) or 
        not isinstance(max_place_details, int) or 
        max_place_details < 0
        ):
        raise ValueError("max_place_details must be None or a nonnegative integer")
    
    query = query.strip()
    if not query:
        raise ValueError("query must not be empty")
    
    if location is not None:
        location = location.strip()
        if not location:
            raise ValueError("location must not be empty")
    
    return {
        "query": query, 
        "location": location, 
        "zoom": zoom, 
        "language": language, 
        "max_places": max_places
        }


def _collect_new_result(
    browser: br.Browser, conditions: dict[str, Any], started_at: datetime, timeout: float, file_format: str,
    ) -> dict[str, Any]:
    """To resolve the region, start Chrome, collect search cards, and persist their initial result."""

    location, language = conditions["location"], conditions["language"]
    resolved_location = geo.resolve_location(location, timeout, language) if location is not None else None
    if resolved_location is not None:
        logger.info("Resolved search region: %s", resolved_location)

    browser.start()
    logger.info("Collecting a search result...")
    result = ser_clct.collect_search(
        browser, 
        conditions["query"], 
        max_places=conditions["max_places"], 
        location=resolved_location,
        zoom=conditions["zoom"], 
        language=language,
        )
    
    for entry in result["places"]:
        entry["completed"] = False

    result["search"].update(conditions=conditions, started_at=started_at.isoformat())
    if file_format != "json":
        output_path = expt.result_paths(result, started_at, file_format)[0]
        if output_path.exists():
            raise FileExistsError(f"Output already exists: {output_path}")
        
    expt.save_progress(result, started_at)
    logger.info("Collected. counts=%s", len(result["places"]))
    return result


def _collect_place_details(
    browser: br.Browser, result: dict[str, Any], target_places: list[dict[str, Any]], started_at: datetime, language: str,
    ) -> None:
    """To fetch selected incomplete cards, persist each success, and wait between actual requests."""

    for i, entry in enumerate(target_places, start=1):
        logger.info("place %s: Collecting... name=%s", i, entry["place"]["name"])
        entry.update(plc_clct.collect_place(browser, entry, 1.5, language))
        entry["completed"] = True
        expt.save_progress(result, started_at, overwrite=True)
        logger.info("place %s: Collected.", i)
        if i < len(target_places):
            time.sleep(5)


def _close_browser(browser: br.Browser) -> None:
    """To close Chrome without masking an active collection error with a cleanup failure."""

    active_error = sys.exception()
    try:
        browser.close()
    except Exception:
        if active_error is None:
            raise
        logger.exception("Browser cleanup failed while handling another error")


def main_cli(argv: list[str] | None = None) -> None:
    """To select a TOML configuration and run collection after validating its contents."""

    cli = argparse.ArgumentParser(
        description="Collect Google Maps data using a TOML settings file."
        )
    cli.add_argument(
        "--config", 
        type=Path, 
        help="Settings file; defaults to config/settings.toml in the repository"
        )
    args = cli.parse_args(argv)
    try:
        options = cfg.load_settings(args.config)
    except (OSError, ValueError) as error:
        cli.error(str(error))
    run(**options)


if __name__ == "__main__":
    main_cli()


