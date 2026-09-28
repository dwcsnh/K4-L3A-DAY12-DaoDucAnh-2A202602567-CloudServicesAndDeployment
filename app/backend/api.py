"""API router aggregating auth, kb, and chat endpoints."""
from __future__ import annotations

from fastapi import APIRouter

from app.backend.auth import router as auth_router
from app.backend.kb import router as kb_router
from app.backend.chat import router as chat_router

api_router = APIRouter(prefix="/api")

api_router.include_router(auth_router)
api_router.include_router(kb_router)
api_router.include_router(chat_router)
