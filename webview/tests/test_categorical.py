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
