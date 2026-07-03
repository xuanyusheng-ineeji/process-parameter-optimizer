"""Tests for product configuration."""
import pytest
from src.filling.config import PRODUCTS, get_param_bounds, get_size_class, get_tolerance_pct

TARGET_ITEM_CDS = [
    "282113", "284023", "284047", "284059", "284235", "284319",
    "284516", "284535", "284573", "284760", "284961", "285101",
    "285102", "285103", "285104", "374424",
]


def test_all_16_products_present():
    for item_cd in TARGET_ITEM_CDS:
        assert item_cd in PRODUCTS, f"{item_cd} missing from PRODUCTS"


def test_lcl_equals_target():
    """Food law: LCL must equal target weight (cannot underfill)."""
    for item_cd, p in PRODUCTS.items():
        assert p.lcl_g == p.target_g, f"{item_cd}: LCL ({p.lcl_g}) != target ({p.target_g})"


def test_ucl_above_target():
    for item_cd, p in PRODUCTS.items():
        if p.ucl_g is not None:
            assert p.ucl_g >= p.target_g, f"{item_cd}: UCL below target"


def test_param_bounds_valid():
    for item_cd, p in PRODUCTS.items():
        bounds = get_param_bounds(p)
        for name, (lo, hi) in bounds.items():
            assert lo < hi, f"{item_cd} {name}: invalid bounds ({lo}, {hi})"
            nominal = p.nominal_params[name]
            assert lo <= nominal <= hi, (
                f"{item_cd} {name}: nominal {nominal} outside bounds [{lo}, {hi}]"
            )


def test_size_class():
    assert get_size_class(PRODUCTS["285104"]) == "small"   # 300g
    assert get_size_class(PRODUCTS["374424"]) == "medium"  # 3000g


def test_tolerance_pct():
    p = PRODUCTS["285104"]  # UCL=330, target=300 → 10%
    assert abs(get_tolerance_pct(p) - 10.0) < 0.1

    p_no_ucl = PRODUCTS["284760"]  # No UCL
    assert get_tolerance_pct(p_no_ucl) is None
