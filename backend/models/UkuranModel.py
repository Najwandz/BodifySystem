from datetime import datetime
from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship
from config.database import Base


class Ukuran(Base):
    __tablename__ = "ukuran"

    id = Column(Integer, primary_key=True, index=True)
    pelanggan_id = Column(Integer, ForeignKey("pelanggan.id"), nullable=False)
    tinggi_badan_cm = Column(Float, nullable=False)
    jenis_pakaian = Column(String(20), default="kasual")

    lebar_bahu = Column(Float, nullable=False)
    lingkar_dada = Column(Float, nullable=False)
    lingkar_pinggang = Column(Float, nullable=False)
    lingkar_pinggul = Column(Float, nullable=False)
    panjang_lengan = Column(Float, nullable=False)
    panjang_badan = Column(Float, nullable=False)

    kalibrasi_regresi_aktif = Column(Boolean, default=False)
    rekomendasi_ukuran = Column(String(10), nullable=True)
    skor_kecocokan = Column(Float, nullable=True)
    catatan_penyesuaian = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    pelanggan = relationship("Pelanggan", back_populates="riwayat_ukuran")