"""Authentication module: registration, login, password hashing, and JWT tokens."""
from __future__ import annotations

import os
import time
import uuid
import bcrypt
import jwt
from fastapi import APIRouter, Depends, HTTPException, Header, status
from pydantic import BaseModel, Field

from app.backend.db import db

JWT_SECRET = os.getenv("JWT_SECRET", "super-secret-rag-jwt-key-2026-production-ready-32b")
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_SECONDS = 7 * 24 * 3600  # 7 days
DEFAULT_USAGE_LIMIT = int(os.getenv("DEFAULT_USAGE_LIMIT", "100"))

router = APIRouter(prefix="/auth", tags=["auth"])


class AuthRequest(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=6, max_length=100)


class UserResponse(BaseModel):
    id: str
    username: str
    usage_limit: int
    usage_used: int
    created_at: float


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


def hash_password(password: str) -> str:
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except Exception:
        return False


def create_token(user_id: str, username: str) -> str:
    payload = {
        "sub": user_id,
        "username": username,
        "exp": int(time.time()) + JWT_EXPIRATION_SECONDS,
        "iat": int(time.time()),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def get_current_user(authorization: str | None = Header(default=None)) -> dict:
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Thiếu header Authorization",
            headers={"WWW-Authenticate": "Bearer"},
        )
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Header Authorization không hợp lệ (phải có dạng 'Bearer <token>')",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = parts[1]
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token không hợp lệ")
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token đã hết hạn")
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token không hợp lệ hoặc bị lỗi")

    user = db.users.find_one({"_id": user_id})
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Người dùng không tồn tại")

    return user


@router.post("/register", response_model=AuthResponse)
def register(req: AuthRequest):
    normalized_username = req.username.strip().lower()
    existing = db.users.find_one({"username": normalized_username})
    if existing:
        raise HTTPException(status_code=400, detail="Tên người dùng đã tồn tại")

    user_id = str(uuid.uuid4())
    user_doc = {
        "_id": user_id,
        "username": normalized_username,
        "password_hash": hash_password(req.password),
        "usage_limit": DEFAULT_USAGE_LIMIT,
        "usage_used": 0,
        "created_at": time.time(),
    }
    db.users.insert_one(user_doc)
    token = create_token(user_id, normalized_username)
    return AuthResponse(
        access_token=token,
        user=UserResponse(
            id=user_id,
            username=normalized_username,
            usage_limit=user_doc["usage_limit"],
            usage_used=user_doc["usage_used"],
            created_at=user_doc["created_at"],
        ),
    )


@router.post("/login", response_model=AuthResponse)
def login(req: AuthRequest):
    normalized_username = req.username.strip().lower()
    user = db.users.find_one({"username": normalized_username})
    if not user or not verify_password(req.password, user.get("password_hash", "")):
        raise HTTPException(status_code=401, detail="Sai tên người dùng hoặc mật khẩu")

    user_id = str(user["_id"])
    token = create_token(user_id, normalized_username)
    return AuthResponse(
        access_token=token,
        user=UserResponse(
            id=user_id,
            username=normalized_username,
            usage_limit=user.get("usage_limit", DEFAULT_USAGE_LIMIT),
            usage_used=user.get("usage_used", 0),
            created_at=user.get("created_at", time.time()),
        ),
    )


@router.get("/me", response_model=UserResponse)
def get_me(user: dict = Depends(get_current_user)):
    return UserResponse(
        id=str(user["_id"]),
        username=user["username"],
        usage_limit=user.get("usage_limit", DEFAULT_USAGE_LIMIT),
        usage_used=user.get("usage_used", 0),
        created_at=user.get("created_at", time.time()),
    )
