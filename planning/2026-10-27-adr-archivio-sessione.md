# ADR 009 — Archivio sessione: store KV unico su file, con porta iniettata

- **Data**: 2026-10-27
- **Stato**: ratificato (owner, su risposte Claude al grill delle fette ES2)
- **Contesto**: ES2 (dopo ADR 008, PR #553). I moduli dichiarano verbi di
  sessione mai eseguiti: `save_session` (6 occorrenze), `load_session` (4),
  `list_session_keys` (3), tutti con forma uniforme `key:
  '<prefix>_{{nome}}'`, `value: '{{<root>_state}}'`, prefissi disgiunti
  (`build_`, `enc_`, `loot_`, `story_`). Dettaglio: voci ADR precedenti in
  `planning/decisions.md`.

## Decisione

**Archivio chiave-valore unico, persistito su un file singolo, accessibile
dall'interprete solo tramite porta iniettata.**

- `SessionStore` KV in-memory + persistenza JSON su **un solo file**. La
  chiave è una chiave di dizionario, non un path: la classe di bug
  "path traversal via chiave" non esiste per costruzione (non si riduce:
  sparisce).
- Percorso default `var/sessions/store.json` sotto la repo, **gitignored**
  (dati utente, non sorgente; il working tree è condiviso tra agenti).
  Override via env (`MASTERS_DD_SESSIONS_PATH`): nessun codice in più,
  copre il deploy fuori repo.
- Scrittura **atomica**: tmp + `os.replace`. È la prima scrittura su disco
  dell'interprete.
- Valore non serializzabile in JSON → **fallimento esplicito** (evento +
  no-op del verbo), mai `str()` silenzioso.
- Chiavi comunque validate a confine fiducia, con **rifiuto** (mai
  sanificazione): whitelist `^[a-z]+_[A-Za-z0-9_-]{1,64}$` post-render —
  `key` è un template reso, arriva da utente/LLM.

## Porta iniettata

I verbi non toccano disco o bus direttamente: parlano a una porta
(`store.save/load/list`, `events.emit`). Nei test la porta è un fake
in memoria: ogni verbo ha un test senza filesystem. `Interpreter`
accetta la porta in costruzione (default reale per il runtime).

## Verbi coperti (a1)

| Verbo | Semantica |
|---|---|
| `save_session` | `store.save(key, value)` — value = nodo reso ricorsivamente |
| `load_session` | `store.load(key)` → scratch[`as`] (None se assente) |
| `list_session_keys` | `store.list(prefix)` → scratch[`as`] |
| `emit_event` | append a log eventi in-porta: `{topic, payload reso}` |
| `replace_placeholder` | sostituzione stringa `<ph>` → valore reso (logica pura) |

## Cosa NON entra in a1

- `goto_state` (18 occ., tutte Taverna_NPC): resta **NO_OP dichiarato
  rumoroso** (`unimplemented: goto_state (fetta b)`) con test sulla traccia.
  Verifica sui moduli: nessuna delle 54 guardie di Taverna_NPC legge lo
  stato macchina corrente, quindi il no-op non altera rami. Un marcatore
  muto non ha oracolo (test tautologico) e fisserebbe una forma che la
  fetta b (`GameMode.X.entry` + `@var@`) potrebbe rompere.
- Verbi dominio/RAG (`search_meta_sources`, `find_in_list`, ecc.): restano
  NO_OP (banco/ES3).
- `input`: 0 occorrenze — non si implementa (YAGNI).

## Conseguenze

- Nota README: `git clean -fdx` cancella `var/sessions/`.
- `var/` va aggiunto a `.gitignore`.
- Il caricamento dello store avviene all'init dell'interprete (se il file
  esiste); mai in `load_kernel` (puro parsing, zero effetti).

## Alternative scartate

- **Store per-modulo / file per chiave**: duplica logica senza guadagno —
  il namespace è già nei prefissi; file-per-chiave reintroduce path
  traversal come classe di bug.
- **File versionato in repo**: dati utente in git, working tree condiviso
  tra agenti → stati PG finirebbero nei commit altrui.
- **goto_state come marcatore in a1**: nessun lettore (no oracolo), forma
  prematura rispetto alla fetta b.
