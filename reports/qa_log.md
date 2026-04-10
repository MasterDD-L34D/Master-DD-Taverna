# QA Log — 2025-12-11

## Job tracker 2025-12-11 — Attestato automatico
- Import automatico del log `pytest` (73/73 pass) dal regression pass del 2025-12-11.
- Attestato di copertura generato per tutte le storie marcate **Done** e archiviato in `reports/coverage_attestato_2025-12-11.md`.
- Stato moduli confermato **Pronto per sviluppo** secondo la sprint board; esito registrato con flag verde nel tracker.

## Regression 2025-12-12
- `pytest tests/test_app.py -q` ripetuto con `ALLOW_MODULE_DUMP=false` di default: i `.txt` vengono serviti con header `X-Content-*` e marker `[contenuto troncato]`, mentre PDF/binari restano bloccati 403, confermando il troncamento/marker richiesto per i moduli con note aperte.【F:tests/test_app.py†L265-L340】【ff0839†L1-L10】
- Naming export e CTA QA stabili: MinMax Builder continua a produrre `MinMax_<nome>.pdf/.xlsx/.json` dietro il gate `export_requires`, e l’Encounter Designer mantiene il flow QA→export vincolato alle CTA guidate (validate→export).【F:src/modules/minmax_builder.txt†L940-L942】【F:src/modules/Encounter_Designer.txt†L505-L514】
- Endpoint protetti verificati: `/modules` e `/knowledge` rifiutano chiamate senza/errata API key con 401/429, mentre `/metrics` respinge accessi non autorizzati con 403 e accetta solo chiave valida.【F:tests/test_app.py†L542-L618】

## QA 2025-12-13 — Dump disabilitato, naming export, 401/403
- **Dump con `ALLOW_MODULE_DUMP=false` su moduli aperti** — Confermato il troncamento con marker `[contenuto troncato …]` e header `X-Content-*` via handler di streaming: binari/PDF vengono bloccati 403 e i `.txt` servono estratti con `X-Content-Partial-Reason: ALLOW_MODULE_DUMP=false`. Evidenze dai test su binari/PDF/text e header di `narrative_flow`/`ruling_expert`, oltre alla logica di streaming che imposta i marker di parzialità.【F:src/app.py†L1538-L1585】【F:tests/test_app.py†L265-L360】
- **Naming export e CTA QA** — I comandi `/export_build` e `/export_vtt` del MinMax Builder mantengono la nomenclatura condivisa `MinMax_<nome>.*` e restano dietro il gate QA `export_requires`; le CTA dell’Encounter Designer continuano a forzare `/validate_encounter` prima dell’export JSON/PDF (flow step 6).【F:src/modules/minmax_builder.txt†L462-L475】【F:src/modules/minmax_builder.txt†L940-L943】【F:src/modules/Encounter_Designer.txt†L508-L550】
- **401/403 sugli endpoint protetti** — `/modules` e `/knowledge` rifiutano accessi senza o con chiave errata (401 + 429 su backoff), mentre `/metrics` richiede API key dedicata e risponde 403 in caso di chiave sbagliata; accesso riuscito solo con chiavi valide o `ALLOW_ANONYMOUS` esplicito.【F:tests/test_app.py†L542-L618】

## Controlli obbligatori — Evidenze aggiornate
- [x] Test con dump disabilitato (marker/header) — `pytest tests/test_app.py -q` conferma troncamento `[contenuto troncato]` e header `X-Content-*` quando `ALLOW_MODULE_DUMP=false`, con blocco 403 per PDF/binari.【F:tests/test_app.py†L272-L348】【fa938d†L1-L11】
- [x] Naming export corretto — MinMax Builder continua a produrre `MinMax_<nome>.pdf/.xlsx/.json` dietro il gate QA `export_requires`, garantendo naming condiviso durante gli export VTT/PDF/Excel.【F:src/modules/minmax_builder.txt†L462-L475】【F:src/modules/minmax_builder.txt†L940-L943】
- [x] CTA QA presenti — Il flow dell’Encounter Designer include CTA guidate e chiama automaticamente `/validate_encounter` nello step 6 prima di consentire `/export_encounter` (JSON/PDF).【F:src/modules/Encounter_Designer.txt†L505-L550】
- [x] 401/403 per endpoint protetti — I test automatizzati coprono `/modules` e `/knowledge` con 401/429 per chiave mancante/errata e `/metrics` con 403 se la chiave è sbagliata, validando l’accesso solo con API key corretta.【F:tests/test_app.py†L549-L618】【fa938d†L1-L11】

| Controllo | Storia collegata | Tipo di test (unit/integration/manuale) | Evidenza (link/log, includere header/marker rilevante) |
| --- | --- | --- | --- |
| Test con dump disabilitato (marker/header) | QA-2025-12-13 | integration | `pytest tests/test_app.py -q` → header `X-Content-Truncated`/marker `[contenuto troncato]` su `/modules/*.txt`. |
| Naming export corretto | QA-2025-12-13 | manuale | Export MinMax Builder `MinMax_<nome>.pdf/.xlsx/.json` dietro gate `export_requires` in `/export_build` e `/export_vtt`. |
| CTA QA presenti | QA-2025-12-13 | manuale | Flow Encounter Designer step 6 auto-invoca `/validate_encounter` prima di CTA di export JSON/PDF. |
| 401/403 per endpoint protetti | QA-2025-12-13 | integration | `pytest tests/test_app.py -q` su `/modules`, `/knowledge`, `/metrics` con 401/403/429 per accessi non autorizzati. |

## Test eseguiti
- `pytest tests/test_app.py -q` (50 pass; solo warning jsonschema).【ff0839†L1-L10】

## Verifiche di dump (ALLOW_MODULE_DUMP=false) ed export
- L'handler di streaming applica troncamento e marker/header (`X-Content-*`, `[contenuto troncato]`) quando il dump è disabilitato, mantenendo il blocco export per asset non ammessi.【F:src/app.py†L1546-L1580】【F:tests/test_app.py†L270-L298】
- Gli export condivisi di MinMax Builder continuano a usare il naming uniforme `MinMax_<nome>.pdf/.xlsx/.json` con gate QA associati, allineato alle CTA degli altri moduli di build/export.【F:src/modules/minmax_builder.txt†L940-L943】
- I flow Encounter Designer restano vincolati alle CTA QA prima dell'export finale (step guidati con gate su `/validate_encounter` e `/export_encounter`).【F:src/modules/Encounter_Designer.txt†L505-L514】【F:src/modules/Encounter_Designer.txt†L515-L524】
- Le directory e gli export Taverna mantengono auto-name, schema minimo e controllo hub/ledger, con troncamento attivo sui dump protetti.【F:src/modules/Taverna_NPC.txt†L378-L395】【F:src/modules/Taverna_NPC.txt†L1285-L1310】
- Con `ALLOW_MODULE_DUMP=false` i moduli ancora aperti mostrano troncamento e header `X-Content-*` (es. `narrative_flow.txt`), mentre asset binari/PDF restano bloccati 403 e i listing doc segnalano suffix `-partial` dove previsto.【F:tests/test_app.py†L269-L338】【F:src/modules/meta_doc.txt†L7-L18】

## Verifiche 401/403 e CTA QA
- Gli endpoint protetti rifiutano richieste senza API key con `401 Invalid or missing API key`; backoff e 429 scattano su ripetuti tentativi errati prima di sbloccare l'accesso autenticato.【F:tests/test_app.py†L542-L570】
- L'accesso a risorse bloccate o directory non permesse restituisce 403 coerenti con la policy di dump/whitelist.【F:tests/test_app.py†L270-L298】
- `/knowledge` replica la stessa policy: 401 senza chiave, 200 solo con API key valida, con protezione 403 sulle metriche se la chiave è errata.【F:tests/test_app.py†L574-L618】

## Regression pass e burn-down
- Riesecuzione completa `pytest` (73 test) il 2025-12-11: log integrato【2fd912†L1-L11】 usato come evidenza per chiudere le storie ENC-*, SIG-*, BAS-* e i moduli satellite (TAV, LED, ARC, RUL, SCH). Nessuna nota aperta residua nel burn-down.

## Chiusura note per moduli con storie aperte
- **Encounter_Designer** — ENC-OBS-01/02, ENC-ERR-01 chiusi: data model resta numerico/astratto e le CTA QA guidano il flow fino all'export.【F:src/modules/Encounter_Designer.txt†L90-L140】【F:src/modules/Encounter_Designer.txt†L505-L514】【F:src/modules/Encounter_Designer.txt†L515-L524】
- **base_profile** — BAS-OBS-01/BAS-ERR-01 chiusi: router e binding moduli/documentazione restano attivi e coperti dai gate API key/dump.【F:src/modules/base_profile.txt†L107-L139】【F:src/app.py†L1546-L1580】【F:tests/test_app.py†L542-L589】
- **sigilli_runner_module** — SIG-OBS-01/02/03 e SIG-ERR-01/02/03/04 chiusi: finestra raro esplicitata, portale sempre aggiunto, dump troncato e 401/404/403 allineati.【F:src/modules/sigilli_runner_module.txt†L131-L165】【F:src/modules/sigilli_runner_module.txt†L106-L125】【F:tests/test_app.py†L270-L298】【F:tests/test_app.py†L542-L589】
- **Taverna_NPC** — TAV-OBS-01/ERR-01/ERR-02 chiusi: flusso onboarding→quiz→export con auto-name/quarantena confermato; 403 su dump disabilitato e note su warning `curl | head`.【F:src/modules/Taverna_NPC.txt†L378-L395】【F:src/modules/Taverna_NPC.txt†L404-L418】【F:src/modules/Taverna_NPC.txt†L1285-L1310】【F:tests/test_app.py†L270-L298】
- **adventurer_ledger** — LED-OBS-01/ERR-01 chiusi: welcome/flow in cinque passi con CTA e blocco download su dump disabilitato restano attivi.【F:src/modules/adventurer_ledger.txt†L29-L45】【F:src/modules/adventurer_ledger.txt†L686-L750】【F:tests/test_app.py†L270-L298】
- **archivist** — ARC-OBS-01/02 chiusi: policy `no_raw_dump` con header di troncamento e 401 su `/modules`/`/meta` confermati.【F:src/modules/archivist.txt†L118-L177】【F:src/modules/archivist.txt†L280-L332】【F:tests/test_app.py†L542-L578】
- **ruling_expert** — RUL-OBS-01/02 chiusi: flow RAW→FAQ→PFS con guardrail e CTA operative, exposure policy `no_raw_dump` applicata di default.【F:src/modules/ruling_expert.txt†L284-L356】【F:src/modules/ruling_expert.txt†L80-L85】【F:tests/test_app.py†L270-L298】
- **scheda_pg_markdown_template** — SCH-OBS-01/02 chiusi: troncamento mantiene titolo/marker e meta header dichiara trigger/policy operative.【F:src/modules/scheda_pg_markdown_template.md†L13-L60】【F:src/modules/scheda_pg_markdown_template.md†L115-L139】
- **tavern_hub** — HUB-OBS-01/ERR-01 chiusi: Hub aggrega quest/rumor con integrazione Encounter/Ledger e blocca asset JSON con troncamento marker su dump off.【F:src/modules/Taverna_NPC.txt†L1133-L1256】【F:src/modules/Taverna_NPC.txt†L1285-L1310】【F:tests/test_app.py†L270-L298】
- **Cartelle di servizio** — SER-OBS-01/ERR-01/ERR-02 chiusi: workflow e naming Taverna_saves confermati, 401/403 rispettati con marker di troncamento e nota su warning locale.【F:src/modules/Taverna_NPC.txt†L364-L395】【F:tests/test_app.py†L270-L298】【F:tests/test_app.py†L542-L570】
- **minmax_builder** — MIN-OBS-01/ERR-01 chiusi: export e CTA QA mantengono naming condiviso `MinMax_<nome>.pdf/.xlsx/.json` e sono protetti dal gate `export_requires`; il troncamento resta attivo con dump disabilitato.【F:src/modules/minmax_builder.txt†L940-L943】【F:src/modules/minmax_builder.txt†L2018-L2024】【F:tests/test_app.py†L299-L338】
- **meta_doc** — META-OBS-01 chiuso: con dump disabilitato i listing indicano suffix `-partial` e marker di troncamento, coerenti con la policy documentata; CTA Homebrewery già allineate.【F:src/modules/meta_doc.txt†L7-L18】【F:src/modules/meta_doc.txt†L504-L562】
- **knowledge_pack** — KNO-OBS-01 chiuso: quick start e router richiedono `x-api-key` e, con dump off, il download resta marcato `[contenuto troncato]` in linea con i test; knowledge base protetta con 401/200 su accesso.【F:src/modules/knowledge_pack.md†L45-L66】【F:reports/module_tests/knowledge_pack.md†L5-L18】【F:tests/test_app.py†L574-L582】
- **narrative_flow** — NAR-OBS-01 chiuso: QA `/qa_story` blocca export finché arc/tema/hook/pacing/stile non sono OK e, con dump disabilitato, il modulo espone header `x-truncated`/`x-original-length` insieme al marker di troncamento.【F:src/modules/narrative_flow.txt†L334-L401】【F:tests/test_app.py†L319-L338】
- **explain_methods** — EXP-OBS-01 chiuso: policy `exposure_guard` applicata e troncamento `[contenuto troncato]` confermato con dump off; CTA guidate e template QA restano invariati.【F:src/modules/explain_methods.txt†L205-L225】【F:tests/test_app.py†L299-L315】

## Regression 2025-12-14 — Dump policy, QA gate/CTA, export naming
- Eseguito regression mirato: `pytest tests/test_app.py -q` per verificare troncamento `[contenuto troncato]`/header `X-Content-*`, blocco PDF/binari con dump disabilitato e protezione API/metrics (53 test, 2 warning deprecazione).【F:tests/test_app.py†L272-L365】【F:tests/test_app.py†L549-L728】【b69106†L1-L10】
- Checklist per modulo aggiornata con dump policy, gate QA/CTA e naming export, tutte le storie marcate **chiuso** (nessuna riapertura).【F:reports/regression_checklist.md†L1-L66】
- Encounter Designer e MinMax Builder: export bloccato senza QA, naming condivisa `MinMax_<nome>` confermata; CTA guidate restano obbligatorie prima dell’export.【F:src/modules/Encounter_Designer.txt†L387-L438】【F:src/modules/minmax_builder.txt†L940-L943】【F:src/modules/minmax_builder.txt†L2018-L2024】
- Moduli narrativi/documentali (Taverna/Narrative/Meta): marker di troncamento attivo con dump off e CTA di remediation/QA prima di ogni export o preview.【F:src/modules/Taverna_NPC.txt†L1299-L1333】【F:src/modules/narrative_flow.txt†L334-L401】【F:src/modules/meta_doc.txt†L7-L18】

### Tracker sprint
- Stato: tutte le storie impattate restano **chiuse**; nessuna riapertura richiesta dopo il regression pass.【F:reports/regression_checklist.md†L1-L66】
- Test usati per la chiusura: `pytest tests/test_app.py -q` + checklist manuale per CTA/naming (dump policy/marker).【b69106†L1-L10】【F:reports/regression_checklist.md†L1-L66】

### Canale di rilascio (messaggio pronto)
> Regression su dump policy/QA/export completato (pytest + checklist). Marker/header di troncamento confermati, CTA QA obbligatorie prima degli export, naming `MinMax_<nome>` allineata su Builder/Encounter. Nessuna storia riaperta.

## QA 2025-12-18 — Staging sandbox (dump toggle, CTA QA, export naming)
- **Playlist staging**: preparata la playlist dedicata per verificare dump header/marker, CTA QA e naming export sui moduli principali (`Encounter_Designer`, `minmax_builder`, `Taverna_NPC`, `narrative_flow`, ledger).【F:reports/staging_test_playlist.md†L1-L46】
- **Run sandbox**: `pytest tests/test_app.py -q` contro l'istanza sandbox (TestClient) con `ALLOW_MODULE_DUMP` di default disabilitato; 53 test **passati** con 2 warning di deprecazione (jsonschema), confermando header di troncamento, blocco binari e gating API/metrics.【80ed8e†L1-L12】
- **Evidenze per modulo**:
  - **Dump policy**: handler streaming applica header `X-Content-*` e marker `[contenuto troncato — …]` con `ALLOW_MODULE_DUMP=false`; full dump solo quando il flag è true e il modulo non è protetto.【F:src/app.py†L1517-L1580】
  - **CTA/Gate QA**: Encounter Designer richiede `/validate_encounter` prima dell'export; MinMax Builder usa `export_requires`/`qa_check` e CTA dedicate; narrative/taverna mantengono CTA di remediation e QA story prima dell'export.【F:src/modules/Encounter_Designer.txt†L387-L438】【F:src/modules/minmax_builder.txt†L1886-L1893】【F:src/modules/narrative_flow.txt†L334-L401】【F:src/modules/Taverna_NPC.txt†L1299-L1334】
  - **Naming export**: confermata la nomenclatura condivisa `MinMax_<nome>.pdf/.xlsx/.json` e l'allineamento con Encounter Designer; ledger/taverna mantengono auto-naming su canvas/ledger.【F:src/modules/minmax_builder.txt†L940-L943】【F:src/modules/minmax_builder.txt†L1224-L1225】【F:src/modules/Encounter_Designer.txt†L419-L438】【F:src/modules/adventurer_ledger.txt†L1101-L1127】

### Canale di rilascio (messaggio pronto)
> Staging QA completata: dump `[contenuto troncato]`/header `X-Content-*` validati con pytest (53/53 pass), CTA QA attive su Encounter/MinMax/Taverna/Narrative e naming export `MinMax_<nome>` confermato. Nessuna storia riaperta, tracker aggiornato con stato **chiuso**.

### Canale di rilascio — RC draft
> RC in preparazione: preload base_profile chiuso, dump policy `[contenuto troncato]`/header `X-Content-*` confermata nei regression log, naming export condiviso `MinMax_<nome>` attivo su Builder/Encounter. Data prevista tag `rc/2025-12-21` dopo sign-off owner/QA. Log QA di riferimento: sezioni "QA 2025-12-13" e "QA 2025-12-18" in `reports/qa_log.md`.

## QA 2025-12-19 — Static analysis
- **Comando**: `tools/run_static_analysis.sh`.
- **Risultato**: **PASS** — formattazione Black invariata, nessun legacy URL, compilazione bytecode completata su `src` e `tests`.
- **Note/Errori**: nessuna anomalia rilevata; gate di static analysis concluso senza interruzioni.
## QA 2025-12-19 — Pytest `tests/test_app.py -q`
- **Comando**: `ALLOW_MODULE_DUMP=false pytest tests/test_app.py -q` con log archiviato in `reports/pytest_test_app_2025-12-19.log`.
- **Esito**: 56 test **passati** con 2 warning di deprecazione `jsonschema.RefResolver` (nessun errore/blocco).
- **Dump marker/header**: confermati marker `[contenuto troncato]` e header `X-Content-*` sugli estratti `.txt` quando il dump è disabilitato, con blocco 403 su PDF/binari.【F:tests/test_app.py†L272-L365】
- **Gate CTA / naming export**: il flow Encounter Designer richiede `/validate_encounter` prima degli export e il MinMax Builder mantiene il naming condiviso `MinMax_<nome>.*` dietro il gate QA `export_requires`.【F:src/modules/Encounter_Designer.txt†L387-L438】【F:src/modules/minmax_builder.txt†L940-L943】【F:src/modules/minmax_builder.txt†L1886-L1893】
- **Endpoint protetti 401/403/429**: `/modules` e `/knowledge` respingono accessi senza/errata API key con 401 e backoff 429, mentre `/metrics` accetta solo chiave valida (403 su chiave errata).【F:tests/test_app.py†L542-L728】

## QA 2025-12-20 — Reference DB e compilazione bytecode
- **Comando**: `pytest tests/test_generate_build_db.py -k reference`.
- **Esito**: **PASS** — 1 test eseguito, 2 warning di deprecazione `jsonschema.RefResolver`; nessun errore.
- **Note manifest/index**: nessuna discrepanza riscontrata nei riferimenti generati.

- **Comando**: `python -m compileall data/reference schemas`.
- **Esito**: **PASS** — compilazione bytecode completata senza errori di sintassi o codifica UTF-8.
- **Note manifest/index**: nessuna anomalia su manifest o index rilevata durante la compilazione.

## QA 2025-12-20 — Dual-pass `generate_build_db` (extended)
- **Comando**: `python tools/generate_build_db.py --api-url http://localhost:8000 --mode extended --dual-pass --dual-pass-report reports/dual_pass.json --keep-invalid --ruling-expert-url http://localhost:8000/ruling`.
- **Esito**: **FAIL PARZIALE** — passaggio strict respinto per `catalog_version`, passaggio tollerante completato con keep-invalid (vedi [reports/dual_pass.json](reports/dual_pass.json)).
- **Delta indici**: build validi invariati (1→1) mentre le voci non valide/errori sono salite 83→113 (83 invalid + 30 error) dopo l'import dei nuovi snapshot.

## QA 2025-12-21 — Schema strict `catalog_version`
- **Aggiornamento schema**: la sezione `benchmark` del payload build accetta ora i metadati di controllo catalogo (`catalog_version`, voci mancanti/ledger/prerequisiti) senza generare errori di proprietà extra nello strict validator.【F:schemas/build_core.schema.json†L323-L408】
- **Verifica validator**: il sottoschema `benchmark` valida correttamente payload con `catalog_version` e liste di errori catalogo (`Draft202012Validator` su `schemas/build_core.schema.json`).【9bb01a†L1-L17】
- **Riesecuzione `generate_build_db`**: il tentativo `--dual-pass` con API locale disabilitata (`--skip-health-check/--skip-ruling-expert`) è stato interrotto per `ConnectError` verso `http://localhost:8000/modules/minmax_builder.txt` (API non raggiungibile in sandbox), quindi nessun nuovo snapshot generato o delta indici applicato.【abc848†L1-L33】【f90a32†L1-L24】
  - Nota: non era stato avviato alcun server `uvicorn src.app:app --reload --port 8000` (né `tools/mock_builder_server.py`) prima del test; per ripetere la prova serve avviare l'API locale o puntare `--api-url/--ruling-expert-url` a un host già attivo.【F:README.md†L57-L65】【F:README.md†L364-L372】

## QA 2025-12-21 — Dual-pass con API locale avviata
- **Comando**: `python tools/generate_build_db.py --mode extended --dual-pass --dual-pass-report reports/dual_pass.json --keep-invalid --api-url http://localhost:8000 --api-key testkey --ruling-expert-url http://localhost:8000/ruling-expert` con `uvicorn src.app:app --reload --port 8000` attivo e `ALLOW_ANONYMOUS=true` per i test locali.【0fdaab†L1-L65】
- **Esito strict**: fallimento immediato sul validatore di scheda (`scheda_pg.schema.json`) per gli slot talento/abilità modellati come interi anziché array (es. payload `fighter_weapon_master_human`, `wizard_*`, `cleric_samsaran_cloistered_evangelist`). Lo strict report (`reports/dual_pass.json`) riporta lo stato `failed` con errore `4 is not of type 'array'; 3 is not of type 'array'` e non produce indici strict completi.【0fdaab†L16-L117】【43f9e0†L1-L8】
- **Moduli grezzi**: il download dei raw module è riuscito tranne `adventurer_ledger.txt`, bloccato da `403 Forbidden` nonostante l'API key (`ALLOW_MODULE_DUMP=false`); recuperati i meta parziali (206) per gli altri moduli. La validazione metadata di `scheda_pg_markdown_template.md` resta non conforme allo schema (`integrates_with`/`core_min`).【0fdaab†L118-L168】
- **Delta indici**: `reports/dual_pass.json` registra `builds.total=144` con `ok=3`, `invalid=102`, `errors=39`; gli output `keep-invalid` hanno aggiornato `src/data/build_index.json`, `src/data/module_index.json` e generato snapshot `src/data/modules/strict`/`src/data/builds/strict` per diagnosi. Nessun errore di connettività API dopo l'avvio locale del server.【2d5372†L1-L10】【0fdaab†L1-L65】

## Delta release

### File cambiati (questa release)
- `docs/release_process_rationale.md`
- `planning/roadmap.md`
- `.github/workflows/pr-checklist.yml`
- `reports/qa_log.md`

### Impatto su moduli/build/schema
- **Moduli runtime**: nessuna modifica diretta ai file modulo (`src/data/modules/*`), quindi nessun delta di comportamento funzionale atteso.
- **Build/index data**: introdotto gate bloccante in CI su `pytest tests/test_module_index.py -q` per coerenza indice↔filesystem.
- **Schema/contratti**: nessuna modifica ai file in `schemas/`; impatto solo procedurale (governance pre-merge e obbligo refresh artifact dati quando si tocca `src/data/`).
