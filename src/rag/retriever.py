"""Retrieval interface for the RAG store."""
import re

from .store import VectorStore


class Retriever:
    def __init__(self, store: VectorStore, encoder):
        self.store = store
        self.encoder = encoder

    def _normalize(self, text: str) -> str:
        return re.sub(r"[^a-z0-9]+", "", text.lower())

    def _name_from_source(self, source: str) -> str:
        if source.startswith("reference::"):
            parts = source.split("::")
            if len(parts) >= 3:
                return parts[2]
        return ""

    def search(self, query: str, top_k: int = 5) -> list[dict]:
        if not self.store.is_ready():
            raise RuntimeError("Vector store non inizializzato. Esegui prima tools/index_rag.py")
        embedding = self.encoder.encode(query, convert_to_numpy=True)
        candidates = self.store.search(embedding, top_k=max(top_k * 4, 20))
        query_terms = set(re.findall(r"[a-zA-Z0-9]+", query.lower()))
        norm_query = self._normalize(query)
        boosted = []
        for c in candidates:
            score = c["score"]
            name = self._name_from_source(c.get("source", ""))
            if name:
                name_terms = set(re.findall(r"[a-zA-Z0-9]+", name.lower()))
                overlap = len(query_terms & name_terms)
                if overlap:
                    score += 0.05 * overlap
                norm_name = self._normalize(name)
                if norm_name and norm_query and (norm_query in norm_name or norm_name in norm_query):
                    score += 0.12
            boosted.append({**c, "score": score})
        boosted.sort(key=lambda x: x["score"], reverse=True)
        return boosted[:top_k]
