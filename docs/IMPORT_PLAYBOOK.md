# Import Playbook — cataloghi OGL da fonti web

> Metodo consolidato nel **Lotto 4 Fase 1** (2026-07-18, 26 commit, `fb89eac..8c5e3a2`) per importare dati di regole PF1e da aonprd.com in cataloghi JSON OGL strutturati. Seguirlo rende i futuri import **più rapidi** (pattern già pronti, niente re-invenzione) e **più completi** (checklist anti-dimenticanze e lezioni dalle review).
>
> Riferimenti codice: `tools/reference_fetch.py`, `tools/import_reference.py`, `tests/test_import_reference.py`, `tests/test_reference_catalogs.py`, `planning/2026-07-18-ogl-creation-catalogs.md`.

---

## 1. Architettura dell'import

```
fonte web (aonprd)  →  reference_fetch  →  cache HTML (gitignored)
                     →  parse_<domain>() (pura, testata su fixture inline)
                     →  build_<domain>(write=False) → dry-run report
                     →  build_<domain>(write=True)  → catalogo JSON
                     →  manifest + schema + invarianti → legal_filter → reindex RAG → verify
```

- **`tools/reference_fetch.py`**: downloader con cache sha256 su disco (`data/reference/aon_cache/`, gitignored), ancorata al repo (mai relativa al CWD), UA dichiarato, delay 2s cortese, **idempotente** (la cache conserva il progresso tra run).
- **`tools/import_reference.py`**: registry `DOMAINS` {nome: builder}. Ogni dominio = `parse_<domain>(html) -> list[entry]` (funzione pura) + `build_<domain>(write=False)` (fetch + parse + merge + scrittura gated).
- **Regola d'oro: `write=False` di default.** I builder stampano un report senza scrivere; la scrittura avviene solo con `--write`. Indispensabile per i merge in-place su file curati.

## 2. Pattern di parsing (con le trappole già incontrate)

- **Tabelle: seleziona per HEADER, mai per posizione.** Cerca la tabella la cui prima riga contiene le colonne attese (es. "Level" + "Base Attack Bonus"). Le pagine AoN annidano tabelle di layout: leggi le righe con `recursive=False` e cerca l'header entro le prime 3 righe (le tabelle caster hanno righe-gruppo colspan).
- **Sezioni bold-led (razze)**: scope stretto alla sezione voluta (es. solo "Racial Traits") e **fail-closed**: se l'heading non c'è, ritorna vuoto — MAI tutto il documento (fail-open = ingestione di sezioni PI).
- **Catch-all di colonne: whitelist, non blacklist.** Le colonne extra di classe finivano tutte in `spells_per_day` (Monaco con "Unarmed Damage" tra gli "incantesimi"): accetta nelle chiavi speciali solo header che matchano un pattern atteso (es. cerchi `^(0|[1-9](st|nd|rd|th))$`), il resto in una chiave `extra_*` separata.
- **Normalizzazioni ricorrenti**: en-dash `–`→`-`, `×`→`x`, `<sup>` footnote via, `rstrip(":")` sui label, titoli con virgola ("Sargava, the Lost Colony") — splitta le fonti solo prima di `pg. N`.
- **Multi-fonte per voce**: le pagine dettaglio elencano più libri (`Source A pg. 5, B pg. 62`): preferisci `PRPG Core Rulebook` (le altre sono ristampe), alias `PRPG Core Rulebook → PFRPG Core`.
- **Link con spazi**: `urllib.parse.quote` sugli href prima del fetch (InvalidURL su "Battle aspergillum").
- **Il fallback delle pagine mancanti**: AoN può rispondere con una 404 mascherata (pagina senza heading atteso). Rileva e ricadi su una pagina generica documentando la scelta (es. Knowledge specifiche → pagina "Knowledge").

## 3. Convenzioni dati (obbligatorie)

- **Entry**: `name, source, source_id, prerequisites[], tags[], references[] (≥1), reference_urls[] (≥1), description` + **`mechanics`** (oggetto libero per kind: progressione, ability_mods, cost, dmg_m...). `description` = prosa riassuntiva dei mechanics (serve al retrieval RAG, che legge name/prerequisites/description/notes/tags).
- **`source_id` = `<slug_fonte>:<slug_nome>`**, univoco GLOBALMENTE tra tutti i cataloghi (invariante testata).
- **Header catalogo**: `{_license, _source, entries}`; i merge in-place preservano header originale e campi curati (`notes`, `status`, `reviewed_by`, `short_description`) e **estendono** `_source` con la nuova fonte.
- **Attribuzione per-voce**: le tabelle aggregate non hanno colonna fonte — per equipment è costato un fetch per-voce (~26 min) ma ~75% delle entry aveva source errata. Se il dominio aggrega più libri, pianifica l'attribuzione dalle pagine di dettaglio fin da subito.
- **Builder idempotenti**: due run consecutivi producono lo stesso file (niente append, niente ri-fill).

## 4. Product Identity (PI) — la parte che fallisce di più

Quattro stadi, tutti necessari (imparato su traits: 3 giri di fix):

1. **Esclusione by design**: solo categorie/sezioni OGC (traits: Basic + Equipment; razze: solo tratti base CRB — niente subrazze/alternate/favored options).
2. **Gate `tools/legal_filter.py`** (`PI_WORDS` word-boundary): obbligatorio 0 violazioni. Attenzione: la word list è deliberatamente conservativa — non copre toponimi minori, etnie, fazioni, **demonimi aggettivali** (Iomedaeans, Chelaxians, Sargavan, Garundi, Vudrani…).
3. **Supplemento per-dominio** (pattern `TRAITS_PI_SUPPLEMENT`): lista extra di termini Golarion applicata solo al dominio, senza toccare `PI_WORDS` globale (che impatterebbe i cataloghi già committati). Includere le **forme aggettivali/demonimiche**.
4. **Strip delle code flavor**: sezioni tipo "Suggested Characters :" sono piene di demonimi — strip, non rimozione della entry (recupera dati OGC validi).
5. **Persistenza**: ogni filtro scrive `reports/pi_removed_<kind>.txt` (entry + motivo) e lo si committa.
6. **Verifica a mano oltre il gate** — **superata il 2026-07-19**: il gate `tools/legal_filter.py` ora usa la lista PI unica del repo (133 parole word-boundary + frasi, masking dei replacement sanitize derivato), condivisa da `tools/triage_pi_feats.py` (assert di identità). Il debito storico (le ~43 entry PI passate col gate a 0) è stato triagiato e chiuso: vedi §6.1.

## 6.1 Decisione policy PI (2026-07-19, lotto triage feats)

Triage completo di `feats.json` (`reports/pi_feats_triage.md`, tool `tools/triage_pi_feats.py`, 75 termini word-boundary) e applicazione (`tools/apply_pi_feats_policy.py`, `tools/apply_pi_traits_equipment_policy.py`, report `reports/pi_feats_apply.md` + `reports/pi_traits_equipment_apply.md`). Categorie e destinazioni:

- **A — PI nel nome** (identità PI: Aldori, Hellknight, Lastwall, Worldwound…) → `pi_local_only/<kind>_local.json` (uso locale, gitignored, indicizzato solo con `--include-local`). **Sanitize del NOME vietata** (la sanitize storica naive produsse mostri come "Noble Scion a fading empire" e corruzioni "Lem"→"a bard" dentro "elemental").
- **B — prerequisito vincolante PI** (deità o etnia/organizzazione/tradizione Golarion: "worshiper of Rovagug", "Human (Chelaxian)", "Member of a Shoanti tribe") → `pi_local_only/` (la sanitize svuoterebbe il vincolo).
- **C — PI solo in prosa description** → sanitize in place con `tools/sanitize_reference_pi.py` (ora word-boundary, idempotente, name mai toccato; regole description-only non repo-wide: `main()` applica solo le REPLACEMENTS base).
- **D — artifact della sanitize storica** → ripristino da fonte AoN, poi ricategorizzazione A/C.

Risultato: feats 2837→2787 (49 in `feats_local.json`), traits 470→466 (4 in `traits_local.json`, 7 sanitize), equipment 790→786 (4 in `equipment_local.json`); **gate a 0 violazioni totali**; scansione word-boundary su name/description/prerequisites: 0 residui. Citazioni di libri PI in `source`/`tags`: sanitize (convenzione "the inner sea region Gods" / "a strict-order handbook"); titoli nel campo `source` di equipment/traits restano follow-up documentato.

## 5. Checklist di registrazione (anti-staleness)

Per ogni nuovo catalogo, TUTTI questi passi (la dimenticanza di uno si paga dopo):

1. `data/reference/manifest.json` → nodo `catalogs[]` (legal_filter + indexer) **e** nodo `files{}` (validate_schemas), con `entries` = **count reale** letto dal file.
2. `schemas/reference_catalog.schema.json` → nuove proprietà opzionali (oggi basta `mechanics` per tutto).
3. `tests/test_reference_catalogs.py` → il catalogo nelle invarianti (struttura, count, mechanics per kind).
4. `tools/legal_filter.py` → 0 violazioni (scansiona `catalogs[]`).
5. Reindice RAG: `.venv/Scripts/python tools/index_rag.py --include-local` (l'indexer legge `catalogs[]` automaticamente per kind arbitrari).
6. Moduli: gli elenchi kind nei disclaimer (`ruling_expert`, `archivist`, `adventurer_ledger`, `Encounter_Designer`, `minmax_builder`) vanno aggiornati; attenzione al **nome file** nel testo (`equipment_mundane.json`, non `equipment.json`).
7. `python launch.py test` → TUTTE LE VERIFICHE OK; YAML-check dei moduli `.txt` toccati.
8. Aggiornare `reports/data_quality_report.json` (rigenerato) e `sessione-2026-07-16/HANDOFF_ATTIVO.md`.

## 6. Test (pattern)

- **Parser: fixture HTML inline nei test** (stringhe), MAI rete. Includi i casi reali scoperti durante il build (righe-gruppo, en-dash, nomi con parentesi).
- **Invarianti permanenti** (`tests/test_reference_catalogs.py`): struttura entry, `source_id` unici globalmente, parità `files{}`↔`catalogs[]`, mechanics per kind, cross-ref (es. class_skills ↔ skills).
- **Gate verify**: `pytest -q` con **≥130 passed ed esattamente 1 skipped** — non aggiungere mai test skipped.
- Commit convenzionali (hook commit-guard: `type(scope): subject` ≤72 char, minuscolo, niente punto, MAI `Co-Authored-By:`).

## 7. Errori commessi (e da non rifare)

| Errore | Lezione |
|---|---|
| `CACHE_DIR` relativa al CWD | Ancorare i path a `Path(__file__).resolve().parents[1]` |
| CLI che non parte (`No module named 'tools'`) | Shim `sys.path.insert(0, parents[1])` in cima al tool |
| Flag `--write` cosmetico | Ogni builder prende `write=False` e gate davvero la scrittura |
| Selezione tabelle per posizione | AoN annida layout tables: selezione per header |
| Catch-all colonne → dati mislabeled | Whitelist sulle chiavi speciali |
| `source` hardcodata su tabelle multi-libro | Attribuzione per-voce dalle pagine dettaglio |
| Match case-sensitive (Knowledge) | Cross-ref case-insensitive + alias ("Knowledge (all)") |
| Assumere che le descriptions contengano i dati | Verificare un campione PRIMA di progettare il parser (feats: prerequisiti solo nell'indice, non nelle descriptions) |
| Fidarsi del gate PI | Supplemento + strip + scansione manuale a sottostringa |
| Prerequisiti autoreferenziali / punto finale | Passata di pulizia sui dati esistenti (`clean_existing_prerequisites`) |
| Manifest count a mano | Leggere i count reali dai file; test di parità permanente |

## 8. Come aggiungere un nuovo dominio (ricetta)

1. Ricognizione fonte: URL esatto, struttura (tabella? bold-led? indice+dettaglio?), PI atteso, segnalato nella pagina o dedotto dalla citazione fonte.
2. Scrivi `parse_<domain>()` + 2-3 test su fixture inline (includi il markup REALE appena visto).
3. `build_<domain>(write=False)` con assert di sanità (conteggio minimo, campi chiave non vuoti) + DOMAINS.
4. Dry-run: ispeziona 3-5 entry a campione contro la pagina.
5. Scrittura, PI scan (gate + supplemento se serve + scansione manuale), report rimossi.
6. Checklist di registrazione (§5) completa, commit, handoff.

---

*Playbook creato il 2026-07-18 al termine del Lotto 4 Fase 1. Prossimi import candidati: archetipi strutturati, classi base/advanced/hybrid/occult, razze non-core, mostri v2 (statblock strutturati), spell per-day per classi non-core.*
