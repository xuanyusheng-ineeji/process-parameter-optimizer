"""
Multi-model predictor: trains all candidates and selects the best by CV R².

Candidate models
----------------
Linear family  : LinearRegression, Ridge, Lasso, ElasticNet,
                 HuberRegressor, BayesianRidge
Kernel         : SVR (RBF kernel)
Instance-based : KNeighborsRegressor
Tree / Forest  : DecisionTree, ExtraTrees, RandomForest
Boosting       : GradientBoosting, HistGradientBoosting
"""

from __future__ import annotations

import warnings
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
from sklearn.ensemble import (
    ExtraTreesRegressor,
    GradientBoostingRegressor,
    HistGradientBoostingRegressor,
    RandomForestRegressor,
)
from sklearn.linear_model import (
    BayesianRidge,
    ElasticNet,
    HuberRegressor,
    Lasso,
    LinearRegression,
    Ridge,
)
from sklearn.model_selection import cross_val_score
from sklearn.neighbors import KNeighborsRegressor
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVR
from sklearn.tree import DecisionTreeRegressor

from .config import PARAM_NAMES, ProductConfig


def _pipe(estimator) -> Pipeline:
    return Pipeline([("scaler", StandardScaler()), ("model", estimator)])


CANDIDATE_MODELS: Dict[str, Pipeline] = {
    # ── Linear family ─────────────────────────────────────────────────────────
    "LinearRegression": _pipe(LinearRegression()),
    "Ridge": _pipe(Ridge(alpha=1.0)),
    "Lasso": _pipe(Lasso(alpha=0.01, max_iter=5000)),
    "ElasticNet": _pipe(ElasticNet(alpha=0.01, l1_ratio=0.5, max_iter=5000)),
    "HuberRegressor": _pipe(HuberRegressor(epsilon=1.35, max_iter=300)),
    "BayesianRidge": _pipe(BayesianRidge()),
    # ── Kernel ────────────────────────────────────────────────────────────────
    "SVR_RBF": _pipe(SVR(kernel="rbf", C=10.0, gamma="scale", epsilon=0.1)),
    "SVR_Poly": _pipe(SVR(kernel="poly", degree=3, C=5.0, epsilon=0.1)),
    # ── Instance-based ────────────────────────────────────────────────────────
    "KNeighbors_5": _pipe(KNeighborsRegressor(n_neighbors=5, weights="distance")),
    "KNeighbors_10": _pipe(KNeighborsRegressor(n_neighbors=10, weights="distance")),
    # ── Tree / Forest ─────────────────────────────────────────────────────────
    "DecisionTree": _pipe(DecisionTreeRegressor(max_depth=6, random_state=42)),
    "ExtraTrees": _pipe(
        ExtraTreesRegressor(n_estimators=150, max_depth=8, random_state=42, n_jobs=-1)
    ),
    "RandomForest": _pipe(
        RandomForestRegressor(n_estimators=150, max_depth=8, random_state=42, n_jobs=-1)
    ),
    # ── Boosting ──────────────────────────────────────────────────────────────
    "GradientBoosting": _pipe(
        GradientBoostingRegressor(
            n_estimators=200, max_depth=4, learning_rate=0.05,
            subsample=0.8, random_state=42,
        )
    ),
    "HistGradientBoosting": _pipe(
        HistGradientBoostingRegressor(
            max_iter=200, max_depth=4, learning_rate=0.05,
            min_samples_leaf=5, random_state=42,
        )
    ),
}


class FillWeightPredictor:
    """
    Trains every CANDIDATE_MODEL with 5-fold CV and selects the one
    with the highest mean CV R².

    Public API:
        train(df, product)   → training summary dict
        predict(params)      → float
        predict_batch(df)    → np.ndarray
        feature_importances()→ Dict[str, float]
        print_summary()      → console table
    """

    def __init__(self) -> None:
        self._best_pipeline: Optional[Pipeline] = None
        self._best_name: str = ""
        self._comparison: List[Dict] = []
        self._train_stats: Dict = {}
        self._trained = False
        self._n_samples = 0

    # ──────────────────────────────────────────────────────────────────────────
    # Training
    # ──────────────────────────────────────────────────────────────────────────

    def train(self, df: pd.DataFrame, product: ProductConfig, cv: int = 5) -> Dict:
        """
        Train all candidate models and select the best by CV R².

        Returns:
            Dict with ``selected_model``, ``n_samples``, and ``comparison`` list.
        """
        X = df[PARAM_NAMES].values
        y = df["fill_weight_g"].values
        n = len(df)

        results = []
        for name, pipeline in CANDIDATE_MODELS.items():
            # CV may fail for very small datasets (< cv folds); guard gracefully
            try:
                cv_scores = cross_val_score(
                    pipeline, X, y, cv=min(cv, n), scoring="r2"
                )
                r2_mean = float(cv_scores.mean())
                r2_std = float(cv_scores.std())
            except ValueError as e:
                warnings.warn(f"[predictor] {name}: CV failed — {e}", stacklevel=2)
                r2_mean, r2_std = -999.0, 0.0

            pipeline.fit(X, y)
            residuals = y - pipeline.predict(X)
            results.append(
                {
                    "name": name,
                    "pipeline": pipeline,
                    "r2_cv_mean": r2_mean,
                    "r2_cv_std": r2_std,
                    "residual_std_g": float(residuals.std()),
                }
            )

        results.sort(key=lambda x: x["r2_cv_mean"], reverse=True)
        best = results[0]

        # Assign all state before setting _trained to avoid partially-initialised object
        self._best_pipeline = best["pipeline"]
        self._best_name = best["name"]
        self._comparison = results
        self._n_samples = n
        self._train_stats = {
            "r2_cv_mean": best["r2_cv_mean"],
            "r2_cv_std": best["r2_cv_std"],
            "residual_std_g": best["residual_std_g"],
        }
        self._trained = True  # set last — predictor is ready only after all fields are assigned

        return {
            "selected_model": self._best_name,
            "n_samples": n,
            "comparison": [
                {k: v for k, v in r.items() if k != "pipeline"} for r in results
            ],
        }

    # ──────────────────────────────────────────────────────────────────────────
    # Inference
    # ──────────────────────────────────────────────────────────────────────────

    def predict(self, params: Dict[str, float]) -> float:
        self._assert_trained()
        missing = set(PARAM_NAMES) - set(params)
        if missing:
            raise ValueError(f"predict() missing required parameters: {sorted(missing)}")
        X = np.array([[params[n] for n in PARAM_NAMES]])
        return float(self._best_pipeline.predict(X)[0])

    def predict_batch(self, df: pd.DataFrame) -> np.ndarray:
        self._assert_trained()
        return self._best_pipeline.predict(df[PARAM_NAMES].values)

    # ──────────────────────────────────────────────────────────────────────────
    # Explainability
    # ──────────────────────────────────────────────────────────────────────────

    def feature_importances(self) -> Dict[str, float]:
        """
        Unified importance accessor:
        - tree models   → .feature_importances_
        - linear models → |coef_| normalised to sum=1
        - SVR/KNN       → equal weight (model gives no native importance)
        """
        self._assert_trained()
        model = self._best_pipeline.named_steps["model"]

        if hasattr(model, "feature_importances_"):
            raw = model.feature_importances_
        elif hasattr(model, "coef_"):
            raw = np.abs(model.coef_)
        else:
            raw = np.ones(len(PARAM_NAMES))

        total = raw.sum() + 1e-9
        return dict(zip(PARAM_NAMES, (raw / total).tolist()))

    # ──────────────────────────────────────────────────────────────────────────
    # Reporting
    # ──────────────────────────────────────────────────────────────────────────

    def print_summary(self) -> None:
        self._assert_trained()
        w = 22
        print(f"\n{'─'*62}")
        print(f"{'Model':<{w}} {'CV R²':>8} {'±':>6} {'Train σ (g)':>12}")
        print(f"{'─'*62}")
        for r in self._comparison:
            marker = " ◀" if r["name"] == self._best_name else "  "
            star = "★ " if r["name"] == self._best_name else "  "
            if r["r2_cv_mean"] < -10:
                r2_str = "  FAILED"
                std_str = "     –"
                sig_str = "           –"
            else:
                r2_str = f"{r['r2_cv_mean']:>8.3f}"
                std_str = f"{r['r2_cv_std']:>6.3f}"
                sig_str = f"{r['residual_std_g']:>10.2f}g"
            print(f"{star}{r['name']:<{w-2}} {r2_str} {std_str} {sig_str}{marker}")
        print(f"{'─'*62}")
        print(f"Selected: {self._best_name}  |  n={self._n_samples} batches")
        print(
            f"Best CV R²: {self._train_stats['r2_cv_mean']:.4f}"
            f" ± {self._train_stats['r2_cv_std']:.4f}"
        )

    # ──────────────────────────────────────────────────────────────────────────
    # Internal
    # ──────────────────────────────────────────────────────────────────────────

    def _assert_trained(self) -> None:
        if not self._trained:
            raise RuntimeError("Call train() before using the predictor.")
