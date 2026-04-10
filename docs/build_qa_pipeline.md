# Pipeline QA per le build generate

Lo script `tools/build_qa_pipeline.py` carica i payload già salvati da
`generate_build_db` e orchestra una catena di QA multi-servizio:

1. **Ruling Expert** — valida/tagga il `ruling_badge` del payload usando il
   contesto di build (classe, talenti chiave, flag HR/META/PFS). Se il badge è
   mancante/non conforme o la modalità PFS include HR/META, il QA fallisce e
   lo snapshot non viene accettato. Il report include sempre il badge finale e
   le fonti dichiarate dal modulo.
2. **MinMax Builder (baseline)** — esegue benchmark e QA per confermare lo stato
   iniziale della build.
3. **Taverna/Narrative** — recupera arco e tema del PG tramite l'endpoint
   dedicato e li invia a MinMax con `/export_arc_to_build`.
4. **Post-import QA** — rilancia la checklist CA/PF/TS/skill/equip/incantesimi e
   un `ruling_check` narrativo; qualsiasi incongruenza marca lo snapshot come
   `invalid`.
5. **Change log** — tutte le modifiche ricevute (tratti, background,
   motivazioni) vengono registrate nel report per tracciabilità.

Ogni step scrive nel report l'esito `PASS/FAIL` con la motivazione; al primo
`FAIL` la build viene marcata `invalid` e il flusso si interrompe.

## Utilizzo

```bash
python tools/build_qa_pipeline.py \
  --ruling-expert-url https://ruling.example.com/validate \
  --minmax-builder-url https://builder.example.com/bench \
  --narrative-arc-url https://taverna.example.com/arc_for_build \
  --narrative-export-url https://taverna.example.com/export_arc_to_build \
  --narrative-ruling-check-url https://taverna.example.com/ruling_check \
  --enable-narrative \
  --api-key "$API_KEY" \
  --classes Fighter Wizard \
  --levels 1 5 \
  --max-items 10 --offset 0
```

Opzioni principali:

- `--index-path`/`--report-path`: file di input (default `src/data/build_index.json`) e
  report di output (default `reports/build_qa_report.json`).
- `--classes` e `--levels`: filtri di classe/livello applicati agli snapshot
  presenti nell'indice.
- `--max-items`/`--offset`: riutilizzano lo stesso batching di `generate_build_db`
  per processare finestre parziali di build.
- `--enable-narrative`: abilita gli hook Taverna/Narrative se gli endpoint sono
  configurati; senza endpoint gli step vengono marcati come PASS con motivo
  esplicito.
- `--narrative-arc-url`: endpoint per ottenere arco e tema del PG da Taverna;
  è richiesto quando `--enable-narrative` è attivo.
- `--api-key`: se valorizzato, viene inviato come header `x-api-key` verso tutti
  gli endpoint.

## Struttura del report

Il report (`reports/build_qa_report.json` di default) contiene una voce per ogni
snapshot processato:

```json
{
  "generated_at": "2025-12-10T12:00:00Z",
  "index_path": "src/data/build_index.json",
  "filters": {"classes": ["Fighter"], "levels": [1], "max_items": 5, "offset": 0},
  "entries": [
    {
      "build_file": "src/data/builds/fighter.json",
      "class": "Fighter",
      "level": 1,
      "status": "invalid",
      "steps": [
        {"name": "ruling_expert", "status": "PASS", "reason": "Badge validato", ...},
        {"name": "minmax_builder", "status": "FAIL", "reason": "HTTP 500: ..."}
      ]
    }
  ]
}
```

- `status` a livello di build è `invalid` se uno qualunque degli step fallisce.
- Ogni `step` riporta `reason` e gli eventuali `details` restituiti dagli
  endpoint (badge aggiornato, esito benchmark, ecc.).
- Ogni step narrativo è riportato separatamente (`narrative_arc`,
  `export_arc_to_build`, `post_import_qa`, `ruling_check`), con la lista di
  modifiche applicate nella chiave `changes` a livello di build.

Usa i filtri e il batching per riprendere rapidamente la QA su subset di classi
senza rifare l'intero export.

## SLO minimi raccomandati

Per promuovere una build in ambienti condivisi (stage/prod), la pipeline QA deve
rispettare almeno questi SLO:

- **Zero 5xx sui percorsi nominali**: su run nominali (`/health`, `/modules`,
  `/modules/{name}`, `/metrics` con credenziali valide) il tasso di risposta 5xx
  deve restare `0.00%` nella finestra di validazione.
- **Coerenza header di truncation**: quando `ALLOW_MODULE_DUMP=false`, ogni
  risposta testuale parziale (`206`) deve includere in modo consistente:
  `X-Content-Partial=true`, `X-Content-Partial-Reason=ALLOW_MODULE_DUMP=false`,
  `X-Content-Served-Bytes`, `X-Content-Remaining-Bytes`, `X-Content-Truncated`
  e `X-Truncation-Limit-Chars`.
- **Nessuna regressione su controllo accessi**: i test auth/metrics devono
  confermare backoff per client/IP indipendenti e corretta valutazione del primo
  hop `x-forwarded-for` rispetto alla allowlist configurata.
