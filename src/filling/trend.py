"""
Real-time fill weight trend monitoring using rolling statistics and EWMA.

Complements the static predictor/recommender with time-aware analysis:
  - Rolling mean / std over a configurable window
  - EWMA (Exponentially Weighted Moving Average) for smooth tracking
  - Trend slope (g/min) via linear regression
  - Out-of-control prediction: "how many seconds until weight hits LCL/UCL?"
  - SPC-style alerts for operators

Designed for 1-second time-series data from the checkweigher.
"""

from __future__ import annotations

from typing import Dict, List, Optional

import numpy as np
import pandas as pd
from scipy.stats import linregress

from .config import ProductConfig


class WeightTrendMonitor:
    """
    Monitors fill weight trends in real-time using rolling statistics and EWMA.

    Args:
        product:        ProductConfig for the current product.
        window_seconds: Number of recent seconds to use for rolling statistics.
        ewma_lambda:    Smoothing factor for EWMA (0 < λ ≤ 1).
                        Higher = more weight on recent observations.
    """

    def __init__(
        self,
        product: ProductConfig,
        window_seconds: int = 60,
        ewma_lambda: float = 0.2,
    ) -> None:
        self.product = product
        self.window = window_seconds
        self.ewma_lambda = ewma_lambda

    # ──────────────────────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────────────────────

    def analyze(
        self,
        df: pd.DataFrame,
        weight_col: str = "fill_weight_g",
    ) -> Dict:
        """
        Compute trend statistics from a time-series weight DataFrame.

        The DataFrame should be sorted chronologically (oldest first).
        Only the ``weight_col`` column is required; a ``timestamp`` column
        is used for display if present.

        Returns:
            Dict with keys:
                n_samples           int
                window_seconds      int  (effective window used)
                rolling_mean_g      float
                rolling_std_g       float
                ewma_g              float
                trend_slope_g_per_s float
                trend_slope_g_per_min float
                trend_r2            float
                seconds_until_ooc   float | None  (None if trend is flat or moving away from limits)
                alerts              List[str]
                status              "OK" | "WARNING" | "CRITICAL"
        """
        weights = df[weight_col].dropna().values
        n = len(weights)
        if n < 2:
            raise ValueError(
                f"Need at least 2 weight readings for trend analysis, got {n}."
            )

        win = min(self.window, n)
        recent = weights[-win:]

        rolling_mean = float(recent.mean())
        rolling_std  = float(recent.std(ddof=1)) if len(recent) > 1 else 0.0

        ewma = float(
            pd.Series(weights)
            .ewm(alpha=self.ewma_lambda, adjust=False)
            .mean()
            .iloc[-1]
        )

        slope, _, r, _, _ = linregress(np.arange(len(recent)), recent)

        alerts = self._check_alerts(rolling_mean, rolling_std, slope)
        seconds_until_ooc = self._predict_ooc(rolling_mean, slope)

        return {
            "n_samples":             n,
            "window_seconds":        win,
            "rolling_mean_g":        round(rolling_mean, 2),
            "rolling_std_g":         round(rolling_std, 3),
            "ewma_g":                round(ewma, 2),
            "trend_slope_g_per_s":   round(float(slope), 5),
            "trend_slope_g_per_min": round(float(slope) * 60, 2),
            "trend_r2":              round(float(r ** 2), 3),
            "seconds_until_ooc":     (
                round(seconds_until_ooc) if seconds_until_ooc is not None else None
            ),
            "alerts": alerts,
            "status": (
                "CRITICAL" if any("CRITICAL" in a for a in alerts)
                else "WARNING" if alerts
                else "OK"
            ),
        }

    def print_report(self, report: Dict) -> None:
        p = self.product
        width = 55
        print(f"\n{'='*width}")
        print(f"WEIGHT TREND MONITOR — {p.item_nm}")
        print(f"Target: {p.target_g}g  LCL: {p.lcl_g}g  UCL: {p.ucl_g}g")
        print(f"{'='*width}")

        print(f"\n[Rolling Statistics]  (last {report['window_seconds']}s, "
              f"n={report['n_samples']} readings)")
        print(f"  Mean  : {report['rolling_mean_g']:>8.2f}g")
        print(f"  Std   : {report['rolling_std_g']:>8.3f}g")
        print(f"  EWMA  : {report['ewma_g']:>8.2f}g")

        slope_min = report["trend_slope_g_per_min"]
        arrow = "↑" if slope_min > 0.01 else ("↓" if slope_min < -0.01 else "→")
        print(f"\n[Trend]")
        print(f"  Slope : {arrow} {abs(slope_min):.2f}g/min  "
              f"(R²={report['trend_r2']:.3f})")
        if report["seconds_until_ooc"] is not None:
            mins = report["seconds_until_ooc"] / 60
            limit = "LCL" if slope_min < 0 else "UCL"
            print(f"  → Reaches {limit} in ~{mins:.0f} min if trend continues")

        print(f"\n[Status]  {report['status']}")
        if report["alerts"]:
            for alert in report["alerts"]:
                prefix = "✖" if "CRITICAL" in alert else "⚠"
                print(f"  {prefix}  {alert}")
        else:
            print("  All checks passed")
        print(f"{'='*width}")

    # ──────────────────────────────────────────────────────────────────────────
    # Internal helpers
    # ──────────────────────────────────────────────────────────────────────────

    def _check_alerts(
        self,
        mean: float,
        std: float,
        slope: float,
    ) -> List[str]:
        alerts: List[str] = []
        target = self.product.target_g
        lcl    = self.product.lcl_g
        ucl    = self.product.ucl_g

        # Mean outside control limits
        if mean < lcl:
            alerts.append(
                f"CRITICAL: Rolling mean {mean:.1f}g is BELOW LCL {lcl:.1f}g"
            )
        elif ucl is not None and mean > ucl:
            alerts.append(
                f"CRITICAL: Rolling mean {mean:.1f}g is ABOVE UCL {ucl:.1f}g"
            )

        # High within-window variation (> 3% of target)
        if std > target * 0.03:
            alerts.append(
                f"WARNING: Weight variation too high "
                f"(σ={std:.2f}g, limit={target*0.03:.2f}g)"
            )

        # Meaningful drift (> 0.05 g/s ≈ 3 g/min)
        slope_per_min = slope * 60
        if slope_per_min < -1.0:
            alerts.append(
                f"WARNING: Falling trend {slope_per_min:.1f}g/min → approaching LCL"
            )
        elif slope_per_min > 1.0:
            alerts.append(
                f"WARNING: Rising trend +{slope_per_min:.1f}g/min → approaching UCL"
            )

        return alerts

    _OOC_HORIZON_S = 86_400  # 24 hours — beyond this the prediction is meaningless

    def _predict_ooc(self, mean: float, slope: float) -> Optional[float]:
        """Return seconds until weight hits LCL or UCL at current slope.

        Returns None when the trend is flat or moving away from limits,
        or when the projected crossing is more than 24 hours away.
        """
        lcl = self.product.lcl_g
        ucl = self.product.ucl_g

        if slope < -1e-6:  # falling toward LCL
            seconds = (mean - lcl) / abs(slope)
            seconds = max(0.0, seconds)
        elif slope > 1e-6 and ucl is not None:  # rising toward UCL
            seconds = (ucl - mean) / slope
            seconds = max(0.0, seconds)
        else:
            return None

        return seconds if seconds <= self._OOC_HORIZON_S else None
