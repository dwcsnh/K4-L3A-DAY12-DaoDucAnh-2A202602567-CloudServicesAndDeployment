"""Chat session and messaging module with rate limiting, usage guard, and conversation history."""
from __future__ import annotations

import time
import uuid
from typing import Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.backend.auth import get_current_user
from app.backend.db import db
from app.backend.rag import generate_rag_answer

router = APIRouter(prefix="/chat", tags=["chat"])

# In-memory sliding window rate limiter per user (fallback if Redis is not configured)
_USER_RATE_TIMESTAMPS: dict[str, list[float]] = {}
RATE_LIMIT_PER_MINUTE = 15


def check_user_rate_limit(user_id: str) -> None:
    now = time.time()
    timestamps = _USER_RATE_TIMESTAMPS.setdefault(user_id, [])
    # Filter out entries older than 60s
    timestamps[:] = [t for t in timestamps if now - t < 60]
    if len(timestamps) >= RATE_LIMIT_PER_MINUTE:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Vượt quá hạn mức gửi tin nhắn ({RATE_LIMIT_PER_MINUTE} tin/phút). Vui lòng đợi trong giây lát.",
            headers={"Retry-After": "60"},
        )
    timestamps.append(now)


class CreateSessionRequest(BaseModel):
    title: Optional[str] = "Hội thoại mới"


class SessionItem(BaseModel):
    id: str
    title: str
    created_at: float
    updated_at: float


class SendMessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=4000)


class CitationItem(BaseModel):
    citation_id: str
    file_id: str
    filename: str
    section: str
    snippet: str


class MessageItem(BaseModel):
    id: str
    session_id: str
    role: str
    content: str
    citations: list[CitationItem] = []
    created_at: float


class ChatResponse(BaseModel):
    user_message: MessageItem
    assistant_message: MessageItem
    usage_used: int
    usage_limit: int


@router.get("/sessions", response_model=list[SessionItem])
def list_sessions(current_user: dict = Depends(get_current_user)):
    user_id = str(current_user["_id"])
    docs = db.chat_sessions.find({"user_id": user_id}, sort=[("updated_at", -1)])
    return [
        SessionItem(
            id=str(d["_id"]),
            title=d.get("title", "Hội thoại mới"),
            created_at=d.get("created_at", time.time()),
            updated_at=d.get("updated_at", time.time()),
        )
        for d in docs
    ]


@router.post("/sessions", response_model=SessionItem)
def create_session(
    req: CreateSessionRequest,
    current_user: dict = Depends(get_current_user),
):
    user_id = str(current_user["_id"])
    session_id = str(uuid.uuid4())
    now = time.time()
    session_doc = {
        "_id": session_id,
        "user_id": user_id,
        "title": req.title or "Hội thoại mới",
        "created_at": now,
        "updated_at": now,
    }
    db.chat_sessions.insert_one(session_doc)
    return SessionItem(
        id=session_id,
        title=session_doc["title"],
        created_at=now,
        updated_at=now,
    )


@router.delete("/sessions/{session_id}")
def delete_session(session_id: str, current_user: dict = Depends(get_current_user)):
    user_id = str(current_user["_id"])
    session = db.chat_sessions.find_one({"_id": session_id, "user_id": user_id})
    if not session:
        raise HTTPException(status_code=404, detail="Không tìm thấy phiên chat")

    db.chat_sessions.delete_one({"_id": session_id, "user_id": user_id})
    # Also delete associated messages
    messages = db.chat_messages.find({"session_id": session_id})
    for m in messages:
        db.chat_messages.delete_one({"_id": m["_id"]})

    return {"message": "Đã xóa phiên chat", "session_id": session_id}


@router.get("/sessions/{session_id}/messages", response_model=list[MessageItem])
def get_session_messages(session_id: str, current_user: dict = Depends(get_current_user)):
    user_id = str(current_user["_id"])
    session = db.chat_sessions.find_one({"_id": session_id, "user_id": user_id})
    if not session:
        raise HTTPException(status_code=404, detail="Không tìm thấy phiên chat")

    docs = db.chat_messages.find({"session_id": session_id}, sort=[("created_at", 1)])
    return [
        MessageItem(
            id=str(d["_id"]),
            session_id=session_id,
            role=d.get("role", "user"),
            content=d.get("content", ""),
            citations=d.get("citations", []),
            created_at=d.get("created_at", time.time()),
        )
        for d in docs
    ]


@router.post("/sessions/{session_id}/messages", response_model=ChatResponse)
def send_message(
    session_id: str,
    req: SendMessageRequest,
    current_user: dict = Depends(get_current_user),
):
    user_id = str(current_user["_id"])
    session = db.chat_sessions.find_one({"_id": session_id, "user_id": user_id})
    if not session:
        raise HTTPException(status_code=404, detail="Không tìm thấy phiên chat")

    # 1. Rate Limiting Check
    check_user_rate_limit(user_id)

    # 2. Usage Limit Check
    usage_limit = current_user.get("usage_limit", 100)
    usage_used = current_user.get("usage_used", 0)
    if usage_used >= usage_limit:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=f"Bạn đã sử dụng hết hạn mức cho phép ({usage_used}/{usage_limit} tin nhắn). Vui lòng nâng cấp gói hoặc liên hệ quản trị viên.",
        )

    # 3. Fetch conversation history for session
    previous_messages = db.chat_messages.find({"session_id": session_id}, sort=[("created_at", 1)])
    history = [{"role": m["role"], "content": m["content"]} for m in previous_messages]

    # 4. Generate RAG answer with citations
    rag_result = generate_rag_answer(req.content, user_id=user_id, history=history)

    now = time.time()
    user_msg_id = str(uuid.uuid4())
    user_msg_doc = {
        "_id": user_msg_id,
        "session_id": session_id,
        "user_id": user_id,
        "role": "user",
        "content": req.content,
        "citations": [],
        "created_at": now,
    }
    db.chat_messages.insert_one(user_msg_doc)

    assistant_msg_id = str(uuid.uuid4())
    citations_data = rag_result.get("citations", [])
    assistant_msg_doc = {
        "_id": assistant_msg_id,
        "session_id": session_id,
        "user_id": user_id,
        "role": "assistant",
        "content": rag_result["answer"],
        "citations": citations_data,
        "created_at": now + 0.1,
    }
    db.chat_messages.insert_one(assistant_msg_doc)

    # 5. Increment user usage limit count
    new_usage = usage_used + 1
    db.users.update_one({"_id": user_id}, {"$inc": {"usage_used": 1}})

    # 6. Update session title if default
    if session.get("title") == "Hội thoại mới" and len(previous_messages) == 0:
        short_title = req.content[:30] + ("..." if len(req.content) > 30 else "")
        db.chat_sessions.update_one({"_id": session_id}, {"$set": {"title": short_title, "updated_at": now}})
    else:
        db.chat_sessions.update_one({"_id": session_id}, {"$set": {"updated_at": now}})

    return ChatResponse(
        user_message=MessageItem(
            id=user_msg_id,
            session_id=session_id,
            role="user",
            content=req.content,
            citations=[],
            created_at=now,
        ),
        assistant_message=MessageItem(
            id=assistant_msg_id,
            session_id=session_id,
            role="assistant",
            content=rag_result["answer"],
            citations=citations_data,
            created_at=now + 0.1,
        ),
        usage_used=new_usage,
        usage_limit=usage_limit,
    )
