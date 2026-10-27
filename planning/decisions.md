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

## ADR 010 — Verbo `export`: persistenza dell'ultimo output su porta
- **Contesto**: censimento ES2-a3 (2026-10-27): 13 occorrenze in 4 moduli, forma scalare `- export: <fmt>` quasi sempre dopo `output_template`; nessun file mai scritto (verbo no-op), helper `minmax_export_filename` solo testo.
- **Decisione**: `export` rende il formato → whitelist estensioni (rifiuto a evento, mai nome file arbitrario da input) → persiste l'ULTIMA entry di `output_log` su `ExportDirPort` iniettata (`var/exports/`, gitignored, env `MASTERS_DD_EXPORTS_PATH`), nome `export_<n>.<ext>` assegnato dalla porta dal contenuto della directory (verità persistente, mai contatore volatile in stato — fix post-review Codex P1 #555), scrittura atomica, path in scratch `exported_path`. Output vuoto: evento `export_senza_output`.
- **Conseguenze**: il file esiste davvero; nome diverso da quello pubblicizzato da `minmax_export_filename` (allineamento = authoring, accodato). Dettaglio e alternative scartate: `planning/2026-10-27-adr-export-porta.md`.

## ADR 011 — Namespace comandi: collisioni rendicontate, deployment per-modulo dichiarato
- **Contesto**: censimento (2026-10-27): 332 nomi comando su 12 moduli, 22 nomi in collisione sovrascritti silenziosamente dal loader (ultimo file alfabetico vince), definizioni semanticamente diverse (comandi sepolti veri). Il deployment reale e' gia' per-modulo (`load_kernel(only=)`, replay G1); il kernel pieno serve ai gate.
- **Decisione** (alternativa A, ratificata owner): il loader raccoglie le sovrascritture in `Kernel.shadowed` (nome → origini, vincitore = ultimo) — mai silenzioso, semantica invariata; perimetro dichiarato: esecuzione reale per-modulo, kernel pieno solo per gate; le 22 collisioni sono backlog authoring accodato (rename una alla volta). Scartate: B namespace qualificato (YAGNI, nessun consumatore), C rename immediato (churn moduli canonici).
- **Conseguenze**: test gate pinnano il censimento (22); `coverage_report()` espone `shadowed`. Dettaglio: `planning/2026-10-27-adr-namespace-shadowed.md`.

## ADR 012 — `goto_state` eseguibile: atterra + renderizza, validazione a due vie
- **Contesto**: censimento ES2-b (2026-10-27): 18 occorrenze in Taverna_NPC.txt, oggi NO_OP — la state machine la "gira mentalmente" il LLM. Due forme: FSM piatta dichiarata (states + transitions, ~30% dei goto non allineati alla tabella) e wizard GameMode gerarchico (nodi prompt/parse/next).
- **Decisione** (D12, ratificata owner dopo grill Q1–Q3 con parere Claude convergente): `goto_state` scrive `runtime.current_state` nella JsonState di sessione (precedente `set_mode` → `runtime.mode`); validazione a due vie con rifiuto a evento mai silenzioso (flat → `state_machine.states`, dotted → primo segmento in `state_machine.GameMode`, no registro dei ~20 nodi); emissione del `prompt` del nodo target in output_log; tabella `transitions` = metadato dichiarativo non enforced (imperativo vs dichiarativo ortogonali); routing input wizard fuori perimetro (ES3).
- **Conseguenze**: i 18 goto esistenti diventano eseguibili senza toccare i moduli; ES2-b = land + render, ES3 = respond + advance. Dettaglio: `planning/2026-10-27-adr-goto-state.md`.

## ADR 013 — Verbi dominio: zucchero generico su helper omonimi
- **Contesto**: censimento ES3 (2026-10-27): 11 verbi dominio con helper omonimi gia' nei moduli (6 Encounter_Designer, 2 minmax_builder, 3 adventurer_ledger — verificati nel `helpers:`, Claude ne contava 9), 5 senza helper, zero collisioni nomi helper, `input` con zero usi action reali (i 71 "input:" sono chiavi di parse_json/esempi training).
- **Decisione** (D13, ratificata owner dopo grill Q1-Q4 con parere Claude): un unico `_v_domain_call` per gli 11 verbi (`as` escluso dai kwargs — keyword Python), semantica ADR 008 preservata via convenzioni `_v_call`; i 5 verbi senza helper restano NO_OP con motivo "non_implementato" (mai competenza finta), `find_in_list` accodato; routing match/match_any/invoke = piano separato (ES4); `input` rimosso da NO_OP (rumoroso come `verb: "?"`).
- **Conseguenze**: moduli intoccabili (le competenze erano gia' negli helper), side-channel `encounter_state` documentato. Dettaglio: `planning/2026-10-27-adr-domain-verbs.md`.

## ADR 014 — Wizard input routing: run_input, parse a gerarchia, alias @GameMode
- **Contesto**: censimento ES3-2 (2026-10-27): 17 nodi con parse (map/regex+groups/any/any_list), next fratello o @assoluto o end:true, guardie when su parse e temi, 63 riferimenti @GameMode (target, template, guardie), {{input}} nelle actions. Dopo grill A1-A4 con parere Claude convergente; addendum alias ratificato dopo la misura (63 usi — fuori perimetro avrebbe inchiodato il wizard).
- **Decisione**: run_input(text) sincrono sull'interprete (game loop dell'host); gerarchia map > regex > any; groups legati in params; end:true (nodo o action) ripristina IDLE; /comando vince sul nodo; alias @GameMode. in lettura (replace template + ctx GameMode=state game_mode) e scrittura (target game_mode.), state game_mode = deepcopy di GameMode.shared all'init; resto della mini-lingua @var@ fuori perimetro; tema con when falso = evento wizard_guard_falso.
- **Conseguenze**: wizard OnboardingTheme percorribile; ES4 router si coordina via run_input (wizard prima, / prima di tutto). Dettaglio: `planning/2026-10-27-adr-wizard-input.md`.

## ADR 015 — Router input libero: regex deterministico, pipeline fuori
- **Contesto**: censimento routing (base_profile.txt, chiave `router:`): rules ordinate con match/match_any/not_match/condition/set/route_to/short_circuit/continue/reply/stop, fallback_policy (multi_match ask_clarification, no_match), decorators pre/post con set e invoke, intent_detection (normalize, segmenter split_regex, priority). Input libero fuori wizard finora senza gestore; match/match_any/invoke erano NO_OP (D13).
- **Decisione** (D15, ratificata owner dopo grill con parere Claude): router solo regex in `src/dsl/router.py`; ordine canali wizard-prima poi router (`Interpreter.route_input`); segmenter con cap 8 e merge_same_module; normalize lowercase/strip_punct/fold_accents/flag i; rules in ordine lista; condition con traduzione minimale `!`→`not`, `&&`→`and`, `||`→`or`; embedding/rerank/invoke NO_OP in noop_log motivo `pipeline_non_implementata` (RZ1); decorators set applicati; esiti short_circuit/continue/reply+stop/clarification/no_match; runtime.route_to + mode_attivo; mai silenzioso.
- **Conseguenze**: routing deterministico testabile senza LLM nel percorso caldo; pipeline semantica fuori fino ad A/B; condition in sintassi non tradotta = falsa + evento (backlog authoring). Dettaglio: `planning/2026-10-27-adr-router.md`.
