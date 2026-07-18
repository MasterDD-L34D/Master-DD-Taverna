# Master-DD-Taverna — RAG Open Source MVP

Questo documento descrive il layer **RAG (Retrieval-Augmented Generation)** aggiunto al progetto per trasformare il bundle GPT in un sistema usabile con LLM open source/locali.

## Cosa è stato aggiunto

- `src/rag/` — modulo RAG:
  - `store.py`: vector store persistente basato su numpy (embeddings + chunks JSON).
  - `indexer.py`: chunking di moduli e catalogo reference + embedding.
  - `retriever.py`: ricerca semantica top-k.
  - `generator.py`: generazione risposta via Ollama (endpoint nativo o OpenAI-compatible), API OpenAI-compatibile o mock offline.
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

## Avvio rapido (launcher globale)

Se stai usando la root del monorepo `pathfinder/`, il comando unico avvia API, frontend e browser:

```bash
python launch.py start
```

Il launcher:
- rileva automaticamente Ollama su `localhost:11434` e, se presente, imposta `RAG_LLM_PROVIDER=ollama`;
- se Ollama non è attivo, parte in modalità `mock` (solo chunk recuperati, nessun LLM);
- costruisce l'indice RAG alla prima esecuzione se manca;
- apre il browser su `http://localhost:8501`.

Su Windows puoi anche fare doppio click su `start.bat` (o `start.ps1`) nella root.

## Avvio manuale dell'API

Se preferisci avviare i servizi separatamente da dentro questa cartella:

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

Avvia Ollama in locale con un modello. Nella sessione 2026-07-16 e' stato testato con successo `qwen2.5-coder:7b`:

```bash
ollama pull qwen2.5-coder:7b
ollama run qwen2.5-coder:7b
```

Poi configura `.env` (o esporta le variabili):

```bash
export RAG_LLM_PROVIDER="ollama"
export OLLAMA_MODEL="qwen2.5-coder:7b"
```

E prova:

```bash
curl -X POST http://localhost:8000/rag/ask \
  -H "Content-Type: application/json" \
  -H "x-api-key: la-tua-chiave" \
  -d '{"query": "cosa fa Power Attack?", "top_k": 5}'
```

### Domanda-risposta con Ollama (endpoint OpenAI-compatible)

Ollama espone anche un endpoint compatibile con OpenAI su `/v1/chat/completions`. Questo permette di usare il formato chat completions e parametri aggiuntivi (es. `temperature`) senza API key:

```bash
export RAG_LLM_PROVIDER="ollama-openai"
export OLLAMA_MODEL="qwen2.5-coder:7b"

curl -X POST http://localhost:8000/rag/ask \
  -H "Content-Type: application/json" \
  -H "x-api-key: la-tua-chiave" \
  -d '{"query": "cosa fa Power Attack?", "top_k": 5}'
```

Lo stesso provider funziona con altri backend locali OpenAI-compatible (es. LM Studio su `http://localhost:1234/v1` o `llama.cpp` server) impostando `OLLAMA_BASE_URL` all'URL del backend.

### Domanda-risposta con API OpenAI-compatibile (cloud)

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
| `RAG_LLM_PROVIDER` | `mock` | `mock`, `ollama`, `ollama-openai`, `openai` |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | URL Ollama (o altro backend OpenAI-compatible locale) |
| `OLLAMA_MODEL` | `qwen2.5-coder:7b` | Modello Ollama (testato `qwen2.5-coder:7b`) |
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

## Frontend Streamlit

Un'interfaccia web di chat è disponibile in `frontend/rag_chat.py`.

Con il launcher globale è già incluso in `python launch.py start`.  
In alternativa, per avviare solo il frontend da questa cartella:

```bash
.venv/Scripts/streamlit run frontend/rag_chat.py
```

Si apre il browser su `http://localhost:8501`. Supporta:

- provider `mock`, `ollama`, `ollama-openai`, `openai` con fallback automatico su `mock`
- indicatori di stato per API e Ollama
- scelta del numero di chunk
- visualizzazione delle fonti recuperate
- cronologia chat
- esempi di domande pronte all'uso

## Build Agent

Genera build Pathfinder 1E in formato JSON valido usando RAG + LLM.

### Endpoint API

```bash
curl -X POST http://localhost:8000/rag/build \
  -H "Content-Type: application/json" \
  -H "x-api-key: la-tua-chiave" \
  -d '{"class": "Fighter", "race": "Human", "level": 5, "focus": "DPR", "provider": "mock"}'
```

### CLI

```bash
.venv/Scripts/python tools/build_agent.py --class Fighter --race Human --level 5 --focus DPR --provider mock
```

Salva su file:

```bash
.venv/Scripts/python tools/build_agent.py --class Wizard --race Elf --level 10 --focus control --provider ollama --output build_wizard.json
```

Il mock restituisce una build valida di esempio. Con Ollama/OpenAI il LLM genera una build usando i chunk recuperati e il catalogo reference.

## Importare mostri e NPC locali (opzionale)

E' possibile arricchire il RAG con mostri/NPC da [PathfinderMonsterDatabase](https://github.com/c0d3rman/PathfinderMonsterDatabase), che parsa `aonprd.com`.
I dati derivati **non sono redistribuibili**: restano in `data/reference/pi_local_only/` (gia' `.gitignore`).

### Requisiti

- Clone di PathfinderMonsterDatabase;
- aver generato un `data.json` seguendo le istruzioni del repo (es. `data/poc/data.json` per una PoC).

### Comandi

```bash
# Esempio con la PoC gia' disponibile in sessione-2026-07-16/ricerca/PathfinderMonsterDatabase
.venv/Scripts/python tools/import_monsters.py \\
  --source-dir ../../sessione-2026-07-16/ricerca/PathfinderMonsterDatabase \\
  --input data/poc/data.json \\
  --limit 10

# Rigenera l'indice includendo i cataloghi locali
.venv/Scripts/python tools/index_rag.py --include-local
```

Per indicizzare i mostri importati, `tools/index_rag.py` richiede esplicitamente il flag `--include-local`; senza di esso i cataloghi in `pi_local_only/` vengono saltati.

## Prossimi passi consigliati

1. **Migliorare il builder**: usare un LLM più strutturato per ottenere build dettagliate (talenti per livello, equipaggiamento, benchmark DPR realistici).
2. **Memoria conversazionale**: aggiungere uno state DB (SQLite) per Taverna e sessioni di gioco.
3. **Docker**: containerizzare FastAPI + Ollama opzionale.
4. **Migliorare chunking**: usare markdown headers per chunk semantici più precisi.

---

*MVP RAG aggiunto il 2026-07-16.*
