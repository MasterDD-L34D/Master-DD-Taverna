# Changelog

Questo file riassume le modifiche rilevanti introdotte dall’integrazione di **Source Governance v1**.

## 2026-04-10 — Reference contract versioning hardening

### Pipeline e controlli automatici
- `tools/validate_schemas.py`: esteso con validazione del contratto versioni reference (manifest, dataset `data/reference/*.json`, controllo `entries`, verifica `reference_catalog_version` su payload build e `composite.build`) con exit code bloccante in caso di mismatch.
- Rafforzata la validazione del manifest: i dataset obbligatori `spells`, `feats`, `items` devono essere presenti e coerenti, altrimenti il gate fallisce.
- `.github/workflows/static-analysis.yml`: aggiunto step esplicito di gate `reference catalog version` con `--manifest data/reference/manifest.json --build-dir src/data/builds`.

### Test
- Aggiunta suite `tests/test_validate_schemas.py` per coprire: allineamento manifest/dataset, obbligo dei dataset canonici e mismatch di `reference_catalog_version`.

### Regola operativa
- Formalizzata la regola: ogni modifica ai dataset `data/reference/*.json` deve includere aggiornamento del manifest e nota in `CHANGELOG.md`.

### Documentazione API
- `docs/api_usage.md`: aggiornata sezione su catalog version e aggiunta sezione **Contract versioning** con comportamento atteso in caso di mismatch e indicazioni CI (`--build-dir`).

## 2025-12-17 — Source Governance v1

### Policy core
- `gpt/system_prompt_core.md`: aggiunta sezione **Source Governance v1** con STEP -1 (META-SEARCH) e STEP 0 (RAW anchoring AoN/Paizo), 4 gate, breadcrumb obbligatoria, divieti di inferenza senza RAW.

### Moduli
- `src/modules/base_profile.txt` + `src/data/modules/base_profile.txt`: aggiunto principio `source_governance_v1` (policy obbligatoria per regole/combo/build).
- `src/modules/ruling_expert.txt` + `src/data/modules/ruling_expert.txt`: vincolato l’uso di META (solo dopo STEP 0 come contesto) e reso obbligatorio RAW anchoring prima del verdetto.
- `src/modules/explain_methods.txt` + `src/data/modules/explain_methods.txt`: reso obbligatorio STEP 0 prima di spiegazioni tecniche su regole/feat/spell/item.
- `src/modules/minmax_builder.txt` + `src/data/modules/minmax_builder.txt`: integrazione governance in constraints + breadcrumb/verdetto quando entra META.

### Template/output
- `src/modules/scheda_pg_markdown_template.md` + `src/data/modules/scheda_pg_markdown_template.md`: breadcrumb automatica **solo quando** `fonti_meta` contiene elementi META (rilevazione robusta su `level`/`tipo`/`badge`).

### Documentazione
- `docs/source-governance/SOURCE_GOVERNANCE.md`: policy ufficiale.
- `docs/source-governance/INTEGRATION_PLAN.md`: piano di integrazione.
- `docs/source-governance/TARGET_MATRIX.md`: matrice file → requisiti/modifiche.
- `docs/source-governance/QA_EXAMPLES.md`: esempi QA (2).
- `docs/source-governance/QA_REPORT.md`: report QA.