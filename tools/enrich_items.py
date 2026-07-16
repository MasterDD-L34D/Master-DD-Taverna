#!/usr/bin/env python3
"""Arricchisce il catalogo items.json con descrizioni meccaniche OGL.

Genera descrizioni per armi, armature, scudi, oggetti meravigliosi,
consumabili e gear basandosi su regole meccaniche di Pathfinder 1E.
Non include lore, nomi propri di setting o Product Identity.

Uso:
    python tools/enrich_items.py [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import re
import time
import unicodedata
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parent.parent
REFERENCE_DIR = ROOT_DIR / "data" / "reference"
ITEMS_PATH = REFERENCE_DIR / "ogl" / "items.json"


def normalize_name(name: str) -> str:
    """Normalizza un nome per il matching: minuscolo, senza accenti/apostrofi."""
    n = unicodedata.normalize("NFKD", name)
    n = "".join(c for c in n if not unicodedata.combining(c))
    n = n.lower()
    n = re.sub(r"[’'']", "", n)
    n = re.sub(r"[^a-z0-9]+", "", n)
    return n


def extract_bonus(name: str) -> int | None:
    """Estrae il primo bonus +N dal nome."""
    m = re.search(r"\+\s*(\d+)", name)
    return int(m.group(1)) if m else None


def extract_quantity(name: str) -> int | None:
    """Estrae una quantità come 'x5' o '(20 cariche)'."""
    m = re.search(r"x\s*(\d+)", name, flags=re.IGNORECASE)
    if m:
        return int(m.group(1))
    m = re.search(r"(\d+)\s*cariche", name, flags=re.IGNORECASE)
    if m:
        return int(m.group(1))
    return None


# ---------------------------------------------------------------------------
# Tabelle meccaniche di base (OGL)
# ---------------------------------------------------------------------------
WEAPONS: dict[str, dict[str, Any]] = {
    # simple
    "dagger": {"prof": "simple", "hands": "light", "dmg": "1d4", "crit": "19-20/x2", "type": "piercing or slashing", "ranged": False},
    "pugnale": {"prof": "simple", "hands": "light", "dmg": "1d4", "crit": "19-20/x2", "type": "piercing or slashing", "ranged": False},
    "lightmace": {"prof": "simple", "hands": "light", "dmg": "1d6", "crit": "x2", "type": "bludgeoning", "ranged": False},
    "heavymace": {"prof": "simple", "hands": "one-handed", "dmg": "1d8", "crit": "x2", "type": "bludgeoning", "ranged": False},
    "sickle": {"prof": "simple", "hands": "light", "dmg": "1d6", "crit": "x2", "type": "slashing", "ranged": False},
    "club": {"prof": "simple", "hands": "one-handed", "dmg": "1d6", "crit": "x2", "type": "bludgeoning", "ranged": False},
    "quarterstaff": {"prof": "simple", "hands": "two-handed", "dmg": "1d6/1d6", "crit": "x2", "type": "bludgeoning", "ranged": False, "double": True},
    "spear": {"prof": "simple", "hands": "two-handed", "dmg": "1d8", "crit": "x3", "type": "piercing", "ranged": False},
    "lancia": {"prof": "simple", "hands": "two-handed", "dmg": "1d8", "crit": "x3", "type": "piercing", "ranged": False},
    "crossbowlight": {"prof": "simple", "hands": "light", "dmg": "1d8", "crit": "19-20/x2", "type": "piercing", "ranged": True},
    "crossbowheavy": {"prof": "simple", "hands": "two-handed", "dmg": "1d10", "crit": "19-20/x2", "type": "piercing", "ranged": True},
    "sling": {"prof": "simple", "hands": "light", "dmg": "1d4", "crit": "x2", "type": "bludgeoning", "ranged": True},
    "fionda": {"prof": "simple", "hands": "light", "dmg": "1d4", "crit": "x2", "type": "bludgeoning", "ranged": True},
    # martial
    "throwingaxe": {"prof": "martial", "hands": "light", "dmg": "1d6", "crit": "x2", "type": "slashing", "ranged": True},
    "lighthammer": {"prof": "martial", "hands": "light", "dmg": "1d4", "crit": "x2", "type": "bludgeoning", "ranged": False},
    "martelloleggero": {"prof": "martial", "hands": "light", "dmg": "1d4", "crit": "x2", "type": "bludgeoning", "ranged": False},
    "handaxe": {"prof": "martial", "hands": "light", "dmg": "1d6", "crit": "x3", "type": "slashing", "ranged": False},
    "kukri": {"prof": "martial", "hands": "light", "dmg": "1d4", "crit": "18-20/x2", "type": "slashing", "ranged": False},
    "shortsword": {"prof": "martial", "hands": "light", "dmg": "1d6", "crit": "19-20/x2", "type": "piercing", "ranged": False},
    "spadacorta": {"prof": "martial", "hands": "light", "dmg": "1d6", "crit": "19-20/x2", "type": "piercing", "ranged": False},
    "battleaxe": {"prof": "martial", "hands": "one-handed", "dmg": "1d8", "crit": "x3", "type": "slashing", "ranged": False},
    "asciadabattaglia": {"prof": "martial", "hands": "one-handed", "dmg": "1d8", "crit": "x3", "type": "slashing", "ranged": False},
    "flail": {"prof": "martial", "hands": "one-handed", "dmg": "1d8", "crit": "x2", "type": "bludgeoning", "ranged": False},
    "longsword": {"prof": "martial", "hands": "one-handed", "dmg": "1d8", "crit": "19-20/x2", "type": "slashing", "ranged": False},
    "spadalunga": {"prof": "martial", "hands": "one-handed", "dmg": "1d8", "crit": "19-20/x2", "type": "slashing", "ranged": False},
    "heavyflail": {"prof": "martial", "hands": "two-handed", "dmg": "1d10", "crit": "19-20/x2", "type": "bludgeoning", "ranged": False},
    "falchion": {"prof": "martial", "hands": "two-handed", "dmg": "2d4", "crit": "18-20/x2", "type": "slashing", "ranged": False},
    "glaive": {"prof": "martial", "hands": "two-handed", "dmg": "1d10", "crit": "x3", "type": "slashing", "ranged": False, "reach": True},
    "greataxe": {"prof": "martial", "hands": "two-handed", "dmg": "1d12", "crit": "x3", "type": "slashing", "ranged": False},
    "asciabipenne": {"prof": "martial", "hands": "two-handed", "dmg": "1d12", "crit": "x3", "type": "slashing", "ranged": False},
    "greatclub": {"prof": "martial", "hands": "two-handed", "dmg": "1d10", "crit": "x2", "type": "bludgeoning", "ranged": False},
    "greatsword": {"prof": "martial", "hands": "two-handed", "dmg": "2d6", "crit": "19-20/x2", "type": "slashing", "ranged": False},
    "halberd": {"prof": "martial", "hands": "two-handed", "dmg": "1d10", "crit": "x3", "type": "piercing or slashing", "ranged": False, "reach": True},
    "lance": {"prof": "martial", "hands": "two-handed", "dmg": "1d8", "crit": "x3", "type": "piercing", "ranged": False, "reach": True, "special": "deals double damage when used from the back of a charging mount"},
    "lanciadacavalleria": {"prof": "martial", "hands": "two-handed", "dmg": "1d8", "crit": "x3", "type": "piercing", "ranged": False, "reach": True, "special": "deals double damage when used from the back of a charging mount"},
    "lancialunga": {"prof": "martial", "hands": "two-handed", "dmg": "1d8", "crit": "x3", "type": "piercing", "ranged": False, "reach": True},
    "ranseur": {"prof": "martial", "hands": "two-handed", "dmg": "2d4", "crit": "x3", "type": "piercing", "ranged": False, "reach": True},
    "scythe": {"prof": "martial", "hands": "two-handed", "dmg": "2d4", "crit": "x4", "type": "piercing or slashing", "ranged": False},
    "longbow": {"prof": "martial", "hands": "two-handed", "dmg": "1d8", "crit": "x3", "type": "piercing", "ranged": True},
    "arcolungo": {"prof": "martial", "hands": "two-handed", "dmg": "1d8", "crit": "x3", "type": "piercing", "ranged": True},
    "compositelongbow": {"prof": "martial", "hands": "two-handed", "dmg": "1d8", "crit": "x3", "type": "piercing", "ranged": True, "special": "adds Strength bonus to damage up to the listed rating"},
    "shortbow": {"prof": "martial", "hands": "two-handed", "dmg": "1d6", "crit": "x3", "type": "piercing", "ranged": True},
    # exotic
    "bastardsword": {"prof": "exotic", "hands": "one-handed", "dmg": "1d10", "crit": "19-20/x2", "type": "slashing", "ranged": False},
    "dwarvenwaraxe": {"prof": "exotic", "hands": "one-handed", "dmg": "1d10", "crit": "x3", "type": "slashing", "ranged": False},
    "asciananicadaguerra": {"prof": "exotic", "hands": "one-handed", "dmg": "1d10", "crit": "x3", "type": "slashing", "ranged": False},
    "asciadaguerananica": {"prof": "exotic", "hands": "one-handed", "dmg": "1d10", "crit": "x3", "type": "slashing", "ranged": False},
    "asciadaguerrananica": {"prof": "exotic", "hands": "one-handed", "dmg": "1d10", "crit": "x3", "type": "slashing", "ranged": False},
    "whip": {"prof": "exotic", "hands": "one-handed", "dmg": "1d3", "crit": "x2", "type": "slashing", "ranged": False, "reach": True, "special": "trip, disarm; does not threaten squares and deals no damage to armored targets"},
    "frusta": {"prof": "exotic", "hands": "one-handed", "dmg": "1d3", "crit": "x2", "type": "slashing", "ranged": False, "reach": True, "special": "trip, disarm; does not threaten squares and deals no damage to armored targets"},
    "kama": {"prof": "exotic", "hands": "light", "dmg": "1d6", "crit": "x2", "type": "slashing", "ranged": False, "special": "trip, monk"},
    "nunchaku": {"prof": "exotic", "hands": "light", "dmg": "1d6", "crit": "x2", "type": "bludgeoning", "ranged": False, "special": "disarm, monk"},
    "sai": {"prof": "exotic", "hands": "light", "dmg": "1d4", "crit": "x2", "type": "bludgeoning", "ranged": False, "special": "disarm, monk"},
    "handcrossbow": {"prof": "exotic", "hands": "light", "dmg": "1d4", "crit": "19-20/x2", "type": "piercing", "ranged": True},
    "repeatingheavycrossbow": {"prof": "exotic", "hands": "two-handed", "dmg": "1d10", "crit": "19-20/x2", "type": "piercing", "ranged": True, "special": "holds 5 bolts in a magazine"},
    "bolas": {"prof": "exotic", "hands": "light", "dmg": "1d4", "crit": "x2", "type": "bludgeoning", "ranged": True, "special": "trip"},
    "net": {"prof": "exotic", "hands": "two-handed", "dmg": "—", "crit": "—", "type": "—", "ranged": True, "special": "entangle"},
    # firearms (exotic)
    "pistol": {"prof": "exotic", "hands": "one-handed", "dmg": "1d8", "crit": "x4", "type": "piercing", "ranged": True, "firearm": True},
    "musket": {"prof": "exotic", "hands": "two-handed", "dmg": "1d12", "crit": "x4", "type": "piercing", "ranged": True, "firearm": True},
    "musketpesante": {"prof": "exotic", "hands": "two-handed", "dmg": "1d12", "crit": "x4", "type": "piercing", "ranged": True, "firearm": True},
    "duelingpistol": {"prof": "exotic", "hands": "one-handed", "dmg": "1d8", "crit": "x3", "type": "piercing", "ranged": True, "firearm": True},
}

ARMORS: dict[str, dict[str, Any]] = {
    "padded": {"type": "light", "bonus": 1, "maxdex": 8, "pen": 0, "spell": 5, "weight": 10},
    "armaturaleggera": {"type": "light", "bonus": 2, "maxdex": 6, "pen": 0, "spell": 10, "weight": 15},
    "leather": {"type": "light", "bonus": 2, "maxdex": 6, "pen": 0, "spell": 10, "weight": 15},
    "cuoiorinforzato": {"type": "light", "bonus": 2, "maxdex": 6, "pen": 0, "spell": 10, "weight": 15},
    "cuoiotinforzata": {"type": "light", "bonus": 2, "maxdex": 6, "pen": 0, "spell": 10, "weight": 15},
    "cuoiotinforzata": {"type": "light", "bonus": 2, "maxdex": 6, "pen": 0, "spell": 10, "weight": 15},
    "armaturadicuoiorinforzata": {"type": "light", "bonus": 2, "maxdex": 6, "pen": 0, "spell": 10, "weight": 15},
    "studdedleather": {"type": "light", "bonus": 3, "maxdex": 5, "pen": -1, "spell": 15, "weight": 20},
    "cuoioborchiato": {"type": "light", "bonus": 3, "maxdex": 5, "pen": -1, "spell": 15, "weight": 20},
    "chainshirt": {"type": "light", "bonus": 4, "maxdex": 4, "pen": -2, "spell": 20, "weight": 25},
    "giacodimaglia": {"type": "light", "bonus": 4, "maxdex": 4, "pen": -2, "spell": 20, "weight": 25},
    "giacodimaglialeggera": {"type": "light", "bonus": 4, "maxdex": 4, "pen": -2, "spell": 20, "weight": 25},
    "hide": {"type": "medium", "bonus": 4, "maxdex": 4, "pen": -3, "spell": 20, "weight": 25},
    "pellerinforzata": {"type": "medium", "bonus": 4, "maxdex": 4, "pen": -3, "spell": 20, "weight": 25},
    "pellechiodata": {"type": "medium", "bonus": 4, "maxdex": 4, "pen": -3, "spell": 20, "weight": 25},
    "scalemail": {"type": "medium", "bonus": 5, "maxdex": 4, "pen": -4, "spell": 25, "weight": 30},
    "corazzaascaglie": {"type": "medium", "bonus": 5, "maxdex": 4, "pen": -4, "spell": 25, "weight": 30},
    "armaturaascaglie": {"type": "medium", "bonus": 5, "maxdex": 4, "pen": -4, "spell": 25, "weight": 30},
    "chainmail": {"type": "medium", "bonus": 6, "maxdex": 2, "pen": -5, "spell": 30, "weight": 40},
    "cottadimaglia": {"type": "medium", "bonus": 6, "maxdex": 2, "pen": -5, "spell": 30, "weight": 40},
    "cottadimaglialeggerarinforzata": {"type": "medium", "bonus": 6, "maxdex": 2, "pen": -5, "spell": 30, "weight": 40},
    "breastplate": {"type": "medium", "bonus": 6, "maxdex": 3, "pen": -4, "spell": 25, "weight": 30},
    "corazzaapiastre": {"type": "medium", "bonus": 6, "maxdex": 3, "pen": -4, "spell": 25, "weight": 30},
    "corazzadicuoiotemprato": {"type": "medium", "bonus": 6, "maxdex": 3, "pen": -4, "spell": 25, "weight": 30},
    "corazzarinforzata": {"type": "medium", "bonus": 6, "maxdex": 3, "pen": -4, "spell": 25, "weight": 30},
    "armaturalamellare": {"type": "medium", "bonus": 6, "maxdex": 3, "pen": -5, "spell": 25, "weight": 35},
    "corazzalamellare": {"type": "medium", "bonus": 6, "maxdex": 3, "pen": -5, "spell": 25, "weight": 35},
    "splintmail": {"type": "heavy", "bonus": 7, "maxdex": 0, "pen": -7, "spell": 40, "weight": 45},
    "bandedmail": {"type": "heavy", "bonus": 7, "maxdex": 1, "pen": -6, "spell": 35, "weight": 35},
    "halfplate": {"type": "heavy", "bonus": 8, "maxdex": 0, "pen": -7, "spell": 40, "weight": 50},
    "corazzadipiastreleggermenterinforzata": {"type": "heavy", "bonus": 8, "maxdex": 0, "pen": -7, "spell": 40, "weight": 50},
    "fullplate": {"type": "heavy", "bonus": 9, "maxdex": 1, "pen": -6, "spell": 35, "weight": 50},
    "armaturacompleta": {"type": "heavy", "bonus": 9, "maxdex": 1, "pen": -6, "spell": 35, "weight": 50},
    "corazzadiapiastre": {"type": "heavy", "bonus": 9, "maxdex": 1, "pen": -6, "spell": 35, "weight": 50},
    "corazzadipietrascolpita": {"type": "heavy", "bonus": 9, "maxdex": 1, "pen": -6, "spell": 35, "weight": 75},
    "corazzadiseta": {"type": "light", "bonus": 1, "maxdex": 8, "pen": 0, "spell": 0, "weight": 4},
    "armaturavivente": {"type": "medium", "bonus": 5, "maxdex": 3, "pen": -4, "spell": 20, "weight": 25},
}

SHIELDS: dict[str, dict[str, Any]] = {
    "buckler": {"type": "light", "bonus": 1, "pen": -1, "spell": 5, "weight": 5},
    "shieldlightwood": {"type": "light", "bonus": 1, "pen": -1, "spell": 5, "weight": 5},
    "shieldlightsteel": {"type": "light", "bonus": 1, "pen": -1, "spell": 5, "weight": 6},
    "scudoleggeroinlegno": {"type": "light", "bonus": 1, "pen": -1, "spell": 5, "weight": 5},
    "shieldheavywood": {"type": "heavy", "bonus": 2, "pen": -2, "spell": 15, "weight": 10},
    "shieldheavysteel": {"type": "heavy", "bonus": 2, "pen": -2, "spell": 15, "weight": 15},
    "scudopesante": {"type": "heavy", "bonus": 2, "pen": -2, "spell": 15, "weight": 15},
    "scudopesanteinacciaio": {"type": "heavy", "bonus": 2, "pen": -2, "spell": 15, "weight": 15},
    "towermield": {"type": "tower", "bonus": 4, "pen": -10, "spell": 50, "weight": 45},
    "scudotorre": {"type": "tower", "bonus": 4, "pen": -10, "spell": 50, "weight": 45},
}

# Prezzi base stimati per oggetti meravigliosi canonici (gp)
WONDROUS_BASE_PRICE: dict[str, dict[str, Any]] = {
    "amuletofnaturalarmor": {"slot": "neck", "spell": "barkskin", "cl": 5, "aura": "faint transmutation", "bonus_cost": lambda b: b * b * 2000},
    "beltofgiantstrength": {"slot": "belt", "spell": "bull's strength", "cl": 8, "aura": "faint transmutation", "bonus_cost": lambda b: b * b * 4000},
    "beltofdexterity": {"slot": "belt", "spell": "cat's grace", "cl": 8, "aura": "faint transmutation", "bonus_cost": lambda b: b * b * 4000},
    "beltofconstitution": {"slot": "belt", "spell": "bear's endurance", "cl": 8, "aura": "faint transmutation", "bonus_cost": lambda b: b * b * 4000},
    "beltofphysicalmight": {"slot": "belt", "spell": "bull's strength / bear's endurance", "cl": 12, "aura": "moderate transmutation", "bonus_cost": lambda b: b * b * 10000},
    "headbandofvastintelligence": {"slot": "headband", "spell": "fox's cunning", "cl": 8, "aura": "faint transmutation", "bonus_cost": lambda b: b * b * 4000},
    "headbandofalluringcharisma": {"slot": "headband", "spell": "eagle's splendor", "cl": 8, "aura": "faint transmutation", "bonus_cost": lambda b: b * b * 4000},
    "headbandofinspiredwisdom": {"slot": "headband", "spell": "owl's wisdom", "cl": 8, "aura": "faint transmutation", "bonus_cost": lambda b: b * b * 4000},
    "headbandofmentalprowess": {"slot": "headband", "spell": "fox's cunning / eagle's splendor", "cl": 12, "aura": "moderate transmutation", "bonus_cost": lambda b: b * b * 10000},
    "bracersofarmor": {"slot": "wrists", "spell": "mage armor", "cl": 7, "aura": "faint conjuration", "bonus_cost": lambda b: b * b * 1000},
    "cloakofresistance": {"slot": "shoulders", "spell": "resistance", "cl": 5, "aura": "faint abjuration", "bonus_cost": lambda b: b * b * 1000},
    "ringofprotection": {"slot": "ring", "spell": "shield of faith", "cl": 5, "aura": "faint abjuration", "bonus_cost": lambda b: b * b * 2000},
    "glovesofdexterity": {"slot": "hands", "spell": "cat's grace", "cl": 8, "aura": "faint transmutation", "bonus_cost": lambda b: b * b * 4000},
    "bootsofspeed": {"slot": "feet", "spell": "haste", "cl": 10, "aura": "moderate transmutation", "price": 12000},
    "cloakofelvenkind": {"slot": "shoulders", "spell": "pass without trace", "cl": 3, "aura": "faint transmutation", "price": 2500},
    "bagofholding": {"slot": "none", "spell": "secret chest", "cl": 9, "aura": "moderate conjuration", "price": {1: 2500, 2: 5000, 3: 7400, 4: 10000}},
    "handyhaversack": {"slot": "none", "spell": "secret chest", "cl": 9, "aura": "moderate conjuration", "price": 2000},
    "pearlofpower": {"slot": "none", "spell": "—", "cl": None, "aura": "strong conjuration", "price": {1: 1000, 2: 4000, 3: 9000, 4: 16000, 5: 25000, 6: 36000, 7: 49000, 8: 64000, 9: 81000}},
    "ringofevasion": {"slot": "ring", "spell": "jump", "cl": 7, "aura": "moderate transmutation", "price": 25000},
    "ringoffeatherfalling": {"slot": "ring", "spell": "feather fall", "cl": 1, "aura": "faint transmutation", "price": 2200},
    "ringofwizardry": {"slot": "ring", "spell": "limited wish", "cl": 11, "aura": "moderate (no school)", "price": {1: 20000, 2: 40000, 3: 70000, 4: 100000}},
    "ringoftheshootingstar": {"slot": "ring", "spell": "scorching ray", "cl": 10, "aura": "moderate evocation", "price": 42000},
    "robeofarcaneheritage": {"slot": "body", "spell": "—", "cl": 9, "aura": "moderate transmutation", "price": 16000},
    "vigilantemask": {"slot": "head", "spell": "disguise self", "cl": 3, "aura": "faint illusion", "price": 5000},
}


# ---------------------------------------------------------------------------
# Generatori di descrizione
# ---------------------------------------------------------------------------
def _weapon_description(name: str, key: str, bonus: int | None = None, special_terms: list[str] | None = None) -> str:
    w = WEAPONS[key]
    prof = w["prof"]
    hands = w["hands"]
    dmg = w["dmg"]
    crit = w["crit"]
    dmg_type = w["type"]
    ranged = w.get("ranged", False)
    firearm = w.get("firearm", False)
    reach = w.get("reach", False)
    double = w.get("double", False)
    special = w.get("special", "")
    terms = special_terms or []
    parts = ["Italiano:"]
    parts.append(f"{name} è un'arma {prof} {'a distanza' if ranged else 'da mischia'}, {hands}.")
    if bonus:
        parts.append(f"Ha un bonus di miglioramento +{bonus} ai tiri per colpire e ai danni.")
    parts.append(f"Danno base: {dmg}; critico {crit}; tipo di danno: {dmg_type}.")
    if reach:
        parts.append("Ha reach.")
    if double:
        parts.append("È un'arma double.")
    if firearm:
        parts.append("È un'arma da fuoco; utilizza munizioni e polvere nera, minaccia su 20/x4 e ha malfunzioni possibili.")
    if special:
        parts.append(f"Speciale: {special}.")
    if terms:
        parts.append(f"Proprietà aggiuntive indicate dal nome: {', '.join(terms)}.")
    parts.append("Requisiti: proficiency appropriata.")
    return " ".join(parts)


def _armor_description(name: str, key: str, bonus: int | None = None, special_terms: list[str] | None = None) -> str:
    a = ARMORS[key]
    parts = ["Italiano:"]
    parts.append(f"{name} è un'armatura {a['type']}.")
    total_bonus = (a["bonus"] + bonus) if bonus else a["bonus"]
    parts.append(f"Bonus totale all'armatura: +{total_bonus}.")
    parts.append(f"Max Dex: {a['maxdex']}; penalità armatura: {a['pen']}; fallimento incantesimi: {a['spell']}%; peso: {a['weight']} lb.")
    terms = special_terms or []
    if "mithral" in terms or "mithral" in normalize_name(name):
        parts.append("In mithral: tratttata come un grado di armatura più leggero, +2 Max Dex, riduzione penalità di 3, riduzione fallimento incantesimi di 10%, metà peso.")
    if "adamantina" in terms or "adamantina" in normalize_name(name) or "adamantio" in normalize_name(name):
        parts.append("In adamantina: fornisce damage reduction 3/— se pesante, 1/— se leggera, 2/— se media.")
    if terms:
        parts.append(f"Proprietà aggiuntive indicate dal nome: {', '.join(terms)}.")
    return " ".join(parts)


def _shield_description(name: str, key: str, bonus: int | None = None, special_terms: list[str] | None = None) -> str:
    s = SHIELDS[key]
    total_bonus = (s["bonus"] + bonus) if bonus else s["bonus"]
    parts = ["Italiano:"]
    parts.append(f"{name} è uno scudo {s['type']}.")
    parts.append(f"Bonus allo scudo: +{total_bonus}; penalità armatura: {s['pen']}; fallimento incantesimi: {s['spell']}%; peso: {s['weight']} lb.")
    if "bashing" in (special_terms or []):
        parts.append("Proprietà bashing: gli attacchi di shield bash contano come se lo scudo fosse di due taglie superiori.")
    if special_terms:
        parts.append(f"Proprietà aggiuntive indicate dal nome: {', '.join(special_terms)}.")
    return " ".join(parts)


def _wondrous_bonus_description(name: str, family: str, bonus: int | None, ability: str | None = None, extra: str = "") -> str:
    base = WONDROUS_BASE_PRICE.get(family)
    if not base:
        return ""
    slot = base.get("slot", "none")
    spell = base.get("spell", "—")
    cl = base.get("cl")
    aura = base.get("aura", "")
    if bonus is not None and "bonus_cost" in base:
        price = base["bonus_cost"](bonus)
    else:
        price = base.get("price", 0)
        if isinstance(price, dict):
            price = price.get(bonus, 0) if bonus else 0
    parts = ["Italiano:"]
    if ability:
        parts.append(f"{name} è un oggetto meraviglioso da indossare ({slot}) che conferisce un bonus di miglioramento +{bonus} al punteggio di {ability}.")
    else:
        parts.append(f"{name} è un oggetto meraviglioso da indossare ({slot}).")
    if cl:
        parts.append(f"Aura {aura}; CL {cl}th; Slot {slot}; Price {price} gp.")
    else:
        parts.append(f"Aura {aura}; Slot {slot}; Price {price} gp.")
    if spell and spell != "—":
        parts.append(f"Construction Requirements: Craft Wondrous Item, {spell}.")
    else:
        parts.append("Construction Requirements: Craft Wondrous Item.")
    if extra:
        parts.append(extra)
    return " ".join(parts)


def _consumable_spell_description(name: str, item_type: str, spell: str, level: int, cl: int | None = None, quantity: int | None = None, charges: int | None = None) -> str:
    cl = cl or (level * 2 - 1)
    parts = ["Italiano:"]
    if item_type == "potion":
        parts.append(f"{name} è una pozione che lancia {spell} come incantesimo di livello {level} (CL {cl}).")
        parts.append(f"L'effetto dura 1 round x CL o come indicato dalla descrizione dell'incantesimo; può essere bevuta come azione standard.")
    elif item_type == "scroll":
        parts.append(f"{name} è una pergamena che lancia {spell} come incantesimo di livello {level} (CL {cl}).")
        parts.append(f"Richiede Decipher Script DC 20 + livello incantesimo e uso della lista incantesimi appropriata per attivarla.")
    elif item_type == "wand":
        parts.append(f"{name} è una bacchetta che lancia {spell} come incantesimo di livello {level} (CL {cl}).")
        parts.append(f"Richiede Uso Congegni Magici per attivare; ogni uso consuma 1 carica.")
    else:
        parts.append(f"{name} è un consumabile che duplica l'effetto di {spell} (livello {level}, CL {cl}).")
    if quantity:
        parts.append(f"Quantità inclusa: {quantity}.")
    if charges:
        parts.append(f"Cariche: {charges}.")
    return " ".join(parts)


def _gear_description(name: str, category: str, effect: str = "") -> str:
    parts = ["Italiano:"]
    parts.append(f"{name} è equipaggiamento non magico di categoria {category}.")
    if effect:
        parts.append(effect)
    return " ".join(parts)


def _generic_wondrous(name: str, slot: str, effect: str) -> str:
    return f"Italiano: {name} è un oggetto meraviglioso da indossare ({slot}). {effect}"


def _make_prereq_arms_armor(bonus: int | None, special: str | None = None) -> list[str]:
    if bonus:
        if special:
            return ["Craft Magic Arms and Armor", special]
        return ["Craft Magic Arms and Armor", f"caster level {bonus * 3}rd"]
    return []


def _make_prereq_wondrous(family: str, spell: str | None = None) -> list[str]:
    base = WONDROUS_BASE_PRICE.get(family, {})
    sp = spell or base.get("spell", "")
    if sp and sp != "—":
        return ["Craft Wondrous Item", sp]
    return ["Craft Wondrous Item"]


# ---------------------------------------------------------------------------
# Template esatti per nomi che non rientrano nei pattern generici
# ---------------------------------------------------------------------------
def _exact_template(name: str) -> dict[str, Any] | None:
    key = normalize_name(name)

    # Borse extradimensionali
    if "bagofholding" in key:
        m = re.search(r"type\s*([IV]+|[1234])", name, flags=re.IGNORECASE)
        raw = m.group(1).upper() if m else "I"
        size_map = {"I": 1, "II": 2, "III": 3, "IV": 4, "1": 1, "2": 2, "3": 3, "4": 4}
        size = size_map.get(raw, 1)
        price = WONDROUS_BASE_PRICE["bagofholding"]["price"].get(size, 2500)
        return {
            "description": f"Italiano: {name} è un oggetto meraviglioso extradimensionale. Ha {size} volte la capacità di una normale borsa da viaggio e può contenere un determinato peso/volume senza aumentare il proprio peso; gli oggetti rimangono accessibili come azione di movimento. Aura moderate conjuration; CL 9th; Slot none; Price {price} gp; Weight 15 lb. Construction Requirements: Craft Wondrous Item, secret chest.",
            "prerequisites": ["Craft Wondrous Item", "secret chest"],
            "tags": ["wondrous", "container", "extradimensional", "slot:none"],
            "source": "Pathfinder Core Rulebook",
            "source_id": "CRB",
        }

    if key == "handyhaversack":
        return {
            "description": "Italiano: Handy Haversack è una sacca extradimensionale con due scomparti laterali. Ogni scomparto può contenere fino a un certo volume/peso; oggetti richiesti vengono in cima come azione di movimento. Aura moderate conjuration; CL 9th; Slot none; Price 2,000 gp; Weight 5 lb. Construction Requirements: Craft Wondrous Item, secret chest.",
            "prerequisites": ["Craft Wondrous Item", "secret chest"],
            "tags": ["wondrous", "utility", "container", "slot:none"],
            "source": "Pathfinder Core Rulebook",
            "source_id": "CRB",
        }

    # Pozioni
    if key in ("potionofcurelightwounds", "pozionedicura"):
        return {
            "description": "Italiano: Pozione di cura ferite leggere. Consumabile che lancia cure light wounds (livello 1, CL 1): cura 1d8+1 punti ferita. Attivazione: azione standard per bere.",
            "tags": ["consumable", "healing", "potion"],
            "source": "Pathfinder Core Rulebook",
            "source_id": "CRB",
        }
    if key in ("potionofinvisibility", "pozionedinvisibilita"):
        return {
            "description": "Italiano: Pozione di invisibilità. Consumabile che lancia invisibility (livello 2, CL 3): il bevitore diventa invisibile per 3 minuti o finché non attacca/lancia un incantesimo.",
            "tags": ["consumable", "potion"],
            "source": "Pathfinder Core Rulebook",
            "source_id": "CRB",
        }
    if key in ("pozionedicuramoderata", "pozionedicuramoderate"):
        return {
            "description": "Italiano: Pozione di cura ferite moderate. Consumabile che lancia cure moderate wounds (livello 2, CL 3): cura 2d8+3 punti ferita.",
            "tags": ["consumable", "healing", "potion"],
            "source": "Pathfinder Core Rulebook",
            "source_id": "CRB",
        }

    # Bacchette
    if "bacchettadicuraferiteleggere" in key:
        return {
            "description": "Italiano: Bacchetta di cura ferite leggere. Lancia cure light wounds (livello 1, CL 1) come azione standard. Richiede Uso Congegni Magici. Cariche: 20.",
            "prerequisites": ["Craft Wand", "cure light wounds"],
            "tags": ["consumable", "wand", "healing"],
            "source": "Pathfinder Core Rulebook",
            "source_id": "CRB",
        }
    if "bacchettadiinvocarealleatonaturaleii" in key:
        return {
            "description": "Italiano: Bacchetta di invocare alleato naturale II. Lancia summon nature's ally II (livello 2, CL 3). Richiede Uso Congegni Magici. Cariche: 15.",
            "prerequisites": ["Craft Wand", "summon nature's ally II"],
            "tags": ["consumable", "wand", "summon"],
            "source": "Pathfinder Core Rulebook",
            "source_id": "CRB",
        }

    # Wand inglesi
    if key == "wandofcurelightwoundscl1":
        return {
            "description": "Italiano: Bacchetta di cura ferite leggere (CL 1). Lancia cure light wounds (livello 1, CL 1). Richiede Uso Congegni Magici. Cariche: 50.",
            "prerequisites": ["Craft Wand", "cure light wounds"],
            "tags": ["consumable", "wand", "healing"],
            "source": "Pathfinder Core Rulebook",
            "source_id": "CRB",
        }
    if key == "wandofmagicmissilecl3":
        return {
            "description": "Italiano: Bacchetta di magic missile (CL 3). Lancia magic missile (livello 1, CL 3): 2 dardi, 1d4+1 ciascuno. Richiede Uso Congegni Magici. Cariche: 50.",
            "prerequisites": ["Craft Wand", "magic missile"],
            "tags": ["consumable", "wand", "force"],
            "source": "Pathfinder Core Rulebook",
            "source_id": "CRB",
        }
    if key == "wandofshieldcl1":
        return {
            "description": "Italiano: Bacchetta di shield (CL 1). Lancia shield (livello 1, CL 1): +4 shield bonus alla CA, immunità a magic missile per 1 minuto. Richiede Uso Congegni Magici. Cariche: 50.",
            "prerequisites": ["Craft Wand", "shield"],
            "tags": ["consumable", "wand", "defense"],
            "source": "Pathfinder Core Rulebook",
            "source_id": "CRB",
        }

    # Pergamene
    if key == "scrolloffireball":
        return {
            "description": "Italiano: Pergamena di fireball (livello 3, CL 5). Lancia fireball: 20-ft. radius spread, 5d6 fire damage, Reflex half. Richiede Decipher Script e la lista incantesimi appropriata.",
            "prerequisites": ["Craft Scroll", "fireball"],
            "tags": ["consumable", "scroll", "arcane", "fire"],
            "source": "Pathfinder Core Rulebook",
            "source_id": "CRB",
        }
    if "pergamenadilitanyofdefense" in key or "pergamenadilitany" in key:
        return {
            "description": "Italiano: Pergamena di Litany of Defense (livello 1, CL 1). Come azione swift conferisce +2 sacred bonus alla CA fino all'inizio del prossimo turno.",
            "prerequisites": ["Craft Scroll", "Litany of Defense"],
            "tags": ["consumable", "scroll", "divine", "defense"],
            "source": "Pathfinder Ultimate Combat",
            "source_id": "UC",
        }

    # Perle del potere
    m = re.search(r"pearl of power\s*\(?([0-9]+)(?:th|rd|nd|st)?\)?", name, flags=re.IGNORECASE)
    if m or "pearlofpower" in key:
        level = int(m.group(1)) if m else 1
        price = WONDROUS_BASE_PRICE["pearlofpower"]["price"].get(level, level * level * 1000)
        return {
            "description": f"Italiano: Pearl of Power ({level}th). Consente al possessore di recuperare un incantesimo preparato o slot incantesimo di livello {level} già lanciato, una volta al giorno. Aura strong conjuration; CL 17th; Slot none; Price {price} gp; Weight —. Construction Requirements: Craft Wondrous Item, creator must be able to cast spells of the level to be recalled.",
            "prerequisites": ["Craft Wondrous Item", "creator must be able to cast spells of the level to be recalled"],
            "tags": ["wondrous", "slot:none", "spell-recovery"],
            "source": "Pathfinder Core Rulebook",
            "source_id": "CRB",
        }

    # Oggetti meravigliosi speciali
    if key == "bootsofspeed":
        return {
            "description": "Italiano: Boots of Speed. Come azione standard, conferisce haste per 10 round al giorno (non necessariamente consecutivi). +1 ai tiri per colpire, +1 CA, +1 Reflex, +30 ft. move speed, un attacco extra in full-attack. Aura moderate transmutation; CL 10th; Slot feet; Price 12,000 gp; Weight 1 lb. Construction Requirements: Craft Wondrous Item, haste.",
            "prerequisites": ["Craft Wondrous Item", "haste"],
            "tags": ["wondrous", "slot:feet", "mobility"],
            "source": "Pathfinder Core Rulebook",
            "source_id": "CRB",
        }
    if key == "cloakofelvenkind":
        return {
            "description": "Italiano: Cloak of Elvenkind. Mantello che conferisce +5 competence bonus a Stealth. Aura faint transmutation; CL 3rd; Slot shoulders; Price 2,500 gp; Weight 1 lb. Construction Requirements: Craft Wondrous Item, pass without trace.",
            "prerequisites": ["Craft Wondrous Item", "pass without trace"],
            "tags": ["wondrous", "slot:shoulders", "stealth"],
            "source": "Pathfinder Core Rulebook",
            "source_id": "CRB",
        }
    if key == "bracersoffalconsaim":
        return {
            "description": "Italiano: Bracers of Falcon's Aim. Bracciali che conferiscono +1 competence bonus ai tiri per colpire a distanza e il beneficio del talento Improved Critical con armi a distanza da tiro (solo per i tiri, non si cumula). Aura faint transmutation; CL 3rd; Slot wrists; Price 4,000 gp; Weight 1 lb. Construction Requirements: Craft Wondrous Item, hunter's eye.",
            "prerequisites": ["Craft Wondrous Item", "hunter's eye"],
            "tags": ["wondrous", "slot:wrist", "ranged", "damage:piercing", "class:ranger", "class:hunter"],
            "source": "Pathfinder Ultimate Equipment",
            "source_id": "UE",
        }
    if key == "beltofphysicalmight2strcon":
        return {
            "description": "Italiano: Belt of Physical Might +2 (Str/Con). Cintura che conferisce +2 enhancement bonus a Strength e Constitution. Trattare come bonus temporaneo per le prime 24 ore. Aura moderate transmutation; CL 12th; Slot belt; Price 10,000 gp; Weight 1 lb. Construction Requirements: Craft Wondrous Item, bull's strength, bear's endurance.",
            "prerequisites": ["Craft Wondrous Item", "bull's strength", "bear's endurance"],
            "tags": ["wondrous", "slot:belt", "enhancement"],
            "source": "Pathfinder Ultimate Equipment",
            "source_id": "UE",
        }
    if key == "headbandofmentalprowess2intcha":
        return {
            "description": "Italiano: Headband of Mental Prowess +2 (Int/Cha). Fascia che conferisce +2 enhancement bonus a Intelligence e Charisma. Trattare come bonus temporaneo per le prime 24 ore. Una skill associata per ogni +2 bonus riceve rank pari ai HD. Aura moderate transmutation; CL 12th; Slot headband; Price 10,000 gp; Weight 1 lb. Construction Requirements: Craft Wondrous Item, fox's cunning, eagle's splendor.",
            "prerequisites": ["Craft Wondrous Item", "fox's cunning", "eagle's splendor"],
            "tags": ["wondrous", "slot:headband", "enhancement"],
            "source": "Pathfinder Ultimate Equipment",
            "source_id": "UE",
        }
    if key == "robeofarcaneheritage":
        return {
            "description": "Italiano: Robe of Arcane Heritage. Veste che aumenta di 4 livelli effettivi il sorcerer bloodline class feature per determinare i bloodline powers, ma non per gli spells known. Aura moderate transmutation; CL 9th; Slot body; Price 16,000 gp; Weight 1 lb. Construction Requirements: Craft Wondrous Item, sorcerer bloodline class feature, caster level 8th.",
            "prerequisites": ["Craft Wondrous Item", "sorcerer bloodline class feature", "caster level 8th"],
            "tags": ["wondrous", "slot:body", "class:sorcerer"],
            "source": "Pathfinder Core Rulebook",
            "source_id": "CRB",
        }
    if key == "vigilantemask":
        return {
            "description": "Italiano: Vigilante Mask. Maschera che conferisce +5 competence bonus a Disguise e permette di cambiare aspetto come disguise self (come azione standard) un numero di volte al giorno pari al bonus di Charisma (min 1). Aura faint illusion; CL 3rd; Slot head; Price 5,000 gp; Weight 1 lb. Construction Requirements: Craft Wondrous Item, disguise self.",
            "prerequisites": ["Craft Wondrous Item", "disguise self"],
            "tags": ["wondrous", "slot:head", "class:vigilante"],
            "source": "Pathfinder Ultimate Intrigue",
            "source_id": "UI",
        }
    if key == "ringofevasion":
        return {
            "description": "Italiano: Ring of Evasion. Anello che permette di usare evasion come class feature (se un attacco consente Reflex per dimezzare, su successo non subisce danno). Richiede la capacità di indossare un anello. Aura moderate transmutation; CL 7th; Slot ring; Price 25,000 gp. Construction Requirements: Forge Ring, evasion class feature.",
            "prerequisites": ["Forge Ring", "evasion class feature"],
            "tags": ["ring", "slot:ring", "defense"],
            "source": "Pathfinder Core Rulebook",
            "source_id": "CRB",
        }
    if key == "ringoffeatherfalling":
        return {
            "description": "Italiano: Ring of Feather Falling. Anello che attiva automaticamente feather fall quando il portatore sta per cadere da altezza pericolosa. Aura faint transmutation; CL 1st; Slot ring; Price 2,200 gp. Construction Requirements: Forge Ring, feather fall.",
            "prerequisites": ["Forge Ring", "feather fall"],
            "tags": ["ring", "slot:ring", "protection"],
            "source": "Pathfinder Core Rulebook",
            "source_id": "CRB",
        }
    if key == "ringoftheshootingstar":
        return {
            "description": "Italiano: Ring of the Shooting Star. Anello che permette di lanciare scorching ray (3 raggi, 4d6 ciascuno) 3 volte al giorno. Aura moderate evocation; CL 10th; Slot ring; Price 42,000 gp. Construction Requirements: Forge Ring, scorching ray.",
            "prerequisites": ["Forge Ring", "scorching ray"],
            "tags": ["ring", "slot:ring", "damage:fire", "ranged"],
            "source": "Pathfinder Ultimate Equipment",
            "source_id": "UE",
        }
    if key == "ringofwizardryi":
        return {
            "description": "Italiano: Ring of Wizardry I. Anello che raddoppia gli slot incantesimo di 1° livello preparabili/memorizzabili dal portatore (solo arcane). Aura moderate (no school); CL 11th; Slot ring; Price 20,000 gp. Construction Requirements: Forge Ring, limited wish.",
            "prerequisites": ["Forge Ring", "limited wish"],
            "tags": ["ring", "slot:ring", "spellcasting"],
            "source": "Pathfinder Core Rulebook",
            "source_id": "CRB",
        }

    # Gear / kit
    if key in ("kitavventuriero", "kittendaavventuriero", "kitdavventuriero", "adventurerskit"):
        return {
            "description": "Italiano: Kit da avventuriero. Contiene l'equipaggiamento base per un'avventura: zaino, sacco a pelo, razioni, corda, torce, acciarino e altri oggetti utili. Fornisce i tool necessari per viaggiare ed esplorare.",
            "tags": ["gear", "kit", "equipment", "nonmagical"],
            "source": "Pathfinder Core Rulebook",
            "source_id": "CRB",
        }
    if key in ("strumentidascasso", "thievestools"):
        return {
            "description": "Italiano: Strumenti da scasso. Kit di lockpicks e attrezzi per Disable Device. Senza di essi si subisce -2 alle prove; la versione masterwork (o di qualità) conferisce +2 competence bonus.",
            "tags": ["gear", "tool", "equipment", "nonmagical"],
            "source": "Pathfinder Core Rulebook",
            "source_id": "CRB",
        }
    if "attrezzidascassodiqualita" in key or "masterworkthievestools" in key:
        return {
            "description": "Italiano: Attrezzi da scasso di qualità (masterwork thieves' tools). Kit superiore che conferisce +2 competence bonus alle prove di Disable Device. Peso 2 lb.",
            "tags": ["gear", "tool", "equipment", "nonmagical"],
            "source": "Pathfinder Core Rulebook",
            "source_id": "CRB",
        }
    if key == "borsadimonete":
        return {
            "description": "Italiano: Borsa di monete (belt pouch). Piccolo contenitore da cintura per monete e piccoli oggetti. Peso ½ lb (vuota).",
            "tags": ["gear", "container", "equipment", "nonmagical"],
            "source": "Pathfinder Core Rulebook",
            "source_id": "CRB",
        }
    if key == "starterkit":
        return {
            "description": "Italiano: Starter kit. Equipaggiamento base per un personaggio di 1° livello: abiti, zaino, corda, razioni, torce e oggetti comuni.",
            "tags": ["gear", "starter", "equipment", "nonmagical"],
            "source": "Pathfinder Core Rulebook",
            "source_id": "CRB",
        }
    if key in ("cordadiseta", "silkrope"):
        return {
            "description": "Italiano: Corda di seta. Corda leggera e resistente, 50 ft. Supporta fino a 200 lb (o di più a seconda del tipo).",
            "tags": ["gear", "equipment", "nonmagical"],
            "source": "Pathfinder Core Rulebook",
            "source_id": "CRB",
        }
    if key == "tanglefootbag":
        return {
            "description": "Italiano: Tanglefoot Bag. Sacca alchemica che, lanciata con un ranged touch attack, esplode in una sostanza appiccicosa. La creatura colpita subisce -2 agli attacchi e alle prove di Destrezza, -10 ft. alla velocità (o è immobilizzata su fallimento Reflex DC 15). Durata 2d4 round.",
            "tags": ["alchemical", "grenade", "consumable"],
            "source": "Pathfinder Core Rulebook",
            "source_id": "CRB",
        }
    if key == "fiaschettediantitoxinsuperiore" or "antitoxin" in key:
        return {
            "description": "Italiano: Antitoxin superiore. Liquido alchemico che, bevuto, conferisce +5 alchemical bonus ai tiri salvezza contro veleno per 1 ora.",
            "tags": ["alchemical", "consumable", "defense"],
            "source": "Pathfinder Core Rulebook",
            "source_id": "CRB",
        }
    if key == "razionix5" or "razioni" in key:
        return {
            "description": "Italiano: Razioni per viaggio. Cibo essiccato sufficiente per 5 giorni/persona.",
            "tags": ["gear", "equipment", "nonmagical"],
            "source": "Pathfinder Core Rulebook",
            "source_id": "CRB",
        }
    if key == "componentiarcane":
        return {
            "description": "Italiano: Componenti arcane. Borsa con materiali comuni necessari per lanciare incantesimi con componenti materiali non costose.",
            "tags": ["gear", "spellcasting", "equipment", "nonmagical"],
            "source": "Pathfinder Core Rulebook",
            "source_id": "CRB",
        }
    if key == "simbolosacro":
        return {
            "description": "Italiano: Simbolo sacro. Focus divino in legno o metallo utilizzato dai chierici e da altri lanciatori divini per incantesimi che richiedono divine focus.",
            "tags": ["gear", "spellcasting", "equipment", "nonmagical"],
            "source": "Pathfinder Core Rulebook",
            "source_id": "CRB",
        }

    # Armi base non coperte dai pattern numerici
    if key in WEAPONS:
        return {
            "description": _weapon_description(name, key),
            "tags": ["weapon", WEAPONS[key]["prof"], "melee" if not WEAPONS[key].get("ranged") else "ranged"],
            "source": "Pathfinder Core Rulebook",
            "source_id": "CRB",
        }

    # Armature base
    if key in ARMORS:
        return {
            "description": _armor_description(name, key),
            "tags": ["armor", ARMORS[key]["type"]],
            "source": "Pathfinder Core Rulebook",
            "source_id": "CRB",
        }

    # Scudi base
    if key in SHIELDS:
        return {
            "description": _shield_description(name, key),
            "tags": ["armor", "shield", SHIELDS[key]["type"]],
            "source": "Pathfinder Core Rulebook",
            "source_id": "CRB",
        }

    return None


# ---------------------------------------------------------------------------
# Pattern matching per varianti numeriche e termini speciali
# ---------------------------------------------------------------------------
SPECIAL_TERMS = {
    "mithral": ["mithral", "mithril"],
    "adamantina": ["adamantina", "adamantine", "adamantio"],
    "silver": ["silver", "argento"],
    "cold iron": ["cold iron", "ferro freddo"],
    "masterwork": ["masterwork", "maestro", "di qualità", "di qualita"],
    "lucidato": ["lucidato"],
    "potenziato": ["potenziato"],
    "benedetto": ["benedetto", "benedetta"],
    "sacro": ["sacro", "sacra", "sacred"],
    "flaming": ["flaming"],
    "frost": ["frost", "gelida", "gelido"],
    "shock": ["shock", "elettrica"],
    "holy": ["holy", "sacra", "sacro"],
    "unholy": ["unholy"],
    "keen": ["keen", "tagliente"],
    "agile": ["agile"],
    "speed": ["speed", "velocità", "velocita"],
    "cruel": ["cruel", "crudele"],
    "furious": ["furious", "furioso"],
    "bilanciato": ["bilanciato", "bilanciata", "balanced"],
    "critico": ["critico"],
    "ombra": ["ombra", "ombreggiato", "ombreggiata", "shadow"],
    "bashing": ["bashing"],
    "alata": ["alata", "alato"],
    "volante": ["volante", "flying"],
    "aerodinamico": ["aerodinamiche", "aerodinamico"],
    "alare": ["alare", "harness"],
    "botanico": ["botaniche", "botanico"],
    "spine": ["spine"],
    "rune": ["rune"],
    "linfa": ["linfa"],
    "luce lunare": ["luce lunare", "moonlight"],
    "psichico": ["psichico", "psichica"],
    "rituale": ["rituale"],
    "luna": ["lunare", "luna", "lunato"],
    "fuoco": ["fuoco", "fiamme", "fiammeggiante"],
}


def _extract_special_terms(name: str) -> list[str]:
    lowered = name.lower()
    found = []
    for canonical, variants in SPECIAL_TERMS.items():
        for v in variants:
            if v.lower() in lowered:
                found.append(canonical)
                break
    return found


def _match_weapon_variant(name: str, key: str) -> dict[str, Any] | None:
    for wkey in sorted(WEAPONS.keys(), key=len, reverse=True):
        idx = key.find(wkey)
        if idx == -1:
            continue
        bonus = extract_bonus(name)
        terms = _extract_special_terms(name)
        return {
            "description": _weapon_description(name, wkey, bonus, terms),
            "prerequisites": _make_prereq_arms_armor(bonus, None),
            "tags": ["weapon", WEAPONS[wkey]["prof"], "melee" if not WEAPONS[wkey].get("ranged") else "ranged"],
            "source": "Pathfinder Core Rulebook",
            "source_id": "CRB",
        }
    return None


def _match_armor_variant(name: str, key: str) -> dict[str, Any] | None:
    for akey in sorted(ARMORS.keys(), key=len, reverse=True):
        idx = key.find(akey)
        if idx == -1:
            continue
        bonus = extract_bonus(name)
        terms = _extract_special_terms(name)
        return {
            "description": _armor_description(name, akey, bonus, terms),
            "prerequisites": _make_prereq_arms_armor(bonus, None),
            "tags": ["armor", ARMORS[akey]["type"]],
            "source": "Pathfinder Core Rulebook",
            "source_id": "CRB",
        }
    return None


def _match_shield_variant(name: str, key: str) -> dict[str, Any] | None:
    for skey in sorted(SHIELDS.keys(), key=len, reverse=True):
        idx = key.find(skey)
        if idx == -1:
            continue
        bonus = extract_bonus(name)
        terms = _extract_special_terms(name)
        return {
            "description": _shield_description(name, skey, bonus, terms),
            "prerequisites": _make_prereq_arms_armor(bonus, "bashing" if "bashing" in terms else None),
            "tags": ["armor", "shield", SHIELDS[skey]["type"]],
            "source": "Pathfinder Core Rulebook",
            "source_id": "CRB",
        }
    return None


WONDROUS_FAMILIES: dict[str, dict[str, Any]] = {
    "amuletofnaturalarmor": {
        "names": ["amuletodellarmaturanaturale", "amuletodellanaturalearmatura", "amuletofnaturalarmor"],
        "ability": None,
        "extra": "",
    },
    "ringofprotection": {
        "names": ["anellodiprotezione", "ringofprotection"],
        "ability": None,
        "extra": "Conferisce un bonus di deviazione +{bonus} alla CA.",
    },
    "beltofgiantstrength": {
        "names": ["cinturadelgigante", "beltofgiantstrength"],
        "ability": "Forza",
    },
    "beltofdexterity": {
        "names": ["cinturadellagilita", "cinturadelladestrezza", "beltofdexterity"],
        "ability": "Destrezza",
    },
    "beltofconstitution": {
        "names": ["cinturadellacostituzione", "beltofconstitution"],
        "ability": "Costituzione",
    },
    "headbandofvastintelligence": {
        "names": ["headbandofvastintelligence"],
        "ability": "Intelligenza",
        "extra": "Una skill associata per ogni +2 bonus riceve rank pari ai HD del portatore.",
    },
    "headbandofalluringcharisma": {
        "names": ["headbandofalluringcharisma"],
        "ability": "Carisma",
    },
    "headbandofinspiredwisdom": {
        "names": ["headbandofinspiredwisdom"],
        "ability": "Saggezza",
    },
    "bracersofarmor": {
        "names": ["braccialidellarmatura", "bracersofarmor"],
        "ability": None,
        "extra": "Conferisce un bonus di armatura +{bonus} alla CA.",
    },
    "cloakofresistance": {
        "names": ["mantellodellaresistenza", "mantellodiresistenza", "mantelloresistente", "cloakofresistance"],
        "ability": None,
        "extra": "Conferisce un bonus di resistenza +{bonus} a tutti i tiri salvezza.",
    },
    "glovesofdexterity": {
        "names": ["guantidelladestrezza", "glovesofdexterity"],
        "ability": "Destrezza",
    },
}


def _match_wondrous_family(name: str, key: str) -> dict[str, Any] | None:
    for family, info in WONDROUS_FAMILIES.items():
        for n in info["names"]:
            if key.startswith(n):
                bonus = extract_bonus(name)
                if bonus is None:
                    # Se non c'è bonus ma il nome implica un bonus (es. +1 omesso?), prova default 1
                    bonus = 1
                ability = info.get("ability")
                extra = info.get("extra", "").format(bonus=bonus) if info.get("extra") else ""
                return {
                    "description": _wondrous_bonus_description(name, family, bonus, ability, extra),
                    "prerequisites": _make_prereq_wondrous(family),
                    "tags": ["wondrous", f"slot:{WONDROUS_BASE_PRICE[family].get('slot', 'none')}", "enhancement"],
                    "source": "Pathfinder Core Rulebook",
                    "source_id": "CRB",
                }
    return None


# Mapping incantesimi comuni per consumabili
SPELLS_LOOKUP: dict[str, dict[str, Any]] = {
    "cura ferite leggere": {"spell": "cure light wounds", "level": 1, "cl": 1},
    "cura ferite moderate": {"spell": "cure moderate wounds", "level": 2, "cl": 3},
    "cura": {"spell": "cure light wounds", "level": 1, "cl": 1},
    "invisibilità": {"spell": "invisibility", "level": 2, "cl": 3},
    "invisibility": {"spell": "invisibility", "level": 2, "cl": 3},
    "protezione dal male": {"spell": "protection from evil", "level": 1, "cl": 1},
    "protezione": {"spell": "protection from evil", "level": 1, "cl": 1},
    "shield": {"spell": "shield", "level": 1, "cl": 1},
    "magic missile": {"spell": "magic missile", "level": 1, "cl": 1},
    "fireball": {"spell": "fireball", "level": 3, "cl": 5},
    "bless": {"spell": "bless", "level": 1, "cl": 1},
    "benedizione": {"spell": "bless", "level": 1, "cl": 1},
    "invocare alleato naturale i": {"spell": "summon nature's ally I", "level": 1, "cl": 1},
    "invocare alleato naturale ii": {"spell": "summon nature's ally II", "level": 2, "cl": 3},
    "summon nature's ally ii": {"spell": "summon nature's ally II", "level": 2, "cl": 3},
}


def _match_consumable(name: str, key: str) -> dict[str, Any] | None:
    lowered = name.lower()
    item_type = None
    if lowered.startswith("pozione di ") or lowered.startswith("potion of "):
        item_type = "potion"
        rest = re.sub(r"^(pozione di |potion of )", "", lowered, flags=re.IGNORECASE)
    elif lowered.startswith("bacchetta di ") or lowered.startswith("wand of "):
        item_type = "wand"
        rest = re.sub(r"^(bacchetta di |wand of )", "", lowered, flags=re.IGNORECASE)
    elif lowered.startswith("pergamena di ") or lowered.startswith("scroll of "):
        item_type = "scroll"
        rest = re.sub(r"^(pergamena di |scroll of )", "", lowered, flags=re.IGNORECASE)
    else:
        return None

    # pulisci rest
    rest = rest.strip().rstrip(".")
    # rimuovi cl
    m = re.search(r"\(?\s*cl\s*(\d+)\s*\)?", rest, flags=re.IGNORECASE)
    cl = int(m.group(1)) if m else None
    rest = re.sub(r"\(?\s*cl\s*\d+\s*\)?", "", rest, flags=re.IGNORECASE).strip()

    # cerca match incantesimo
    rest_norm = normalize_name(rest)
    matched = None
    for spell_key, info in sorted(SPELLS_LOOKUP.items(), key=lambda x: -len(x[0])):
        if spell_key in rest or spell_key in rest_norm or rest.startswith(spell_key):
            matched = info
            break
    if matched:
        quantity = extract_quantity(name)
        charges = None
        if item_type == "wand":
            charges = quantity or 50
            quantity = None
        return {
            "description": _consumable_spell_description(name, item_type, matched["spell"], matched["level"], cl or matched["cl"], quantity, charges),
            "tags": ["consumable", item_type],
            "source": "Pathfinder Core Rulebook",
            "source_id": "CRB",
        }
    # fallback generico consumabile
    return {
        "description": f"Italiano: {name} è un consumabile di tipo {item_type} che duplica l'effetto di {rest} (livello e CL determinati dal tipo).",
        "tags": ["consumable", item_type],
        "source": "Pathfinder Core Rulebook",
        "source_id": "CRB",
    }


def _match_level_prefixed(name: str, key: str) -> dict[str, Any] | None:
    m = re.match(r"^(L\d+):\s*(.+)$", name)
    if not m:
        return None
    level = m.group(1)
    inner_name = m.group(2).strip()
    inner_key = normalize_name(inner_name)
    # Prova ad arricchire l'item interno
    inner_entry = {"name": inner_name}
    result = _enrich_entry_logic(inner_entry)
    if result:
        desc = inner_entry.get("description", "")
        desc = f"Italiano: Oggetto di riferimento per personaggio di livello {level[1:]}. {desc}"
        return {
            "description": desc,
            "tags": inner_entry.get("tags", ["gear"]),
            "source": inner_entry.get("source", "Autogenerated"),
            "source_id": inner_entry.get("source_id", "AUTO"),
        }
    return {
        "description": f"Italiano: Oggetto di riferimento per personaggio di livello {level[1:]}: {inner_name}.",
        "tags": ["gear"],
        "source": "Autogenerated",
        "source_id": "AUTO",
    }


# ---------------------------------------------------------------------------
# Fallback generici per categorie
# ---------------------------------------------------------------------------
def _fallback_wondrous(name: str, key: str) -> dict[str, Any] | None:
    lowered = name.lower()
    slot = "none"
    effect = ""
    if "anello" in lowered or "ring" in lowered:
        slot = "ring"
        effect = "Anello magico che conferisce un beneficio meccanico continuo o attivabile al portatore."
    elif "amuleto" in lowered or "amulet" in lowered:
        slot = "neck"
        effect = "Amuleto magico che conferisce un bonus o un beneficio difensivo al portatore."
    elif "cintura" in lowered or "belt" in lowered:
        slot = "belt"
        effect = "Cintura magica che solitamente conferisce un bonus di miglioramento a una caratteristica fisica."
    elif "mantello" in lowered or "cloak" in lowered:
        slot = "shoulders"
        effect = "Mantello magico che conferisce bonus a salvataggi, furtività o protezione ambientale."
    elif "stivali" in lowered or "boots" in lowered:
        slot = "feet"
        effect = "Stivali magici che conferiscono bonus a movimento, salti o abilità di movimento."
    elif "guanti" in lowered or "gloves" in lowered:
        slot = "hands"
        effect = "Guanti magici che conferiscono bonus a Destrezza o a prove di abilità manuali."
    elif "bracciali" in lowered or "bracers" in lowered:
        slot = "wrists"
        effect = "Bracciali magici che conferiscono bonus di armatura o competence a prove specifiche."
    elif "diadema" in lowered or "headband" in lowered or "mitria" in lowered or "cappuccio" in lowered:
        slot = "headband" if "headband" in lowered or "diadema" in lowered or "mitria" in lowered else "head"
        effect = "Oggetto per la testa che conferisce bonus a caratteristiche mentali o competenze."
    elif "veste" in lowered or "robe" in lowered or "cappa" in lowered:
        slot = "body" if "veste" in lowered or "robe" in lowered else "shoulders"
        effect = "Veste magica che conferisce protezione o potenziamento a capacità di classe."
    elif "bastone" in lowered or "staff" in lowered:
        slot = "none"
        effect = "Bastone magico utilizzabile come focus o arma quarterstaff, con proprietà magiche specifiche."
    elif "feticcio" in lowered or "talismano" in lowered:
        slot = "neck"
        effect = "Oggetto fetish/talismano che conferisce un bonus a tiri salvezza, concentrazione o abilità secondo il tipo."
    elif "libro" in lowered or "grimoire" in lowered or "diario" in lowered:
        slot = "none"
        effect = "Libro o diario che funge da spellbook o fonte di conoscenza, spesso contenente incantesimi aggiuntivi."
    elif "focus" in lowered:
        slot = "none"
        effect = "Focus arcano o divino richiesto per lanciare determinati incantesimi o per potenziare classi psichiche."
    elif "santino" in lowered or "simbolo" in lowered:
        slot = "none"
        effect = "Focus divino o simbolo religioso utilizzato per incantesimi e capacità di classe."
    elif "lira" in lowered or "cornamusa" in lowered or "tamburo" in lowered:
        slot = "none"
        effect = "Strumento musicale utilizzabile per eseguire Perform e per le capacità bardiche."
    else:
        return None
    return {
        "description": _generic_wondrous(name, slot, effect),
        "tags": ["wondrous", f"slot:{slot}"],
        "source": "Autogenerated",
        "source_id": "AUTO",
    }


def _fallback_kit(name: str, key: str) -> dict[str, Any] | None:
    lowered = name.lower()
    if "kit" in lowered or "set" in lowered:
        return {
            "description": _gear_description(name, "kit", "Fornisce gli strumenti necessari per attività specifiche; può conferire competence bonus a prove di abilità pertinenti."),
            "tags": ["gear", "kit", "equipment", "nonmagical"],
            "source": "Autogenerated",
            "source_id": "AUTO",
        }
    return None


def _fallback_generic(name: str, key: str) -> dict[str, Any] | None:
    lowered = name.lower()
    if any(w in lowered for w in ["armatura", "armor", "corazza", "scudo", "shield", "giaco", "cotta", "piastre", "pelle"]):
        return {
            "description": f"Italiano: {name} è un'armatura o uno scudo. Il nome indica bonus di miglioramento, materiali speciali o proprietà magiche che modificano bonus alla CA, Max Dex, penalità e fallimento incantesimi.",
            "tags": ["armor", "defense"],
            "source": "Autogenerated",
            "source_id": "AUTO",
        }
    if any(w in lowered for w in ["arma", "weapon", "spada", "ascia", "lancia", "martello", "pugnale", "dagger", "longsword", "arco", "bow", "musket", "pistol", "frusta", "kukri", "kama", "falchion", "falchion"]):
        return {
            "description": f"Italiano: {name} è un'arma. Il nome indica una o più proprietà speciali (bonus di miglioramento, materiale o ability) che si applicano ai tiri per colpire e ai danni secondo le regole delle armi magiche.",
            "tags": ["weapon", "martial", "melee"],
            "source": "Autogenerated",
            "source_id": "AUTO",
        }
    if any(w in lowered for w in ["pozione", "potion", "bacchetta", "wand", "pergamena", "scroll"]):
        return {
            "description": f"Italiano: {name} è un oggetto consumabile magico che duplica l'effetto di un incantesimo noto, attivabile secondo le regole di pozioni, bacchette o pergamene.",
            "tags": ["consumable"],
            "source": "Autogenerated",
            "source_id": "AUTO",
        }
    if any(w in lowered for w in ["munizioni", "cartucce", "polvere", "frecce", "dardi", "proiettili"]):
        return {
            "description": f"Italiano: {name} è munizione o materiale alchemico per armi a distanza o da fuoco. Può fornire bonus al danno o effetti speciali secondo il tipo.",
            "tags": ["gear", "ammunition", "equipment", "nonmagical"],
            "source": "Autogenerated",
            "source_id": "AUTO",
        }
    return {
        "description": f"Italiano: {name} è un oggetto del catalogo. Il nome suggerisce una funzione meccanica specifica (bonus, slot, incantesimo o abilità) da risolvere secondo le regole di Pathfinder 1E.",
        "tags": ["wondrous"],
        "source": "Autogenerated",
        "source_id": "AUTO",
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def _enrich_entry_logic(entry: dict[str, Any]) -> bool:
    name = entry.get("name", "")
    if not name:
        return False
    key = normalize_name(name)

    result = _exact_template(name)
    if not result:
        result = _match_wondrous_family(name, key)
    if not result:
        result = _match_consumable(name, key)
    if not result:
        result = _match_level_prefixed(name, key)
    if not result:
        result = _match_weapon_variant(name, key)
    if not result:
        result = _match_armor_variant(name, key)
    if not result:
        result = _match_shield_variant(name, key)
    if not result:
        result = _fallback_wondrous(name, key)
    if not result:
        result = _fallback_kit(name, key)
    if not result:
        result = _fallback_generic(name, key)

    if result:
        entry["description"] = result["description"]
        if result.get("prerequisites") and not entry.get("prerequisites"):
            entry["prerequisites"] = result["prerequisites"]
        if result.get("tags"):
            entry["tags"] = result["tags"]
        if result.get("source"):
            entry["source"] = result["source"]
        if result.get("source_id"):
            entry["source_id"] = result["source_id"]
        entry["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        return True
    return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Arricchisce items.json con descrizioni meccaniche")
    parser.add_argument("--dry-run", action="store_true", help="Non scrive il file")
    parser.add_argument("--force", action="store_true", help="Sovrascrive anche entry già descritte")
    parser.add_argument("--output", type=Path, help="Percorso output (default: sovrascrive items.json)")
    args = parser.parse_args()

    data = json.loads(ITEMS_PATH.read_text(encoding="utf-8"))
    entries = data.get("entries", []) if isinstance(data, dict) else data

    enriched = 0
    skipped = 0
    for entry in entries:
        if not args.force and (entry.get("description") or entry.get("short_description")):
            skipped += 1
            continue
        if _enrich_entry_logic(entry):
            enriched += 1

    total = len(entries)
    covered = sum(1 for e in entries if e.get("description") or e.get("short_description"))
    print(f"Entry totali: {total}")
    print(f"Arricchite in questa run: {enriched}")
    print(f"Saltate (già descritte): {skipped}")
    print(f"Copertura finale descrizioni: {covered}/{total} ({100*covered/total:.1f}%)")

    if not args.dry_run:
        out_path = args.output or ITEMS_PATH
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
        print(f"Scritto: {out_path}")
    else:
        print("DRY-RUN: nessuna modifica scritta.")


if __name__ == "__main__":
    main()
