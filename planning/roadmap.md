# Roadmap Pathfinder 1E Master DD

## Obiettivi correnti
- Stabilizzare il ciclo di generazione del database build esteso e dei moduli raw per esport/benchmark.
- Rendere la validazione dei payload modulare con livelli progressivi (`--strict`, `--keep-invalid`) per individuare rapidamente dati non conformi senza perdere evidenze utili.
- Hardening di healthcheck/metriche e autenticazione per ridurre falsi positivi/negativi nei probe e nei rate-limit.

## Milestone
- **Target numerici copertura classi/livelli (checkpoint 1/5/10)**:
  - **Checkpoint 1 (baseline operativo):** almeno **11/11 classi core** con almeno **1 build per livello** sui checkpoint **1/5/10** (totale minimo **33 build core** tracciate in `build_index.json`), con tasso di validità schema ≥ **85%** sul perimetro core.
  - **Checkpoint 5 (espansione controllata):** almeno **20 classi totali** (core + non-core) coperte su **1/5/10** (totale minimo **60 build**) con riduzione errori di completezza ≥ **40%** rispetto alla baseline del checkpoint 1.
  - **Checkpoint 10 (copertura estesa):** almeno **30 classi totali** coperte su **1/5/10** (totale minimo **90 build**) con validità schema ≥ **95%** per modalità `extended` e backlog `full-pg` ridotto a soli casi noti/documentati.
  - **KPI di controllo ciclo:** ogni run deve aggiornare nello stesso ciclo `src/data/build_index.json` + `src/data/module_index.json` e registrare il riepilogo `checkpoints` per livello (`1`, `5`, `10`) con conteggi `total/invalid/schema_errors/completeness_errors`.
- **Generazione DB esteso**: usare `tools/generate_build_db.py` in modalità `extended` per coprire classi e varianti chiave, salvando build e moduli in `src/data/`. Collegamento al flusso descritto in README per l'orchestrazione completa (health check, parametri `mode`, dump moduli).
- **Discovery e filtri moduli**: abilitare `--discover-modules` per unire moduli pinnati e quelli esposti da `/modules`, applicando filtri glob (`--include/--exclude`) per controllare ciò che finisce nel dump, come previsto dal flusso di selezione moduli nel README.
- **Validazione progressiva**: adottare i flag `--strict` e `--keep-invalid` per gestire errori di schema durante la generazione DB, preservando payload non conformi per analisi successive come indicato nella sezione troubleshooting.
- **Health/metrics hardening**: estendere probe di `/health` e raccolta delle metriche per allinearsi ai workflow di avvio API e backoff descritti nel README, riducendo blocchi dovuti a `401/429` e time-out su endpoint remoti.

## Stato ultimo ciclo build
- **Esecuzione:** preflight locale con `--export-lists` per rigenerare `reports/build_review.json` e `reports/index_analysis.json`; gli alert evidenziano che nessuna classe core ha build valide negli indici correnti.
- **Core coverage sprint (2026-04-09):** eseguito run mirato con `planning/core_coverage_sprint.yml` (checkpoint lvl 1/5/10) su mock API locale per ridurre il rumore e riallineare l'indice alle classi segnalate da `alerts.missing_core_classes`.
- **Motivazione gap residuo `missing_core_classes`:** le build core candidate continuano a risultare `invalid/error` perché i payload correnti non soddisfano `build_full_pg.schema.json` (campo richiesto `sheet_payload`) e, in più casi, hanno incoerenze sul formato `sheet_payload.spell_levels` (valori non array). Finché non vengono corretti payload o schema di compatibilità, il ciclo non può chiudersi con lista vuota.
- **Follow-up rapido (handoff):**
  - **Tech Lead:** priorizzare un run mirato per coprire almeno le classi core e ridurre gli alert CI appena introdotti.
  - **Backend/API:** verificare le cause dei warning di validazione (es. versioni catalogo e campo `source` nei meta moduli) e proporre fix lato API/schema.
  - **Data/Validation:** riprocessare i payload esistenti aggiornando catalogo/versioni e correggendo i metadati per rientrare negli schemi.
  - **Docs & Prompt:** documentare nel README/runbook la presenza degli alert di copertura e le azioni richieste per chiudere il gap sulle classi core.
  - **QA reportistica:** continuare a far girare `python tools/refresh_module_reports.py --check` (lint anti-placeholder) e validare gli output coverage generati in CI.

## Owner / Responsabili
- **Tech Lead**: supervisione roadmap, priorità e merge decisioni.
- **Backend/API**: implementazione script `generate_build_db`, autenticazione (`AUTH_BACKOFF_*`), metriche/health.
- **Data/Validation**: schemi in `schemas/`, flag `--strict`/`--keep-invalid`, indici `build_index.json` e `module_index.json`.
- **Docs & Prompt**: allineamento README, `docs/api_usage.md`, `gpt/system_prompt_core.md` e comunicazione cambiamenti.

## Checklist pre-merge unificata (obbligatoria)

Checklist unica condivisa con `docs/release_process_rationale.md`, da completare prima del merge:

- [ ] **Gate indice↔filesystem bloccante in CI**: pass obbligatorio di `pytest tests/test_module_index.py -q`.
- [ ] **Aggiornamento artifact dati obbligatorio**: se la PR modifica `src/data/`, aggiornare anche:
  - `reports/build_review.json`
  - `reports/index_analysis.json`
  - `src/data/module_index.json`
- [ ] **Delta release in QA log**: aggiungere/aggiornare in `reports/qa_log.md` la sezione “Delta release” con file cambiati e impatto su moduli/build/schema.
- [ ] **Ready-to-release evidence**: note release + stato RC + timeline coerenti con il merge candidato.
