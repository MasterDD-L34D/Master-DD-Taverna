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
        "spells": "spells.json",
    }[kind]
    with open(OGL_DIR / filename, encoding="utf-8") as f:
        return json.load(f)["entries"]


@functools.lru_cache(maxsize=None)
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


# NOTA: le entry restituite dai getter sono condivise (cache): non mutarle.
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


def find_spell(name):
    return _by_name("spells").get(name)


def spell_level_for_class(spell, class_name):
    """Cerchio di `spell` per `class_name`; None se la classe non la lancia.

    Le chiavi di mechanics.spell_level sono lowercase e possono essere
    combinate ("sorcerer/wizard", "cleric/oracle"): splittate su "/".
    Il match sul nome classe e' case-insensitive ("Wizard" == "wizard").
    Le classi assenti da classes.json (bloodrager, oracle, occultist, ...)
    sono ignorate senza errore: una chiave che nomina solo classi fuori
    catalogo non produce match."""
    known = {e["name"].lower() for e in load("classes")}
    target = class_name.lower()
    for key, level in spell.get("mechanics", {}).get("spell_level", {}).items():
        for part in key.split("/"):
            if part in known and part == target:
                return level
    return None


# Character Wealth by Level (PFRPG Core, tabella OGC).
WBL_BY_LEVEL = {2: 1000, 3: 3000, 4: 6000, 5: 10500, 6: 16000, 7: 23500,
                8: 33000, 9: 46000, 10: 62000, 11: 82000, 12: 108000, 13: 140000,
                14: 185000, 15: 240000, 16: 315000, 17: 410000, 18: 530000,
                19: 685000, 20: 880000}


def wealth_by_level(level):
    """Wealth-by-level per livelli > 1; None per lv1 (usa starting_wealth)."""
    return None if level == 1 else WBL_BY_LEVEL.get(level)


def class_skill_matches(skill_name, class_skill):
    """Match skill del catalogo vs etichetta class_skills di classes.json.
    Case-insensitive; 'Knowledge (all)' matcha ogni Knowledge specifica.
    NOTA: specchio di tools/import_reference._class_skill_matches (stesso criterio)."""
    s = skill_name.lower()
    c = class_skill.lower()
    if c == "knowledge (all)":
        return s.startswith("knowledge (")
    return s == c
