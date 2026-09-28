"""Database abstraction layer supporting MongoDB with automatic in-memory/JSON fallback."""
from __future__ import annotations

import os
import time
import uuid
from typing import Any, Optional


class MemoryCollection:
    def __init__(self):
        self._docs: dict[str, dict] = {}

    def insert_one(self, doc: dict) -> Any:
        doc = dict(doc)
        if "_id" not in doc:
            doc["_id"] = str(uuid.uuid4())
        doc_id = str(doc["_id"])
        self._docs[doc_id] = doc
        return type("Result", (), {"inserted_id": doc_id})()

    def find_one(self, query: dict) -> Optional[dict]:
        for doc in self._docs.values():
            if self._matches(doc, query):
                return dict(doc)
        return None

    def find(self, query: dict | None = None, sort: list[tuple[str, int]] | None = None) -> list[dict]:
        query = query or {}
        results = [dict(doc) for doc in self._docs.values() if self._matches(doc, query)]
        if sort:
            for key, direction in reversed(sort):
                reverse = direction < 0
                results.sort(key=lambda x: x.get(key, 0) or 0, reverse=reverse)
        return results

    def update_one(self, query: dict, update: dict) -> Any:
        for doc_id, doc in self._docs.items():
            if self._matches(doc, query):
                if "$set" in update:
                    doc.update(update["$set"])
                if "$inc" in update:
                    for k, v in update["$inc"].items():
                        doc[k] = doc.get(k, 0) + v
                return type("Result", (), {"modified_count": 1})()
        return type("Result", (), {"modified_count": 0})()

    def delete_one(self, query: dict) -> Any:
        for doc_id, doc in list(self._docs.items()):
            if self._matches(doc, query):
                del self._docs[doc_id]
                return type("Result", (), {"deleted_count": 1})()
        return type("Result", (), {"deleted_count": 0})()

    def _matches(self, doc: dict, query: dict) -> bool:
        for k, v in query.items():
            if doc.get(k) != v:
                return False
        return True


class DatabaseManager:
    def __init__(self):
        self._mongo_client = None
        self._db = None
        self._is_mongo = False
        self._init_connection()

    def _init_connection(self):
        mongo_uri = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
        try:
            from pymongo import MongoClient
            client = MongoClient(mongo_uri, serverSelectionTimeoutMS=1000)
            client.admin.command("ping")
            self._mongo_client = client
            self._db = client.get_database(os.getenv("MONGODB_DB_NAME", "rag_chatbot"))
            self._is_mongo = True
        except Exception:
            # Fallback to Memory Collections
            self._db = {
                "users": MemoryCollection(),
                "kb_files": MemoryCollection(),
                "chat_sessions": MemoryCollection(),
                "chat_messages": MemoryCollection(),
            }
            self._is_mongo = False

    def get_collection(self, name: str):
        if self._is_mongo and self._db is not None:
            return self._db[name]
        if isinstance(self._db, dict):
            if name not in self._db:
                self._db[name] = MemoryCollection()
            return self._db[name]
        return MemoryCollection()

    @property
    def users(self):
        return self.get_collection("users")

    @property
    def kb_files(self):
        return self.get_collection("kb_files")

    @property
    def chat_sessions(self):
        return self.get_collection("chat_sessions")

    @property
    def chat_messages(self):
        return self.get_collection("chat_messages")


db = DatabaseManager()
