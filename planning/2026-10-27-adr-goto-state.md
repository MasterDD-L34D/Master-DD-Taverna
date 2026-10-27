# ADR 012 — `goto_state` eseguibile: atterra + renderizza, validazione a due vie

Data: 2026-10-27
Stato: ratificata (owner 2026-10-27, D12 dopo grill Q1–Q3 con parere Claude convergente)
Contesto: fetta ES2-b (state machine) del piano ES2 residuo; ultima fetta del piano

## Censimento (banco)

- `goto_state`: **18 occorrenze, tutte in `Taverna_NPC.txt`**, oggi NO_OP
  dichiarato in `interpreter.py` — zero consumatori nel codice: la state
  machine la "gira mentalmente" il LLM (stesso meccanismo del difetto
  storico del mago).
- Due forme d'uso:
  1. **FSM piatta dichiarata**: `state_machine.states [IDLE, QUIZ,
     SYNTHESIS, READY, EXPORTED]` + `transitions` (6, `on/from/to`). I
     `goto_state` piatti vivono dentro le action dei comandi e **non
     coincidono 1:1 con la tabella** (~30% degli uso senza transizione
     dichiarata: `IDLE` a riga 906, `EXPORTED` 4 volte in comandi che non
     sono `/npc_export`).
  2. **Wizard GameMode gerarchico**: `goto_state: GameMode.X.entry` entra
     in nodi `{prompt, parse (map/regex/groups), actions, next}` con
     shared state in mini-lingua `@GameMode.shared.@...`.

## Decisione (D12)

1. **`goto_state` eseguibile**: scrive `runtime.current_state` nella
   JsonState di sessione (precedente `set_mode` → `runtime.mode`,
   riga 735). Visibilità cross-comando è lo scopo del verbo → chiave
   shared, non per-modulo.
2. **Validazione a due vie, rifiuto a evento mai silenzioso**:
   - identificatore semplice (senza punti) → validato contro
     `state_machine.states` (prende i typo, zero rotture);
   - percorso dotted → validato solo sul **primo segmento** (deve esistere
     in `state_machine.GameMode`); niente registro statico dei ~20 nodi
     wizard (YAGNI).
3. **Emissione del prompt**: se il nodo target ha `prompt`, viene emesso
   in `output_log` (wizard: atterra + renderizza).
4. **Tabella `transitions` = metadato dichiarativo per il planner LLM,
   non enforced**: goto e tabella sono due meccanismi ortogonali
   (imperativo vs dichiarativo); enforcing romperebbe ~30% degli uso
   correnti dal giorno 1.
5. **Routing input wizard fuori perimetro (ES3)**: il loop parse/next
   richiede un confine async che l'interprete non ha.

## Conseguenze

- ES2-b = land + render; ES3 = respond + advance (input routing).
- I 18 goto esistenti diventano eseguibili senza toccare i moduli.
- Gate: test RED su mini-modulo + pin sui moduli reali (stato scritto,
  prompt emesso, rifiuto validato).
