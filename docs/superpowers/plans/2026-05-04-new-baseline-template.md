# New Baseline Template + Facet Scraper Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Support a new baseline Excel template (different stakeholder schema) alongside the legacy template, and replace the dead card-level sector scraper with one that traverses website facets to capture Portfolio + Ecosystem per company.

**Architecture:** Auto-detect the template at upload, build a `TemplateSpec` that drives all downstream behavior. Scraper is split into focused functions (`_open_portfolio_page`, `_discover_facets`, `_scrape_with_facet`, `scrape_website`) and now traverses 3 portfolio + 6 ecosystem facets. Comparison engine becomes spec-driven, status enum collapses to four values (`OK` / `Add` / `Remove` / `Requires update`) with specifics in per-field columns. SQLite history is dropped and recreated with new nullable columns.

**Tech Stack:** Python 3.13, Flask 3.1, Playwright 1.59 (Firefox), pandas 3.0, openpyxl, rapidfuzz, pytest (added by this plan).

**Spec:** [docs/superpowers/specs/2026-05-03-new-baseline-template-design.md](../specs/2026-05-03-new-baseline-template-design.md)

---

## File map

| Path | Action |
|---|---|
| `webview/tests/__init__.py` | Create (empty package marker) |
| `webview/tests/conftest.py` | Create — adds `webview/` to `sys.path` so tests can import modules |
| `webview/tests/test_template_spec.py` | Create — unit tests for `TemplateSpec` + `detect_template` |
| `webview/tests/test_categorical.py` | Create — unit tests for `normalize_categorical` + `compare_categorical` |
| `webview/tests/test_compare_driver.py` | Create — unit tests for `enhanced_compare_companies` with synthetic data |
| `webview/tests/test_results_analyzer.py` | Create — unit tests for `ResultsSummarizer` schema & spec-awareness |
| `webview/template_spec.py` | Create — `TemplateSpec` dataclass + `detect_template` function |
| `webview/enhanced_matching.py` | Modify — rename helpers, rewrite `enhanced_compare_companies` to be spec-driven |
| `webview/compare.py` | Modify — split into 4 functions, traverse facets, drop `h5` sector scrape |
| `webview/config.py` | Modify — add facet selectors, remove `company_sector` |
| `webview/results_analyzer.py` | Modify — accept `template_spec`, conditional `status_breakdown` keys, new SQLite schema |
| `webview/app.py` | Modify — call `detect_template`, pass spec to driver and summarizer, map `ValueError` → 400 |
| `webview/index.html` | Modify — loop-driven `status_breakdown` rendering in dashboard JS |
| `webview/comparison_history.db` | Delete — recreated on first run with new schema |
| `webview/requirements.txt` | Modify — add `pytest>=8.4.0` |
| `README.md` | Modify — document both templates and the facet scraper |
| `SETUP.md` | Modify — note both templates accepted |

---

## Task 1: Bootstrap pytest infrastructure

**Files:**
- Create: `webview/tests/__init__.py`
- Create: `webview/tests/conftest.py`
- Create: `webview/tests/test_smoke.py`
- Modify: `webview/requirements.txt`

- [ ] **Step 1.1: Add pytest to requirements**

Edit `webview/requirements.txt` to append:

```
pytest>=8.4.0
```

- [ ] **Step 1.2: Install pytest**

Run: `pip install -r webview/requirements.txt`
Expected: pytest installed; "Successfully installed pytest-..." line.

- [ ] **Step 1.3: Create the tests package marker**

Create `webview/tests/__init__.py` with empty content (zero bytes).

- [ ] **Step 1.4: Create conftest.py to put webview/ on sys.path**

Create `webview/tests/conftest.py`:

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
```

- [ ] **Step 1.5: Write a smoke test that verifies imports**

Create `webview/tests/test_smoke.py`:

```python
def test_imports():
    import app
    import compare
    import enhanced_matching
    import results_analyzer
    assert callable(app.app)
```

- [ ] **Step 1.6: Run pytest to verify the smoke test passes**

Run: `pytest webview/tests/ -v`
Expected: `1 passed` for `test_imports`.

- [ ] **Step 1.7: Commit**

```bash
git add webview/requirements.txt webview/tests/
git commit -m "test: bootstrap pytest infrastructure"
```

---

## Task 2: Add TemplateSpec and detect_template

**Files:**
- Create: `webview/template_spec.py`
- Create: `webview/tests/test_template_spec.py`

- [ ] **Step 2.1: Write failing tests for detect_template**

Create `webview/tests/test_template_spec.py`:

```python
import pandas as pd
import pytest
from template_spec import TemplateSpec, detect_template


def test_detects_legacy_template():
    df = pd.DataFrame(columns=["CR Name", "Brand Name", "VRP Sector"])
    spec = detect_template(df)
    assert spec.kind == "legacy"
    assert spec.name_field == "CR Name"
    assert spec.brand_field == "Brand Name"
    assert spec.portfolio_field is None
    assert spec.ecosystem_field is None


def test_detects_new_template():
    df = pd.DataFrame(columns=[
        "CR Name", "Brand Name", "Portfolio", "Inv. Pool",
        "Ecosystem", "Verticals", "Ecosystem Team comments",
        "ISEI Comments", "DX Website",
    ])
    spec = detect_template(df)
    assert spec.kind == "new"
    assert spec.portfolio_field == "Portfolio"
    assert spec.ecosystem_field == "Ecosystem"


def test_strips_trailing_whitespace_in_columns():
    df = pd.DataFrame(columns=["CR Name", "Brand Name", "Portfolio", "Ecosystem", "Verticals "])
    spec = detect_template(df)
    assert spec.kind == "new"
    assert "Verticals" in df.columns
    assert "Verticals " not in df.columns


def test_drops_unnamed_columns():
    df = pd.DataFrame({
        "CR Name": ["Foo"], "Brand Name": ["Foo"],
        "Portfolio": ["Vision"], "Ecosystem": ["Neom"],
        "Unnamed: 7": [None],
    })
    detect_template(df)
    assert "Unnamed: 7" not in df.columns


def test_unknown_template_raises_value_error():
    df = pd.DataFrame(columns=["Some", "Random", "Columns"])
    with pytest.raises(ValueError, match="unrecognized template"):
        detect_template(df)


def test_template_spec_is_frozen():
    spec = TemplateSpec(
        kind="legacy", name_field="CR Name", brand_field="Brand Name",
        portfolio_field=None, ecosystem_field=None,
    )
    with pytest.raises(Exception):
        spec.kind = "new"  # frozen dataclasses raise FrozenInstanceError
```

- [ ] **Step 2.2: Run the tests to confirm they fail**

Run: `pytest webview/tests/test_template_spec.py -v`
Expected: all 6 tests fail with `ModuleNotFoundError: No module named 'template_spec'`.

- [ ] **Step 2.3: Implement template_spec.py**

Create `webview/template_spec.py`:

```python
from dataclasses import dataclass
from typing import Literal, Optional
import pandas as pd


@dataclass(frozen=True)
class TemplateSpec:
    kind: Literal["legacy", "new"]
    name_field: str
    brand_field: str
    portfolio_field: Optional[str]
    ecosystem_field: Optional[str]


def detect_template(df: pd.DataFrame) -> TemplateSpec:
    """Detect baseline template from column headers and clean the DataFrame in place.

    Mutates df: strips trailing whitespace from column names and drops any
    'Unnamed: N' columns (Excel artifacts).
    """
    df.columns = df.columns.str.strip()
    unnamed_cols = [c for c in df.columns if c.startswith("Unnamed:")]
    if unnamed_cols:
        df.drop(columns=unnamed_cols, inplace=True)

    cols = set(df.columns)

    if "VRP Sector" in cols and "Portfolio" not in cols:
        return TemplateSpec(
            kind="legacy",
            name_field="CR Name",
            brand_field="Brand Name",
            portfolio_field=None,
            ecosystem_field=None,
        )

    if {"Portfolio", "Ecosystem"}.issubset(cols):
        return TemplateSpec(
            kind="new",
            name_field="CR Name",
            brand_field="Brand Name",
            portfolio_field="Portfolio",
            ecosystem_field="Ecosystem",
        )

    raise ValueError(
        f"unrecognized template: expected legacy columns "
        f"['CR Name', 'Brand Name', 'VRP Sector'] or new columns "
        f"['CR Name', 'Brand Name', 'Portfolio', 'Ecosystem']; "
        f"got {sorted(cols)}"
    )
```

- [ ] **Step 2.4: Run the tests to confirm they pass**

Run: `pytest webview/tests/test_template_spec.py -v`
Expected: `6 passed`.

- [ ] **Step 2.5: Commit**

```bash
git add webview/template_spec.py webview/tests/test_template_spec.py
git commit -m "feat: add TemplateSpec and detect_template"
```

---

## Task 3: Generalize categorical comparison helpers

**Files:**
- Modify: `webview/enhanced_matching.py`
- Create: `webview/tests/test_categorical.py`

- [ ] **Step 3.1: Write failing tests for normalize_categorical and compare_categorical**

Create `webview/tests/test_categorical.py`:

```python
import pandas as pd
import pytest
from enhanced_matching import EnhancedCompanyMatcher


@pytest.fixture
def matcher():
    return EnhancedCompanyMatcher()


def test_normalize_categorical_lowercases_and_strips(matcher):
    assert matcher.normalize_categorical("  Vision  ") == "vision"


def test_normalize_categorical_handles_none(matcher):
    assert matcher.normalize_categorical(None) == ""
    assert matcher.normalize_categorical(pd.NA) == ""
    assert matcher.normalize_categorical("") == ""


def test_compare_categorical_exact_match(matcher):
    result = matcher.compare_categorical("Vision", "Vision")
    assert result["match"] is True
    assert result["score"] == 100


def test_compare_categorical_case_insensitive(matcher):
    result = matcher.compare_categorical("VISION", "vision")
    assert result["match"] is True


def test_compare_categorical_fuzzy_match_above_threshold(matcher):
    # Punctuation drift between sources
    a = "Clean Energy, Water and Renewables Infrastructure"
    b = "Clean Energy, Water, & Renewable Infrastructure"
    result = matcher.compare_categorical(a, b)
    assert result["match"] is True
    assert result["score"] >= 80


def test_compare_categorical_no_match(matcher):
    result = matcher.compare_categorical("Vision", "Financial")
    assert result["match"] is False


def test_compare_categorical_empty_inputs(matcher):
    result = matcher.compare_categorical("", "Vision")
    assert result["match"] is False
    assert result["score"] == 0
```

- [ ] **Step 3.2: Run the tests to confirm they fail**

Run: `pytest webview/tests/test_categorical.py -v`
Expected: all 7 tests fail with `AttributeError: 'EnhancedCompanyMatcher' object has no attribute 'normalize_categorical'`.

- [ ] **Step 3.3: Rename helpers and remove sector_synonyms**

In `webview/enhanced_matching.py`:

Replace the `sector_synonyms` block in `__init__` (lines beginning with `# Sector synonyms mapping` through the end of the dictionary) with nothing — delete the attribute entirely.

Rename method `normalize_sector` → `normalize_categorical`. Body stays the same except remove the synonyms loop (the few lines that iterate `self.sector_synonyms`). The method becomes:

```python
def normalize_categorical(self, value: str) -> str:
    """Lowercase + strip; return '' for null/empty inputs."""
    if not value or pd.isna(value):
        return ""
    return str(value).lower().strip()
```

Rename method `compare_sectors` → `compare_categorical`. Body stays the same except calls to `self.normalize_sector` become `self.normalize_categorical`. Threshold parameter defaults to `self.sector_threshold` for backward continuity:

```python
def compare_categorical(self, baseline_value: str, website_value: str) -> dict:
    norm_baseline = self.normalize_categorical(baseline_value)
    norm_website = self.normalize_categorical(website_value)

    if not norm_baseline or not norm_website:
        return {"match": False, "score": 0,
                "normalized_baseline": norm_baseline,
                "normalized_website": norm_website}

    if norm_baseline == norm_website:
        return {"match": True, "score": 100,
                "normalized_baseline": norm_baseline,
                "normalized_website": norm_website}

    score = fuzz.ratio(norm_baseline, norm_website)
    return {"match": score >= self.sector_threshold, "score": score,
            "normalized_baseline": norm_baseline,
            "normalized_website": norm_website}
```

In `enhanced_compare_companies` further down the file, change the call site from:

```python
sector_comparison = matcher.compare_sectors(
    baseline_row.get('VRP Sector', ''),
    website_sector
)
```

to (this is a temporary line — the whole function gets rewritten in Task 5):

```python
sector_comparison = matcher.compare_categorical(
    baseline_row.get('VRP Sector', ''),
    website_sector
)
```

- [ ] **Step 3.4: Run categorical tests to confirm they pass**

Run: `pytest webview/tests/test_categorical.py -v`
Expected: `7 passed`.

- [ ] **Step 3.5: Run the full test suite to confirm nothing else broke**

Run: `pytest webview/tests/ -v`
Expected: all tests pass.

- [ ] **Step 3.6: Commit**

```bash
git add webview/enhanced_matching.py webview/tests/test_categorical.py
git commit -m "refactor: rename sector helpers to categorical, drop sector_synonyms"
```

---

## Task 4: Update config.py for facet selectors

**Files:**
- Modify: `webview/config.py`

- [ ] **Step 4.1: Replace the SELECTORS dict**

Replace the entire contents of `webview/config.py` with:

```python
# Configuration settings
WEBSITE_URL = "https://www.pif.gov.sa/en/our-investments/our-portfolio/"
FUZZY_MATCH_THRESHOLD = 85       # Minimum score for fuzzy matching
SECTOR_MATCH_THRESHOLD = 80      # Minimum score for categorical (portfolio/ecosystem) matching

# Selectors for web scraping
SELECTORS = {
    "cookie_accept": "button#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll",
    "pagination": "ul.page-selector-list li a.page-selector-item-link",
    "company_card": ".search-result-list li a",
    "company_name": "h4.investmentTitle.field-title",
    # Facet panels — exact container selectors get nailed down in Task 7 by
    # inspecting the live page; placeholder values shown here.
    "portfolio_facet_panel": "div.facet-search-filter[data-facet='portfolio']",
    "ecosystem_facet_panel": "div.facet-search-filter[data-facet='ecosystem']",
    "facet_item": "p.facet-value",
    "facet_value_attr": "data-facetvalue",
    "facet_checkbox": "input[type='checkbox']",
}
```

- [ ] **Step 4.2: Verify config still imports cleanly**

Run: `python3 -c "import sys; sys.path.insert(0, 'webview'); import config; print(config.SELECTORS.keys())"`
Expected: prints all selector keys including the new facet ones; no `company_sector` key.

- [ ] **Step 4.3: Run smoke test**

Run: `pytest webview/tests/test_smoke.py -v`
Expected: passes (the smoke test just verifies imports).

- [ ] **Step 4.4: Commit**

```bash
git add webview/config.py
git commit -m "feat(config): add facet selectors, remove dead company_sector"
```

---

## Task 5: Spec-driven enhanced_compare_companies

**Files:**
- Modify: `webview/enhanced_matching.py`
- Create: `webview/tests/test_compare_driver.py`

- [ ] **Step 5.1: Write failing tests for the spec-driven driver**

Create `webview/tests/test_compare_driver.py`:

```python
import pandas as pd
import pytest
from enhanced_matching import enhanced_compare_companies
from template_spec import TemplateSpec


@pytest.fixture
def legacy_spec():
    return TemplateSpec(
        kind="legacy", name_field="CR Name", brand_field="Brand Name",
        portfolio_field=None, ecosystem_field=None,
    )


@pytest.fixture
def new_spec():
    return TemplateSpec(
        kind="new", name_field="CR Name", brand_field="Brand Name",
        portfolio_field="Portfolio", ecosystem_field="Ecosystem",
    )


@pytest.fixture
def website_df():
    return pd.DataFrame([
        {"Company": "ACWA Power", "Portfolio": "Vision", "Ecosystem": "Clean Energy, Water and Renewables Infrastructure"},
        {"Company": "Neom Company", "Portfolio": "Strategic", "Ecosystem": "Neom"},
        {"Company": "AccorInvest Group", "Portfolio": "Financial", "Ecosystem": None},
    ])


def test_legacy_template_status_only_uses_four_values(legacy_spec, website_df):
    baseline = pd.DataFrame([
        {"CR Name": "Acwa Power Company", "Brand Name": "ACWA POWER", "VRP Sector": "Power"},
        {"CR Name": "Missing Company", "Brand Name": "MISSING", "VRP Sector": "Foo"},
    ])
    results, _ = enhanced_compare_companies(baseline, website_df, legacy_spec)

    assert set(results["Status"].unique()).issubset({"OK", "Add", "Remove", "Requires update"})
    # Legacy never gets portfolio/ecosystem columns
    assert "Portfolio Match" not in results.columns
    assert "Ecosystem Match" not in results.columns


def test_new_template_includes_portfolio_and_ecosystem_columns(new_spec, website_df):
    baseline = pd.DataFrame([
        {"CR Name": "Acwa Power Company", "Brand Name": "ACWA POWER",
         "Portfolio": "Vision", "Ecosystem": "Clean Energy, Water, & Renewable Infrastructure"},
    ])
    results, _ = enhanced_compare_companies(baseline, website_df, new_spec)

    expected_cols = {
        "Portfolio", "Website Portfolio", "Portfolio Match",
        "Ecosystem", "Website Ecosystem", "Ecosystem Match",
    }
    assert expected_cols.issubset(set(results.columns))


def test_new_template_perfect_match_is_ok(new_spec, website_df):
    baseline = pd.DataFrame([
        {"CR Name": "Acwa Power Company", "Brand Name": "ACWA POWER",
         "Portfolio": "Vision", "Ecosystem": "Clean Energy, Water, & Renewable Infrastructure"},
    ])
    results, _ = enhanced_compare_companies(baseline, website_df, new_spec)
    row = results[results["CR Name"] == "Acwa Power Company"].iloc[0]
    assert row["Status"] == "OK"
    assert row["Portfolio Match"] == "Yes"
    assert row["Ecosystem Match"] == "Yes"


def test_new_template_portfolio_mismatch_marks_requires_update(new_spec, website_df):
    baseline = pd.DataFrame([
        {"CR Name": "Acwa Power Company", "Brand Name": "ACWA POWER",
         "Portfolio": "Strategic", "Ecosystem": "Clean Energy, Water, & Renewable Infrastructure"},
    ])
    results, _ = enhanced_compare_companies(baseline, website_df, new_spec)
    row = results[results["CR Name"] == "Acwa Power Company"].iloc[0]
    assert row["Status"] == "Requires update"
    assert row["Portfolio Match"] == "No"
    assert row["Ecosystem Match"] == "Yes"


def test_new_template_empty_baseline_ecosystem_marks_na(new_spec, website_df):
    baseline = pd.DataFrame([
        {"CR Name": "AccorInvest Group", "Brand Name": "AccorInvest",
         "Portfolio": "Financial", "Ecosystem": None},
    ])
    results, _ = enhanced_compare_companies(baseline, website_df, new_spec)
    row = results[results["CR Name"] == "AccorInvest Group"].iloc[0]
    assert row["Status"] == "OK"
    assert row["Ecosystem Match"] == "N/A"


def test_missing_baseline_company_status_add(new_spec, website_df):
    baseline = pd.DataFrame([
        {"CR Name": "Brand New Co", "Brand Name": "BRAND NEW",
         "Portfolio": "Vision", "Ecosystem": "Tourism, Travel and Entertainment"},
    ])
    results, _ = enhanced_compare_companies(baseline, website_df, new_spec)
    row = results[results["CR Name"] == "Brand New Co"].iloc[0]
    assert row["Status"] == "Add"


def test_unmatched_website_companies_get_remove_status(new_spec, website_df):
    baseline = pd.DataFrame([
        {"CR Name": "Acwa Power Company", "Brand Name": "ACWA POWER",
         "Portfolio": "Vision", "Ecosystem": "Clean Energy, Water, & Renewable Infrastructure"},
    ])
    results, unmatched = enhanced_compare_companies(baseline, website_df, new_spec)
    remove_rows = results[results["Status"] == "Remove"]
    assert len(remove_rows) == 2  # Neom Company + AccorInvest Group
    assert len(unmatched) == 2
```

- [ ] **Step 5.2: Run the tests to confirm they fail**

Run: `pytest webview/tests/test_compare_driver.py -v`
Expected: most tests fail; the existing `enhanced_compare_companies` doesn't accept a `template_spec` argument.

- [ ] **Step 5.3: Rewrite enhanced_compare_companies**

In `webview/enhanced_matching.py`, replace the entire `enhanced_compare_companies` function with the spec-driven version. Also add a new `_build_result_row` helper to keep the per-row construction readable.

```python
def _build_result_row(
    matcher: 'EnhancedCompanyMatcher',
    baseline_row: pd.Series,
    best_match,
    match_info: dict,
    spec: 'TemplateSpec',
) -> dict:
    """Build a single result row, including spec-conditional columns."""
    exists = match_info['score'] >= matcher.fuzzy_threshold and best_match is not None
    website_name = best_match['Company'] if exists else ""

    row = {
        "CR Name": baseline_row.get(spec.name_field, ''),
        "Brand Name": baseline_row.get(spec.brand_field, ''),
        "Website Name": website_name,
    }

    name_matches = exists and match_info['score'] >= matcher.exact_match_threshold
    field_mismatch = False

    if spec.portfolio_field is not None:
        baseline_portfolio = baseline_row.get(spec.portfolio_field, '')
        website_portfolio = best_match['Portfolio'] if exists else ''
        if not baseline_portfolio:
            portfolio_match = "N/A"
        elif not exists:
            portfolio_match = "N/A"
        else:
            cmp = matcher.compare_categorical(baseline_portfolio, website_portfolio)
            portfolio_match = "Yes" if cmp['match'] else "No"
            if not cmp['match']:
                field_mismatch = True
        row["Portfolio"] = baseline_portfolio
        row["Website Portfolio"] = website_portfolio
        row["Portfolio Match"] = portfolio_match

    if spec.ecosystem_field is not None:
        baseline_ecosystem = baseline_row.get(spec.ecosystem_field, '')
        website_ecosystem = (best_match['Ecosystem'] if exists else '') or ''
        if not baseline_ecosystem or pd.isna(baseline_ecosystem):
            ecosystem_match = "N/A"
        elif not exists:
            ecosystem_match = "N/A"
        else:
            cmp = matcher.compare_categorical(baseline_ecosystem, website_ecosystem)
            ecosystem_match = "Yes" if cmp['match'] else "No"
            if not cmp['match']:
                field_mismatch = True
        row["Ecosystem"] = baseline_ecosystem
        row["Website Ecosystem"] = website_ecosystem
        row["Ecosystem Match"] = ecosystem_match

    row.update({
        "Match Score": round(match_info['score'], 1),
        "Match Type": match_info.get('match_type', 'none'),
        "Match Confidence": match_info.get('confidence', 'none'),
        "Matched Field": match_info.get('matched_field', 'N/A'),
        "PC exist in website": "Yes" if exists else "No",
    })

    if not exists:
        row["Status"] = "Add"
    elif not name_matches or field_mismatch:
        row["Status"] = "Requires update"
    else:
        row["Status"] = "OK"

    return row


def _build_remove_row(website_row: pd.Series, spec: 'TemplateSpec') -> dict:
    """Build a result row for an unmatched website company."""
    row = {
        "CR Name": "",
        "Brand Name": "",
        "Website Name": website_row['Company'],
    }
    if spec.portfolio_field is not None:
        row["Portfolio"] = ""
        row["Website Portfolio"] = website_row.get('Portfolio', '') or ''
        row["Portfolio Match"] = "N/A"
    if spec.ecosystem_field is not None:
        row["Ecosystem"] = ""
        row["Website Ecosystem"] = website_row.get('Ecosystem', '') or ''
        row["Ecosystem Match"] = "N/A"
    row.update({
        "Match Score": 0,
        "Match Type": "unmatched",
        "Match Confidence": "none",
        "Matched Field": "N/A",
        "PC exist in website": "Yes",
        "Status": "Remove",
    })
    return row


def enhanced_compare_companies(
    baseline_df: pd.DataFrame,
    website_df: pd.DataFrame,
    template_spec,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Compare baseline against website using the supplied TemplateSpec."""
    matcher = EnhancedCompanyMatcher()
    results = []
    matched_website_companies = set()

    print(f"Comparing {len(baseline_df)} baseline companies against "
          f"{len(website_df)} website companies (template={template_spec.kind})...")

    for idx, baseline_row in baseline_df.iterrows():
        best_match, match_info = matcher.find_best_match(baseline_row, website_df)
        if best_match is not None and match_info['score'] >= matcher.fuzzy_threshold:
            matched_website_companies.add(best_match['Company'])
        results.append(_build_result_row(matcher, baseline_row, best_match, match_info, template_spec))

    for _, website_row in website_df.iterrows():
        if website_row['Company'] not in matched_website_companies:
            results.append(_build_remove_row(website_row, template_spec))

    results_df = pd.DataFrame(results)

    unmatched_rows = []
    for _, website_row in website_df.iterrows():
        if website_row['Company'] not in matched_website_companies:
            entry = {"Company": website_row['Company']}
            if 'Portfolio' in website_df.columns:
                entry["Portfolio"] = website_row.get('Portfolio', '')
            if 'Ecosystem' in website_df.columns:
                entry["Ecosystem"] = website_row.get('Ecosystem', '')
            unmatched_rows.append(entry)
    unmatched_df = pd.DataFrame(unmatched_rows)

    return results_df, unmatched_df
```

No new import is needed in `enhanced_matching.py` — the spec parameter is annotated with the string forward reference `'TemplateSpec'` to avoid a circular dependency.

- [ ] **Step 5.4: Run the driver tests to confirm they pass**

Run: `pytest webview/tests/test_compare_driver.py -v`
Expected: `7 passed`.

- [ ] **Step 5.5: Run the full suite**

Run: `pytest webview/tests/ -v`
Expected: all tests pass.

- [ ] **Step 5.6: Commit**

```bash
git add webview/enhanced_matching.py webview/tests/test_compare_driver.py
git commit -m "feat: spec-driven enhanced_compare_companies with new status enum"
```

---

## Task 6: Spec-aware ResultsSummarizer + new SQLite schema

**Files:**
- Modify: `webview/results_analyzer.py`
- Create: `webview/tests/test_results_analyzer.py`

- [ ] **Step 6.1: Write failing tests for the summarizer**

Create `webview/tests/test_results_analyzer.py`:

```python
import os
import pandas as pd
import pytest
from results_analyzer import ResultsSummarizer
from template_spec import TemplateSpec


@pytest.fixture
def legacy_spec():
    return TemplateSpec(
        kind="legacy", name_field="CR Name", brand_field="Brand Name",
        portfolio_field=None, ecosystem_field=None,
    )


@pytest.fixture
def new_spec():
    return TemplateSpec(
        kind="new", name_field="CR Name", brand_field="Brand Name",
        portfolio_field="Portfolio", ecosystem_field="Ecosystem",
    )


@pytest.fixture
def tmp_summarizer(tmp_path):
    db = tmp_path / "history.db"
    return ResultsSummarizer(db_path=str(db))


def _legacy_results():
    return pd.DataFrame([
        {"CR Name": "A", "Brand Name": "A", "Website Name": "A",
         "Match Score": 100, "PC exist in website": "Yes", "Status": "OK"},
        {"CR Name": "B", "Brand Name": "B", "Website Name": "B",
         "Match Score": 88, "PC exist in website": "Yes", "Status": "Requires update"},
        {"CR Name": "C", "Brand Name": "C", "Website Name": "",
         "Match Score": 0, "PC exist in website": "No", "Status": "Add"},
        {"CR Name": "", "Brand Name": "", "Website Name": "X",
         "Match Score": 0, "PC exist in website": "Yes", "Status": "Remove"},
    ])


def _new_results():
    return pd.DataFrame([
        {"CR Name": "A", "Brand Name": "A", "Website Name": "A",
         "Portfolio": "Vision", "Website Portfolio": "Vision", "Portfolio Match": "Yes",
         "Ecosystem": "Neom", "Website Ecosystem": "Neom", "Ecosystem Match": "Yes",
         "Match Score": 100, "PC exist in website": "Yes", "Status": "OK"},
        {"CR Name": "B", "Brand Name": "B", "Website Name": "B",
         "Portfolio": "Vision", "Website Portfolio": "Strategic", "Portfolio Match": "No",
         "Ecosystem": "", "Website Ecosystem": "", "Ecosystem Match": "N/A",
         "Match Score": 100, "PC exist in website": "Yes", "Status": "Requires update"},
        {"CR Name": "C", "Brand Name": "C", "Website Name": "C",
         "Portfolio": "Vision", "Website Portfolio": "Vision", "Portfolio Match": "Yes",
         "Ecosystem": "Neom", "Website Ecosystem": "Industrials and Logistics", "Ecosystem Match": "No",
         "Match Score": 100, "PC exist in website": "Yes", "Status": "Requires update"},
    ])


def test_legacy_status_breakdown_omits_portfolio_and_ecosystem(tmp_summarizer, legacy_spec):
    summary = tmp_summarizer.save_and_summarize(_legacy_results(), "legacy.xlsx", 5, legacy_spec)
    breakdown = summary['current_analysis']['status_breakdown']
    assert "ok" in breakdown
    assert "missing_from_website" in breakdown
    assert "extra_on_website" in breakdown
    assert "name_mismatches" in breakdown
    assert "portfolio_mismatches" not in breakdown
    assert "ecosystem_mismatches" not in breakdown


def test_new_status_breakdown_includes_portfolio_and_ecosystem(tmp_summarizer, new_spec):
    summary = tmp_summarizer.save_and_summarize(_new_results(), "new.xlsx", 5, new_spec)
    breakdown = summary['current_analysis']['status_breakdown']
    assert breakdown["ok"] == 1
    assert breakdown["portfolio_mismatches"] == 1
    assert breakdown["ecosystem_mismatches"] == 1
    assert "name_mismatches" in breakdown


def test_new_db_schema_includes_portfolio_and_ecosystem_columns(tmp_summarizer):
    import sqlite3
    conn = sqlite3.connect(tmp_summarizer.tracker.db_path)
    cols = [r[1] for r in conn.execute("PRAGMA table_info(company_history)").fetchall()]
    conn.close()
    for needed in ("portfolio", "website_portfolio", "ecosystem", "website_ecosystem"):
        assert needed in cols
```

- [ ] **Step 6.2: Run tests to confirm they fail**

Run: `pytest webview/tests/test_results_analyzer.py -v`
Expected: failures — `save_and_summarize` doesn't accept a spec arg, and the schema doesn't have the new columns.

- [ ] **Step 6.3: Update HistoricalTracker schema**

In `webview/results_analyzer.py`, modify `HistoricalTracker.__init__` to accept `db_path` (it already does) and update `init_database` to use the new schema. Also drop the old DB file if it exists at module-level boot — but only do this once at import time, not in `init_database` (which runs per-instance and shouldn't side-effect unrelated paths). The safest choice: leave deletion of the production DB to a separate manual step (Task 11), and let `init_database` simply create whatever is missing.

Replace the body of `init_database` with:

```python
def init_database(self):
    """Create tables if they don't exist (with current schema)."""
    conn = sqlite3.connect(self.db_path)
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS comparison_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_date TEXT NOT NULL,
            baseline_file TEXT NOT NULL,
            total_baseline_companies INTEGER,
            total_website_companies INTEGER,
            summary_stats TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS company_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER,
            cr_name TEXT,
            brand_name TEXT,
            website_name TEXT,
            portfolio TEXT,
            website_portfolio TEXT,
            ecosystem TEXT,
            website_ecosystem TEXT,
            match_score REAL,
            status TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (run_id) REFERENCES comparison_runs (id)
        )
    ''')

    conn.commit()
    conn.close()
```

Update `save_comparison_run` to write the new columns:

```python
def save_comparison_run(self, results_df: pd.DataFrame, baseline_file: str,
                       website_count: int, summary: Dict) -> int:
    conn = sqlite3.connect(self.db_path)
    cursor = conn.cursor()

    cursor.execute('''
        INSERT INTO comparison_runs
        (run_date, baseline_file, total_baseline_companies, total_website_companies, summary_stats)
        VALUES (?, ?, ?, ?, ?)
    ''', (
        datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        baseline_file,
        len(results_df[results_df['CR Name'] != '']),
        website_count,
        json.dumps(summary),
    ))

    run_id = cursor.lastrowid

    for _, row in results_df.iterrows():
        cursor.execute('''
            INSERT INTO company_history
            (run_id, cr_name, brand_name, website_name,
             portfolio, website_portfolio, ecosystem, website_ecosystem,
             match_score, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            run_id,
            row.get('CR Name', ''),
            row.get('Brand Name', ''),
            row.get('Website Name', ''),
            row.get('Portfolio', None),
            row.get('Website Portfolio', None),
            row.get('Ecosystem', None),
            row.get('Website Ecosystem', None),
            row.get('Match Score', 0),
            row.get('Status', ''),
        ))

    conn.commit()
    conn.close()
    return run_id
```

- [ ] **Step 6.4: Update ResultsSummarizer to be spec-aware**

Modify `ResultsSummarizer.__init__` to accept an optional `db_path`:

```python
def __init__(self, db_path: str = "comparison_history.db"):
    self.tracker = HistoricalTracker(db_path=db_path)
```

Replace `generate_summary` to accept a `template_spec` and conditionally include keys:

```python
def generate_summary(self, results_df: pd.DataFrame, baseline_file: str,
                    website_count: int, template_spec) -> Dict:
    total_baseline = len(results_df[results_df['CR Name'] != ''])

    exists = results_df['PC exist in website'] == 'Yes'
    is_baseline = results_df['CR Name'] != ''

    breakdown = {
        "ok": int((results_df['Status'] == 'OK').sum()),
        "missing_from_website": int((results_df['Status'] == 'Add').sum()),
        "extra_on_website": int((results_df['Status'] == 'Remove').sum()),
        "name_mismatches": int((exists & is_baseline & (results_df['Match Score'] < 95)).sum()),
    }

    if template_spec.portfolio_field is not None and 'Portfolio Match' in results_df.columns:
        breakdown["portfolio_mismatches"] = int((results_df['Portfolio Match'] == 'No').sum())

    if template_spec.ecosystem_field is not None and 'Ecosystem Match' in results_df.columns:
        breakdown["ecosystem_mismatches"] = int((results_df['Ecosystem Match'] == 'No').sum())

    matched = int(exists.sum())
    accuracy_rate = round(matched / total_baseline * 100, 1) if total_baseline else 0.0

    return {
        'run_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'baseline_file': baseline_file,
        'template_kind': template_spec.kind,
        'totals': {
            'baseline_companies': total_baseline,
            'website_companies': website_count,
            'matched_companies': matched,
            'accuracy_rate': accuracy_rate,
        },
        'status_breakdown': breakdown,
    }
```

Update `save_and_summarize` to thread the spec through:

```python
def save_and_summarize(self, results_df: pd.DataFrame, baseline_file: str,
                      website_count: int, template_spec) -> Dict:
    summary = self.generate_summary(results_df, baseline_file, website_count, template_spec)
    historical_comparison = self.generate_historical_comparison(summary)
    run_id = self.tracker.save_comparison_run(results_df, baseline_file, website_count, summary)

    return {
        'run_id': run_id,
        'current_analysis': summary,
        'historical_comparison': historical_comparison,
        'recommendations': self._generate_recommendations(summary, historical_comparison, template_spec),
    }
```

Update `_generate_recommendations` to take the spec and skip portfolio/ecosystem branches when not applicable:

```python
def _generate_recommendations(self, summary: Dict, historical: Dict, template_spec) -> List[str]:
    recommendations = []
    breakdown = summary['status_breakdown']

    if breakdown.get('missing_from_website', 0) > 10:
        recommendations.append(
            f"HIGH PRIORITY: {breakdown['missing_from_website']} companies are missing from the website."
        )

    if breakdown.get('extra_on_website', 0) > 5:
        recommendations.append(
            f"REVIEW NEEDED: {breakdown['extra_on_website']} companies appear on the website but not in your baseline."
        )

    if breakdown.get('name_mismatches', 0) > 0:
        recommendations.append(
            f"Name standardization needed for {breakdown['name_mismatches']} companies."
        )

    if template_spec.portfolio_field and breakdown.get('portfolio_mismatches', 0) > 0:
        recommendations.append(
            f"Portfolio assignment differs for {breakdown['portfolio_mismatches']} companies."
        )

    if template_spec.ecosystem_field and breakdown.get('ecosystem_mismatches', 0) > 0:
        recommendations.append(
            f"Ecosystem assignment differs for {breakdown['ecosystem_mismatches']} companies."
        )

    accuracy = summary['totals']['accuracy_rate']
    if accuracy < 95:
        recommendations.append(
            f"Current accuracy is {accuracy}%. Review companies with low match scores."
        )

    if historical.get('has_historical_data'):
        if historical.get('overall_trend') == 'declining':
            recommendations.append("Data quality is declining vs. previous run.")
        elif historical.get('overall_trend') == 'improving':
            recommendations.append("Data quality is improving vs. previous run.")

    return recommendations
```

Also update `generate_historical_comparison` so it iterates whatever keys are in `current_summary['status_breakdown']` rather than the old hardcoded list:

```python
def generate_historical_comparison(self, current_summary: Dict) -> Dict:
    historical_data = self.tracker.get_historical_comparison()
    if historical_data is None:
        return {'has_historical_data': False, 'message': 'No historical data available'}

    historical_status_counts = historical_data['status'].value_counts().to_dict()
    current_breakdown = current_summary['status_breakdown']

    # Map status_breakdown keys back to Status string values for historical comparison
    status_label_map = {
        'ok': 'OK', 'missing_from_website': 'Add', 'extra_on_website': 'Remove',
    }

    changes = {}
    for key, current_count in current_breakdown.items():
        historical_count = historical_status_counts.get(status_label_map.get(key, ''), 0)
        change = current_count - historical_count
        changes[key] = {
            'current': current_count,
            'previous': historical_count,
            'change': change,
            'trend': 'improved' if change < 0 and key != 'ok' else 'worsened' if change > 0 and key != 'ok' else 'same',
        }

    return {
        'has_historical_data': True,
        'changes': changes,
        'overall_trend': self._calculate_overall_trend(changes),
    }
```

- [ ] **Step 6.5: Run results_analyzer tests**

Run: `pytest webview/tests/test_results_analyzer.py -v`
Expected: `3 passed`.

- [ ] **Step 6.6: Run the full suite**

Run: `pytest webview/tests/ -v`
Expected: all tests pass.

- [ ] **Step 6.7: Commit**

```bash
git add webview/results_analyzer.py webview/tests/test_results_analyzer.py
git commit -m "feat(summary): spec-aware status_breakdown + new SQLite schema"
```

---

## Task 7: Extract setup helper from scrape_website

**Files:**
- Modify: `webview/compare.py`

This is a pure refactor with no behavior change yet — extract the page-setup logic into `_open_portfolio_page` so the orchestrator can be rebuilt cleanly in subsequent tasks.

- [ ] **Step 7.1: Add the extracted setup helper**

In `webview/compare.py`, add this helper above the existing `scrape_website`:

```python
async def _open_portfolio_page(playwright, headless, browser_type, timeout):
    """Launch the browser, apply stealth, navigate, dismiss cookies, and wait for the company list.

    Returns (browser, context, page) so the caller can drive interactions and tear down.
    """
    if browser_type == 'firefox':
        browser = await playwright.firefox.launch(headless=headless)
    elif browser_type == 'webkit':
        browser = await playwright.webkit.launch(headless=headless)
    else:
        browser = await playwright.chromium.launch(
            headless=headless,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--disable-dev-shm-usage',
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-web-security',
                '--disable-features=IsolateOrigins,site-per-process',
            ],
        )

    context = await browser.new_context(
        viewport={'width': 1920, 'height': 1080},
        user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
        locale='en-US',
        timezone_id='America/New_York',
        color_scheme='light',
        permissions=['geolocation'],
        extra_http_headers={
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Cache-Control': 'max-age=0',
            'sec-ch-ua': '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"macOS"',
        },
    )

    page = await context.new_page()
    await Stealth().apply_stealth_async(page)

    await page.mouse.move(100, 100)
    await page.wait_for_timeout(500)

    try:
        await page.goto(WEBSITE_URL, wait_until='domcontentloaded', timeout=timeout)
        await page.wait_for_timeout(5000)
    except Exception:
        await page.goto(WEBSITE_URL, wait_until='load', timeout=timeout)
        await page.wait_for_timeout(5000)

    content = await page.content()
    if 'cloudflare' in content.lower() and ('challenge' in content.lower() or 'checking' in content.lower()):
        print("⚠ CLOUDFLARE CHALLENGE DETECTED — waiting 30s...")
        await page.wait_for_timeout(30000)
        if not headless:
            content = await page.content()
            if 'cloudflare' in content.lower() and 'challenge' in content.lower():
                print("   Solve manually in browser; waiting 120s...")
                await page.wait_for_timeout(120000)

    try:
        await page.wait_for_selector(SELECTORS["cookie_accept"], timeout=5000)
        await page.click(SELECTORS["cookie_accept"])
        await page.wait_for_timeout(3000)
    except Exception:
        pass

    await page.wait_for_selector('div.search-results', state='visible', timeout=30000)
    await page.wait_for_selector('ul.search-result-list', state='visible', timeout=30000)
    await page.wait_for_timeout(3000)

    return browser, context, page
```

- [ ] **Step 7.2: Run smoke test**

Run: `pytest webview/tests/test_smoke.py -v`
Expected: passes (the helper isn't called yet).

- [ ] **Step 7.3: Commit**

```bash
git add webview/compare.py
git commit -m "refactor(scrape): extract _open_portfolio_page helper"
```

---

## Task 8: Discover facets from the live page

**Files:**
- Modify: `webview/compare.py`

This task requires a quick manual inspection of the live page to identify the actual container selectors for the Portfolio and Ecosystem facet panels. Update `webview/config.py` once the real selectors are known.

- [ ] **Step 8.1: Identify real facet panel selectors**

Run: `python3 webview/debug_selectors.py`

In the opened browser, find the Portfolio facet panel and the Ecosystem facet panel. Identify a unique CSS selector for each (look for `data-facet="..."` attributes, a parent heading, or a parent class). Write them down.

- [ ] **Step 8.2: Update config.py with the real selectors**

Edit `webview/config.py` and replace the placeholder values for `portfolio_facet_panel` and `ecosystem_facet_panel` with the real selectors from Step 8.1.

- [ ] **Step 8.3: Add the discovery helper**

In `webview/compare.py`, add below `_open_portfolio_page`:

```python
async def _discover_facets(page) -> dict:
    """Read facet values from the Portfolio and Ecosystem panels.

    Returns {"portfolio": [...values...], "ecosystem": [...values...]}.
    Values come from the `data-facetvalue` attribute and are URL-encoded —
    the caller decodes them before display.
    """
    from urllib.parse import unquote

    async def _read(panel_selector: str) -> list[str]:
        items = await page.query_selector_all(
            f'{panel_selector} {SELECTORS["facet_item"]}'
        )
        values = []
        for item in items:
            raw = await item.get_attribute(SELECTORS["facet_value_attr"])
            if raw:
                values.append(unquote(raw))
        return values

    portfolio = await _read(SELECTORS["portfolio_facet_panel"])
    ecosystem = await _read(SELECTORS["ecosystem_facet_panel"])

    print(f"Discovered facets: portfolio={portfolio}, ecosystem={ecosystem}")
    return {"portfolio": portfolio, "ecosystem": ecosystem}
```

- [ ] **Step 8.4: Run smoke test**

Run: `pytest webview/tests/test_smoke.py -v`
Expected: passes.

- [ ] **Step 8.5: Commit**

```bash
git add webview/compare.py webview/config.py
git commit -m "feat(scrape): add _discover_facets and real panel selectors"
```

---

## Task 9: Single-facet scrape helper

**Files:**
- Modify: `webview/compare.py`

- [ ] **Step 9.1: Add the per-facet scraper**

In `webview/compare.py`, add below `_discover_facets`:

```python
async def _scrape_with_facet(page, panel_selector: str, facet_value: str) -> list[str]:
    """Click one facet checkbox, paginate the filtered list, return company names, then uncheck.

    Asserts that the result list visibly changed after the click — if it didn't,
    we abort this facet and return an empty list rather than scrape the
    unfiltered list silently.
    """
    from urllib.parse import quote

    encoded = quote(facet_value)
    item_selector = (
        f'{panel_selector} {SELECTORS["facet_item"]}'
        f'[{SELECTORS["facet_value_attr"]}="{encoded}"]'
    )

    # Capture the first card's name so we can detect a change
    before_card = await page.query_selector('ul.search-result-list li a h4')
    before_name = await before_card.inner_text() if before_card else ""
    before_count_elems = await page.query_selector_all('ul.search-result-list li')
    before_count = len(before_count_elems)

    # Click the facet's checkbox
    try:
        item = await page.wait_for_selector(item_selector, timeout=10000)
        checkbox = await item.query_selector(SELECTORS["facet_checkbox"])
        target = checkbox or item
        await target.click()
    except Exception as e:
        print(f"  ⚠ could not click facet '{facet_value}': {e}")
        return []

    # Wait for the list to actually change
    changed = False
    for _ in range(20):
        await page.wait_for_timeout(500)
        after_card = await page.query_selector('ul.search-result-list li a h4')
        after_name = await after_card.inner_text() if after_card else ""
        after_count = len(await page.query_selector_all('ul.search-result-list li'))
        if after_name != before_name or after_count != before_count:
            changed = True
            break

    if not changed:
        print(f"  ⚠ facet '{facet_value}' click had no visible effect; skipping")
        # Try to uncheck anyway to restore state
        try:
            await target.click()
            await page.wait_for_timeout(1000)
        except Exception:
            pass
        return []

    # Determine total pages for the filtered list
    page_links = await page.query_selector_all('ul.page-selector-list li a')
    page_numbers = []
    for link in page_links:
        text = await link.inner_text()
        if text.isdigit():
            page_numbers.append(int(text))
    total_pages = max(page_numbers) if page_numbers else 1

    names: list[str] = []
    for page_num in range(1, total_pages + 1):
        cards = await page.query_selector_all('ul.search-result-list li a')
        for card in cards:
            name_elem = await card.query_selector('h4')
            if name_elem:
                name = (await name_elem.inner_text()).strip()
                if name:
                    names.append(name)

        if page_num < total_pages:
            first_before = await page.query_selector('ul.search-result-list li a h4')
            first_before_name = await first_before.inner_text() if first_before else ""
            next_link = await page.query_selector(
                f'ul.page-selector-list li a[data-itemnumber="{page_num + 1}"]'
            )
            if next_link:
                await next_link.click()
                for _ in range(10):
                    await page.wait_for_timeout(500)
                    first_after = await page.query_selector('ul.search-result-list li a h4')
                    first_after_name = await first_after.inner_text() if first_after else ""
                    if first_after_name != first_before_name:
                        break

    # Uncheck the facet to restore the unfiltered state for the next pass
    try:
        item = await page.query_selector(item_selector)
        checkbox = await item.query_selector(SELECTORS["facet_checkbox"]) if item else None
        target = checkbox or item
        if target:
            await target.click()
            await page.wait_for_timeout(1000)
    except Exception:
        pass

    print(f"  ✓ facet '{facet_value}': {len(names)} companies")
    return names
```

- [ ] **Step 9.2: Run smoke test**

Run: `pytest webview/tests/test_smoke.py -v`
Expected: passes.

- [ ] **Step 9.3: Commit**

```bash
git add webview/compare.py
git commit -m "feat(scrape): add _scrape_with_facet helper"
```

---

## Task 10: New scrape_website orchestrator

**Files:**
- Modify: `webview/compare.py`

- [ ] **Step 10.1: Replace scrape_website with the new orchestrator**

In `webview/compare.py`, replace the entire existing `scrape_website` function with:

```python
async def scrape_website(headless=True, browser_type='firefox', debug_mode=False, timeout=60000):
    """Scrape company data from PIF portfolio site, traversing facets to extract
    Portfolio and Ecosystem per company.

    Returns a DataFrame with columns: Company, Portfolio, Ecosystem.
    """
    print("=" * 80)
    print("STARTING WEBSITE SCRAPING (facet traversal)")
    print(f"Browser: {browser_type} | Headless: {headless} | Timeout: {timeout}ms")
    print("=" * 80)

    debug_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')

    try:
        async with async_playwright() as p:
            browser = context = page = None
            try:
                browser, context, page = await _open_portfolio_page(
                    p, headless, browser_type, timeout,
                )
            except Exception as e:
                if debug_mode and page is not None:
                    os.makedirs(debug_dir, exist_ok=True)
                    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                    await page.screenshot(path=os.path.join(debug_dir, f'error_screenshot_{ts}.png'))
                    with open(os.path.join(debug_dir, f'error_page_{ts}.html'), 'w', encoding='utf-8') as f:
                        f.write(await page.content())
                raise

            try:
                facets = await _discover_facets(page)

                # Pass 1: Portfolio facets — defines the company universe
                portfolio_map: dict[str, str] = {}
                for value in facets["portfolio"]:
                    print(f"Scraping portfolio facet: {value}")
                    names = await _scrape_with_facet(
                        page, SELECTORS["portfolio_facet_panel"], value,
                    )
                    for name in names:
                        portfolio_map[name] = value

                # Pass 2: Ecosystem facets — enriches the universe
                ecosystem_map: dict[str, str] = {}
                for value in facets["ecosystem"]:
                    print(f"Scraping ecosystem facet: {value}")
                    names = await _scrape_with_facet(
                        page, SELECTORS["ecosystem_facet_panel"], value,
                    )
                    for name in names:
                        ecosystem_map[name] = value

                # Merge into a single record per company
                all_names = set(portfolio_map.keys()) | set(ecosystem_map.keys())
                companies = []
                for name in sorted(all_names):
                    portfolio = portfolio_map.get(name)
                    ecosystem = ecosystem_map.get(name)
                    if portfolio is None:
                        print(f"  ⚠ data inconsistency: '{name}' tagged with ecosystem but no portfolio")
                    companies.append({
                        "Company": name,
                        "Portfolio": portfolio,
                        "Ecosystem": ecosystem,
                    })

                print(f"Scraped {len(companies)} companies "
                      f"({sum(1 for c in companies if c['Ecosystem'])} with ecosystem)")
                return pd.DataFrame(companies)

            finally:
                if context is not None:
                    await context.close()
                if browser is not None:
                    await browser.close()

    except Exception as e:
        print(f"Failed to scrape website: {e}")
        import traceback
        traceback.print_exc()
        return None
```

- [ ] **Step 10.2: Run smoke test**

Run: `pytest webview/tests/test_smoke.py -v`
Expected: passes.

- [ ] **Step 10.3: Commit**

```bash
git add webview/compare.py
git commit -m "feat(scrape): new facet-traversal scrape_website orchestrator"
```

---

## Task 11: Wire detect_template into the Flask app + delete old DB

**Files:**
- Modify: `webview/app.py`
- Delete: `webview/comparison_history.db`

- [ ] **Step 11.1: Add detect_template integration**

Edit `webview/app.py`. At the imports, add:

```python
from template_spec import detect_template
```

Replace the body of `process_file` (the section from `baseline_df = pd.read_excel(filepath)` through the `enhanced_compare_companies` call and the `summarizer.save_and_summarize` call) with:

```python
        baseline_df = pd.read_excel(filepath)
        print(f"Loaded {len(baseline_df)} companies from baseline file")

        try:
            template_spec = detect_template(baseline_df)
            print(f"Detected template: {template_spec.kind}")
        except ValueError as ve:
            processing_results[result_id] = {'status': 'error', 'message': str(ve)}
            print(f"ERROR: {ve}")
            return

        print("Starting website scraping...")
        try:
            website_df = await scrape_website(
                headless=headless,
                browser_type=browser_type,
                debug_mode=debug,
                timeout=timeout,
            )
            if website_df is None:
                processing_results[result_id] = {
                    'status': 'error',
                    'message': 'Failed to scrape website. Check server logs. Try Firefox or visible mode.',
                }
                print("ERROR: Website scraping returned None")
                return
        except Exception as e:
            error_msg = f'Failed to scrape website: {str(e)}'
            if 'ERR_NAME_NOT_RESOLVED' in str(e) or 'Cloudflare' in str(e) or '403' in str(e):
                error_msg += '\n\nSuggestions:\n- Try Firefox (better Cloudflare bypass)\n- Enable visible mode to solve CAPTCHA manually\n- Check internet connection'
            processing_results[result_id] = {'status': 'error', 'message': error_msg}
            print(f"ERROR: {error_msg}")
            import traceback
            traceback.print_exc()
            return

        print(f"Scraped {len(website_df)} companies from website")

        print("Starting enhanced comparison...")
        results_df, unmatched_df = enhanced_compare_companies(baseline_df, website_df, template_spec)

        print("Generating summary and historical analysis...")
        summary = summarizer.save_and_summarize(
            results_df,
            os.path.basename(filepath),
            len(website_df),
            template_spec,
        )
```

**Also update the Excel output block** further down `process_file` to include the `status_breakdown` rows in the Summary sheet (per the spec). Replace the existing `with pd.ExcelWriter(output_path, ...) as writer:` block with:

```python
        print("Saving results to Excel...")
        with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
            results_df.to_excel(writer, sheet_name='Comparison Results', index=False)
            unmatched_df.to_excel(writer, sheet_name='Unmatched Website Companies', index=False)

            current = summary['current_analysis']
            summary_rows = [
                {'Metric': k.replace('_', ' ').title(), 'Value': v}
                for k, v in current['totals'].items()
            ]
            summary_rows.extend(
                {'Metric': k.replace('_', ' ').title(), 'Value': v}
                for k, v in current['status_breakdown'].items()
            )
            pd.DataFrame(summary_rows).to_excel(writer, sheet_name='Summary', index=False)
```

`unmatched_df` already carries the new `Portfolio` / `Ecosystem` columns from Task 5.

- [ ] **Step 11.2: Delete the old SQLite history**

Run: `rm webview/comparison_history.db`
Expected: file removed. The new schema is created on first app boot.

- [ ] **Step 11.3: Sanity-check the app boots**

Run: `python3 -c "import sys; sys.path.insert(0, 'webview'); import app; print('routes:', sorted(r.rule for r in app.app.url_map.iter_rules()))"`
Expected: prints all 5 expected routes (`/`, `/upload`, `/status/<result_id>`, `/summary/<result_id>`, `/download/<result_id>`).

- [ ] **Step 11.4: Run the full test suite**

Run: `pytest webview/tests/ -v`
Expected: all tests pass.

- [ ] **Step 11.5: Commit**

```bash
git add webview/app.py
git rm webview/comparison_history.db
git commit -m "feat(app): wire detect_template, drop legacy SQLite history"
```

---

## Task 12: Dashboard JS — loop-driven status_breakdown rendering

**Files:**
- Modify: `webview/index.html`

- [ ] **Step 12.1: Replace the hardcoded issues block**

Open `webview/index.html`. Find the JavaScript section that begins:

```javascript
                // Show issues if any
                const totalIssues = statusBreakdown.missing_from_website +
```

Replace from there through the closing of the `if (totalIssues > 0)` block (ending at `issuesSummary.innerHTML = issuesHtml;`) with:

```javascript
                // Issues breakdown — render whichever keys the backend included
                const issueLabels = {
                    missing_from_website: 'companies missing from website',
                    extra_on_website: 'extra companies on website',
                    name_mismatches: 'companies need name updates',
                    portfolio_mismatches: 'companies need portfolio updates',
                    ecosystem_mismatches: 'companies need ecosystem updates',
                };
                const renderOrder = [
                    'missing_from_website',
                    'extra_on_website',
                    'name_mismatches',
                    'portfolio_mismatches',
                    'ecosystem_mismatches',
                ];
                const issueLines = renderOrder
                    .filter(key => (statusBreakdown[key] || 0) > 0)
                    .map(key => `<li><strong>${statusBreakdown[key]}</strong> ${issueLabels[key]}</li>`);

                if (issueLines.length > 0) {
                    issuesCard.style.display = 'block';
                    issuesSummary.innerHTML = `<ul>${issueLines.join('')}</ul>`;
                }
```

- [ ] **Step 12.2: Replace the hardcoded historical comparison block**

In the same file, find the block that begins:

```javascript
                // Show historical comparison if available
                const historical = summary.historical_comparison;
                if (historical.has_historical_data) {
```

Replace through the closing of that `if` block (ending at the closing `;` of the `historicalComparison.innerHTML = ...` template literal) with:

```javascript
                // Historical comparison — iterate whatever keys the payload includes
                const historical = summary.historical_comparison;
                if (historical.has_historical_data) {
                    historicalCard.style.display = 'block';
                    const trend = historical.overall_trend;
                    const trendClass = `trend-${trend}`;

                    const changeLines = Object.entries(historical.changes || {}).map(([key, info]) => {
                        const label = issueLabels[key] || key.replaceAll('_', ' ');
                        const sign = info.change >= 0 ? '+' : '';
                        return `<li>${label}: ${info.current} (${sign}${info.change})</li>`;
                    });

                    historicalComparison.innerHTML = `
                        <p>Compared to previous run: <span class="trend-indicator ${trendClass}">${trend.toUpperCase()}</span></p>
                        <div class="historical-details">
                            <p><strong>Changes since last run:</strong></p>
                            <ul>${changeLines.join('')}</ul>
                        </div>
                    `;
                }
```

- [ ] **Step 12.3: Manual smoke test of the dashboard**

Start the app: `python3 webview/app.py`
Open `http://127.0.0.1:5000` in a browser.
Verify the page loads without console errors. (Full upload→render flow happens in the next task.)
Stop the app with Ctrl-C.

- [ ] **Step 12.4: Commit**

```bash
git add webview/index.html
git commit -m "feat(ui): loop-driven status_breakdown rendering in dashboard"
```

---

## Task 13: End-to-end smoke test against live site

**Files:**
- (No code changes — exercises the full system)

- [ ] **Step 13.1: Start the Flask app**

Run in one terminal: `python3 webview/app.py`
Expected: `Running on http://127.0.0.1:5000`.

- [ ] **Step 13.2: Smoke test the new template**

In a browser at `http://127.0.0.1:5000`:
1. Upload `webview/uploads/new-template.xlsx`.
2. Wait for processing (1–3 minutes — facet scraping is slower than the legacy single-pass scrape).
3. Watch the Flask console; expected log lines include `Detected template: new`, `Discovered facets: ...`, `✓ facet '<name>': N companies` per facet, `Scraped N companies (M with ecosystem)`.
4. Verify the dashboard renders and includes Portfolio + Ecosystem mismatch counts.
5. Download the result Excel; open it and confirm Sheet 1 has `Portfolio Match` and `Ecosystem Match` columns, and Sheet 2 has `Portfolio` + `Ecosystem` columns.

If any of those checks fail, debug before continuing — do not proceed to legacy testing while the new template is broken.

- [ ] **Step 13.3: Smoke test the legacy template**

Upload `webview/uploads/baseline4.xlsx` (the legacy baseline).
Expected:
1. Flask console logs `Detected template: legacy`.
2. Dashboard shows OK / Add / Remove / name-mismatch counts only — no portfolio or ecosystem counts.
3. Result Excel Sheet 1 has the legacy column set (no Portfolio/Ecosystem columns).
4. Result Excel Sheet 2 still has `Portfolio` + `Ecosystem` columns (those come from the website scrape, regardless of template).

- [ ] **Step 13.4: Stop the app**

Ctrl-C in the Flask terminal.

- [ ] **Step 13.5: No commit needed unless smoke tests revealed bugs**

If smoke tests passed, no commit. If they revealed issues, fix them in a focused commit referencing what was wrong.

---

## Task 14: Documentation refresh

**Files:**
- Modify: `README.md`
- Modify: `SETUP.md`

- [ ] **Step 14.1: Update the root README**

Edit `README.md`. Add a new section after "How It Works" titled "Supported Baseline Templates" with:

```markdown
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
```

In the "How It Works" section, replace the bullet "Background scrape — Flask spawns a thread that runs `compare.scrape_website()`..." with:

```markdown
2. **Background scrape** — Flask spawns a thread that runs [`compare.scrape_website()`](webview/compare.py), which traverses the PIF site's facet filters (3 Portfolio facets + 6 Ecosystem facets) using Playwright + [`playwright-stealth`](https://github.com/AtuboDad/playwright_stealth). Each facet pass scrapes the filtered company list across pagination; results are merged into a single `(Company, Portfolio, Ecosystem)` table. Firefox is the default (best Cloudflare bypass).
```

- [ ] **Step 14.2: Update SETUP.md**

Edit `SETUP.md`. Replace the "Usage" section with:

```markdown
## Usage

1. Upload a baseline Excel file. Two templates are accepted:
   - Legacy: columns `CR Name`, `Brand Name`, `VRP Sector`.
   - New: columns `CR Name`, `Brand Name`, `Portfolio`, `Ecosystem` (extra columns are ignored).
2. Wait for processing (typically 1–3 minutes — the scraper traverses facet filters on the PIF site).
3. Review the dashboard. Issue counts shown depend on which template was detected.
4. Download the enhanced Excel report.
```

- [ ] **Step 14.3: Commit**

```bash
git add README.md SETUP.md
git commit -m "docs: document both templates and facet scraper"
```

---

## Final verification

- [ ] **Run the full suite one last time**

Run: `pytest webview/tests/ -v`
Expected: all tests pass.

- [ ] **Confirm no stray files**

Run: `git status`
Expected: clean working tree (everything committed).

- [ ] **Confirm SQLite is regenerated correctly on next boot**

Run: `python3 -c "import sys; sys.path.insert(0, 'webview'); from results_analyzer import HistoricalTracker; t = HistoricalTracker('webview/comparison_history.db'); import sqlite3; c = sqlite3.connect('webview/comparison_history.db'); print([r[1] for r in c.execute('PRAGMA table_info(company_history)').fetchall()])"`
Expected: prints column list including `portfolio`, `website_portfolio`, `ecosystem`, `website_ecosystem`.

Run: `rm webview/comparison_history.db`
(Delete the freshly created DB so the first real upload creates it cleanly.)
