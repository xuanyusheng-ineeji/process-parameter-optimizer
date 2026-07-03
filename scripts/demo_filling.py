"""End-to-end smoke test for the filling process optimization pipeline.

Two demos:
  run_demo()            — batch-level historical data (default)
  run_timeseries_demo() — full time-series pipeline (aggregate → optimize + monitor)
"""

from src.filling import synthetic_data, data_loader, aggregate
from src.filling.config import PRODUCTS, PARAM_NAMES
from src.filling.predictor import FillWeightPredictor
from src.filling.analyzer import RootCauseAnalyzer
from src.filling.recommender import SetPointRecommender
from src.filling.trend import WeightTrendMonitor


def run_demo(item_cd: str = "285104") -> None:
    product = PRODUCTS[item_cd]

    print(f"\n{'='*60}")
    print(f"FILLING PROCESS OPTIMIZER — {product.item_nm}")
    print(f"Target: {product.target_g}g  LCL: {product.lcl_g}g  UCL: {product.ucl_g}g")
    print(f"{'='*60}\n")

    # ── Step 1: Load historical data (synthetic for now) ───────────────────
    print("[1/4] Generating synthetic historical data...")
    raw_df = synthetic_data.generate(item_cd, n_batches=300, seed=42)
    df = data_loader.from_dataframe(raw_df, item_cd=item_cd)
    data_loader.summary(df, product)

    # ── Step 2: Train prediction model ─────────────────────────────────────
    print("\n[2/4] Training fill-weight prediction model...")
    predictor = FillWeightPredictor()
    predictor.train(df, product)
    predictor.print_summary()

    # ── Step 3: Root cause analysis ────────────────────────────────────────
    print("\n[3/4] Running root cause analysis...")
    analyzer = RootCauseAnalyzer(predictor, product)
    analyzer.print_report(df)

    # ── Step 4: Recommend new Set Points ───────────────────────────────────
    print("\n[4/4] Generating Set Point recommendations...")
    current_params = {
        "fill_time_s":        1.75,
        "fill_pressure_bar":  1.70,
        "product_temp_c":     22.0,
        "nozzle_opening_pct": 68.0,
        "line_speed_bpm":     42.0,
    }
    recommender = SetPointRecommender(predictor, product)
    rec = recommender.recommend(current_params)
    recommender.print_report(rec)


def run_timeseries_demo(item_cd: str = "285104") -> None:
    """
    Full time-series pipeline demo.

    1. Generate 1-second synthetic PLC data (1 hour run with drift)
    2. Aggregate stable windows  → batch-level rows
    3. Train predictor on aggregated batches
    4. Root cause analysis + Set Point recommendation
    5. Real-time trend monitoring report
    """
    product = PRODUCTS[item_cd]

    print(f"\n{'='*60}")
    print(f"TIME-SERIES PIPELINE DEMO - {product.item_nm}")
    print(f"Target: {product.target_g}g  LCL: {product.lcl_g}g  UCL: {product.ucl_g}g")
    print(f"{'='*60}\n")

    # ── Step 1: Generate 1-second time-series data ─────────────────────────
    print("[1/6] Generating 1-hour synthetic time-series (1s resolution)...")
    ts_df = synthetic_data.generate_timeseries(
        item_cd,
        duration_seconds=3600,
        seed=42,
        drift_rate_g_per_min=0.8,   # viscosity thinning → weight creeping up
        n_param_adjustments=20,
    )
    print(f"      {len(ts_df):,} rows  ({ts_df['timestamp'].min()} → {ts_df['timestamp'].max()})")

    # ── Step 2: Trend monitoring on raw time-series ────────────────────────
    print("\n[2/6] Real-time weight trend monitoring (last 5 min window)...")
    monitor = WeightTrendMonitor(product, window_seconds=300, ewma_lambda=0.2)
    trend_report = monitor.analyze(ts_df)
    monitor.print_report(trend_report)

    # ── Step 3: Aggregate to stable parameter windows ──────────────────────
    print("\n[3/6] Aggregating time-series into stable parameter windows...")
    batches = aggregate.from_timeseries(
        ts_df,
        item_cd=item_cd,
        lag_seconds=2,
        min_stable_seconds=30,
    )
    aggregate.summary(batches)

    # ── Step 4: Load and train ─────────────────────────────────────────────
    print("\n[4/6] Loading aggregated batches and training model...")
    df = data_loader.from_dataframe(batches, item_cd=item_cd)
    data_loader.summary(df, product)

    predictor = FillWeightPredictor()
    predictor.train(df, product)
    predictor.print_summary()

    # ── Step 5: Root cause analysis ────────────────────────────────────────
    print("\n[5/6] Root cause analysis on aggregated data...")
    analyzer = RootCauseAnalyzer(predictor, product)
    analyzer.print_report(df)

    # ── Step 6: Recommend Set Points ───────────────────────────────────────
    print("\n[6/6] Generating Set Point recommendations...")
    # Use the last row's parameters as the current machine state
    last_row = batches.iloc[-1]
    current_params = {p: float(last_row[p]) for p in PARAM_NAMES}

    print("  Current parameters (from last stable window):")
    for p, v in current_params.items():
        print(f"    {p}: {v:.4g}")

    recommender = SetPointRecommender(predictor, product)
    rec = recommender.recommend(current_params)
    recommender.print_report(rec)


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "timeseries":
        run_timeseries_demo()
    else:
        run_demo()
