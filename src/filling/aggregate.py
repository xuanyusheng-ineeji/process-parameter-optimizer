"""
Aggregate 1-second time-series PLC/checkweigher data into stable parameter windows.

Raw time-series data (1 row per second) cannot be fed directly into the static
regression models — parameters change infrequently while weights fluctuate every
second. This module detects parameter-stable windows and aggregates each window
into a single "batch" row compatible with data_loader.from_dataframe().

Typical flow:
    raw_ts = synthetic_data.generate_timeseries("285104", duration_seconds=3600)
    batches = aggregate.from_timeseries(raw_ts, item_cd="285104")
    df = data_loader.from_dataframe(batches, item_cd="285104")
    # → feed into predictor, analyzer, recommender as usual
"""

from __future__ import annotations

import logging
from typing import Dict, Optional

import pandas as pd

from .config import PARAM_NAMES

logger = logging.getLogger(__name__)

# Per-parameter tolerance for change detection.
# A difference smaller than this is treated as measurement noise, not a real change.
_DEFAULT_CHANGE_TOLERANCE: Dict[str, float] = {
    "fill_time_s":        0.005,   # 5 ms
    "fill_pressure_bar":  0.02,
    "product_temp_c":     0.2,
    "nozzle_opening_pct": 0.5,
    "line_speed_bpm":     0.5,
}


def from_timeseries(
    df: pd.DataFrame,
    item_cd: str,
    timestamp_col: str = "timestamp",
    weight_col: str = "fill_weight_g",
    lag_seconds: int = 2,
    min_stable_seconds: int = 30,
    change_tolerance: Optional[Dict[str, float]] = None,
) -> pd.DataFrame:
    """
    Convert 1-second time-series data into stable parameter windows (batch rows).

    Each window is a contiguous period where all parameters remain within
    ``change_tolerance``. The output is a batch-level DataFrame that can be
    passed directly to ``data_loader.from_dataframe()``.

    Args:
        df:                  Raw time-series DataFrame sorted (or sortable) by timestamp.
                             Required columns: timestamp, PARAM_NAMES, fill_weight_g, item_cd.
        item_cd:             Product item code.
        timestamp_col:       Name of the timestamp column.
        weight_col:          Name of the fill weight column.
        lag_seconds:         PLC-to-checkweigher delay. The weight measured at second t
                             was produced by the parameters set at second (t - lag_seconds).
                             Compensated by shifting the weight column forward in time.
        min_stable_seconds:  Windows shorter than this are discarded (parameters not
                             yet stable, or transient between two set points).
        change_tolerance:    Override per-parameter change thresholds.

    Returns:
        Batch-level DataFrame with columns:
            PARAM_NAMES (mean over window), fill_weight_g (mean), weight_std_g,
            weight_min_g, weight_max_g, n_seconds, window_start, window_end, item_cd
    """
    if lag_seconds < 0:
        raise ValueError(
            f"lag_seconds must be >= 0, got {lag_seconds}. "
            "A negative lag would shift weights into the past, which has no physical meaning."
        )

    df = df.copy().sort_values(timestamp_col).reset_index(drop=True)

    # ── Lag compensation ──────────────────────────────────────────────────────
    # Weight at row t reflects parameters set at row (t - lag).
    # Shifting weight by -lag aligns each row's weight with the parameters that
    # produced it.
    if lag_seconds > 0:
        df[weight_col] = df[weight_col].shift(-lag_seconds)
        df = df.dropna(subset=[weight_col]).reset_index(drop=True)

    # ── Parameter change detection ────────────────────────────────────────────
    tol = {**_DEFAULT_CHANGE_TOLERANCE, **(change_tolerance or {})}
    present_params = [p for p in PARAM_NAMES if p in df.columns]

    changed = pd.Series(False, index=df.index)
    for param in present_params:
        threshold = tol.get(param, 0.0)
        changed |= df[param].diff().abs().fillna(0) > threshold

    window_id = changed.cumsum()

    # ── Aggregation ───────────────────────────────────────────────────────────
    agg_spec: Dict[str, tuple] = {p: (p, "mean") for p in present_params}
    agg_spec["fill_weight_g"] = (weight_col, "mean")
    agg_spec["weight_std_g"]  = (weight_col, "std")
    agg_spec["weight_min_g"]  = (weight_col, "min")
    agg_spec["weight_max_g"]  = (weight_col, "max")
    agg_spec["n_seconds"]     = (weight_col, "count")
    if timestamp_col in df.columns:
        agg_spec["window_start"] = (timestamp_col, "first")
        agg_spec["window_end"]   = (timestamp_col, "last")

    batches = (
        df.groupby(window_id, sort=True)
        .agg(**agg_spec)
        .reset_index(drop=True)
    )
    batches["item_cd"] = item_cd

    # ── Filter short windows ──────────────────────────────────────────────────
    n_before = len(batches)
    batches = batches[batches["n_seconds"] >= min_stable_seconds].reset_index(drop=True)
    n_dropped = n_before - len(batches)
    if n_dropped:
        logger.info(
            "Dropped %d short windows (< %ds); %d windows kept.",
            n_dropped, min_stable_seconds, len(batches),
        )

    if len(batches) == 0:
        raise ValueError(
            f"No stable parameter windows found (all shorter than {min_stable_seconds}s). "
            "Try reducing min_stable_seconds, or verify that the data covers multiple "
            "distinct parameter settings."
        )

    logger.info(
        "Aggregated %d seconds → %d windows (mean duration %.0fs, "
        "weight mean %.2fg ± %.2fg).",
        len(df),
        len(batches),
        batches["n_seconds"].mean(),
        batches["fill_weight_g"].mean(),
        batches["fill_weight_g"].std(),
    )

    return batches


def summary(batches: pd.DataFrame) -> None:
    """Print a brief summary of the aggregated windows."""
    print(f"Windows       : {len(batches)}")
    print(f"Total seconds : {batches['n_seconds'].sum():.0f}")
    print(f"Window dur    : {batches['n_seconds'].min():.0f}s – {batches['n_seconds'].max():.0f}s "
          f"(mean {batches['n_seconds'].mean():.0f}s)")
    print(f"Weight mean   : {batches['fill_weight_g'].mean():.2f}g "
          f"(σ={batches['fill_weight_g'].std():.2f}g)")
    if "weight_std_g" in batches.columns:
        print(f"Within-window σ (mean): {batches['weight_std_g'].mean():.2f}g")
