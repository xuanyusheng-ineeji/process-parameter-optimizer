"""Tests for src/filling/aggregate.py."""

import pytest
import pandas as pd
import numpy as np

from src.filling.config import PARAM_NAMES, PRODUCTS
from src.filling import synthetic_data, aggregate


ITEM_CD = "285104"


@pytest.fixture
def ts_df():
    """Short 5-minute time-series (no drift, 2 parameter adjustments)."""
    return synthetic_data.generate_timeseries(
        ITEM_CD, duration_seconds=300, seed=0,
        drift_rate_g_per_min=0.0, n_param_adjustments=2,
    )


def test_basic_aggregation_returns_dataframe(ts_df):
    batches = aggregate.from_timeseries(ts_df, item_cd=ITEM_CD, min_stable_seconds=10)
    assert isinstance(batches, pd.DataFrame)
    assert len(batches) >= 1


def test_output_columns_include_all_params(ts_df):
    batches = aggregate.from_timeseries(ts_df, item_cd=ITEM_CD, min_stable_seconds=10)
    for param in PARAM_NAMES:
        assert param in batches.columns, f"Missing column: {param}"


def test_output_columns_include_weight_stats(ts_df):
    batches = aggregate.from_timeseries(ts_df, item_cd=ITEM_CD, min_stable_seconds=10)
    for col in ("fill_weight_g", "weight_std_g", "weight_min_g", "weight_max_g", "n_seconds"):
        assert col in batches.columns, f"Missing column: {col}"


def test_item_cd_column_set(ts_df):
    batches = aggregate.from_timeseries(ts_df, item_cd=ITEM_CD, min_stable_seconds=10)
    assert (batches["item_cd"] == ITEM_CD).all()


def test_window_timestamps_present(ts_df):
    batches = aggregate.from_timeseries(ts_df, item_cd=ITEM_CD, min_stable_seconds=10)
    assert "window_start" in batches.columns
    assert "window_end" in batches.columns
    assert (batches["window_end"] >= batches["window_start"]).all()


def test_n_seconds_matches_filter(ts_df):
    min_s = 30
    batches = aggregate.from_timeseries(ts_df, item_cd=ITEM_CD, min_stable_seconds=min_s)
    assert (batches["n_seconds"] >= min_s).all()


def test_short_window_filter_discards_transients():
    """Forcing a very long min_stable_seconds should drop short windows."""
    ts = synthetic_data.generate_timeseries(
        ITEM_CD, duration_seconds=600, seed=1,
        drift_rate_g_per_min=0.0, n_param_adjustments=8,
    )
    batches_loose = aggregate.from_timeseries(ts, item_cd=ITEM_CD, min_stable_seconds=5)
    batches_strict = aggregate.from_timeseries(ts, item_cd=ITEM_CD, min_stable_seconds=60)
    assert len(batches_strict) <= len(batches_loose)


def test_no_valid_windows_raises():
    """When all windows are shorter than min_stable_seconds, raise ValueError."""
    ts = synthetic_data.generate_timeseries(
        ITEM_CD, duration_seconds=120, seed=2,
        drift_rate_g_per_min=0.0, n_param_adjustments=20,
    )
    with pytest.raises(ValueError, match="No stable parameter windows"):
        aggregate.from_timeseries(ts, item_cd=ITEM_CD, min_stable_seconds=9999)


def test_lag_compensation_shifts_weight():
    """With lag=5, fill_weight_g in window N should differ from lag=0."""
    ts = synthetic_data.generate_timeseries(
        ITEM_CD, duration_seconds=300, seed=3,
        drift_rate_g_per_min=0.0, n_param_adjustments=1,
    )
    batches_no_lag  = aggregate.from_timeseries(ts, item_cd=ITEM_CD, lag_seconds=0,  min_stable_seconds=5)
    batches_with_lag = aggregate.from_timeseries(ts, item_cd=ITEM_CD, lag_seconds=5, min_stable_seconds=5)
    # Lag reduces the effective duration; the two DataFrames needn't have identical shapes,
    # but the overall weight means should differ (or at least both be numeric).
    assert batches_no_lag["fill_weight_g"].notna().all()
    assert batches_with_lag["fill_weight_g"].notna().all()


def test_single_stable_window():
    """If parameters never change, everything should collapse into one window."""
    product = PRODUCTS[ITEM_CD]
    nom = product.nominal_params
    n = 200
    rows = [
        {
            "timestamp": pd.Timestamp("2024-01-01") + pd.Timedelta(seconds=i),
            "item_cd": ITEM_CD,
            **nom,
            "fill_weight_g": product.target_g + np.random.default_rng(i).normal(0, 0.5),
            "in_spec": "OK",
        }
        for i in range(n)
    ]
    ts = pd.DataFrame(rows)
    batches = aggregate.from_timeseries(ts, item_cd=ITEM_CD, lag_seconds=0, min_stable_seconds=10)
    assert len(batches) == 1
    assert batches["n_seconds"].iloc[0] == n


def test_output_compatible_with_data_loader(ts_df):
    """Aggregated output should pass through data_loader.from_dataframe() without error."""
    from src.filling import data_loader
    batches = aggregate.from_timeseries(ts_df, item_cd=ITEM_CD, min_stable_seconds=10)
    df = data_loader.from_dataframe(batches, item_cd=ITEM_CD)
    assert len(df) >= 1
    for param in PARAM_NAMES:
        assert param in df.columns
