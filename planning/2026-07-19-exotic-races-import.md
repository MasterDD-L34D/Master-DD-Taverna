# Exotic Races Import (Oracle Coverage) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Estendere `races.json` dalle 7 core alle 24 razze del corpus build (7 core + 17 esotiche), portando la copertura dell'oracolo a tre vie (pathmaster v1 | v2 | Taverna) da 7/28 a **13/28 build confrontabili**.

**Architecture:** La pipeline esiste gia' (`tools/import_reference.py`, dominio `races` con merge in place su `data/reference/ogl/races.json`, parser bold-led di `RacesDisplay.aspx`). Il lotto estende la lista razze con le 17 esotiche presenti nel corpus (`src/data/builds/`), tutte disponibili su aonprd (verificato 200 su tutte e 17 il 2026-07-19). Poi legal/PI check, manifest counts, reindice.

**Tech Stack:** `docs/IMPORT_PLAYBOOK.md` come metodo; test pytest; nessuna nuova dipendenza.

**Le 17 razze esotiche (corpus):** Catfolk, Fetchling, Goblin, Grippli, Kasatha, Kitsune, Oread, Samsaran, Shabti, Strix, Suli, Sylph, Tengu, Tiefling, Vanara, Vishkanya, Wayang.

**Sblocco oracolo (join corpus misurato 2026-07-19):** barbarian/fetchling, bard/kitsune, cleric/samsaran, druid/wayang, magus/kitsune, monk/vanara (tutti con classi core gia' coperte) = +6 build (7 → 13/28). Le altre 15 richiedono classi mancanti (Alchemist, Arcanist, Bloodrager, Brawler, Cavalier, Gunslinger, Hunter, Inquisitor, Investigator, Kineticist, Medium, Witch) — lotto successivo.

**Rischi noti:**
- Formati ability mods esotici (varianti "Choose one", mod flessibili per sub-specie, razze senza mods, construct traits per Shabti): il parser ha il fallback `{"any": 2}` per "to one ability"; per formati diversi adattare con test su fixture reale.
- Sezioni subrazze/alternate traits: lo scoping fail-closed del Task 3 lotto 4 le esclude gia' — verificare che i tratti base delle esotiche siano nella sezione "Racial Traits" standard.
- **PI**: Shabti (Mummy's Mask), Samsaran/Wayang/Vishkanya/Grippli/Vanara (Blood of Shadows), Suli (Qadira), Tengu/Kitsune/Catfolk (Dragon Empires) sono libri legati a Golarion: il testo dei tratti puo' contenere termini PI. Gate: `legal_filter` + `TRAITS_PI_SUPPLEMENT`-style scan manuale con la lista del Lotto 4 Task 7.

---

### Task 1: Estensione lista + build import + parser esotici

**Files:**
- Modify: `tooling/Master-DD-Taverna/tools/import_reference.py` (RACES list + parser se serve)
- Modify (generato): `tooling/Master-DD-Taverna/data/reference/ogl/races.json`
- Modify: `tooling/Master-DD-Taverna/tests/test_import_reference.py`

- [ ] **Step 1: Estendere la lista e lanciare in dry-run**

In `tools/import_reference.py`, dopo `RACES_CORE` aggiungere:

```python
RACES_EXOTIC = ["Catfolk", "Fetchling", "Goblin", "Grippli", "Kasatha", "Kitsune",
                "Oread", "Samsaran", "Shabti", "Strix", "Suli", "Sylph", "Tengu",
                "Tiefling", "Vanara", "Vishkanya", "Wayang"]
RACES_ALL = RACES_CORE + RACES_EXOTIC
```

e in `build_races` usare `RACES_ALL` (il merge in place aggiorna le 7 core e aggiunge le 17 nuove).

- [ ] **Step 2: Dry-run e triage parser**

Run: `cd tooling/Master-DD-Taverna && python tools/import_reference.py --domain races`
Expected: report 24 entry, NESSUN assert fallito su `ability_mods` vuoti. Per OGNI razza che fallisce (mods vuoti o formato diverso):
1. ispeziona il dump in `data/reference/aon_cache/` (o riscarica con delay),
2. adatta il parser (varianti: "Choose one" → `{"any": 2}`? mods flessibili per sub-specie → prendere la forma base; razze con mods in formato diverso tipo "+2 Dexterity, +2 Charisma, -2 Strength" vs "to one ability"),
3. aggiungi una fixture del formato reale a `tests/test_import_reference.py`.

- [ ] **Step 3: Test parser su formati esotici**

Aggiungere a `tests/test_import_reference.py` 2-3 test con fixture ricalcate sui formati REALI trovati al punto 2 (una per formato problematico: variante "choose", mods misti, sezione tratti non standard). Ogni test asserisce `ability_mods` corretto e almeno 1 tratto parsato.

- [ ] **Step 4: Write + verifica contenuto**

Run: `cd tooling/Master-DD-Taverna && python tools/import_reference.py --domain races --write`
Expected: `scritto .../races.json (24 entry)`. Verifica a campione:
`.venv/Scripts/python -c "import json; d=json.load(open('data/reference/ogl/races.json',encoding='utf-8')); print(len(d['entries'])); print([(e['name'], e['mechanics']['ability_mods'], e['mechanics'].get('size'), e['mechanics'].get('speed')) for e in d['entries'] if e['name'] in ('Goblin','Tiefling','Kitsune','Shabti','Strix','Kasatha')])"`
Atteso: mods corretti (Goblin {dex:2,cha:2,str:-2}, Tiefling {dex:2,int:2,cha:-2}, Kitsune {dex:2,cha:2,str:-2}...); Small per Goblin/Halfling-size; campi curati delle 7 core preservati (merge in place).

- [ ] **Step 5: Legal + PI scan manuale**

Run: `cd tooling/Master-DD-Taverna && .venv/Scripts/python tools/legal_filter.py` → 0 violazioni (races.json e' nel manifest da Lotto 4).
Poi scan manuale (stessa tecnica del Lotto 4 Task 7) con i 32 termini supplemento + demonimi su name/description/notes/tratti delle nuove 17 entry: rimuovere i termini PI dai testi tratti (strip della frase, non della entry, se il tratto e' OGC; rimuovere il tratto se e' PI sostanziale). Documentare i casi nel report.

- [ ] **Step 6: Commit**

```bash
cd tooling/Master-DD-Taverna
git add tools/import_reference.py tests/test_import_reference.py data/reference/ogl/races.json
git commit -F commit_msg.txt  # subject: feat(reference): import 17 exotic races from aonprd
# trailer: Coding-Agent: kimi-code-cli + Trace-Id: <uuidv7> (ADR-0011, vedi AGENTS.md)
```

---

### Task 2: Manifest counts + reindice + verifica + handoff

**Files:**
- Modify: `tooling/Master-DD-Taverna/data/reference/manifest.json` (races entries 7 → 24 in `catalogs[]` e `files{}`, `last_verified: 2026-07-19`)
- Modify: `sessione-2026-07-16/HANDOFF_ATTIVO.md` (controller)

- [ ] **Step 1: Manifest**

Aggiornare `entries` per il kind `races` a 24 (o il numero reale post-import) in entrambi i nodi del manifest + `last_verified`.

- [ ] **Step 2: Test invarianti**

Run: `cd tooling/Master-DD-Taverna && .venv/Scripts/python -m pytest tests/test_reference_catalogs.py -q`
Expected: 5 passed (la parita' manifest↔files obbliga i count aggiornati; `test_classes_races_mechanics` richiede ability_mods non vuoto per OGNI razza: se un'esotica ha mods vuoti per formato legittimo, documentare l'eccezione nel test con la ragione, NON indebolire l'invariante per le altre).

- [ ] **Step 3: Reindice + verifica completa**

Run: `cd tooling/Master-DD-Taverna && .venv/Scripts/python tools/index_rag.py --include-local 2>&1 | tail -2`
Run: `cd C:/dev/pathfinder && python launch.py test` → TUTTE LE VERIFICHE OK.

- [ ] **Step 4: Verifica copertura oracolo**

Ricalcolare il join corpus: le 6 build sbloccate devono essere comparabili (razza presente in races.json con ability_mods): script rapido che per le 6 build (barbarian/fetchling, bard/kitsune, cleric/samsaran, druid/wayang, magus/kitsune, monk/vanara) verifica `catalogs.get_race(race) is not None`.

- [ ] **Step 5: Commit + handoff + push**

Commit manifest (`chore(reference): register exotic races in manifest`, con trailer ADR-0011). Aggiornare `HANDOFF_ATTIVO.md` (riga + voce completato: 24 razze, oracolo 13/28). Push.

---

## Note operative

- Se una pagina AoN ritorna 200 ma formato non standard (tabella al posto di bold-led): adattare il parser o segnalarla come skip documentato (NON inventare mechanics a mano).
- Kasatha/Strix: pur essendo su AoN (200), potrebbero non essere Paizo-PRD (3PP hostato): se la fonte citata in pagina non e' Paizo OGL, importarle con `source` onesta (3PP book) e segnalare nel commit — OGL 3PP e' importabile ma va attribuito correttamente.
- Speed formati: razze con "Slow and Steady" vs "Normal Speed" vs forme diverse ("Speed 30 ft." diretto): il parser copre i primi due; estendere il terzo se serve.
- Commit convenzionali + trailer `Coding-Agent:`/`Trace-Id:` (ADR-0011, da AGENTS.md), MAI `Co-Authored-By:`.
