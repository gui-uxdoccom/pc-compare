# New Baseline Template Support — Design

**Date:** 2026-05-03
**Status:** Approved (ready for implementation plan)

## Background

A new stakeholder uses a different baseline Excel template — same comparison goal (validate against the live PIF portfolio page), different schema. The legacy stakeholder's template stays in use, so both formats must be supported.

In parallel, the PIF website itself has changed: company **sectors are no longer printed on the result cards**. The new taxonomy is exposed only through facet filters in the left sidebar:

- **Portfolio** — `Vision` / `Strategic` / `Financial`. Every company is tagged.
- **Ecosystem** — 6 categorical values (e.g. *Advanced Manufacturing and Innovation*, *Tourism, Travel and Entertainment*). Only ~83 of the listed companies are tagged.

The current scraper extracts a `Sector` value from `<h5>` inside each card; that selector now returns nothing. The old baseline's `VRP Sector` comparison is therefore broken end-to-end, regardless of this stakeholder change.

## Goals

1. Add support for the new baseline format alongside the legacy one — auto-detected at upload, no UI selector.
2. Replace the dead card-level sector scrape with a facet-traversal scrape that captures both Portfolio and Ecosystem per company.
3. Make the comparison engine schema-driven so the per-row comparison adapts to whichever template was uploaded, without if/else branches scattered across the codebase.
4. Keep the legacy baseline functional for name/presence matching even though its sector check no longer applies.

## Non-goals

- No changes to the 5-strategy name matching algorithm — it works well and is unrelated to this change.
- No generic schema-config system (rejected as premature with only two stakeholders).
- No new UI features beyond targeted dashboard JS edits to render whichever fields the spec produces.
- No data migration of the existing SQLite history — it will be dropped and recreated.

## Approach summary

Approach **B** from brainstorming: extract both Portfolio and Ecosystem from website facets and compare each when the baseline includes the corresponding column.

- Approach A (ecosystem only, ignore portfolios) — rejected: leaves obvious value on the table given the website's full new taxonomy.
- Approach C (generic YAML/JSON-driven schemas) — rejected: premature abstraction for two stakeholders.

## Detailed design

### 1. Template detection and schema mapping

A single `TemplateSpec` dataclass carries everything downstream code needs to know about the uploaded baseline:

```python
@dataclass(frozen=True)
class TemplateSpec:
    kind: Literal["legacy", "new"]
    name_field: str          # "CR Name" for both
    brand_field: str         # "Brand Name" for both
    portfolio_field: str | None   # None for legacy, "Portfolio" for new
    ecosystem_field: str | None   # None for legacy, "Ecosystem" for new
```

`detect_template(df: DataFrame) -> TemplateSpec`:

- If columns include `VRP Sector` and exclude `Portfolio` → `legacy`.
- If columns include `Portfolio` and `Ecosystem` → `new`.
- Otherwise → raise a `ValueError` with a message listing the columns that were expected. The Flask `/upload` endpoint catches this and returns HTTP 400 with the message.

Detection runs once at upload time. All downstream code reads from the spec, never directly from raw column names.

**Cleanup rolled in:**
- Drop the empty `Unnamed: 7` column on read (Excel artifact in the new template).
- `df.columns = df.columns.str.strip()` to fix the trailing space on `Verticals ` (we don't consume `Verticals`, but this prevents future confusion).

### 2. Scraper redesign — facet traversal

`scrape_website()` is refactored from one monolithic async function into focused pieces:

| Function | Responsibility |
|---|---|
| `_open_portfolio_page(...)` | Browser launch, stealth setup, navigate, accept cookies, wait for the company list. Pure setup; no business logic. |
| `_discover_facets(page)` | Read the Portfolio panel and Ecosystem panel, return `{"portfolio": [...], "ecosystem": [...]}` of facet values from `data-facetvalue` attributes. No hardcoded list — picks up changes automatically. |
| `_scrape_with_facet(page, panel_selector, facet_value)` | Click the facet's checkbox, wait for the result list to actually change (verified by first-card name change OR result count drop), iterate pagination collecting names, uncheck before returning. Reused by both panels. |
| `scrape_website(...) -> DataFrame` | Orchestrator. Calls setup → portfolio pass → ecosystem pass → merges both into `{Company, Portfolio, Ecosystem}` DataFrame. |

**Order:** Portfolio pass first. Every company is tagged with a portfolio, so the union of the 3 portfolio scrapes is the complete company universe. The ecosystem pass then enriches that universe; companies not present in any ecosystem facet keep `Ecosystem = None` (matches the new template's sparse pattern).

**Validation:** any company picked up in an ecosystem pass that wasn't seen in the portfolio pass is logged as `WARNING: data inconsistency` and added to the universe with `Portfolio = None`. We do not silently drop it.

**Selectors move into `webview/config.py`:**

```python
SELECTORS = {
    # ... existing card/pagination selectors retained ...
    "portfolio_facet_panel": "<container selector for the Portfolio facet block>",
    "ecosystem_facet_panel": "<container selector for the Ecosystem facet block>",
    "facet_item": "p.facet-value",
    "facet_value_attr": "data-facetvalue",
    "facet_checkbox": "input[type='checkbox']",
}
```

The exact container selectors for the two panels are nailed down during implementation by inspecting the live page — the facet block in the user's HTML sample (`<div class="facet-search-filter facet-hided">`) appears multiple times, so we need a parent or sibling identifier. `debug_selectors.py` is the right tool for this.

**Dead code dropped:** `h5` sector extraction in the scrape loop, `company_sector: "div.field-phrase"` from `SELECTORS`, the `Sector` column from the returned DataFrame.

**Performance:** 9 facet passes (3 portfolio + 6 ecosystem) — expected total scrape time 1–3 minutes vs. ~30s today. Acceptable for a quarterly process.

**Resilience:**
- Per-facet failure isolation — log and continue if a single facet errors out; the merge handles partial data.
- Click-success assertion — abort the facet's scrape if the list doesn't visibly change after a checkbox click (avoids silently re-scraping the unfiltered list).
- Stealth setup runs once at page open; in-page facet clicks should not retrigger Cloudflare.

### 3. Comparison engine changes

`enhanced_compare_companies(baseline_df, website_df, template_spec)` — the spec parameter drives all template-conditional behavior. The driver no longer mentions `'VRP Sector'` or `'Sector'` directly.

**Name matching is unchanged.** The 5-strategy `calculate_match_score` and `find_best_match` continue as-is.

**Categorical comparison is generalized.** `EnhancedCompanyMatcher.compare_sectors` is renamed to `compare_categorical(baseline_value, website_value, threshold)` and reused for both Portfolio and Ecosystem. Same logic — normalize, exact match, fuzzy fallback. Portfolio matches will almost always be exact (3 enum values); Ecosystem may need fuzzy because of punctuation drift between sources. `normalize_sector` is renamed to `normalize_categorical` for consistency. `sector_synonyms` is removed (sector taxonomy is gone; the new ecosystem and portfolio values are stable enums).

**Status enum is simplified to four values:**

| Status | Meaning |
|---|---|
| `OK` | Name matches and all applicable categorical fields match |
| `Add` | Present in baseline, missing from website |
| `Remove` | Present on website, missing from baseline |
| `Requires update` | Present on both sides, but at least one field differs |

The specifics live in **per-field columns**, which is where the truth is anyway:

**Legacy template output columns:**
`CR Name`, `Brand Name`, `Website Name`, `Match Score`, `Match Type`, `Match Confidence`, `Matched Field`, `PC exist in website`, `Status`

**New template output columns** (additions in **bold**):
`CR Name`, `Brand Name`, `Website Name`, **`Portfolio`**, **`Website Portfolio`**, **`Portfolio Match`** (`Yes` / `No` / `N/A`), **`Ecosystem`**, **`Website Ecosystem`**, **`Ecosystem Match`** (`Yes` / `No` / `N/A`), `Match Score`, `Match Type`, `Match Confidence`, `Matched Field`, `PC exist in website`, `Status`

`N/A` covers the case where the baseline cell is empty (sparse Ecosystem column) — we don't flag it as a mismatch because the stakeholder hasn't asserted a value to compare.

**Why this shape, not multi-value statuses:**
- Excel filtering and pivot tables work cleanly — no parsing comma-separated status strings.
- Dashboard summary still gets its breakdown by aggregating per-field columns.
- Adding a future categorical field is one new pair of columns and one bullet in status derivation — no new status enum value.

**`ResultsSummarizer` becomes spec-aware.** Its returned `status_breakdown` only contains keys that apply to the spec:

```json
"status_breakdown": {
    "ok": 198,
    "missing_from_website": 5,
    "extra_on_website": 2,
    "name_mismatches": 4,
    "portfolio_mismatches": 1,    // only when spec.portfolio_field is set
    "ecosystem_mismatches": 3     // only when spec.ecosystem_field is set
}
```

Each count is derived from per-row columns, not from the `Status` string:

| Key | Derivation |
|---|---|
| `ok` | rows where `Status == "OK"` |
| `missing_from_website` | rows where `Status == "Add"` |
| `extra_on_website` | rows where `Status == "Remove"` |
| `name_mismatches` | rows where `PC exist in website == "Yes"` AND `Match Score < exact_match_threshold` |
| `portfolio_mismatches` | rows where `Portfolio Match == "No"` |
| `ecosystem_mismatches` | rows where `Ecosystem Match == "No"` |

A row may contribute to more than one `*_mismatches` count (e.g. both name and ecosystem differ); this is intentional — each count answers an independent question.

Recommendations branch on the spec — no portfolio recommendation is emitted for the legacy template.

### 4. Output format and dashboard

**Excel report — three sheets, same shape:**
- **Sheet 1 (Comparison Results):** column set per template (see Section 3).
- **Sheet 2 (Unmatched Website Companies):** `Company` + `Portfolio` + `Ecosystem` regardless of which template was uploaded — the website scrape always carries those now, and seeing them helps triage "extra on website" entries.
- **Sheet 3 (Summary):** same Metric/Value layout, only includes rows for metrics that apply to the spec.

**`/summary/<result_id>` JSON:** keys in `status_breakdown` are conditional per Section 3.

**Dashboard JS edits in [webview/index.html](../../webview/index.html) — minimal and targeted:**
1. The "Issues Found" card currently hardcodes reads of `statusBreakdown.name_updates_needed` and `statusBreakdown.sector_updates_needed`. Replace with a loop over `status_breakdown` keys, excluding `ok`/`missing_from_website`/`extra_on_website` (which already have their own labels in the Issues card). Render `"<count> companies need <label>"` for each remaining key, with a fixed display order `name_mismatches` → `portfolio_mismatches` → `ecosystem_mismatches`.
2. The "Historical Comparison" block similarly hardcodes `name_updates_needed`. Apply the same loop pattern to whatever keys the historical payload includes.

No CSS or layout changes.

**SQLite — fresh start.** Per stakeholder decision, drop `webview/comparison_history.db` as part of the rollout. New `company_history` schema:

```sql
CREATE TABLE company_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER,
    cr_name TEXT,
    brand_name TEXT,
    website_name TEXT,
    portfolio TEXT,           -- nullable, populated for new template only
    website_portfolio TEXT,   -- nullable
    ecosystem TEXT,           -- nullable
    website_ecosystem TEXT,   -- nullable
    match_score REAL,
    status TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (run_id) REFERENCES comparison_runs (id)
);
```

`comparison_runs` is unchanged — its `summary_stats` JSON blob already absorbs whatever new fields the summary generates.

**Historical comparison feature:** dormant on the first run after rollout, returns from the second run onward — same behavior as a fresh install.

## Files affected

| File | Change |
|---|---|
| `webview/app.py` | Call `detect_template` after read; pass `template_spec` to `enhanced_compare_companies` and `summarizer.save_and_summarize`; map `ValueError` → HTTP 400. |
| `webview/compare.py` | Refactor `scrape_website` into the four functions in Section 2; remove `h5`-based sector extraction; output DataFrame columns become `Company` / `Portfolio` / `Ecosystem`. |
| `webview/config.py` | Add facet selectors; remove `company_sector` entry. |
| `webview/enhanced_matching.py` | Add `TemplateSpec` + `detect_template`; rename `normalize_sector` → `normalize_categorical`, `compare_sectors` → `compare_categorical`; remove `sector_synonyms`; rewrite the per-row result builder in `enhanced_compare_companies` to be spec-driven. |
| `webview/results_analyzer.py` | `save_and_summarize` accepts `template_spec`; conditional keys in `status_breakdown`; updated `company_history` schema; updated recommendations to skip portfolio/ecosystem branches when spec doesn't include them. |
| `webview/index.html` | Loop-driven rendering of `status_breakdown` and historical changes. |
| `webview/comparison_history.db` | Deleted; recreated on first run with new schema. |
| `README.md`, `SETUP.md` | Doc refresh covering both templates and the facet scraper. |

## Risks and open questions

- **Selector discovery for the two facet panels.** Placeholder selectors in Section 2 are intentional — the live page needs a quick inspection (via `debug_selectors.py`) to find unique container identifiers for the Portfolio vs. Ecosystem panels. This is implementation work, not a design decision.
- **Scrape time goes from ~30s to 1–3 min.** Acceptable for a quarterly process; flagged so it isn't a surprise in implementation.
- **Cloudflare behavior under repeated facet clicks** is unverified. Stealth setup runs at page open and facet interactions are normal in-page DOM events, so re-challenge is unlikely — but the implementation plan should include a smoke run with facets to confirm.
- **Ecosystem coverage skew between sources.** The new template has 119 ecosystem-tagged rows; the website's facet counts sum to ~83. Some baseline ecosystem assignments may not appear on the website (yielding `Ecosystem Match == No` or `N/A`) and vice versa. This is expected output for the stakeholder to act on, not a defect — flagging here so the first run isn't mistaken for a bug.

## Out of scope for this design

- Matching algorithm changes.
- A UI template selector (we auto-detect; can revisit if a third stakeholder ever has overlapping columns).
- Data migration of legacy SQLite history.
- Generic schema-config / multi-stakeholder framework.
