# PC Compare — Portfolio Company Validation Tool

A Flask web app that compares a quarterly portfolio baseline (Excel) against the live company list scraped from the [PIF portfolio page](https://www.pif.gov.sa/en/our-investments/our-portfolio/), and reports what to add, remove, or rename.

There is **one** application — a browser-based web UI. There is no separate CLI tool. (An older terminal script, `bkp-compare.py`, has been removed; see [.gitignore](.gitignore) for the historical reference.)

## Quick Start

```bash
cd webview
python3 -m venv venv
source venv/bin/activate              # Windows: venv\Scripts\activate
pip install -r requirements.txt
playwright install firefox chromium
python3 app.py
```

Open `http://127.0.0.1:5000` and upload a baseline `.xlsx` file with columns: `CR Name`, `Brand Name`, `VRP Sector`.

## How It Works

1. **Upload** — `POST /upload` accepts the Excel file plus scraping options (browser, headless, debug, timeout) and returns a `result_id`.
2. **Background scrape** — Flask spawns a thread that runs [`compare.scrape_website()`](webview/compare.py), which traverses the PIF site's facet filters (3 Portfolio facets + 6 Ecosystem facets) using Playwright + [`playwright-stealth`](https://github.com/AtuboDad/playwright_stealth). Each facet pass scrapes the filtered company list across pagination; results are merged into a single `(Company, Portfolio, Ecosystem)` table. Firefox is the default (best Cloudflare bypass).
3. **Match** — [`enhanced_matching.enhanced_compare_companies()`](webview/enhanced_matching.py) runs the baseline rows against the scraped list using five strategies in order: exact normalized → core name → acronym/substring → token-based → fuzzy fallback. See thresholds in [webview/config.py](webview/config.py).
4. **Persist & summarize** — [`results_analyzer.ResultsSummarizer`](webview/results_analyzer.py) writes a 3-sheet Excel report (Comparison Results, Unmatched Website Companies, Summary) and saves a row per run plus per-company history into `webview/comparison_history.db` (SQLite) for quarter-over-quarter trend analysis.
5. **Poll & download** — Browser polls `GET /status/<result_id>`, then fetches `GET /summary/<result_id>` and `GET /download/<result_id>` when complete.

## Supported Baseline Templates

The app accepts two Excel formats and auto-detects which one was uploaded based on column headers.

**Legacy template** (existing stakeholder):
- Required columns: `CR Name`, `Brand Name`, `VRP Sector`
- Comparison: name + presence only. Sector is no longer compared because the website's card-level sector field has been removed.

**New template** (extended stakeholder):
- Required columns: `CR Name`, `Brand Name`, `Portfolio`, `Ecosystem` (other columns are tolerated and ignored)
- Comparison: name + presence + Portfolio assignment + Ecosystem assignment.
- `Ecosystem` is sparse — rows with no Ecosystem value are reported as `N/A` rather than as mismatches.

Uploading a file that matches neither shape returns HTTP 400 with the expected column lists.

## Project Layout

```
pc-compare/
├── webview/                       # The application (everything lives here)
│   ├── app.py                     # Flask routes + background processing
│   ├── compare.py                 # Playwright scraper (Cloudflare bypass)
│   ├── enhanced_matching.py       # 5-strategy matcher
│   ├── results_analyzer.py        # Summary + SQLite historical tracker
│   ├── config.py                  # WEBSITE_URL, thresholds, CSS selectors
│   ├── index.html                 # Single-page web UI
│   ├── debug_selectors.py         # Dev tool: opens visible browser to verify selectors
│   ├── requirements.txt
│   ├── uploads/                   # Uploaded baselines + generated results + debug dumps
│   └── comparison_history.db      # SQLite history (auto-created)
├── README.md                      # This file
├── SETUP.md                       # Short install walkthrough
├── CLOUDFLARE_TROUBLESHOOTING.md  # Bypass strategies + escalation path
├── requirements.txt               # Duplicate of webview/requirements.txt
└── config.py                      # Unused duplicate of webview/config.py — safe to delete
```

## Output

Results land in `webview/uploads/results_<YYYYMMDDHHMMSS>.xlsx`. Status values per row:

| Status | Meaning |
|--------|---------|
| `OK` | All applicable fields match (name + Portfolio + Ecosystem) |
| `Add` | In baseline, missing from website |
| `Remove` | On website, missing from baseline |
| `Requires update` | Present on both sides but at least one field differs — see per-field columns (`Match Score`, `Portfolio Match`, `Ecosystem Match`) for which |

For the new template, the per-field `Portfolio Match` / `Ecosystem Match` columns take values `Yes`, `No`, or `N/A` (the latter when the baseline cell is empty or the company isn't on the website).

## Configuration

Edit [webview/config.py](webview/config.py):

- `WEBSITE_URL` — target portfolio page
- `FUZZY_MATCH_THRESHOLD` (default 90) — minimum score for fuzzy name matching
- `SECTOR_MATCH_THRESHOLD` (default 80) — minimum score for categorical (Portfolio/Ecosystem) matching
- `SELECTORS` — CSS selectors for cookie banner, pagination, company cards, and facet panels. Update these if the PIF site changes its markup.

## Cloudflare Troubleshooting

The scraper applies `playwright-stealth` automatically and detects Cloudflare challenge pages, waiting up to 30s (headless) or 120s (visible) for resolution. If scraping fails:

1. Switch to **Firefox** in the UI (already default).
2. Switch to **Visible** mode and solve any CAPTCHA manually.
3. Increase timeout to 120–180 s.
4. Inspect `webview/uploads/error_screenshot_*.png` and `error_page_*.html` (debug mode is on by default).
5. Run [webview/debug_selectors.py](webview/debug_selectors.py) to verify selectors haven't changed on the live page.

Full escalation path (incl. switching to `camoufox` or a managed bypass proxy) is in [CLOUDFLARE_TROUBLESHOOTING.md](CLOUDFLARE_TROUBLESHOOTING.md).

## Requirements

- Python 3.8+
- Playwright browsers (Firefox required, Chromium recommended)
- Outbound HTTPS to `pif.gov.sa`

## Testing

**Unit tests** (no network, ~1s):

```bash
pytest webview/tests/ -v
```

**End-to-end smoke test** against the live PIF site (~2 min):

```bash
python3 webview/app.py &                          # start the app
python3 webview/smoke_test.py                     # uploads new-template.xlsx, polls, downloads, asserts schema
python3 webview/smoke_test.py --baseline path/to/your.xlsx
```

Exits 0 on success; prints the actual sheet/column/status breakdown of the downloaded result.

## Upgrading from a previous version

The SQLite history schema changed in this release (sector columns removed, Portfolio + Ecosystem columns added). If you have an existing `webview/comparison_history.db` from a previous version, **delete it before first run** — the app will create a fresh one with the current schema. Old run history is not migrated.
