"""Tests for the Set Point recommender."""
import pytest
from src.filling import synthetic_data, data_loader
from src.filling.config import PRODUCTS
from src.filling.predictor import FillWeightPredictor
from src.filling.recommender import SetPointRecommender

ITEM_CD = "285104"
product = PRODUCTS[ITEM_CD]


@pytest.fixture
def recommender():
    raw = synthetic_data.generate(ITEM_CD, n_batches=200, seed=42)
    df = data_loader.from_dataframe(raw, item_cd=ITEM_CD)
    pred = FillWeightPredictor()
    pred.train(df, product)
    return SetPointRecommender(pred, product)


def test_recommendation_in_spec(recommender):
    current = product.nominal_params.copy()
    current["fill_time_s"] *= 0.90  # deliberately light
    rec = recommender.recommend(current)
    w = rec["recommended_predicted_weight_g"]
    assert w >= product.lcl_g, f"Recommended weight {w}g below LCL {product.lcl_g}g"
    if product.ucl_g:
        assert w <= product.ucl_g, f"Recommended weight {w}g above UCL {product.ucl_g}g"


def test_recommendation_improves_weight(recommender):
    current = product.nominal_params.copy()
    current["fill_time_s"] *= 0.90
    rec = recommender.recommend(current)
    assert rec["weight_improvement_g"] > 0


def test_max_change_respected(recommender):
    from src.filling.config import get_param_bounds, PARAM_NAMES
    current = product.nominal_params.copy()
    current["fill_time_s"] *= 0.85
    bounds = get_param_bounds(product)
    max_pct = 0.15

    rec = recommender.recommend(current, max_change_pct=max_pct)
    for name in PARAM_NAMES:
        lo, hi = bounds[name]
        max_delta = (hi - lo) * max_pct
        actual_change = abs(rec["recommended_params"][name] - current[name])
        assert actual_change <= max_delta + 1e-6, (
            f"{name}: change {actual_change:.4f} exceeds limit {max_delta:.4f}"
        )


def test_recommendation_keys_present(recommender):
    rec = recommender.recommend(product.nominal_params.copy())
    for key in ["product", "item_cd", "target_g", "recommended_params",
                "recommended_predicted_weight_g", "in_spec"]:
        assert key in rec


def test_already_in_spec_remains_in_spec(recommender):
    """P3-04: when current weight is already within spec, recommendation keeps in_spec as OK."""
    # Use nominal params which should produce on-target weight
    rec = recommender.recommend(product.nominal_params.copy())
    assert "OK" in rec["in_spec"], (
        f"Nominal params should produce in-spec weight, got: {rec['in_spec']}"
    )
    assert rec["weight_improvement_g"] >= 0, "Should not worsen an already-good result"
