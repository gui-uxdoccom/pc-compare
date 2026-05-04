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
