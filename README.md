# Process Parameter Optimizer

**Language / 语言 / 언어:** [English](README.md) · [中文](README.zh-CN.md) · [한국어](README.ko.md)

---

**AI-assisted Set Point recommendation system for food factory filling lines**

Analyzes historical production data, identifies root causes of fill weight deviation, and recommends equipment parameter adjustments — without touching the PLC.

---

## The Challenge

Food filling lines run 5+ interdependent parameters simultaneously. When fill weight drifts out of spec, engineers face:

- **Underfill risk** — legal violation; every gram below target is non-compliant
- **Manual guesswork** — adjusting one parameter at a time while production runs
- **Experience dependency** — optimal settings live in a few people's heads
- **Slow feedback loop** — hours of off-spec product before the cause is found

Result: scrap, rework, and legal exposure from underfilled product.

## Solution

This system turns historical batch data into actionable Set Point recommendations:

```
Historical Data (parameters + fill weights)
            ↓
    AI Model Training
   (15 models → auto-select best)
            ↓
   Root Cause Analysis
   (which parameter drives deviation, and which direction)
            ↓
   Set Point Recommendation
   (constrained optimization — minimal, targeted adjustments)
            ↓
   Engineer Reviews → Enters into PLC/HMI
            ↓
       Next production batch
```

**The system does not automate PLC control.** Output is a recommendation for the engineer to review and apply.

---

## Quick Start

```powershell
# 1. Activate your conda environment
conda activate venv

# 2. Install package (once after cloning)
pip install -e .

# 3. Run end-to-end demo (synthetic data, product 285104 — 300g cream)
python scripts/demo_filling.py

# 4. Run tests
python -m pytest tests/filling/ -v
```

Expected test result: **30 passed**

---

## Demo Output

```
============================================================
FILLING PROCESS OPTIMIZER — BK)연유크림F 300g
Target: 300g  LCL: 300g  UCL: 330.0g
============================================================

[2/4] Training fill-weight prediction model...
──────────────────────────────────────────────────────────────
Model                     CV R²      ±  Train σ (g)
──────────────────────────────────────────────────────────────
★ HuberRegressor          0.996  0.001       1.05g ◀
  LinearRegression        0.996  0.001       1.05g
  GradientBoosting        0.950  0.037       0.55g
  RandomForest            0.903  0.063       2.07g
  SVR_RBF                 0.753  0.124       6.44g
  ...
──────────────────────────────────────────────────────────────
Selected: HuberRegressor  |  n=300 batches

[3/4] Root cause analysis...
  fill_time_s         59.2%  ███████████  ↑ increases weight
  fill_pressure_bar   19.2%  ███          ↑ increases weight
  nozzle_opening_pct   9.6%  █            ↑ increases weight

[4/4] Set Point recommendation...
  Parameter               Current   Recommended   Change
  fill_time_s               1.750         1.832   +0.082  ← main lever
  fill_pressure_bar         1.700         1.717   +0.017
  ...

  Predicted fill weight: 300.0g  |  Status: OK ✓
```

---

## Module Reference

### config.py — Products & Parameter Bounds

```python
from src.filling.config import PRODUCTS, get_param_bounds, get_size_class

product = PRODUCTS["285104"]   # BK)연유크림F 300g
print(product.target_g)        # 300.0
print(product.lcl_g)           # 300.0  (always = target — food law)
print(product.ucl_g)           # 330.0

bounds = get_param_bounds(product)
# {'fill_time_s': (1.2, 2.5), 'fill_pressure_bar': (1.2, 2.5), ...}
```

**16 products** configured across two size classes:

| Size class | Target range | Products |
|------------|-------------|---------|
| small | 200 – 500 g | 282113, 284023, 284047, 284059, 284535, 284760, 284961, 285101–285104 |
| medium | > 500 g (up to 3 kg) | 284235, 284319, 284516, 284573, 374424 |

**5 machine parameters (PARAM_NAMES):**

| Parameter | Unit | Small range | Medium range |
|-----------|------|------------|-------------|
| `fill_time_s` | s | 1.2 – 2.5 | 3.0 – 5.5 |
| `fill_pressure_bar` | bar | 1.2 – 2.5 | 1.8 – 3.2 |
| `product_temp_c` | °C | 8 – 28 | 8 – 28 |
| `nozzle_opening_pct` | % | 50 – 90 | 55 – 95 |
| `line_speed_bpm` | packs/min | 25 – 55 | 12 – 28 |

> **Note:** These parameter names are placeholders. Real machine parameters (pump inverter speed, correction outputs, etc.) are listed in `docs/machine_parameters.txt` and should replace `PARAM_NAMES` once real data is available.

---

### data_loader.py — Load Historical Data

```python
from src.filling import data_loader

# From CSV
df = data_loader.from_csv("production_history.csv", item_cd="285104")

# From Excel
df = data_loader.from_excel("production.xlsx", sheet="Sheet1", item_cd="285104")

# From DataFrame
df = data_loader.from_dataframe(raw_df, item_cd="285104")

# Print summary statistics and spec compliance
data_loader.summary(df, product)
```

Required columns (case-insensitive):
```
item_cd, fill_time_s, fill_pressure_bar, product_temp_c,
nozzle_opening_pct, line_speed_bpm, fill_weight_g
```

The loader automatically drops rows with missing values, zero weights, and out-of-range sensor values. Raises `ValueError` if no valid rows remain after cleaning.

---

### predictor.py — Multi-Model Training & Selection

Trains 15 candidate models simultaneously and selects the highest CV R² automatically.

```python
from src.filling.predictor import FillWeightPredictor

predictor = FillWeightPredictor()
predictor.train(df, product)          # trains all 15, selects best
predictor.print_summary()             # show ranked comparison table

weight = predictor.predict({
    "fill_time_s": 1.80,
    "fill_pressure_bar": 1.75,
    "product_temp_c": 18.0,
    "nozzle_opening_pct": 70.0,
    "line_speed_bpm": 40.0,
})  # → float (grams)

importances = predictor.feature_importances()
# {'fill_time_s': 0.59, 'fill_pressure_bar': 0.19, ...}
```

**Candidate models:**

| Category | Models |
|----------|--------|
| Linear | LinearRegression, Ridge, Lasso, ElasticNet, HuberRegressor, BayesianRidge |
| Kernel | SVR (RBF), SVR (Polynomial) |
| Instance | KNeighbors (k=5), KNeighbors (k=10) |
| Tree / Forest | DecisionTree, ExtraTrees, RandomForest |
| Boosting | GradientBoosting, HistGradientBoosting |

Selection rule: highest 5-fold cross-validation R². In food filling scenarios, linear models typically win (fill weight responds nearly linearly to parameter changes). Tree models may outperform on real data with nonlinear material interactions.

---

### analyzer.py — Root Cause Analysis

```python
from src.filling.analyzer import RootCauseAnalyzer

analyzer = RootCauseAnalyzer(predictor, product)

result = analyzer.analyze(df)
# result["top_cause"]      → "fill_time_s"
# result["importance"]     → [("fill_time_s", 59.2), ("fill_pressure_bar", 19.2), ...]
# result["direction"]      → {"fill_time_s": "↑ increases weight", ...}
# result["deviation_summary"] → {"mean_weight_g": 298.9, "low_pct": 51.3, ...}

analyzer.print_report(df)   # formatted console output
```

Direction is determined by perturbing each parameter ±5% (clipped to valid bounds) and measuring the predicted weight change.

---

### recommender.py — Set Point Optimization

```python
from src.filling.recommender import SetPointRecommender

recommender = SetPointRecommender(predictor, product)

current_params = {
    "fill_time_s":        1.75,
    "fill_pressure_bar":  1.70,
    "product_temp_c":     22.0,
    "nozzle_opening_pct": 68.0,
    "line_speed_bpm":     42.0,
}

rec = recommender.recommend(current_params, max_change_pct=0.15)
# rec["recommended_params"]           → {"fill_time_s": 1.832, ...}
# rec["recommended_predicted_weight_g"] → 300.0
# rec["weight_improvement_g"]         → 12.1
# rec["in_spec"]                      → "OK ✓"

recommender.print_report(rec)
```

**Optimization objective:**
```
minimize  (predicted_weight − target)²
        + change_cost  (penalizes changing low-importance parameters more)
        + 1000 × max(0, LCL − predicted)   ← hard constraint
        + 500  × max(0, predicted − UCL)    ← soft constraint
```

Parameters are constrained to move at most `max_change_pct` (default 15%) of their operating range from the current value. L-BFGS-B with 10 random multi-starts is used to avoid local minima.

---

### synthetic_data.py — Test Data Generation

For development and testing before real production data is available.

```python
from src.filling import synthetic_data

# Single product, 300 batches
df = synthetic_data.generate("285104", n_batches=300, seed=42)

# All 16 products combined
df_all = synthetic_data.generate_all(n_batches=200, seed=42)
```

Physics model used for weight simulation:
```
weight = target × (time/nom)^0.85 × (pressure/nom)^0.30
                × (nozzle/nom)^0.20 × (nom_speed/speed)^0.10
                × (1 + 0.003 × (temp − nom_temp))
       + noise(±0.3% for small packs, ±0.15% for large)
```

---

## Using Real Production Data

Replace the synthetic data lines in `scripts/demo_filling.py`:

```python
# Before (synthetic):
raw_df = synthetic_data.generate(item_cd, n_batches=300, seed=42)
df = data_loader.from_dataframe(raw_df, item_cd=item_cd)

# After (real CSV):
df = data_loader.from_csv("path/to/production_log.csv", item_cd=item_cd)
```

Minimum recommended dataset: **≥ 100 batches** per product for reliable model training. More data (300+) improves model stability and recommendation quality.

---

## Optimization Strategy

Adapted from the general parameter optimization workflow:

1. **Collect baseline data** — Run production normally for 1–2 shifts; record all parameters and fill weights.

2. **Train the model** — `predictor.train(df, product)` selects the best-fit model automatically.

3. **Identify root cause** — `analyzer.analyze(df)` ranks parameters by influence and tells you which direction to move each.

4. **Generate recommendations** — `recommender.recommend(current_params)` computes the minimal parameter adjustment to bring weight to target.

5. **Apply and validate** — Engineer enters recommended values into HMI, runs next batch, measures actual weight, repeats if needed.

6. **Retrain periodically** — Physical properties (viscosity, temperature) drift over time. Retrain the model:
   - Every shift (8h) for fast-changing products
   - Daily for stable products using previous day's data
   - Immediately after raw material batch changes (discard old data, retrain from scratch with ≥ 100 new batches)

---

## Core Module (Generic Bayesian Optimizer)

`src/core/` contains a general-purpose Bayesian optimizer originally built for injection molding — kept as a reference and reusable foundation for experimental-trial scenarios (small data, expensive measurements).

```python
from src.core.bayesian_optimizer import BayesianOptimizer, ParameterSpace, ExperimentResult

optimizer = BayesianOptimizer(
    parameter_space=params_space,
    objective_weights={'quality': 0.5, 'cycle_time': 0.3, 'energy': 0.2}
)

for iteration in range(20):
    params = optimizer.suggest_next_parameters()[0]   # EI acquisition
    result = ExperimentResult(parameters=params, quality_score=..., ...)
    optimizer.update(result)

optimal = optimizer.get_optimal_parameters()
```

Uses Expected Improvement (EI) acquisition function:
```
EI(x) = (μ(x) − f_best) × Φ(Z) + σ(x) × φ(Z),  where Z = (μ(x) − f_best) / σ(x)
```

> **Note:** The current GP prediction uses inverse-distance weighting as a placeholder rather than a full Gaussian Process. Suitable for exploration but uncertainty estimates are approximate.

---

## Adding a New Product

1. Add a `ProductConfig` entry to `PRODUCTS` in `src/filling/config.py`:
   ```python
   "999999": ProductConfig(
       item_cd="999999",
       item_nm="New Product 500g",
       target_g=500,
       lcl_g=500,       # must equal target_g
       ucl_g=520.0,
       nominal_params=dict(_NOMINAL_SMALL),
   ),
   ```

2. Add the item code to `TARGET_ITEM_CDS` in `tests/filling/test_config.py`.

3. Verify: `python -m pytest tests/filling/test_config.py -v`

---

## Testing

```powershell
# Run all filling tests
python -m pytest tests/filling/ -v

# Run a single test file
python -m pytest tests/filling/test_predictor.py -v
```

| Test file | Tests | Scope |
|-----------|-------|-------|
| test_config.py | 6 | Product configs, LCL=target invariant, bounds |
| test_data_loader.py | 6 | Loading, cleaning, edge cases |
| test_predictor.py | 6 | CV R²≥0.80, predictions, error handling |
| test_recommender.py | 6 | In-spec output, max_change constraint |
| test_analyzer.py | 7 | Importance sums, direction validity |
| **Total** | **30** | |

---

## Known Limitations

| Area | Status |
|------|--------|
| Parameter names | Placeholder names; map to actual machine parameters when real data arrives |
| Product config source | 16 products are hardcoded; `data/raw/MST_ITEM_*.csv` is not auto-loaded |
| Physical property drift | No time-series modeling; mitigate by retraining frequently |
| Prediction uncertainty | Point estimates only; no confidence intervals |
| Web API | FastAPI dependency included but not implemented |

---

## Project Structure

```
src/filling/       core filling optimization modules
src/core/          generic Bayesian optimizer (injection molding origin)
scripts/           runnable demos
tests/filling/     30 unit tests
data/raw/          raw product master data (CSV)
docs/              machine parameter reference, product list
```

See [PROJECT_SUMMARY.md](PROJECT_SUMMARY.md) for a detailed module-by-module breakdown.

---

## License

MIT License — See LICENSE file.
