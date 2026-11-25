from pathlib import Path
from typing import Dict, Tuple
import joblib
import numpy as np

from config.settings import CALIBRATION_MODEL_PATH, CLOTHING_ENCODING, TARGET_MEASUREMENTS


class RegressionCorrector:
    """Memuat model Ridge/Random Forest untuk koreksi bias ketebalan pakaian kasual."""

    def __init__(self, model_path: Path = CALIBRATION_MODEL_PATH):
        self.model = joblib.load(model_path) if Path(model_path).exists() else None

    def apply(
        self,
        raw_measurements: Dict[str, float],
        height_cm: float,
        clothing_type: str = "kasual",
    ) -> Tuple[Dict[str, float], bool]:
        if self.model is None:
            return {k: round(float(v), 2) for k, v in raw_measurements.items()}, False

        cloth_code = CLOTHING_ENCODING.get(clothing_type.lower(), 1)
        features = np.array([[
            height_cm,
            cloth_code,
            raw_measurements["lebar_bahu"],
            raw_measurements["lingkar_dada"],
            raw_measurements["lingkar_pinggang"],
            raw_measurements["lingkar_pinggul"],
            raw_measurements["panjang_lengan"],
            raw_measurements["panjang_badan"],
        ]])
        corrected_vec = self.model.predict(features)[0]
        result = {
            metric: round(float(corrected_vec[idx]), 2)
            for idx, metric in enumerate(TARGET_MEASUREMENTS)
        }
        return result, True