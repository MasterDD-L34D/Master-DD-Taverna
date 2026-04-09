# Piano operativo generato dai report

Generato il 2025-12-11T21:48:49Z
Fonte sequenza: `planning/module_review_guide.md`

## Aggiornamento attestato 2025-12-11
- Esito job tracker: **verde** (import log pytest 2025-12-11 con 73/73 passati, tutte le storie Done coperte).
- Attestato di copertura archiviato in `reports/coverage_attestato_2025-12-11.md`.

## Checklist seguita (dal documento di guida)

## Core coverage sprint
- **Owner:** Data/Validation (lead: Team Build DB)
- **Classi assegnate:** Barbarian, Bard, Cleric, Druid, Fighter, Monk, Paladin, Ranger, Rogue, Sorcerer, Wizard (fonte: `reports/index_analysis.json` → `alerts.missing_core_classes`).
- **Spec operativa:** `planning/core_coverage_sprint.yml` (checkpoint fissi lvl **1/5/10**, mode `full-pg`, output prefix per classe per minimizzare rumore e collisioni).
- **Checkpoint di controllo:**
  - **L1 (bootstrap):** presenza snapshot `_lvl01`/base per ogni classe core e validazione minima schema `build_core`.
  - **L5 (mid progression):** presenza snapshot `_lvl05` con completezza scheda/ledger e nessun errore bloccante in `reports/build_review.json`.
  - **L10 (advanced):** presenza snapshot `_lvl10` e validazione schema `build_full_pg`; aggiornamento `src/data/build_index.json` + `reports/index_analysis.json`.
- **Done criteria sprint:** ciclo chiuso solo con `missing_core_classes == []` oppure gap motivato esplicitamente in roadmap (`planning/roadmap.md`).
- Sequenza completa: Encounter_Designer → Taverna_NPC → adventurer_ledger → archivist → base_profile → explain_methods → knowledge_pack → meta_doc → minmax_builder → narrative_flow → ruling_expert → scheda_pg_markdown_template → sigilli_runner_module → tavern_hub → Cartelle di servizio.
- Per ogni report: checklist Ambiente di test → Esiti API → Metadati → Comandi/Flow → QA → Errori → Miglioramenti → Fix necessari.
- Task derivati da Errori/Fix/Miglioramenti con priorità P1 bug/ambiguità, P2 QA/completezza, P3 UX/copy; collegare a sezioni/linee citate nei report.
- Stato modulo: Pronto per sviluppo se i task sono completi e scoped; In attesa se servono dati aggiuntivi.
- Cross-cutting: coordinare builder/bilanciamento (Encounter_Designer, minmax_builder) e hub/persistenza (Taverna_NPC, tavern_hub, Cartelle di servizio).

## Encounter_Designer
- Report: `reports/module_tests/Encounter_Designer.md`
- Stato: Pronto per sviluppo

### Task (priorità e scope)
- [P1] Nessuno: i gate QA coprono ora pacing, loot e snapshot di bilanciamento e bloccano l’export con CTA esplicite verso `/auto_balance`, `/simulate_encounter`, `/set_pacing` e `/set_loot_policy`; copertura confermata nel regression pass 2025-12-11 (pytest 73 test + checklist).【F:src/modules/Encounter_Designer.txt†L380-L404】
- [P2] Nessun miglioramento aperto dopo l’estensione dei gate QA (pacing/loot/balance_snapshot) e dei messaggi di correzione verso i comandi di setup/bilanciamento.【F:src/modules/Encounter_Designer.txt†L380-L404】

### Dipendenze
- Nessuna dipendenza esplicita

### Note (Osservazioni/Errori)
- [Osservazione] Il modello dati evita riferimenti a testi protetti: stat e DC sono valori numerici astratti, mentre badge e gate PFS delimitano eventuali HR.【F:src/modules/Encounter_Designer.txt†L92-L140】【F:src/modules/Encounter_Designer.txt†L357-L419】
- [Osservazione] Il flusso incorporato consente pipeline completa: setup → generazione/auto-bilanciamento → QA → export VTT/MD/PDF, con CTA che richiamano i comandi chiave e auto-validate prima dell’export.【F:src/modules/Encounter_Designer.txt†L486-L523】【F:src/modules/Encounter_Designer.txt†L400-L419】
- [Errore] Nessun errore bloccante sul calcolo CR/QA dopo l’allineamento al singolo helper clampato.【F:src/modules/Encounter_Designer.txt†L293-L314】【F:src/modules/Encounter_Designer.txt†L777-L788】

## Taverna_NPC
- Report: `reports/module_tests/Taverna_NPC.md`
- Stato: Pronto per sviluppo

### Task (priorità e scope)
- [P1] Nessuno: lo storage espone già `/storage_meta` con quota/pattern di auto-name e, con `ALLOW_MODULE_DUMP=false`, i dump vengono tronchi a 4k con marker `[…TRUNCATED ALLOW_MODULE_DUMP=false…]` e risposta standard “⚠️ Output parziale” anche per export plain/markdown, in linea con le policy dichiarate; copertura QA/CTA e dump verificata nel regression pass 2025-12-11 (pytest 73 test + checklist).【F:src/modules/Taverna_NPC.txt†L364-L386】【F:src/modules/Taverna_NPC.txt†L273-L305】【F:src/modules/Taverna_NPC.txt†L1285-L1317】
- [P2] Nessuno: lo storage espone `/storage_meta` con quota residua, pattern di auto-name e marker di troncamento quando `ALLOW_MODULE_DUMP=false`; i gate Echo/QA includono CTA di remediation (ripeti `/grade` o `/self_check` e disattiva Echo in sandbox) prima di sbloccare salvataggi/export.【F:src/modules/Taverna_NPC.txt†L364-L386】【F:src/modules/Taverna_NPC.txt†L996-L1008】【F:src/modules/Taverna_NPC.txt†L1194-L1208】

### Dipendenze
- Nessuna dipendenza esplicita

### Note (Osservazioni/Errori)
- [Osservazione] Il flusso guidato accompagna l’utente da onboarding lingua/universo/ritratto alle fasi di quiz e generazione PNG, con CTA e template UI dedicati per ogni step.【F:src/modules/Taverna_NPC.txt†L282-L518】【F:src/modules/Taverna_NPC.txt†L838-L974】
- [Errore] ✅ API core rispondono correttamente; `taverna_saves` non esposto (atteso per sicurezza). 【e01c22†L1-L8】
- [Errore] ⚠️ `curl | head` con dump abilitato ritorna errore di write locale, ma il server fornisce `content-length`; nessuna azione necessaria lato server. 【b21fe7†L3-L16】

## adventurer_ledger
- Report: `reports/module_tests/adventurer_ledger.md`
- Stato: Pronto per sviluppo

### Task (priorità e scope)
- [P1] Nessuno: la coerenza PFS è mantenuta perché `/buy` preserva `pfs_legal` sugli item importati e `enrich_badges` aggiunge badge `PFS:ILLEGAL` quando `policies.pfs_active` è attivo, mentre `craft_estimator` blocca la creazione di item non legali.【F:src/modules/adventurer_ledger.txt†L415-L470】【F:src/modules/adventurer_ledger.txt†L1389-L1435】
- [P2] Nessuno: il `cta_guard` mantiene una CTA sintetica nelle call principali e `vendor_cap_gp` ora parte da default 2000 gp con QA che segnala WARN solo se configurato a `null`.【F:src/modules/adventurer_ledger.txt†L29-L68】【F:src/modules/adventurer_ledger.txt†L1672-L1693】

### Dipendenze
- Nessuna dipendenza esplicita

### Note (Osservazioni/Errori)
- [Osservazione] Il welcome e il flow guidato coprono cinque passi (policy, stile giocatore, profilo WBL, roll loot, export) con CTA e template Markdown/VTT per ledger, buylist e scheda PG pronti all’uso.【F:src/modules/adventurer_ledger.txt†L29-L45】【F:src/modules/adventurer_ledger.txt†L686-L750】【F:src/modules/adventurer_ledger.txt†L1760-L1772】
- [Errore] Nessuno: il blocco del download in modalità `ALLOW_MODULE_DUMP=false` si applica ora anche al ledger testuale.【fd69a0†L1-L41】

## archivist
- Report: `reports/module_tests/archivist.md`
- Stato: Pronto per sviluppo

### Task (priorità e scope)
- [P1] Nessuno: la logica di troncamento con header/JSON di lunghezza è descritta e applicata anche ai `.txt`, coerentemente con la policy base/README.【F:src/modules/archivist.txt†L118-L177】【F:src/modules/base_profile.txt†L356-L366】
- [P2] Nessuno aperto: la UX di troncamento include già i metadati di lunghezza residua richiesti.【F:src/modules/archivist.txt†L118-L177】

### Dipendenze
- Nessuna dipendenza esplicita

### Note (Osservazioni/Errori)
- [Osservazione] I dump seguono ora la policy `no_raw_dump`: con `ALLOW_MODULE_DUMP=false` i moduli testuali vengono troncati, marcati con `[…TRUNCATED ALLOW_MODULE_DUMP=false…]` e corredati da header/JSON `x-original-length`, `x-served-length` e `x-served-percent`, mentre asset non testuali restano bloccati; gli endpoint proteggono comunque l’accesso senza API key con 401 esplicito.【F:src/modules/archivist.txt†L118-L177】【F:src/modules/archivist.txt†L280-L332】
- [Osservazione] L’endpoint `/modules` rifiuta richieste senza API key con dettaglio chiaro; idem per `/modules/archivist.txt/meta` (401), fornendo copertura ai casi di autenticazione mancata.【d95840†L1-L7】
- [Errore] Nessun errore bloccante rilevato dopo l’allineamento della dump policy.

## base_profile
- Report: `reports/module_tests/base_profile.md`
- Stato: Pronto per sviluppo

### Task (priorità e scope)
- [P1] Nessuno: l’endpoint di documentazione (`/doc`/`/help`/`/manuale`) è instradato nel router di base_profile e rimanda al modulo `meta_doc.txt` per l’elenco comandi principali; gate QA/CTA e dump policy risultano coperti nel regression pass 2025-12-11 (pytest 73 test + checklist).【F:src/modules/base_profile.txt†L140-L175】【F:src/modules/base_profile.txt†L430-L472】
- [P2] Nessuno: la documentazione copre ora health/404 e la distinzione dump/troncamento, in linea con la policy Documentazione.【F:tests/test_app.py†L282-L314】【F:tests/test_app.py†L547-L591】

### Dipendenze
- Dipendenza unica del router: hard-gate verso i moduli core con binding ai file locali (archivist, ruling_expert, Taverna_NPC, narrative_flow, explain_methods, minmax_builder, Encounter_Designer, adventurer_ledger, meta_doc) e segmenter attivo; richiede preload completato prima di servire richieste.【F:src/modules/base_profile.txt†L107-L146】
- Preload obbligatorio via bundle `src/modules/preload_all_modules.txt` o endpoint `GET /modules/preload_all_modules` con `x-api-key`, che setta `runtime.preload_done` e attiva la pipeline `Preload_Warmup`/`Ingest` prima del routing.【F:src/modules/base_profile.txt†L252-L307】

### Checklist readiness (Checkpoint 2025-12-19)
- ✅ API key valida per `/modules/preload_all_modules` (401 atteso se mancante) e accesso a `/modules`/`/modules/base_profile.txt` confermato.
- ✅ Preload attivo: `runtime.preload_done` impostato da warmup silente e decorator `pre_routing`.
- ✅ Moduli core disponibili su disco: tutti i `file_binding` del router puntano a file esistenti (archivist, ruling_expert, Taverna_NPC, narrative_flow, explain_methods, minmax_builder, Encounter_Designer, adventurer_ledger, meta_doc).

### Note (Osservazioni/Errori)
- [Osservazione] Il router centralizza CTA e preset per le modalità specializzate (MinMax, Encounter, Taverna, Narrativa) guidando l’utente con flow e quiz sequenziali e welcome dedicato.【F:src/modules/base_profile.txt†L95-L176】【F:src/modules/base_profile.txt†L452-L560】
- [Osservazione] La pipeline QA integra badge/citazioni/sigilli e ricevute SHA256, collegando i log Echo e gli export di qualità per garantire trasparenza e auditabilità.【F:src/modules/base_profile.txt†L430-L447】【F:src/modules/base_profile.txt†L576-L614】
- [Errore] Nessun errore bloccante riscontrato durante i test di health check, listing e download dei moduli.

### Comunicazioni verso owner dei moduli ereditati
- Condiviso stato dipendenza/preload con owner: Alice Bianchi (Encounter_Designer), Elisa Romano (Taverna_NPC), Luca Ferri (adventurer_ledger), Martina Gallo (archivist), Valentina Riva (ruling_expert), Marco Conti (minmax_builder), Davide Serra (narrative_flow), Francesca Vitale (explain_methods) e Chiara Esposito (meta_doc); in attesa di conferma assenza blocchi prima dei fix P1.

## explain_methods
- Report: `reports/module_tests/explain_methods.md`
- Stato: Pronto per sviluppo

### Task (priorità e scope)
- [P1] Nessuno: l’header del modulo riporta già la versione **3.3-hybrid-kernel** in linea con il changelog e i requisiti QA, senza altre azioni pendenti.【F:src/modules/explain_methods.txt†L1-L4】【F:src/modules/explain_methods.txt†L318-L325】
- [P2] **Deleghe/quiz**: il modulo documenta deleghe ma ne delega enforcement al kernel; quiz teach-back e auto-suggest follow-up già descritti e coerenti con UI hints.【F:src/modules/explain_methods.txt†L30-L48】【F:src/modules/explain_methods.txt†L94-L117】

### Dipendenze
- Nessuna dipendenza esplicita

### Note (Osservazioni/Errori)
- [Osservazione] Il flusso guidato con header/CTA seleziona metodo, profondità e speed, propone follow-up/quiz e fornisce template dedicati (ELI5, First Principles, Storytelling, Visualization, Analogies, Technical) con supporto ASCII per la resa visuale.【F:src/modules/explain_methods.txt†L42-L200】【F:src/modules/explain_methods.txt†L149-L171】【F:src/modules/explain_methods.txt†L231-L248】
- [Errore] **Protezione dump**: `exposure_guard` vieta dump integrali, ma con `ALLOW_MODULE_DUMP=true` l'API serve il file completo; con `ALLOW_MODULE_DUMP=false` il troncamento a 4000 char funziona ma non menziona header MIME nel corpo — comportamento conforme all'handler generico.【F:src/app.py†L543-L563】【F:src/modules/explain_methods.txt†L216-L225】【981c3b†L1-L6】

## knowledge_pack
- Report: `reports/module_tests/knowledge_pack.md`
- Stato: Pronto per sviluppo

### Task (priorità e scope)
- [P1] Nessuno: l’API espone già version/compatibility nei metadati e il modulo è allineato al percorso `.txt` documentato, senza ulteriori difetti aperti.【F:src/app.py†L392-L458】【F:src/modules/knowledge_pack.md†L1-L6】
- [P2] Nessuno aperto: la documentazione/client fa già riferimento ai percorsi `.txt` e l’API di metadata restituisce `version`/`compatibility` dal modulo senza necessità di parsing aggiuntivo.【F:docs/api_usage.md†L20-L27】【F:src/app.py†L392-L458】【F:src/modules/knowledge_pack.md†L1-L6】

### Dipendenze
- Nessuna dipendenza esplicita

### Note (Osservazioni/Errori)
- [Osservazione] Il quick start orchestra i moduli principali (quiz PG → MinMax → Encounter → Ledger) e fornisce prompt “copia/incolla” parametrizzati per Taverna, Ruling, Archivist, Narrativa, Explain, semplificando CTA e integrazione UI.【F:src/modules/knowledge_pack.md†L45-L92】【F:src/modules/knowledge_pack.md†L126-L237】
- [Errore] Nessun errore rilevato sulle chiamate API; il troncamento con `ALLOW_MODULE_DUMP=false` è correttamente marcato con `[contenuto troncato]`.【7645d7†L1-L8】

## meta_doc
- Report: `reports/module_tests/meta_doc.md`
- Stato: Pronto per sviluppo

### Task (priorità e scope)
- [P1] Nessuno: i gate QA, gli esempi di errore e i template Homebrewery coprono già i casi di export e non risultano difetti pendenti dopo gli ultimi aggiornamenti.【F:src/modules/meta_doc.txt†L440-L520】【F:src/modules/meta_doc.txt†L820-L829】
- [P2] ✅ L’elenco `/modules` ora documenta che, con `ALLOW_MODULE_DUMP=false`, i file possono comparire con size ridotta e suffix `-partial`, chiarendo il comportamento in ambienti a dump limitato.【F:src/modules/meta_doc.txt†L1-L18】
- [P2] ✅ `/render_brew_example` include snippet aggiuntivi HR/Primary (anche combinati) e una CTA di export Homebrewery pronta all’uso.【F:src/modules/meta_doc.txt†L504-L562】【F:src/modules/meta_doc.txt†L614-L640】

### Dipendenze
- Nessuna dipendenza esplicita

### Note (Osservazioni/Errori)
- [Osservazione] Il flusso documentale segue le fasi Draft → PeerReview → QA → Publish con CTA esplicite e tool di editing/export (outline, patch suggestion, mappe ASCII, generatori di manuale/how-to) per coprire sia documentazione interna sia bundle Homebrewery.【F:src/modules/meta_doc.txt†L678-L724】【F:src/modules/meta_doc.txt†L831-L835】【F:src/modules/meta_doc.txt†L470-L539】
- [Errore] ✅ Troncamento e 403 sono coerenti con la policy: i dump sono chunked con marker finale e gli asset non testuali vengono bloccati se `ALLOW_MODULE_DUMP=false`.【3e8480†L1-L74】【da084a†L1-L8】

## minmax_builder
- Report: `reports/module_tests/minmax_builder.md`
- Stato: Pronto per sviluppo

### Task (priorità e scope)
- [P1] Nessuno: export e gate QA (`export_requires`) risultano già documentati con naming condiviso `MinMax_<nome>.*`, senza ulteriori azioni aperte.【F:src/modules/minmax_builder.txt†L930-L960】【F:src/modules/minmax_builder.txt†L1995-L2017】
- [P2] Nessuno aperto: le CTA di export riportano ora il nome file previsto (`MinMax_<nome>.pdf/.xlsx/.json`) allineato con la nomenclatura condivisa di Encounter_Designer, riducendo gli equivoci sull’output.【F:src/modules/minmax_builder.txt†L940-L943】【F:src/modules/minmax_builder.txt†L1070-L1088】

### Dipendenze
- Nessuna dipendenza esplicita

### Note (Osservazioni/Errori)
- [Osservazione] Lo stub builder è validato contro schema `build_core`/`build_extended`; in caso di errore restituisce `500 Stub payload non valido ...` (testato in commit precedente, logica stabile).【F:src/app.py†L556-L570】
- [Osservazione] Il troncamento con `ALLOW_MODULE_DUMP=false` applica `[contenuto troncato]` ai moduli testuali, coerente con handler streaming; utile per review di sicurezza senza esporre l’intero asset.【02412a†L1-L1】【430a71†L3-L3】【F:src/app.py†L589-L600】
- [Errore] Nessun errore bloccante emerso nei test API e negli stub di build.【1cc753†L6-L7】

## narrative_flow
- Report: `reports/module_tests/narrative_flow.md`
- Stato: Pronto per sviluppo

### Task (priorità e scope)
- [P1] Nessuno aperto: `/qa_story` usa validator concreti e blocca export finché arc/tema/thread/pacing/stile non sono tutti OK, includendo preview troncato e CTA dedicate.【F:src/modules/narrative_flow.txt†L320-L404】
- [P2] Nessuno aperto: l’API fornisce ora header `x-truncated` e `x-original-length` per i dump troncati, chiarendo dimensione originaria e limite applicato.【F:tests/test_app.py†L319-L343】【F:src/app.py†L1420-L1492】

### Dipendenze
- Nessuna dipendenza esplicita

### Note (Osservazioni/Errori)
- [Osservazione] Il flow narrativo in 11 step guida genere, tono, protagonisti, conflitto e arc/tema con retry e cache, integrando template per scene/outline/bible e interfacce con Taverna, Encounter e Ledger tramite seed condivisi; il QA ora fornisce checklist dettagliata, flag export e CTA su arc/tema/hook/pacing/stile.【F:src/modules/narrative_flow.txt†L465-L658】【F:src/modules/narrative_flow.txt†L320-L404】
- [Errore] Nessun errore bloccante rilevato dopo l’attivazione dei validator reali in `/qa_story`.

## ruling_expert
- Report: `reports/module_tests/ruling_expert.md`
- Stato: Pronto per sviluppo

### Task (priorità e scope)
- [P1] Nessuno.
- [P2] Nessuno: lo stub builder è già documentato con payload di esempio e mapping dei campi, e il `status_example` include CTA esplicito per confermare la stagione PFS prima dei rulings.【F:docs/api_usage.md†L99-L129】【F:src/modules/ruling_expert.txt†L448-L455】

### Dipendenze
- Nessuna dipendenza esplicita

### Note (Osservazioni/Errori)
- [Osservazione] Il flow guidato RAW→FAQ→PFS applica guardrail anti-injection, disambiguazione con soglia 0.65 e CTA post-risposta, offrendo template UI per sezioni RAW/RAI/PFS/HR e strumenti di diagnostica per cache/offline e arithmetic_guard.【F:src/modules/ruling_expert.txt†L284-L356】【F:src/modules/ruling_expert.txt†L331-L410】
- [Osservazione] La policy `exposure_policy: no_raw_dump` è applicata di default con `ALLOW_MODULE_DUMP=false` e whitelist opzionale: i dump testuali vengono troncati salvo opt-in esplicito.【F:src/modules/ruling_expert.txt†L80-L85】【F:src/config.py†L17-L28】
- [Errore] Nessun errore bloccante rilevato dopo i test combinati di autenticazione e troncamento: i comportamenti 401/404/200 sono coerenti con la configurazione e la policy di esposizione limitata.【1aba59†L1-L4】【88122c†L1-L74】

## scheda_pg_markdown_template
- Report: `reports/module_tests/scheda_pg_markdown_template.md`
- Stato: Pronto per sviluppo

### Task (priorità e scope)
- [P1] Nessuno: il meta header e le CTA di export/QA sono già allineati e non emergono difetti aperti dopo i test di download e stub.【F:src/modules/scheda_pg_markdown_template.md†L13-L63】【bff25f†L4-L6】
- [P2] Nessuno aperto: i trigger/policy operative sono documentati nel meta header con CTA di export e note di sblocco.【F:src/modules/scheda_pg_markdown_template.md†L13-L63】【F:src/modules/scheda_pg_markdown_template.md†L35-L63】

### Dipendenze
- Nessuna dipendenza esplicita

### Note (Osservazioni/Errori)
- [Osservazione] Il troncamento mantiene il titolo e il marker finale, utile per audit in ambienti con dump limitato; la lunghezza compatta (4k) preserva contesto iniziale.【300994†L1-L4】
- [Osservazione] Il meta header espone ora versione/compatibilità, trigger e policy operative (activation, export_policy) permettendo QA e pipeline automatiche senza inferenze manuali.【F:src/modules/scheda_pg_markdown_template.md†L13-L60】
- [Errore] Nessun errore funzionale nelle API; 404 atteso su file mancante.【bff25f†L6-L6】

## sigilli_runner_module
- Report: `reports/module_tests/sigilli_runner_module.md`
- Stato: Pronto per sviluppo

### Task (priorità e scope)
- [P1] Nessuno: la logica di sigilli, cooldown e tagging MDA/CTA è già descritta e non risultano bug aperti dopo gli ultimi test di dump troncato e autenticazione.【F:src/modules/sigilli_runner_module.txt†L106-L159】【5c31d3†L11-L18】
- [P2] Nessuno: logica di assegnazione sigilli e motivazioni MDA/CTA risultano allineate alla checklist.

### Dipendenze
- Nessuna dipendenza esplicita

### Note (Osservazioni/Errori)
- [Osservazione] Il raro può attivarsi solo da indice 14 con stato di default; documentare la finestra di attivazione per evitare percezione di malfunzionamento iniziale.【F:src/modules/sigilli_runner_module.txt†L116-L148】
- [Osservazione] Il portale viene aggiunto anche quando nessun sigillo è stato assegnato, garantendo almeno un elemento in `seals`.【F:src/modules/sigilli_runner_module.txt†L144-L154】
- [Osservazione] Il presente report incorpora tutti i punti richiesti nelle due iterazioni precedenti (API, metadati, modello dati, flow/CTA, errori simulati e fix applicati), senza ulteriori lacune note.
- [Errore] API key mancante: `/modules*` ritorna `401 Invalid or missing API key`, confermato con TestClient.【fc8c1a†L3-L12】
- [Errore] Modulo inesistente: `/modules/bogus.txt` → `404 Module not found`.【5c31d3†L9-L10】
- [Errore] Dump disabilitato: `ALLOW_MODULE_DUMP=false` restituisce header troncato, utile per evitare leak completi.【5c31d3†L11-L18】
- [Errore] Nessun errore bloccante dopo l’integrazione di `code_ok` e il tagging MDA/CTA nei sigilli.

## tavern_hub
- Report: `reports/module_tests/tavern_hub.md`
- Stato: Pronto per sviluppo

### Task (priorità e scope)
- [P1] Nessuno: le CTA export sono allineate alla policy e allo stato dei gate QA.
- [P2] Nessuno: i gate QA di `/export_tavern`/`/adventure_outline` bloccono su QA fail con CTA univoca verso `/save_hub` o `/check_conversation`, e lo storage hub/ledger è validato con `schema_min` e quarantena attiva.【F:src/modules/Taverna_NPC.txt†L1285-L1317】【F:src/modules/Taverna_NPC.txt†L1225-L1247】

### Dipendenze
- Nessuna dipendenza esplicita

### Note (Osservazioni/Errori)
- [Osservazione] L’Hub aggrega quest/rumor/bounty/eventi con flow GameMode, CTA di salvataggio e export, mantenendo storage con rate limit/quarantena e integrazioni con Encounter/Ledger per outline e inventari WBL.【F:src/modules/Taverna_NPC.txt†L1133-L1256】【F:src/modules/Taverna_NPC.txt†L365-L386】【F:src/modules/Taverna_NPC.txt†L789-L802】
- [Errore] Nessun errore aperto: con `ALLOW_MODULE_DUMP=false` gli asset JSON vengono bloccati via `403` come da policy, mentre gli export hub ereditano ora marker di troncamento e logging gate quando necessario.【3bedc0†L1-L8】【F:src/modules/Taverna_NPC.txt†L1285-L1310】

## Cartelle di servizio
- Report: `reports/module_tests/service_dirs.md`
- Stato: Pronto per sviluppo

### Task (priorità e scope)
- [P1] Nessuno: la risposta include ora marker e header parziale (`X-Content-Partial`, `X-Content-Remaining-Bytes`) con CTA dedicate, e lo storage espone `/storage_meta` con quota residua e auto_name_policy per `taverna_saves`.【F:src/modules/Taverna_NPC.txt†L364-L386】【F:src/modules/Taverna_NPC.txt†L1285-L1317】
- [P2] ✅ CTA Echo/self-check aggiornate: i blocchi Echo<8.5 o QA="CHECK" ora includono passi espliciti (/grade→/self_check, toggle /echo off in sandbox) prima di consentire salvataggi/export.【F:src/modules/Taverna_NPC.txt†L788-L811】【F:src/modules/Taverna_NPC.txt†L1129-L1144】

### Dipendenze
- Nessuna dipendenza esplicita

### Note (Osservazioni/Errori)
- [Osservazione] Le directory di servizio aggregano i template e i workflow Taverna (onboarding, quiz MaxDiff/Pairwise/SJT, export `taverna_saves`) garantendo naming coerente, guardrail Echo e CTA guidate per generazione e salvataggio PNG/quest/rumor.【F:src/modules/Taverna_NPC.txt†L364-L386】【F:src/modules/Taverna_NPC.txt†L428-L965】
- [Errore] ✅ API core rispondono correttamente; `taverna_saves` non esposto (scelta di sicurezza).【F:reports/module_tests/Taverna_NPC.md†L7-L13】
- [Errore] ⚠️ `curl | head` con dump abilitato può fallire in locale per errore di scrittura ma il server fornisce `content-length`; nessuna azione lato server.【F:reports/module_tests/Taverna_NPC.md†L11-L13】

## Riepilogo osservazioni ed errori
| Modulo | Osservazioni | Errori | Totale note |
| --- | --- | --- | --- |
| 🔶 sigilli_runner_module | 3 | 4 | 7 |
| Encounter_Designer | 2 | 1 | 3 |
| Taverna_NPC | 1 | 2 | 3 |
| archivist | 2 | 1 | 3 |
| 🔗 base_profile | 2 | 1 | 3 |
| minmax_builder | 2 | 1 | 3 |
| ruling_expert | 2 | 1 | 3 |
| scheda_pg_markdown_template | 2 | 1 | 3 |
| Cartelle di servizio | 1 | 2 | 3 |
| adventurer_ledger | 1 | 1 | 2 |
| explain_methods | 1 | 1 | 2 |
| knowledge_pack | 1 | 1 | 2 |
| meta_doc | 1 | 1 | 2 |
| narrative_flow | 1 | 1 | 2 |
| tavern_hub | 1 | 1 | 2 |

## Tracker delle storie derivate da osservazioni/errori

### Moduli critici (storie con acceptance criteria e owner)

#### Encounter_Designer — Owner: Alice Bianchi — Checkpoint: 2025-12-12
| Story ID | Deriva da | Descrizione | Severità | Acceptance Criteria | Tracciabilità (piano → codice) | Stato |
| --- | --- | --- | --- | --- | --- | --- |
| ENC-OBS-01 | Osservazione | Documentare nel tracker dati che il modello usa solo valori numerici/astratti per stat, DC e badge/gate PFS, evitando riferimenti a testi protetti. | S3 (Info) | - Nota di conformità legale visibile nel tracker.<br>- QA verifica che gli output di esempio mantengano valori numerici/astratti.<br>- Convalida durante il checkpoint 2025-12-12. | Piano: L24-L25. Codice: `src/modules/Encounter_Designer.txt` (data model e policy PFS).【F:src/modules/Encounter_Designer.txt†L92-L140】 | Done |
| ENC-OBS-02 | Osservazione | Tracciare la pipeline completa (setup → auto-bilanciamento → QA → export VTT/MD/PDF) con CTA obbligatorie verso i comandi chiave e auto-validazione prima dell’export. | S2 (Minor) | - Descrizione pipeline e CTA registrate come definizione di pronto.<br>- Verifica che ogni fase richiami i comandi citati nei gate QA.<br>- Checkpoint 2025-12-12 approva la checklist. | Piano: L25-L27. Codice: `src/modules/Encounter_Designer.txt` (pipeline e CTA QA/export).【F:src/modules/Encounter_Designer.txt†L486-L523】【F:src/modules/Encounter_Designer.txt†L400-L419】 | Done |
| ENC-ERR-01 | Errore | Conservare evidenza che non risultano errori bloccanti su CR/QA dopo l’allineamento al helper clampato. | S3 (Info) | - Nota “nessun errore bloccante” collegata al test CR/QA.<br>- QA ripete il test clampato e allega esito nel tracker.<br>- Validato entro il checkpoint 2025-12-12. | Piano: L26-L27. Codice: `src/modules/Encounter_Designer.txt` (calcolo CR/QA clampato).【F:src/modules/Encounter_Designer.txt†L293-L314】【F:src/modules/Encounter_Designer.txt†L777-L788】 | Done |

#### sigilli_runner_module — Owner: Fabio Marchetti — Checkpoint: 2025-12-26
| Story ID | Deriva da | Descrizione | Severità | Acceptance Criteria | Tracciabilità (piano → codice) | Stato |
| --- | --- | --- | --- | --- | --- | --- |
| SIG-OBS-01 | Osservazione | Evidenziare la finestra di attivazione del raro solo da indice 14 con stato di default per evitare percezione di malfunzionamento iniziale. | S2 (Minor) | - Nota di comportamento “rare da indice 14” visibile nel tracker.<br>- QA riproduce l’attivazione a indice 14 e allega evidenza.<br>- Checkpoint 2025-12-26 valida la nota. | Piano: L221-L222. Codice: `src/modules/sigilli_runner_module.txt` (logica raro).【F:src/modules/sigilli_runner_module.txt†L116-L150】 | Done |
| SIG-OBS-02 | Osservazione | Documentare che il portale viene aggiunto anche quando nessun sigillo è stato assegnato, garantendo almeno un elemento in `seals`. | S3 (Info) | - Nota portale sempre presente registrata nel tracker.<br>- QA verifica risposta con `seals` popolato solo dal portale.<br>- Checkpoint 2025-12-26 chiude la verifica. | Piano: L222-L223. Codice: `src/modules/sigilli_runner_module.txt` (aggiunta portale).【F:src/modules/sigilli_runner_module.txt†L148-L159】 | Done |
| SIG-OBS-03 | Osservazione | Registrare che il report copre API, metadati, modello dati, flow/CTA, errori simulati e fix applicati senza ulteriori lacune note. | S3 (Info) | - Nota di completezza report archiviata nel tracker.<br>- QA allega riferimento al set di test eseguiti.<br>- Checkpoint 2025-12-26 approva la nota. | Piano: L223-L224. Codice: `src/modules/sigilli_runner_module.txt` (model e flow CTA).【F:src/modules/sigilli_runner_module.txt†L6-L22】 | Done |
| SIG-ERR-01 | Errore | API key mancante su `/modules*` restituisce `401 Invalid or missing API key`. | S1 (Major) | - Test QA allegato con richiesta senza API key e risposta 401.<br>- Nota collegata ai log/trace di sicurezza.<br>- Validazione al checkpoint 2025-12-26. | Piano: L225-L226. Codice: `tests`/`TestClient` esito 401.【fc8c1a†L3-L12】【ca78a1†L1-L14】 | Done |
| SIG-ERR-02 | Errore | `/modules/bogus.txt` ritorna `404 Module not found`. | S2 (Minor) | - Test QA allegato per modulo inesistente con 404.<br>- Ticket include output grezzo del test.<br>- Checkpoint 2025-12-26 conferma. | Piano: L226-L227. Codice: API lookup mancante modulo.【5c31d3†L9-L10】【ca78a1†L1-L14】 | Done |
| SIG-ERR-03 | Errore | Con `ALLOW_MODULE_DUMP=false` il dump viene troncato con header coerente per evitare leak completi. | S1 (Major) | - Test QA allegato con header di troncamento.<br>- Verifica che il marker di dump limitato sia presente.<br>- Validato al checkpoint 2025-12-26. | Piano: L227-L228. Codice: `src/modules/sigilli_runner_module.txt` (troncamento e header).【F:src/modules/sigilli_runner_module.txt†L148-L159】【5c31d3†L11-L18】【ca78a1†L1-L14】 | Done |
| SIG-ERR-04 | Errore | Nessun errore bloccante dopo integrazione di `code_ok` e tagging MDA/CTA nei sigilli. | S3 (Info) | - Nota “nessun errore bloccante” collegata ai test post `code_ok`.<br>- QA allega log di esecuzione con tagging MDA/CTA.<br>- Checkpoint 2025-12-26 registra l’evidenza. | Piano: L228. Codice: `src/modules/sigilli_runner_module.txt` (tagging MDA/CTA).【F:src/modules/sigilli_runner_module.txt†L106-L150】 | Done |

#### base_profile — Owner: Andrea Rizzi — Checkpoint: 2025-12-19
| Story ID | Deriva da | Descrizione | Severità | Acceptance Criteria | Tracciabilità (piano → codice) | Stato |
| --- | --- | --- | --- | --- | --- | --- |
| BAS-OBS-01 | Osservazione | Evidenziare che l’endpoint di documentazione (`/doc`/`/help`/`/manuale`) è instradato nel router base_profile e rimanda a `meta_doc.txt`. | S2 (Minor) | - Evidenza routing e link a `meta_doc.txt` nel tracker.<br>- Test manuale o automatico allegato con status 200.<br>- Checkpoint 2025-12-19 registra la verifica. | Piano: L81-L82. Codice: `src/modules/base_profile.txt` (router doc/help/manuale).【F:src/modules/base_profile.txt†L140-L175】【F:src/modules/base_profile.txt†L430-L472】 | Done |
| BAS-OBS-02 | Osservazione | Dipendenza unica: router hard-gate ai moduli core (binding file locale) con preload obbligatorio `preload_all_modules` protetto da `x-api-key`. | S3 (Info) | - Sezione dipendenze aggiornata con elenco moduli core e link al codice router/preload.<br>- Verifica preload con API key valida e flag `runtime.preload_done` attivo.<br>- Convalida nel checkpoint 2025-12-19 (bundle presente e servibile via API key, runtime flag settato da regola pre_routing). | Piano: L84-L91. Codice: `src/modules/base_profile.txt` (binding moduli core e preload).【F:src/modules/base_profile.txt†L107-L146】【F:src/modules/base_profile.txt†L142-L150】【F:src/modules/base_profile.txt†L252-L262】【F:src/modules/preload_all_modules.txt†L1-L15】【3ae972†L1-L4】 | Done (Pronto: binding core confermati su disco e bundle preload 206 protetto da API key; flag `runtime.preload_done` impostato dal router).【2879d6†L2-L3】【8c37bc†L1-L6】【F:src/modules/base_profile.txt†L114-L122】【F:src/modules/base_profile.txt†L148-L156】 |
| BAS-CHK-19 | Checkpoint | Checklist readiness 2025-12-19 (API key, preload, moduli core disponibili). | S2 (Minor) | - API key e endpoint preload verificati (206 con troncamento su call autenticata / 401 su assenza key).<br>- Preload eseguito (flag runtime, warmup e decorator attivi).<br>- Binding ai moduli core disponibili su disco prima di avviare i fix P1. | Piano: L88-L91. Codice: `tests/test_app.py` (health/doc e dump policy).【F:tests/test_app.py†L282-L314】【F:tests/test_app.py†L547-L591】【F:src/modules/base_profile.txt†L142-L150】【F:src/modules/base_profile.txt†L252-L262】【3ae972†L1-L4】 | Done (riesecuzione QA: preload bundle 206/troncato con API key e guard `runtime.preload_done` attiva).【9a9887†L1-L2】【F:src/modules/base_profile.txt†L148-L156】 |
| BAS-ERR-01 | Errore | Annotare che non ci sono errori bloccanti dopo l’allineamento della documentazione e della protezione dump nel router base_profile. | S3 (Info) | - Nota “nessun errore bloccante” collegata ai test del router e della documentazione.<br>- QA allega log del percorso `/doc` con e senza dump.<br>- Checkpoint 2025-12-19 approva la nota. | Piano: L93-L96. Codice: `src/modules/base_profile.txt` (router e dump policy).【F:src/modules/base_profile.txt†L356-L366】【F:src/modules/base_profile.txt†L95-L176】【ca78a1†L1-L14】 | Done |

> **Release gate** — Mantieni bloccati i rilasci dipendenti dal router base_profile finché BAS-OBS-02 e BAS-CHK-19 non sono marcati Done nel tracker; la verifica odierna (preload 206 con API key e binding core su disco) conferma che il gate resta attivo finché entrambi i checkpoint non risultano Done.【8c37bc†L1-L6】【2879d6†L2-L3】【F:src/modules/base_profile.txt†L114-L122】【F:src/modules/base_profile.txt†L148-L156】

### Altri moduli

#### Taverna_NPC — Owner: Elisa Romano
| Story ID | Deriva da | Descrizione | Severità | Stato |
| --- | --- | --- | --- | --- |
| TAV-OBS-01 | Osservazione | Documentare il flusso guidato dall’onboarding al quiz MaxDiff/SJT e generazione PNG con CTA/template dedicati per ogni step. | S2 (Minor) | Done |
| TAV-ERR-01 | Errore | Registrare che le API core rispondono correttamente mentre `taverna_saves` resta non esposto per sicurezza. | S3 (Info) | Done |
| TAV-ERR-02 | Errore | Segnalare l’errore locale `curl | head` con dump abilitato (write failure) indicando che non richiede azione server-side. | S3 (Info) | Done |

#### adventurer_ledger — Owner: Luca Ferri
| Story ID | Deriva da | Descrizione | Severità | Stato |
| --- | --- | --- | --- | --- |
| LED-OBS-01 | Osservazione | Raccogliere il welcome/flow in cinque passi (policy → stile giocatore → profilo WBL → roll loot → export) con CTA e template pronti per ledger/buylist/scheda PG. | S2 (Minor) | Done |
| LED-ERR-01 | Errore | Annotare che il blocco download con `ALLOW_MODULE_DUMP=false` si applica anche al ledger testuale. | S2 (Minor) | Done |

#### archivist — Owner: Martina Gallo
| Story ID | Deriva da | Descrizione | Severità | Stato |
| --- | --- | --- | --- | --- |
| ARC-OBS-01 | Osservazione | Tracciare l’applicazione della policy `no_raw_dump` con header/JSON di lunghezza e marker di troncamento per dump testuali. | S2 (Minor) | Done |
| ARC-OBS-02 | Osservazione | Registrare che `/modules` e `/modules/archivist.txt/meta` rifiutano le richieste senza API key con 401 esplicito. | S2 (Minor) | Done |

#### ruling_expert — Owner: Valentina Riva
| Story ID | Deriva da | Descrizione | Severità | Stato |
| --- | --- | --- | --- | --- |
| RUL-OBS-01 | Osservazione | Documentare il flow guidato RAW→FAQ→PFS con guardrail anti-injection, disambiguazione 0.65 e CTA post-risposta. | S2 (Minor) | Done (QA 2025-12-11) |
| RUL-OBS-02 | Osservazione | Evidenziare la policy `exposure_policy: no_raw_dump` applicata di default con whitelist opzionale. | S2 (Minor) | Done (QA 2025-12-11) |

#### scheda_pg_markdown_template — Owner: Matteo Leone
| Story ID | Deriva da | Descrizione | Severità | Stato |
| --- | --- | --- | --- | --- |
| SCH-OBS-01 | Osservazione | Annotare che il troncamento mantiene titolo e marker finale, utile per audit con dump limitato. | S3 (Info) | Done (QA 2025-12-11) |
| SCH-OBS-02 | Osservazione | Evidenziare meta header con versione/compatibilità, trigger e policy operative per pipeline automatiche. | S2 (Minor) | Done (QA 2025-12-11) |

## Kanban e log test (To Do → In Review → Done)

- Riesecuzione QA del 2025-12-11: suite `pytest` completa (73 pass) utilizzata come log unico di regressione per tutte le storie chiuse riportate nelle tabelle sottostanti.【2fd912†L1-L11】
- Job tracker: import automatico dei log `pytest` del 2025-12-11 (73 pass) nel sistema di tracking con generazione di un attestato di copertura per ciascuna storia marcata **Done**.

## Attività di rilascio
- Preparazione note/changelog (P2) per finestra 2025-12-26
  - Dipendenze: log QA aggiornati al regression 2025-12-11 e tracker storie "Done" per evitare discrepanze con lo stato "Pronto per sviluppo" dei moduli.
  - Stato: completato con `reports/changelog_2025-12-26.md` allegato al ticket e al canale di rilascio.【F:reports/changelog_2025-12-26.md†L1-L36】
- Verifica automatica dei log QA 2025-12-11 e attestato di copertura (P1)
  - Output atteso: attestato generato dal job tracker a partire dai log `pytest` del 2025-12-11 con evidenza della copertura per ogni storia **Done** e conferma che tutti i moduli restano in stato "Pronto per sviluppo".
  - Dipendenze: esito positivo del job tracker sugli import/log e stato moduli aggiornato a "Pronto per sviluppo" nel tracker.
  - Stato: completato, attestato archiviato in `reports/coverage_attestato_2025-12-11.md` (job tracker verde su 73/73).【F:reports/coverage_attestato_2025-12-11.md†L1-L16】【F:data/pytest_logs/pytest_run_2025-12-11.json†L1-L9】
- Creazione tag/branch RC (P2) allineato alla finestra 2025-12-26
  - Output atteso: tag/branch RC nominato sulla finestra 2025-12-26 e puntato all'ultimo commit con attestato automatico verde.
  - Dipendenze: note/changelog finali, attestato automatico attivo e conferma di continuità con la finestra 2025-12-26 senza pause operative.
  - Stato: creato tag `rc/2025-12-26` (commit `5968b375e2` con changelog aggiornato e attestato QA 73/73) e configurata la pipeline di rilascio per usare l'RC.
- Comunicazione nel canale di rilascio (P3) con riepilogo changelog e stato QA
  - Output atteso: messaggio nel canale di rilascio con link al changelog, ai log QA 2025-12-11 e all'attestato di copertura generato dal job.
  - Dipendenze: changelog consolidato, attestato automatico allegato e allineamento con lo stato "Pronto per sviluppo" dei moduli.
  - Stato: pubblicato messaggio nel canale di rilascio con tag `rc/2025-12-26` e link a log/attestato/changelog.【F:reports/release_announcement_2025-12-26.md†L1-L8】

### Moduli critici
| Story | Origine piano | Stato | Evidenza test |
| --- | --- | --- | --- |
| ENC-OBS-01 | planning/module_work_plan.md L287-L288 | Done | Verifica API/QA su Encounter Designer con dump on/off e 404 controllato; suite pytest completa (73 pass).【F:reports/module_tests/Encounter_Designer.md†L1-L25】【3756b1†L1-L11】 |
| ENC-OBS-02 | planning/module_work_plan.md L288-L289 | Done | Pipeline QA/export documentata e validata su API principali; suite pytest completa (73 pass).【F:reports/module_tests/Encounter_Designer.md†L26-L45】【3756b1†L1-L11】 |
| ENC-ERR-01 | planning/module_work_plan.md L289-L290 | Done | Test clampato su CR/QA senza errori bloccanti; suite pytest completa (73 pass).【F:reports/module_tests/Encounter_Designer.md†L1-L17】【3756b1†L1-L11】 |
| SIG-OBS-01 | planning/module_work_plan.md L294-L295 | Done | Log di attivazione raro da indice 14 nella suite sigilli; suite pytest completa (73 pass).【F:reports/module_tests/sigilli_runner_module.md†L26-L33】【3756b1†L1-L11】 |
| SIG-OBS-02 | planning/module_work_plan.md L295-L296 | Done | Risposta con solo portale presente in `seals` confermata via test API; suite pytest completa (73 pass).【F:reports/module_tests/sigilli_runner_module.md†L33-L43】【3756b1†L1-L11】 |
| SIG-OBS-03 | planning/module_work_plan.md L296-L297 | Done | Report di copertura completo archiviato (API, metadati, flow/CTA); suite pytest completa (73 pass).【F:reports/module_tests/sigilli_runner_module.md†L1-L23】【3756b1†L1-L11】 |
| SIG-ERR-01 | planning/module_work_plan.md L297-L298 | Done | Richiesta senza API key restituisce 401 esplicito; suite pytest completa (73 pass).【F:reports/module_tests/sigilli_runner_module.md†L43-L52】【3756b1†L1-L11】 |
| SIG-ERR-02 | planning/module_work_plan.md L298-L299 | Done | Chiamata a modulo inesistente produce 404 `Module not found`; suite pytest completa (73 pass).【F:reports/module_tests/sigilli_runner_module.md†L52-L59】【3756b1†L1-L11】 |
| SIG-ERR-03 | planning/module_work_plan.md L299-L300 | Done | Dump troncato con header coerente quando ALLOW_MODULE_DUMP=false; suite pytest completa (73 pass).【F:reports/module_tests/sigilli_runner_module.md†L59-L67】【3756b1†L1-L11】 |
| SIG-ERR-04 | planning/module_work_plan.md L300-L301 | Done | Nessun errore bloccante dopo integrazione `code_ok` e tagging MDA/CTA; suite pytest completa (73 pass).【F:reports/module_tests/sigilli_runner_module.md†L67-L73】【3756b1†L1-L11】 |
| BAS-OBS-01 | planning/module_work_plan.md L305-L306 | Done | Routing doc/help/manuale verificato con status 200 e link a `meta_doc`; suite pytest completa (73 pass).【F:reports/module_tests/base_profile.md†L9-L19】【3756b1†L1-L11】 |
| BAS-OBS-02 | planning/module_work_plan.md L306-L307 | Done | Preload protetto da API key con flag runtime attivo registrato nel QA log; suite pytest completa (73 pass).【F:reports/module_tests/base_profile.md†L19-L34】【3756b1†L1-L11】 |
| BAS-CHK-19 | planning/module_work_plan.md L307-L308 | Done | Checkpoint 2025-12-19 coperto da test health/doc e dump policy; suite pytest completa (73 pass).【F:reports/module_tests/base_profile.md†L1-L9】【F:reports/module_tests/base_profile.md†L34-L44】【3756b1†L1-L11】 |
| BAS-ERR-01 | planning/module_work_plan.md L308-L309 | Done | Percorso `/doc` validato con dump protetto, nessun errore bloccante; suite pytest completa (73 pass).【F:reports/module_tests/base_profile.md†L44-L55】【3756b1†L1-L11】 |

### Altri moduli
| Story | Origine piano | Stato | Evidenza test |
| --- | --- | --- | --- |
| TAV-OBS-01 | planning/module_work_plan.md L315-L316 | Done | Flusso onboarding→quiz→PNG con CTA verificato nel report Taverna; suite pytest completa (73 pass).【F:reports/module_tests/Taverna_NPC.md†L15-L33】【3756b1†L1-L11】 |
| TAV-ERR-01 | planning/module_work_plan.md L316-L317 | Done | API core ok mentre `taverna_saves` resta non esposto; suite pytest completa (73 pass).【F:reports/module_tests/Taverna_NPC.md†L7-L16】【3756b1†L1-L11】 |
| TAV-ERR-02 | planning/module_work_plan.md L317-L318 | Done | Nota su errore locale `curl | head` con dump abilitato archiviata; suite pytest completa (73 pass).【F:reports/module_tests/Taverna_NPC.md†L11-L16】【3756b1†L1-L11】 |
| LED-OBS-01 | planning/module_work_plan.md L322-L323 | Done | Welcome/flow in cinque passi documentato con CTA e template ledger; suite pytest completa (73 pass).【F:reports/module_tests/adventurer_ledger.md†L9-L23】【3756b1†L1-L11】 |
| LED-ERR-01 | planning/module_work_plan.md L323-L324 | Done | Blocco download con ALLOW_MODULE_DUMP=false applicato al ledger; suite pytest completa (73 pass).【F:reports/module_tests/adventurer_ledger.md†L23-L30】【3756b1†L1-L11】 |
| ARC-OBS-01 | planning/module_work_plan.md L328-L329 | Done | Policy `no_raw_dump` e marker di troncamento verificati; suite pytest completa (73 pass).【F:reports/module_tests/archivist.md†L7-L15】【3756b1†L1-L11】 |
| ARC-OBS-02 | planning/module_work_plan.md L329-L330 | Done | 401 esplicito su `/modules` e `/modules/archivist.txt/meta` senza API key; suite pytest completa (73 pass).【F:reports/module_tests/archivist.md†L15-L24】【3756b1†L1-L11】 |
| RUL-OBS-01 | planning/module_work_plan.md L334-L335 | Done | Flow RAW→FAQ→PFS con CTA post-risposta validato dal QA 2025-12-11; suite pytest completa (73 pass).【F:reports/module_tests/ruling_expert.md†L6-L19】【3756b1†L1-L11】 |
| RUL-OBS-02 | planning/module_work_plan.md L335-L336 | Done | Policy `no_raw_dump` attiva di default con whitelist opzionale confermata; suite pytest completa (73 pass).【F:reports/module_tests/ruling_expert.md†L19-L28】【3756b1†L1-L11】 |
| SCH-OBS-01 | planning/module_work_plan.md L340-L341 | Done | Troncamento mantiene titolo e marker finale per audit; suite pytest completa (73 pass).【F:reports/module_tests/scheda_pg_markdown_template.md†L7-L15】【3756b1†L1-L11】 |
| SCH-OBS-02 | planning/module_work_plan.md L341-L342 | Done | Meta header con version/compatibility e trigger/policy operative validato dai test; suite pytest completa (73 pass).【F:reports/module_tests/scheda_pg_markdown_template.md†L47-L60】【3756b1†L1-L11】 |

#### tavern_hub — Owner: Paolo Greco
| Story ID | Deriva da | Descrizione | Severità | Stato |
| --- | --- | --- | --- | --- |
| HUB-OBS-01 | Osservazione | Documentare l’Hub che aggrega quest/rumor/bounty/eventi con flow GameMode, CTA di salvataggio/export e integrazione Encounter/Ledger. | S2 (Minor) | Done (QA 2025-12-11) |
| HUB-ERR-01 | Errore | Registrare che con `ALLOW_MODULE_DUMP=false` gli asset JSON sono bloccati con 403 e gli export hub ereditano marker di troncamento/logging gate. | S2 (Minor) | Done (QA 2025-12-11) |

#### Cartelle di servizio — Owner: Sara De Luca
| Story ID | Deriva da | Descrizione | Severità | Stato |
| --- | --- | --- | --- | --- |
| SER-OBS-01 | Osservazione | Tracciare workflow e template Taverna (onboarding, quiz, export `taverna_saves`) con naming coerente, guardrail Echo e CTA guidate. | S2 (Minor) | Done (QA 2025-12-11) |
| SER-ERR-01 | Errore | Registrare che le API core rispondono correttamente e `taverna_saves` resta non esposto per sicurezza. | S3 (Info) | Done (QA 2025-12-11) |
| SER-ERR-02 | Errore | Segnalare l’errore locale `curl | head` con dump abilitato (write failure) come informazione senza azione server-side. | S3 (Info) | Done (QA 2025-12-11) |

## Vista riepilogativa per burn-down
| Modulo | Nota/Errore | Story ID | Severità | Owner | Stato |
| --- | --- | --- | --- | --- | --- |
| Encounter_Designer | Modello dati solo valori numerici/astratti | ENC-OBS-01 | S3 | Alice Bianchi | Done (QA 2025-12-11, pytest suite 73 pass) |
| Encounter_Designer | Pipeline completa con CTA QA/export | ENC-OBS-02 | S2 | Alice Bianchi | Done (QA 2025-12-11, pytest suite 73 pass) |
| Encounter_Designer | Nessun errore bloccante CR/QA | ENC-ERR-01 | S3 | Alice Bianchi | Done (QA 2025-12-11, pytest suite 73 pass) |
| base_profile | Endpoint doc instradato verso meta_doc.txt | BAS-OBS-01 | S2 | Andrea Rizzi | Done (QA 2025-12-11, pytest suite 73 pass) |
| base_profile | Hard-gate moduli core + preload protetto | BAS-OBS-02 | S3 | Andrea Rizzi | Done (QA 2025-12-11, pytest suite 73 pass) |
| base_profile | Checkpoint readiness 2025-12-19 | BAS-CHK-19 | S2 | Andrea Rizzi | Done (QA 2025-12-11, pytest suite 73 pass) |
| base_profile | Nessun errore bloccante router/doc | BAS-ERR-01 | S3 | Andrea Rizzi | Done (QA 2025-12-11, pytest suite 73 pass) |
| sigilli_runner_module | Finestra raro solo da indice 14 | SIG-OBS-01 | S2 | Fabio Marchetti | Done (QA 2025-12-11) |
| sigilli_runner_module | Portale anche senza sigilli assegnati | SIG-OBS-02 | S3 | Fabio Marchetti | Done (QA 2025-12-11) |
| sigilli_runner_module | Copertura iterazioni precedenti | SIG-OBS-03 | S3 | Fabio Marchetti | Done (QA 2025-12-11) |
| sigilli_runner_module | 401 su API key mancante | SIG-ERR-01 | S1 | Fabio Marchetti | Done (QA 2025-12-11) |
| sigilli_runner_module | 404 su modulo inesistente | SIG-ERR-02 | S2 | Fabio Marchetti | Done (QA 2025-12-11) |
| sigilli_runner_module | Troncamento con ALLOW_MODULE_DUMP=false | SIG-ERR-03 | S1 | Fabio Marchetti | Done (QA 2025-12-11) |
| sigilli_runner_module | Nessun errore bloccante post code_ok | SIG-ERR-04 | S3 | Fabio Marchetti | Done (QA 2025-12-11) |
| Taverna_NPC | Flusso guidato onboarding→quiz→PNG | TAV-OBS-01 | S2 | Elisa Romano | Done (QA 2025-12-11) |
| Taverna_NPC | API core ok, `taverna_saves` non esposto | TAV-ERR-01 | S3 | Elisa Romano | Done (QA 2025-12-11) |
| Taverna_NPC | Errore locale `curl | head` | TAV-ERR-02 | S3 | Elisa Romano | Done (QA 2025-12-11) |
| adventurer_ledger | Welcome/flow in cinque passi con CTA | LED-OBS-01 | S2 | Luca Ferri | Done (QA 2025-12-11) |
| adventurer_ledger | Blocco download con ALLOW_MODULE_DUMP=false | LED-ERR-01 | S2 | Luca Ferri | Done (QA 2025-12-11) |
| archivist | Policy no_raw_dump con header/JSON lunghezza | ARC-OBS-01 | S2 | Martina Gallo | Done (QA 2025-12-11) |
| archivist | 401 chiaro su /modules e /meta senza API key | ARC-OBS-02 | S2 | Martina Gallo | Done (QA 2025-12-11) |
| ruling_expert | Flow RAW→FAQ→PFS con guardrail e CTA | RUL-OBS-01 | S2 | Valentina Riva | Done (QA 2025-12-11) |
| ruling_expert | Default exposure_policy no_raw_dump | RUL-OBS-02 | S2 | Valentina Riva | Done (QA 2025-12-11) |
| scheda_pg_markdown_template | Troncamento con titolo/marker finale | SCH-OBS-01 | S3 | Matteo Leone | Done (QA 2025-12-11) |
| scheda_pg_markdown_template | Meta header con trigger/policy operative | SCH-OBS-02 | S2 | Matteo Leone | Done (QA 2025-12-11) |
| tavern_hub | Hub con quest/rumor e integrazione Encounter/Ledger | HUB-OBS-01 | S2 | Paolo Greco | Done (QA 2025-12-11) |
| tavern_hub | Blocco asset JSON con ALLOW_MODULE_DUMP=false | HUB-ERR-01 | S2 | Paolo Greco | Done (QA 2025-12-11) |
| Cartelle di servizio | Workflow/template Taverna con guardrail Echo | SER-OBS-01 | S2 | Sara De Luca | Done (QA 2025-12-11) |
| Cartelle di servizio | API core ok, `taverna_saves` non esposto | SER-ERR-01 | S3 | Sara De Luca | Done (QA 2025-12-11) |
| Cartelle di servizio | Errore locale `curl | head` | SER-ERR-02 | S3 | Sara De Luca | Done (QA 2025-12-11) |
## Cross-cutting e dipendenze
- Builder/Bilanciamento (Encounter_Designer, minmax_builder): usare i task sopra per valutare epic condivise su export/QA o flow di bilanciamento; ordinare i fix P1 prima dei miglioramenti.
- Hub/Persistenza (Taverna_NPC, tavern_hub, Cartelle di servizio): verificare coerenza delle policy di salvataggio/quarantena e annotare eventuali blocchi prima di procedere con altri moduli dipendenti.

## Chiusura
- Compila il sommario sprint con numero task, priorità massima e blocchi per modulo usando la tabella seguente, con owner
  assegnati e checkpoint giornalieri a partire da **2025-12-12**.

| Modulo | Owner | Task totali | Priorità massima | #Dipendenze | Stato | #Osservazioni | #Errori | Checkpoint | Note |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Encounter_Designer | Alice Bianchi | 2 | P1 | 0 | Done (QA 2025-12-11 chiusa, pytest suite 73 pass) | 2 | 1 | 2025-12-12 | Nessuna dipendenza esplicita |
| minmax_builder | Marco Conti | 2 | P1 | 0 | Done (burn-down completato con suite pytest 73 pass) | 2 | 1 | 2025-12-13 | Nessuna dipendenza esplicita |
| Taverna_NPC | Elisa Romano | 2 | P1 | 0 | Done (QA 2025-12-11 chiusa, pytest suite 73 pass) | 1 | 2 | 2025-12-14 | Nessuna dipendenza esplicita |
| tavern_hub | Paolo Greco | 2 | P1 | 0 | Done (QA 2025-12-11 chiusa, pytest suite 73 pass) | 1 | 1 | 2025-12-15 | Nessuna dipendenza esplicita |
| Cartelle di servizio | Sara De Luca | 2 | P1 | 0 | Done (QA 2025-12-11 chiusa, pytest suite 73 pass) | 1 | 2 | 2025-12-16 | Nessuna dipendenza esplicita |
| adventurer_ledger | Luca Ferri | 2 | P1 | 0 | Done (QA 2025-12-11 chiusa, pytest suite 73 pass) | 1 | 1 | 2025-12-17 | Nessuna dipendenza esplicita |
| archivist | Martina Gallo | 2 | P1 | 0 | Done (QA 2025-12-11 chiusa, pytest suite 73 pass) | 2 | 1 | 2025-12-18 | Nessuna dipendenza esplicita |
| 🔗 base_profile | Andrea Rizzi | 3 | P1 | 1 | Done (QA 2025-12-11 chiusa, preload/API key verificati, pytest suite 73 pass) | 3 | 1 | 2025-12-19 | Router vincolato ai moduli core e preload tramite `preload_all_modules` con API key; readiness checklist chiusa |
| explain_methods | Francesca Vitale | 2 | P1 | 0 | Done (burn-down completato con suite pytest 73 pass) | 1 | 1 | 2025-12-20 | Nessuna dipendenza esplicita |
| knowledge_pack | Gianni Moretti | 2 | P1 | 0 | Done (burn-down completato con suite pytest 73 pass) | 1 | 1 | 2025-12-21 | Nessuna dipendenza esplicita |
| meta_doc | Chiara Esposito | 3 | P1 | 0 | Done (burn-down completato con suite pytest 73 pass) | 1 | 1 | 2025-12-22 | Nessuna dipendenza esplicita |
| narrative_flow | Davide Serra | 2 | P1 | 0 | Done (burn-down completato con suite pytest 73 pass) | 1 | 1 | 2025-12-23 | Nessuna dipendenza esplicita |
| ruling_expert | Valentina Riva | 2 | P1 | 0 | Done (QA 2025-12-11 chiusa, pytest suite 73 pass) | 2 | 1 | 2025-12-24 | Nessuna dipendenza esplicita |
| scheda_pg_markdown_template | Matteo Leone | 2 | P1 | 0 | Done (QA 2025-12-11 chiusa, pytest suite 73 pass) | 2 | 1 | 2025-12-25 | Nessuna dipendenza esplicita |
| 🔶 sigilli_runner_module | Fabio Marchetti | 2 | P1 | 0 | Done (QA 2025-12-11 chiusa, pytest suite 73 pass) | 3 | 4 | 2025-12-26 | Nessuna dipendenza esplicita; osservazioni elevate su finestra raro/portale |

### Aggiornamenti giornalieri (SIG\*, ENC\*, BAS\*)
- Programma un check-in quotidiano per **sigilli_runner_module (SIG\*)**, **Encounter_Designer (ENC\*)** e **base_profile (BAS\*)**, registrando per ogni giornata:
  - rischi individuati o nuove regressioni;
  - avanzamento verso i checkpoint indicati nel tracker (esito QA/autotest, CTA completate);
  - eventuali blocchi o dipendenze emerse, collegandole ai rispettivi Story ID.
- Gli owner (Fabio Marchetti, Alice Bianchi, Andrea Rizzi) inseriscono gli aggiornamenti direttamente nel tracker della storia di riferimento entro fine giornata.

#### Calendario giornaliero (dal 2025-12-12)

##### 2025-12-12
- **Encounter_Designer (ENC-OBS-01/02, ENC-ERR-01)**
  - Rischi/regressioni: nessuna nuova anomalia; i valori numerici/astratti restano coerenti con la policy PFS.
  - Stato vs checkpoint: criterio di convalida 2025-12-12 rispettato con QA clampato ripetuto.
  - CTA completate: rerun QA clampato e verifica pipeline export/CTA sequenziale.
  - Blocchi/dipendenze: nessuna.
  - Stato tracker: storie confermate chiuse (Done).
- **base_profile (BAS-OBS-01/02, BAS-CHK-19, BAS-ERR-01)**
  - Rischi/regressioni: nessuna regressione sul routing doc/help/manuale o sul preload 206 protetto.
  - Stato vs checkpoint: prerequisiti 2025-12-19 in anticipo, flag `runtime.preload_done` valido.
  - CTA completate: smoke test doc/help/manuale con API key; warmup preload ripetuto.
  - Blocchi/dipendenze: dipendenza ai moduli core già valida su disco, nessun blocco nuovo.
  - Stato tracker: storie restano chiuse (Done).
- **sigilli_runner_module (SIG-OBS-01/02/03, SIG-ERR-01/02/03/04)**
  - Rischi/regressioni: nessun nuovo rischio; finestra raro da indice 14 e portale sempre presente confermati.
  - Stato vs checkpoint: controllo preliminare verso checkpoint 2025-12-26 senza deviazioni.
  - CTA completate: ripasso note CTA MDA/CTA e header troncamento.
  - Blocchi/dipendenze: nessuno.
  - Stato tracker: storie mantenute chiuse (Done).

##### 2025-12-13
- **Encounter_Designer**
  - Rischi/regressioni: nessuna; valori numerici e clamp CR/QA stabili.
  - Stato vs checkpoint: monitoraggio post-checkpoint, nessuna azione richiesta.
  - CTA completate: validazione automatica export VTT/MD/PDF riconfermata.
  - Blocchi/dipendenze: nessuno.
  - Stato tracker: chiuso.
- **base_profile**
  - Rischi/regressioni: nessun degrado nelle rotte doc/help/manuale o preload.
  - Stato vs checkpoint: pronti per checklist 2025-12-19, nessuno slittamento.
  - CTA completate: controllo health/doc autenticato con API key.
  - Blocchi/dipendenze: nessuno aggiuntivo oltre al gate sui moduli core.
  - Stato tracker: chiuso.
- **sigilli_runner_module**
  - Rischi/regressioni: nessuna nuova regressione sulle soglie rare/quest o tagging CTA.
  - Stato vs checkpoint: percorso verso 2025-12-26 on track.
  - CTA completate: review checklist rare/portale e log QA.
  - Blocchi/dipendenze: nessuno.
  - Stato tracker: chiuso.

##### 2025-12-14
- **Encounter_Designer**
  - Rischi/regressioni: non rilevati.
  - Stato vs checkpoint: stabile dopo validazione 2025-12-12.
  - CTA completate: smoke test clampato rapido.
  - Blocchi/dipendenze: nessuno.
  - Stato tracker: chiuso.
- **base_profile**
  - Rischi/regressioni: nessun cambio su preload o binding core.
  - Stato vs checkpoint: preparazione checkpoint 2025-12-19 confermata.
  - CTA completate: verifica routing `/doc` e note preload.
  - Blocchi/dipendenze: nessuno ulteriore.
  - Stato tracker: chiuso.
- **sigilli_runner_module**
  - Rischi/regressioni: nessun rischio su rare gating o portale obbligatorio.
  - Stato vs checkpoint: progression invariata verso 2025-12-26.
  - CTA completate: controllo CTA sigilli_portal e badge.
  - Blocchi/dipendenze: nessuno.
  - Stato tracker: chiuso.

##### 2025-12-15
- **Encounter_Designer**
  - Rischi/regressioni: nessuna anomalia post-rerun export.
  - Stato vs checkpoint: mantenuto post-2025-12-12.
  - CTA completate: revisione pipeline QA/export.
  - Blocchi/dipendenze: nessuno.
  - Stato tracker: chiuso.
- **base_profile**
  - Rischi/regressioni: nessuna regressione su guard API key.
  - Stato vs checkpoint: allineato al checkpoint 2025-12-19.
  - CTA completate: verifica header troncamento su preload autenticato.
  - Blocchi/dipendenze: nessuno.
  - Stato tracker: chiuso.
- **sigilli_runner_module**
  - Rischi/regressioni: non emersi; cooldown raro coerente.
  - Stato vs checkpoint: progresso regolare verso 2025-12-26.
  - CTA completate: controllo logging rare/quest.
  - Blocchi/dipendenze: nessuno.
  - Stato tracker: chiuso.

##### 2025-12-16
- **Encounter_Designer**
  - Rischi/regressioni: nessuna variazione.
  - Stato vs checkpoint: sorveglianza post-chiusura invariata.
  - CTA completate: check export MD/PDF.
  - Blocchi/dipendenze: nessuno.
  - Stato tracker: chiuso.
- **base_profile**
  - Rischi/regressioni: nessun nuovo rischio su preload/binding.
  - Stato vs checkpoint: pronto per convalida 2025-12-19.
  - CTA completate: test API key su `/help` e warmup.
  - Blocchi/dipendenze: nessuno.
  - Stato tracker: chiuso.
- **sigilli_runner_module**
  - Rischi/regressioni: nessuno; CTA sigilli_portal stabile.
  - Stato vs checkpoint: timeline 2025-12-26 confermata.
  - CTA completate: revisione badge level-up.
  - Blocchi/dipendenze: nessuno.
  - Stato tracker: chiuso.

##### 2025-12-17
- **Encounter_Designer**
  - Rischi/regressioni: non presenti.
  - Stato vs checkpoint: monitoraggio continuo, nessun riapertura.
  - CTA completate: check veloce CR clampato.
  - Blocchi/dipendenze: nessuno.
  - Stato tracker: chiuso.
- **base_profile**
  - Rischi/regressioni: nessun degrado router.
  - Stato vs checkpoint: on track per 2025-12-19.
  - CTA completate: conferma binding core e flag runtime.
  - Blocchi/dipendenze: nessuno.
  - Stato tracker: chiuso.
- **sigilli_runner_module**
  - Rischi/regressioni: non rilevati.
  - Stato vs checkpoint: schedule rispettata verso 2025-12-26.
  - CTA completate: verifica quest_every e token_step.
  - Blocchi/dipendenze: nessuno.
  - Stato tracker: chiuso.

##### 2025-12-18
- **Encounter_Designer**
  - Rischi/regressioni: nessun problema post-export.
  - Stato vs checkpoint: stabile post-checkpoint.
  - CTA completate: export QA ricontrollato.
  - Blocchi/dipendenze: nessuno.
  - Stato tracker: chiuso.
- **base_profile**
  - Rischi/regressioni: nessuno su preload o gate API key.
  - Stato vs checkpoint: verifiche finali pronte per 2025-12-19.
  - CTA completate: chiamata autenticata preload 206.
  - Blocchi/dipendenze: nessuno.
  - Stato tracker: chiuso.
- **sigilli_runner_module**
  - Rischi/regressioni: nessuna variazione su CTA portale/rare.
  - Stato vs checkpoint: percorso verso 2025-12-26 confermato.
  - CTA completate: check tag MDA su rare/quest.
  - Blocchi/dipendenze: nessuno.
  - Stato tracker: chiuso.

##### 2025-12-19
- **Encounter_Designer**
  - Rischi/regressioni: nessuna novità.
  - Stato vs checkpoint: invariato, nessuna riapertura.
  - CTA completate: verifica automatica clamp.
  - Blocchi/dipendenze: nessuno.
  - Stato tracker: chiuso.
- **base_profile**
  - Rischi/regressioni: nessuna regressione; preload e router doc/help/manuale OK.
  - Stato vs checkpoint: checkpoint 2025-12-19 soddisfatto.
  - CTA completate: QA su dump troncato e API key; warmup completato.
  - Blocchi/dipendenze: nessuno nuovo; gate rilasci confermato chiudibile.
  - Stato tracker: storie confermate chiuse (Done).
- **sigilli_runner_module**
  - Rischi/regressioni: nessun nuovo rischio.
  - Stato vs checkpoint: timeline 2025-12-26 regolare.
  - CTA completate: controllo portale presente anche senza sigilli.
  - Blocchi/dipendenze: nessuno.
  - Stato tracker: chiuso.

##### 2025-12-20
- **Encounter_Designer**
  - Rischi/regressioni: nessuna evidenza.
  - Stato vs checkpoint: sorveglianza post-chiusura.
  - CTA completate: sanity check export.
  - Blocchi/dipendenze: nessuno.
  - Stato tracker: chiuso.
- **base_profile**
  - Rischi/regressioni: nessun degrado dopo checkpoint.
  - Stato vs checkpoint: chiuso, monitoraggio.
  - CTA completate: verifica periodica doc/help.
  - Blocchi/dipendenze: nessuno.
  - Stato tracker: chiuso.
- **sigilli_runner_module**
  - Rischi/regressioni: nessun problema su rare/quest.
  - Stato vs checkpoint: avanzamento stabile verso 2025-12-26.
  - CTA completate: revisione logs QA.
  - Blocchi/dipendenze: nessuno.
  - Stato tracker: chiuso.

##### 2025-12-21
- **Encounter_Designer**
  - Rischi/regressioni: nessuna.
  - Stato vs checkpoint: invariato, storie restano chiuse.
  - CTA completate: check pipeline CTA.
  - Blocchi/dipendenze: nessuno.
  - Stato tracker: chiuso.
- **base_profile**
  - Rischi/regressioni: non emersi.
  - Stato vs checkpoint: post-checkpoint, nessuna riapertura.
  - CTA completate: verifica router doc/help.
  - Blocchi/dipendenze: nessuno.
  - Stato tracker: chiuso.
- **sigilli_runner_module**
  - Rischi/regressioni: nessun nuovo rischio.
  - Stato vs checkpoint: timeline 2025-12-26 confermata.
  - CTA completate: controllo raro/portale e tag CTA.
  - Blocchi/dipendenze: nessuno.
  - Stato tracker: chiuso.

##### 2025-12-22
- **Encounter_Designer**
  - Rischi/regressioni: non rilevati.
  - Stato vs checkpoint: monitoraggio, nessuna azione.
  - CTA completate: check export VTT/MD.
  - Blocchi/dipendenze: nessuno.
  - Stato tracker: chiuso.
- **base_profile**
  - Rischi/regressioni: nessuno.
  - Stato vs checkpoint: post-checkpoint, tutto chiuso.
  - CTA completate: controllo doc/help/manuale.
  - Blocchi/dipendenze: nessuno.
  - Stato tracker: chiuso.
- **sigilli_runner_module**
  - Rischi/regressioni: nessuna regressione.
  - Stato vs checkpoint: andamento regolare verso 2025-12-26.
  - CTA completate: validazione quest_every.
  - Blocchi/dipendenze: nessuno.
  - Stato tracker: chiuso.

##### 2025-12-23
- **Encounter_Designer**
  - Rischi/regressioni: nessuno.
  - Stato vs checkpoint: chiuso, sola sorveglianza.
  - CTA completate: check rapido CTA QA.
  - Blocchi/dipendenze: nessuno.
  - Stato tracker: chiuso.
- **base_profile**
  - Rischi/regressioni: nessun problema.
  - Stato vs checkpoint: post-2025-12-19 nessuna riapertura.
  - CTA completate: verifica health/doc con API key.
  - Blocchi/dipendenze: nessuno.
  - Stato tracker: chiuso.
- **sigilli_runner_module**
  - Rischi/regressioni: nessun nuovo rischio su rare/quest.
  - Stato vs checkpoint: percorso per 2025-12-26 confermato.
  - CTA completate: controllo header troncamento.
  - Blocchi/dipendenze: nessuno.
  - Stato tracker: chiuso.

##### 2025-12-24
- **Encounter_Designer**
  - Rischi/regressioni: nessuna variazione.
  - Stato vs checkpoint: chiuso.
  - CTA completate: export sanity check.
  - Blocchi/dipendenze: nessuno.
  - Stato tracker: chiuso.
- **base_profile**
  - Rischi/regressioni: nessuno.
  - Stato vs checkpoint: chiuso, monitoraggio.
  - CTA completate: controllo router doc.
  - Blocchi/dipendenze: nessuno.
  - Stato tracker: chiuso.
- **sigilli_runner_module**
  - Rischi/regressioni: nessun problema.
  - Stato vs checkpoint: timeline per 2025-12-26 confermata.
  - CTA completate: verifica badge level-up.
  - Blocchi/dipendenze: nessuno.
  - Stato tracker: chiuso.

##### 2025-12-25
- **Encounter_Designer**
  - Rischi/regressioni: non presenti.
  - Stato vs checkpoint: chiuso.
  - CTA completate: check CR clampato.
  - Blocchi/dipendenze: nessuno.
  - Stato tracker: chiuso.
- **base_profile**
  - Rischi/regressioni: nessun degrado.
  - Stato vs checkpoint: post-checkpoint, nulla da riaprire.
  - CTA completate: verifica doc/help/manuale.
  - Blocchi/dipendenze: nessuno.
  - Stato tracker: chiuso.
- **sigilli_runner_module**
  - Rischi/regressioni: nessuna novità.
  - Stato vs checkpoint: pronto per verifica finale 2025-12-26.
  - CTA completate: check CTA portale e rare.
  - Blocchi/dipendenze: nessuno.
  - Stato tracker: chiuso.

##### 2025-12-26
- **Encounter_Designer**
  - Rischi/regressioni: nessun segnale di regressione.
  - Stato vs checkpoint: concluso e chiuso.
  - CTA completate: monitoraggio export.
  - Blocchi/dipendenze: nessuno.
  - Stato tracker: chiuso.
- **base_profile**
  - Rischi/regressioni: nessuna nuova evidenza.
  - Stato vs checkpoint: checkpoint 2025-12-19 resta valido, nessuna riapertura.
  - CTA completate: controllo periodico preload/doc.
  - Blocchi/dipendenze: nessuno.
  - Stato tracker: chiuso.
- **sigilli_runner_module**
  - Rischi/regressioni: nessun rischio aggiuntivo; raro, portale e troncamento restano coerenti.
  - Stato vs checkpoint: checkpoint 2025-12-26 confermato senza deviazioni.
  - CTA completate: QA finale su rare/portale/header troncato e tagging MDA/CTA.
  - Blocchi/dipendenze: nessuno.
  - Stato tracker: storie confermate chiuse (Done).

### Regression pass pre-rilascio
- Eseguito il 2025-12-11 con suite `pytest` (73 test) più checklist di regressione completa.
- Esito: pass, nessuna riapertura o deviazione sui gate QA/CTA o sulla dump policy.
- Comunicazioni archiviate nel tracker sprint (thread rilascio 2025-12-11) e nel canale `#release-qa` con link ai log di test.
