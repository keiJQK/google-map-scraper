# Offline CDP Tests

Run commands from the repository root after installing `requirements.txt`.
The tests use Python's built-in `unittest`; no additional test dependencies are required.

Run every test:

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s test -v
```

Run only export tests:

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s test -p "test_export.py" -v
```

| File | Coverage |
|---|---|
| `test_browser.py` | CDP events, response bodies, failures, feed selection, browser lifecycle |
| `test_search.py` | Search URLs, parsing, deduplication, scrolling, stop conditions |
| `test_place.py` | Place identity, details, reviews, photo URLs, navigation |
| `test_response.py` | Shared response decoding and profile normalization |
| `test_geocoding.py` | HTTP responses, cache reuse, rate limiting, lookup failures |
| `test_export.py` | JSON/CSV/TXT, raw-response separation, naming, existing-file protection |
| `test_main.py` | Workflow order, detail targets, waiting, cleanup, saving |
| `test_resume.py` | Result-based resume, changing detail limits, raw-body restoration, export retry, atomic updates, discovery, output protection |
| `test_settings.py` | TOML parsing, value validation, examples, config selection, CLI dispatch |
| `test_language.py` | Language configuration, Chrome preferences, localized URLs, cache isolation, workflow propagation |

`fixtures.py` builds fictional response payloads. Tests do not require private
`runtime/` samples, launch Chrome, contact Google Maps or Nominatim, or wait for
real request intervals. Output and SQLite caches use temporary directories that
are removed after each test.

Passing these tests verifies the supported data contracts and workflow. It does
not verify compatibility with the live Google Maps UI or current response layout.
