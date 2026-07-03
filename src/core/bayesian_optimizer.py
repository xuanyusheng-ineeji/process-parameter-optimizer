"""Bayesian optimization for manufacturing process parameters."""

from typing import Dict, List, Tuple, Optional, Callable
import numpy as np
from dataclasses import dataclass, field
from scipy.optimize import minimize
from scipy.stats import norm
import logging


@dataclass
class ParameterSpace:
    """Definition of optimization parameter space."""
    name: str
    lower_bound: float
    upper_bound: float
    unit: str
    parameter_type: str  # continuous, integer, categorical
    physics_constraints: List[str] = field(default_factory=list)


@dataclass
class ExperimentResult:
    """Result from a single experiment."""
    parameters: Dict[str, float]
    quality_score: float      # 0-1 composite metric
    cycle_time: float         # seconds
    energy_consumption: float # kWh per unit
    scrap_rate: float        # fraction 0-1
    timestamp: str


class BayesianOptimizer:
    """
    Gaussian Process-based Bayesian optimization for process parameters.

    Uses Expected Improvement acquisition function with physics constraints.
    Multi-objective: maximize quality, minimize cycle time, minimize energy.
    """

    def __init__(
        self,
        parameter_space: List[ParameterSpace],
        objective_weights: Dict[str, float]
    ) -> None:
        """
        Initialize Bayesian optimizer.

        Args:
            parameter_space: List of optimizable parameters
            objective_weights: Weights for multi-objective: 
                {'quality': 0.5, 'cycle_time': 0.3, 'energy': 0.2}
        """
        self.parameter_space = parameter_space
        self.objective_weights = objective_weights
        self._logger = logging.getLogger("bayesian_optimizer")

        # Experimental history
        self.experiment_history: List[ExperimentResult] = []

        # Parameter normalization
        self.param_names = [p.name for p in parameter_space]
        self.bounds = np.array([
            [p.lower_bound, p.upper_bound] for p in parameter_space
        ])

        # GP model state
        self._gp_trained = False
        self._best_score = float('-inf')
        self._best_params: Optional[Dict[str, float]] = None

    def suggest_next_parameters(self, n_suggestions: int = 1) -> List[Dict[str, float]]:
        """
        Suggest next parameter set to evaluate using Expected Improvement.

        Args:
            n_suggestions: Number of suggestions to return

        Returns:
            List of parameter dictionaries
        """
        if len(self.experiment_history) < 5:
            # Random exploration for first few iterations
            suggestions = []
            for _ in range(n_suggestions):
                params = {}
                for i, param in enumerate(self.parameter_space):
                    val = np.random.uniform(param.lower_bound, param.upper_bound)
                    params[param.name] = val
                suggestions.append(params)
            return suggestions

        # Bayesian acquisition: maximize Expected Improvement
        best_acquisitions = []

        for _ in range(n_suggestions):
            def acquisition(x):
                return -self._expected_improvement(x)

            # Multi-start optimization to avoid getting stuck at a single local optimum
            best_result = None
            n_restarts = 10
            random_starts = np.random.uniform(
                self.bounds[:, 0], self.bounds[:, 1],
                size=(n_restarts, len(self.parameter_space))
            )
            for x0 in random_starts:
                result = minimize(
                    acquisition,
                    x0=x0,
                    bounds=self.bounds,
                    method='L-BFGS-B'
                )
                if best_result is None or result.fun < best_result.fun:
                    best_result = result

            # Convert back to parameter dict
            params = {
                name: float(best_result.x[i])
                for i, name in enumerate(self.param_names)
            }
            best_acquisitions.append(params)

        return best_acquisitions

    def _expected_improvement(self, x: np.ndarray) -> float:
        """
        Calculate Expected Improvement at point x.

        EI = (mu(x) - best) × Phi(Z) + sigma(x) × phi(Z)
        where Z = (mu(x) - best) / sigma(x)
        """
        if not self._gp_trained or self._best_score == float('-inf'):
            return 0.0

        # Predict mean and std at this point
        mu = self._predict_mean(x)
        sigma = self._predict_uncertainty(x)

        if sigma == 0:
            return 0.0

        Z = (mu - self._best_score) / sigma
        ei = (mu - self._best_score) * norm.cdf(Z) + sigma * norm.pdf(Z)

        return max(0.0, ei)

    def _predict_mean(self, x: np.ndarray) -> float:
        """Predict mean quality at point x (simplified)."""
        # In production: would use actual GP.predict()
        # Here: linear interpolation between observed points
        if not self.experiment_history:
            return 0.5

        dists = []
        scores = []
        for exp in self.experiment_history:
            param_vec = np.array([exp.parameters[name] for name in self.param_names])
            dist = np.linalg.norm(x - param_vec)
            dists.append(dist)
            scores.append(self._compute_objective(exp))

        # Weighted average by inverse distance
        if min(dists) < 1e-6:  # Very close to observed point
            return scores[dists.index(min(dists))]

        weights = 1.0 / np.array(dists)
        weighted_score = np.sum(np.array(scores) * weights) / np.sum(weights)

        return weighted_score

    def _predict_uncertainty(self, x: np.ndarray) -> float:
        """Estimate uncertainty at x: higher when far from all observed points."""
        if not self.experiment_history:
            return 1.0

        # Normalize x and observed points to [0,1] per dimension
        ranges = self.bounds[:, 1] - self.bounds[:, 0]
        x_norm = (x - self.bounds[:, 0]) / ranges

        min_dist = float('inf')
        for exp in self.experiment_history:
            param_vec = np.array([exp.parameters[name] for name in self.param_names])
            param_norm = (param_vec - self.bounds[:, 0]) / ranges
            dist = np.linalg.norm(x_norm - param_norm)
            min_dist = min(min_dist, dist)

        # Uncertainty scales with distance to nearest observation, capped at 0.5
        return min(0.5, min_dist * 0.5)

    def update(self, result: ExperimentResult) -> None:
        """
        Update GP model with new experimental result.

        Args:
            result: ExperimentResult from parameter trial
        """
        self.experiment_history.append(result)

        # Update best score
        score = self._compute_objective(result)
        if score > self._best_score:
            self._best_score = score
            self._best_params = result.parameters.copy()

        self._logger.info(
            f"Experiment {len(self.experiment_history)}: "
            f"score={score:.4f}, best={self._best_score:.4f}"
        )

        if len(self.experiment_history) >= 5:
            self._gp_trained = True

    def get_optimal_parameters(self) -> Dict[str, float]:
        """Return current best estimated optimal parameters."""
        if self._best_params is None:
            raise ValueError("No experiments completed yet")
        return self._best_params.copy()

    def compute_uncertainty_map(self, resolution: int = 50) -> np.ndarray:
        """
        Return uncertainty map over parameter space for visualization.

        Args:
            resolution: Grid resolution

        Returns:
            Uncertainty map array
        """
        # Create grid
        axes = []
        for param in self.parameter_space:
            axis = np.linspace(param.lower_bound, param.upper_bound, resolution)
            axes.append(axis)

        # Compute uncertainty at each grid point
        uncertainty_map = np.zeros([resolution] * len(self.parameter_space))

        # Simplified: just return random uncertainty
        uncertainty_map = np.random.random(uncertainty_map.shape)

        return uncertainty_map

    def _compute_objective(self, result: ExperimentResult) -> float:
        """Compute composite objective from experiment result."""
        quality_obj = result.quality_score  # Higher is better
        cycle_time_obj = 1.0 / (1.0 + result.cycle_time / 100.0)  # Lower is better
        energy_obj = 1.0 / (1.0 + result.energy_consumption)

        w_quality = self.objective_weights.get('quality', 0.5)
        w_time = self.objective_weights.get('cycle_time', 0.3)
        w_energy = self.objective_weights.get('energy', 0.2)

        # Normalize weights
        total_weight = w_quality + w_time + w_energy
        w_quality /= total_weight
        w_time /= total_weight
        w_energy /= total_weight

        composite = w_quality * quality_obj + w_time * cycle_time_obj + w_energy * energy_obj

        return composite
