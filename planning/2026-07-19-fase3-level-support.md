# Fase 3 — Level Support (1-20) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Estendere il builder deterministico (Fase 2 + feat effects) da livello 1 a livelli 1-20: HP per livello, BAB/TS/feature da progressione, skill multi-livello, talenti per livello, incantesimi al giorno (caster), WBL.

**Architecture:** `CharacterDraft.level: int = 1` (default: piena retrocompatibilita' con i 47 test lv1 esistenti) + `hp_method: str = "average"` ("average" PFS: `hd//2 + 1` per livello dopo il 1° | "max"). L'engine legge `mech["progression"][level-1]` e moltiplica i budget per livello. Equipment: lv1 resta rigoroso (errori), lv>1 best-effort (warning: oggetti ignoti/oltre WBL, perche' gli item magici non sono nel catalogo mundano). Nessuna dipendenza nuova.

**Tech Stack:** Python 3 stdlib, dati esistenti (`classes.json` progressione 20 livelli, spells_per_day, extra_progression). Test pytest su `tests/test_pc_engine.py` (47 passed attuali) + `tests/test_pc_api.py` (4).

**Decisioni chiave:**
- `favored_class_bonus` resta "hp" | "skill" e si moltiplica per livello (RAW: +1 hp o +1 skill per livello nella favored class).
- Feat count RAW: base `1 + level//2` (livelli 1,3,5,...); Human +1; Fighter bonus `1 + level//2` (livelli 1,2,4,6,...); Monk bonus = count di soglie `(1,2,6,10,14,18) <= level`.
- Prereq evaluator: il ramo class level usa `needed <= ctx["class_level"]` (= draft.level in single-class).
- WBL tabella CRB come costante in `src/pc/catalogs.py` (19 valori OGC, commento fonte); lv1 usa starting_wealth come oggi (errore), lv>1 warning se spesa > WBL.
- Oggetti sconosciuti: lv1 errore (come oggi), lv>1 warning (item magici attesi).

---

### Task 1: `models.level` + core progressione (hp/saves/bab/special/spells)

**Files:**
- Modify: `tooling/Master-DD-Taverna/src/pc/models.py`
- Modify: `tooling/Master-DD-Taverna/src/pc/engine.py`
- Modify: `tooling/Master-DD-Taverna/tests/test_pc_engine.py`

- [ ] **Step 1: Write the failing tests**

```python
def _draft_lv(level, **kw):
    base = {"name": "T", "method": "point-buy", "campaign_type": "Standard Fantasy",
            "abilities": {"str": 13, "dex": 12, "con": 13, "int": 10, "wis": 14, "cha": 12},
            "race": "Human", "race_bonus_ability": "str", "class": "Fighter",
            "level": level}
    base.update(kw)
    return CharacterDraft.from_dict(base)


def test_level_validation():
    sheet = build_character(_draft_lv(0))
    assert any("level" in e.lower() for e in sheet["errors"])
    sheet = build_character(_draft_lv(21))
    assert any("level" in e.lower() for e in sheet["errors"])


def test_fighter_lv5_average_hp_and_progression():
    sheet = build_character(_draft_lv(5, skills={"Climb": 5, "Perception": 1}))
    assert sheet["errors"] == [], sheet["errors"]
    # d10 max + 4 livelli x 6 (media d10) + Con 1 x5 + favored hp x5 = 10+24+5+5 = 44
    assert sheet["hp"] == 44
    assert sheet["bab"] == 5
    assert sheet["saves"]["fort"] == 4 + 1  # fort lv5 Fighter = +4, +Con 1
    assert "weapon training" in " ".join(sheet["special"]).lower()


def test_wizard_lv10_spells_and_max_hp():
    sheet = build_character(_draft_lv(10, hp_method="max",
                                      **{"class": "Wizard", "race": "Elf"},
                                      skills={"Spellcraft": 10}))
    assert sheet["errors"] == [], sheet["errors"]
    # d6 max x10 + Con 1 x10 = 70 (Elf: con 13-2=11 -> mod 0!) ricalcola:
    # Elf: dex+2, int+2, con-2 -> con 11 -> mod 0; favored hp +10 -> 60+0+10 = 70
    assert sheet["hp"] == 70
    assert sheet["bab"] == 5  # Wizard lv10: +5
    assert sheet["spells_per_day"]
    # favored_class_bonus="hp" di default: +10 gia' incluso sopra
```

NOTA: Elf con-2 → con 11 mod 0; Wizard favored hp lv10 = +10; 60+0+10 = 70. Verifica le progressioni reali in classes.json per Fighter lv5 (fort 4, special "weapon training") e Wizard lv10 (bab 5) prima di asserire.

- [ ] **Step 2: Run test to verify it fails**

Expected: FAIL (level non gestito / assertion hp).

- [ ] **Step 3: Implement**

`src/pc/models.py`: aggiungere `level: int = 1` e `hp_method: str = "average"` (dopo favored_class_bonus; `from_dict` li accetta gia' via `**data`).

`src/pc/engine.py` (dentro `build_character`, dopo il guard classe):

```python
    if not isinstance(draft.level, int) or not 1 <= draft.level <= 20:
        sheet["errors"].append(f"level: deve essere un intero 1-20 (ricevuto {draft.level!r})")
        return sheet
    if draft.hp_method not in ("average", "max"):
        sheet["errors"].append(f"hp_method non valido: {draft.hp_method}")
        return sheet
```

e sostituire il blocco hp/saves/bab usando il livello:

```python
    lvl = mech["progression"][draft.level - 1]
    hd = int(mech["hd"][1:])
    per_level = hd if draft.hp_method == "max" else hd // 2 + 1
    favored_hp = draft.level if draft.favored_class_bonus == "hp" else 0
    sheet["hp"] = hd + (draft.level - 1) * per_level + mods["con"] * draft.level + favored_hp
    sheet["saves"] = {"fort": lvl["fort"] + mods["con"],
                      "ref": lvl["ref"] + mods["dex"],
                      "will": lvl["will"] + mods["wis"]}
    sheet["bab"] = lvl["bab"]
    sheet["special"] = list(lvl.get("special", []))
    if lvl.get("spells_per_day"):
        sheet["spells_per_day"] = dict(lvl["spells_per_day"])
    if lvl.get("extra_progression"):
        sheet["extra_progression"] = dict(lvl["extra_progression"])
```

(attenzione: il codice attuale usa `lvl1 = mech["progression"][0]` — sostituire le sue occorrenze con `lvl`; i granted feats della classe continuano a leggere `lvl1`/`lvl` allo stesso modo.)

- [ ] **Step 4: Run test + commit**

Run: `cd tooling/Master-DD-Taverna && .venv/Scripts/python -m pytest tests/test_pc_engine.py -q`
Expected: 50 passed (47 + 3 nuovi, lv1 invariato).

```bash
cd tooling/Master-DD-Taverna
git add src/pc/models.py src/pc/engine.py tests/test_pc_engine.py
git commit -m "feat(pc): support levels 1-20 for hp saves bab and spells"
```

---

### Task 2: Skill e talenti multi-livello

**Files:**
- Modify: `tooling/Master-DD-Taverna/src/pc/engine.py`
- Modify: `tooling/Master-DD-Taverna/tests/test_pc_engine.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_skills_multi_level_budget_and_cap():
    # Fighter lv5: (2 + 0) x5 + 1x5 Human + 5 favored? no: favored hp -> 10+5 = 15 ranks
    sheet = build_character(_draft_lv(5, skills={"Climb": 5, "Perception": 5, "Survival": 5}))
    assert sheet["errors"] == [], sheet["errors"]
    assert sheet["skills"]["Climb"]["total"] == 5 + 2 + 3  # 5 rank + str2 + class3
    sheet2 = build_character(_draft_lv(5, skills={"Climb": 6}))
    assert any("Climb" in e for e in sheet2["errors"])  # cap = level (5)


def test_feats_count_by_level():
    # Human Fighter lv5: 1 + 5//2 + 1 + (1 + 5//2) = 1+2+1+3 = 7 consentiti
    feats = ["Power Attack", "Dodge", "Cleave", "Point-Blank Shot", "Weapon Focus",
             "Improved Initiative", "Toughness"]
    sheet = build_character(_draft_lv(5, race_bonus_ability="dex",
                                      skills={"Climb": 5, "Perception": 5, "Survival": 5},
                                      feats=feats))
    assert sheet["errors"] == [], sheet["errors"]
    assert len(sheet["feats"]) == 7
    sheet2 = build_character(_draft_lv(5, race_bonus_ability="dex",
                                       skills={"Climb": 5, "Perception": 5, "Survival": 5},
                                       feats=feats + ["Lightning Reflexes"]))
    assert any("feat" in e.lower() for e in sheet2["errors"])


def test_prereq_class_level_threshold():
    # Weapon Specialization richiede fighter level 4th + Weapon Focus: fallisce a lv3, ok a lv4 (con Weapon Focus)
    sheet = build_character(_draft_lv(3, skills={"Climb": 3},
                                      feats=["Weapon Focus", "Weapon Specialization"]))
    assert any("Weapon Specialization" in e for e in sheet["errors"])
    sheet = build_character(_draft_lv(4, skills={"Climb": 4},
                                      feats=["Weapon Focus", "Weapon Specialization"]))
    assert sheet["errors"] == [], sheet["errors"]
```

NOTA: skill budget a lv3 = (2+0)*3+3 = 9 >= 3 ok; a lv4 = 12 ok. Weapon Specialization prereq reali: "fighter level 4th" + "Weapon Focus" (verificare in feats.json e adattare se servono altri requisiti).

- [ ] **Step 2: Run test to verify it fails**

Expected: FAIL.

- [ ] **Step 3: Implement**

In `build_character`, blocco skill:

```python
    per_level_sp = max(mech["skill_points_per_level"] + mods["int"], 1)
    budget = per_level_sp * draft.level
    budget += draft.level if draft.race == "Human" else 0
    budget += draft.level if draft.favored_class_bonus == "skill" else 0
    spent = sum(draft.skills.values())
    if spent > budget:
        errors.append(f"skill ranks: {spent} spesi oltre il budget {budget} (lv{draft.level})")
    # nel loop skill:
        if not 0 < ranks <= draft.level:
            errors.append(f"{name}: ranks {ranks} fuori range (1..{draft.level})")
```

In `validate_feats`: conteggio consentiti per livello:

```python
def _class_bonus_feats(class_name, level):
    if class_name == "Fighter":
        return 1 + level // 2
    if class_name == "Monk":
        return sum(1 for x in (1, 2, 6, 10, 14, 18) if level >= x)
    return 0

# in validate_feats:
    allowed = 1 + draft.level // 2 + (1 if draft.race == "Human" else 0) + _class_bonus_feats(draft.class_, draft.level)
```

e in `_check_prereq`, ramo class level: `ctx["class_level"] = draft.level` (da validate_feats) e `return needed <= ctx["class_level"], ...`.

- [ ] **Step 4: Run test + commit**

Run: `cd tooling/Master-DD-Taverna && .venv/Scripts/python -m pytest tests/test_pc_engine.py -q`
Expected: 53 passed.

```bash
cd tooling/Master-DD-Taverna
git add src/pc/engine.py tests/test_pc_engine.py
git commit -m "feat(pc): scale skill and feat counts by level"
```

---

### Task 3: Equipment lv>1 best-effort + WBL + docs

**Files:**
- Modify: `tooling/Master-DD-Taverna/src/pc/catalogs.py` (WBL)
- Modify: `tooling/Master-DD-Taverna/src/pc/engine.py`
- Modify: `tooling/Master-DD-Taverna/tests/test_pc_engine.py`
- Modify: `tooling/Master-DD-Taverna/README.md`
- Modify: `tooling/Master-DD-Taverna/src/app.py` (docstring endpoint)

- [ ] **Step 1: Write the failing tests**

```python
def test_wbl_warning_and_unknown_magic_item():
    # lv5 WBL = 10500 gp; item magico sconosciuto -> warning (non errore)
    sheet = build_character(_draft_lv(5, skills={"Climb": 5},
                                      equipment=["Longsword", "Chain shirt", "+1 Flaming Longsword"]))
    assert sheet["errors"] == []
    assert any("+1 Flaming Longsword" in w for w in sheet["warnings"])
    # oltre WBL -> warning
    sheet2 = build_character(_draft_lv(2, skills={"Climb": 1},  # WBL 1000
                                       equipment=["Chain shirt", "Full plate", "Longsword", "Shortbow"]))
    assert any("wbl" in w.lower() or "wealth" in w.lower() for w in sheet2["warnings"])


def test_wbl_table():
    from src.pc.catalogs import wealth_by_level
    assert wealth_by_level(1) is None
    assert wealth_by_level(2) == 1000
    assert wealth_by_level(20) == 880000
```

- [ ] **Step 2: Run test to verify it fails**

Expected: FAIL.

- [ ] **Step 3: Implement**

In `src/pc/catalogs.py`:

```python
# Character Wealth by Level (PFRPG Core, tabella OGC).
WBL_BY_LEVEL = {2: 1000, 3: 3000, 4: 6000, 5: 10500, 6: 16000, 7: 23500,
                8: 33000, 9: 46000, 10: 62000, 11: 82000, 12: 108000, 13: 140000,
                14: 185000, 15: 240000, 16: 315000, 17: 410000, 18: 530000,
                19: 685000, 20: 880000}


def wealth_by_level(level):
    """Wealth-by-level per livelli > 1; None per lv1 (usa starting_wealth)."""
    return None if level == 1 else WBL_BY_LEVEL.get(level)
```

In `apply_equipment`, comportamento per livello:

```python
    level = getattr(draft, "level", 1)
    if level == 1:
        wealth = <starting_wealth come oggi>
        strict = True
    else:
        wealth = catalogs.wealth_by_level(level) or 0
        strict = False
    # item sconosciuto: strict -> error (come oggi); else -> warnings.append(f"{name}: non in catalogo (valutato a mano)")
    # spesa > wealth: strict -> error; else -> warnings.append(f"wealth: spesi {spent} gp oltre WBL {wealth} gp (warning)")
```

**Docs**: README riga endpoint: "livelli 1-20 (lv>1: equipment best-effort con warning, WBL)"; docstring endpoint in `src/app.py`: stessa nota + "limitazione: effetti talenti solo per i supportati (feat_effects.py)".

- [ ] **Step 4: Run test + full verify + commit**

Run: `cd tooling/Master-DD-Taverna && .venv/Scripts/python -m pytest tests/test_pc_engine.py -q`
Expected: 55 passed.

Run: `cd tooling/Master-DD-Taverna && .venv/Scripts/python -m pytest tests/ -q`
Expected: nessuna regressione (1 skipped).

```bash
cd tooling/Master-DD-Taverna
git add src/pc/catalogs.py src/pc/engine.py tests/test_pc_engine.py README.md src/app.py
git commit -m "feat(pc): add wealth by level and lenient equipment above level 1"
```

---

### Task 4: Verifica completa + handoff (controller)

- [ ] `cd C:/dev/pathfinder && python launch.py test` → TUTTE LE VERIFICHE OK
- [ ] Smoke API: POST /pc/build lv5 Fighter e lv10 Wizard → numeri corretti
- [ ] Rigenera `reports/data_quality_report.json`, commit piano in `planning/`, aggiorna `HANDOFF_ATTIVO.md`, push

---

## Note operative

- **Retrocompatibilita'**: `level: 1` di default — i 47 test lv1 esistenti devono passare INVARIATI (eccetto eventuali messaggi arricchiti con "(lv1)").
- **Favored per livello**: hp o skill x level, sommati ai rispettivi totali (gia' nel design, verificarlo nei test).
- **extra_progression**: passthrough per classi con colonne extra (Monk); consumer futuri decideranno l'uso.
- **Fuori scope**: multiclasse, archetipi, incantesimi conosciuti/preparati (solo slots), XP, HP rolled (solo average/max).
- Commit convenzionali (hook attivo), MAI `Co-Authored-By:`, nessun test skipped nuovo.
