"""Tests for data loading and validation."""
import pytest
import pandas as pd
from src.filling import synthetic_data, data_loader
from src.filling.config import PRODUCTS

ITEM_CD = "285104"


@pytest.fixture
def sample_df():
    raw = synthetic_data.generate(ITEM_CD, n_batches=50, seed=0)
    return data_loader.from_dataframe(raw, item_cd=ITEM_CD)


def test_loads_correct_columns(sample_df):
    required = ["fill_time_s", "fill_pressure_bar", "product_temp_c",
                "nozzle_opening_pct", "line_speed_bpm", "fill_weight_g", "item_cd"]
    for col in required:
        assert col in sample_df.columns, f"Missing column: {col}"


def test_no_zero_weights(sample_df):
    assert (sample_df["fill_weight_g"] > 0).all()


def test_item_cd_filter():
    raw = synthetic_data.generate_all(n_batches=20)
    df = data_loader.from_dataframe(raw, item_cd=ITEM_CD)
    assert (df["item_cd"] == ITEM_CD).all()


def test_missing_column_raises():
    bad_df = pd.DataFrame({"fill_weight_g": [300], "item_cd": [ITEM_CD]})
    with pytest.raises(ValueError, match="Missing columns"):
        data_loader.from_dataframe(bad_df, item_cd=ITEM_CD)


def test_all_invalid_rows_raises():
    """P2-01 fix: all rows removed by cleaning must raise ValueError, not return empty df."""
    raw = synthetic_data.generate(ITEM_CD, n_batches=10, seed=0)
    raw["fill_weight_g"] = 0          # force all rows to be dropped
    with pytest.raises(ValueError, match="All.*rows were removed"):
        data_loader.from_dataframe(raw, item_cd=ITEM_CD)


def test_single_valid_row():
    """Loader should handle a minimal single-row dataset without error."""
    raw = synthetic_data.generate(ITEM_CD, n_batches=1, seed=0)
    df = data_loader.from_dataframe(raw, item_cd=ITEM_CD)
    assert len(df) == 1
    assert df["fill_weight_g"].iloc[0] > 0
