import hashlib
import secrets
from fastapi import HTTPException
from sqlalchemy.orm import Session
from models.UserModel import User


def hash_password(password: str) -> str:
    return hashlib.sha256(f"bodify_salt::{password}".encode("utf-8")).hexdigest()


def login_user(db: Session, username: str, password: str) -> dict:
    user = db.query(User).filter(User.username == username).first()
    if not user or user.password_hash != hash_password(password):
        raise HTTPException(status_code=401, detail="Username atau password salah.")

    return {
        "token": secrets.token_hex(24),
        "user": {
            "id": user.id,
            "username": user.username,
            "nama_lengkap": user.nama_lengkap,
            "role": user.role,
        },
    }