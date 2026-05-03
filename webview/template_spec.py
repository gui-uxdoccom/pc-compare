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
