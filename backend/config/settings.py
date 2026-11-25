import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# Default SQLite agar langsung jalan; ganti ke URL PostgreSQL/MySQL saat produksi
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'bodify.db'}")

CALIBRATION_MODEL_PATH = BASE_DIR / "saved_models" / "calibration_model.pkl"
CALIBRATION_CSV_PATH = BASE_DIR / "training" / "dataset_kalibrasi.csv"

CORS_ORIGINS = ["*"]

TARGET_MEASUREMENTS = [
    "lebar_bahu",
    "lingkar_dada",
    "lingkar_pinggang",
    "lingkar_pinggul",
    "panjang_lengan",
    "panjang_badan",
]

CLOTHING_ENCODING = {
    "ketat": 0,
    "kasual": 1,
    "longgar": 2,
}