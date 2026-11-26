import base64
from typing import Optional
import cv2
import numpy as np
from fastapi import HTTPException
from sqlalchemy.orm import Session

from ai_pipeline.body_estimator import BodyEstimator
from controllers.SizeMatcherController import match_with_catalog
from models.PelangganModel import Pelanggan
from models.UkuranModel import Ukuran

_estimator = BodyEstimator()


def _decode_image(raw_bytes: bytes) -> np.ndarray:
    arr = np.frombuffer(raw_bytes, np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise HTTPException(status_code=400, detail="File gambar tidak valid atau rusak.")
    return img


def _encode_image_base64(img_bgr: np.ndarray) -> str:
    ok, buf = cv2.imencode(".jpg", img_bgr, [int(cv2.IMWRITE_JPEG_QUALITY), 88])
    if not ok:
        return ""
    b64 = base64.b64encode(buf.tobytes()).decode("ascii")
    return f"data:image/jpeg;base64,{b64}"


def proses_estimasi(
    db: Session,
    front_bytes: bytes,
    side_bytes: bytes,
    height_cm: float,
    clothing_type: str = "kasual",
    pelanggan_id: Optional[int] = None,
    nama_pelanggan: Optional[str] = None,
    no_hp: Optional[str] = None,
    kategori_sewa: Optional[str] = None,
) -> dict:
    """Mode lengkap 2 foto (depan & samping) + tinggi badan."""
    front_bgr = _decode_image(front_bytes)
    side_bgr = _decode_image(side_bytes)

    try:
        measurements, calibrated = _estimator.estimate(front_bgr, side_bgr, height_cm, clothing_type)
    except ValueError as err:
        raise HTTPException(status_code=422, detail=str(err))

    size_match = match_with_catalog(db, measurements, kategori=kategori_sewa)

    pelanggan = None
    if pelanggan_id:
        pelanggan = db.query(Pelanggan).filter(Pelanggan.id == pelanggan_id).first()
    elif nama_pelanggan and nama_pelanggan.strip():
        pelanggan = Pelanggan(
            nama=nama_pelanggan.strip(),
            no_hp=(no_hp or "").strip(),
            tinggi_badan_cm=height_cm,
        )
        db.add(pelanggan)
        db.commit()
        db.refresh(pelanggan)

    saved_id = None
    if pelanggan:
        pelanggan.tinggi_badan_cm = height_cm
        record = Ukuran(
            pelanggan_id=pelanggan.id,
            tinggi_badan_cm=height_cm,
            jenis_pakaian=clothing_type,
            kalibrasi_regresi_aktif=calibrated,
            rekomendasi_ukuran=size_match["rekomendasi_ukuran"],
            skor_kecocokan=size_match["skor_kecocokan"],
            catatan_penyesuaian="; ".join(size_match["catatan_penyesuaian"]),
            **measurements,
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        saved_id = record.id

    return {
        "status": "success",
        "ukuran_id": saved_id,
        "pelanggan_id": pelanggan.id if pelanggan else None,
        "kalibrasi_regresi_aktif": calibrated,
        "estimasi_ukuran_cm": measurements,
        "pencocokan_sewa": size_match,
    }


def proses_estimasi_satu_foto(
    db: Session,
    front_bytes: bytes,
    clothing_type: str = "kasual",
    nama_pelanggan: Optional[str] = None,
    no_hp: Optional[str] = None,
    kategori_sewa: Optional[str] = None,
) -> dict:
    """Mode praktis 1 foto tampak depan tanpa input tinggi badan."""
    front_bgr = _decode_image(front_bytes)

    try:
        measurements, inferred_height, pose_info = _estimator.estimate_single_photo(front_bgr, clothing_type)
    except ValueError as err:
        raise HTTPException(status_code=422, detail=str(err))

    size_match = match_with_catalog(db, measurements, kategori=kategori_sewa)
    annotated_bgr = _estimator.draw_measurement_overlay(
        front_bgr,
        measurements,
        inferred_height,
        rekomendasi_ukuran=size_match.get("rekomendasi_ukuran", "-"),
        pose_info=pose_info,
    )
    annotated_b64 = _encode_image_base64(annotated_bgr)

    saved_id = None
    pelanggan_id = None
    if nama_pelanggan and nama_pelanggan.strip():
        pelanggan = Pelanggan(
            nama=nama_pelanggan.strip(),
            no_hp=(no_hp or "").strip(),
            tinggi_badan_cm=inferred_height,
        )
        db.add(pelanggan)
        db.commit()
        db.refresh(pelanggan)
        pelanggan_id = pelanggan.id

        record = Ukuran(
            pelanggan_id=pelanggan.id,
            tinggi_badan_cm=inferred_height,
            jenis_pakaian=clothing_type,
            lebar_bahu=measurements["lebar_bahu"],
            lingkar_dada=measurements["lingkar_dada"],
            lingkar_pinggang=measurements["lingkar_pinggang"],
            lingkar_pinggul=0.0,
            panjang_lengan=0.0,
            panjang_badan=0.0,
            kalibrasi_regresi_aktif=pose_info["aruco_terdeteksi"],
            rekomendasi_ukuran=size_match["rekomendasi_ukuran"],
            skor_kecocokan=size_match["skor_kecocokan"],
            catatan_penyesuaian="; ".join(size_match["catatan_penyesuaian"]),
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        saved_id = record.id

    return {
        "status": "success",
        "mode": "single_photo_3d_rectified",
        "ukuran_id": saved_id,
        "pelanggan_id": pelanggan_id,
        "estimasi_tinggi_otomatis_cm": inferred_height,
        "info_pose": pose_info,
        "estimasi_ukuran_cm": measurements,
        "pencocokan_sewa": size_match,
        "foto_anotasi_base64": annotated_b64,
    }