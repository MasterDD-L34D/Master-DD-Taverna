# ADR 008 — Update parziale: semantica merge nei comandi del DSL

- **Data**: 2026-10-27
- **Stato**: ratificato (owner, su risposte Claude ai grill round 1-2)
- **Contesto**: ES1 ha introdotto `src/dsl/` (interprete deterministico dei
  comandi dei moduli). Il binding assegnava `None` ai params dichiarati-non
  passati e ogni `set` lo scriveva: `/update_build nome=Grog razza=Mezzorco`
  azzerava 8 campi (misura G1). Dettaglio completo: voci ADR precedenti in
  `planning/decisions.md`.

## Decisione

**Update parziale con semantica merge.** Un *param non legato* (dichiarato
nel comando, assente nella chiamata) rende **no-op il verbo mutante** che lo
legge; lo stato conserva il valore esistente.

- Rilevamento per scansione statica AST (`find_undeclared_variables`, cache
  LRU) su: `value`, `set` in forma lista, `with`, `key`, `append_values`,
  `compute` monoriga, stringa di `command`/`route`/`call_command`.
- **Template misto** (`'{{nome}} {{ruolo}}'` con `ruolo` non legato): salta
  l'intera action — un render parziale scriverebbe un valore falso.
- **Contaminazione via scratch**: un `call`/`find_in` saltato con
  `return_as: tmp` rende `tmp` non legato per il resto del comando.
- **Spec di comando**: i token che leggono params non legati vengono scartati
  prima del render, così il sottocomando li vede non legati a sua volta
  (chiude il bug esistente `/sub None`).
- **"Non legato" = chiave assente in `params`**. Un `None` passato
  esplicitamente è legato e scrive: è una cancellazione voluta.

## Cosa NON cambia

- Il binding `None` nelle **condizioni** (`if`/`when`/`switch`): la guardia di
  `/toggle_rules` e la convenzione "assente = non valorizzato" restano intatte.
- Le chiavi di stato assenti che leggono come `None` nei template.
- Gli wipe espliciti: `clear:`, `value: []`, `value: ''`, None passato esplicito.

## Evento

Un evento aggregato per `run_command` (mai vuoto; i comandi annidati emettono
il proprio):

```
{'update_parziale': {'comando': nome, 'param_non_legati': [...],
                     'saltati': [path target | 'call:<nome>' | ...]}}
```

## Divieto

`value: null` vietato al caricamento (gate rosso), in tutte le forme YAML:
`null`, `~`, vuoto, e `value` assente su `set`/`append`/`extend`. Uso misurato
nei moduli: 0 (pre-divisione ES2).

## Conseguenze

- Gate G1 ri-pinnati nello stesso PR (Verify-RED: i nuovi test fallivano sul
  codice pre-decisione); test negativo che documenta la semantica scartata.
- Audit dei 18 comandi con ≥5 params dichiarati (task di implementazione).
- Glossario (`CONTEXT.md`): *param non legato*, *update parziale*.

## Alternative scartate

- **A) write-None + evento**: rende il wipe visibile ma non lo elimina.
- **C) opt-in per comando (`partial: true`)**: doppia semantica da mantenere
  per sempre.
- **C') togliere i params non legati dal contesto di render**: rompe la
  guardia D8 (`{{abp is not none}}` su Undefined dà `True`) e la ricaduta sui
  nomi è imprecisa (può pescare chiavi di stato omonime).

## Migrazione

Nessuna. L'interprete ES1 è nuovo e nessun replay persistente dipende dal
wipe (verificato: i replay vivono nei test, ri-pinnati qui).
