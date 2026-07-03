"""Tests for the fill-weight prediction model."""
import pytest
from src.filling import synthetic_data, data_loader
from src.filling.config import PRODUCTS
from src.filling.predictor import FillWeightPredictor

ITEM_CD = "285104"
product = PRODUCTS[ITEM_CD]


@pytest.fixture
def trained_predictor():
    raw = synthetic_data.generate(ITEM_CD, n_batches=200, seed=42)
    df = data_loader.from_dataframe(raw, item_cd=ITEM_CD)
    pred = FillWeightPredictor()
    pred.train(df, product)
    return pred


@pytest.fixture
def train_result():
    raw = synthetic_data.generate(ITEM_CD, n_batches=200, seed=42)
    df = data_loader.from_dataframe(raw, item_cd=ITEM_CD)
    pred = FillWeightPredictor()
    return pred.train(df, product)


def test_r2_above_threshold(train_result):
    # train() returns a sorted comparison list; index 0 is the selected model
    best_r2 = train_result["comparison"][0]["r2_cv_mean"]
    assert best_r2 >= 0.80, f"R² too low: {best_r2:.3f}"


def test_predict_returns_float(trained_predictor):
    params = product.nominal_params.copy()
    result = trained_predictor.predict(params)
    assert isinstance(result, float)
    assert result > 0


def test_predict_near_target_at_nominal(trained_predictor):
    params = product.nominal_params.copy()
    predicted = trained_predictor.predict(params)
    assert abs(predicted - product.target_g) < product.target_g * 0.05


def test_feature_importances_sum_to_one(trained_predictor):
    importances = trained_predictor.feature_importances()
    total = sum(importances.values())
    assert abs(total - 1.0) < 1e-6


def test_predict_before_train_raises():
    pred = FillWeightPredictor()
    with pytest.raises(RuntimeError):
        pred.predict(product.nominal_params)


def test_predict_missing_param_raises(trained_predictor):
    """P1-03 fix: missing keys must raise ValueError with a clear message."""
    from src.filling.config import PARAM_NAMES
    incomplete = {k: v for k, v in product.nominal_params.items()
                  if k != PARAM_NAMES[0]}  # drop first param
    with pytest.raises(ValueError, match="missing required parameters"):
        trained_predictor.predict(incomplete)
