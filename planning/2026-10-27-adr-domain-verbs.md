# ADR 013 — Verbi dominio: zucchero generico su helper omonimi, onestà sui non implementati

Data: 2026-10-27
Stato: ratificata (owner 2026-10-27, D13 dopo grill Q1–Q4 con parere Claude)
Contesto: apertura ES3, piano dei verbi NO_OP rimasti dopo ES2

## Censimento (banco)

- **11 verbi dominio con helper OMONIMI già scritti nei moduli** (verificati
  uno a uno nel rispettivo `helpers:`): compute_xp_budget_estimate,
  classify_balance_label, estimate_party_benchmarks,
  estimate_enemy_benchmarks, detect_risks, compute_effective_cr_from_enemies
  (Encounter_Designer); build_risk_heatmap, build_top_risks (minmax_builder);
  build_buylist, find_and_consume_item, find_and_update_item
  (adventurer_ledger). Forma d'uso: `verbo: {params…, as: scratch}` —
  computazione pura, risultato in scratch.
  *(Nota: Claude al grill contava 9 — refutato, grep sui `helpers:` dà 11.)*
- **5 verbi senza helper**: generate_enemies_from_biome (1 uso),
  analyze_meta_results, search_meta_sources, run_qagates,
  cross_reference_class (appare come flag, non verbo puro).
- **Zero collisioni nomi helper** tra i 3 moduli — il side-channel
  (helper che leggono `encounter_state` dai globals, non dai params) è
  sicuro oggi ma resta implicito: documentato qui.
- **`input` come action verb: zero usi reali** — i 71 "input:" censiti sono
  chiave di `parse_json` ed esempi training in archivist.
- Routing (match/match_any 16 usi, invoke 10 usi): infra del router,
  non verbi computazionali.

## Decisione (D13)

1. **Zucchero generico**: un unico `_v_domain_call` serve gli 11 verbi —
   `scratch[as] = helper_omonimo(**params_renderizzati)`. `as` è escluso
   dai kwargs (keyword Python, rischio SyntaxError al call-time segnalato
   da Claude). Semantica ADR 008 preservata: `_skip_node` sui params non
   legati, scratch stale rimosso (convenzioni di `_v_call`).
2. **I 5 verbi senza helper restano NO_OP con motivo dichiarato**
   `"non_implementato"` — mai competenza finta; log backlog.
   `find_in_list` (1 uso, niente helper) accodato con loro.
3. **Routing (match/match_any/invoke) = piano separato (ES4)** — tocca il
   router dei comandi, un comportamento per slot.
4. **`input` rimosso da NO_OP**: se appare come verbo, `_dispatch` lo
   registra come `{"verb": "?"}` rumoroso invece di ingoiarlo.

## Conseguenze

- I moduli non vanno toccati: le competenze erano già negli helper, ora
  sono richiamabili dal DSL.
- Side-channel `encounter_state` negli helper: funziona perché i helper
  sono compilati nei globals che includono lo stato sessione — implicito
  ma documentato; un helper futuro che voglia input diversi li dichiari
  in `params`.
- ES4 (routing/orchestrazione) si progetta a parte, con loop-guard.
