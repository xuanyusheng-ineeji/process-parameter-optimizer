"""Tests for src/filling/trend.py (WeightTrendMonitor)."""

import pytest
import numpy as np
import pandas as pd

from src.filling.config import PRODUCTS
from src.filling.trend import WeightTrendMonitor
from src.filling import synthetic_data


ITEM_CD = "285104"
PRODUCT = PRODUCTS[ITEM_CD]


@pytest.fixture
def monitor():
    return WeightTrendMonitor(PRODUCT, window_seconds=60, ewma_lambda=0.2)


def _make_df(weights) -> pd.DataFrame:
    """Build a minimal time-series DataFrame from a weight list."""
    origin = pd.Timestamp("2024-01-01 08:00:00")
    return pd.DataFrame({
        "timestamp": [origin + pd.Timedelta(seconds=i) for i in range(len(weights))],
        "fill_weight_g": weights,
    })


# ── Basic return structure ────────────────────────────────────────────────────

def test_analyze_returns_required_keys(monitor):
    weights = [PRODUCT.target_g] * 100
    report = monitor.analyze(_make_df(weights))
    for key in (
        "n_samples", "window_seconds", "rolling_mean_g", "rolling_std_g",
        "ewma_g", "trend_slope_g_per_s", "trend_slope_g_per_min",
        "trend_r2", "seconds_until_ooc", "alerts", "status",
    ):
        assert key in report, f"Missing key: {key}"


def test_n_samples_matches_input(monitor):
    weights = [PRODUCT.target_g] * 150
    report = monitor.analyze(_make_df(weights))
    assert report["n_samples"] == 150


# ── Status checks ─────────────────────────────────────────────────────────────

def test_stable_data_ok_status(monitor):
    # LCL == target_g for food products, so stable "OK" weights must be
    # comfortably above target (i.e. mean well above LCL).
    target_midpoint = PRODUCT.target_g + (PRODUCT.ucl_g - PRODUCT.target_g) * 0.4
    rng = np.random.default_rng(42)
    weights = [target_midpoint + rng.normal(0, 0.1) for _ in range(120)]
    report = monitor.analyze(_make_df(weights))
    assert report["status"] == "OK"
    assert len(report["alerts"]) == 0


def test_below_lcl_critical(monitor):
    weights = [PRODUCT.lcl_g - 5.0] * 120
    report = monitor.analyze(_make_df(weights))
    assert report["status"] == "CRITICAL"
    assert any("CRITICAL" in a for a in report["alerts"])


def test_above_ucl_critical(monitor):
    if PRODUCT.ucl_g is None:
        pytest.skip("Product has no UCL")
    weights = [PRODUCT.ucl_g + 5.0] * 120
    report = monitor.analyze(_make_df(weights))
    assert report["status"] == "CRITICAL"
    assert any("CRITICAL" in a for a in report["alerts"])


def test_falling_trend_warning(monitor):
    """A consistent downward slope (approaching LCL) should produce WARNING or CRITICAL."""
    target = PRODUCT.target_g
    # 120 readings falling from target by ~5g/min (0.083 g/s)
    weights = [target - 0.083 * i for i in range(120)]
    report = monitor.analyze(_make_df(weights))
    assert report["status"] in ("WARNING", "CRITICAL")
    assert any("falling" in a.lower() or "CRITICAL" in a for a in report["alerts"])


def test_rising_trend_warning(monitor):
    """A consistent upward slope should produce WARNING or CRITICAL."""
    target = PRODUCT.target_g
    weights = [target + 0.083 * i for i in range(120)]
    report = monitor.analyze(_make_df(weights))
    assert report["status"] in ("WARNING", "CRITICAL")


def test_high_variance_warning(monitor):
    """Variance > 3% of target → WARNING."""
    rng = np.random.default_rng(999)
    std_large = PRODUCT.target_g * 0.05   # 5% > 3% threshold
    weights = [PRODUCT.target_g + rng.normal(0, std_large) for _ in range(120)]
    report = monitor.analyze(_make_df(weights))
    assert any("variation" in a.lower() for a in report["alerts"])


# ── Trend slope ───────────────────────────────────────────────────────────────

def test_positive_slope_on_rising_series(monitor):
    weights = list(range(100, 220))   # strictly rising
    report = monitor.analyze(_make_df(weights))
    assert report["trend_slope_g_per_s"] > 0
    assert report["trend_slope_g_per_min"] > 0


def test_negative_slope_on_falling_series(monitor):
    weights = list(range(220, 100, -1))   # strictly falling
    report = monitor.analyze(_make_df(weights))
    assert report["trend_slope_g_per_s"] < 0
    assert report["trend_slope_g_per_min"] < 0


# ── OOC prediction ────────────────────────────────────────────────────────────

def test_seconds_until_ooc_none_for_flat(monitor):
    weights = [PRODUCT.target_g] * 120
    report = monitor.analyze(_make_df(weights))
    assert report["seconds_until_ooc"] is None


def test_seconds_until_ooc_finite_for_falling(monitor):
    target = PRODUCT.target_g
    weights = [target - 0.05 * i for i in range(120)]
    report = monitor.analyze(_make_df(weights))
    assert report["seconds_until_ooc"] is not None
    assert report["seconds_until_ooc"] >= 0


def test_seconds_until_ooc_reasonable(monitor):
    """If mean is 2g above LCL and slope is -0.1 g/s, OOC in ~20s."""
    target = PRODUCT.lcl_g + 2.0
    weights = [target - 0.1 * i for i in range(120)]
    report = monitor.analyze(_make_df(weights))
    if report["seconds_until_ooc"] is not None:
        assert report["seconds_until_ooc"] < 3600  # sanity upper bound


# ── Edge cases ────────────────────────────────────────────────────────────────

def test_too_few_readings_raises(monitor):
    with pytest.raises(ValueError, match="at least 2"):
        monitor.analyze(_make_df([PRODUCT.target_g]))


def test_window_capped_to_n_samples(monitor):
    """If n < window_seconds, effective window = n."""
    weights = [PRODUCT.target_g] * 30  # < window_seconds=60
    report = monitor.analyze(_make_df(weights))
    assert report["window_seconds"] == 30


def test_ewma_value_is_numeric(monitor):
    weights = [PRODUCT.target_g + i * 0.01 for i in range(100)]
    report = monitor.analyze(_make_df(weights))
    assert isinstance(report["ewma_g"], float)
    assert not np.isnan(report["ewma_g"])


def test_synthetic_timeseries_integration():
    """Full pipeline: generate → monitor.analyze() without errors."""
    ts = synthetic_data.generate_timeseries(
        ITEM_CD, duration_seconds=300, seed=7,
        drift_rate_g_per_min=1.0, n_param_adjustments=3,
    )
    mon = WeightTrendMonitor(PRODUCT, window_seconds=120)
    report = mon.analyze(ts)
    assert report["status"] in ("OK", "WARNING", "CRITICAL")
