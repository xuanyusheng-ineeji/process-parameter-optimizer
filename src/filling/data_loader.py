"""Load and validate historical production data for filling process."""

import logging
import pandas as pd
import numpy as np
from pathlib import Path
from typing import Optional
from .config import PRODUCTS, PARAM_NAMES, ProductConfig

logger = logging.getLogger(__name__)


REQUIRED_COLUMNS = PARAM_NAMES + ["fill_weight_g", "item_cd"]


def from_csv(path: str, item_cd: Optional[str] = None) -> pd.DataFrame:
    """Load production history from a CSV file."""
    df = pd.read_csv(path)
    return _process(df, item_cd)


def from_excel(path: str, sheet: str = "Sheet1", item_cd: Optional[str] = None) -> pd.DataFrame:
    """Load production history from an Excel file."""
    df = pd.read_excel(path, sheet_name=sheet)
    return _process(df, item_cd)


def from_dataframe(df: pd.DataFrame, item_cd: Optional[str] = None) -> pd.DataFrame:
    """Accept a DataFrame directly (e.g. from synthetic_data.generate())."""
    return _process(df.copy(), item_cd)


def _process(df: pd.DataFrame, item_cd: Optional[str]) -> pd.DataFrame:
    df.columns = df.columns.str.strip().str.lower()

    if item_cd is not None:
        if "item_cd" in df.columns:
            df = df[df["item_cd"] == item_cd].copy()
        else:
            df["item_cd"] = item_cd

    _check_columns(df)
    df = _clean(df)
    return df


def _check_columns(df: pd.DataFrame) -> None:
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(
            f"Missing columns: {missing}\n"
            f"Required: {REQUIRED_COLUMNS}\n"
            f"Found: {list(df.columns)}"
        )


def _clean(df: pd.DataFrame) -> pd.DataFrame:
    before = len(df)

    # Drop rows missing key values
    df = df.dropna(subset=REQUIRED_COLUMNS)

    # Remove obvious sensor errors (weight <= 0)
    df = df[df["fill_weight_g"] > 0]

    # Clip parameters to physically plausible ranges
    df["fill_time_s"]        = df["fill_time_s"].clip(0.5, 20.0)
    df["fill_pressure_bar"]  = df["fill_pressure_bar"].clip(0.5, 6.0)
    df["product_temp_c"]     = df["product_temp_c"].clip(0.0, 50.0)
    df["nozzle_opening_pct"] = df["nozzle_opening_pct"].clip(10.0, 100.0)
    df["line_speed_bpm"]     = df["line_speed_bpm"].clip(1.0, 120.0)

    dropped = before - len(df)
    if dropped > 0:
        logger.info("Dropped %d invalid rows (%d → %d)", dropped, before, len(df))

    if len(df) == 0:
        raise ValueError(
            f"All {before} rows were removed during cleaning. "
            "Check that the input data contains valid parameter values and positive fill weights."
        )

    df = df.reset_index(drop=True)
    return df


def summary(df: pd.DataFrame, product: Optional[ProductConfig] = None) -> None:
    """Print a quick summary of the loaded dataset."""
    print(f"Rows: {len(df)}")
    print(f"Products: {df['item_cd'].unique().tolist()}")
    print(f"\nParameter statistics:")
    print(df[PARAM_NAMES + ['fill_weight_g']].describe().round(3).to_string())

    if product is not None:
        low  = (df["fill_weight_g"] < product.lcl_g).sum()
        ok   = ((df["fill_weight_g"] >= product.lcl_g) &
                (df["fill_weight_g"] <= (product.ucl_g or float("inf")))).sum()
        high = (product.ucl_g is not None and
                df["fill_weight_g"] > product.ucl_g).sum() if product.ucl_g else 0
        total = len(df)
        print(f"\nWeight distribution vs spec:")
        print(f"  LOW  (< {product.lcl_g}g): {low:4d} ({100*low/total:.1f}%)")
        print(f"  OK              : {ok:4d} ({100*ok/total:.1f}%)")
        print(f"  HIGH (> {product.ucl_g}g): {high:4d} ({100*high/total:.1f}%)")
