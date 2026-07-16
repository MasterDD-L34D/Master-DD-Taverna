# Handoff — Sessione Master-DD-Pathfinder-GPT Anomalies

## Stato attuale

- **Repository**: `tooling/Master-DD-Pathfinder-GPT`
- **Branch**: `main`
- **Commit locali già pushati su `origin/main`**:
  1. `4fda22c` — `fix: risolte anomalie repository Master-DD-Pathfinder-GPT`
  2. `5efcecb` — `test: correggi 7 fallimenti pre-esistenti su Windows`
  3. `d54303a` — `docs: aggiorna HANDOFF.md con risultati swarm NPC profiler/IPIP`
- **Repo npc-profiler pushato**: `9cfb94b` — `docs: aggiungi handoff ricerca NPC profiler e assi IPIP`

## Test suite

```text
.venv/Scripts/python -m pytest tests/ -q
104 passed, 1 skipped, 3 warnings
```

L'unico skip è `tests/test_app.py::test_get_module_rejects_symlink_outside_modules`, che salta automaticamente su Windows se mancano i privilegi per creare symlink.

## Cosa è stato fatto in questa sessione

### 1. Ripristino endpoint persi in `src/app.py`

Durante la rimozione del codice legacy erano stati eliminati accidentalmente:

- `GET /health`
- `GET /modules` (listing)
- Middleware metriche (`metrics_middleware`)
- Funzione `_validate_directories()` (chiamata nel lifespan)

Sono stati reintrodotti nella posizione corretta, ripristinando la compatibilità con i test.

### 2. Allineamento moduli

- Copiati i file `.txt`/`.md` da `src/modules/` a `src/data/modules/` (sovrascrivendo gli stub troncati).
- Rimossa la directory `src/data/modules/strict/` (non referenziata da nessuno script in `tools/`).

### 3. Fix `_is_placeholder` in `tools/generate_build_db.py`

La funzione considerava "placeholder" qualsiasi stringa contenente la parola "stub". Dopo l'allineamento, il template `scheda_pg_markdown_template.md` reale (668 righe) conteneva la parola "stub" nella documentazione e veniva scartato, facendo fallire `test_run_harvest_smoke`.

Fix: stringhe più lunghe di 200 caratteri non vengono più trattate come placeholder.

### 4. Aggiornamento `gpt/openapi.json`

Aggiunti endpoint reali mancanti rispetto a `src/app.py`:

- `GET /health` con risposta 503
- `GET /modules`
- `GET /modules/{name}` con query params (`mode`, `class`, `race`, `archetype`, `level`, `stub`)
- `POST /modules/{name}`
- `GET /modules/{name}/meta`
- `GET /modules/taverna_saves/meta`
- `GET /modules/taverna_saves/quota`
- `GET /storage_meta`
- `GET /knowledge`
- `GET /knowledge/{name}/meta`
- `POST /ruling-expert`
- `GET /metrics`

### 5. Licenza OGL e NOTICE

- `LICENSE`: testo Open Game License v1.0a.
- `NOTICE`: dichiarazione di trademark Paizo/Wizards e fonti SRD/PRD.

### 6. Gestione `.env`

- `.env` aggiunto a `.gitignore` (incluse varianti `.env.local`, `.env.*.local`).
- `git rm --cached .env` per rimuoverlo dal tracking (il file locale resta disponibile).

### 7. Pulizia patch e doc duplicati

- Rimosse patch obsolete in root:
  - `sgv1_secondary_fix.patch` (non applicava più correttamente dopo l'allineamento)
  - `source_governance_v1_fix.patch` (già applicata, file presenti)
- Rimosso changelog duplicato `reports/changelog_2025-12-26.md`; mantenuto `docs/changelog_2025-12-26.md`.

### 8. Fix 7 fallimenti pre-esistenti

| Test | Fix |
|------|-----|
| `test_ruling_expert_full_dump_requires_whitelist` | Normalizzazione CRLF/LF nel confronto |
| `test_get_module_rejects_symlink_outside_modules` | `pytest.skip` se symlink non creabile su Windows |
| `test_daily_workflow_help_message` | Skip se bash non disponibile; uso percorso assoluto |
| `test_check_only_run_uses_stubbed_commands` | Stesso fix bash/WSL |
| `test_missing_plan_path_argument_exits_with_error` | Stesso fix bash/WSL |
| `test_module_truncated_when_env_missing` | Mutazione oggetto `settings` esistente per coerenza con `auth_backoff` |
| `test_module_full_body_when_env_enabled` | Mutazione `settings` + normalizzazione CRLF/LF |

## File modificati in questa sessione

```
.gitignore
LICENSE
NOTICE
gpt/openapi.json
reports/changelog_2025-12-26.md  (eliminato)
sgv1_secondary_fix.patch          (eliminato)
source_governance_v1_fix.patch    (eliminato)
src/app.py
src/data/modules/Encounter_Designer.txt
src/data/modules/Taverna_NPC.txt
src/data/modules/adventurer_ledger.txt
src/data/modules/archivist.txt
src/data/modules/base_profile.txt
src/data/modules/explain_methods.txt
src/data/modules/meta_doc.txt
src/data/modules/minmax_builder.txt
src/data/modules/narrative_flow.txt
src/data/modules/ruling_expert.txt
src/data/modules/scheda_pg_markdown_template.md
src/data/modules/sigilli_runner_module.txt
src/data/modules/strict/...       (eliminati)
tests/test_app.py
tests/test_daily_workflow_cli.py
tests/test_module_dump_env.py
tools/generate_build_db.py
```

## Note tecniche importanti

- `src/app.py`: il router `APIRouter` viene incluso senza prefisso con `app.include_router(router)`, quindi gli endpoint `/knowledge`, `/ruling-expert`, `/metrics` sono esposti alla root.
- `auth_backoff.py` importa `settings` da `config` all'import; i test che sostituiscono `config.settings` con un nuovo oggetto devono invece mutare l'oggetto esistente.
- `FileResponse` serve i file in modalità binaria, preservando i CRLF; i test che confrontano il testo devono normalizzare i line endings.

## Handoff swarm — risultati

È stata avviata una swarm di 3 agenti di esplorazione a partire da questo handoff:

1. **verify-handoff**: ha confermato che il handoff riflette fedelmente lo stato del repo (commit, test, file).
2. **npc-profiler-research**: ha prodotto `tooling/npc-profiler/RESEARCH_HANDOFF.md` con 5 risorse open-source per NPC/personalità.
3. **ipip-axes-research**: ha prodotto `tooling/npc-profiler/IPIP_AXES_HANDOFF.md` con la struttura canonica 5 domini × 30 facet, forme brevi e mappatura sugli assi NPC esistenti.

Entrambi i documenti sono stati committati nel repo `tooling/npc-profiler/` come `9cfb94b`.

## Prossimi passi consigliati (da decidere con l'utente)

1. **NPC Profiler**: l'utente aveva menzionato ricerca e compilazione swarm del NPC Profiler con opposite review, bilanciamento e profili. Materiali pronti in `tooling/npc-profiler/RESEARCH_HANDOFF.md` e `IPIP_AXES_HANDOFF.md`.
2. **Open Source Review**: cercare correlazioni online da integrare (IPIP, assi core etc.).
3. **IPIP extensions**: estendere gli assi coretti IPIP.
4. **Merge e caso reale**: provare il lavoro mergiato in un caso reale.
5. **Ispezione GPT Pathfinder Master DD**: verificare e risolvere anomalie residue nel contenuto.

## Comandi utili per riprendere

```bash
cd tooling/Master-DD-Pathfinder-GPT
.venv/Scripts/python -m pytest tests/ -q
git log --oneline -5
git status
```

---

*Handoff generato il 2026-07-16. Sessione chiusa in attesa di ripresa.*
