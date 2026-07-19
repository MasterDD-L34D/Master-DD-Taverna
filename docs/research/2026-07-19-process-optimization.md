# Ricerca: valorizzare il materiale scartato, deduplicare i processi, usare meglio gli swarm — 2026-07-19

> Sintesi di 3 ricerche parallele (swarm) commissionate dall'utente: (A) materiale analizzato/fetchato e poi "buttato", (B) ripetizioni nella pipeline fetch→parse→catalogo→consumer, (C) uso di swarm/subagent/skill con determinismo intatto. Ogni proposta ha costo/beneficio stimato. **Nulla qui è implementato: sono proposte da decidere.**

---

## A. Cosa "buttiamo" e cosa vale (inventario verificato su file)

Il progetto oggi scarta o ignora materiale già in casa:

| Materiale | Quantità | Perché scartato | Riuso proposto | Valore/costo |
|---|---|---|---|---|
| **Mostri: ~23 campi strutturati della fonte** (CR, AC, HD, BAB, attacks, saves, ability_scores, skills, special_abilities) | 199 mostri, fonte `data/full/data.json` (46 MB) già a dict | `convert_monsters` appiattisce 8 campi in testo inline | **`mechanics` strutturati** (nessun parsing, una run) — Encounter_Designer li dichiara già fonte nemici | **Alto / Basso** ⭐ |
| **Spells: campi in description key:value + cache gist strutturata** (school, spell_level, components, range, duration, save, SR; cache gist 2.827 entry) | 1.035 spell (99% con School/Level nel testo) | Import storico testuale | **`mechanics.spells`** via join gist + fallback regex → sblocca builder caster (slot già in `classes.progression.spells_per_day`) | **Alto / Medio-basso** ⭐ |
| **mechanics non indicizzati nel RAG** (progressioni, tratti razziali, statblock) | 6.733 chunk senza mechanics | indexer legge solo name/prereq/description/notes/tags | Serializzare mechanics come testo nei chunk + `--include-local` nel workflow standard | **Alto / Basso** ⭐ |
| **Description equipment complete** (sezioni Statistics/Description) | 808 pagine dettaglio in cache | Import prese solo il libro Source | Parser sezioni → description ricche per RAG e schede | Medio-alto / Medio-basso |
| **Class features text** (rage powers, mercy, talents...) | 12 pagine classe in cache (~19k chars/classe) | Parsata solo la tabella | Catalogo `class_features` (markup complesso) | Alto / Medio-alto |
| **Entry PI rimosse/filtrate** (80 traits complete, 2 feats, 61 prerequisiti, 5 equipment, ~43 feats PI preesistenti) | ~190 entry | Policy OGL-committabile | **`pi_local_only/`** (uso locale non redistribuito): `traits_local.json`, `feats_local.json` con fonte completa da git history/re-parse | Medio / Basso |
| **Subrazze + alternate racial traits** | 24 pagine in cache, zero fetch | Fail-closed per PI | `pi_local_only/subraces.json` (markup variegato) | Medio / Medio |
| **Campi importati ma mai letti dall'engine** (`traits.prerequisites`, `equipment.weight/dmg_s/type`, `classes.proficiencies`, `races.traits[].text`) | — | engine minimo voluto | Consumer upgrade senza nuovi import (validazione tratti, ingombro, PG Small, check proficiency, scheda) | Medio / Basso |
| **4 PDF homebrew + 105 build in `src/data/`** | ~30 MB | indexer solo .txt/.md | Estrazione testo + indicizzazione | Basso-medio / Medio (dipendenza nuova) |

**Quick win (tutto offline, zero fetch): mostri v2, spells strutturate, RAG con mechanics.**

## B. Deduplicazione pipeline (ripetizioni misurate)

Trovate: 2 fetcher paralleli con 2 cache (`reference_fetch` nuovo vs `enrich_reference` vecchio, con accoppiamento incrociato: `_feat_card_prereq_lookup` legge la cache dell'altro); reindex **totale a ogni run** (~1 min per 6.733 chunk anche se cambia una riga) con bug di duplicazione su merge senza dedup; builder che riscrivono i JSON anche quando identici (mtime inaffidabile); verify che rilegge gli stessi 5,5 MB in 4-5 subprocess separati; `class_skill_matches` copiato in due punti.

| # | Proposta | Cosa cambia | Valore/costo |
|---|---|---|---|
| **B1 ⭐** | **Reindex incrementale per hash contenuto** — chunk id = `sha256(text)[:16]`; ri-encode solo testi nuovi/cambiati; dedup per id gratis; stabile a inserimenti mid-catalogo | `src/rag/indexer.py` solo | **Alto / Medio-basso** (1 min → secondi per piccoli cambi; chiude il bug extend) |
| **B2** | **Write-if-changed + `import_state.json`** per dominio (last_run, entry_count, sha) | `tools/import_reference.py` | Medio-alto / Basso — rende i segnali mtime/hash affidabili (prerequisito di B1) |
| **B3** | **Unificare fetch** — funzioni vive fuori da `enrich_reference` in modulo neutro; cache feats via `reference_fetch`; deprecare main() con path morti | `tools/enrich_reference.py`, `tools/import_reference.py` | Medio / Medio — ⚠️ `.cache/enrichment` è l'unica fonte offline dei prerequisiti feats: migrare, non cancellare |
| **B4** | **legal_filter: una regex ad alternanza** (oggi ~54 finditer per stringa) + `tests/conftest.py` session-scoped per caricare i cataloghi una volta per processo | `tools/legal_filter.py`, nuovo conftest | Medio-basso / Basso |
| **B5** | **Dedup `class_skill_matches`** — implementazione in `src/pc/catalogs.py`, import in `tools/import_reference.py` | 2 file | Basso / Basso |

**NON ottimizzare**: riletture JSON tra i 4 tool del verify (subprocess isolati per design, <1s); migrazione chiavi cache AoN (885 file, rischio re-download); fetch parallelo (cortesia 2s verso aonprd — vedi sotto); unificare PathfinderMonsterDatabase (archivio, PI local-only per scelta); cache modello embeddings (non è il collo).

## C. Processo ibrido swarm + determinismo (validato)

Correzione del vincolo noto: il collo del fan-out è il **file codice** `tools/import_reference.py` (unico modulo), non i dati (ogni dominio ha il suo JSON; uniche dipendenze dati: skills legge classes, feats legge feats).

**Architettura proposta:**
1. **Fase 0 — seriale, sempre**: `grill-me` sulla spec → `writing-plans` → **warm-cache seriale** (fetch con delay 2s cortese verso aonprd; ~30s per 12 pagine). Il fetch parallelo è vietato per policy, ma dopo questa fase è **tutto offline**.
2. **Fase build — sequenziale subagent-driven classico** sul codice condiviso (parser comune + varianti con fixture reali).
3. **Fase review — swarm per-item** (1 reviewer per razza/classe/dominio) con **fixture-fedeltà come golden check**: ogni reviewer verifica 3-5 entry contro il dump in cache + sanity RAW. PI scan parallelo.
4. **Gate finali — seriali, controller-owned, mai delegati**: invarianti in `test_reference_catalogs.py`, `legal_filter` 0, `validate_schemas` 0, suite completa (≥passed attuali, esattamente 1 skipped), reindice, `launch.py test`, commit/push con trailer ADR-0011.

**Split lazy del modulo import (opzione raccomandata)**: estrarre `tools/reference_lib.py` con gli helper condivisi **solo quando arriva il prossimo dominio nuovo** (spells mechanics, classi mancanti, mostri v2): i nuovi domini vivono in `tools/import_<domain>.py`, `import_reference.py` re-esporta tutto (i 15+ simboli importati dai test attuali restano il gate di regressione). Nessuna migrazione dei 7 domini esistenti.

| Usare swarm per | NON usare swarm per |
|---|---|
| Review per item su file+cache (RAW, convenzioni, regressioni) | Scrittura di file condivisi (`import_reference.py` pre-split, manifest, handoff) |
| PI scan per dominio + report al controller | Fetch di rete (cortesia 2s: seriale) |
| Triage formati pagina su cache offline | Task con dipendenze (skills dopo classes; manifest dopo tutto) |
| Ricerca fonti/schemi esterni (`last30days`) | Gate finali (legal, pytest, launch.py, reindice, commit/push) |
| Audit pre-refactor (`codebase-map`/`graphify`) | Validazione PI con artifact committati (mostri = pi_local_only) |
| Verifica drift handoff↔repo (precedente crash 07-17) | Review senza accesso a file/comandi reali (teatro) |

**Skill da attivare nei prossimi lotti**: `grill-me` **prima della spec di mostri v2** (lotto più ambiguo: schema, campi, fonte, implicazioni PI); `codebase-map` **prima dello split** di import_reference (grafo import); `code-review` **sulla final review dei lotti grandi** (fan-out per aspetto con scoring); `last30days` per schemi statblock open esistenti (non inventare).

## Roadmap consigliata (ordine valore/costo)

1. **Quick win offline** (tutto in casa, zero fetch, sbloccano consumer): mostri v2 `mechanics`, spells `mechanics` (gist+regex), RAG chunk con mechanics (`indexer.py` poche righe), B1 reindex incrementale, B2 write-if-changed, B5 dedup class_skill_matches, B4 conftest+regex.
2. **Split lazy + spells builder**: `reference_lib` + `tools/import_spells.py` (primo dominio nuovo nel pattern parallelo-sicuro) → builder caster con spells/day.
3. **Classi mancanti** (12: Alchemist in testa) con processo ibrido completo: grill-me → warm-cache → build sequenziale → review swarm 12-way → gate seriali → **diff oracolo a tre** sulle build sbloccate (13→fino a 28/28 potenziale).
4. **Mostri v2** (dopo grill-me): statblock strutturato in `pi_local_only/`, validazione per CR-band, report non committati.
5. **Triage PI feats preesistenti** (~43 entry registrate nel debito) con decisione policy documentata.
6. Dopo: equipment descriptions da cache dettaglio, class_features catalog, subraces in pi_local_only, engine consumer dei campi importati.

---

*Ricerca eseguita con 3 explore agent in parallelo (dogfood del punto C). Fonti verificate su file reali: tools/import_reference.py, src/rag/indexer.py, tools/legal_filter.py, tools/enrich_reference.py, tools/import_monsters.py, src/pc/engine.py, tests/*, manifest, reports/pi_removed_traits.txt, .cache/enrichment, data/reference/aon_cache (885 file / 40 MB).*
