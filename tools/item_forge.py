#!/usr/bin/env python3
"""Core deterministico per la generazione oggetti magici PF1e (cantiere
item-gen A-leggera, PRD §9.2 decisione 4).

Numeri dalle regole ufficiali (formule già curate nel legacy
tooling/Item-generator, adattate e rese testabili): prezzi, costo
crafting, LI minimo, aura, CD. Il LLM interviene SOLO per il flavor
(nome/descrizione), mai per i numeri — badge "deterministico verificato".
"""

from __future__ import annotations

from pathlib import Path

# --- Formule prezzo (gp) -------------------------------------------------
# Incantesimo in oggetto: livello incantesimo x LI x fattore uso.
SPELL_USE_FACTOR = {"1/day": 1800, "3/day": 5400, "unlimited": 2000 * 4}
# Bacchette/bastoni: 50 cariche, prezzo = livello x LI x fattore.
WAND_FACTOR = 750
STAFF_FACTOR = 400
# Bonus fisso +X: bonus^2 x fattore per tipo. Fattori verificati sulle
# entry ufficiali: ring of protection +1 = 2.000 gp (deviazione 2000),
# cloak of resistance +1 = 1.000 gp (resistenza 1000), bracers of armor
# +1 = 1.000 gp (armatura 1000); legacy: competenza 1000, altri 2000.
BONUS_TYPE_FACTOR = {
    "competenza": 1000,
    "armatura": 1000,
    "resistenza": 1000,
    "deviazione": 2000,
    "potenziamento": 2000,  # armi/armature +N
    "altro": 2000,
}

AURA_BY_CL = [(5, "Debole"), (11, "Moderata"), (20, "Forte")]

SCHOOLS_IT = {
    "abjuration": "Abjurazione",
    "conjuration": "Evocazione",
    "divination": "Divinazione",
    "enchantment": "Ammaliamento",
    "evocation": "Invocazione",
    "illusion": "Illusione",
    "necromancy": "Necromanzia",
    "transmutation": "Trasmutazione",
    "universal": "Universale",
}


def price_spell_item(spell_level: int, caster_level: int, uses: str = "1/day") -> int:
    """Prezzo di un oggetto che replica un incantesimo.

    uses: '1/day' | '3/day' | 'unlimited'. Validazione onesta: LI >= minimo
    RAW (2 x livello incantesimo - 1)."""
    if uses not in SPELL_USE_FACTOR:
        raise ValueError(
            f"uses non ammesso: {uses!r} (attesi {sorted(SPELL_USE_FACTOR)})"
        )
    min_cl = min_caster_level(spell_level)
    if caster_level < min_cl:
        raise ValueError(
            f"LI {caster_level} sotto il minimo RAW {min_cl} "
            f"per incantesimo di livello {spell_level}"
        )
    return spell_level * caster_level * SPELL_USE_FACTOR[uses]


def price_charged_item(spell_level: int, caster_level: int, kind: str = "wand") -> int:
    """Prezzo bacchetta (wand, 750) o bastone (staff, 400), 50 cariche."""
    factor = {"wand": WAND_FACTOR, "staff": STAFF_FACTOR}.get(kind)
    if factor is None:
        raise ValueError(f"kind non ammesso: {kind!r} (attesi wand/staff)")
    min_cl = min_caster_level(spell_level)
    if caster_level < min_cl:
        raise ValueError(f"LI {caster_level} sotto il minimo RAW {min_cl}")
    return spell_level * caster_level * factor


def price_bonus_item(bonus: int, bonus_type: str) -> int:
    """Prezzo bonus fisso +X: bonus^2 x fattore del tipo."""
    factor = BONUS_TYPE_FACTOR.get(bonus_type)
    if factor is None:
        raise ValueError(
            f"bonus_type sconosciuto: {bonus_type!r} "
            f"(attesi {sorted(BONUS_TYPE_FACTOR)})"
        )
    if bonus < 1:
        raise ValueError("bonus deve essere >= 1")
    return bonus * bonus * factor


def min_caster_level(spell_level: int) -> int:
    """LI minimo RAW per replicare un incantesimo: 2 x livello - 1."""
    if spell_level < 1:
        raise ValueError("spell_level deve essere >= 1 (trucchetti esclusi)")
    return 2 * spell_level - 1


def crafting_cost(price: int) -> int:
    """Costo di costruzione: meta' prezzo, arrotondato per difetto."""
    return price // 2


def aura_for_cl(caster_level: int) -> str:
    """Aura dell'oggetto dal LI: Debole (1-5), Moderata (6-11), Forte (12+)."""
    for cap, aura in AURA_BY_CL:
        if caster_level <= cap:
            return aura
    return "Forte"


def save_dc(spell_level: int, ability_mod: int = 3) -> int:
    """CD del tiro salvezza: 10 + livello incantesimo + mod attributo
    (minimo convenzionale +3)."""
    return 10 + spell_level + max(ability_mod, 3)


def rarity_for_price(price: int) -> str:
    """Fasce di rarita' del legacy Formato Torneo."""
    if price < 10_000:
        return "Comune"
    if price <= 50_000:
        return "Non comune"
    if price <= 200_000:
        return "Raro"
    return "Unico"


def school_it(school_en: str) -> str:
    """Scuola in italiano (mappa legacy; sconosciuta -> errore onesto)."""
    it = SCHOOLS_IT.get(school_en.strip().lower())
    if it is None:
        raise ValueError(f"scuola sconosciuta: {school_en!r}")
    return it


# --- Lookup incantesimi dal catalogo reference ---------------------------

_SPELLS_CACHE = None


def _spells_by_name():
    """Indice lazy nome-normalizzato -> entry di spells.json (catalogo OGL)."""
    global _SPELLS_CACHE
    if _SPELLS_CACHE is None:
        import json

        path = (
            Path(__file__).resolve().parents[1]
            / "data"
            / "reference"
            / "ogl"
            / "spells.json"
        )
        with open(path, encoding="utf-8") as f:
            catalog = json.load(f)
        _SPELLS_CACHE = {}
        for e in catalog["entries"]:
            key = " ".join(e["name"].lower().split())
            _SPELLS_CACHE.setdefault(key, e)
    return _SPELLS_CACHE


def spell_lookup(name: str) -> dict:
    """Entry incantesimo dal catalogo per nome (case-insensitive, spazi
    normalizzati). KeyError onesto con suggerimento dei quasi-match."""
    key = " ".join(name.lower().split())
    table = _spells_by_name()
    if key in table:
        return table[key]
    near = [k for k in table if key in k or k in key][:5]
    raise KeyError(
        f"incantesimo non trovato nel catalogo: {name!r}"
        + (f" (forse: {', '.join(near)})" if near else "")
    )


def forge_from_spell(
    name: str, caster_level: int, uses: str = "1/day", slot: str = "—"
) -> dict:
    """Blocco deterministico completo per un oggetto che replica un
    incantesimo del catalogo: prezzo, costo crafting, aura, CD, scuola IT,
    rarita'. I numeri sono tutti derivati da regole (badge 'deterministico
    verificato'); nome/descrizione restano al layer flavor."""
    entry = spell_lookup(name)
    mech = entry.get("mechanics", {})
    levels = mech.get("spell_level") or {}
    if not levels:
        raise ValueError(f"{name!r}: nessun livello incantesimo in mechanics")
    spell_level = min(int(v) for v in levels.values())
    school_en = mech.get("school")
    if not school_en:
        raise ValueError(f"{name!r}: scuola assente in mechanics")
    price = price_spell_item(spell_level, caster_level, uses)
    return {
        "spell": entry["name"],
        "spell_level": spell_level,
        "caster_level": caster_level,
        "uses": uses,
        "slot": slot,
        "price": price,
        "crafting_cost": crafting_cost(price),
        "aura": aura_for_cl(caster_level),
        "school_it": school_it(school_en),
        "saving_throw": (
            f"CD {save_dc(spell_level)}" if mech.get("saving_throw") else "—"
        ),
        "spell_resistance": (
            "Sì" if (mech.get("spell_resistance") or "").startswith("y") else "No"
        ),
        "rarity": rarity_for_price(price),
        "reference": entry["source_id"],
    }
