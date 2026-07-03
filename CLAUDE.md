# CLAUDE.md

## Project Overview

Food factory filling process parameter optimizer. Analyzes historical production data (parameters + fill weights), identifies root causes of weight deviation, and recommends new equipment Set Points for engineers to enter manually into PLC/HMI.

**The system does NOT automate PLC control — output is recommendations only.**

## Environment & Commands

```powershell
# Activate environment (conda)
conda activate venv

# Install package in editable mode (required once after cloning)
pip install -e .

# Run end-to-end demo
python scripts/demo_filling.py

# Run all tests
python -m pytest tests/filling/ -v

# Expected test result: 30 passed
```

## Architecture

```
src/filling/          ← active development (filling process)
  config.py           product configs + parameter bounds
  data_loader.py      CSV/Excel/DataFrame ingestion + cleaning
  synthetic_data.py   physics-based test data generator
  predictor.py        trains 15 models, selects best by CV R²
  analyzer.py         feature importance + sensitivity direction
  recommender.py      constrained L-BFGS-B optimization for Set Points

src/core/             ← legacy (injection molding project, not used by filling)
  bayesian_optimizer.py
  injection_molding.py

scripts/demo_filling.py   end-to-end 4-step demo
tests/filling/            30 tests across 5 test files
```

## Key Domain Rules

- **LCL always equals target_g** — food law prohibits underfilling; never relax this.
- **UCL is optional** — some export products have `ucl_g = None`; always null-check before using.
- **Size classes**: ≤ 500g → `"small"`, > 500g → `"medium"`; bounds differ between classes.
- **16 products** are hardcoded in `config.py` (item codes 282113–374424). Source of truth is `data/raw/MST_ITEM_202606231336.csv` but config is not auto-loaded from it yet.

## Machine Parameters

Current `PARAM_NAMES` are placeholder names:

```python
PARAM_NAMES = [
    "fill_time_s", "fill_pressure_bar", "product_temp_c",
    "nozzle_opening_pct", "line_speed_bpm"
]
```

Actual machine parameters (pump inverter speed, correction outputs, etc.) are documented in Korean in `docs/machine_parameters.txt`. Replace `PARAM_NAMES` and `nominal_params` in `config.py` once real data is available.

## Predictor Model Selection

`FillWeightPredictor.train()` trains 15 candidate models (linear, SVR, KNN, tree, boosting) and picks the highest CV R² automatically. In practice, linear models (HuberRegressor, Ridge) usually win on synthetic data; tree models may win on real data with nonlinear physical interactions.

## Recommender Constraints

`SetPointRecommender.recommend()`:
- `max_change_pct=0.15` — each parameter can move at most ±15% of its operating range.
- Change penalty is weighted by **inverse feature importance**: unimportant parameters are heavily penalized for changing (preserves engineer intuition).
- Hard LCL penalty: 1000×; soft UCL penalty: 500×.
- 10 random multi-starts with configurable `seed`.

## Data Loading Contract

Input DataFrame must contain these exact columns (case-insensitive, auto-lowercased):

```
item_cd, fill_time_s, fill_pressure_bar, product_temp_c,
nozzle_opening_pct, line_speed_bpm, fill_weight_g
```

`_clean()` raises `ValueError` if all rows are removed after cleaning — never silently returns empty DataFrame.

## Adding a New Product

1. Add a `ProductConfig` entry to `PRODUCTS` in `src/filling/config.py`.
2. Ensure `lcl_g == target_g` (enforced by `test_lcl_equals_target`).
3. Add the item code to `TARGET_ITEM_CDS` in `tests/filling/test_config.py`.
4. Run `pytest tests/filling/test_config.py` to verify.

## Replacing Synthetic Data with Real Data

```python
# In scripts/demo_filling.py, swap:
raw_df = synthetic_data.generate(item_cd, n_batches=300, seed=42)
df = data_loader.from_dataframe(raw_df, item_cd=item_cd)

# For:
df = data_loader.from_csv("path/to/production.csv", item_cd=item_cd)
```

## Model Retraining Cadence

The model is static — it does not update itself. For food products with changing physical properties (viscosity drift, temperature changes):
- Retrain every shift (8h) using the most recent 50–100 batches.
- On raw material batch change: discard old data, retrain from scratch after ≥ 100 new batches.
- If viscosity is measurable, add it to `PARAM_NAMES` for better accuracy.

## Test Coverage

| File | Tests | What it guards |
|------|-------|----------------|
| test_config.py | 6 | LCL=target invariant, bounds validity, all 16 products present |
| test_data_loader.py | 6 | Column validation, cleaning, edge cases (empty, single row) |
| test_predictor.py | 6 | CV R²≥0.80, prediction near target, missing-param ValueError |
| test_recommender.py | 6 | In-spec output, improvement, max_change_pct bound |
| test_analyzer.py | 7 | Importance sums to 100%, direction validity, pct sums to 100% |

## Known Gaps (do not implement without discussion)

- `src/core/bayesian_optimizer.py` uses inverse-distance weighting, not a real Gaussian Process.
- `config.py` product definitions are hardcoded; CSV auto-loading is not implemented.
- No prediction confidence intervals — point estimates only.
- No web API layer (FastAPI dependency is present but unused).
- No time-series or drift modeling for within-shift physical property changes.
