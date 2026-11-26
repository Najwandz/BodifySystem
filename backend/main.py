from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from config.database import Base, SessionLocal, engine
from config.settings import CORS_ORIGINS
from controllers.AuthController import hash_password
from models.KatalogSewaModel import KatalogSewa
from models.PelangganModel import Pelanggan  # noqa: F401
from models.UkuranModel import Ukuran  # noqa: F401
from models.UserModel import User
from routes.api_routes import router

Base.metadata.create_all(bind=engine)


def seed_initial_data():
    db = SessionLocal()
    try:
        if db.query(User).count() == 0:
            db.add(User(
                username="admin",
                nama_lengkap="Admin Mitra Penjahit",
                password_hash=hash_password("admin123"),
                role="admin",
            ))

        if db.query(KatalogSewa).count() == 0:
            sample_catalog = [
                KatalogSewa(nama_busana="Kebaya Brokat Wisuda", kategori="Kebaya", ukuran_label="S", dada_min=82, dada_max=88, pinggang_min=64, pinggang_max=70, pinggul_min=88, pinggul_max=94, bahu_min=37, bahu_max=40, stok=3),
                KatalogSewa(nama_busana="Kebaya Brokat Wisuda", kategori="Kebaya", ukuran_label="M", dada_min=89, dada_max=95, pinggang_min=71, pinggang_max=77, pinggul_min=95, pinggul_max=101, bahu_min=40, bahu_max=43, stok=4),
                KatalogSewa(nama_busana="Jas Formal Wool Hitam", kategori="Jas Formal", ukuran_label="L", dada_min=96, dada_max=103, pinggang_min=78, pinggang_max=85, pinggul_min=102, pinggul_max=109, bahu_min=43, bahu_max=46, stok=5),
                KatalogSewa(nama_busana="Gaun Pengantin Modern", kategori="Pengantin", ukuran_label="XL", dada_min=104, dada_max=112, pinggang_min=86, pinggang_max=94, pinggul_min=110, pinggul_max=118, bahu_min=46, bahu_max=49, stok=2),
            ]
            db.add_all(sample_catalog)
        db.commit()
    finally:
        db.close()


seed_initial_data()

app = FastAPI(title="BodifySystem API - Estimasi Ukuran Tubuh Tanpa Sentuh", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def block_disabled_features(request: Request, call_next):
    path = request.url.path.lower()
    if path.startswith("/api/") and ("katalog" in path or "remote" in path):
        return JSONResponse(status_code=404, content={"detail": "Fitur tidak tersedia."})
    return await call_next(request)


app.include_router(router)


@app.get("/api/health")
def health_check():
    return {"service": "BodifySystem Backend", "status": "running"}


FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend-pwa"
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")