"""Synthetic data generator for filling process development and testing.

Two modes:
  generate()            → batch-level (one row per parameter setting)
  generate_timeseries() → 1-second time-series (one row per second)
"""

import numpy as np
import pandas as pd
from typing import Optional
from .config import ProductConfig, PRODUCTS, PARAM_NAMES, get_param_bounds


# ── Batch-level generation ────────────────────────────────────────────────────

def generate(
    item_cd: str,
    n_batches: int = 200,
    seed: Optional[int] = 42,
) -> pd.DataFrame:
    """
    Generate synthetic historical production data (one row = one batch).

    Args:
        item_cd:   Product code from PRODUCTS dict
        n_batches: Number of historical batches to generate
        seed:      Random seed for reproducibility

    Returns:
        DataFrame with columns: batch_id, item_cd, [PARAM_NAMES], fill_weight_g, in_spec
    """
    rng = np.random.default_rng(seed)
    product = PRODUCTS[item_cd]
    bounds = get_param_bounds(product)
    nominal = product.nominal_params

    rows = []
    for i in range(n_batches):
        params = {}
        for name in PARAM_NAMES:
            lo, hi = bounds[name]
            nom = nominal[name]
            std = (hi - lo) * (0.05 if rng.random() < 0.8 else 0.15)
            params[name] = float(np.clip(rng.normal(nom, std), lo, hi))

        fill_weight = _compute_weight(params, product, rng)
        rows.append({
            "batch_id": f"B{i+1:04d}",
            "item_cd": item_cd,
            **params,
            "fill_weight_g": round(fill_weight, 1),
            "in_spec": _in_spec(fill_weight, product),
        })

    return pd.DataFrame(rows)


def generate_all(n_batches: int = 200, seed: int = 42) -> pd.DataFrame:
    """Generate batch-level data for all 16 products combined."""
    frames = []
    for i, item_cd in enumerate(PRODUCTS):
        df = generate(item_cd, n_batches=n_batches, seed=seed + i)
        frames.append(df)
    return pd.concat(frames, ignore_index=True)


# ── Time-series generation ────────────────────────────────────────────────────

def generate_timeseries(
    item_cd: str,
    duration_seconds: int = 3600,
    seed: int = 42,
    drift_rate_g_per_min: float = 0.5,
    n_param_adjustments: int = 6,
) -> pd.DataFrame:
    """
    Generate 1-second time-series data simulating a production run.

    Simulates:
    - Parameters stable for random periods (engineer adjusts occasionally)
    - Pack-to-pack weight noise
    - Optional gradual weight drift (viscosity / temperature change over time)

    Args:
        item_cd:              Product code
        duration_seconds:     Total simulated run time in seconds
        seed:                 Random seed
        drift_rate_g_per_min: Gradual weight drift rate (g/min).
                              Positive = weight creeping up, negative = falling.
                              Simulates viscosity thinning / thickening over a shift.
        n_param_adjustments:  How many times the engineer adjusts parameters.

    Returns:
        DataFrame with columns:
            timestamp, item_cd, [PARAM_NAMES], fill_weight_g, in_spec
    """
    rng = np.random.default_rng(seed)
    product = PRODUCTS[item_cd]
    bounds = get_param_bounds(product)
    nominal = product.nominal_params.copy()

    # ── Build parameter adjustment schedule ───────────────────────────────────
    # Distribute adjustment times evenly across the run with some jitter
    min_gap = max(60, duration_seconds // (n_param_adjustments + 1))
    change_times = [0]
    for k in range(n_param_adjustments):
        t = change_times[-1] + int(rng.integers(min_gap, min_gap * 2))
        if t >= duration_seconds - 60:
            break
        change_times.append(t)

    # For each period, define parameter settings
    period_params = []
    current = dict(nominal)
    for idx, _ in enumerate(change_times):
        period_params.append(current.copy())
        if idx < len(change_times) - 1:
            # Adjust 1–2 parameters by a small amount
            n_change = rng.integers(1, 3)
            for param in rng.choice(PARAM_NAMES, size=int(n_change), replace=False):
                lo, hi = bounds[param]
                delta = (hi - lo) * float(rng.uniform(0.03, 0.10))
                direction = float(rng.choice([-1, 1]))
                current[param] = float(np.clip(current[param] + direction * delta, lo, hi))

    # ── Generate 1-second rows ────────────────────────────────────────────────
    drift_g_per_s = drift_rate_g_per_min / 60.0
    noise_pct = 0.005 if product.target_g <= 500 else 0.003
    origin = pd.Timestamp("2024-01-01 08:00:00")

    rows = []
    for t in range(duration_seconds):
        # Find which parameter period applies
        period_idx = sum(1 for ct in change_times if ct <= t) - 1
        params = period_params[period_idx]

        weight_ratio = _weight_ratio(params, product)
        base_weight  = product.target_g * weight_ratio
        drift        = drift_g_per_s * t
        noise        = float(rng.normal(0, product.target_g * noise_pct))
        fill_weight  = base_weight + drift + noise

        rows.append({
            "timestamp":    origin + pd.Timedelta(seconds=t),
            "item_cd":      item_cd,
            **{p: params[p] for p in PARAM_NAMES},
            "fill_weight_g": round(fill_weight, 2),
            "in_spec":       _in_spec(fill_weight, product),
        })

    return pd.DataFrame(rows)


# ── Internal helpers ──────────────────────────────────────────────────────────

def _weight_ratio(params: dict, product: ProductConfig) -> float:
    """
    Compute the deterministic weight ratio (no noise) from the physics model.
    weight = target_g × weight_ratio  (before adding noise or drift).
    """
    nom = product.nominal_params
    time_ratio     = params["fill_time_s"]        / nom["fill_time_s"]
    pressure_ratio = params["fill_pressure_bar"]  / nom["fill_pressure_bar"]
    nozzle_ratio   = params["nozzle_opening_pct"] / nom["nozzle_opening_pct"]
    speed_ratio    = nom["line_speed_bpm"]        / params["line_speed_bpm"]
    temp_factor    = 1.0 + 0.003 * (params["product_temp_c"] - nom["product_temp_c"])
    return (
        time_ratio     ** 0.85 *
        pressure_ratio ** 0.30 *
        nozzle_ratio   ** 0.20 *
        speed_ratio    ** 0.10 *
        temp_factor
    )


def _compute_weight(params: dict, product: ProductConfig, rng: np.random.Generator) -> float:
    """Physics-inspired weight with measurement noise (batch-level use)."""
    target    = product.target_g
    noise_pct = 0.003 if target <= 500 else 0.0015
    noise     = rng.normal(0, target * noise_pct)
    return target * _weight_ratio(params, product) + noise


def _in_spec(weight: float, product: ProductConfig) -> str:
    if weight < product.lcl_g:
        return "LOW"
    if product.ucl_g is not None and weight > product.ucl_g:
        return "HIGH"
    return "OK"
