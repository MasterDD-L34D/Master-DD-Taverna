"""FastAPI endpoints for RAG search and ask."""
import os
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..auth_backoff import require_api_key
from ..config import MODULES_DIR, DATA_DIR

router = APIRouter(prefix="/rag", tags=["rag"])


def _get_encoder():
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        raise HTTPException(status_code=503, detail=f"sentence-transformers non installato: {exc}")
    model = os.getenv("RAG_EMBEDDING_MODEL", "paraphrase-multilingual-MiniLM-L12-v2")
    return SentenceTransformer(model)


def _get_store():
    store_dir = Path(os.getenv("RAG_STORE_DIR", str(DATA_DIR / "vector_store")))
    from .store import VectorStore
    return VectorStore(store_dir)


def _get_retriever():
    store = _get_store()
    if not store.is_ready():
        raise HTTPException(status_code=503, detail="Indice RAG non trovato. Esegui: python tools/index_rag.py")
    encoder = _get_encoder()
    from .retriever import Retriever
    return Retriever(store, encoder)


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1)
    top_k: int = Field(5, ge=1, le=20)


class AskRequest(BaseModel):
    query: str = Field(..., min_length=1)
    top_k: int = Field(5, ge=1, le=20)
    provider: str | None = None


class BuildRequest(BaseModel):
    class_name: str = Field(..., min_length=1, alias="class")
    race: str | None = None
    level: int = Field(1, ge=1, le=20)
    archetype: str | None = None
    focus: str | None = None
    provider: str | None = None


@router.post("/search")
async def rag_search(req: SearchRequest, _=Depends(require_api_key)):
    retriever = _get_retriever()
    results = retriever.search(req.query, top_k=req.top_k)
    return {"query": req.query, "results": results}


@router.post("/ask")
async def rag_ask(req: AskRequest, _=Depends(require_api_key)):
    retriever = _get_retriever()
    results = retriever.search(req.query, top_k=req.top_k)
    from .generator import get_provider
    provider = get_provider(req.provider)
    answer = provider.generate(req.query, results)
    return {
        "query": req.query,
        "provider": req.provider or os.getenv("RAG_LLM_PROVIDER", "mock"),
        "results": results,
        "answer": answer,
    }


@router.post("/build")
async def rag_build(req: BuildRequest, _=Depends(require_api_key)):
    from ..agents.builder import generate_build
    retriever = _get_retriever()
    request_dict = req.model_dump(by_alias=True)
    # 'class' è riservato in Python; BuildRequest usa class_name mappato sull'alias "class"
    request_dict["class"] = request_dict.pop("class_name", request_dict.get("class"))
    payload = generate_build(request_dict, retriever=retriever, provider_name=req.provider)
    return {"request": request_dict, "build": payload}
