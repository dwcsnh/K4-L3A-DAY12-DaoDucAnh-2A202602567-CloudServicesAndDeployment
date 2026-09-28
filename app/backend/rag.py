"""RAG retrieval and generation engine with citations and OpenAI/Mock LLM support."""
from __future__ import annotations

import os
import re
from typing import Any
import httpx

from app.backend.db import db
from utils.mock_llm import ask_llm


def retrieve_relevant_chunks(user_id: str, query: str, top_k: int = 4) -> list[dict]:
    """Tìm kiếm các đoạn tài liệu phù hợp nhất với câu hỏi từ KB của người dùng."""
    files = db.kb_files.find({"user_id": user_id})
    all_chunks: list[dict] = []
    for file_doc in files:
        f_id = str(file_doc["_id"])
        f_name = file_doc["filename"]
        for c in file_doc.get("chunks", []):
            all_chunks.append({
                "file_id": f_id,
                "filename": f_name,
                "section": c.get("section", "Nội dung"),
                "content": c.get("content", ""),
            })

    if not all_chunks:
        return []

    # Simple BM25 / token matching scoring
    query_tokens = set(re.findall(r"\w+", query.lower()))
    if not query_tokens:
        return all_chunks[:top_k]

    scored_chunks = []
    for chunk in all_chunks:
        text = (chunk["section"] + " " + chunk["content"]).lower()
        chunk_tokens = re.findall(r"\w+", text)
        score = 0
        for token in query_tokens:
            count = chunk_tokens.count(token)
            if count > 0:
                score += 1.0 + (count * 0.5)
        if score > 0:
            scored_chunks.append((score, chunk))

    scored_chunks.sort(key=lambda x: x[0], reverse=True)
    if scored_chunks:
        return [chunk for _, chunk in scored_chunks[:top_k]]
    return all_chunks[:top_k]


def build_rag_prompt(query: str, chunks: list[dict]) -> tuple[str, list[dict]]:
    """Tạo prompt kèm ngữ cảnh từ KB và danh sách trích dẫn (citations)."""
    citations = []
    context_parts = []

    for i, c in enumerate(chunks, start=1):
        snippet = c["content"][:200].strip() + ("..." if len(c["content"]) > 200 else "")
        citations.append({
            "citation_id": f"ref-{i}",
            "file_id": c["file_id"],
            "filename": c["filename"],
            "section": c["section"],
            "snippet": snippet,
        })
        context_parts.append(
            f"[Nguồn {i} - File: {c['filename']} | Phần: {c['section']}]:\n{c['content']}"
        )

    context_str = "\n\n".join(context_parts)
    prompt = (
        f"Bạn là trợ lý AI thông minh hỗ trợ trả lời câu hỏi dựa trên tài liệu người dùng đã tải lên.\n\n"
        f"TÀI LIỆU THAM KHẢO:\n{context_str}\n\n"
        f"CÂU HỎI CỦA NGƯỜI DÙNG: {query}\n\n"
        f"HƯỚNG DẪN: Trả lời chính xác, dễ hiểu dựa trên tài liệu được cung cấp. "
        f"Nếu thông tin có trong tài liệu, hãy chỉ rõ tên tài liệu và phần tương ứng."
    )
    return prompt, citations


def generate_rag_answer(query: str, user_id: str, history: list[dict] | None = None) -> dict[str, Any]:
    """Truy xuất tài liệu từ KB, tạo ngữ cảnh và sinh câu trả lời kèm trích dẫn."""
    chunks = retrieve_relevant_chunks(user_id, query)
    history = history or []

    if chunks:
        prompt, citations = build_rag_prompt(query, chunks)
    else:
        prompt = query
        citations = []

    # Check for OpenAI API Key
    openai_key = os.getenv("OPENAI_API_KEY")
    if openai_key and not openai_key.startswith("sk-placeholder") and not openai_key.startswith("mock"):
        try:
            return _call_openai(prompt, history, citations)
        except Exception:
            pass

    # Seamless fallback to mock LLM
    mock_result = ask_llm(prompt, history)
    answer = mock_result["answer"]
    if citations:
        answer = f"Dựa trên các tài liệu đã tải lên ({', '.join({c['filename'] for c in citations})}):\n\n" + answer

    return {
        "answer": answer,
        "citations": citations,
        "tokens_in": mock_result.get("tokens_in", 50),
        "tokens_out": mock_result.get("tokens_out", 120),
        "cost_usd": mock_result.get("cost_usd", 0.0001),
    }


def _call_openai(prompt: str, history: list[dict], citations: list[dict]) -> dict:
    url = "https://api.openai.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {os.getenv('OPENAI_API_KEY')}",
        "Content-Type": "application/json",
    }
    messages = [{"role": "system", "content": "Bạn là trợ lý AI trả lời câu hỏi dựa trên tài liệu."}]
    for h in history[-6:]:
        messages.append({"role": h.get("role", "user"), "content": h.get("content", "")})
    messages.append({"role": "user", "content": prompt})

    with httpx.Client(timeout=30.0) as client:
        resp = client.post(
            url,
            headers=headers,
            json={"model": os.getenv("OPENAI_MODEL", "gpt-4o-mini"), "messages": messages, "temperature": 0.3},
        )
        resp.raise_for_status()
        data = resp.json()
        answer = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
        return {
            "answer": answer,
            "citations": citations,
            "tokens_in": usage.get("prompt_tokens", 100),
            "tokens_out": usage.get("completion_tokens", 150),
            "cost_usd": 0.0002,
        }
