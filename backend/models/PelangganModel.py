import uuid
from datetime import datetime
from sqlalchemy import Column, DateTime, Float, Integer, String
from sqlalchemy.orm import relationship
from config.database import Base


class Pelanggan(Base):
    __tablename__ = "pelanggan"

    id = Column(Integer, primary_key=True, index=True)
    nama = Column(String(100), nullable=False)
    no_hp = Column(String(25), nullable=True)
    jenis_kelamin = Column(String(15), default="Perempuan")
    tinggi_badan_cm = Column(Float, nullable=True)
    remote_token = Column(String(36), unique=True, index=True, default=lambda: uuid.uuid4().hex[:12])
    created_at = Column(DateTime, default=datetime.utcnow)

    riwayat_ukuran = relationship("Ukuran", back_populates="pelanggan", cascade="all, delete-orphan")