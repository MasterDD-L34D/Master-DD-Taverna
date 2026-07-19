# Split Lazy reference_lib + Spells Builder (caster spells/day) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Roadmap 2 di `docs/research/2026-07-19-process-optimization.md`: estrarre `tools/reference_lib.py` (split lazy), creare `tools/import_spells.py` (primo dominio nuovo nel pattern parallelo-sicuro), evolvere il builder deterministico `src/pc/` perché i caster usino spells/day (`classes.progression.spells_per_day`) e i `mechanics` di spells.json.

**Architecture:** Task 1 muove gli helper condivisi in `reference_lib` lasciando `import_reference` come facade di re-export (i 16 simboli importati dai test = gate di regressione, zero modifiche ai test); Task 2 aggiunge il dominio spells come modulo proprio senza toccare il modulo condiviso; Task 3 insegna al motore deterministico a validare la selezione incantesimi; Task 4 chiude i gate seriali e segnala il cambio di contratto all'oracolo a tre vie (`docs/WORKFLOW.md` §4).

---

### Task 1: `tools/reference_lib.py` + re-export (nessun cambio comportamento)

**Files:**
- Create: `tooling/Master-DD-Taverna/tools/reference_lib.py`
- Modify: `tooling/Master-DD-Taverna/tools/import_reference.py` (solo import/re-export)
- Test: `tooling/Master-DD-Taverna/tests/test_import_reference.py` (NON toccare: è la gate)

- [ ] **Step 1: Baseline**

Run: `cd tooling/Master-DD-Taverna && .venv/Scripts/python -m pytest tests/test_import_reference.py tests/test_reference_catalogs.py -q`
Expected: tutto verde (baseline repo: 237 passed, 1 skipped su tutta la suite).

- [ ] **Step 2: Crea reference_lib con gli helper condivisi**

Muovere (non copiare) da `import_reference.py`: costanti `OGL_DIR/LICENSE/SOURCE/BASE`, `slug`, `source_id`, `clean`, `_cell_text`, `table_rows`, `write_catalog`, `_to_bonus`, `_parse_level`, `_header_index`, `_class_skill_matches`, `extract_prerequisites`, `split_prereq_string`, `clean_existing_prerequisites`. Lasciare in `import_reference.py` i parser/builder di dominio e i supplementi PI per-dominio.

- [ ] **Step 3: import_reference come facade**

In `tools/import_reference.py`: `from tools.reference_lib import (...)` per TUTTI i 16 simboli importati dai test (`SKILL_HEADER_RE, _class_skill_matches, parse_abilities, parse_class, parse_equipment_table, parse_item_source, parse_race, parse_skill, parse_traits, source_id, slug, extract_prerequisites, _trait_pi_hits, parse_feats_index, split_prereq_string, clean_existing_prerequisites`). I simboli di dominio restano definiti qui; quelli spostati sono solo re-esportati.

- [ ] **Step 4: Run test gate**

Run: `.venv/Scripts/python -m pytest tests/test_import_reference.py tests/test_reference_catalogs.py tests/test_pc_engine.py -q`
Expected: verde identico alla baseline, zero modifiche ai test.

- [ ] **Step 5: Commit** `refactor(tools): extract shared reference_lib helpers` (trailer ADR-0011).

---

### Task 2: `tools/import_spells.py` — primo dominio parallelo-sicuro

**Files:**
- Create: `tooling/Master-DD-Taverna/tools/import_spells.py`
- Test: `tooling/Master-DD-Taverna/tests/test_import_spells.py` (nuovo, fixture HTML inline)
- Modify (generato): `tooling/Master-DD-Taverna/data/reference/ogl/spells.json` (merge in place)
- Modify: `tooling/Master-DD-Taverna/data/reference/manifest.json` (note/count se cambiano)

- [ ] **Step 1: Ricognizione fonte AoN**

Verifica su 2 pagine `SpellDisplay.aspx` in `data/reference/aon_cache` la forma reale (tabella? righe bold-led come traits? header key:value come le description d20pfsrd?). Riporta le forme esatte nel report. Decidi se il tool fa merge in place su spells.json (pattern `build_races`/`build_classes`: update by name, preserva description/tags curate) con fonte AoN aggiunta a `reference_urls`/`_source`.

- [ ] **Step 2: Write the failing test** — fixture HTML inline (MAI rete):

`parse_spell(html, name)` -> entry catalogo con mechanics (school, spell_level dict, casting_time, components, range, duration, saving_throw, spell_resistance); riusa `parse_spell_level`/`parse_description_mechanics` di `tools/enrich_spells.py` se la forma dell'header coincide (import diretto o promozione in reference_lib).

- [ ] **Step 3: Implement** pattern dominio

`parse_spell(html, name)` + `build_spells(write=False)` (fetch via `tools.reference_fetch.fetch`, merge in place, report matched/unmatched, assert di copertura, PI scan via `legal_filter._find_pi` su campi testuali, fail-closed come traits). CLI `main()` con `--write` (specchio di `import_reference.main`, ma file proprio: niente registrazione in `DOMAINS` — il punto del pattern è NON toccare il modulo condiviso).

- [ ] **Step 4: Run + checklist registrazione (`docs/IMPORT_PLAYBOOK.md` §5)**

Run: `.venv/Scripts/python tools/import_spells.py` (report), poi `--write` se il merge cambia qualcosa. Verifiche: `manifest.json` catalogs[]+files{} count reale; `tests/test_reference_catalogs.py` invarianti verdi; `tools/legal_filter.py` → 0; `tools/validate_schemas.py` → 0.

- [ ] **Step 5: Commit** `feat(reference): add aon spells domain importer` (trailer ADR-0011).

---

### Task 3: Builder caster — spells/day + validazione selezione incantesimi

**Files:**
- Modify: `tooling/Master-DD-Taverna/src/pc/models.py` (campo `spells: list = []`)
- Modify: `tooling/Master-DD-Taverna/src/pc/catalogs.py` (kind "spells" + `find_spell`)
- Modify: `tooling/Master-DD-Taverna/src/pc/engine.py` (`validate_spells` + render)
- Test: `tooling/Master-DD-Taverna/tests/test_pc_engine.py`, `tests/test_pc_api.py`

- [ ] **Step 1: Write the failing tests**

Casi: (a) Wizard lv1 con ["Magic Missile", "Mage Armor"] -> `sheet["spells"]` ok, nessun errore; (b) spell sconosciuto -> errore bloccante; (c) spell non della classe ("Cure Light Wounds" per Wizard) -> errore; (d) spell di cerchio senza slot (Paladin lv4: `spells_per_day {"1st": "0"}` -> cerchio 1 non castabile) -> errore; (e) non-caster con spells -> errore dichiarato; (f) `spells` omesso -> comportamento identico a oggi (retrocompatibilità oracolo).

- [ ] **Step 2: catalogs**

`"spells": "spells.json"` nella mappa `load` (`src/pc/catalogs.py:12-16`), `find_spell(name)` per nome; helper `spell_level_for_class(spell, class_name)`: normalizza case e splitta le chiavi combinate ("sorcerer/wizard" -> {sorcerer, wizard}); classi assenti da classes.json (bloodrager...) ignorate senza errore.

- [ ] **Step 3: engine.validate_spells(draft, sheet)**

Dopo `validate_feats` (`src/pc/engine.py:399`). Regole DICHIARATE in docstring (contratto WORKFLOW §4):
- non-caster (nessuna riga `spells_per_day` in progressione): selezione spells -> errore;
- per ogni spell: esiste in catalogo? `spell_level` contiene la classe (post-split)? cerchio <= max cerchio con slot > 0 al livello (valori `spells_per_day` sono STRINGHE: int(); `"0"` = nessuno slot base -> cerchio non castabile, es. Paladin lv4);
- `sheet["spells"]` = lista entry validate con `{name, level (per questa classe), school}`;
- fuori scope dichiarato: spells known vs prepared, bonus spells da ability score, caster level separato da class level.

- [ ] **Step 4: render_markdown** — sezione `**Incantesimi**` + riga slot/giorno (cambio output: da segnalare in commit body per l'adapter oracolo, WORKFLOW §4).

- [ ] **Step 5: Run test + verifica API**

Run: `.venv/Scripts/python -m pytest tests/test_pc_engine.py tests/test_pc_api.py -q`
Verifica manuale: POST /pc/build con draft Wizard lv3 + spells -> sheet con spells e spells_per_day.

- [ ] **Step 6: Commit** `feat(pc): caster spell selection validated against spells/day` (trailer ADR-0011; body: nota cambio forma output sheet per oracolo pathmaster-dd).

---

### Task 4: Gate finali + segnalazione oracolo

- [ ] **Step 1:** Suite completa: `.venv/Scripts/python -m pytest tests/ -q` -> >= 237 passed, esattamente 1 skipped (mai aggiungere skipped).
- [ ] **Step 2:** `tools/legal_filter.py` -> 0; `tools/validate_schemas.py` -> 0; reindice `.venv/Scripts/python tools/index_rag.py --include-local` (dati reference toccati; incrementale, atteso solo delta).
- [ ] **Step 3:** `python launch.py test` dalla root workspace -> TUTTE LE VERIFICHE OK.
- [ ] **Step 4:** Aggiorna README/docstring limitazioni builder (cosa il motore NON modella: spells known/prepared, bonus spells) e `sessione-2026-07-16/HANDOFF_ATTIVO.md`; nota a pathmaster-dd sul nuovo campo opzionale `spells` del draft e sulle nuove chiavi dello sheet.
- [ ] **Step 5: Commit** `docs(pc): document caster spell support and contract change` (trailer ADR-0011).

---

## Note operative

- Task 1 deve precedere 2 e 3 (3 non dipende da 2: la selezione spell usa spells.json già arricchito; 2 e 3 sono parallelizzabili su file disgiunti).
- Fetch di rete: solo seriale con delay 2s (policy cortesia aonprd); test sempre su fixture.
- `spells_per_day` valori stringa -> int() obbligatorio; chiave "0" = cantrips (prepared), assente per Sorcerer (a volontà): trattare l'assenza come "nessun vincolo di slot".
- Commit convenzionali + trailer ADR-0011 (`Coding-Agent: kimi-code-cli`, `Trace-Id: uuidv7`), MAI `Co-Authored-By:`; niente refactor fuori scope.
- Questo file di piano entra nel commit del Task 4 (docs).

## Ambiguità dichiarate (decise dal controller)

- **Scope di `import_spells.py`**: la ricerca non specifica cosa importa — lettura coerente col "pattern parallelo-sicuro": importer di dominio AoN che fa merge su `spells.json` (come `build_races`/`build_classes`). Lo Step 1 del Task 2 (ricognizione fonte) chiarisce prima dell'implementazione.
- **Semantica spells/day**: `spells_per_day` conta gli *lanci*, non le spell note/preparate — la validazione proposta (esistenza + classe + cerchio castabile) è il minimo RAW difendibile; contare la selezione contro gli slot sarebbe sbagliato per i caster prepared.
