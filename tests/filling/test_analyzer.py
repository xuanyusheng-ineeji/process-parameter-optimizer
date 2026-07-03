"""Unit tests for RootCauseAnalyzer."""
import pytest
from src.filling import synthetic_data, data_loader
from src.filling.config import PRODUCTS, PARAM_NAMES
from src.filling.predictor import FillWeightPredictor
from src.filling.analyzer import RootCauseAnalyzer

ITEM_CD = "285104"
product = PRODUCTS[ITEM_CD]


@pytest.fixture(scope="module")
def analyzer():
    raw = synthetic_data.generate(ITEM_CD, n_batches=200, seed=42)
    df = data_loader.from_dataframe(raw, item_cd=ITEM_CD)
    pred = FillWeightPredictor()
    pred.train(df, product)
    return RootCauseAnalyzer(pred, product), df


def test_importance_sums_to_100(analyzer):
    rca, df = analyzer
    result = rca.analyze(df)
    total = sum(v for _, v in result["importance"])
    assert abs(total - 100.0) < 0.5, f"Importance total {total:.2f} != 100%"


def test_all_params_in_importance(analyzer):
    rca, df = analyzer
    result = rca.analyze(df)
    names = [n for n, _ in result["importance"]]
    assert set(names) == set(PARAM_NAMES)


def test_top_cause_is_valid_param(analyzer):
    rca, df = analyzer
    result = rca.analyze(df)
    assert result["top_cause"] in PARAM_NAMES


def test_direction_keys_are_param_names(analyzer):
    rca, df = analyzer
    result = rca.analyze(df)
    assert set(result["direction"].keys()) == set(PARAM_NAMES)


def test_direction_values_are_valid(analyzer):
    rca, df = analyzer
    result = rca.analyze(df)
    valid = {"↑ increases weight", "↓ decreases weight"}
    for name, direction in result["direction"].items():
        assert direction in valid, f"{name}: unexpected direction '{direction}'"


def test_deviation_summary_keys(analyzer):
    rca, df = analyzer
    result = rca.analyze(df)
    dev = result["deviation_summary"]
    for key in ["mean_weight_g", "std_g", "bias_g", "ok_pct", "low_pct", "high_pct"]:
        assert key in dev, f"Missing key: {key}"


def test_pct_sums_to_100(analyzer):
    rca, df = analyzer
    result = rca.analyze(df)
    dev = result["deviation_summary"]
    total_pct = dev["ok_pct"] + dev["low_pct"] + dev["high_pct"]
    assert abs(total_pct - 100.0) < 0.5, f"Pct total {total_pct:.2f} != 100%"
