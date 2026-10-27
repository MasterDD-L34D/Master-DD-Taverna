# ADR 010 — Verbo `export`: persistenza dell'ultimo output su porta

Data: 2026-10-27
Stato: proposta (fetta ES2-a3)
Contesto: ES2 residuo (scope `0ec1e37`), dopo ES2-a1 (ADR 009, #554)

## Censimento (banco)

Il verbo `export` compare 13 volte in 4 moduli, forma **scalare**
`- export: <formato>`, quasi sempre subito dopo `output_template`
(il render del documento da esportare):

- Encounter_Designer (2): `json`, `{{format}}`
- adventurer_ledger (6): `markdown`, `json` x3, `{{format or "markdown"}}`, `markdown`
- meta_doc (3): `{{format}}`, `zip`, `brew`
- minmax_builder (2): `{{format}}`, `json`

Formati dichiarati dai moduli: json, md/markdown, pdf, canvas, zip, brew.
L'helper `minmax_export_filename` (minmax_builder:556) e' solo testo
nell'output successivo — nessun file e' mai stato scritto (verbo no-op).

## Decisione

`export: <fmt>` con:

1. **Formato** reso (`_rn`) → minuscolo → whitelist
   `{json, md, markdown, txt, brew, zip, pdf, canvas}`. Formato non in
   whitelist (incluso path traversal come `../../x`): evento
   `formato_export_non_valido` + no-op — mai un nome file arbitrario
   da input utente. Formato con nomi non legati (template senza
   fallback): skip `update_parziale` come gli altri verbi (ADR 008).
2. **Contenuto**: l'ultima entry di `output_log` (cioe' cio' che il
   comando ha appena "stampato" come documento). Output vuoto: evento
   `export_senza_output` + no-op.
3. **Persistenza**: porta `ExportDirPort` iniettata
   (`Interpreter(kernel, port=None, export_port=None)`), directory
   `var/exports/` (gitignored; env `MASTERS_DD_EXPORTS_PATH`), nome
   `export_<n>.<ext>` ASSEGNATO DALLA PORTA: il contatore deriva dai
   file già presenti nella directory (la directory è la verità
   persistente), mai da stato volatile dell'interprete — un interprete
   nuovo non riparte da `export_1` e non sovrascrive l'export di una
   sessione precedente (correzione post-review Codex P1, PR #555:
   `runtime.export_counter` era volatile). Scrittura atomica
   (tmp + os.replace). Il path scritto va in scratch `exported_path`
   (visibile agli action successivi dello stesso comando; lo scratch
   non tracima fuori dal comando — MEDIA-8).
4. I verbi non toccano disco diretto: solo la porta (stesso confine
   fiducia dell'ADR 009).

## Conseguenze

- I file esistono davvero: il flow output_template → export produce
  un artefatto in `var/exports/`.
- Il nome `export_<n>.<ext>` NON coincide con quello pubblicizzato da
  `minmax_export_filename` (MinMax_<slug>.<ext>): allineamento
  verb/helper = authoring dei moduli, accodato (non bloccante).
- meta_doc `/export_doc_brew` ed `/export_pack_zip` esportano il loro
  output testuale (non un template documento): coerente con la
  semantica "persisti l'ultimo output", authoring migliorabile.
- `pdf`/`canvas`/`zip`/`brew` sono persistiti come testo (il DSL non
  genera binari): formato marcato dall'estensione, contenuto testuale.

## Alternative scartate

- Nome file dal modulo (helper per-modulo): accoppia il verbo ai
  moduli, rompe l'indipendenza della porta.
- Contatore nella porta: due istanze divergono (stessa lezione del
  lost update ADR 009 giro 2).
- `export` come solo segnale (emit sulla porta): non chiude il
  requisito "l'artefatto esiste" della fetta a3.
