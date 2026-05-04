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
