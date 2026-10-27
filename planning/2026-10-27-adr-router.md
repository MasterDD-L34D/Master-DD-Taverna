# ADR 015 — Router input libero: regex deterministico, pipeline fuori

Data: 2026-10-27
Stato: ratificata (D15, owner dopo grill; parere Claude convergente)
Contesto: ES4. Censimento routing (base_profile.txt, chiave `router:`)

## Contesto

I moduli dichiarano una tabella di routing `router:` con:

- `rules`: lista ordinata di `{match | match_any, not_match, condition,
  set, route_to, short_circuit, continue, reply, stop, fallback,
  embedding, rerank, eps_threshold}`;
- `fallback_policy`: `{multi_match: ask_clarification, no_match, clarification_prompt}`;
- `decorators`: `{pre_routing, post_routing}` con blocchi `if/then`
  che usano `set` e `invoke`;
- `intent_detection`: `normalize` (lowercase, strip_punct, fold_accents),
  `segmenter` (split_regex, per_segment_routing, merge_same_module),
  `priority`, `preload`.

Fino a ES3 l'input libero fuori wizard non aveva alcun gestore
(`run_input` emette solo `input_fuori_wizard`). I verbi `match`,
`match_any`, `invoke` erano NO_OP "non_implementato" (D13).

## Decisione

**Solo router regex deterministico in `src/dsl/router.py`**, coordinato
con l'interprete:

1. **Ordine dei canali**: wizard attivo prima (`run_input` gestisce `/` e
   parse, ADR 014); il router serve gli input NON wizard. L'host chiama
   `Interpreter.route_input(text) -> str | None` (route_to), che delega al
   Router con lo stesso stato/eloghi dell'interprete.
2. **Segmenter**: split per `split_regex`, cap di 8 segmenti
   (oltre → evento `segmenter_troppi_segmenti`, routing sull'input
   intero); `merge_same_module` unifica i candidati uguali;
   `per_segment_routing` valuta ogni segmento.
3. **Normalize** prima del match: lowercase, strip punteggiatura,
   fold accenti, flag regex `i`.
4. **Rules in ordine di lista** (la `priority` authored è già l'ordine):
   `match`/`match_any` regex su tutto l'input normalizzato;
   `not_match` esclude; `condition` valutata sullo stato — con
   **traduzione minimale delle forme authored** (`!x` → `not x`,
   `&&` → `and`, `||` → `or`) prima del parse Jinja: è la sintassi
   consolidata della tabella canonica, senza traduzione ogni condition
   del router sarebbe morta (il guard non parseggiabile vale falso).
5. **Flag di pipeline** (`embedding`, `rerank`, `eps_threshold`): NON
   implementati — loggati in `noop_log` con motivo
   `pipeline_non_implementata` (mai competenza finta, lezione RZ1:
   embedding/LLM solo a misura A/B).
6. **`invoke`** (decorators): NO_OP in `noop_log` con motivo
   `pipeline_non_implementata`. I `set` dei decorators invece si
   applicano (sono verbi core già eseguibili).
7. **Esiti**: `short_circuit` ferma al primo match; `continue` procede;
   `reply`+`stop` emettono output e fermano; più moduli diversi sullo
   stesso input → `fallback_policy.multi_match` = chiarimento
   (clarification_prompt in output_log, `runtime.intent_candidates`
   valorizzato); nessun match → `fallback_policy.no_match`.
   `runtime.route_to` e `runtime.mode_attivo` (via decorator post_routing)
   registrano l'esito; tutto mai silenzioso (evento se la tabella manca).

## Conseguenze

- L'input libero fuori wizard routa in modo deterministico e testabile;
  nessun LLM nel percorso caldo.
- La pipeline semantica (embedding/NLI/rerank) resta fuori fino a
  evidenza A/B; i punti di attacco sono gia' dichiarati nella tabella.
- Le condition in sintassi non coperta dalle 3 forme tradotte restano
  "non parseggiabile = falsa + evento" (fix authoring = backlog).
