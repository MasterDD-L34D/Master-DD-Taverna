# Feat Mechanical Effects Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Applicare gli effetti meccanici dei talenti selezionati ai valori calcolati dal builder deterministico (Fase 2), chiudendo la limitazione documentata "effetti non applicati": hp/CA/TS/iniziativa/bonus attacco/skill per i talenti supportati, con selezioni parentetiche (`Weapon Focus (X)`, `Skill Focus (Y)`) e Weapon Finesse.

**Architecture:** Nuovo modulo `src/pc/feat_effects.py` con mappa dichiarativa `FEAT_EFFECTS` (talento → modificatori), parser selezioni parentetiche e `apply_feat_effects(sheet)` chiamata da `build_character` come ultimo step prima del return. Niente dipendenze nuove; aggiornamento docs (README/engine docstring) dalla limitazione a "applicati per i talenti supportati".

**Tech Stack:** Python 3 stdlib, cataloghi OGL esistenti (`src/pc/catalogs.py`), test pytest su `tests/test_pc_engine.py` (29 passed attuali) + eventuale `tests/test_pc_api.py` (4 passed).

**Talenti supportati (v1):**
- Passivi diretti: `Toughness` (+3 hp), `Dodge` (+1 CA), `Iron Will` (+2 Will), `Lightning Reflexes` (+2 Ref), `Great Fortitude` (+2 Fort), `Improved Initiative` (+4 iniziativa)
- Selezioni: `Weapon Focus (X)` (+1 bonus con arma X; senza selezione → prima arma + warning), `Skill Focus (Y)` (+3 alla skill Y, anche senza ranks)
- `Weapon Finesse`: bonus attacco = BAB + Dex (invece di Str) per le armi finessabili (lista curata v1, vedi Task 3)

---

### Task 1: `src/pc/feat_effects.py` — mappa effetti + apply base

**Files:**
- Create: `tooling/Master-DD-Taverna/src/pc/feat_effects.py`
- Modify: `tooling/Master-DD-Taverna/src/pc/engine.py` (chiamata finale)
- Test: `tooling/Master-DD-Taverna/tests/test_pc_engine.py`

- [ ] **Step 1: Write the failing tests**

Aggiungere a `tests/test_pc_engine.py`:

```python
def test_passive_feat_effects_applied():
    plain = build_character(_draft(abilities=dict(_OK_ABILS), race_bonus_ability="str",
                                   skills={"Climb": 1, "Perception": 1, "Survival": 1}))
    boosted = build_character(_draft(abilities=dict(_OK_ABILS), race_bonus_ability="str",
                                     skills={"Climb": 1, "Perception": 1, "Survival": 1},
                                     feats=["Toughness", "Dodge", "Iron Will", "Improved Initiative"]))
    assert boosted["errors"] == []
    assert boosted["hp"] == plain["hp"] + 3          # Toughness
    assert boosted["ac"] == plain["ac"] + 1          # Dodge
    assert boosted["saves"]["will"] == plain["saves"]["will"] + 2  # Iron Will
    assert boosted["initiative"] == plain["initiative"] + 4        # Improved Initiative
    assert boosted["saves"]["fort"] == plain["saves"]["fort"]      # invariato
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd tooling/Master-DD-Taverna && .venv/Scripts/python -m pytest tests/test_pc_engine.py -q`
Expected: FAIL `ImportError: cannot import name 'apply_feat_effects'` (o differenze hp/ac).

- [ ] **Step 3: Implement**

`src/pc/feat_effects.py`:

```python
"""Effetti meccanici dei talenti applicati ai valori della scheda (lv1).

La mappa e' deliberatamente dichiarativa: ogni talento -> dict di modificatori
applicati in apply_feat_effects. I talenti senza effetto numerico sui valori
lv1 (metamagic, skill focus generici non selezionati, granted di classe) sono
ignorati senza warning; le selezioni mancanti/invalide producono warning."""

FEAT_EFFECTS = {
    "Toughness": {"hp": 3},
    "Dodge": {"ac": 1},
    "Iron Will": {"saves": {"will": 2}},
    "Lightning Reflexes": {"saves": {"ref": 2}},
    "Great Fortitude": {"saves": {"fort": 2}},
    "Improved Initiative": {"initiative": 4},
}


def apply_feat_effects(sheet):
    """Applica FEAT_EFFECTS ai talenti in sheet['feats'] (in place)."""
    for feat in sheet.get("feats", []):
        effect = FEAT_EFFECTS.get(feat)
        if not effect:
            continue
        if "hp" in effect:
            sheet["hp"] += effect["hp"]
        if "ac" in effect:
            sheet["ac"] += effect["ac"]
        if "initiative" in effect:
            sheet["initiative"] += effect["initiative"]
        for save, bonus in effect.get("saves", {}).items():
            sheet["saves"][save] += bonus
```

e in `build_character` (`src/pc/engine.py`), come ULTIMA riga prima del `return sheet`:

```python
    from src.pc.feat_effects import apply_feat_effects
    apply_feat_effects(sheet)
```

(import in cima alla funzione o al modulo, seguendo lo stile del file.)

- [ ] **Step 4: Run test + commit**

Run: `cd tooling/Master-DD-Taverna && .venv/Scripts/python -m pytest tests/test_pc_engine.py -q`
Expected: 30 passed.

```bash
cd tooling/Master-DD-Taverna
git add src/pc/feat_effects.py src/pc/engine.py tests/test_pc_engine.py
git commit -m "feat(pc): apply passive feat effects to computed values"
```

---

### Task 2: Selezioni parentetiche — `Weapon Focus (X)` e `Skill Focus (Y)`

**Files:**
- Modify: `tooling/Master-DD-Taverna/src/pc/feat_effects.py`
- Modify: `tooling/Master-DD-Taverna/tests/test_pc_engine.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_weapon_focus_selection():
    sheet = build_character(_draft(abilities=dict(_OK_ABILS), race_bonus_ability="str",
                                   skills={"Climb": 1, "Perception": 1, "Survival": 1},
                                   feats=["Weapon Focus (Longsword)"],
                                   equipment=["Longsword", "Shortbow"]))
    assert sheet["errors"] == []
    melee = [a for a in sheet["attacks"] if a["weapon"] == "Longsword"][0]
    bow = [a for a in sheet["attacks"] if a["weapon"] == "Shortbow"][0]
    assert melee["bonus"] == 4   # bab 1 + str 2 + focus 1
    assert bow["bonus"] == 2     # bab 1 + dex 1, niente focus


def test_weapon_focus_without_selection_warns():
    sheet = build_character(_draft(abilities=dict(_OK_ABILS), race_bonus_ability="str",
                                   skills={"Climb": 1, "Perception": 1, "Survival": 1},
                                   feats=["Weapon Focus"],
                                   equipment=["Longsword"]))
    assert sheet["errors"] == []
    assert any("Weapon Focus" in w for w in sheet["warnings"])
    assert sheet["attacks"][0]["bonus"] == 4  # fallback: prima arma +1


def test_skill_focus_selection():
    sheet = build_character(_draft(abilities=dict(_OK_ABILS), race_bonus_ability="str",
                                   skills={"Climb": 1, "Perception": 1, "Survival": 1},
                                   feats=["Skill Focus (Perception)"]))
    assert sheet["errors"] == []
    assert sheet["skills"]["Perception"]["total"] == 1 + 2 + 3  # rank1 + wis2 + focus3
    # senza ranks nella skill: +3 lo stesso (RAW)
    sheet2 = build_character(_draft(abilities=dict(_OK_ABILS), race_bonus_ability="str",
                                    skills={"Climb": 1, "Perception": 1, "Survival": 1},
                                    feats=["Skill Focus (Ride)"]))
    assert sheet2["skills"]["Ride"]["total"] == 0 + 1 + 3  # 0 rank + str1 + focus3 (Ride e' Str)
    assert sheet2["skills"]["Ride"]["ranks"] == 0
```

NOTA: verifica prima la key_ability reale di Ride in skills.json (potrebbe essere dex! `.venv/Scripts/python -c "from src.pc.catalogs import get_skill; print(get_skill('Ride')['mechanics'])"`) e adatta l'asserzione (`0 + mods[key] + 3`).

- [ ] **Step 2: Run test to verify it fails**

Expected: FAIL (selections non implementate).

- [ ] **Step 3: Implement**

Aggiungere a `src/pc/feat_effects.py`:

```python
import re

from src.pc import catalogs


def parse_selection(feat_name):
    """'Weapon Focus (Longsword)' -> ('Weapon Focus', 'Longsword'); altro -> (name, None)."""
    m = re.match(r"^(.+?)\s*\(([^)]+)\)\s*$", feat_name)
    return (m.group(1).strip(), m.group(2).strip()) if m else (feat_name, None)


def _apply_weapon_focus(sheet, selection):
    if not sheet.get("attacks"):
        sheet["warnings"].append("Weapon Focus: nessun attacco da migliorare")
        return
    if selection:
        for attack in sheet["attacks"]:
            if attack["weapon"].lower() == selection.lower():
                attack["bonus"] += 1
                return
        sheet["warnings"].append(f"Weapon Focus ({selection}): arma non in equip, nessun bonus")
        return
    sheet["attacks"][0]["bonus"] += 1
    sheet["warnings"].append("Weapon Focus senza selezione: bonus applicato alla prima arma")


def _apply_skill_focus(sheet, selection, mods):
    if not selection:
        sheet["warnings"].append("Skill Focus senza selezione: nessun bonus applicato")
        return
    skills = sheet.setdefault("skills", {})
    if selection in skills:
        skills[selection]["total"] += 3
        return
    sk = catalogs.get_skill(selection)
    if sk is None:
        sheet["warnings"].append(f"Skill Focus ({selection}): skill sconosciuta")
        return
    key = sk["mechanics"]["key_ability"]
    skills[selection] = {"ranks": 0, "ability": key, "total": mods[key] + 3, "class_skill": False}
```

e in `apply_feat_effects`, prima del loop su FEAT_EFFECTS, gestire le selezioni:

```python
def apply_feat_effects(sheet):
    mods = {ab: (sc - 10) // 2 for ab, sc in sheet["abilities"].items()}
    for feat in sheet.get("feats", []):
        base, selection = parse_selection(feat)
        if base == "Weapon Focus":
            _apply_weapon_focus(sheet, selection)
        elif base == "Skill Focus":
            _apply_skill_focus(sheet, selection, mods)
            continue
        effect = FEAT_EFFECTS.get(base)
        ...  # come Task 1
```

NOTA coerenza validazione: il prereq evaluator in engine.py gia' gestisce la forma parentetica nella chain (strip `\s*\([^)]*\)\s*$` prima di find_feat — aggiunto nel Task 4 fix). `validate_feats` deve trovare il talento base: se non lo fa gia' (cerca `catalogs.find_feat(name)` col nome intero), applica la stessa strip: `feat_base = re.sub(r"\s*\([^)]*\)\s*$", "", name)` prima di find_feat. Verifica e allinea.

- [ ] **Step 4: Run test + commit**

Run: `cd tooling/Master-DD-Taverna && .venv/Scripts/python -m pytest tests/test_pc_engine.py -q`
Expected: 33 passed.

```bash
cd tooling/Master-DD-Taverna
git add src/pc/feat_effects.py src/pc/engine.py tests/test_pc_engine.py
git commit -m "feat(pc): support weapon and skill focus selections"
```

---

### Task 3: Weapon Finesse + lista armi finessabili + docs

**Files:**
- Modify: `tooling/Master-DD-Taverna/src/pc/feat_effects.py`
- Modify: `tooling/Master-DD-Taverna/tests/test_pc_engine.py`
- Modify: `tooling/Master-DD-Taverna/README.md`
- Modify: `tooling/Master-DD-Taverna/src/pc/engine.py` (docstring limitazione)

- [ ] **Step 1: Write the failing tests**

```python
def test_weapon_finesse_uses_dex():
    # Halfling Rogue (dex+2, cha+2, str-2 razziali) con Weapon Finesse e Dagger (finessabile)
    sheet = build_character(_draft(abilities=dict(_OK_ABILS),
                                   **{"race": "Halfling", "class": "Rogue"},
                                   skills={"Stealth": 1, "Perception": 1, "Acrobatics": 1},
                                   feats=["Weapon Finesse"],
                                   equipment=["Dagger", "Longsword"]))
    assert sheet["errors"] == []
    dagger = [a for a in sheet["attacks"] if a["weapon"] == "Dagger"][0]
    longsword = [a for a in sheet["attacks"] if a["weapon"] == "Longsword"][0]
    # dex 12+2=14 -> +2, +1 taglia; bab Rogue 0
    assert dagger["bonus"] == 3          # bab 0 + dex 2 + taglia 1 (NON str)
    assert dagger["damage"] == "1d4"     # danno a Str: str 13-2=11 -> mod 0
    assert longsword["bonus"] == 1       # bab 0 + str 0 + taglia 1 (non finesse)


def test_finesse_documented_list():
    from src.pc.feat_effects import FINESSE_WEAPONS
    assert "Dagger" in FINESSE_WEAPONS and "Rapier" in FINESSE_WEAPONS
    assert "Longsword" not in FINESSE_WEAPONS
```

- [ ] **Step 2: Run test to verify it fails**

Expected: FAIL (finesse non implementata).

- [ ] **Step 3: Implement**

Aggiungere a `src/pc/feat_effects.py`:

```python
# Lista curata v1 di armi finessabili comuni (la categoria "light" completa
# non e' ancora nei mechanics del catalogo equipment; ampliare quando disponibile).
FINESSE_WEAPONS = {
    "Dagger", "Punching dagger", "Rapier", "Short sword", "Whip",
    "Spiked chain", "Elven curve blade", "Light hammer", "Handaxe",
    "Sickle", "Kukri", "Starknife",
}


def _apply_finesse(sheet, mods):
    for attack in sheet.get("attacks", []):
        if attack["weapon"] in FINESSE_WEAPONS:
            attack["bonus"] += mods["dex"] - mods["str"]
```

e in `apply_feat_effects`: `elif base == "Weapon Finesse": _apply_finesse(sheet, mods)`.

NOTA: `attack["bonus"] += mods["dex"] - mods["str"]` sostituisce la stat (dopo che apply_equipment ha messo str o dex-thrown): per Dagger (thrown<30ft → gia' melee str) passa da str a dex; il danno resta a str (corretto RAW: finesse cambia solo il tiro per colpire).

**Docs**:
- `src/pc/engine.py` docstring di build_character: la limitazione diventa "gli effetti meccanici dei talenti sono applicati solo per i talenti supportati in `src/pc/feat_effects.py` (passivi lv1, Weapon/Skill Focus, Weapon Finesse)".
- `README.md` riga endpoint: "gli effetti meccanici dei talenti supportati (passivi lv1, Weapon/Skill Focus, Weapon Finesse — vedi `src/pc/feat_effects.py`) vengono applicati ai valori; gli altri sono solo validati".

- [ ] **Step 4: Run test + full verify + commit**

Run: `cd tooling/Master-DD-Taverna && .venv/Scripts/python -m pytest tests/test_pc_engine.py -q`
Expected: 35 passed.

Run: `cd tooling/Master-DD-Taverna && .venv/Scripts/python -m pytest tests/ -q`
Expected: nessuna regressione (1 skipped esatto).

```bash
cd tooling/Master-DD-Taverna
git add src/pc/feat_effects.py src/pc/engine.py tests/test_pc_engine.py README.md
git commit -m "feat(pc): apply weapon finesse attack stat swap"
```

---

### Task 4: Verifica completa + handoff (controller)

- [ ] `cd C:/dev/pathfinder && python launch.py test` → TUTTE LE VERIFICHE OK
- [ ] Smoke API reale (POST /pc/build con feats=[Toughness, Dodge, Weapon Finesse] → hp+3, ac+1, finesse su Dagger)
- [ ] Rigenera `reports/data_quality_report.json` se cambiato, commit
- [ ] Aggiorna `sessione-2026-07-16/HANDOFF_ATTIVO.md` (feat effects completato) + commit piano in `planning/` + push

---

## Note operative

- **Weapon Focus / Skill Focus senza selezione**: fallback con warning, mai errore (talento valido RAW, solo non applicabile automaticamente).
- **Danno finesse**: resta a Str (finesse cambia solo il bonus attacco — corretto PF1e).
- **Talenti non modellati**: ignorati in silenzio (metamagic, granted di classe, condizionali tipo Point-Blank Shot); niente warning di massa.
- **Validazione selezioni**: la strip parentetica in validate_feats deve trovare il talento base in feats.json (allineata al fix Task 4 della chain prerequisiti).
- **Fuori scope (prossimi lotti)**: livelli >1 (progression[N], HP per livello, WBL, spells/day), effetti condizionali (Point-Blank Shot, Power Attack), categoria "light" completa nel catalogo equipment, arcani spells da spells.json.
- Commit convenzionali (hook attivo), MAI `Co-Authored-By:`, nessun test skipped nuovo.
