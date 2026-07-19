# Missing Classes Import (Oracle Coverage) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Estendere `classes.json` da 12 a 24 classi (12 core + Alchemist, Arcanist, Bloodrager, Brawler, Cavalier, Gunslinger, Hunter, Inquisitor, Investigator, Kineticist, Medium, Witch), portando la copertura oracolo da **13/28 a 28/28** build confrontabili (paladin_aasimar resta fuori per razza Aasimar mancante).

**Architecture:** pipeline esistente (`build_classes`, merge in place, dominio già registrato — nessun nuovo modulo). Processo ibrido da `docs/research/2026-07-19-process-optimization.md` §C: warm-cache seriale → build sequenziale sul file condiviso → **review swarm 12-way per classe** (fixture-fedeltà vs cache) → gate seriali controller-owned.

**Forme tabella (verificate live 2026-07-19, da ricontrollare su cache al Task 1):** tutte compatibili col parser (`_header_index` entro 3 righe, scarto righe colspan). Alchemist/Investigator hanno **Extracts per Day** (colonne `1st…6th`); Arcanist `1st…9th` senza "0"; Bloodrager/Medium `1st…4th`; Hunter/Inquisitor `1st…6th` senza "0"; Witch full caster `0,1st…9th`; Brawler `Unarmed Damage` → `extra_progression`; Cavalier/Gunslinger/Kineticist pulite (nessuna colonna Burn/Spirit).

## Decisioni controller (grill documentato — sessione auto, niente grill interattivo)

- **(a) Extracts → `spells_per_day`**: accettato e dichiarato. Alchemist/Investigator diventano "caster" per `validate_spells` del builder: semantica estratti ≈ livelli incantesimo (spell_level "alchemist"/"investigator" già presenti in spells.json dal gist). Limitazione dichiarata in docstring/README: estratti ≠ incantesimi RAW (niente spell trigger implicito nel builder).
- **(b) `source_id` slug `pfrpg_core:` per tutte**: mantenuto (pattern attuale, unicità garantita, nessun consumer dipende dal libro fonte).
- **(c) Campi curati assenti sulle 12 nuove entry** (`status`/`reviewed_by`/ecc.): lo schema non li richiede; valorizzarli fittiziamente sarebbe disonesto.
- **(d) `reports/data_quality_report.json`**: rigenerato da zero ai gate finali e incluso nel commit dei gate.
- **Fonte onesta per classe** via `CLASS_SOURCES` (APG: Alchemist, Cavalier, Inquisitor, Witch; UC: Gunslinger; ACG: Arcanist, Bloodrager, Brawler, Hunter, Investigator; OA: Kineticist, Medium; UM: Magus) — niente "PFRPG Core" per tutte.

---

### Task 1: Warm-cache seriale + fixture dump

**Files:** (cache gitignored) `data/reference/aon_cache/`; nessun file committato.

- [ ] **Step 1: Warm-cache** — fetch seriale (delay 2s) delle 12 pagine `ClassDisplay.aspx?ItemName=<Classe>` via `tools/reference_fetch.py`. Expected: 12 file nuovi, cache 888 → 900.
- [ ] **Step 2: Dump forme reali** — per OGNI classe: header row idx, elenco colonne, 2 righe dati campione (lv1, lv20), testo esatto Hit Die / Starting Wealth / Skill Ranks / class skills / proficiencies. Output = allegato fixture per il Task 2.

### Task 2: Lista + mappa fonti + import/merge 12 classi

**Files:**
- Modify: `tools/import_reference.py` (`CLASSES_MISSING`, `CLASS_SOURCES`, `build_classes`)
- Modify (generato): `data/reference/ogl/classes.json`
- Modify: `tests/test_import_reference.py`

- [ ] **Step 1: Estendere lista e fonti** — `CLASSES_MISSING` (12 nomi), `CLASS_SOURCES` come da decisioni controller; `parse_class` usa la mappa per `source`/tag (`base` APG/UC, `hybrid` ACG, `occult` OA); `build_classes` itera `CLASSES_CORE + CLASSES_MISSING`.
- [ ] **Step 2: Dry-run + triage** — `python tools/import_reference.py --domain classes` → 24 entry, nessun assert (`progression==20`, `hd`). Per ogni classe fallita: ispeziona dump cache, adatta parser, fixture reale nel test.
- [ ] **Step 3: Test parser su formati reali** — 3 fixture inline da cache: (a) caster con riga-gruppo + extracts (Alchemist: `spells_per_day` con `1st…6th`); (b) extra_progression (Brawler: `Unarmed Damage` NON in spells_per_day); (c) full caster con colonna "0" (Witch). Stile di `test_parse_class` esistente.
- [ ] **Step 4: Write + verifica campione** — `--write` → `classes.json (24 entry)`. Verifica a campione (BAB/HD/saves lv1 e lv20 di Alchemist, Kineticist, Witch vs pagina; campi curati delle 12 core preservati).
- [ ] **Step 5: Legal + PI scan** — `tools/legal_filter.py` → 0; scansione manuale sottostringa (~30 termini Golarion) su name/description/special/class_skills delle 12 entry.
- [ ] **Step 6: Commit** — `feat(reference): import 12 missing classes from aonprd` (trailer ADR-0011, `git commit -F`).

### Task 3: Review swarm per-classe (12 reviewer in parallelo)

**Files:** nessuna modifica — report al controller.

- [ ] **Step 1:** Un reviewer per classe: 3-5 punti dati (BAB/saves/special lv1, lv5, lv10, lv20; spells/extracts a 2 livelli) verificati contro il dump in cache + sanity RAW (HD coerente col BAB; saves buone/cattive). Report tabellare: OK / mismatch con evidenza.
- [ ] **Step 2:** PI scan parallelo per classe (stessa lista del Task 2 Step 5) — doppio controllo indipendente.
- [ ] **Step 3:** Triage controller dei mismatch: fix parser + re-run (idempotente) o eccezione documentata nel test. Verifica incrociata `_granted_feats`: Brawler/Alchemist con eventuali grant lv1 attesi (comportamento da dichiarare, WORKFLOW §4).

### Task 4: Gate + misura oracolo

**Files:** `data/reference/manifest.json`, `data/reference/SOURCES.md`, `src/pc/catalogs.py` (solo docstring), `docs/WORKFLOW.md` (riga copertura).

- [ ] **Step 1: Manifest + SOURCES** — `entries` classes 12 → 24 in `catalogs[]` e `files{}`; notes e `last_verified`; `SOURCES.md:26` (count/composizione) e chiusura nota `:58`.
- [ ] **Step 2: Invarianti** — `pytest tests/test_reference_catalogs.py -q` verde (mechanics 20 livelli × 24, cross-ref class skills, formato spells_per_day, parità manifest).
- [ ] **Step 3: Docstring catalogs** — aggiornare il commento di `spell_level_for_class` (`src/pc/catalogs.py:80-82`): bloodrager & co. ora presenti; nota in commit body sul cambio di matchabilità (contratto §4).
- [ ] **Step 4: Misura oracolo** — script di join normalizzato (normalizzazione `[^a-z]` su lower, gestisce "Half Orc"/"Halfelf"/minuscole del corpus) → **atteso 28/29**; riportare nel commit body e in handoff le 15 build sbloccate per nome.
- [ ] **Step 5: Gate finali seriali** — suite completa → ≥259 passed, esattamente 1 skipped; legal_filter → 0; validate_schemas → 0; reindice incrementale (delta ~12 chunk); `python launch.py test` dalla root → TUTTE LE VERIFICHE OK; rigenerare `reports/data_quality_report.json`.
- [ ] **Step 6: Commit** — `chore(reference): register missing classes in manifest` (trailer ADR-0011).

### Task 5: Handoff + push

- [ ] **Step 1:** `sessione-2026-07-16/HANDOFF_ATTIVO.md`: riga lotto (24 classi, oracolo 28/28, paladin_aasimar unica esclusa per Aasimar) + `docs/WORKFLOW.md:55` (13 → 28/28). Questo file di piano entra nel commit docs.
- [ ] **Step 2:** Commit `docs(planning): add missing classes import plan and handoff` + push. Segnalazione a pathmaster-dd per la riesecuzione del tre-vie sulle 15 build sbloccate (caveat normalizzazione nomi corpus: `arcanist`/`tiefling` minuscoli, "Half Orc"/"Halfelf").

---

## Note operative

- Fetch solo seriale, delay 2s (policy cortesia aonprd); test MAI su rete, solo fixture inline.
- Builder idempotente: due run consecutivi stesso file; dry-run obbligatorio prima di `--write`.
- Commit convenzionali: `type(scope): subject` ≤72 char, minuscolo, niente punto; `git commit -F` con trailer ADR-0011 (`Coding-Agent: kimi-code-cli`, `Trace-Id: uuidv7`), MAI `Co-Authored-By:`.
- Punti di attenzione parser: ① extracts→`spells_per_day` semantica dichiarata (decisione a); ② caster senza colonna "0": cantrips non quotate — stesso trattamento Sorcerer ("assenza = nessun vincolo di slot", nota `planning/2026-07-19-spells-builder.md`); ③ Brawler `Unarmed Damage` → `extra_progression` automatico; ④ riga-gruppo "Extracts/Spells Per Day" sopra l'header: già gestita da `_header_index`; ⑤ fonte per classe onesta via `CLASS_SOURCES`.
- Rischio residuo dichiarato: le forme tabella derivano da GET live del 2026-07-19 (read-only); al Task 1 vanno ri-verificate sul dump in cache prima di scrivere le fixture.
- Le 15 build sbloccate attese: alchemist-goblin-vivisectionist, alchemist_goblin_bombardier, arcanist_tiefling_hexcrafter_blood_arcanist, bloodrager-shabti-steelblood-metamagic-rager, brawler_grippli_mutagenic_mauler_strangler, cavalier_strix_strategist_honor_guard, gunslinger_strix_gun_tank, gunslinger_tengu_pistolero_bolt_ace, hunter_kasatha_packmaster, inquisitor_vishkanya_tactical_leader_preacher, investigator_catfolk_empiricist_psychic_detective, kineticist_strix_kinetic_knight_overwhelming_soul, kineticist_suli_kinetic_knight_overwhelming_soul, medium_oread_spirit_dancer_reanimated_medium, witch_sylph_gravewalker_hedge_witch.
