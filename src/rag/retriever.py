"""Retrieval interface for the RAG store."""

import re

from .lexicon import load_lexicon, translate_query
from .store import VectorStore


class Retriever:
    def __init__(self, store: VectorStore, encoder):
        self.store = store
        self.encoder = encoder
        self._lexicon = load_lexicon()

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
            raise RuntimeError(
                "Vector store non inizializzato. Esegui prima tools/index_rag.py"
            )
        # Mitigazione finding RAG eval 2026-07-25: query-translation IT->EN
        # prima dell'encoding e del matching (hit rate 33% -> 78% validato).
        query = translate_query(query, self._lexicon)
        embedding = self.encoder.encode(query, convert_to_numpy=True)
        candidates = self.store.search(embedding, top_k=max(top_k * 4, 20))
        query_terms = set(re.findall(r"[a-zA-Z0-9]+", query.lower()))
        norm_query = self._normalize(query)
        norm_term_set = {self._normalize(t) for t in query_terms if len(t) >= 4}
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
                if (
                    norm_name
                    and norm_query
                    and (norm_query in norm_name or norm_name in norm_query)
                ):
                    score += 0.12
            boosted.append({**c, "score": score})
        # Fast-path esatto (embedding debole su nomi inventati, es.
        # Aasimar/Reactionary): nome == query o == un token >= 4 caratteri
        # della query -> vittoria deterministica. Il boost sopra vale solo
        # nei candidati dense: qui si iniettano i match esatti dall'intero
        # store (ponytail: scansione lineare ~50ms a query, accettabile finche
        # le misure non dicono il contrario).
        exact = []
        if norm_term_set or norm_query:
            seen_ids = {id(c) for c in boosted}
            for c in self.store.chunks:
                name = self._name_from_source(c.get("source", ""))
                if not name:
                    continue
                norm_name = self._normalize(name)
                if norm_name and (
                    norm_name == norm_query or norm_name in norm_term_set
                ):
                    if id(c) not in seen_ids:
                        exact.append(c)
            seen_exact = {id(c) for c in exact}
            boosted = [c for c in boosted if id(c) not in seen_exact]
        if exact:
            top_score = boosted[0]["score"] if boosted else 0.0
            boosted = [{**c, "score": top_score + 0.01} for c in exact] + boosted
            boosted.sort(key=lambda x: x["score"], reverse=True)
        return boosted[:top_k]
