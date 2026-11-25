from typing import Dict, List
from sqlalchemy.orm import Session
from models.KatalogSewaModel import KatalogSewa

STANDARD_SIZE_CHART = [
    {"size": "S",   "dada": (82, 88),   "pinggang": (64, 72),  "bahu": (37, 40)},
    {"size": "M",   "dada": (89, 95),   "pinggang": (73, 79),  "bahu": (40, 43)},
    {"size": "L",   "dada": (96, 103),  "pinggang": (80, 87),  "bahu": (43, 46)},
    {"size": "XL",  "dada": (104, 112), "pinggang": (88, 96),  "bahu": (46, 49)},
    {"size": "XXL", "dada": (113, 122), "pinggang": (97, 106), "bahu": (49, 53)},
]


def _determine_standard_size(measurements: Dict[str, float]) -> Dict:
    """Menentukan ukuran standar (S-XXL) berdasarkan dimensi terbesar agar baju tidak sempit."""
    best = None
    lowest_penalty = float("inf")

    for entry in STANDARD_SIZE_CHART:
        penalty = 0.0
        notes = []
        checks = [
            ("lingkar_dada", entry["dada"], 0.45),
            ("lingkar_pinggang", entry["pinggang"], 0.35),
            ("lebar_bahu", entry["bahu"], 0.20),
        ]
        for key, (low, high), weight in checks:
            val = measurements.get(key, 0.0)
            if val <= 0:
                continue
            if val < low:
                diff = low - val
                penalty += diff * weight * 0.7
                if diff > 3.0:
                    notes.append(f"{key.replace('_', ' ')} agak longgar ±{diff:.1f} cm")
            elif val > high:
                diff = val - high
                # Penalti berat jika kekecilan supaya otomatis naik ke ukuran yang muat
                penalty += diff * weight * 3.2
                notes.append(f"{key.replace('_', ' ')} sempit ±{diff:.1f} cm")

        score = round(max(0.0, 100.0 - penalty * 4.5), 1)
        if penalty < lowest_penalty:
            lowest_penalty = penalty
            best = {
                "rekomendasi_ukuran": entry["size"],
                "skor_kecocokan": score,
                "catatan_penyesuaian": notes if notes else ["Ukuran pas sesuai standar."],
            }
    return best


def match_with_catalog(db: Session, measurements: Dict[str, float], kategori: str = None) -> Dict:
    std_result = _determine_standard_size(measurements)

    query = db.query(KatalogSewa).filter(KatalogSewa.stok > 0)
    if kategori and kategori.strip() and kategori.strip().lower() != "string":
        query = query.filter(KatalogSewa.kategori.ilike(f"%{kategori.strip()}%"))
    items = query.all()

    matched_items: List[Dict] = []
    for item in items:
        if item.ukuran_label.upper() == std_result["rekomendasi_ukuran"]:
            matched_items.append({
                "id": item.id,
                "nama_busana": item.nama_busana,
                "kategori": item.kategori,
                "ukuran_label": item.ukuran_label,
                "stok": item.stok,
                "skor_kecocokan": std_result["skor_kecocokan"],
            })

    return {
        "rekomendasi_ukuran": std_result["rekomendasi_ukuran"],
        "skor_kecocokan": std_result["skor_kecocokan"],
        "catatan_penyesuaian": std_result["catatan_penyesuaian"],
        "rekomendasi_busana": matched_items,
    }