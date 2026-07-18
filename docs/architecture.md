# Architettura — Master-DD-Taverna (Kernel + API)

Questo progetto separa il **kernel** del tuo GPT (prompt lunghi, moduli, knowledge pack)
dal **profilo GPT** vero e proprio.

- Il **profilo GPT** contiene solo le istruzioni compatte (`gpt/system_prompt_core.md`)
  e l'aggancio Actions all'API (`gpt/openapi.json`).
- L'**API Python (FastAPI)** in `src/` espone i file reali che hai caricato:
  `base_profile.txt`, i moduli specializzati, i knowledge pack, ecc.
- In questo modo non hai più il problema di superare il limite di caratteri del prompt
  del builder GPT: il grosso del contenuto vive nel repo.

Flusso tipico:
1. Il GPT riceve una domanda.
2. Decide la modalità interna (Ruling / Archivist / MinMax / Encounter / Taverna / Ledger / Explain / Narrativa).
3. Se serve un dettaglio del kernel, chiama l'API (es. `GET /modules/minmax_builder.txt`).
4. Usa il contenuto del modulo solo come riferimento, riformulando con parole proprie.
5. Risponde all'utente con tag [RAW]/[RAI]/[PFS]/[HR]/🧠META quando opportuno.

## Difese sugli endpoint statici

- Gli endpoint `/modules` e `/knowledge` risolvono il percorso richiesto con `Path.resolve()` e
  verificano l'appartenenza alla directory attesa tramite `is_relative_to` per bloccare traversal
  (`..`, percorsi percent-encoded) e link simbolici verso posizioni esterne.
- I symlink che puntano fuori da `MODULES_DIR` o `DATA_DIR` vengono quindi rifiutati con `400`:
  la risoluzione porta al percorso reale, che non risulta relativo alla directory radice.
- Limitazione: eventuali symlink interni (che restano sotto la dir radice) sono accettati perché
  considerati parte dello spazio autorizzato; assicurarsi che non espongano dati indesiderati.
