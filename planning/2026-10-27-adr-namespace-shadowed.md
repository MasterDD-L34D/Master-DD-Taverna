# ADR 011 — Namespace comandi: collisioni rendicontate, deployment per-modulo dichiarato

Data: 2026-10-27
Stato: ratificata (owner 2026-10-27, alternativa A)
Contesto: fetta namespace del piano ES2 residuo (scope `0ec1e37`)

## Censimento (banco)

- 332 nomi comando su 12 moduli; il loader fonde kernel + tutti i moduli
  in un unico dizionario `commands` dove l'ultimo file caricato
  (ordine = nome file sorted) **sovrascrive in silenzio**.
- **22 nomi in collisione** (~50 definizioni coinvolte), con definizioni
  SEMANTICAMENTE DIVERSE (es. `/update_build` in Taverna_NPC e' una patch
  guardata `when: feature_flags.minmax_builder==on`, oggi sepolta;
  `/explain_rule` ha parametri diversi tra Encounter_Designer e
  ruling_expert). Comandi sepolti veri, non duplicati.
- Il deployment reale e' gia' **per-modulo**: `load_kernel(only=...)`
  con un modulo alla volta (i replay G1 lo usano; il commento in
  test_dsl_interpreter lo dichiara). Il kernel pieno serve ai gate
  G2/G3 (copertura, statico).

## Decisione (alternativa A)

1. **Rendicontazione**: il loader raccoglie ogni sovrascrittura in
   `Kernel.shadowed: dict[str, list[str]]` — nome → origini in ordine di
   caricamento (il VINCENTE e' l'ultimo della lista). Mai silenzioso:
   la semantica di risoluzione resta quella attuale (deterministica),
   ma diventa ispezionabile e pinnabile dai test.
2. **Perimetro dichiarato**: l'esecuzione reale dei comandi e' per-modulo
   per definizione (un kernel per sessione, `only=`); il kernel pieno
   (tutti i moduli) esiste solo per i gate. Dichiarato nella docstring
   di `load_kernel` e in questo ADR.
3. **Cura authoring accodata**: le 22 collisioni sono un backlog esplicito
   (rename nei moduli coinvolti, una alla volta con il metodo) — non
   bloccante per questa fetta.

## Alternative scartate

- **B. Namespace qualificato** (`<modulo>:<nome>` per raggiungere i
  comandi sepolti): superficie nuova senza consumatori oggi — YAGNI.
- **C. Rename authoring immediato**: churn sui moduli canonici +
  decisione nome-per-nome — separabile in coda dopo A.

## Conseguenze

- Test gate pinna il censimento: 22 collisioni note; chi ne cura una
  aggiorna il test consapevolmente.
- `coverage_report()` espone le collisioni (`shadowed`) per i gate G2.
- Quando un consumatore reale vorra' i comandi sepolti, B diventa
  valutabile con un motivo misurato.
