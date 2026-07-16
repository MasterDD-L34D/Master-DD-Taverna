"""Retrieval interface for the RAG store."""
from .store import VectorStore


class Retriever:
    def __init__(self, store: VectorStore, encoder):
        self.store = store
        self.encoder = encoder

    def search(self, query: str, top_k: int = 5) -> list[dict]:
        if not self.store.is_ready():
            raise RuntimeError("Vector store non inizializzato. Esegui prima tools/index_rag.py")
        embedding = self.encoder.encode(query, convert_to_numpy=True)
        return self.store.search(embedding, top_k=top_k)
