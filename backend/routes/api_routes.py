from typing import Optional
from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from config.database import get_db
from controllers.AuthController import login_user
from controllers.EstimasiController import proses_estimasi, proses_estimasi_satu_foto
from controllers.PelangganController import (
    create_pelanggan,
    export_riwayat_csv,
    get_riwayat_pelanggan,
    list_pelanggan,
)
from models.KatalogSewaModel import KatalogSewa
from models.PelangganModel import Pelanggan

router = APIRouter(prefix="/api/v1")


class LoginPayload(BaseModel):
    username: str
    password: str


class PelangganPayload(BaseModel):
    nama: str
    no_hp: Optional[str] = ""
    jenis_kelamin: Optional[str] = "Perempuan"
    tinggi_badan_cm: Optional[float] = None


class KatalogPayload(BaseModel):
    nama_busana: str
    kategori: str
    ukuran_label: str
    dada_min: float
    dada_max: float
    pinggang_min: float
    pinggang_max: float
    pinggul_min: float
    pinggul_max: float
    bahu_min: float
    bahu_max: float
    stok: int = 1


@router.post("/auth/login")
def api_login(payload: LoginPayload, db: Session = Depends(get_db)):
    return login_user(db, payload.username, payload.password)


@router.post("/estimate-single")
async def api_estimate_single(
    front_image: UploadFile = File(...),
    clothing_type: str = Form("kasual"),
    nama_pelanggan: Optional[str] = Form(None),
    no_hp: Optional[str] = Form(None),
    kategori_sewa: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    return proses_estimasi_satu_foto(
        db=db,
        front_bytes=await front_image.read(),
        clothing_type=clothing_type,
        nama_pelanggan=nama_pelanggan,
        no_hp=no_hp,
        kategori_sewa=kategori_sewa,
    )


@router.post("/estimate")
async def api_estimate(
    front_image: UploadFile = File(...),
    side_image: UploadFile = File(...),
    height_cm: float = Form(..., ge=100.0, le=230.0),
    clothing_type: str = Form("kasual"),
    pelanggan_id: Optional[int] = Form(None),
    nama_pelanggan: Optional[str] = Form(None),
    no_hp: Optional[str] = Form(None),
    kategori_sewa: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    return proses_estimasi(
        db=db,
        front_bytes=await front_image.read(),
        side_bytes=await side_image.read(),
        height_cm=height_cm,
        clothing_type=clothing_type,
        pelanggan_id=pelanggan_id,
        nama_pelanggan=nama_pelanggan,
        no_hp=no_hp,
        kategori_sewa=kategori_sewa,
    )


@router.get("/pelanggan")
def api_list_pelanggan(db: Session = Depends(get_db)):
    return list_pelanggan(db)


@router.post("/pelanggan")
def api_create_pelanggan(payload: PelangganPayload, db: Session = Depends(get_db)):
    p = create_pelanggan(db, payload.nama, payload.no_hp, payload.jenis_kelamin, payload.tinggi_badan_cm)
    return {"id": p.id, "nama": p.nama, "remote_token": p.remote_token}


@router.get("/pelanggan/{pelanggan_id}/riwayat")
def api_riwayat_pelanggan(pelanggan_id: int, db: Session = Depends(get_db)):
    return get_riwayat_pelanggan(db, pelanggan_id)


@router.get("/pelanggan/export/csv")
def api_export_csv(db: Session = Depends(get_db)):
    csv_data = export_riwayat_csv(db)
    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=riwayat_ukuran_bodify.csv"},
    )


@router.get("/remote/{remote_token}")
def api_get_remote_info(remote_token: str, db: Session = Depends(get_db)):
    pelanggan = db.query(Pelanggan).filter(Pelanggan.remote_token == remote_token).first()
    if not pelanggan:
        raise HTTPException(status_code=404, detail="Tautan ukur mandiri tidak valid.")
    return {"id": pelanggan.id, "nama": pelanggan.nama, "tinggi_badan_cm": pelanggan.tinggi_badan_cm}


@router.post("/remote/{remote_token}/estimate")
async def api_remote_estimate(
    remote_token: str,
    front_image: UploadFile = File(...),
    side_image: UploadFile = File(...),
    height_cm: float = Form(..., ge=100.0, le=230.0),
    clothing_type: str = Form("kasual"),
    db: Session = Depends(get_db),
):
    pelanggan = db.query(Pelanggan).filter(Pelanggan.remote_token == remote_token).first()
    if not pelanggan:
        raise HTTPException(status_code=404, detail="Tautan ukur mandiri tidak valid.")
    return proses_estimasi(
        db=db,
        front_bytes=await front_image.read(),
        side_bytes=await side_image.read(),
        height_cm=height_cm,
        clothing_type=clothing_type,
        pelanggan_id=pelanggan.id,
    )


@router.get("/katalog")
def api_list_katalog(db: Session = Depends(get_db)):
    return db.query(KatalogSewa).all()


@router.post("/katalog")
def api_add_katalog(payload: KatalogPayload, db: Session = Depends(get_db)):
    item = KatalogSewa(**payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.delete("/katalog/{item_id}")
def api_delete_katalog(item_id: int, db: Session = Depends(get_db)):
    item = db.query(KatalogSewa).filter(KatalogSewa.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item katalog tidak ditemukan.")
    db.delete(item)
    db.commit()
    return {"status": "deleted"}