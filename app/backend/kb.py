"""Knowledge Base management module: upload, ingest to md, view, download, delete."""
from __future__ import annotations

import os
import shutil
import time
import uuid
from pathlib import Path
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.backend.auth import get_current_user
from app.backend.db import db
from app.backend.ingest.parser import chunk_markdown, is_allowed_file, parse_file_to_markdown

STORAGE_DIR = Path(os.getenv("STORAGE_DIR", "./storage/uploads"))
router = APIRouter(prefix="/kb", tags=["kb"])


class KBFileItem(BaseModel):
    id: str
    filename: str
    file_type: str
    size_bytes: int
    chunks_count: int
    created_at: float


class KBFileDetail(BaseModel):
    id: str
    filename: str
    file_type: str
    size_bytes: int
    chunks_count: int
    created_at: float
    markdown_content: str
    chunks: list[dict]


@router.post("/upload", response_model=KBFileItem)
async def upload_file(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
):
    filename = file.filename or "uploaded_file"
    if not is_allowed_file(filename):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Định dạng file không được phép. Chỉ chấp nhận các định dạng: .pdf, .txt, .docx",
        )

    user_id = str(current_user["_id"])
    user_upload_dir = STORAGE_DIR / user_id
    user_upload_dir.mkdir(parents=True, exist_ok=True)

    file_id = str(uuid.uuid4())
    ext = Path(filename).suffix.lower()
    stored_filename = f"{file_id}_{filename}"
    file_path = user_upload_dir / stored_filename

    # Save original file
    with file_path.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    size_bytes = file_path.stat().st_size

    # Ingest file to Markdown
    try:
        markdown_text = parse_file_to_markdown(file_path)
    except Exception as e:
        if file_path.exists():
            file_path.unlink()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Lỗi khi xử lý và chuyển đổi file sang Markdown: {e}",
        )

    # Save Markdown file
    md_filename = f"{file_id}_{Path(filename).stem}.md"
    md_path = user_upload_dir / md_filename
    md_path.write_text(markdown_text, encoding="utf-8")

    # Chunk markdown for RAG
    chunks = chunk_markdown(markdown_text)

    # Save metadata in DB
    kb_doc = {
        "_id": file_id,
        "user_id": user_id,
        "filename": filename,
        "file_type": ext.lstrip("."),
        "size_bytes": size_bytes,
        "file_path": str(file_path),
        "md_path": str(md_path),
        "chunks": chunks,
        "created_at": time.time(),
    }
    db.kb_files.insert_one(kb_doc)

    return KBFileItem(
        id=file_id,
        filename=filename,
        file_type=ext.lstrip("."),
        size_bytes=size_bytes,
        chunks_count=len(chunks),
        created_at=kb_doc["created_at"],
    )


@router.get("/files", response_model=list[KBFileItem])
def list_files(current_user: dict = Depends(get_current_user)):
    user_id = str(current_user["_id"])
    docs = db.kb_files.find({"user_id": user_id}, sort=[("created_at", -1)])
    return [
        KBFileItem(
            id=str(doc["_id"]),
            filename=doc["filename"],
            file_type=doc.get("file_type", "unknown"),
            size_bytes=doc.get("size_bytes", 0),
            chunks_count=len(doc.get("chunks", [])),
            created_at=doc.get("created_at", time.time()),
        )
        for doc in docs
    ]


@router.get("/files/{file_id}", response_model=KBFileDetail)
def get_file_detail(file_id: str, current_user: dict = Depends(get_current_user)):
    user_id = str(current_user["_id"])
    doc = db.kb_files.find_one({"_id": file_id, "user_id": user_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Không tìm thấy tài liệu")

    md_path = Path(doc.get("md_path", ""))
    markdown_content = ""
    if md_path.exists():
        markdown_content = md_path.read_text(encoding="utf-8", errors="replace")

    return KBFileDetail(
        id=str(doc["_id"]),
        filename=doc["filename"],
        file_type=doc.get("file_type", "unknown"),
        size_bytes=doc.get("size_bytes", 0),
        chunks_count=len(doc.get("chunks", [])),
        created_at=doc.get("created_at", time.time()),
        markdown_content=markdown_content,
        chunks=doc.get("chunks", []),
    )


@router.get("/files/{file_id}/download")
def download_file(file_id: str, current_user: dict = Depends(get_current_user)):
    user_id = str(current_user["_id"])
    doc = db.kb_files.find_one({"_id": file_id, "user_id": user_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Không tìm thấy tài liệu")

    file_path = Path(doc.get("file_path", ""))
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File vật lý không tồn tại trên hệ thống")

    return FileResponse(
        path=str(file_path),
        filename=doc["filename"],
        media_type="application/octet-stream",
    )


@router.delete("/files/{file_id}")
def delete_file(file_id: str, current_user: dict = Depends(get_current_user)):
    user_id = str(current_user["_id"])
    doc = db.kb_files.find_one({"_id": file_id, "user_id": user_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Không tìm thấy tài liệu")

    # Delete physical files
    for p_key in ("file_path", "md_path"):
        p = Path(doc.get(p_key, ""))
        if p.exists():
            try:
                p.unlink()
            except Exception:
                pass

    db.kb_files.delete_one({"_id": file_id, "user_id": user_id})
    return {"message": "Đã xóa tài liệu thành công", "file_id": file_id}
