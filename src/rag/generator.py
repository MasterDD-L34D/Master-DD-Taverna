"""LLM generator abstraction for RAG answers."""
import json
import os
from typing import List

import httpx


class MockProvider:
    """Provider di fallback che non chiama alcun LLM; utile per test e demo offline."""

    def generate(self, query: str, context: List[dict]) -> str:
        chunks_text = "\n\n---\n\n".join(
            f"[fonte: {c['source']}]\n{c['text']}" for c in context
        )
        return (
            f"[RISPOSTA MOCK - nessun LLM configurato]\n\n"
            f"Domanda: {query}\n\n"
            f"Contesto recuperato ({len(context)} chunk):\n{chunks_text}"
        )


class OllamaProvider:
    def __init__(self, base_url: str = "http://localhost:11434", model: str = "llama3.1"):
        self.base_url = base_url.rstrip("/")
        self.model = model

    def generate(self, query: str, context: List[dict]) -> str:
        chunks_text = "\n\n".join(c["text"] for c in context)
        prompt = (
            "Sei un Master esperto di Pathfinder 1E. Rispondi alla domanda usando solo "
            "il contesto fornito. Se il contesto non basta, dillo chiaramente.\n\n"
            f"Contesto:\n{chunks_text}\n\nDomanda: {query}\nRisposta:"
        )
        try:
            resp = httpx.post(
                f"{self.base_url}/api/generate",
                json={"model": self.model, "prompt": prompt, "stream": False},
                timeout=120,
            )
            resp.raise_for_status()
            return resp.json().get("response", "[risposta vuota da Ollama]")
        except Exception as exc:
            return f"[Errore connessione Ollama: {exc}]"


class OpenAIProvider:
    def __init__(self, api_key: str | None = None, base_url: str = "https://api.openai.com/v1", model: str = "gpt-3.5-turbo"):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.base_url = base_url.rstrip("/")
        self.model = model

    def generate(self, query: str, context: List[dict]) -> str:
        if not self.api_key:
            return "[Errore: OPENAI_API_KEY mancante]"
        chunks_text = "\n\n".join(c["text"] for c in context)
        messages = [
            {"role": "system", "content": "Sei un Master esperto di Pathfinder 1E. Rispondi usando solo il contesto fornito."},
            {"role": "user", "content": f"Contesto:\n{chunks_text}\n\nDomanda: {query}"},
        ]
        try:
            resp = httpx.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                json={"model": self.model, "messages": messages, "temperature": 0.3},
                timeout=120,
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
        except Exception as exc:
            return f"[Errore API OpenAI-compatibile: {exc}]"


def get_provider(
    provider: str | None = None,
    *,
    ollama_base_url: str | None = None,
    ollama_model: str | None = None,
    openai_base_url: str | None = None,
    openai_model: str | None = None,
    openai_api_key: str | None = None,
) -> MockProvider | OllamaProvider | OpenAIProvider:
    name = (provider or os.getenv("RAG_LLM_PROVIDER", "mock")).lower()
    if name == "ollama":
        return OllamaProvider(
            base_url=ollama_base_url or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
            model=ollama_model or os.getenv("OLLAMA_MODEL", "llama3.1"),
        )
    if name in ("openai", "openai-compatible"):
        return OpenAIProvider(
            api_key=openai_api_key or os.getenv("OPENAI_API_KEY"),
            base_url=openai_base_url or os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
            model=openai_model or os.getenv("OPENAI_MODEL", "gpt-3.5-turbo"),
        )
    return MockProvider()
