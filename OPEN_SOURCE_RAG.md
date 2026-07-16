# Master DD Pathfinder — RAG Open Source MVP

Questo documento descrive il layer **RAG (Retrieval-Augmented Generation)** aggiunto al progetto per trasformare il bundle GPT in un sistema usabile con LLM open source/locali.

## Cosa è stato aggiunto

- `src/rag/` — modulo RAG:
  - `store.py`: vector store persistente basato su numpy (embeddings + chunks JSON).
  - `indexer.py`: chunking di moduli e catalogo reference + embedding.
  - `retriever.py`: ricerca semantica top-k.
  - `generator.py`: generazione risposta via Ollama, API OpenAI-compatibile o mock offline.
  - `router.py`: endpoint FastAPI `/rag/search` e `/rag/ask`.
- `tools/index_rag.py` — script per costruire l'indice.
- `tests/test_rag.py` — test unitari e di integrazione endpoint.

## Requisiti

```bash
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt
```

Le nuove dipendenze sono:

- `sentence-transformers>=2.3`
- `numpy`

## Costruire l'indice RAG

```bash
.venv/Scripts/python tools/index_rag.py
```

L'operazione:

1. scarica il modello di embeddings `paraphrase-multilingual-MiniLM-L12-v2` (~120 MB) al primo avvio;
2. legge i moduli da `src/modules/`;
3. legge il catalogo reference da `data/reference/` (feats, spells, items);
4. salva embeddings e chunk in `src/data/vector_store/`.

Dimensione attesa dell'indice: ~5.000 chunk (1.000 dai moduli + 4.000 dal catalogo reference).

## Avviare l'API

```bash
.venv/Scripts/uvicorn src.app:app --reload --port 8000
```

Di default l'autenticazione è attiva. Imposta:

```bash
export API_KEY="la-tua-chiave"
```

oppure, solo per sviluppo locale:

```bash
export ALLOW_ANONYMOUS="true"
```

## Usare gli endpoint RAG

### Ricerca semantica

```bash
curl -X POST http://localhost:8000/rag/search \
  -H "Content-Type: application/json" \
  -H "x-api-key: la-tua-chiave" \
  -d '{"query": "talento Power Attack", "top_k": 5}'
```

### Domanda-risposta (mock offline)

```bash
curl -X POST http://localhost:8000/rag/ask \
  -H "Content-Type: application/json" \
  -H "x-api-key: la-tua-chiave" \
  -d '{"query": "cosa fa Power Attack?", "top_k": 5, "provider": "mock"}'
```

Il provider `mock` non chiama alcun LLM: restituisce la query e i chunk recuperati, utile per test e demo offline.

### Domanda-risposta con Ollama

Avvia Ollama in locale con un modello, es. `llama3.1`:

```bash
ollama run llama3.1
```

Poi:

```bash
export RAG_LLM_PROVIDER="ollama"
export OLLAMA_MODEL="llama3.1"

curl -X POST http://localhost:8000/rag/ask \
  -H "Content-Type: application/json" \
  -H "x-api-key: la-tua-chiave" \
  -d '{"query": "cosa fa Power Attack?", "top_k": 5}'
```

### Domanda-risposta con API OpenAI-compatibile

```bash
export RAG_LLM_PROVIDER="openai"
export OPENAI_API_KEY="sk-..."
export OPENAI_BASE_URL="https://api.openai.com/v1"  # oppure altro provider compatibile
export OPENAI_MODEL="gpt-3.5-turbo"

curl -X POST http://localhost:8000/rag/ask \
  -H "Content-Type: application/json" \
  -H "x-api-key: la-tua-chiave" \
  -d '{"query": "cosa fa Power Attack?", "top_k": 5}'
```

## Variabili d'ambiente

| Variabile | Default | Descrizione |
|---|---|---|
| `RAG_EMBEDDING_MODEL` | `paraphrase-multilingual-MiniLM-L12-v2` | Modello sentence-transformers per embeddings |
| `RAG_STORE_DIR` | `src/data/vector_store` | Directory dell'indice |
| `RAG_LLM_PROVIDER` | `mock` | `mock`, `ollama`, `openai` |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | URL Ollama |
| `OLLAMA_MODEL` | `llama3.1` | Modello Ollama |
| `OPENAI_API_KEY` | — | API key per provider OpenAI-compatibile |
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` | Base URL API |
| `OPENAI_MODEL` | `gpt-3.5-turbo` | Modello remoto |

## Test

```bash
.venv/Scripts/python -m pytest tests/test_rag.py -q
```

Per testare anche gli endpoint con indice reale:

```bash
.venv/Scripts/python tools/index_rag.py
.venv/Scripts/python -m pytest tests/test_rag.py -q
```

## Architettura

```
Utente/Frontend
      │
      ▼
FastAPI (/rag/search, /rag/ask)
      │
      ├──────────────┐
      ▼              ▼
Retriever      Generator
(embeddings)   (Ollama/OpenAI/mock)
      │
      ▼
Vector Store (numpy + JSON)
      │
      ▼
src/modules/ + data/reference/
```

## Prossimi passi consigliati

1. **Builder reale**: sostituire lo stub `/modules/minmax_builder.txt?stub=true` con un agente che usa il catalogo reference + LLM per generare build validate.
2. **Memoria conversazionale**: aggiungere uno state DB (SQLite) per Taverna e sessioni di gioco.
3. **Frontend**: aggiungere Streamlit/Gradio per renderlo accessibile a non-tecnici.
4. **Docker**: containerizzare FastAPI + Ollama opzionale.
5. **Migliorare chunking**: usare markdown headers per chunk semantici più precisi.

---

*MVP RAG aggiunto il 2026-07-16.*
