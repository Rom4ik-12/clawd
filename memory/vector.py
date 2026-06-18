"""
memory/vector.py — Векторная память через ChromaDB
"""
import logging
import os
from config import VECTOR_DB_PATH

logger = logging.getLogger("vector")
_collection = None


def _get_collection():
    global _collection
    if _collection is not None:
        return _collection
    try:
        import chromadb
        from chromadb.utils import embedding_functions
        client = chromadb.PersistentClient(path=VECTOR_DB_PATH)
        ef = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name="paraphrase-multilingual-MiniLM-L12-v2"
        )
        _collection = client.get_or_create_collection(
            name="memory",
            embedding_function=ef
        )
    except Exception as e:
        logger.warning(f"ChromaDB недоступен: {e}")
        _collection = None
    return _collection


def add_memory(text: str, metadata: dict = None):
    try:
        col = _get_collection()
        if col is None:
            return
        import hashlib
        doc_id = hashlib.md5(text.encode()).hexdigest()
        col.upsert(
            documents=[text],
            ids=[doc_id],
            metadatas=[metadata or {}]
        )
    except Exception as e:
        logger.warning(f"add_memory error: {e}")


def query_memory(query: str, n: int = 3, chat_id=None) -> list:
    try:
        col = _get_collection()
        if col is None:
            return []
        where = {"chat_id": chat_id} if chat_id is not None else None
        results = col.query(
            query_texts=[query],
            n_results=min(n, max(1, col.count())),
            where=where
        )
        docs = results.get("documents", [[]])[0]
        return [d for d in docs if d]
    except Exception as e:
        logger.warning(f"query_memory error: {e}")
        return []
