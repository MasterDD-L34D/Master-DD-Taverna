# AGENTS.md — Master-DD-Taverna

**Master-DD-Taverna** — un Master per Pathfinder 1e completo e modulare. Sistema RAG locale (FastAPI + Streamlit + moduli prompt YAML), nato come bundle GPT (`Master-DD-Pathfinder-GPT`) e convertito a stack open source/locale. Lingua del progetto: italiano.

## Struttura

- `src/app.py` — API FastAPI (moduli, RAG, storage taverna). Endpoint canonico storage: `/taverna_storage_meta` (`/storage_meta` = alias legacy)
- `src/modules/` — 15 moduli prompt (12 `.txt` YAML + 2 `.md` Markdown + `tavern_hub.json`). Serviti via API e indicizzati nel RAG
- `src/rag/` — layer RAG (retrieval su moduli + catalogo reference)
- `src/pc/` — builder deterministico PG lv1 (catalogs/engine/models) + endpoint `POST /pc/build`
- `frontend/rag_chat.py` — UI Streamlit
- `data/reference/` — cataloghi: `ogl/` (OGC, committabile), `original/`, `cup_fan_content/`, `pi_local_only/` (Product Identity, **solo locale, mai committare**)
- `tools/` — `index_rag.py`, `import_monsters.py`, `legal_filter.py`, ecc.
- `gpt/` — integrazione legacy GPT Actions (openapi.json + prompt): mantenere coerente con `src/app.py`

## Comandi

```bash
# Dalla root del workspace C:/dev/pathfinder
python launch.py test     # verifica completa (questo repo + npc-profiler): deve dare TUTTE LE VERIFICHE OK
python launch.py start    # API :8000 + frontend :8501 + browser

# Dentro il repo (venv Windows)
.venv/Scripts/python tools/index_rag.py --include-local   # reindice RAG (obbligatorio dopo modifiche ai moduli o ai dati)
.venv/Scripts/python tools/legal_filter.py                # deve dare 0 violazioni
```

## Rituale obbligatorio dopo ogni modifica a `src/modules/`

1. **YAML validity**: tutti i `.txt` devono parsare con `yaml.safe_load` (i test NON parsano i moduli — verifica manuale puntuale; i `.md` non sono YAML e non devono esserlo)
2. **Reindice RAG**: `tools/index_rag.py --include-local`
3. **Test**: `python launch.py test` → TUTTE LE VERIFICHE OK prima di committare
4. **Handoff**: aggiornare `sessione-2026-07-16/HANDOFF_ATTIVO.md` ai cambi significativi

## Vincoli

- **Legale/OGL**: niente Product Identity fuori da `pi_local_only/`; `legal_filter` a 0 violazioni prima di ogni commit
- **Local-first**: nessuna dipendenza da API esterne per il flusso principale; LLM via provider `mock` (test/default CI) o `ollama-openai` (uso reale). Non modificare la logica provider senza istruzioni: è testata
- **Retrieval moduli**: ancorato al catalogo locale `reference://ogl/`; niente assunzioni di navigazione web live nei moduli
- **`.env`**: mai committare; template in `.env.example`
- **Dati locali**: `src/data/vector_store/`, `pi_local_only/` non vanno committati

## Convenzioni

- Commit: conventional, scope tra parentesi, es. `fix(modules): ... (batch N)`; push su `origin/main`. **ADR-0011** (dal 2026-07-19): trailer `Coding-Agent:` + `Trace-Id:` su ogni commit (via `git commit -F`); MAI `Co-Authored-By:`; niente riscrittura della storia
- Metadati moduli: bump `version`/`last_updated` nell'header del file modificato; voce di `changelog:` se il modulo ne ha una sezione
- Modifiche minime e mirate; niente refactor opportunistici fuori scope

## Riferimenti

- `sessione-2026-07-16/HANDOFF_ATTIVO.md` — stato di lavorazione corrente (leggere per primo)
- `sessione-2026-07-16/AVVIO_PROSSIMA_SESSIONE.md` — punto di ripresa e troubleshooting
- `OPEN_SOURCE_RAG.md` — guida RAG e provider LLM
- `docs/IMPORT_PLAYBOOK.md` — metodo consolidato per import di cataloghi OGL da fonti web (leggere prima di qualunque nuovo import dati)
- `docs/WORKFLOW.md` — il ciclo di lavoro completo (piano → subagent-driven → review → push), policy commit ADR-0011, contratto del builder, punti di contatto con pathmaster-dd
- `docs/research/2026-07-19-process-optimization.md` — ricerca su riuso materiale scartato, deduplicazione pipeline e processo ibrido swarm (proposte ordinate per valore/costo; leggere prima di nuovi lotti su dati/infrastruttura)
