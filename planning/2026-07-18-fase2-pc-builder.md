# Fase 2 — Deterministic PC Builder (lv1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Un motore deterministico che costruisce un personaggio PF1e di livello 1 dai cataloghi OGL del Lotto 4: valida le scelte (point-buy, razza, classe, skill, talenti, tratti, equip) e calcola i valori finali (caratteristiche, PF, TS, BAB, CA, attacchi, skill, ricchezza) senza alcun LLM.

**Architecture:** Nuovo package `src/pc/` (`catalogs.py` loaders dai JSON del lotto, `models.py` draft/sheet dataclass, `engine.py` computazione) + endpoint `POST /pc/build` in `src/app.py` (specchio del pattern auth di `POST /build/stub`). Input = JSON "draft" con le scelte; output = JSON "sheet" con valori calcolati + `errors` (bloccanti, HTTP 422) e `warnings` (non bloccanti). Solo livello 1 (progression[0]); nessuna dipendenza nuova.

**Tech Stack:** Python 3 stdlib + FastAPI/TestClient esistenti. Cataloghi reali: `data/reference/ogl/{abilities,races,classes,skills,traits,equipment_mundane,feats}.json` (campi `mechanics` del Lotto 4). Test pytest, nessuno skipped (gate verify: esattamente 1 skipped globale).

**Input draft (contratto):**
```json
{
  "name": "Seelah",
  "method": "point-buy",
  "campaign_type": "Standard Fantasy",
  "abilities": {"str": 14, "dex": 12, "con": 13, "int": 10, "wis": 15, "cha": 11},
  "race": "Human",
  "race_bonus_ability": "str",
  "class": "Fighter",
  "favored_class_bonus": "hp",
  "skills": {"Climb": 1, "Perception": 1, "Survival": 1, "Intimidate": 1},
  "feats": ["Power Attack", "Dodge", "Cleave"],
  "traits": ["Reactionary", "Indomitable Faith"],
  "equipment": ["Longsword", "Chain shirt", "Backpack (common)"]
}
```
`race_bonus_ability` e' obbligatorio solo se la razza ha `ability_mods == {"any": N}`. `favored_class_bonus`: "hp" | "skill".

---

### Task 1: `src/pc/catalogs.py` — loaders cataloghi OGL

**Files:**
- Create: `tooling/Master-DD-Taverna/src/pc/__init__.py` (vuoto)
- Create: `tooling/Master-DD-Taverna/src/pc/catalogs.py`
- Test: `tooling/Master-DD-Taverna/tests/test_pc_catalogs.py`

- [ ] **Step 1: Write the failing test**

```python
"""Test per src/pc/catalogs.py (dati reali su disco, nessuna rete)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.pc.catalogs import (ability_cost, campaign_budget, find_equipment,
                             find_feat, find_trait, get_class, get_race,
                             get_skill)


def test_ability_tables():
    assert ability_cost(7) == -4
    assert ability_cost(14) == 5
    assert ability_cost(18) == 17
    assert campaign_budget("Standard Fantasy") == 15
    assert campaign_budget("Epic Fantasy") == 25


def test_getters():
    human = get_race("Human")
    assert human["mechanics"]["ability_mods"] == {"any": 2}
    fighter = get_class("Fighter")
    assert fighter["mechanics"]["hd"] == "d10"
    assert len(fighter["mechanics"]["progression"]) == 20
    assert get_skill("Perception")["mechanics"]["key_ability"] == "wis"
    assert find_feat("Power Attack") is not None
    assert find_feat("Non Esiste") is None
    assert find_equipment("Longsword")["mechanics"]["cost"] == "15 gp"
    assert find_trait("Reactionary")["mechanics"]["category"] == "Basic (Combat)"
    print("OK: catalogs loaders")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd tooling/Master-DD-Taverna && .venv/Scripts/python -m pytest tests/test_pc_catalogs.py -q`
Expected: FAIL `ModuleNotFoundError: No module named 'src.pc'`

- [ ] **Step 3: Implement**

`src/pc/catalogs.py`:

```python
"""Loaders dei cataloghi OGL (Lotto 4) per il builder deterministico."""
import functools
import json
from pathlib import Path

OGL_DIR = Path(__file__).resolve().parents[2] / "data" / "reference" / "ogl"


@functools.lru_cache(maxsize=None)
def load(kind):
    """Carica le entries di un catalogo per kind (abilities, races, ...)."""
    filename = {
        "abilities": "abilities.json", "races": "races.json", "classes": "classes.json",
        "skills": "skills.json", "traits": "traits.json",
        "equipment": "equipment_mundane.json", "feats": "feats.json",
    }[kind]
    with open(OGL_DIR / filename, encoding="utf-8") as f:
        return json.load(f)["entries"]


def _by_name(kind):
    return {e["name"]: e for e in load(kind)}


def ability_cost(score):
    """Costo point-buy di un punteggio (7..18)."""
    for e in load("abilities"):
        m = e.get("mechanics", {})
        if m.get("kind") == "ability_cost" and m.get("score") == score:
            return m["cost"]
    raise KeyError(f"costo point-buy non trovato per {score}")


def campaign_budget(name):
    """Budget punti per tipo di campagna (es. 'Standard Fantasy' -> 15)."""
    for e in load("abilities"):
        m = e.get("mechanics", {})
        if m.get("kind") == "campaign_budget" and e["name"].lower() == name.lower():
            return m["points"]
    raise KeyError(f"budget campagna non trovato: {name}")


def get_race(name):
    return _by_name("races").get(name)


def get_class(name):
    return _by_name("classes").get(name)


def get_skill(name):
    return _by_name("skills").get(name)


def find_feat(name):
    return _by_name("feats").get(name)


def find_trait(name):
    return _by_name("traits").get(name)


def find_equipment(name):
    return _by_name("equipment").get(name)
```

- [ ] **Step 4: Run test + commit**

Run: `cd tooling/Master-DD-Taverna && .venv/Scripts/python -m pytest tests/test_pc_catalogs.py -q`
Expected: 2 passed.

```bash
cd tooling/Master-DD-Taverna
git add src/pc/__init__.py src/pc/catalogs.py tests/test_pc_catalogs.py
git commit -m "feat(pc): add OGL catalog loaders for deterministic builder"
```

---

### Task 2: `src/pc/models.py` + step caratteristiche in `engine.py`

**Files:**
- Create: `tooling/Master-DD-Taverna/src/pc/models.py`
- Create: `tooling/Master-DD-Taverna/src/pc/engine.py` (solo step abilities per ora)
- Test: `tooling/Master-DD-Taverna/tests/test_pc_engine.py`

- [ ] **Step 1: Write the failing test**

```python
"""Test per src/pc/engine.py — step caratteristiche."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.pc.engine import apply_abilities
from src.pc.models import CharacterDraft


def _draft(**kw):
    base = {"name": "T", "method": "point-buy", "campaign_type": "Standard Fantasy",
            "abilities": {"str": 14, "dex": 12, "con": 13, "int": 10, "wis": 15, "cha": 11},
            "race": "Human", "class": "Fighter"}
    base.update(kw)
    return CharacterDraft.from_dict(base)


def test_point_buy_over_budget():
    sheet = apply_abilities(_draft())  # costa 18 su budget 15
    assert any("budget" in e.lower() for e in sheet["errors"])
```

ATTENZIONE: il draft d'esempio nel contratto (14/12/13/10/15/11) costa 18 punti su budget 15: i test devono rifletterlo. Usa questi due test REALI:

```python
def test_within_budget_with_racial_bonus():
    # 13(3) 12(2) 13(3) 10(0) 14(5) 12(2) = 15 <= 15
    sheet = apply_abilities(_draft(abilities={"str": 13, "dex": 12, "con": 13,
                                             "int": 10, "wis": 14, "cha": 12},
                                   race_bonus_ability="str"))
    assert sheet["errors"] == []
    assert sheet["abilities"]["str"] == 15  # 13 + 2 any Human


def test_over_budget_and_missing_any_choice():
    sheet = apply_abilities(_draft())  # costa 18 su 15
    assert any("budget" in e.lower() for e in sheet["errors"])
    sheet2 = apply_abilities(_draft(abilities={"str": 13, "dex": 12, "con": 13,
                                              "int": 10, "wis": 14, "cha": 12}))
    assert any("race_bonus_ability" in e for e in sheet2["errors"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd tooling/Master-DD-Taverna && .venv/Scripts/python -m pytest tests/test_pc_engine.py -q`
Expected: FAIL `ModuleNotFoundError: No module named 'src.pc.engine'`

- [ ] **Step 3: Implement models + abilities step**

`src/pc/models.py`:

```python
"""Modelli input/output del builder deterministico."""
from dataclasses import dataclass, field


@dataclass
class CharacterDraft:
    name: str
    method: str
    campaign_type: str
    abilities: dict
    race: str
    class_: str = field(metadata={"alias": "class"})
    race_bonus_ability: str | None = None
    favored_class_bonus: str = "hp"
    skills: dict = field(default_factory=dict)
    feats: list = field(default_factory=list)
    traits: list = field(default_factory=list)
    equipment: list = field(default_factory=list)

    @classmethod
    def from_dict(cls, data):
        data = dict(data)
        if "class" in data:
            data["class_"] = data.pop("class")
        return cls(**data)
```

`src/pc/engine.py`:

```python
"""Motore deterministico di creazione PG lv1 (nessun LLM)."""
from src.pc import catalogs

ABILS = ("str", "dex", "con", "int", "wis", "cha")


def ability_mod(score):
    return (score - 10) // 2


def apply_abilities(draft):
    """Valida point-buy e applica i modificatori razziali.
    Ritorna dict con 'abilities' finali e 'errors'."""
    errors = []
    if draft.method != "point-buy":
        errors.append(f"metodo non supportato: {draft.method} (solo point-buy)")
        return {"abilities": {}, "errors": errors}
    budget = catalogs.campaign_budget(draft.campaign_type)
    spent = sum(catalogs.ability_cost(v) for v in draft.abilities.values())
    if spent > budget:
        errors.append(f"point-buy: {spent} punti spesi oltre il budget {budget} ({draft.campaign_type})")
    race = catalogs.get_race(draft.race)
    if race is None:
        errors.append(f"razza sconosciuta: {draft.race}")
        return {"abilities": {}, "errors": errors}
    mods = race["mechanics"].get("ability_mods", {})
    final = dict(draft.abilities)
    if mods == {"any": 2} or mods.get("any"):
        if not draft.race_bonus_ability:
            errors.append(f"race_bonus_ability obbligatorio per {draft.race}")
        elif draft.race_bonus_ability not in ABILS:
            errors.append(f"race_bonus_ability non valida: {draft.race_bonus_ability}")
        else:
            final[draft.race_bonus_ability] += mods["any"]
    for ab, bonus in mods.items():
        if ab != "any":
            final[ab] = final.get(ab, 10) + bonus
    return {"abilities": final, "errors": errors}
```

- [ ] **Step 4: Run test + commit**

Run: `cd tooling/Master-DD-Taverna && .venv/Scripts/python -m pytest tests/test_pc_engine.py -q`
Expected: 2 passed (quelli REALI del blocco ATTENZIONE; il primo blocco `test_point_buy_valid_and_racial_any` con `assert False` e' una trappola da NON committare: scrivi direttamente solo i due test reali).

```bash
cd tooling/Master-DD-Taverna
git add src/pc/models.py src/pc/engine.py tests/test_pc_engine.py
git commit -m "feat(pc): validate point-buy abilities with racial mods"
```

---

### Task 3: Step classe + skill in `engine.py`

**Files:**
- Modify: `tooling/Master-DD-Taverna/src/pc/engine.py`
- Modify: `tooling/Master-DD-Taverna/tests/test_pc_engine.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_fighter_lv1_combat_basics():
    sheet = build_character(_draft(race_bonus_ability="str", skills={"Climb": 1, "Perception": 1}))
    assert sheet["errors"] == []
    assert sheet["hp"] == 12  # d10 max + Con mod 1 (13) + favored hp 1
    assert sheet["saves"] == {"fort": 3, "ref": 1, "will": 2}  # base 2/0/0 + Con1/Dex1/Wis2
    assert sheet["bab"] == 1
    assert sheet["initiative"] == 1  # Dex 12 -> +1


def test_skill_points_and_totals():
    # Fighter 2 + Int 0 + Human 1 = 3 ranks max; 4 ranks -> errore
    sheet = build_character(_draft(race_bonus_ability="str",
                                   skills={"Climb": 1, "Perception": 1, "Survival": 1, "Intimidate": 1}))
    assert any("skill" in e.lower() for e in sheet["errors"])
    # 3 ranks ok: Climb di classe (+3), Perception NON di classe Fighter
    sheet = build_character(_draft(race_bonus_ability="str",
                                   skills={"Climb": 1, "Perception": 1, "Survival": 1}))
    assert sheet["errors"] == []
    assert sheet["skills"]["Climb"]["total"] == 1 + 2 + 3  # rank1 + Str mod 2 (15) + class 3
    assert sheet["skills"]["Perception"]["total"] == 1 + 2  # rank1 + Wis mod 2 (no class bonus)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd tooling/Master-DD-Taverna && .venv/Scripts/python -m pytest tests/test_pc_engine.py -q`
Expected: FAIL `NameError: build_character` (o ImportError).

- [ ] **Step 3: Implement class application + skills**

Aggiungere a `src/pc/engine.py`:

```python
def build_character(draft):
    """Costruisce la scheda lv1 completa (per ora: abilities, classe, skill).
    Ritorna dict con errors (bloccanti) e warnings."""
    abilities = apply_abilities(draft)
    errors = list(abilities["errors"])
    warnings = []
    final = abilities["abilities"]
    mods = {ab: ability_mod(sc) for ab, sc in final.items()} if final else {}
    cls = catalogs.get_class(draft.class_)
    sheet = {"name": draft.name, "race": draft.race, "class": draft.class_,
             "abilities": final, "errors": errors, "warnings": warnings}
    if errors:
        return sheet
    mech = cls["mechanics"]
    lvl1 = mech["progression"][0]
    favored_hp = 1 if draft.favored_class_bonus == "hp" else 0
    sheet["hp"] = int(mech["hd"][1:]) + mods["con"] + favored_hp
    sheet["saves"] = {"fort": lvl1["fort"] + mods["con"],
                      "ref": lvl1["ref"] + mods["dex"],
                      "will": lvl1["will"] + mods["wis"]}
    sheet["bab"] = lvl1["bab"]
    sheet["initiative"] = mods["dex"]
    # skill
    race = catalogs.get_race(draft.race)
    budget = mech["skill_points_per_level"] + mods["int"] + (1 if draft.race == "Human" else 0)
    budget += 1 if draft.favored_class_bonus == "skill" else 0
    spent = sum(draft.skills.values())
    if spent > budget:
        errors.append(f"skill ranks: {spent} spesi oltre il budget {budget}")
    class_skills = set(mech.get("class_skills", []))
    out = {}
    for name, ranks in draft.skills.items():
        sk = catalogs.get_skill(name)
        if sk is None:
            errors.append(f"skill sconosciuta: {name}")
            continue
        if ranks != 1:
            errors.append(f"{name}: al lv1 ogni skill puo' avere al piu' 1 rank")
        key = sk["mechanics"]["key_ability"]
        class_bonus = 3 if name in class_skills else 0
        if sk["mechanics"].get("trained_only") and name not in class_skills and ranks > 0:
            warnings.append(f"{name}: trained only e non di classe per {draft.class_}")
        out[name] = {"ranks": ranks, "ability": key,
                     "total": ranks + mods[key] + class_bonus, "class_skill": name in class_skills}
    sheet["skills"] = out
    return sheet
```

- [ ] **Step 4: Run test + commit**

Run: `cd tooling/Master-DD-Taverna && .venv/Scripts/python -m pytest tests/test_pc_engine.py -q`
Expected: 4 passed.

```bash
cd tooling/Master-DD-Taverna
git add src/pc/engine.py tests/test_pc_engine.py
git commit -m "feat(pc): compute class basics and skill totals at level 1"
```

---

### Task 4: Validatore prerequisiti talenti

**Files:**
- Modify: `tooling/Master-DD-Taverna/src/pc/engine.py`
- Modify: `tooling/Master-DD-Taverna/tests/test_pc_engine.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_feat_count_and_prereqs():
    # 3 feat per Human Fighter (1 base + 1 human + 1 fighter): ok con Str 15 (Power Attack richiede Str 13)
    sheet = build_character(_draft(race_bonus_ability="str", skills={"Climb": 1, "Perception": 1, "Survival": 1},
                                   feats=["Power Attack", "Dodge", "Cleave"]))
    assert sheet["errors"] == [], sheet["errors"]
    # Cleave richiede Power Attack (presente) e Str 13 (ok) e BAB +1 (ok)


def test_feat_prereq_failures():
    # Str 12 (<13): Power Attack fallisce; e 4 feat su 3 consentiti
    d = _draft(abilities={"str": 12, "dex": 13, "con": 13, "int": 10, "wis": 14, "cha": 12},
               race_bonus_ability="dex", skills={"Climb": 1, "Perception": 1, "Survival": 1},
               feats=["Power Attack", "Dodge", "Cleave", "Weapon Finesse"])
    sheet = build_character(d)
    assert any("Power Attack" in e and "Str" in e for e in sheet["errors"])
    assert any("feat" in e.lower() and "3" in e for e in sheet["errors"])


def test_unverifiable_prereq_is_warning():
    # Combat Expertise richiede Int 13: draft con Int 14 passa; una forma sconosciuta va in warning
    sheet = build_character(_draft(race_bonus_ability="str", skills={"Climb": 1, "Perception": 1, "Survival": 1},
                                   feats=["Combat Expertise"]))
    assert sheet["errors"] == []
```

- [ ] **Step 2: Run test to verify it fails**

Expected: FAIL (feat validation non implementata).

- [ ] **Step 3: Implement feat validation**

Aggiungere a `src/pc/engine.py`:

```python
FEAT_BONUS_CLASSES = {"Fighter"}


def _check_prereq(prereq, ctx):
    """Valuta un prerequisito testuale. Ritorna (ok, nota)."""
    import re
    text = prereq.rstrip(".")
    m = re.match(r"^(Str|Dex|Con|Int|Wis|Cha)\w*\s+(\d+)$", text, re.I)
    if m:
        ab = m.group(1)[:3].lower()
        need = int(m.group(2))
        return ctx["abilities"][ab] >= need, f"richiede {m.group(1)} {need}"
    m = re.match(r"^base attack bonus \+(\d+)$", text, re.I)
    if m:
        return ctx["bab"] >= int(m.group(1)), f"richiede BAB +{m.group(1)}"
    if catalogs.find_feat(text) is not None:
        return text in ctx["feats"], f"richiede il talento {text}"
    if re.search(r"level\s+\d+(st|nd|rd|th)", text, re.I):
        return False, f"richiede livello di classe superiore al 1 ({text})"
    if "proficien" in text.lower():
        return True, f"proficiency: {text} (assunta da classe)"
    if re.search(r"rank", text, re.I):
        return True, f"skill rank: {text} (verificata a mano)"
    return True, f"forma prerequisito non valutabile: {text}"  # warning, non errore


def validate_feats(draft, sheet):
    """Conta talenti consentiti e valuta i prerequisiti noti."""
    ctx = {"abilities": dict(sheet["abilities"]), "bab": sheet["bab"], "feats": list(draft.feats)}
    allowed = 1 + (1 if draft.race == "Human" else 0) + (1 if draft.class_ in FEAT_BONUS_CLASSES else 0)
    if len(draft.feats) > allowed:
        sheet["errors"].append(f"feat: {len(draft.feats)} selezionati su {allowed} consentiti al lv1")
    for name in draft.feats:
        feat = catalogs.find_feat(name)
        if feat is None:
            sheet["errors"].append(f"talento sconosciuto: {name}")
            continue
        for prereq in feat.get("prerequisites", []):
            ok, note = _check_prereq(prereq, ctx)
            if not ok:
                sheet["errors"].append(f"{name}: prerequisito non soddisfatto ({note})")
            elif "non valutabile" in note:
                sheet["warnings"].append(f"{name}: {note}")
```

e in `build_character`, dopo la sezione skill, aggiungere:

```python
    validate_feats(draft, sheet)
```

- [ ] **Step 4: Run test + commit**

Run: `cd tooling/Master-DD-Taverna && .venv/Scripts/python -m pytest tests/test_pc_engine.py -q`
Expected: 7 passed.

```bash
cd tooling/Master-DD-Taverna
git add src/pc/engine.py tests/test_pc_engine.py
git commit -m "feat(pc): validate feat counts and prerequisites at level 1"
```

---

### Task 5: Equipaggiamento, ricchezza, CA e attacchi

**Files:**
- Modify: `tooling/Master-DD-Taverna/src/pc/engine.py`
- Modify: `tooling/Master-DD-Taverna/tests/test_pc_engine.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_equipment_wealth_and_ac():
    sheet = build_character(_draft(race_bonus_ability="str",
                                   skills={"Climb": 1, "Perception": 1, "Survival": 1},
                                   equipment=["Longsword", "Chain shirt", "Backpack (common)"]))
    assert sheet["errors"] == [], sheet["errors"]
    # Fighter: average 175 gp; Longsword 15 + Chain shirt 100 + Backpack 2 = 117 -> restano 58
    assert sheet["gold_remaining"] == 58
    # CA = 10 + armor +4 (Chain shirt) + Dex mod 1 (Dex 12; max +4 Chain shirt non cappato) = 15
    assert sheet["ac"] == 15
    melee = [a for a in sheet["attacks"] if a["weapon"] == "Longsword"][0]
    assert melee["bonus"] == 3  # bab 1 + Str mod +2 (str finale 15)
    assert melee["damage"] == "1d8+2"  # dmg_m + Str mod
```

CORREZIONE sul draft contratto: str finale e' 13+2=15 → mod +2. Il test corretto:

```python
    assert melee["bonus"] == 3  # bab 1 + Str mod +2 (str finale 15)
    assert melee["damage"] == "1d8+2"  # dmg_m + Str mod


def test_equipment_over_wealth_and_unknown():
    sheet = build_character(_draft(race_bonus_ability="str", skills={"Climb": 1},
                                   equipment=["Chain shirt", "Full plate"]))
    assert any("wealth" in e.lower() or "oro" in e.lower() for e in sheet["errors"])
    sheet = build_character(_draft(race_bonus_ability="str", skills={"Climb": 1},
                                   equipment=["Spada Inesistente"]))
    assert any("Spada Inesistente" in e for e in sheet["errors"])
```

- [ ] **Step 2: Run test to verify it fails**

Expected: FAIL (equipment step non implementato).

- [ ] **Step 3: Implement equipment step**

Aggiungere a `src/pc/engine.py`:

```python
def _parse_gp(text):
    """'15 gp' -> 15; 'average 175 gp' (da starting_wealth) -> 175."""
    import re
    m = re.search(r"(\d[\d,]*)\s*gp", text or "")
    return int(m.group(1).replace(",", "")) if m else 0


def _parse_bonus(text):
    """'+4' -> 4; None/''/'-' -> 0."""
    import re
    m = re.match(r"^\+(\d+)$", str(text or ""))
    return int(m.group(1)) if m else 0


def apply_equipment(draft, sheet):
    """Valida gli acquisti contro la ricchezza iniziale e calcola CA/attacchi."""
    import re
    cls = catalogs.get_class(draft.class_)
    wealth_text = cls["mechanics"].get("starting_wealth", "")
    wealth = 0
    if "average" in wealth_text:
        m = re.search(r"average\s+([\d,]+)\s*gp", wealth_text)
        wealth = int(m.group(1).replace(",", "")) if m else 0
    else:
        wealth = _parse_gp(wealth_text)
    spent = 0
    items = []
    for name in draft.equipment:
        item = catalogs.find_equipment(name)
        if item is None:
            sheet["errors"].append(f"equipaggiamento sconosciuto: {name}")
            continue
        cost = _parse_gp(item["mechanics"].get("cost"))
        spent += cost
        items.append({"name": name, "cost": cost, "mechanics": item["mechanics"],
                      "tags": item.get("tags", [])})
    if spent > wealth:
        sheet["errors"].append(f"wealth: spesi {spent} gp oltre la ricchezza iniziale {wealth} gp")
    sheet["gold_remaining"] = wealth - spent
    mods = {ab: ability_mod(sc) for ab, sc in sheet["abilities"].items()}
    armor = shield = max_dex = None
    for it in items:
        m = it["mechanics"]
        bonus = _parse_bonus(m.get("armor_bonus"))
        if "shield" in it["tags"]:
            shield = (shield or 0) + bonus
        elif bonus:
            armor = (armor or 0) + bonus
            md = m.get("maximum_dex_bonus") or m.get("max_dex_bonus")
            max_dex = _parse_bonus(md) if md else max_dex
    dex = min(mods["dex"], max_dex) if max_dex is not None else mods["dex"]
    sheet["ac"] = 10 + (armor or 0) + (shield or 0) + dex
    attacks = []
    for it in items:
        if "weapon" not in it["tags"]:
            continue
        m = it["mechanics"]
        is_ranged = bool(m.get("range"))
        mod = mods["dex"] if is_ranged else mods["str"]
        attacks.append({"weapon": it["name"], "bonus": sheet["bab"] + mod,
                        "damage": f"{m.get('dmg_m', '-')}{'+' + str(mod) if mod > 0 and not is_ranged else ''}",
                        "critical": m.get("critical"), "range": m.get("range")})
    sheet["attacks"] = attacks
```

e in `build_character`, dopo `validate_feats(draft, sheet)`, aggiungere:

```python
    apply_equipment(draft, sheet)
```

NOTA IMPLEMENTAZIONE: le chiavi `mechanics` di equipment_mundane.json derivano dagli header reali delle tabelle AoN (es. `armor_bonus`, `maximum_dex_bonus`, `dmg_m`, `critical`, `range`, `weight`, `cost`): prima di scrivere il test, verifica le chiavi reali con `.venv/Scripts/python -c "import json; d=json.load(open('data/reference/ogl/equipment_mundane.json',encoding='utf-8')); print([x['mechanics'] for x in d['entries'] if x['name']=='Chain shirt'][0])"` e adatta `_parse_bonus`/lookup di conseguenza (aggiornando anche i test).

- [ ] **Step 4: Run test + commit**

Run: `cd tooling/Master-DD-Taverna && .venv/Scripts/python -m pytest tests/test_pc_engine.py -q`
Expected: 9 passed (con il test corretto del blocco CORREZIONE, non quello con assert False).

```bash
cd tooling/Master-DD-Taverna
git add src/pc/engine.py tests/test_pc_engine.py
git commit -m "feat(pc): compute equipment wealth ac and attacks at level 1"
```

---

### Task 6: Tratti + assembly finale + render markdown + end-to-end

**Files:**
- Modify: `tooling/Master-DD-Taverna/src/pc/engine.py`
- Modify: `tooling/Master-DD-Taverna/tests/test_pc_engine.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_traits_validation():
    sheet = build_character(_draft(race_bonus_ability="str", skills={"Climb": 1, "Perception": 1, "Survival": 1},
                                   traits=["Reactionary", "Indomitable Faith"]))
    assert sheet["errors"] == []
    assert sheet["traits"] == ["Reactionary", "Indomitable Faith"]
    # 2 stessa categoria -> errore; 3 tratti -> errore
    bad = _draft(race_bonus_ability="str", skills={"Climb": 1, "Perception": 1, "Survival": 1},
                 traits=["Reactionary", "Indomitable Faith", "Armor Expert"])
    sheet = build_character(bad)
    assert any("tratt" in e.lower() for e in sheet["errors"])


def test_markdown_render():
    sheet = build_character(_draft(race_bonus_ability="str", skills={"Climb": 1, "Perception": 1, "Survival": 1},
                                   feats=["Power Attack", "Dodge", "Cleave"],
                                   traits=["Reactionary", "Indomitable Faith"],
                                   equipment=["Longsword", "Chain shirt"]))
    md = render_markdown(sheet)
    assert "# T" in md and "PF: 12" in md and "Longsword" in md and "Power Attack" in md
```

- [ ] **Step 2: Run test to verify it fails**

Expected: FAIL (traits/render non implementati).

- [ ] **Step 3: Implement traits + render**

Aggiungere a `src/pc/engine.py`:

```python
def validate_traits(draft, sheet):
    if len(draft.traits) > 2:
        sheet["errors"].append(f"tratti: {len(draft.traits)} selezionati, max 2")
    seen = set()
    out = []
    for name in draft.traits:
        trait = catalogs.find_trait(name)
        if trait is None:
            sheet["errors"].append(f"tratto sconosciuto: {name}")
            continue
        cat = trait["mechanics"].get("category")
        if cat in seen:
            sheet["errors"].append(f"tratti: due tratti della stessa categoria ({cat})")
        seen.add(cat)
        out.append(name)
    sheet["traits"] = out


def render_markdown(sheet):
    """Scheda testuale compatta della build lv1."""
    mods = {ab: ability_mod(sc) for ab, sc in sheet["abilities"].items()}
    lines = [f"# {sheet['name']}",
             f"{sheet['race']} {sheet['class']} 1 — PF: {sheet['hp']} — CA: {sheet['ac']} — Iniziativa: {'+' if sheet['initiative'] >= 0 else ''}{sheet['initiative']}",
             "",
             "**Caratteristiche**: " + ", ".join(
                 f"{ab.upper()} {sc} ({'+' if mods[ab] >= 0 else ''}{mods[ab]})"
                 for ab, sc in sheet["abilities"].items()),
             f"**TS**: Tempra {'+' if sheet['saves']['fort'] >= 0 else ''}{sheet['saves']['fort']}, "
             f"Riflessi {'+' if sheet['saves']['ref'] >= 0 else ''}{sheet['saves']['ref']}, "
             f"Volonta' {'+' if sheet['saves']['will'] >= 0 else ''}{sheet['saves']['will']} — BAB +{sheet['bab']}"]
    if sheet.get("attacks"):
        lines.append("**Attacchi**: " + "; ".join(f"{a['weapon']} +{a['bonus']} ({a['damage']})" for a in sheet["attacks"]))
    if sheet.get("skills"):
        lines.append("**Skill**: " + ", ".join(f"{n} +{s['total']}" for n, s in sheet["skills"].items()))
    if sheet.get("feats"):
        lines.append("**Talenti**: " + ", ".join(sheet["feats"]))
    if sheet.get("traits"):
        lines.append("**Tratti**: " + ", ".join(sheet["traits"]))
    if sheet.get("equipment"):
        lines.append(f"**Equip** (oro restante {sheet.get('gold_remaining', 0)} gp): "
                     + ", ".join(i["name"] for i in sheet["equipment"]))
    if sheet.get("warnings"):
        lines.append("_Note_: " + " | ".join(sheet["warnings"]))
    return "\n".join(lines) + "\n"
```

e in `build_character`: dopo `apply_equipment`, aggiungere `validate_traits(draft, sheet)`; e il draft feats/traits/equipment vanno anche in sheet: aggiungere `sheet["feats"] = list(draft.feats)` (in validate_feats, se errors vuoti o comunque alla fine), `sheet["equipment"] = items` (in apply_equipment).

- [ ] **Step 4: Run test + commit**

Run: `cd tooling/Master-DD-Taverna && .venv/Scripts/python -m pytest tests/test_pc_engine.py -q`
Expected: 11 passed.

```bash
cd tooling/Master-DD-Taverna
git add src/pc/engine.py tests/test_pc_engine.py
git commit -m "feat(pc): validate traits and render level 1 markdown sheet"
```

---

### Task 7: Endpoint API `POST /pc/build` + test + docs

**Files:**
- Modify: `tooling/Master-DD-Taverna/src/app.py`
- Create: `tooling/Master-DD-Taverna/tests/test_pc_api.py`
- Modify: `tooling/Master-DD-Taverna/README.md`
- Modify: `tooling/Master-DD-Taverna/AGENTS.md`

- [ ] **Step 1: Leggere il pattern esistente**

Leggi `src/app.py` intorno a `POST /build/stub` (riga ~309): nota il decorator, la dipendenza auth (`Depends(require_api_key)` se presente), come valida il body (JSON schema) e come ritorna errori (HTTPException status/detail). Leggi anche `tests/test_app.py` per il pattern di autenticazione dei test (fixture `auth_headers` o simile). L'endpoint nuovo deve SPECCHIARE quel pattern, non inventarne uno.

- [ ] **Step 2: Write the failing test**

```python
"""Test endpoint POST /pc/build."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# usa lo stesso client/auth pattern di tests/test_app.py
from tests.test_app import client, auth_headers  # adatta all'import reale

VALID = {
    "name": "Seelah", "method": "point-buy", "campaign_type": "Standard Fantasy",
    "abilities": {"str": 13, "dex": 12, "con": 13, "int": 10, "wis": 14, "cha": 12},
    "race": "Human", "race_bonus_ability": "str", "class": "Fighter",
    "skills": {"Climb": 1, "Perception": 1, "Survival": 1},
    "feats": ["Power Attack", "Dodge", "Cleave"],
    "traits": ["Reactionary", "Indomitable Faith"],
    "equipment": ["Longsword", "Chain shirt"],
}


def test_pc_build_ok():
    resp = client.post("/pc/build", json=VALID, headers=auth_headers())
    assert resp.status_code == 200, resp.text
    sheet = resp.json()
    assert sheet["errors"] == []
    assert sheet["hp"] == 12 and sheet["ac"] == 15
    assert sheet["abilities"]["str"] == 15


def test_pc_build_invalid():
    bad = dict(VALID, abilities={"str": 14, "dex": 12, "con": 13, "int": 10, "wis": 15, "cha": 11})
    resp = client.post("/pc/build", json=bad, headers=auth_headers())
    assert resp.status_code == 422
    assert "budget" in resp.text.lower()
```

- [ ] **Step 3: Implement endpoint**

In `src/app.py`, dopo l'endpoint `/build/stub` (stesso stile):

```python
@app.post("/pc/build")
async def pc_build(draft: dict, _: None = Depends(require_api_key)):
    """Costruzione deterministica di un PG lv1 dai cataloghi OGL (nessun LLM)."""
    from src.pc.engine import build_character
    from src.pc.models import CharacterDraft
    try:
        sheet = build_character(CharacterDraft.from_dict(draft))
    except (KeyError, TypeError) as exc:
        raise HTTPException(status_code=400, detail=f"draft malformato: {exc}")
    if sheet["errors"]:
        raise HTTPException(status_code=422, detail=sheet["errors"])
    return sheet
```

(adatta il decorator/auth all'ESATTO pattern di `POST /build/stub`: se li' la dependency si chiama diversamente, copia quella.)

- [ ] **Step 4: Run test + docs + commit**

Run: `cd tooling/Master-DD-Taverna && .venv/Scripts/python -m pytest tests/test_pc_api.py -q`
Expected: 2 passed.

Aggiungere a `README.md` (sezione API/docs, una riga): `POST /pc/build` — costruzione deterministica PG lv1 dai cataloghi OGL (point-buy, razza, classe, skill, talenti, tratti, equip; 422 con lista errori di validazione). Vedi `src/pc/`.

Aggiungere ad `AGENTS.md` sezione Struttura, una riga: `src/pc/` — builder deterministico PG lv1 (catalogs/engine/models) + endpoint `POST /pc/build`.

```bash
cd tooling/Master-DD-Taverna
git add src/app.py tests/test_pc_api.py README.md AGENTS.md
git commit -m "feat(pc): expose deterministic level 1 builder endpoint"
```

---

### Task 8: Verifica completa + handoff

**Files:**
- Modify: `sessione-2026-07-16/HANDOFF_ATTIVO.md` (a cura del controller, non dell'implementer)

- [ ] **Step 1: Suite completa**

Run: `cd tooling/Master-DD-Taverna && .venv/Scripts/python -m pytest -q`
Expected: tutti passed, 1 skipped totale (gate).

- [ ] **Step 2: Verifica completa workspace**

Run: `cd C:/dev/pathfinder && python launch.py test`
Expected: `TUTTE LE VERIFICHE OK`.

- [ ] **Step 3: Smoke reale dell'endpoint**

Avvia l'API (`.venv/Scripts/python -m uvicorn src.app:app --port 8000` in background) e chiama:

```bash
curl -s -X POST http://localhost:8000/pc/build -H "x-api-key: test" -H "Content-Type: application/json" -d '{"name":"Test","method":"point-buy","campaign_type":"Standard Fantasy","abilities":{"str":13,"dex":12,"con":13,"int":10,"wis":14,"cha":12},"race":"Human","race_bonus_ability":"str","class":"Fighter","skills":{"Climb":1,"Perception":1,"Survival":1},"feats":["Power Attack","Dodge","Cleave"],"traits":["Reactionary","Indomitable Faith"],"equipment":["Longsword","Chain shirt"]}'
```

Expected: JSON con `hp: 12`, `ac: 16`, `abilities.str: 15`, nessun errore. Poi chiudi l'API (taskkill del processo uvicorn).

- [ ] **Step 4: Commit finale dati/report (se serve) + handoff controller**

Se `reports/data_quality_report.json` e' cambiato, committarlo; il controller aggiorna `HANDOFF_ATTIVO.md` (lotto 4 Fase 2 completata) e pusha.

---

## Note operative

- **Scope lv1 esplicito**: progression[0] solo; niente multiclasse, niente livelli >1, niente archetipi, niente rolled abilities (solo point-buy). Estensioni future: lv N (progression[N-1], HP per livello, WBL), archetipi (mechanics da importare), gestazione incantesimi (spells.json ha le liste).
- **Chiavi mechanics reali**: verificare SEMPRE le chiavi dei JSON reali prima dei test (Step equipment): i nomi derivano dagli header AoN (`maximum_dex_bonus`, non `max_dex`).
- **Prereq evaluator**: deliberatamente permissivo sulle forme ignote (warning, non errore) — le forme coperte sono ability score, BAB, feat name, class level, proficiency, skill rank.
- **Draft example del contratto**: il draft Seelah in testa (14/12/13/10/15/11) supera il budget 15 — e' voluto come caso negativo nei test; i draft validi usano (13/12/13/10/14/12).
- **Pattern repo**: shim sys.path nei tool, write=False nei builder, nessun test skipped nuovo, commit convenzionali (hook attivo), niente `Co-Authored-By:`.
