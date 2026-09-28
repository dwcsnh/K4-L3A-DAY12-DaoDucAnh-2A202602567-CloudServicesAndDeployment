"""Standalone FastAPI application for RAG Chatbot Backend."""
from __future__ import annotations

import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.backend.api import api_router

app = FastAPI(
    title="RAG Chatbot API",
    description="Backend API for Knowledge Base management, RAG search, and chat",
    version="1.0.0",
)

allowed_origins = os.getenv("ALLOWED_ORIGINS", "*").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.get("/")
def root():
    return {
        "service": "RAG Chatbot Backend",
        "status": "online",
        "docs_url": "/docs",
    }


@app.get("/health")
def health():
    return {"status": "ok", "service": "rag-chatbot-backend"}


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("app.backend.main:app", host="0.0.0.0", port=port, reload=True)
