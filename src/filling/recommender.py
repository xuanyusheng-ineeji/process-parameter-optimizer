"""Recommend optimal equipment Set Points to bring fill weight within spec."""

import numpy as np
from typing import Dict, List
from scipy.optimize import minimize, differential_evolution
from .config import PARAM_NAMES, ProductConfig, get_param_bounds
from .predictor import FillWeightPredictor


class SetPointRecommender:
    """
    Uses the trained prediction model + optimization to find equipment
    Set Points that produce fill weight closest to target while
    respecting LCL ≤ weight ≤ UCL.

    Optimization objective:
        minimize (predicted_weight - target)²
        subject to: predicted_weight ≥ LCL
                    predicted_weight ≤ UCL  (if defined)
    """

    def __init__(self, predictor: FillWeightPredictor, product: ProductConfig) -> None:
        self._predictor = predictor
        self._product = product
        self._bounds = get_param_bounds(product)

    def recommend(
        self,
        current_params: Dict[str, float],
        max_change_pct: float = 0.15,
        seed: int = 0,
    ) -> Dict:
        """
        Generate Set Point recommendations based on current parameter settings.

        Prefers minimal parameter changes: only adjusts what is necessary,
        prioritises the most influential parameters first.

        Args:
            current_params: Current equipment Set Points (dict of param→value)
            max_change_pct: Maximum allowed change per parameter as fraction of
                            its operating range (default 15%)

        Returns:
            Recommendation dict with suggested values, predicted weight, confidence
        """
        target = self._product.target_g
        lcl = self._product.lcl_g
        ucl = self._product.ucl_g

        scipy_bounds = [self._bounds[n] for n in PARAM_NAMES]
        current_arr = np.array([current_params.get(n, self._bounds[n][0]) for n in PARAM_NAMES])

        # Normalised range per parameter (used for change penalty scaling)
        ranges = np.array([b[1] - b[0] for b in scipy_bounds])

        # Feature importances from the model — less important params pay higher
        # change penalty, so the optimizer prefers moving the right levers
        importances = np.array([
            self._predictor.feature_importances().get(n, 1.0) for n in PARAM_NAMES
        ])
        importances = importances / importances.sum()
        # Inverse importance → penalty weight (unimportant params penalised more)
        change_weights = 1.0 / (importances + 0.05)
        change_weights = change_weights / change_weights.mean()

        # Narrow bounds to ±max_change_pct of range from current value
        constrained_bounds = []
        for i, (lo, hi) in enumerate(scipy_bounds):
            max_delta = ranges[i] * max_change_pct
            constrained_bounds.append((
                max(lo, current_arr[i] - max_delta),
                min(hi, current_arr[i] + max_delta),
            ))

        def objective(x: np.ndarray) -> float:
            params = dict(zip(PARAM_NAMES, x))
            predicted = self._predictor.predict(params)

            # Hard penalty: must stay above LCL
            penalty = max(0.0, lcl - predicted) * 1000.0
            # Soft penalty: stay below UCL
            if ucl is not None:
                penalty += max(0.0, predicted - ucl) * 500.0

            # Primary: distance from target
            weight_cost = (predicted - target) ** 2

            # Regularisation: penalise large changes, scaled by inverse importance
            normalised_changes = ((x - current_arr) / ranges) ** 2
            change_cost = float(np.dot(change_weights, normalised_changes)) * 50.0

            return weight_cost + change_cost + penalty

        # Start from current params; add a few small random perturbations
        best_result = None
        rng = np.random.default_rng(seed)
        starts = [current_arr.copy()]
        for _ in range(9):
            lo = np.array([b[0] for b in constrained_bounds])
            hi = np.array([b[1] for b in constrained_bounds])
            starts.append(rng.uniform(lo, hi))

        for x_start in starts:
            res = minimize(objective, x_start, bounds=constrained_bounds, method="L-BFGS-B")
            if best_result is None or res.fun < best_result.fun:
                best_result = res

        recommended_params = dict(zip(PARAM_NAMES, best_result.x))
        predicted_weight = self._predictor.predict(recommended_params)
        current_weight = self._predictor.predict(current_params)

        return {
            "product": self._product.item_nm,
            "item_cd": self._product.item_cd,
            "target_g": target,
            "lcl_g": lcl,
            "ucl_g": ucl,
            "current_params": current_params,
            "current_predicted_weight_g": round(current_weight, 2),
            "recommended_params": {k: round(v, 3) for k, v in recommended_params.items()},
            "recommended_predicted_weight_g": round(predicted_weight, 2),
            "weight_improvement_g": round(
                abs(current_weight - target) - abs(predicted_weight - target), 2
            ),
            "in_spec": _check_spec(predicted_weight, lcl, ucl),
        }

    def print_report(self, recommendation: Dict) -> None:
        r = recommendation
        p = self._product

        print("=" * 60)
        print(f"SET POINT RECOMMENDATION — {r['product']}")
        print(f"Target: {r['target_g']}g  LCL: {r['lcl_g']}g  UCL: {r['ucl_g']}g")
        print("=" * 60)

        print(f"\n[Current Situation]")
        print(f"  Predicted weight with current settings: {r['current_predicted_weight_g']}g")
        bias = r["current_predicted_weight_g"] - r["target_g"]
        print(f"  Deviation from target: {bias:+.2f}g")

        print(f"\n[Recommended Set Points]")
        print(f"  {'Parameter':<25} {'Current':>10} {'Recommended':>13} {'Change':>10}")
        print(f"  {'-'*60}")
        for name in PARAM_NAMES:
            cur = r["current_params"].get(name, "-")
            rec = r["recommended_params"][name]
            if isinstance(cur, float):
                change = rec - cur
                print(f"  {name:<25} {cur:>10.3f} {rec:>13.3f} {change:>+10.3f}")
            else:
                print(f"  {name:<25} {'N/A':>10} {rec:>13.3f}")

        print(f"\n[Expected Outcome]")
        print(f"  Predicted fill weight: {r['recommended_predicted_weight_g']}g")
        print(f"  Status: {r['in_spec']}")
        print(f"  Improvement: {r['weight_improvement_g']:+.2f}g closer to target")
        print("=" * 60)


def _check_spec(weight: float, lcl: float, ucl) -> str:
    if weight < lcl:
        return f"LOW — {lcl - weight:.2f}g below LCL (NOT OK)"
    if ucl is not None and weight > ucl:
        return f"HIGH — {weight - ucl:.2f}g above UCL (waste)"
    return "OK ✓"
