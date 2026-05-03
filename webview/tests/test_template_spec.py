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
