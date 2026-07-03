"""End-to-end smoke test for the filling process optimization pipeline."""

from src.filling import synthetic_data, data_loader
from src.filling.config import PRODUCTS
from src.filling.predictor import FillWeightPredictor
from src.filling.analyzer import RootCauseAnalyzer
from src.filling.recommender import SetPointRecommender


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


if __name__ == "__main__":
    run_demo()
