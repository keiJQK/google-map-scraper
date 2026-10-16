# Google Maps Data Collector

A Python tool for collecting Google Maps place information and reviews.

The tool captures search and place-detail traffic through Chrome DevTools Protocol
(CDP) and saves the results as JSON, CSV, or TXT. Search regions can be specified
using OpenStreetMap Nominatim.

## Features

- Search for places by keyword and region.
- Capture additional results by scrolling and remove duplicates.
- Collect place profiles, details, and reviews.
- Extract photo URLs from reviews without downloading images.
- Save parsed results and raw responses separately.
- Resume unfinished place details directly from saved results.

## Requirements

- Windows (development and test environment).
- Python 3.12 or later.
- Google Chrome.
- Internet access.

Other environments have not been verified.

Language defaults to English. Set `browser.language` to change Chrome, Google Maps,
and Nominatim language preferences. See [Language Settings](references/languages.md) for
codes and examples. Input keywords are passed unchanged; review text is saved as
returned by Google Maps.

## Quick Start

Run PowerShell from the repository root.

### 1. Set up the environment

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Install Google Chrome beforehand.

### 2. Create the settings file

```powershell
Copy-Item config/settings.example.toml config/settings.toml
```

Open `config/settings.toml` and set your search conditions. Refer to the short
comments in the template for each setting.

Example:

```toml
[search]
query = "Italian restaurants"
location = "New York, New York, USA"
zoom = 14
max_places = 30
max_place_details = 2

[output]
format = "json"

[browser]
language = "en"
headless = false
timeout = 30
```

Omit `location` to let Google Maps determine the search area.

### 3. Run

```powershell
.\.venv\Scripts\python.exe -B -m src.main
```

To use another settings file:

```powershell
.\.venv\Scripts\python.exe -B -m src.main --config config/paris.toml
```

Results are saved under `data/`.

## Settings

| Setting | Description | Default |
|---|---|---|
| `search.query` | Search keyword (required) | None |
| `search.location` | Region name | Chosen by Google Maps |
| `search.zoom` | Zoom level, 0-21; applies only with a region | `14` |
| `search.max_places` | Target number of places to capture | `30` |
| `search.max_place_details` | Maximum places to fetch details for; `0` skips details | All places |
| `output.format` | `json` / `csv` / `text` | `json` |
| `browser.language` | Language code; see [Language Settings](references/languages.md) | `en` |
| `browser.headless` | Headless mode | `false` |
| `browser.timeout` | Timeout in seconds | `30` |
| `browser.chrome_binary` | Chrome executable path | Automatic detection |

Omit optional keys to use their defaults. Invalid settings produce an error before
browser startup.

`max_places` is a target rather than a strict cap. The final response batch may
contain more places than requested.

## Python Usage

```python
from src import main

main.run("Italian restaurants", location="New York, New York, USA", zoom=14, max_places=30, max_place_details=2, file_format="json")
```

`main.run()` collects and saves the data and returns `None`. It does not load a
TOML settings file automatically.

## Output Files

A folder is created for each region and keyword combination.

```text
data/
`-- New York, New York, USA_Italian restaurants/
    |-- result_2026-10-16_14-30-05.json
    |-- raw_response_search_2026-10-16_14-30-05.txt
    `-- raw_response_place_2026-10-16_14-30-05.txt
```

| File | Contents |
|---|---|
| `result_*` | Place profiles, details, and reviews |
| `raw_response_search_*` | Raw search responses |
| `raw_response_place_*` | Raw place-detail responses |

Results are always saved as JSON for incremental saving and resume. Selecting CSV
or TXT also creates that format after the requested detail targets finish. Raw
responses always use separate TXT files.

Main result structure:

```text
result
|-- search
|   |-- query
|   |-- conditions
|   |-- started_at
|   |-- url
|   |-- location
|   |-- zoom
|   `-- center
`-- places[]
    |-- rank
    |-- completed
    |-- place
    |-- details
    |-- reviews[]
    |   `-- photo_urls[]
    `-- url
```

`rank` is capture order. `place.review_count` is the total review count shown by
Google Maps, which differs from the number of reviews actually captured.

### Example Place Entry

The following is one item in `places`. All names, identifiers, coordinates, and
URLs are illustrative. `place` contains the basic profile, `details` contains
additional information, and `reviews` contains captured reviews and their photo
URLs. Raw response bodies are saved separately.

```json
{
  "rank": 1,
  "completed": true,
  "place": {
    "place_id": "example-place-id",
    "feature_id": "0x1:0x2",
    "name": "Example Italian Restaurant",
    "address": "123 Example Street, New York, NY",
    "categories": [
      "Italian restaurant"
    ],
    "latitude": 40.71,
    "longitude": -74.01,
    "rating": 4.5,
    "review_count": 120,
    "website": "https://example.com",
    "phone": "+1 212-555-0100"
  },
  "details": {
    "price_range": "$$",
    "opening_hours": [
      {
        "day": "Friday",
        "date": "2026-10-16",
        "hours": [
          "11:00 AM-10:00 PM"
        ]
      }
    ],
    "opening_status": "Open",
    "attributes": [],
    "rating_distribution": {
      "star_1": 2,
      "star_2": 3,
      "star_3": 10,
      "star_4": 23,
      "star_5": 82
    }
  },
  "reviews": [
    {
      "review_id": "example-review-id",
      "author_name": "Example Reviewer",
      "author_id": "example-author-id",
      "rating": 5,
      "timestamp_us": null,
      "time_text": "A week ago",
      "text": "Great pasta and friendly service.",
      "photo_urls": [
        "https://example.com/review-photo.jpg"
      ],
      "aspects": []
    }
  ],
  "url": "https://www.google.com/maps/search/?api=1&query=Example%20Italian%20Restaurant&query_place_id=example-place-id&hl=en"
}
```

Places without detail collection have `details` and `url` set to `null` and an
empty `reviews` list. Missing scalar fields may also be `null`.

Other storage locations:

- Nominatim cache: `data/cache/nominatim.sqlite3`.
- Log: `logs/google_map_cdp.log`.

## Incremental Saving and Resume

The normal `result_YYYY-MM-DD_HH-MM-SS.json` is saved after search finishes and
after each successful place-detail request. Every card has a boolean `completed`:
`false` until detail collection and data updates succeed, then `true`. Empty
details or reviews can still represent a successfully completed request.
There is no separate checkpoint wrapper or global completion flag, and the result
data is retained after all cards finish. Search failures create no result file.

Rerun the same command to load a matching result and skip completed cards. Matching
uses the normalized keyword, region, zoom, language, and `max_places`, stored in
`search.conditions`. The original execution time is kept in `search.started_at`.
Neither `max_place_details` nor the output format is part of matching, so a trial
with `max_place_details = 2` can later continue with a larger limit or no limit.
The limit still means the first N captured cards, not N additional cards per run.
`0` saves search-only data without fetching details.

Resume skips search and region lookup and updates the original dated result and
raw-response files. Raw bodies stay outside the result JSON; their TXT records
include metadata and body lengths so they can be restored without altering text.
Keep both raw-response files beside the JSON when moving a saved execution.
JSON updates use temporary files and atomic replacement, publishing raw files
before the JSON. Optional CSV/TXT exports are generated after the requested targets
finish. If export fails, rerun to retry it using saved data.

An unfinished matching result is preferred. Multiple unfinished matches cause an
error listing their paths. If all matching results are complete, the latest result
is reused without fetching details again. To collect a fresh dataset, move the
matching result JSON files out of the query folder first. Invalid results or missing
raw files cause an error rather than silently discarding saved data.

Older result files without resume metadata and old `checkpoint_*.json` files are
not used for resume or deleted. Run one process at a time for the same search
conditions; concurrent updates are not supported.

## Processing Flow

```text
Load settings
    v
Resolve region coordinates (when specified)
    v
Search Google Maps
    v
Capture search responses through CDP
    v
Scroll and deduplicate results
    v
Fetch place details and reviews
    v
Save results and raw responses
```

## Nominatim

Region names are resolved to latitude and longitude. Results are cached in SQLite.
When multiple candidates are returned, the first candidate is selected. No matches
produce an error. The selected name and coordinates are recorded in `search.location`.

Environment variables:

| Variable | Purpose |
|---|---|
| `NOMINATIM_URL` | API endpoint |
| `NOMINATIM_USER_AGENT` | User-Agent identifying the application |
| `NOMINATIM_CACHE_PATH` | Cache database path |

When using the public Nominatim server, follow its usage policy, including the
application-wide maximum of one request per second, an identifying User-Agent,
and attribution. Scheduled and bulk use has additional restrictions.

- [Nominatim Usage Policy](https://operations.osmfoundation.org/policies/nominatim/)
- [OpenStreetMap Copyright](https://www.openstreetmap.org/copyright)

© OpenStreetMap contributors

## Limitations

- The collector depends on Google's undocumented response format and may break when it changes.
- Scrolling uses some DOM elements.
- Coordinates specify a search center, not a strict geographic boundary.
- Reviews are limited to those included in captured responses.
- CAPTCHA and access restrictions may prevent collection.
- End-to-end headless operation has not been verified.

## Tests

See [test/README.md](test/README.md) for test commands and coverage.

## License

Original project code is licensed under the [MIT License](LICENSE) and provided
"AS IS", without warranty. Operation, data accuracy, and continued maintenance
are not guaranteed. Users are responsible for complying with applicable laws
and service terms.

Third-party dependencies, documentation screenshots, and collected data remain
subject to their respective licenses and terms; the MIT License does not grant
rights to those materials.

## TODO

- [ ] Verify, in headless mode, search, scrolling, and place-detail collection.
