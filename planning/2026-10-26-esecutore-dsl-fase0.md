# Esecutore-DSL fase 0 — censimento e piano dell'interprete comandi moduli

Data: 2026-10-26 sera (kimi). Owner: ratificata fetta **Esecutore-DSL**
(voce MOD-LLM, rapporto hub
`sessione-2026-07-16/rapporti/2026-10-26-revisione-metodo-moduli-llm.md`).

## Premessa misurata (con ricerca negativa documentata, metodo §4.6)

I moduli in `src/modules/*.txt` sono **YAML valido** (verificato:
`yaml.safe_load(minmax_builder.txt)` → 42 comandi). Le `action` dei comandi
usano un DSL di verbi. **Ricerca negativa — dove ho cercato un esecutore:**
`output_template|goto_state|emit_event` = **0 hit** in `src/`, `frontend/`,
`gpt/`, `tools/` (python). Uniche eccezioni omonime non pertinenti, verificate
a mano: `tools/generate_build_db.py` (campo audit-log `"action"`, non DSL),
`src/utils/module_resolver.py` (risolutore URI, non interprete),
`src/builder/stub_builder.py` (`build_state` proprio del builder lv1, non
modulo), `src/metadata_parser.py` (parsa snippet di metadati, non action).
I test trattano i moduli come testo/spec (zero hit esecutore).
`src/app.py` li serve come testo grezzo via `GET /modules/{name}`;
`src/agents/builder.py` non parsa YAML. Premesa: nessun interprete — REGGE.

## Censimento verbi (grep su tutti i moduli, 7 moduli con comandi)

Slash command totali: 224 (minmax 42, ledger 48, npc 37, narrative 35,
meta_doc 27, encounter 23, explain 12).

Verbi per frequenza (uso reale nei file):

| classe | verbi | occorrenze |
|---|---|---|
| **core stato** | `set` (431), `append` (72), `copy` (2), `clear` (1), `update_dict` (1), `increment` (1) | ~508 |
| **output** | `output` (322), `output_template` (49) | 371 |
| **controllo** | `if/then` (136), `when` (35), `foreach` (12), `for` (1), `switch` (2), `route` (2), `match`/`match_any` (16), `condition` (2) | ~206 |
| **funzioni** | `call` (84), `invoke` (10), `compute` (11) | 105 |
| **sessione/flow** | `goto_state` (11), `save_session` (6), `load_session` (4), `list_session_keys` (3), `emit_event` (8), `abort` (1), `error` (4) | 37 |
| **I/O** | `input` (5), `parse_json` (9), `export` (13), `reply` (1) | 28 |
| **dominio** (Encounter_Designer) | `roll`, `generate_enemies_from_biome`, `compute_xp_budget_estimate`, `compute_effective_cr_from_enemies`, `classify_balance_label`, `estimate_party_benchmarks`, `estimate_enemy_benchmarks`, `detect_risks`, `build_buylist`, `analyze_meta_results`, `find_in_list`, `find_and_consume_item`, `find_and_update_item`, `run_qagates`, `cross_reference_class`, `search_meta_sources` | ~16 |
| **utility** | `find_in` (2), `replace_placeholder` (1), `guard_all` (2), `find_and_*` | 5 |

Template: sintassi Jinja2 (`{{ }}`, `{% for %}`, `{% if %}`) dentro `output`
e `output_template` — **Jinja2 è già dipendenza** (`requirements.txt:10`).

## Decisioni (ponytail) — v2 post-review Claude 2026-10-26 sera

- **D1**: il DSL si esegue con `yaml.safe_load` + un dispatcher di verbi su un
  `state` dict in memoria. Nessun parser custom, nessuna dipendenza nuova.
- **D2**: formato moduli **invariato**. L'interprete si adatta ai file, non
  viceversa. **Corollario recepito (review Claude ALTA-3): gli oracoli di
  gate seguono la semantica reale dei file, non l'intuizione** — es.
  `/update_build` fa `set` incondizionato di tutti i campi (verificato
  minmax:1167-1188): l'interprete fedele sovrascrive i non passati con
  None, e l'oracolo G1 asserisce QUELLO.
- **D3**: i verbi dominio (Encounter_Designer) NON si implementano in ES1.
- **D4 v2**: due environment Jinja — **`NativeEnvironment` solo per
  `value`/`if`/`when`** (bool e int nativi dove serve), **environment
  standard per `output`/`output_template`** (altrimenti `literal_eval`
  muta le stringhe: `"007"`→`7`, `[1, 2]`→list — recepito giro 2 Claude,
  da verificare nel primo test).
- **D5 v2 (ALTA-1, corretta): le funzioni `logic:` sono Python REALE** —
  verificato: `import re`, f-string (minmax:556-565), `import random`
  (Taverna_NPC, adventurer_ledger, 269 righe in 9 moduli). Chiave reale:
  **`helpers:`** in 10 moduli + **`functions:`** in narrative_flow:780 —
  il loader legge entrambe. Meccanica recepita giro 2: i `logic:` sono
  **corpi con `return` top-level** → wrap `def nome(params):` + indent;
  **un solo dict globals vivo** condiviso da tutti i def (`build_state` =
  riferimento vivo, gli helper si chiamano tra loro); **`__import__` con
  whitelist** (re, random, datetime, math, json) — non una sandbox di
  sicurezza (moduli fidati versionati), `ponytail:`-comment col soffitto;
  determinismo G1: comandi **senza `random`/`now`** (minmax:452); assert
  con `deepcopy` dello stato prima/dopo.
- **D6 (MEDIA-5): due schemi di comandi** — dizionario `^  /cmd:` (224) +
  lista `- name: /cmd` (18: ruling_expert 15, explain_methods 2,
  Taverna_NPC 1, verificato). Il loader normalizza entrambi.
- **D7 (MEDIA-4): verbo `command:` = dispatch ricorsivo** del sottocomando
  (95 occorrenze nei file). Senza di esso `/bench`, `/update_build` e altri
  resterebbero no-op parziali in silenzio.
- **D8 (MEDIA-6): builtin python nei template** — 54 occorrenze
  `str/int/len/any/sum/...` dentro `{{ }}`: registrati come globals Jinja.
  Namespace `local.*`/`runtime.*` mappati sullo stato. **Aggiunta giro 2:
  binding esplicito dei parametri dichiarati-non-passati a `None`** —
  altrimenti Jinja `Undefined` rende `'{{abp is not none}}'` vero e
  `/toggle_rules` scrive `abp_active=False` per un parametro mai passato.
- **D9 (MEDIA-7): `output_template` risolve nomi in `ui_templates:` /
  `qa_templates:` / `export_templates:`** con `inherits_from`: merge =
  deep, **modulo vince su kernel**, funzioni omonime: modulo vince.
- **D10 (MEDIA-8): RED solo locale** — `verify_master_dd.py:30-34` esce se
  `skipped != 0` e mai un test rosso si committa (romperebbe `launch.py
  test` dell'hub). Il RED reale vive solo nel worktree pre-implementazione.
- **Regex censimento dichiarata (BASSA-9 recepita):** verbi =
  `^ +- [a-z_]+:` su `src/modules/*.{txt,md}`; comandi = `^  /[a-z_]+:` +
  `^ +- name: /`; scarti noti: 439 grezzi `set` vs 423 sui 7 moduli
  perimetro (quarantine/tavern_hub esclusi).

## Fette

- **ES1 — interprete core**: `src/dsl/` (4 file — stima corretta giro 2:
  loader ~150, interpreter ~250, state ~60 = **450-550 righe src più
  150-250 di test**): `loader.py` (YAML + inherit + doppio schema comandi
  + helpers/functions + wrap def + exec con globals vivo e import
  whitelist), `interpreter.py` (dispatcher: set/append/copy/clear/
  if/when/foreach/output/output_template/call/compute/command ricorsivo con
  limite di profondità/abort/error + due environment + builtins globals;
  non eseguibili → no-op dichiarato nel report G2), `state.py` (dict +
  path set + namespace local./runtime. + binding None).
- **ES2**: sessione tool-calling per il builder (save/load/goto_state/
  emit_event) + bridge `src/agents/builder.py`.
- **ES3** (solo se misurato): verbi dominio Encounter_Designer.

## Gate ES1 (metodo v2.1 allineati, zero LLM)

- **TDD RED reale** (metodo §7): il test `tests/test_dsl_interpreter.py`
  esiste e FALLISCE prima dell'implementazione (interprete assente).
- **G1 replay** (oracoli riscritti sulla semantica reale, v. D2): esegue
  comandi reali di `minmax_builder.txt` **senza `random`/`now`**:
  `/toggle_rules pfs=on` → assert `state.rules.pfs_active is True` (bool
  nativo, NativeEnvironment); `/update_build` campione → assert che TUTTI
  i campi siano riscritti (`None` nei non passati, binding D8), come fa
  il file. Assert con `deepcopy` prima/dopo.
- **G2 copertura**: per ogni comando dei 7 moduli **più i 18 dello schema
  lista** (D6) l'interprete classifica `eseguibile|no-op dichiarato|errore`
  — report falsificabile allegato alla PR.
- **G3 statico** (giro 2 Claude): `compile()` di ogni `logic:` dopo il
  wrap + `env.parse()` di ogni stringa `{{ }}`/`{% %}` dei moduli —
  atteso 0 errori oppure lista nominale degli errori. Prende i buchi di
  wrap e template senza eseguire nulla.
- **Review sponda Claude: giri 1 e 2 ESEGUITI** — giro 1: 3 ALTA + 5 MEDIA
  + 3 BASSA, recepite; giro 2: 5 OK, 3 recezioni corrette nel meccanismo
  (wrap def, due environment, binding None — integrate come D4 v2, D5 v2,
  D8+), G3 aggiunto, stima corretta. **Verdetto giro 2 Claude: "con
  queste aggiunte lo ratificherei senza un terzo giro".**
- **T1/T2 repo**: `python launch.py test` → TUTTE LE VERIFICHE OK (include
  gate oracolo, ora attivo su entrambi i repo); `.venv/Scripts/python
  tools/legal_filter.py` → 0 violazioni. Moduli NON toccati → rituale
  reindice RAG non applicabile (D2).
- **Tetto turni** (metodo §5): ES1 = max 8 turni (stima corretta giro 2); superato → stop e report,
  non si gira a vuoto.

## Vincoli di metodo rispettati

Commit con trailer ADR-0011 (`Coding-Agent` + `Trace-Id` uuidv7, via
`git commit -F`); push solo dopo conferma owner; worktree isolato secondo
`metodo-merge-stack-2026-10-23.md`; niente refactor opportunistici;
local-first (zero API esterne, ES1 e' puro stdlib+yaml+jinja2 gia' in
`requirements.txt`).

## Prossimo passo

Ratifica di questo piano → implementazione ES1 in worktree Taverna →
PR con gate 1-3 verdi.
