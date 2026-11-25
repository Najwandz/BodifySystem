from sqlalchemy import Column, Float, Integer, String
from config.database import Base


class KatalogSewa(Base):
    __tablename__ = "katalog_sewa"

    id = Column(Integer, primary_key=True, index=True)
    nama_busana = Column(String(120), nullable=False)
    kategori = Column(String(50), nullable=False)  # Kebaya, Jas Formal, Gaun Wisuda, Pengantin
    ukuran_label = Column(String(10), nullable=False)  # S, M, L, XL
    dada_min = Column(Float, nullable=False)
    dada_max = Column(Float, nullable=False)
    pinggang_min = Column(Float, nullable=False)
    pinggang_max = Column(Float, nullable=False)
    pinggul_min = Column(Float, nullable=False)
    pinggul_max = Column(Float, nullable=False)
    bahu_min = Column(Float, nullable=False)
    bahu_max = Column(Float, nullable=False)
    stok = Column(Integer, default=1)