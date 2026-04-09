# Command run log


## Template minimo run
Copiare questo blocco per ogni nuova esecuzione e compilarlo in modo sintetico.

```md
## <nome run>
- **Timestamp:** <YYYY-MM-DDTHH:MM:SSZ>
- **Input:** <comando/i o sorgenti dati usate>
- **Esito:** <ok|warning|fail + nota breve>
- **Artifact aggiornati:** <lista file in reports/ e altri output>
```

## CI preflight (schemi, report moduli, attestato coverage locale)
- **Commands:**
  - `python tools/validate_schemas.py`
  - `python tools/refresh_module_reports.py --check`
  - `python tools/generate_build_db.py --export-lists --output-dir src/data/builds --modules-output-dir src/data/modules --index-path src/data/build_index.json --module-index-path src/data/module_index.json`
- **Result:** tutti gli schemi JSON risultano validi; i report in `reports/module_tests/` superano il lint anti-placeholder. La rigenerazione dell'attestato di copertura produce warning di validazione sugli artefatti esistenti ma conclude con i file aggiornati in `reports/` (inclusi `index_analysis.json` con alert sulle classi core mancanti).
- **Next:** coprire almeno le classi core con build valide per eliminare gli alert e correggere i campi extra/metadati che violano `module_metadata.schema.json`.
- **Timestamp:** 2025-12-27T10:15:00Z

## generate_module_plan smoke (heading combinati)
- **Prep:** creato un report temporaneo con heading duplicati/combinati per Fix/Errori/Osservazioni e popolato con bullet distinti per verificare l'aggregazione.
- **Command:**
  ```bash
  python - <<'PY'
  from pathlib import Path
  from tools.generate_module_plan import summarise_module

  report = Path("/tmp/combined_headings.md")
  report.write_text(
      "\n".join(
          [
              "## Fix necessari",
              "- [P1] Primo fix",
              "",
              "## Fix necessari (API)",
              "- Secondo fix API",
              "",
              "## Note e miglioramenti",
              "- [P3] Ritocco opzionale",
              "",
              "## Errori",
              "- Errore nelle API",
              "",
              "## Errori replicati",
              "- Errore di copia",
              "",
              "## Osservazioni e note",
              "- Nota combinata uno",
              "",
              "## Note e osservazioni",
              "- Nota combinata due",
              "",
          ]
      ),
      encoding="utf-8",
  )

  summary = summarise_module("Smoke test", report)

  print("Tasks", summary.tasks)
  print("Errors", summary.errors)
  print("Observations", summary.observations)
  PY
  ```
- **Result:** l'output contiene 3 task (due P1, un P3), 2 errori e 2 osservazioni, confermando che i contenuti provenienti da heading multipli vengono unificati.
- **Timestamp:** 2025-12-11T13:54:01Z

## Handoff operativo post-build
- **Contesto:** ultimo ciclo `generate_build_db` in modalità extended completato con discovery moduli e validazione strict.
- **Azioni:**
  - **Tech Lead:** conferma priorità di follow-up prima del prossimo run (eventuali retry su classi/moduli mancanti).
  - **Backend/API:** verifica flag di discovery/validazione e endpoint (`/health`, `/metrics`, `/modules`) prima di riattivare i workflow schedulati.
  - **Data/Validation:** analizza `src/data/build_index.json` e `src/data/module_index.json` per individuare errori o payload borderline, proponendo fix su schemi/filtri.
  - **Docs:** aggiorna note operative e README con eventuali nuove opzioni/deroghe emerse dall'analisi.
- **Esito atteso:** checklist condivisa nel canale di handoff prima del prossimo ciclo di build.

## generate_build_db connectivity check (initial)
- **Command:** `python tools/generate_build_db.py --api-url http://localhost:8000 --mode extended --discover-modules --max-retries 3 --strict`
- **Result:** Failed with `httpx.ConnectError: All connection attempts failed` while calling `/modules` during module discovery. The tool issued schema-related deprecation warnings before the network failure.
- **Notes:** No spec file was provided; defaults targeted `src/data/builds` and `src/data/modules`. Strict validation remained enabled; switching to `--warn-only` or `--keep-invalid` was not tested because the run stopped before any payloads were retrieved.
- **Timestamp:** 2025-12-08T03:27:49Z

## generate_build_db strict run with discovery (localhost, anonymous enabled)
- **Prep:** Avviato `uvicorn src.app:app --port 8000 --reload` con `ALLOW_ANONYMOUS=true` per permettere l'accesso senza API key.
- **Command:** `python tools/generate_build_db.py --api-url http://localhost:8000 --mode extended --discover-modules --strict --index-path src/data/build_index.json --module-index-path src/data/module_index.json --output-dir src/data/builds --modules-output-dir src/data/modules`
- **Include/Exclude:** nessun filtro applicato (`--include`/`--exclude` non specificati) durante la discovery dei moduli.
- **Result:** Fallito su validazione scheda (`scheda_pg.schema.json`) per i payload delle classi (es. Fighter, Wizard, Cleric, Ranger, Druid, Rogue) a causa di campi numerici riportati come oggetti. La validazione strict ha chiuso il client interrompendo anche i download dei moduli.
- **Timestamp:** 2025-12-08T23:44:28Z

## generate_build_db keep-invalid rerun (localhost, anonymous enabled)
- **Prep:** Server già in esecuzione con `ALLOW_ANONYMOUS=true` su `http://localhost:8000`.
- **Command:** `python tools/generate_build_db.py --api-url http://localhost:8000 --mode extended --discover-modules --keep-invalid --index-path src/data/build_index.json --module-index-path src/data/module_index.json --output-dir src/data/builds --modules-output-dir src/data/modules`
- **Include/Exclude:** nessun filtro applicato (`--include`/`--exclude` non specificati) durante la discovery dei moduli.
- **Result:** Completato con warning di schema; le build extended (Fighter, Wizard, Cleric, Rogue, Ranger, Druid) sono state salvate con `status="invalid"` ma mantenute grazie a `--keep-invalid`. Discovery moduli scaricata integralmente con esito `ok` per tutti i file richiesti e indici aggiornati in `src/data/build_index.json` e `src/data/module_index.json`.
- **Timestamp:** 2025-12-08T23:46:17Z

## generate_build_db rerun with local API up
- **Prep:** Started `uvicorn src.app:app --reload --port 8000` with `ALLOW_ANONYMOUS=true` to bypass the missing API key that blocked the previous attempt.
- **Command:** `python tools/generate_build_db.py --api-url http://localhost:8000 --mode extended --discover-modules --max-retries 3 --strict`
- **Result:** Success. Discovery hit `/modules`, downloaded 14 module assets, and fetched extended builds for all PF1e classes. Strict validation passed; only deprecation warnings from `jsonschema.RefResolver` and `datetime.utcnow()` were reported. Index files were written to `src/data/build_index.json` and `src/data/module_index.json` alongside per-class JSON in `src/data/builds/` and module dumps in `src/data/modules/`.
- **Notes:** No spec file was used. Module fetches included metadata calls (e.g., `/modules/<name>/meta`) and validated step totals at 16 for extended mode. Keep `ALLOW_ANONYMOUS=true` or set `API_KEY` before reruns.
- **Timestamp:** 2025-12-08T03:32:06Z

## generate_build_db comandi di riferimento (core)
- **Variabili:** impostare `API_URL` verso l'endpoint MinMax Builder e `API_KEY` quando richiesto dal gateway; esempio `API_URL=https://builder.example.org API_KEY=token-supersegret`.
- **Comando base:** `API_URL=$API_URL API_KEY=$API_KEY python tools/generate_build_db.py --mode core --classes Alchemist Barbarian --output-dir src/data/builds --modules-output-dir src/data/modules --index-path src/data/build_index.json --module-index-path src/data/module_index.json --max-retries 2`.
- **Probe iniziali:** prima di lanciare lo script verificare `/health` e `/metrics` passando l'header `x-api-key` corretto (preferibilmente `METRICS_API_KEY` per le metriche); in pipeline il log deve riportare quando viene abilitato `--skip-health-check` per endpoint remoti senza probe.
- **Archiviazione locale:** dopo l'esecuzione si possono comprimere gli output con `tar -czf build_db_core.tar.gz src/data/builds src/data/build_index.json src/data/module_index.json` per il caricamento come artefatto CI.

## generate-build-db-core (GitHub Actions)
- **Nome job:** `generate-build-db-core / Build DB core e archiviazione` (workflow `generate-build-db-core.yml`).
- **Cosa fa:** usa `API_URL`/`API_KEY` da secret GitHub per eseguire `python tools/generate_build_db.py --mode core --strict --max-retries 3` archiviando log e output (builds, moduli, indici) nella cartella `build_artifacts/`.
- **Trigger:** schedulato ogni lunedì alle 03:00 UTC e avviabile manualmente via **Run workflow**.
- **Recupero log e artefatti:** al termine del job scaricare l'artefatto `generate-build-db-core-artifacts`, che contiene `generate_build_db_core.log`, i dump in `builds/` e `modules/` e i file indice `build_index.json` e `module_index.json`.
