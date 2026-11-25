import sys
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error
from sklearn.model_selection import KFold, cross_val_predict
from sklearn.multioutput import MultiOutputRegressor
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

# Pastikan modul dari folder backend/ dapat diimpor langsung
sys.path.append(str(Path(__file__).resolve().parent.parent))
from config.settings import CALIBRATION_CSV_PATH, CALIBRATION_MODEL_PATH, TARGET_MEASUREMENTS

FEATURE_COLS = ["height_cm", "clothing_code"] + [f"raw_{m}" for m in TARGET_MEASUREMENTS]
TARGET_COLS = [f"true_{m}" for m in TARGET_MEASUREMENTS]


def create_simulation_dataset(n_samples: int = 50, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    heights = rng.uniform(150, 182, n_samples)
    cloth = rng.integers(0, 3, n_samples)

    true_bahu = 0.25 * heights + rng.normal(0, 1.8, n_samples)
    true_dada = 0.54 * heights + rng.normal(0, 4.5, n_samples)
    true_pinggang = 0.45 * heights + rng.normal(0, 4.8, n_samples)
    true_pinggul = 0.56 * heights + rng.normal(0, 4.0, n_samples)
    true_lengan = 0.34 * heights + rng.normal(0, 1.5, n_samples)
    true_badan = 0.38 * heights + rng.normal(0, 1.6, n_samples)

    offset = cloth * 1.6
    return pd.DataFrame({
        "height_cm": heights,
        "clothing_code": cloth,
        "raw_lebar_bahu": true_bahu + 0.5 * offset + rng.normal(0.4, 0.7, n_samples),
        "raw_lingkar_dada": true_dada + 1.4 * offset + rng.normal(1.2, 1.1, n_samples),
        "raw_lingkar_pinggang": true_pinggang + 1.5 * offset + rng.normal(1.5, 1.2, n_samples),
        "raw_lingkar_pinggul": true_pinggul + 1.2 * offset + rng.normal(1.0, 1.0, n_samples),
        "raw_panjang_lengan": true_lengan + rng.normal(-0.5, 0.8, n_samples),
        "raw_panjang_badan": true_badan + rng.normal(0.3, 0.8, n_samples),
        "true_lebar_bahu": true_bahu,
        "true_lingkar_dada": true_dada,
        "true_lingkar_pinggang": true_pinggang,
        "true_lingkar_pinggul": true_pinggul,
        "true_panjang_lengan": true_lengan,
        "true_panjang_badan": true_badan,
    })


def train():
    if CALIBRATION_CSV_PATH.exists():
        df = pd.read_csv(CALIBRATION_CSV_PATH)
        print(f"Memuat dataset lapangan: {CALIBRATION_CSV_PATH} ({len(df)} partisipan)")
    else:
        df = create_simulation_dataset(n_samples=50)
        CALIBRATION_CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(CALIBRATION_CSV_PATH, index=False)
        print(f"Dataset simulasi (50 partisipan) dibuat di: {CALIBRATION_CSV_PATH}")

    X = df[FEATURE_COLS].values
    y = df[TARGET_COLS].values

    models = {
        "Ridge Regression": Pipeline([("scaler", StandardScaler()), ("reg", Ridge(alpha=1.5))]),
        "Random Forest": MultiOutputRegressor(
            RandomForestRegressor(n_estimators=200, max_depth=8, random_state=42)
        ),
    }

    kf = KFold(n_splits=5, shuffle=True, random_state=42)
    best_name, best_model, best_mae = None, None, float("inf")

    for name, model in models.items():
        preds = cross_val_predict(model, X, y, cv=kf)
        avg_mae = mean_absolute_error(y, preds)
        print(f"\n=== 5-Fold CV: {name} ===")
        for idx, metric in enumerate(TARGET_MEASUREMENTS):
            col_mae = mean_absolute_error(y[:, idx], preds[:, idx])
            status = "PASS" if col_mae <= 2.0 else "PERLU KALIBRASI"
            print(f"  - {metric:<18}: MAE = {col_mae:.2f} cm [{status}]")
        print(f"  > MAE Rata-rata: {avg_mae:.2f} cm")

        if avg_mae < best_mae:
            best_mae, best_name, best_model = avg_mae, name, model

    best_model.fit(X, y)
    CALIBRATION_MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(best_model, CALIBRATION_MODEL_PATH)
    print(f"\nModel terbaik ({best_name}, MAE={best_mae:.2f} cm) disimpan ke: {CALIBRATION_MODEL_PATH}")


if __name__ == "__main__":
    train()