# CONTEXT.md — Glossario del dominio

Solo vocabolario: niente dettagli di implementazione (quelli vivono nei
piani in `planning/` e negli ADR in `planning/decisions.md`).

## DSL dei moduli

- **Modulo**: file YAML in `src/modules/*.txt` che dichiara comandi, helper,
  template e dati di un dominio (build, taverna, encounter, …).
- **Comando**: unità eseguiva del DSL; dichiara i propri **params** e una
  lista di action (verbi).
- **Param dichiarato**: nome elencato in `params` del comando.
- **Param non legato**: param dichiarato ma assente nella chiamata del
  comando. Con la semantica merge (ADR 008) rende no-op il verbo mutante che
  lo legge: l'update è parziale e conserva lo stato esistente.
- **Update parziale**: esecuzione di un comando con uno o più params non
  legati; lo stato conserva i valori dei campi non passati. Segnalato
  dall'evento `update_parziale`.
- **Binding**: associazione tra params dichiarati e valori passati. I params
  non passati valgono `None` nelle condizioni (guardia), ma non vengono
  scritti nello stato.
