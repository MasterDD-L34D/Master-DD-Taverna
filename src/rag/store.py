"""Simple persistent vector store based on numpy embeddings."""
import json
import os
from pathlib import Path

import numpy as np


class VectorStore:
    """Store text chunks and their embeddings on disk.

    Files written under `root`:
      - chunks.json      list of {"id", "source", "text", "meta"}
      - embeddings.npy   float32 matrix (n_chunks, dim)
      - meta.json        {"model", "dim", "count"}
    """

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.chunks_path = self.root / "chunks.json"
        self.embeddings_path = self.root / "embeddings.npy"
        self.meta_path = self.root / "meta.json"
        self.chunks: list[dict] = []
        self.embeddings: np.ndarray | None = None
        self.meta: dict = {}
        self._load()

    def _load(self):
        if self.chunks_path.exists():
            self.chunks = json.load(open(self.chunks_path, encoding="utf-8"))
        if self.embeddings_path.exists():
            self.embeddings = np.load(self.embeddings_path)
        if self.meta_path.exists():
            self.meta = json.load(open(self.meta_path, encoding="utf-8"))

    def save(self, chunks: list[dict], embeddings: np.ndarray, model: str):
        self.chunks = chunks
        self.embeddings = embeddings.astype(np.float32)
        self.meta = {"model": model, "dim": embeddings.shape[1], "count": len(chunks)}
        json.dump(self.chunks, open(self.chunks_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        np.save(self.embeddings_path, self.embeddings)
        json.dump(self.meta, open(self.meta_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    def is_ready(self) -> bool:
        return bool(self.chunks) and self.embeddings is not None and len(self.chunks) == len(self.embeddings)

    def search(self, query_embedding: np.ndarray, top_k: int = 5) -> list[dict]:
        if not self.is_ready():
            return []
        query = query_embedding.astype(np.float32).reshape(1, -1)
        # cosine similarity via normalized dot product
        norms = np.linalg.norm(self.embeddings, axis=1)
        q_norm = np.linalg.norm(query)
        if q_norm == 0 or np.any(norms == 0):
            return []
        sim = (self.embeddings @ query.T).flatten() / (norms * q_norm)
        top_idx = np.argsort(sim)[::-1][:top_k]
        return [
            {
                "chunk_id": self.chunks[i]["id"],
                "source": self.chunks[i]["source"],
                "text": self.chunks[i]["text"],
                "score": float(sim[i]),
                "meta": self.chunks[i].get("meta", {}),
            }
            for i in top_idx
        ]
