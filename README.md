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
# 1. Activate conda environment
conda activate venv

# 2. Install package (once after cloning)
pip install -e .

# 3. Run batch-mode demo (synthetic data, product 285104 — 300g cream)
python scripts/demo_filling.py

# 4. Run time-series pipeline demo (1-hour run with drift simulation)
python scripts/demo_filling.py timeseries

# 5. Run all tests
python -m pytest tests/filling/ -v
# Expected: 58 passed
```

---

## Demo Output (Batch Mode)

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
  ...
──────────────────────────────────────────────────────────────
Selected: HuberRegressor  |  n=300 batches

[3/4] Root cause analysis...
  fill_time_s         59.2%  ███████████  ↑ increases weight
  fill_pressure_bar   19.2%  ███          ↑ increases weight
  nozzle_opening_pct   9.6%  █            ↑ increases weight

[4/4] Set Point recommendation...
  Parameter               Current   Recommended   Change
  fill_time_s               1.750         1.832   +0.082
  fill_pressure_bar         1.700         1.717   +0.017
  ...
  Predicted fill weight: 300.0g  |  Status: OK ✓
```

---

## Module Reference

### config.py — Products & Parameter Bounds

```python
from src.filling.config import PRODUCTS, get_param_bounds

product = PRODUCTS["285104"]   # BK)연유크림F 300g
print(product.target_g)        # 300.0
print(product.lcl_g)           # 300.0  (always = target — food law)
print(product.ucl_g)           # 330.0

bounds = get_param_bounds(product)
# {'fill_time_s': (1.2, 2.5), 'fill_pressure_bar': (1.2, 2.5), ...}
```

**16 products** across two size classes:

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

> **Note:** These parameter names are placeholders. Real machine parameters are listed in `docs/machine_parameters.txt` and should replace `PARAM_NAMES` once real data is available.

---

### data_loader.py — Load Historical Data

```python
from src.filling import data_loader

df = data_loader.from_csv("production_history.csv", item_cd="285104")
df = data_loader.from_excel("production.xlsx", sheet="Sheet1", item_cd="285104")
df = data_loader.from_dataframe(raw_df, item_cd="285104")
data_loader.summary(df, product)
```

Required columns (case-insensitive):
```
item_cd, fill_time_s, fill_pressure_bar, product_temp_c,
nozzle_opening_pct, line_speed_bpm, fill_weight_g
```

Automatically drops rows with missing values, zero weights, and sensor outliers. Raises `ValueError` if no valid rows remain.

---

### predictor.py — Multi-Model Training & Selection

```python
from src.filling.predictor import FillWeightPredictor

predictor = FillWeightPredictor()
result = predictor.train(df, product)   # trains all 15, selects best by CV R²
predictor.print_summary()

weight = predictor.predict({
    "fill_time_s": 1.80, "fill_pressure_bar": 1.75,
    "product_temp_c": 18.0, "nozzle_opening_pct": 70.0, "line_speed_bpm": 40.0,
})  # → float (grams)

importances = predictor.feature_importances()
# {'fill_time_s': 0.59, 'fill_pressure_bar': 0.19, ...}
```

**15 candidate models:**

| Category | Models |
|----------|--------|
| Linear | LinearRegression, Ridge, Lasso, ElasticNet, HuberRegressor, BayesianRidge |
| Kernel | SVR_RBF, SVR_Poly |
| Instance | KNeighbors_5, KNeighbors_10 |
| Tree / Forest | DecisionTree, ExtraTrees, RandomForest |
| Boosting | GradientBoosting, HistGradientBoosting |

Selection: highest 5-fold CV R². Linear models typically win on synthetic data; tree models may win on real data with nonlinear material interactions.

---

### analyzer.py — Root Cause Analysis

```python
from src.filling.analyzer import RootCauseAnalyzer

analyzer = RootCauseAnalyzer(predictor, product)
result = analyzer.analyze(df)
# result["top_cause"]         → "fill_time_s"
# result["importance"]        → [("fill_time_s", 59.2), ...]
# result["direction"]         → {"fill_time_s": "↑ increases weight", ...}
# result["deviation_summary"] → {"mean_weight_g": 298.9, "low_pct": 51.3, ...}

analyzer.print_report(df)
```

Direction is determined by perturbing each parameter ±5% (clipped to valid bounds) and measuring predicted weight change.

---

### recommender.py — Set Point Optimization

```python
from src.filling.recommender import SetPointRecommender

recommender = SetPointRecommender(predictor, product)
rec = recommender.recommend(current_params, max_change_pct=0.15)
# rec["recommended_params"]             → {"fill_time_s": 1.832, ...}
# rec["recommended_predicted_weight_g"] → 300.0
# rec["weight_improvement_g"]           → 12.1
# rec["in_spec"]                        → "OK ✓"

recommender.print_report(rec)
```

**Optimization objective:**
```
minimize  (predicted_weight − target)²
        + change_cost  (penalizes changing low-importance parameters more)
        + 1000 × max(0, LCL − predicted)   ← hard constraint
        + 500  × max(0, predicted − UCL)    ← soft constraint
```

L-BFGS-B with 10 random multi-starts. Each parameter constrained to move at most `max_change_pct` (default 15%) of its operating range.

---

### synthetic_data.py — Test Data Generation

```python
from src.filling import synthetic_data

# Batch mode: one row per parameter setting
df = synthetic_data.generate("285104", n_batches=300, seed=42)
df_all = synthetic_data.generate_all(n_batches=200)

# Time-series mode: one row per second (simulates a full shift)
ts_df = synthetic_data.generate_timeseries(
    "285104",
    duration_seconds=3600,
    drift_rate_g_per_min=0.8,   # simulates viscosity thinning over a shift
    n_param_adjustments=20,
    seed=42,
)
```

Physics model:
```
weight = target × (time/nom)^0.85 × (pressure/nom)^0.30
                × (nozzle/nom)^0.20 × (nom_speed/speed)^0.10
                × (1 + 0.003 × (temp − nom_temp))
       + noise + drift
```

---

### aggregate.py — Time-Series Aggregation

Converts 1-second PLC data into stable-window batch rows compatible with `data_loader`.

```python
from src.filling import aggregate

batches = aggregate.from_timeseries(
    ts_df,
    item_cd="285104",
    lag_seconds=2,           # PLC-to-checkweigher delay (measure per machine)
    min_stable_seconds=30,   # discard transient windows
)
# Output columns: PARAM_NAMES (mean), fill_weight_g, weight_std_g,
#                 weight_min_g, weight_max_g, n_seconds, window_start, window_end

aggregate.summary(batches)
```

Key behavior:
- **Lag compensation**: shifts the weight column by `-lag_seconds` to align weight readings with the parameters that produced them
- **Change detection**: per-parameter tolerances filter out measurement noise (e.g. fill_time_s ±5ms)
- Raises `ValueError` if no windows meet `min_stable_seconds`; raises `ValueError` if `lag_seconds < 0`

---

### trend.py — Real-Time Weight Trend Monitoring

```python
from src.filling.trend import WeightTrendMonitor

monitor = WeightTrendMonitor(product, window_seconds=300, ewma_lambda=0.2)
report = monitor.analyze(ts_df)
# report["status"]                → "OK" / "WARNING" / "CRITICAL"
# report["rolling_mean_g"]        → mean over last window_seconds
# report["trend_slope_g_per_min"] → weight drift rate
# report["seconds_until_ooc"]     → seconds until LCL/UCL at current slope (None if flat / > 24h)
# report["alerts"]                → list of alert messages

monitor.print_report(report)
```

Alert thresholds:
- **CRITICAL**: rolling mean < LCL or > UCL
- **WARNING**: σ > 3% of target, or slope > ±1 g/min

---

## Time-Series Pipeline

When real PLC data arrives as 1-second rows, the full pipeline is:

```python
# 1. Monitor trends in real time
monitor = WeightTrendMonitor(product, window_seconds=300)
report = monitor.analyze(ts_df)

# 2. Aggregate to batch-level rows
batches = aggregate.from_timeseries(ts_df, item_cd="285104", lag_seconds=2)

# 3. Feed into the standard training pipeline
df = data_loader.from_dataframe(batches, item_cd="285104")
predictor.train(df, product)
analyzer.analyze(df)
recommender.recommend(current_params)
```

---

## Using Real Production Data

**Batch data** (one row per batch):
```python
df = data_loader.from_csv("production_log.csv", item_cd="285104")
```

**Time-series data** (one row per second):
```python
batches = aggregate.from_timeseries(
    ts_df, item_cd="285104",
    lag_seconds=2,         # adjust to your machine's actual delay
    min_stable_seconds=30,
)
df = data_loader.from_dataframe(batches, item_cd="285104")
```

Minimum recommended dataset: **≥ 100 batches** per product (300+ for stable recommendations).

---

## Retraining Cadence

| Situation | Recommendation |
|-----------|---------------|
| Slow viscosity drift within shift | Retrain every 1–2h using most recent 50–100 batches |
| Daily raw material change | Retrain at shift start using previous day's data |
| Sudden raw material batch change | Discard old data; retrain from scratch after ≥ 100 new batches |
| Viscosity measurable by instrument | Add it to `PARAM_NAMES` for significantly better accuracy |

---

## Testing

```powershell
python -m pytest tests/filling/ -v
```

| Test file | Tests | Scope |
|-----------|-------|-------|
| test_config.py | 6 | Product configs, LCL=target invariant, bounds |
| test_data_loader.py | 6 | Loading, cleaning, edge cases |
| test_predictor.py | 6 | CV R²≥0.80, predictions, error handling |
| test_recommender.py | 5 | In-spec output, max_change constraint |
| test_analyzer.py | 7 | Importance sums, direction validity |
| test_aggregate.py | 11 | Window aggregation, lag, short-window filter, loader compat |
| test_trend.py | 17 | CRITICAL/WARNING alerts, slope, OOC prediction, edge cases |
| **Total** | **58** | |

---

## Adding a New Product

1. Add a `ProductConfig` to `PRODUCTS` in `src/filling/config.py`:
   ```python
   "999999": ProductConfig("999999", "New Product 500g", 500, 500, 520.0, dict(_NOMINAL_SMALL)),
   ```
2. Add the item code to `TARGET_ITEM_CDS` in `tests/filling/test_config.py`.
3. Verify: `python -m pytest tests/filling/test_config.py -v`

---

## Known Limitations

| Area | Status |
|------|--------|
| Parameter names | Placeholders; map to actual machine parameters when real data arrives |
| Product config source | 16 products hardcoded; `data/raw/MST_ITEM_*.csv` not auto-loaded |
| Prediction uncertainty | Point estimates only; no confidence intervals |
| Web API | FastAPI dependency included but not implemented |

---

## Project Structure

```
src/filling/       core filling optimization modules (8 files)
src/core/          generic Bayesian optimizer (injection molding origin)
scripts/           runnable demos (batch + time-series)
tests/filling/     58 unit tests across 7 files
data/raw/          raw product master data (CSV)
docs/              machine parameter reference, product list
```

See [PROJECT_SUMMARY.md](PROJECT_SUMMARY.md) for a detailed module-by-module breakdown.

---

## License

MIT License — See LICENSE file.
