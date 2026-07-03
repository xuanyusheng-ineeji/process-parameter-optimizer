"""Synthetic historical data generator for filling process development and testing."""

import numpy as np
import pandas as pd
from typing import Optional
from .config import ProductConfig, PRODUCTS, PARAM_NAMES, get_param_bounds, get_size_class


def generate(
    item_cd: str,
    n_batches: int = 200,
    seed: Optional[int] = 42,
) -> pd.DataFrame:
    """
    Generate synthetic historical production data for one product.

    Each row = one batch. Columns = parameter settings + actual fill weight.
    Simulates realistic parameter drift and weight variation over time.

    Args:
        item_cd: Product code from PRODUCTS dict
        n_batches: Number of historical batches to generate
        seed: Random seed for reproducibility

    Returns:
        DataFrame with columns: batch_id, [params...], fill_weight_g, in_spec
    """
    rng = np.random.default_rng(seed)
    product = PRODUCTS[item_cd]
    bounds = get_param_bounds(product)
    nominal = product.nominal_params

    rows = []
    for i in range(n_batches):
        # Simulate operator setting parameters near nominal with some variation
        # Occasional deliberate changes (operator adjustments) + random drift
        params = {}
        for name in PARAM_NAMES:
            lo, hi = bounds[name]
            nom = nominal[name]
            # 80% of batches: near nominal; 20%: wider exploration
            if rng.random() < 0.8:
                std = (hi - lo) * 0.05
            else:
                std = (hi - lo) * 0.15
            val = float(np.clip(rng.normal(nom, std), lo, hi))
            params[name] = val

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
    """Generate data for all 16 products combined."""
    frames = []
    for i, item_cd in enumerate(PRODUCTS):
        df = generate(item_cd, n_batches=n_batches, seed=seed + i)
        frames.append(df)
    return pd.concat(frames, ignore_index=True)


def _compute_weight(params: dict, product: ProductConfig, rng: np.random.Generator) -> float:
    """
    Physics-inspired weight model for paste/cream filling.

    Weight ≈ flow_rate × fill_time
    flow_rate depends on: pressure, nozzle opening, viscosity(temp)
    """
    nominal = product.nominal_params
    target = product.target_g

    # Each parameter's relative contribution to fill weight
    time_ratio     = params["fill_time_s"]        / nominal["fill_time_s"]
    pressure_ratio = params["fill_pressure_bar"]  / nominal["fill_pressure_bar"]
    nozzle_ratio   = params["nozzle_opening_pct"] / nominal["nozzle_opening_pct"]

    # Temperature effect: higher temp → lower viscosity → higher flow → more weight
    temp_delta = params["product_temp_c"] - nominal["product_temp_c"]
    temp_factor = 1.0 + 0.003 * temp_delta

    # line_speed effect: faster line → less effective fill time
    speed_ratio = nominal["line_speed_bpm"] / params["line_speed_bpm"]

    weight_ratio = (
        time_ratio     ** 0.85 *
        pressure_ratio ** 0.30 *
        nozzle_ratio   ** 0.20 *
        speed_ratio    ** 0.10 *
        temp_factor
    )

    # Measurement noise: ±0.3% of target for small packs, ±0.15% for large
    noise_pct = 0.003 if product.target_g <= 500 else 0.0015
    noise = rng.normal(0, target * noise_pct)

    return target * weight_ratio + noise


def _in_spec(weight: float, product: ProductConfig) -> str:
    if weight < product.lcl_g:
        return "LOW"
    if product.ucl_g is not None and weight > product.ucl_g:
        return "HIGH"
    return "OK"
