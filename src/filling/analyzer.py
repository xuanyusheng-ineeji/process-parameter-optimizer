"""Root cause analysis: which parameters drive fill weight deviation."""

import numpy as np
import pandas as pd
from typing import Dict, List, Tuple
from .config import PARAM_NAMES, ProductConfig, get_param_bounds
from .predictor import FillWeightPredictor


class RootCauseAnalyzer:
    """
    Identifies which equipment parameters most influence fill weight,
    and in which direction (increase/decrease weight).
    """

    def __init__(self, predictor: FillWeightPredictor, product: ProductConfig) -> None:
        self._predictor = predictor
        self._product = product

    def analyze(self, df: pd.DataFrame) -> Dict:
        """
        Full root cause analysis on a historical dataset.

        Returns a dict with:
          - importance: ranked parameter importance (0-100%)
          - direction: effect direction per parameter (+/-)
          - deviation_summary: how far current weight is from target
          - top_cause: the single most influential parameter
        """
        importance = self._feature_importance()
        direction = self._effect_direction(df)
        deviation = self._deviation_summary(df)

        # Rank by importance descending
        ranked = sorted(importance.items(), key=lambda x: x[1], reverse=True)

        return {
            "importance": ranked,
            "direction": direction,
            "deviation_summary": deviation,
            "top_cause": ranked[0][0] if ranked else None,
        }

    def _feature_importance(self) -> Dict[str, float]:
        raw = self._predictor.feature_importances()
        total = sum(raw.values()) or 1.0
        return {k: round(v / total * 100, 1) for k, v in raw.items()}

    def _effect_direction(self, df: pd.DataFrame) -> Dict[str, str]:
        """
        For each parameter, determine whether increasing it raises or lowers fill weight.
        Uses sensitivity analysis: perturb each parameter by +5%, clipped to valid bounds.
        If +5% hits the upper bound, falls back to -5% perturbation (direction is inverted).
        """
        baseline_params = {n: df[n].mean() for n in PARAM_NAMES}
        baseline_weight = self._predictor.predict(baseline_params)
        bounds = get_param_bounds(self._product)

        directions = {}
        for name in PARAM_NAMES:
            lo, hi = bounds[name]
            base_val = baseline_params[name]
            perturbed = baseline_params.copy()

            up_val = min(base_val * 1.05, hi)
            if abs(up_val - base_val) > 1e-9:
                perturbed[name] = up_val
                sign = 1
            else:
                # Upper bound hit — use downward perturbation and invert sign
                perturbed[name] = max(base_val * 0.95, lo)
                sign = -1

            delta = (self._predictor.predict(perturbed) - baseline_weight) * sign
            directions[name] = "↑ increases weight" if delta > 0 else "↓ decreases weight"

        return directions

    def _deviation_summary(self, df: pd.DataFrame) -> Dict:
        target = self._product.target_g
        lcl = self._product.lcl_g
        ucl = self._product.ucl_g

        weights = df["fill_weight_g"]
        mean_w = weights.mean()
        std_w = weights.std()

        low_pct  = (weights < lcl).mean() * 100
        high_pct = (weights > ucl).mean() * 100 if ucl is not None else 0.0
        ok_pct   = 100 - low_pct - high_pct

        return {
            "mean_weight_g": round(mean_w, 2),
            "std_g": round(std_w, 2),
            "bias_g": round(mean_w - target, 2),  # positive = overfilling
            "ok_pct": round(ok_pct, 1),
            "low_pct": round(low_pct, 1),
            "high_pct": round(high_pct, 1),
        }

    def print_report(self, df: pd.DataFrame) -> None:
        result = self.analyze(df)
        p = self._product

        print("=" * 55)
        print(f"ROOT CAUSE ANALYSIS — {p.item_nm}")
        print(f"Target: {p.target_g}g  LCL: {p.lcl_g}g  UCL: {p.ucl_g}g")
        print("=" * 55)

        dev = result["deviation_summary"]
        print(f"\n[Weight Status]")
        print(f"  Mean:  {dev['mean_weight_g']}g  (bias: {dev['bias_g']:+.2f}g vs target)")
        print(f"  Std:   {dev['std_g']}g")
        print(f"  OK:    {dev['ok_pct']}%")
        print(f"  LOW:   {dev['low_pct']}%  ← must be 0% (legal)")
        print(f"  HIGH:  {dev['high_pct']}%  ← product waste")

        print(f"\n[Parameter Influence on Fill Weight]")
        for param, imp in result["importance"]:
            direction = result["direction"][param]
            bar = "█" * int(imp / 5)
            print(f"  {param:<25} {imp:5.1f}%  {bar}  {direction}")

        print(f"\n[Top Cause]  {result['top_cause']}")
        print("=" * 55)
