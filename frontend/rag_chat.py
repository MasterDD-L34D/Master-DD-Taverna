#!/usr/bin/env python3
"""Frontend Streamlit user-friendly per il RAG Master-DD-Taverna.

Uso:
    .venv/Scripts/streamlit run frontend/rag_chat.py

L'API FastAPI deve essere in esecuzione (di norma avviata da launch.py start).
"""
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sentence_transformers import SentenceTransformer

from src.config import DATA_DIR
from src.rag.generator import get_provider
from src.rag.retriever import Retriever
from src.rag.store import VectorStore


def load_retriever():
    store_dir = Path(os.getenv("RAG_STORE_DIR", str(DATA_DIR / "vector_store")))
    store = VectorStore(store_dir)
    if not store.is_ready():
        st.error(
            f"Indice RAG non trovato in {store_dir}.\n\n"
            "Esegui prima: `python launch.py setup` (costruisce l'indice automaticamente)"
        )
        st.stop()
    model = os.getenv("RAG_EMBEDDING_MODEL", "paraphrase-multilingual-MiniLM-L12-v2")
    encoder = SentenceTransformer(model)
    return Retriever(store, encoder)


def ollama_is_running(url: str = "http://localhost:11434/api/tags") -> bool:
    try:
        with urllib.request.urlopen(url, timeout=2) as resp:
            return resp.status == 200
    except Exception:
        return False


def api_is_running(url: str = "http://localhost:8000/health") -> bool:
    try:
        with urllib.request.urlopen(url, timeout=2) as resp:
            return resp.status == 200
    except Exception:
        return False


def get_env_default(key: str, default: str) -> str:
    return os.getenv(key, default)


def main():
    st.set_page_config(page_title="Master-DD-Taverna — RAG", layout="wide")
    st.title("🎲 Master-DD-Taverna — Assistente RAG")
    st.markdown(
        "Fai domande su regole, talenti, incantesimi e build di Pathfinder 1E. "
        "Il sistema recupera il contesto dai moduli e dal catalogo reference e lo passa a un LLM."
    )

    ollama_available = ollama_is_running()
    api_available = api_is_running()

    with st.sidebar:
        st.header("Stato")
        if api_available:
            st.success("API collegata ✅")
        else:
            st.error("API non raggiungibile ❌\nAvvia: `python launch.py start`")

        if ollama_available:
            st.success("Ollama rilevato ✅")
        else:
            st.warning("Ollama non rilevato ⚠️\nIl mock restituira' solo i chunk.")

        st.divider()
        st.header("Configurazione LLM")

        providers = ["mock", "ollama", "ollama-openai", "openai"]
        default_provider = "ollama" if ollama_available else "mock"
        provider = st.selectbox("Provider", providers, index=providers.index(default_provider))

        top_k = st.slider("Chunk da recuperare", min_value=1, max_value=10, value=5)

        if provider == "ollama":
            st.text_input(
                "Ollama URL",
                value=get_env_default("OLLAMA_BASE_URL", "http://localhost:11434"),
                key="ollama_url",
            )
            st.text_input(
                "Modello",
                value=get_env_default("OLLAMA_MODEL", "qwen2.5-coder:7b"),
                key="ollama_model",
            )
            if st.button("Testa connessione Ollama"):
                if ollama_is_running(st.session_state.ollama_url + "/api/tags"):
                    st.success("Ollama raggiungibile!")
                else:
                    st.error("Ollama non raggiungibile. Verifica che sia avviato.")
        elif provider == "ollama-openai":
            st.text_input(
                "Ollama URL",
                value=get_env_default("OLLAMA_BASE_URL", "http://localhost:11434"),
                key="ollama_url",
            )
            st.text_input(
                "Modello",
                value=get_env_default("OLLAMA_MODEL", "qwen2.5-coder:7b"),
                key="ollama_model",
            )
            if st.button("Testa connessione Ollama"):
                if ollama_is_running(st.session_state.ollama_url + "/api/tags"):
                    st.success("Ollama raggiungibile!")
                else:
                    st.error("Ollama non raggiungibile. Verifica che sia avviato.")
        elif provider == "openai":
            st.text_input(
                "Base URL",
                value=get_env_default("OPENAI_BASE_URL", "https://api.openai.com/v1"),
                key="openai_base",
            )
            st.text_input(
                "Modello",
                value=get_env_default("OPENAI_MODEL", "gpt-3.5-turbo"),
                key="openai_model",
            )
            st.text_input("API Key", type="password", key="openai_key")

        st.divider()
        st.caption(
            "**mock**: offline, restituisce solo i chunk.\n"
            "**ollama**: LLM locale via endpoint nativo /api/generate (richiede Ollama).\n"
            "**ollama-openai**: LLM locale via endpoint OpenAI-compatible /v1/chat/completions (richiede Ollama).\n"
            "**openai**: API compatibile OpenAI (cloud o altri backend compatibili)."
        )

    if "messages" not in st.session_state:
        st.session_state.messages = []

    st.subheader("Esempi di domande")
    cols = st.columns(3)
    examples = [
        "cosa fa il talento Power Attack?",
        "come funziona la classe Magus?",
        "quali sono i prerequisiti di Furious Focus?",
    ]
    for i, ex in enumerate(examples):
        if cols[i].button(ex, use_container_width=True):
            st.session_state.pending_prompt = ex

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if msg.get("sources"):
                with st.expander("Fonti"):
                    for src in msg["sources"]:
                        st.markdown(f"**{src['source']}** (score: {src['score']:.3f})")
                        st.markdown(f"> {src['text'][:500]}...")

    prompt = st.chat_input("Cosa vuoi chiedere?")
    if not prompt and "pending_prompt" in st.session_state:
        prompt = st.session_state.pop("pending_prompt")

    if not prompt:
        return

    if not api_available and provider != "mock":
        st.warning("L'API non e' raggiungibile; passo automaticamente al provider mock.")
        provider = "mock"

    with st.chat_message("user"):
        st.markdown(prompt)
    st.session_state.messages.append({"role": "user", "content": prompt})

    with st.spinner("Recupero contesto..."):
        retriever = load_retriever()
        results = retriever.search(prompt, top_k=top_k)

    with st.spinner("Generazione risposta..."):
        provider_kwargs = {}
        if provider in ("ollama", "ollama-openai"):
            provider_kwargs["ollama_base_url"] = st.session_state.get("ollama_url", "http://localhost:11434")
            provider_kwargs["ollama_model"] = st.session_state.get("ollama_model", "qwen2.5-coder:7b")
        elif provider == "openai":
            provider_kwargs["openai_base_url"] = st.session_state.get("openai_base", "https://api.openai.com/v1")
            provider_kwargs["openai_model"] = st.session_state.get("openai_model", "gpt-3.5-turbo")
            key = st.session_state.get("openai_key", "")
            if key:
                provider_kwargs["openai_api_key"] = key

        try:
            gen = get_provider(provider, **provider_kwargs)
            answer = gen.generate(prompt, results)
        except Exception as e:
            answer = f"[Errore durante la generazione: {e}]\n\nPassa al provider mock per vedere solo i chunk recuperati."

    sources = [
        {"source": r["source"], "score": r["score"], "text": r["text"]} for r in results
    ]

    with st.chat_message("assistant"):
        st.markdown(answer)
        if sources:
            with st.expander("Fonti"):
                for src in sources:
                    st.markdown(f"**{src['source']}** (score: {src['score']:.3f})")
                    st.markdown(f"> {src['text'][:500]}...")

    st.session_state.messages.append(
        {"role": "assistant", "content": answer, "sources": sources}
    )


if __name__ == "__main__":
    main()
