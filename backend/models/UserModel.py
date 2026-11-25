from datetime import datetime
from sqlalchemy import Column, DateTime, Integer, String
from config.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    nama_lengkap = Column(String(100), nullable=False)
    password_hash = Column(String(128), nullable=False)
    role = Column(String(20), default="staf")  # admin | staf
    created_at = Column(DateTime, default=datetime.utcnow)