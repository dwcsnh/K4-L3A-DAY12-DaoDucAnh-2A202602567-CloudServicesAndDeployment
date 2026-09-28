"""Tests for RAG Chatbot backend: auth, KB management, file validation, RAG citations, rate limiting, and usage limit."""
from __future__ import annotations

import io
import uuid
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app, raise_server_exceptions=False)


def test_auth_register_and_login():
    uid = uuid.uuid4().hex[:8]
    username = f"user_{uid}"
    password = "password12345"

    # Register
    res = client.post("/api/auth/register", json={"username": username, "password": password})
    assert res.status_code == 200, res.text
    data = res.json()
    assert "access_token" in data
    assert data["user"]["username"] == username
    assert data["user"]["usage_limit"] > 0
    assert data["user"]["usage_used"] == 0

    token = data["access_token"]

    # Duplicate register -> 400
    res_dup = client.post("/api/auth/register", json={"username": username, "password": password})
    assert res_dup.status_code == 400

    # Login
    res_login = client.post("/api/auth/login", json={"username": username, "password": password})
    assert res_login.status_code == 200
    assert "access_token" in res_login.json()

    # Get me
    res_me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert res_me.status_code == 200
    assert res_me.json()["username"] == username


def test_unauthenticated_kb_access():
    res = client.get("/api/kb/files")
    assert res.status_code == 401


def test_upload_disallowed_file_rejected():
    # Register/login user
    u = f"user_{uuid.uuid4().hex[:8]}"
    reg = client.post("/api/auth/register", json={"username": u, "password": "pass12345"}).json()
    token = reg["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Upload .exe or .py file
    file_payload = {"file": ("malicious.exe", b"binarycontent", "application/octet-stream")}
    res = client.post("/api/kb/upload", headers=headers, files=file_payload)
    assert res.status_code == 400
    assert "Chỉ chấp nhận các định dạng" in res.json()["detail"]


def test_kb_upload_txt_and_operations():
    u = f"user_{uuid.uuid4().hex[:8]}"
    reg = client.post("/api/auth/register", json={"username": u, "password": "pass12345"}).json()
    token = reg["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    sample_text = (
        "# Kiến trúc Cloud\n\n"
        "Cloud Computing cung cấp tài nguyên tính toán theo nhu cầu qua mạng Internet.\n\n"
        "## Lợi ích\n\n"
        "Khả năng mở rộng linh hoạt, chi phí tối ưu theo lượng sử dụng."
    )
    file_payload = {"file": ("cloud_doc.txt", sample_text.encode("utf-8"), "text/plain")}
    res_up = client.post("/api/kb/upload", headers=headers, files=file_payload)
    assert res_up.status_code == 200, res_up.text
    doc = res_up.json()
    file_id = doc["id"]
    assert doc["filename"] == "cloud_doc.txt"
    assert doc["file_type"] == "txt"
    assert doc["chunks_count"] >= 1

    # List files
    res_list = client.get("/api/kb/files", headers=headers)
    assert res_list.status_code == 200
    files = res_list.json()
    assert any(f["id"] == file_id for f in files)

    # Get detail
    res_detail = client.get(f"/api/kb/files/{file_id}", headers=headers)
    assert res_detail.status_code == 200
    detail = res_detail.json()
    assert "Cloud Computing" in detail["markdown_content"]
    assert len(detail["chunks"]) >= 1

    # Download
    res_dl = client.get(f"/api/kb/files/{file_id}/download", headers=headers)
    assert res_dl.status_code == 200
    assert b"Cloud Computing" in res_dl.content

    # Delete
    res_del = client.delete(f"/api/kb/files/{file_id}", headers=headers)
    assert res_del.status_code == 200

    # Verify deleted
    res_get_del = client.get(f"/api/kb/files/{file_id}", headers=headers)
    assert res_get_del.status_code == 404


def test_chat_session_and_rag_with_citations():
    u = f"user_{uuid.uuid4().hex[:8]}"
    reg = client.post("/api/auth/register", json={"username": u, "password": "pass12345"}).json()
    token = reg["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Upload document
    kb_content = (
        "# Hướng dẫn bảo mật Docker\n\n"
        "## Non-root user\n\n"
        "Chạy container với user appuser để tránh lỗ hổng leo thang đặc quyền root trên máy host.\n\n"
        "## Multi-stage build\n\n"
        "Tách builder stage và runtime stage giúp giảm dung lượng image dưới 200MB."
    )
    client.post("/api/kb/upload", headers=headers, files={"file": ("docker_security.txt", kb_content.encode("utf-8"), "text/plain")})

    # Create chat session
    res_session = client.post("/api/chat/sessions", headers=headers, json={"title": "Hỏi về Docker"})
    assert res_session.status_code == 200
    session_id = res_session.json()["id"]

    # Send chat question
    res_msg = client.post(
        f"/api/chat/sessions/{session_id}/messages",
        headers=headers,
        json={"content": "Tại sao cần chạy container bằng non-root user?"},
    )
    assert res_msg.status_code == 200, res_msg.text
    chat_data = res_msg.json()

    assert chat_data["user_message"]["role"] == "user"
    assert chat_data["assistant_message"]["role"] == "assistant"
    assert len(chat_data["assistant_message"]["content"]) > 0
    # Citations returned
    assert len(chat_data["assistant_message"]["citations"]) >= 1
    citation = chat_data["assistant_message"]["citations"][0]
    assert citation["filename"] == "docker_security.txt"
    assert "Non-root" in citation["section"] or "Docker" in citation["snippet"]
    assert chat_data["usage_used"] == 1

    # Verify message history stored
    res_hist = client.get(f"/api/chat/sessions/{session_id}/messages", headers=headers)
    assert res_hist.status_code == 200
    messages = res_hist.json()
    assert len(messages) == 2  # 1 user + 1 assistant


def test_user_usage_limit_enforced():
    from app.backend.db import db
    u = f"user_{uuid.uuid4().hex[:8]}"
    reg = client.post("/api/auth/register", json={"username": u, "password": "pass12345"}).json()
    token = reg["access_token"]
    user_id = reg["user"]["id"]
    headers = {"Authorization": f"Bearer {token}"}

    # Set usage_used = usage_limit
    db.users.update_one({"_id": user_id}, {"$set": {"usage_used": 100, "usage_limit": 100}})

    res_session = client.post("/api/chat/sessions", headers=headers, json={"title": "Test Limit"})
    session_id = res_session.json()["id"]

    res_msg = client.post(
        f"/api/chat/sessions/{session_id}/messages",
        headers=headers,
        json={"content": "Câu hỏi khi đã hết quota"},
    )
    assert res_msg.status_code == 402  # Payment Required / usage limit exceeded
