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
