# ADR 014 — Wizard input routing: `run_input`, parse a gerarchia, alias `@GameMode`

Data: 2026-10-27
Stato: ratificata (owner 2026-10-27, D14 + addendum alias dopo censimento dettagliato)
Contesto: fetta ES3-2 (respond + advance), completamento della state machine ES2-b

## Censimento (banco)

- 17 nodi wizard con `parse` in Taverna_NPC.txt, forme: map esatta
  (`"1": {set…}`), regex+groups (`groups: [gopt, age]`), catch-all
  (`any: {…}`, `any_list: {sep, as}`).
- `next`: nome fratello, percorso assoluto `@GameMode.X.entry`, cicli
  (Chase.turn→turn), assente con `end: true` (7 nodi).
- Guardie `when:` dentro le voci di parse (traits_mode) e sui temi
  (kingdom/mass_combat, flag unlocked).
- 63 riferimenti `@GameMode`: targets di `set`, letture dentro template
  (`{{ max(0, @GameMode.shared.profile.money_gp …) }}` — sintassi non
  Jinja, va normalizzata), guardie.
- `{{input}}` nelle actions del nodo: il testo utente grezzo deve essere
  nel contesto di rendering.

## Decisione (D14 + addendum)

1. **`run_input(text)`** sull'interprete, analogo a `run_command`: il DSL
   resta sincrono, `parse:` resta dati dichiarativo, il game loop è
   dell'host. Se `runtime.current_state` non punta a un nodo → evento
   `input_fuori_wizard`, mai silenzioso.
2. **Gerarchia parse**: map esatta > regex (ordine di dichiarazione,
   prima che corrisponde) > `any`/`any_list`. Voce con `when:` falsa o
   non valutabile → saltata (guardia intatta). Nessun match → evento
   `parse_non_riconosciuto`, si resta sul nodo.
3. **Groups regex** legati in params delle actions del nodo.
4. **`next`**: fratello → stesso tema; `@GameMode.X.y` assoluto (via `@`
   strip); `end: true` (proprietà nodo o action `- end: true`) →
   `runtime.current_state = IDLE` dopo le actions. Cicli consentiti
   (navigazione stato, non ricorsione); `MAX_DEPTH` esistente riusato.
5. **`/comando` vince**: se il testo inizia con `/` e il comando esiste
   → `run_command`; se il router non lo conosce (futuro ES4) → il nodo
   lo consuma come testo. Precedenza wizard > router tranne `/`-prefixed.
6. **Alias `@GameMode.`** (addendum ratificato): letture — replace
   `@GameMode.`→`GameMode.` nel sorgente template + `ctx["GameMode"] =
   state["game_mode"]`; scritture — target `@GameMode.`→`game_mode.` nei
   verbi mutanti. `state["game_mode"]` = deepcopy di
   `state_machine.GameMode.shared` all'init (mai kernel.data: statico,
   condiviso). Resto della mini-lingua `@var@` fuori perimetro, backlog.
7. **Temi con `when:` falso**: goto non consentito a priori? No — il goto
   resta valido (ES2-b), ma il nodo entry con guard falso non renderizza
   prompt: evento `wizard_guard_falso`.

## Conseguenze

- Il wizard reale (OnboardingTheme completo) diventa percorribile;
  KingdomTurn/MassCombat restano dietro flag unlocked.
- `@var@` generale (build refs, ecc.) = fetta separata futura.
- ES4 (router regex) si coordina via `run_input`: wizard prima, router
  dopo, `/` prima di tutto.
