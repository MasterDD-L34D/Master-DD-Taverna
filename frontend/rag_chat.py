#!/usr/bin/env python3
"""Frontend Streamlit per interrogare il RAG Master DD Pathfinder.

Uso:
    .venv/Scripts/streamlit run frontend/rag_chat.py

Requisito: avere eseguito almeno una volta `python tools/index_rag.py`.
"""
import os
import sys
from pathlib import Path

import streamlit as st

# rendi disponibili src.*
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
            "Esegui prima: `.venv/Scripts/python tools/index_rag.py`"
        )
        st.stop()
    model = os.getenv("RAG_EMBEDDING_MODEL", "paraphrase-multilingual-MiniLM-L12-v2")
    encoder = SentenceTransformer(model)
    return Retriever(store, encoder)


def main():
    st.set_page_config(page_title="Master DD Pathfinder — RAG", layout="wide")
    st.title("🎲 Master DD Pathfinder — Assistente RAG")
    st.markdown(
        "Fai domande su regole, talenti, incantesimi e build di Pathfinder 1E. "
        "Il sistema recupera il contesto dai moduli e dal catalogo reference."
    )

    with st.sidebar:
        st.header("Configurazione LLM")
        provider = st.selectbox("Provider", ["mock", "ollama", "openai"], index=0)
        top_k = st.slider("Chunk da recuperare", min_value=1, max_value=10, value=5)

        if provider == "ollama":
            st.text_input("Ollama URL", value="http://localhost:11434", key="ollama_url")
            st.text_input("Modello", value="llama3.1", key="ollama_model")
        elif provider == "openai":
            st.text_input("Base URL", value="https://api.openai.com/v1", key="openai_base")
            st.text_input("Modello", value="gpt-3.5-turbo", key="openai_model")
            st.text_input("API Key", type="password", key="openai_key")

        st.divider()
        st.caption(
            "Provider mock = offline, restituisce solo i chunk recuperati. "
            "Per risposte reali usa Ollama o un'API compatibile OpenAI."
        )

    if "messages" not in st.session_state:
        st.session_state.messages = []

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if "sources" in msg and msg["sources"]:
                with st.expander("Fonti"):
                    for src in msg["sources"]:
                        st.markdown(f"**{src['source']}** (score: {src['score']:.3f})")
                        st.markdown(f"> {src['text'][:500]}...")

    prompt = st.chat_input("Cosa vuoi chiedere?")
    if not prompt:
        return

    with st.chat_message("user"):
        st.markdown(prompt)
    st.session_state.messages.append({"role": "user", "content": prompt})

    with st.spinner("Recupero contesto..."):
        retriever = load_retriever()
        results = retriever.search(prompt, top_k=top_k)

    with st.spinner("Generazione risposta..."):
        # configura env per provider scelto
        if provider == "ollama":
            os.environ["OLLAMA_BASE_URL"] = st.session_state.get("ollama_url", "http://localhost:11434")
            os.environ["OLLAMA_MODEL"] = st.session_state.get("ollama_model", "llama3.1")
        elif provider == "openai":
            os.environ["OPENAI_BASE_URL"] = st.session_state.get("openai_base", "https://api.openai.com/v1")
            os.environ["OPENAI_MODEL"] = st.session_state.get("openai_model", "gpt-3.5-turbo")
            key = st.session_state.get("openai_key", "")
            if key:
                os.environ["OPENAI_API_KEY"] = key
        os.environ["RAG_LLM_PROVIDER"] = provider

        gen = get_provider(provider)
        answer = gen.generate(prompt, results)

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
