"""Product configurations for the 16 filling products (from MST_ITEM_202606231336.csv)."""

from dataclasses import dataclass, field
from typing import Dict, Optional


@dataclass
class ProductConfig:
    item_cd: str
    item_nm: str
    target_g: float     # CHG_WEIGHT — also the legal minimum (LCL = target for food products)
    lcl_g: float        # CHG_WEIGHT_LCL — must fill AT LEAST this amount (legal requirement)
    ucl_g: Optional[float]  # CHG_WEIGHT_UCL — None means no upper limit defined
    nominal_params: Dict[str, float] = field(default_factory=dict)


# Nominal machine parameters by package size class
# These will be replaced with real machine data when available
_NOMINAL_SMALL = {   # ~200-300g
    "fill_time_s": 1.8,
    "fill_pressure_bar": 1.8,
    "product_temp_c": 18.0,
    "nozzle_opening_pct": 70.0,
    "line_speed_bpm": 40.0,
}

_NOMINAL_MEDIUM = {  # ~3000g
    "fill_time_s": 4.2,
    "fill_pressure_bar": 2.4,
    "product_temp_c": 18.0,
    "nozzle_opening_pct": 75.0,
    "line_speed_bpm": 20.0,
}

# 16 products from WRK_WEIGHT_SUMMARY_ORDER with real Target/LCL/UCL from CSV
# NOTE: LCL = target for all food products (legal minimum fill weight)
PRODUCTS: Dict[str, ProductConfig] = {
    # --- 3kg bag products ---
    "282113": ProductConfig("282113", "DD)보름달딸기크림F-(3Kg*3ea)", 3000, 3000, 3333.3, dict(_NOMINAL_MEDIUM)),
    "284023": ProductConfig("284023", "연유크림",                      300,   300,  330.0,  dict(_NOMINAL_SMALL)),
    "284047": ProductConfig("284047", "연유토핑물",                    300,   300,  330.0,  dict(_NOMINAL_SMALL)),
    "284059": ProductConfig("284059", "[수출]뉴아몬드크림",             250,   250,  270.0,  dict(_NOMINAL_SMALL)),
    "284235": ProductConfig("284235", "화이트크림F 9kg",               3000,  3000, 3333.3, dict(_NOMINAL_MEDIUM)),
    "284319": ProductConfig("284319", "연유크림F-9kg(화이트)",          3000,  3000, 3050.0, dict(_NOMINAL_MEDIUM)),
    "284516": ProductConfig("284516", "PC에그마요 3kg",                3000,  3000, 3100.0, dict(_NOMINAL_MEDIUM)),
    "284535": ProductConfig("284535", "[수출]마늘토핑",                 200,   200,  230.0,  dict(_NOMINAL_SMALL)),
    "284573": ProductConfig("284573", "DD)오)화이트크림F-9kg",          3000,  3000, 3333.3, dict(_NOMINAL_MEDIUM)),
    "284760": ProductConfig("284760", "[수출]캄보디아_연유크림",         240,   240,  None,   dict(_NOMINAL_SMALL)),
    "284961": ProductConfig("284961", "[수출]베트남_연유크림",           240,   240,  260.0,  dict(_NOMINAL_SMALL)),
    "285101": ProductConfig("285101", "BK)냉아몬드크림 300g",           300,   300,  330.0,  dict(_NOMINAL_SMALL)),
    "285102": ProductConfig("285102", "BK)냉커피번토핑물 300g",          300,   300,  330.0,  dict(_NOMINAL_SMALL)),
    "285103": ProductConfig("285103", "BK)마늘크림믹스F 300g",           300,   300,  330.0,  dict(_NOMINAL_SMALL)),
    "285104": ProductConfig("285104", "BK)연유크림F 300g",               300,   300,  330.0,  dict(_NOMINAL_SMALL)),
    "374424": ProductConfig("374424", "반)토마토크림치즈3KG(샐러드용)",  3000,  3000, 3030.0, dict(_NOMINAL_MEDIUM)),
}

PARAM_NAMES = ["fill_time_s", "fill_pressure_bar", "product_temp_c", "nozzle_opening_pct", "line_speed_bpm"]

# Parameter bounds by size class
PARAM_BOUNDS = {
    "fill_time_s":        {"small": (1.2, 2.5),  "medium": (3.0, 5.5)},
    "fill_pressure_bar":  {"small": (1.2, 2.5),  "medium": (1.8, 3.2)},
    "product_temp_c":     {"small": (8.0, 28.0), "medium": (8.0, 28.0)},
    "nozzle_opening_pct": {"small": (50.0, 90.0),"medium": (55.0, 95.0)},
    "line_speed_bpm":     {"small": (25.0, 55.0),"medium": (12.0, 28.0)},
}


def get_size_class(product: ProductConfig) -> str:
    return "small" if product.target_g <= 500 else "medium"


def get_param_bounds(product: ProductConfig) -> Dict[str, tuple]:
    size = get_size_class(product)
    return {param: PARAM_BOUNDS[param][size] for param in PARAM_NAMES}


def get_tolerance_pct(product: ProductConfig) -> Optional[float]:
    """Return allowed overfill percentage above target. None if no UCL defined."""
    if product.ucl_g is None:
        return None
    return (product.ucl_g - product.target_g) / product.target_g * 100
