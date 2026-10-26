# Esecutore-DSL — scope ES2 e coda scoperte (ratificato owner 2026-10-27)

ES1 e' merged (#550, squash `75b34f9`): loader+interpreter+state in `src/dsl/`,
22 test verdi, review Claude (2 giri) e Codex (P1+3xP2) recepite integralmente.
Questo documento colloca le scoperte emerse e fissa il perimetro di ES2.

## Cantiere 0 — cura moduli DSL (PRIMA di ES2)

Le condizioni con comprehension Python dei moduli sono latenti: il gate G3
le rifila come referti (23 pinna normalizzati) e `_cond` le valuta false
con evento. Fix modulo per modulo, con rituale AGENTS.md: validita' YAML +
reindice RAG (`tools/index_rag.py --include-local`). Stesso rituale per
qualunque edit futuro ai moduli.

## ES2 — sessione per-modulo (scope ratificato)

1. **Decisione D8/MEDIA-9 esplicita**: l'update parziale azzera i campi
   dichiarati-non-passati. Va resa una semantic choice documentata con
   evento `campi azzerati` — mai silenziosa (perdita dati a ogni update
   parziale e' il rischio principale in produzione).
2. **Collisioni nomi comando tra moduli** (es. `/update_build` in
   Taverna_NPC vs minmax_builder): oggi mitigate dal perimetro `only=` dei
   replay; ES2 introduce namespace per-modulo.
3. **Verbi sessione/flow** (input/export/save_session/load_session/
   goto_state/list_session_keys/...): oggi NO_OP dichiarati in `noop_log`.
4. **state_machine `@var@`** (mini-lingua Taverna_NPC): valutare se
   interpretare o lasciare fuori perimetro (decisione ES2, non default).
5. **Precondizione dura**: moduli solo da repo. Se un modulo arriva mai da
   utente/modello (homebrew), l'isolamento va a livello di processo —
   prerequisito ES2/ES3, non un fix locale (vedi modello di minaccia in
   `src/dsl/interpreter.py`).

## Chiuso in ES1 — non riaprire

Posizionali legati ai params dichiarati, dict-normalizzazione condivisa
esecuzione/gate, lookup primo token per nomi con firma, P1-P4 Codex
(render ricorsivo, spec command reso, helper namespace, compute
forma-espressione).

## P3 in coda (MOD-LLM, non bloccano)

Tag BASSA-13 duplicato; snap superficiale dello scratch (copia profonda
solo se un chiamante fara' append in place); token `_depth=` collide col
kwarg interno; kwarg non dichiarati muti vs posizionali verbosi; primo
token ambiguo tra comandi omonimi; `assert events == []` nei replay G1;
pin G3 accetta scambio indici (compromesso dichiarato).
