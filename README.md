# Google Maps Scraper Pipeline
A Selenium-based pipeline that searches Google Maps by keyword,
collects a target number of result cards,
opens each place page, captures Overview/Review HTML,
extracts structured fields (profile + ratings + review texts),
and exports them as a CSV for downstream processing such as analysis or reporting.


## How to Run
- This repository requires an external Selenium worker implementation
  (e.g. `scraping.src.retrieve.worker_selenium.SetupGoogleMap`).
- In `google_map_runner.py`, `temporary_setup()` must be replaced to create
  and return your own `SetupGoogleMap` instance.
- See: [Required Worker Contract](./HOW_TO_RUN.md#required-worker-contract-selenium)

- Run the runner script (example in `__main__`) after setting the keyword and target counts in `MapContext`.


## Intended Use Cases
- Collect Google Maps place data for a given keyword (e.g., “居酒屋”)
- Build a lightweight report dataset: name, address, link, phone, plus code, ratings, star distribution, and review excerpts


## Architecture / Directory Structure
This repository adopts a simple layered structure
to keep responsibilities clear and replaceable.

- runner
  - Orchestration only (step chaining / context wiring)
  - No parsing rules, no scraping details

- usecase
  - Workflow steps (usecase step classes)
  - Coordinates Selenium actions and data extraction flow
  - No low-level I/O implementations

- infrastructure
  - External access and utilities (HTML I/O, CSV I/O, parsing helpers)
  - No workflow decisions

There is currently no dedicated domain layer.
The project is workflow-driven, and shared objects mainly serve
as pipeline context / DTOs rather than stable business models.


### Processing Flow
Initialization
- Selenium Worker (SetupGoogleMap) is created once and shared
- MapInfra (Infrastructure) provides file I/O + HTML parsing utilities

Execution Flow
- Runner
  -> GetResult (open maps, search keyword, scroll results, pick N cards)
  -> EachCard (click each card, save Overview HTML, open Review tab, scroll reviews, expand “detail”, save Review HTML)
  -> Extract (load saved HTML, extract fields, build vertical dataset, export CSV)

## Data Outputs
HTML snapshots
- maps_{i:03}_overview.html
- maps_{i:03}_review.html

CSV output
- output_google_map.csv (vertical format: each shop becomes a column; rows are typed fields) 


## Current Limitations
- **Japanese UI only (language-dependent selectors)**  
  This pipeline assumes Google Maps is displayed in Japanese and relies on
  Japanese UI labels such as "概要", "クチコミ", and "詳細".
  If your Google Maps UI is not Japanese, selectors may break and the pipeline
  may fail.

- **Fragile against UI / DOM changes**  
  Google Maps frequently changes its DOM structure and UI labels.
  This project uses hardcoded selectors and minimal retry logic, so it may stop
  working without notice and require manual selector updates.

- **Not designed for large-scale crawling**  
  Error handling and retries are intentionally minimal. Google may block
  automated access (e.g., CAPTCHA / rate limits), and manual intervention
  may be required.


