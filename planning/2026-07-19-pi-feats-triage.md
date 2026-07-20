# Triage PI Feats Preesistenti Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Chiudere il debito PI dei feats (roadmap 5 di `docs/research/2026-07-19-process-optimization.md`, esperienza `docs/IMPORT_PLAYBOOK.md` §6): triage delle entry PI preesistenti in `feats.json` con **decisione policy documentata** e codifica del gate perché non si ripeta.

**Stato misurato (scansione 2026-07-19, word-boundary, lista estesa ~55 termini):** 41 entry con match in `data/reference/ogl/feats.json` (2837 entry). Categorie:
- **A — PI nel NOME** (24): Aldori×12 (Artistry, Dueling Disciple, Dueling Mastery, Style, Style Aegis, Style Conquest, Duelist Of The Roaring Falls, Duelist Of The Shrouded Lake, Falling Water Gambit, Garen's Discipline, Redistributed Might, Sirian's Masterstroke), Hellknight×5 (Aegis, Obedience, Obsession, Ominous Mien, Signifer Armor Training), Andoren Falconry, Taldan Duelist, Thuvian Grenadier, Rahadoumi Exorcist + Eye of the Arclord (Nex in nome? verificare: match in description — ricategorizzare in triage) + nomi mangiati dalla sanitize storica (Noble Scion a fading empire = "Noble Scion of Taldor" mangiato).
- **B — PI deità nei prerequisiti** (10): Rovagug×4 (Breaker Of Barriers, Merciless Rush, Oath Of The Unbound, Squash Flat), Lamashtu×3 (Destroy Identity, Fearsome Finish, Nightmare Scars), Gozreh×3 (Channel Endurance, Riptide Attack, Wave Master).
- **C — PI solo in description, sanificabile** (~8): Inner Sea×4 (Cypher Magic, Harrowed Summoning, Quah Bond, Scholar, Wyvaran Spellcasting), Taldan/Chelish/Chelaxian in testo (Friendly Rivalry, Scion Of The Lost Empire, Ruthless Opportunist, Noble Scion a fading empire).

## Decisione policy (controller, da documentare in IMPORT_PLAYBOOK §6)

1. **PI nell'identità (nome) o prerequisito deità-specifico → `pi_local_only/feats_local.json`** (nuovo catalogo `local_only`, pattern di `monsters_local.json`): restano disponibili in locale per le build, non redistribuiti nel catalogo OGL. La sanitize del NOME è vietata (produce mostri tipo "Noble Scion a fading empire").
2. **PI solo in prosa description → sanitize in place**, ma con tool corretto: `tools/sanitize_reference_pi.py` oggi sostituisce sottostringhe naive e ha già corrotto testo ("Varisian"→"a frontier landn", artifacts "ISM…ISWG" puliti in `b9f9d63`). Prima dell'uso va reso **word-boundary** e coperto da test.
3. **Entry mangiate dalla sanitize storica → ripristino da fonte** (cache AoN / git history) poi ricategorizzazione A/C.
4. **Gate**: la lista estesa (~55 termini, word-boundary) entra in `tools/legal_filter.py` (o in un check dedicato agganciato agli invarianti) così i futuri import falliscono fail-closed su queste classi di PI — il gate attuale le lasciava passare a 0.
5. **Prerequisiti dangling**: spostare entry in feats_local può lasciare riferimenti pendenti in altri feats (pattern noto da `b9f9d63`): il triage li elenca; gestione = strip del riferimento con nota nel report (come da prassi) oppure spostamento a cascata se il feat referenziante è a sua volta Golarion-specifico.

---

### Task 1: Triage tool + report

**Files:**
- Create: `tools/triage_pi_feats.py` (scan word-boundary, categorizza A/B/C/D, check dangling refs, output report)
- Create: `reports/pi_feats_triage.md` (report non committato? NO: committato — è l'evidenza della decisione policy)

- [ ] **Step 1:** Implementa lo scan: lista termini estesa (dai ~55 usati per la misura 2026-07-19: sanitize_reference_pi + demonimi/organizzazioni Aldori, Hellknight, Chelish, Taldan, Andoren, Rahadoumi, Thuvian, Inner Sea, Nex, Geb, Nidal + deità maggiori/demon lord), word-boundary, campi name/description/prerequisites. Categorie: A (match in name), B (match deità in prerequisites), C (match solo in description), D (artifact da sanitize storica: pattern "a frontier landn", "ISM…ISWG", nomi con "a fading empire"/"a great city" etc.).
- [ ] **Step 2:** Dangling refs: per ogni entry categoria A/B, cerca il nome nelle prerequisites/references delle altre entry ( feats.json ) e riporta i riferimenti che lo spostamento renderebbe pendenti.
- [ ] **Step 3:** Scrivi `reports/pi_feats_triage.md`: tabella per entry con categoria, match, campi, dangling refs, azione proposta (da policy). Conteggio finale per categoria.
- [ ] **Step 4: Commit** `docs(reference): add pi feats triage report` (trailer ADR-0011).

### Task 2: Applicazione policy

**Files:**
- Create: `data/reference/pi_local_only/feats_local.json` (entry A+B+D, formato catalogo standard, `_source` dichiarato)
- Modify: `data/reference/ogl/feats.json` (rimozione entry A+B+D, sanitize C)
- Modify: `tools/sanitize_reference_pi.py` (word-boundary + nuovi termini mancanti: Nex, Geb, Nidal, Rahadoum/Rahadoumi, Thuvia/Thuvian, Taldan, Chelish/Chelaxian, Andoren, Aldori SOLO in description mai in name, Gozreh, Rovagug, Lamashtu SOLO description)
- Modify: `data/reference/manifest.json` (registrazione feats_local local_only, count feats aggiornato, notes, last_verified)
- Test: `tests/test_sanitize_pi.py` (nuovo: word-boundary, nessuna corruzione "Varisian", replacement in description, name MAI toccato)

- [ ] **Step 1: TDD sanitize** — test rossi: (a) "Varisian Tattoo" NON viene corrotto; (b) "Inner Sea" in description → "the inner sea region"; (c) name contenente "Taldor" NON modificato; (d) possessivi. Poi fix del tool.
- [ ] **Step 2: Ripristino D** — nomi/campi mangiati ripristinati da cache AoN (`FeatDisplay.aspx?ItemName=Noble%20Scion%20of%20Taldor` se in cache, altrimenti git history pre-sanitize) poi ricategorizzati.
- [ ] **Step 3: Spostamento A+B in feats_local.json** — entry complete con fonte; rimozione da feats.json; strip riferimenti dangling con lista nel report (aggiornamento di `reports/pi_feats_triage.md` o secondo report applicazione).
- [ ] **Step 4: Sanitize C in place** — run del tool corretto solo sui campi description delle entry categoria C (scope chirurgico, non tutto il file).
- [ ] **Step 5: Manifest** — feats_local registrato local_only (indicizzato dal RAG solo con --include-local, come monsters_local); counts aggiornati.
- [ ] **Step 6: Verifica** — `pytest tests/test_sanitize_pi.py tests/test_reference_catalogs.py -q`; legal_filter 0; validate_schemas 0; scansione word-boundary finale su feats.json → 0 match residui (o residui documentati).
- [ ] **Step 7: Commit** `fix(reference): move pi identity feats to local catalog and sanitize descriptions` (trailer ADR-0011).

### Task 3: Gate esteso

**Files:**
- Modify: `tools/legal_filter.py` (lista termini estesa word-boundary) o `tests/test_reference_catalogs.py` (invariante PI word-boundary su feats.json)
- Test: aggiornamento test esistenti del filtro

- [ ] **Step 1:** Estendi il gate con la lista ~55 termini word-boundary (stessa fonte della lista di triage — unificare, niente doppie liste: la lista vive in un punto solo, es. `tools/legal_filter.py`, e il triage la importa).
- [ ] **Step 2:** Test: feats.json OGL pulita passa; entry con "worship Rovagug" fallisce; "your next turn" NON fallisce (regressione "Nex"/"next").
- [ ] **Step 3:** Run gate: legal_filter 0 violazioni sul catalogo pulito.
- [ ] **Step 4: Commit** `feat(tools): extend pi filter with word-boundary golarion terms` (trailer ADR-0011).

### Task 4: Gate finali + docs + push

- [ ] **Step 1:** Suite completa (≥264 passed, esattamente 1 skipped); legal_filter 0; validate_schemas 0; reindice incrementale (`--include-local`, feats_local entra come monsters_local).
- [ ] **Step 2:** `python launch.py test` dalla root → TUTTE LE VERIFICHE OK; rigenera `reports/data_quality_report.json`.
- [ ] **Step 3:** Docs: `docs/IMPORT_PLAYBOOK.md` §6 — la decisione policy scritta (categorie A/B/C/D, destinazione per categoria, divieto sanitize nomi, gate word-boundary); `sessione-2026-07-16/HANDOFF_ATTIVO.md`.
- [ ] **Step 4: Commit** `docs(reference): document pi feats policy decision` (piano incluso) + push.

---

## Note operative

- La scansione misurata del 2026-07-19 (41 entry) è riprodotta dal tool di Task 1: se il conteggio diverge, il tool ha ragione (ri-derivare la lista e segnalare lo scarto nel report).
- `feats_local.json` segue il contratto di `monsters_local.json`: `local_only: true` in manifest, git-committato? NO — `pi_local_only/` è gitignored come monsters_local (verificare `.gitignore`: monsters_local.json NON è committato). feats_local.json resta locale, generato dal tool di Task 2 con istruzioni di rigenerazione nel report.
- Ordine categorie conflittuali: D (ripristino) prima di A/C; una entry con PI sia in name sia in description va in A (vince la categoria più severa).
- Commit convenzionali + trailer ADR-0011 (`Coding-Agent: kimi-code-cli`, `Trace-Id: uuidv7`), MAI `Co-Authored-By:`.
