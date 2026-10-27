# Decision Log (ADR brevi)

Formato: contesto → decisione → conseguenze.

## ADR 001 — Build DB e dump moduli
- **Contesto**: lo script `tools/generate_build_db.py` deve produrre build estese (16 step) e scaricare i moduli critici per scheda/narrativa.
- **Decisione**: usare `mode=extended` come default, con health check opzionale (`--skip-health-check`) e uso della variabile `API_URL`/flag `--api-url` per endpoint remoti. Combinare moduli pinnati e discovery `GET /modules` quando `--discover-modules` è attivo.
- **Conseguenze**: gli output finiscono in `src/data/builds/` e `src/data/modules/` con indici `build_index.json` e `module_index.json`; i parametri `--modules`, `--include/--exclude` consentono di riprodurre la selezione indicata nel README.

## ADR 002 — Livelli di validazione
- **Contesto**: alcune risposte possono violare gli schemi in `schemas/` durante la generazione del DB o il download moduli.
- **Decisione**: supportare livelli progressivi: `--strict` interrompe al primo payload non valido; `--keep-invalid` conserva comunque i file difettosi per debug; default tollerante ma con log dell'esito per ogni voce in `build_index.json` e `module_index.json`.
- **Conseguenze**: consente di scegliere tra fail-fast e raccolta completa, come descritto nel troubleshooting del README; gli indici annotano gli errori per analisi successive.

## ADR 003 — Discovery moduli e filtri glob
- **Contesto**: il set di moduli esposti dall'API può variare; serve controllare quali asset entrano nel dump.
- **Decisione**: quando `--discover-modules` è abilitato, unire la lista scoperta con moduli pinnati, applicando filtri `--include/--exclude` solo ai moduli scoperti.
- **Conseguenze**: replica il flusso di selezione moduli documentato nel README; i filtri e i timestamp vengono registrati in `module_index.json` per rendere riproducibile la discovery.

## ADR 004 — Uso di spec file e filtri combinatori
- **Contesto**: servono combinazioni classe/razza/archetipo/background riproducibili senza hardcodare ogni variante.
- **Decisione**: permettere `--spec-file` (default `docs/examples/pg_variants.yml` se non fornito) oppure l'uso di flag combinatori (`--races`, `--archetypes`, `--background-hooks`) per generare il prodotto cartesiano con le classi finali.
- **Conseguenze**: gli output riportano `spec_id` e varianti nel `build_index.json`; l'approccio riusa il flusso di generazione build descritto nel README e mantiene compatibilità con moduli aggiuntivi scaricati tramite discovery.

## ADR 005 — Hardening health/metrics e autenticazione
- **Contesto**: probe falliti (`/health`), rate-limit (`429`) e chiavi assenti (`401`) possono interrompere la pipeline di build.
- **Decisione**: seguire i passaggi di avvio API del README (esportare `API_KEY`, opzionale `ALLOW_ANONYMOUS`) e regolare il backoff tramite `AUTH_BACKOFF_*`; permettere `--skip-health-check` quando l'endpoint non espone `/health` ma è raggiungibile.
- **Conseguenze**: riduce falsi negativi nei probe e blocchi temporanei durante `generate_build_db`; gli script devono documentare le variabili d'ambiente e i fallback nei log, collegandosi ai workflow di avvio API e probe.

## ADR 006 — Handoff post-build esteso
- **Contesto**: l'ultimo ciclo `generate_build_db` extended è andato a buon fine con discovery moduli e validazione strict; servono follow-up rapidi prima di un nuovo run.
- **Decisione**: organizzare un handoff operativo con ruoli espliciti: Tech Lead riallinea priorità e merge, Backend/API rivede flag di discovery/validazione e endpoint (`/health`, `/metrics`, `/modules`), Data/Validation analizza `build_index.json`/`module_index.json` per errori o payload borderline, Docs aggiorna note operative/README e canali di comunicazione.
- **Conseguenze**: garantisce checklist condivisa e correzioni mirate prima del prossimo ciclo di build, evitando regressioni su autenticazione, filtri e schemi; le note risultanti devono essere riportate in `docs/run_logs.md` e nella roadmap.

## ADR 007 — Report di copertura build locali
- **Contesto**: servono elenchi aggiornati di classi/razze/prefissi disponibili in `src/data/builds/` per capire rapidamente i checkpoint presenti o mancanti senza interrogare l'API.
- **Decisione**: aggiungere la flag CLI `--export-lists` a `tools/generate_build_db.py` (con `--reports-dir` personalizzabile) che scansiona i JSON locali e genera i report `reports/build_classes.json`, `reports/build_races.json` e `reports/checkpoint_coverage.json` con livelli presenti/mancanti.
- **Conseguenze**: i report possono essere rigenerati offline in pochi secondi e committati nel repository per allineare il team sulla copertura corrente delle build.

## ADR 008 — Update parziale: semantica merge nei comandi del DSL
- **Contesto**: il binding dei comandi DSL assegnava `None` ai params dichiarati-non-passati e ogni `set` lo scriveva: `/update_build` con 2 params azzerava 8 campi (misura G1, 2026-10-27).
- **Decisione**: semantica merge — un *param non legato* rende no-op il verbo mutante che lo legge (scansione AST statica, cache LRU); template misto = salto dell'intera action; contaminazione via scratch tracciata; token di spec di comando che leggono non-legati scartati; `None` passato esplicitamente resta una cancellazione voluta; condizioni `if`/`when`/`switch` mai scansionate (guardia None intatta). Divieto di `value: null` al caricamento. Evento aggregato per comando: `update_parziale`.
- **Conseguenze**: gate G1 ri-pinnati (Verify-RED nello stesso PR), audit dei 18 comandi con ≥5 params, glossario `CONTEXT.md` (*param non legato*, *update parziale*). Dettaglio e alternative scartate: `planning/2026-10-27-adr-update-parziale.md`.

## ADR 009 — Archivio sessione: store KV unico su file, con porta iniettata
- **Contesto**: i moduli dichiarano verbi di sessione mai eseguiti (save 6, load 4, list 3, forma uniforme con prefissi disgiunti). Risposte Claude al grill delle fette ES2, Q3 verificata sui moduli (2026-10-27).
- **Decisione**: archivio KV unico su file singolo (`var/sessions/store.json`, gitignored, override via env); la chiave è chiave di dizionario, non path — la classe path traversal sparisce; scrittura atomica (tmp + os.replace); valori non serializzabili falliscono espliciti; chiavi whitelist con rifiuto; porta iniettata (store/events) con fake in memoria nei test. Verbi a1: save/load/list_session_keys, emit_event, replace_placeholder. `goto_state` resta NO_OP rumoroso (fetta b); `input` mai usato, non implementato.
- **Conseguenze**: nota README su `git clean -fdx`, `var/` in .gitignore, caricamento store all'init dell'interprete (mai in load_kernel). Dettaglio e alternative scartate: `planning/2026-10-27-adr-archivio-sessione.md`.
