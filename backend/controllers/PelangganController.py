import csv
import io
from fastapi import HTTPException
from sqlalchemy.orm import Session
from models.PelangganModel import Pelanggan
from models.UkuranModel import Ukuran


def list_pelanggan(db: Session):
    customers = db.query(Pelanggan).order_by(Pelanggan.created_at.desc()).all()
    results = []
    for c in customers:
        latest = (
            db.query(Ukuran)
            .filter(Ukuran.pelanggan_id == c.id)
            .order_by(Ukuran.created_at.desc())
            .first()
        )
        results.append({
            "id": c.id,
            "nama": c.nama,
            "no_hp": c.no_hp,
            "jenis_kelamin": c.jenis_kelamin,
            "tinggi_badan_cm": c.tinggi_badan_cm,
            "remote_token": c.remote_token,
            "ukuran_terakhir": {
                "lebar_bahu": latest.lebar_bahu,
                "lingkar_dada": latest.lingkar_dada,
                "lingkar_pinggang": latest.lingkar_pinggang,
                "lingkar_pinggul": latest.lingkar_pinggul,
                "panjang_lengan": latest.panjang_lengan,
                "panjang_badan": latest.panjang_badan,
                "rekomendasi_ukuran": latest.rekomendasi_ukuran,
                "tanggal": latest.created_at.isoformat(),
            } if latest else None,
        })
    return results


def create_pelanggan(db: Session, nama: str, no_hp: str = "", jenis_kelamin: str = "Perempuan", tinggi_badan_cm: float = None):
    pelanggan = Pelanggan(
        nama=nama,
        no_hp=no_hp,
        jenis_kelamin=jenis_kelamin,
        tinggi_badan_cm=tinggi_badan_cm,
    )
    db.add(pelanggan)
    db.commit()
    db.refresh(pelanggan)
    return pelanggan


def get_riwayat_pelanggan(db: Session, pelanggan_id: int):
    pelanggan = db.query(Pelanggan).filter(Pelanggan.id == pelanggan_id).first()
    if not pelanggan:
        raise HTTPException(status_code=404, detail="Data pelanggan tidak ditemukan.")
    riwayat = (
        db.query(Ukuran)
        .filter(Ukuran.pelanggan_id == pelanggan_id)
        .order_by(Ukuran.created_at.desc())
        .all()
    )
    return {"pelanggan": pelanggan, "riwayat": riwayat}


def export_riwayat_csv(db: Session) -> str:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "ID", "Nama Pelanggan", "No HP", "Tanggal", "Tinggi (cm)", "Pakaian",
        "Lebar Bahu", "Lingkar Dada", "Lingkar Pinggang", "Lingkar Pinggul",
        "Panjang Lengan", "Panjang Badan", "Rekomendasi Sewa",
    ])
    records = db.query(Ukuran).order_by(Ukuran.created_at.desc()).all()
    for r in records:
        writer.writerow([
            r.id, r.pelanggan.nama, r.pelanggan.no_hp or "-", r.created_at.strftime("%Y-%m-%d %H:%M"),
            r.tinggi_badan_cm, r.jenis_pakaian, r.lebar_bahu, r.lingkar_dada,
            r.lingkar_pinggang, r.lingkar_pinggul, r.panjang_lengan, r.panjang_badan,
            r.rekomendasi_ukuran or "-",
        ])
    return output.getvalue()