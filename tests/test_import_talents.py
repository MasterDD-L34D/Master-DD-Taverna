"""Test per tools/import_talents.py — parser offline su fixture HTML reali
(cache AoN 2026-07-26, estratti in tests/fixtures/) + invarianti del
catalogo talents.json importato. Nessuna rete."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.import_talents import (
    _category_from_h2,
    _parse_added_skills,
    _split_name_kind,
    collect_entries,
    parse_bloodline_page,
    parse_ki_powers,
    parse_mystery_page,
    parse_order_page,
    parse_talent_tables,
    talent_entry,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"
TALENTS_PATH = Path("data/reference/ogl/talents.json")
ALLOWED_KINDS = {"Ex", "Su", "Sp", None}


def _fixture(name):
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_parse_mercies_markup_b_level_sections():
    """Mercies: nome in <b>, sezioni h2 'Nth-Level Mercies' -> level (la
    sezione di livello NON e' una category)."""
    rows = parse_talent_tables(_fixture("talents_mercies.html"))
    assert len(rows) == 4
    r0 = rows[0]
    assert r0["name"] == "Deceived" and r0["kind"] is None
    assert r0["level"] == 3 and r0["category"] is None
    assert r0["source"] == "Healer's Handbook"
    assert r0["text"].startswith(
        "The target can immediately attempt a new saving throw"
    )
    # seconda sezione h2 della stessa pagina -> level 6
    assert rows[3]["name"] == "Dazed" and rows[3]["level"] == 6
    assert rows[3]["source"] == "PRPG Core Rulebook"


def test_parse_rage_offensive_markup_i_category():
    """Rage powers: nome in <i> con (Ex)/(Su), category dalla sottopagina
    (config), kind tolto dal nome."""
    rows = parse_talent_tables(
        _fixture("talents_rage_offensive.html"), page_category="offensive"
    )
    assert len(rows) == 3
    assert rows[0]["name"] == "Animal Fury" and rows[0]["kind"] == "Ex"
    assert rows[0]["category"] == "offensive"
    assert rows[0]["source"] == "PRPG Core Rulebook"
    # entry senza suffisso di fonte -> kind None (assenza onesta)
    assert rows[1]["name"] == "Armor Ripper" and rows[1]["kind"] is None
    assert rows[2]["name"] == "Auspicious Mark" and rows[2]["kind"] == "Su"


def test_parse_ki_powers_inline_section():
    """Ki powers: entry '<i>Nome (Su)</i>:' inline dentro ClassDisplay, la
    sezione finisce al bold della feature successiva (Style Strike non
    entra nel pool)."""
    rows = parse_ki_powers(_fixture("talents_ki_powers.html"))
    names = [r["name"] for r in rows]
    assert names == ["Abundant Step", "Cobra Breath", "Diamond Body"]
    assert all(r["kind"] == "Su" for r in rows)
    assert rows[1]["text"].startswith(
        "Whenever a monk with this ki power uses diamond body"
    )
    # regressione 2026-07-26: gli <i> inline (spell citate) NON aprono entry
    # e NON troncano il testo — Abundant Step arriva fino al punto finale
    assert not any("dimension door" in n.lower() for n in names)
    assert "as if using the spell dimension door." in rows[0]["text"]
    assert rows[0]["text"].endswith("before selecting this ki power.")


def test_parse_talent_tables_esclude_tabelle_annidate():
    """Regressione 2026-07-26: la <table class="inner"> dentro la riga (DC
    per settlement size) NON finisce serializzata nella description."""
    rows = parse_talent_tables(_fixture("talents_rogue_inner_table.html"))
    assert len(rows) == 1
    r = rows[0]
    assert r["name"] == "Black Market Connections" and r["kind"] == "Ex"
    assert "Metropolis" not in r["text"] and "Hamlet" not in r["text"]
    assert r["text"].endswith("given in the table below.")


def test_parse_ninja_tricks_h1_pools():
    """Ninja (C4-bis follow-up): h1 -> pool ('Ninja Tricks'/'Advanced Ninja
    Tricks'), h2 'Sneak Attack Talents' -> category (stessa convenzione
    dei rogue talents)."""
    rows = parse_talent_tables(
        _fixture("talents_ninja.html"),
        {
            "Ninja Tricks": "ninja trick",
            "Advanced Ninja Tricks": "advanced ninja trick",
        },
    )
    assert len(rows) == 2
    assert rows[0]["name"] == "Acrobatic Master" and rows[0]["kind"] == "Su"
    assert rows[0]["pool"] == "ninja trick"
    assert rows[0]["category"] == "sneak attack"
    assert rows[0]["source"] == "Ultimate Combat"
    assert rows[1]["name"] == "Assassinate" and rows[1]["kind"] == "Ex"
    assert rows[1]["pool"] == "advanced ninja trick"
    assert rows[1]["category"] == "sneak attack"


def test_parse_vigilante_hidden_strike_e_category_ridondante():
    """Vigilante (C4-bis follow-up): la sotto-lista 'Hidden Strike' resta nel
    pool 'vigilante talent' con category esplicita da h1_categories; la
    category che duplica il pool (h2 'Social Talents' nel pool 'social
    talent') e' ridondante -> None."""
    rows = parse_talent_tables(
        _fixture("talents_vigilante.html"),
        {
            "Social Talents": "social talent",
            "Vigilante Talents": "vigilante talent",
            "Vigilante Talents - Hidden Strike": "vigilante talent",
        },
        h1_categories={"Vigilante Talents - Hidden Strike": "hidden strike"},
    )
    assert len(rows) == 3
    social = rows[0]
    assert social["name"] == "Case the Joint"
    assert social["pool"] == "social talent" and social["category"] is None
    assert [r["name"] for r in rows[1:]] == ["Foe Collision", "Leave an Opening"]
    assert all(r["pool"] == "vigilante talent" for r in rows[1:])
    assert all(r["category"] == "hidden strike" for r in rows[1:])


def test_split_name_kind_star_suffix():
    """Il marchio '*' finale AoN (non-PFS) non fa parte del nome; il kind si
    legge anche prima dell'asterisco."""
    assert _split_name_kind("Acid bomb*") == ("Acid bomb", None)
    assert _split_name_kind("Blackstar Bomb (Su)*") == ("Blackstar Bomb", "Su")
    assert _split_name_kind(" Animal Fury (Ex) ") == ("Animal Fury", "Ex")


def test_category_from_h2():
    assert _category_from_h2("Sneak Attack Talents") == "sneak attack"
    assert _category_from_h2("Bomb Discoveries") == "bomb"
    assert _category_from_h2("Swashbuckler Renowned Deeds") == "renowned"
    # sezioni di livello e sezioni che duplicano il pool: niente category
    assert _category_from_h2("3rd-Level Mercies") is None
    assert _category_from_h2("1st-level Deeds") is None
    assert _category_from_h2("Grand Discoveries") is None


def test_talent_entry_catalog_shape():
    row = {
        "name": "Animal Fury",
        "kind": "Ex",
        "source": "PRPG Core Rulebook",
        "text": "While raging, the barbarian gains a bite attack.",
        "pool": "rage power",
        "category": "offensive",
        "level": None,
    }
    e = talent_entry(
        row,
        "rage power",
        "Barbarian",
        "AoN: Rage Powers (Barbarian)",
        "https://aonprd.com/BarbarianRagePowers.aspx?Type=Offensive",
    )
    assert e["source_id"] == "talent:rage_power_animal_fury"
    assert e["prerequisites"] == []
    assert e["tags"] == ["talent", "rage-power", "barbarian", "animal-fury"]
    assert e["mechanics"] == {
        "class": "Barbarian",
        "pool": "rage power",
        "kind": "Ex",
        "category": "offensive",
    }
    # level assente in fonte -> chiave assente (nessun campo inventato)
    assert "level" not in e["mechanics"]


def test_parse_mystery_page_battle():
    """Mystery (residui C2 task 2): pagina dettaglio -> entry mystery
    (class_skills/bonus_spells/final_revelation; sezione Deities MAI letta,
    PI) + 10 revelation inline con category = nome del mystery."""
    mystery, revelations = parse_mystery_page(_fixture("talents_mystery_battle.html"))
    assert mystery["name"] == "Battle"
    assert mystery["source"] == "Advanced Player's Guide"
    assert mystery["mechanics_extra"]["class_skills"] == [
        "Intimidate",
        "Knowledge (engineering)",
        "Perception",
        "Ride",
    ]
    spells = mystery["mechanics_extra"]["bonus_spells"]
    assert len(spells) == 9 and spells[0] == {"name": "enlarge person", "level": 2}
    assert "avatar of battle" in mystery["mechanics_extra"]["final_revelation"]
    assert mystery["text"].startswith("Class Skills:")
    assert "Gorum" not in mystery["text"] and "Rovagug" not in mystery["text"]
    assert len(revelations) == 10
    assert all(
        r["pool"] == "revelation" and r["category"] == "battle" for r in revelations
    )
    assert revelations[0]["name"] == "Battlecry" and revelations[0]["kind"] == "Ex"
    assert revelations[0]["text"].startswith("As a standard action")


def test_parse_bloodline_page_aberrant():
    """Bloodline: flavor senza il prefisso fonte ('pg. N'), powers come
    NOMI+kind (auto-conferiti, niente entry separate)."""
    b = parse_bloodline_page(_fixture("talents_bloodline_aberrant.html"))
    assert b["name"] == "Aberrant"  # suffisso ' Bloodline' tolto
    assert b["source"] == "PRPG Core Rulebook"
    assert b["text"].startswith("There is a taint in your blood")
    assert not b["text"].startswith("pg.")
    mech = b["mechanics_extra"]
    assert mech["class_skill"] == "Knowledge (dungeoneering)"
    assert mech["bonus_spells"][0] == {"name": "enlarge person", "level": 3}
    assert "Combat Casting" in mech["bonus_feats"]
    assert mech["arcana"].startswith("Whenever you cast a spell of the polymorph")
    assert mech["powers"] == [
        {"name": "Acidic Ray", "kind": "Sp"},
        {"name": "Long Limbs", "kind": "Ex"},
        {"name": "Unusual Anatomy", "kind": "Ex"},
        {"name": "Alien Resistance", "kind": "Su"},
        {"name": "Aberrant Form", "kind": "Ex"},
    ]


def test_parse_order_page_asp():
    """Order: flavor senza prefisso fonte; skills dalla frase 'adds X and Y
    to his/her class skills'."""
    o = parse_order_page(_fixture("talents_order_asp.html"))
    assert o["name"] == "Order of the Asp"
    assert o["source"] == "Adventurer's Guide"
    assert o["text"].startswith("Cavaliers belonging to the order of the asp")
    assert o["mechanics_extra"]["skills"] == ["Knowledge (local)", "Sleight of Hand"]


def test_parse_added_skills_variants():
    """Le tre formulazioni reali della sezione Skills/Class Skills."""
    assert _parse_added_skills(
        "An order of the x cavalier adds Knowledge (local) and Survival "
        "to his class skills. Whenever..."
    ) == ["Knowledge (local)", "Survival"]
    assert _parse_added_skills(
        "An order of the Green cavalier gains Knowledge (nature) and "
        "Survival as class skills. In addition,..."
    ) == ["Knowledge (nature)", "Survival"]
    assert _parse_added_skills("Nessuna frase skill.") == []


def test_collect_entries_offline_pools():
    """Pipeline completa su cache: tutti i pool attesi, dedup (pool, name) —
    per revelation (pool, category, name) perche' la stessa entry e'
    offerta da piu' mystery."""
    entries, dupes, anomalies = collect_entries(offline=True)
    pools = {}
    for e in entries:
        pools[e["mechanics"]["pool"]] = pools.get(e["mechanics"]["pool"], 0) + 1
    expected = {
        "rage power",
        "mercy",
        "rogue talent",
        "advanced rogue talent",
        "discovery",
        "grand discovery",
        "hex",
        "major hex",
        "grand hex",
        "deed",
        "ki power",
        "ninja trick",
        "advanced ninja trick",
        "slayer talent",
        "advanced slayer talent",
        "social talent",
        "vigilante talent",
        "magus arcana",
        "mystery",
        "revelation",
        "bloodline",
        "order",
    }
    assert set(pools) == expected
    assert dupes == 0 and not anomalies
    keys = [
        (e["mechanics"]["pool"], e["name"].lower())
        for e in entries
        if e["mechanics"]["pool"] != "revelation"
    ]
    assert len(keys) == len(set(keys))
    rkeys = [
        (e["mechanics"].get("category"), e["name"].lower())
        for e in entries
        if e["mechanics"]["pool"] == "revelation"
    ]
    assert len(rkeys) == len(set(rkeys))


def test_talents_catalog_invariants():
    """Invarianti sul catalogo reale importato (dati su disco)."""
    catalog = json.loads(TALENTS_PATH.read_text(encoding="utf-8"))
    assert catalog["_license"] and catalog["_source"]
    entries = catalog["entries"]
    assert len(entries) >= 700
    sids, keys = set(), set()
    for e in entries:
        assert e["source_id"] not in sids, f"source_id duplicato: {e['source_id']}"
        sids.add(e["source_id"])
        key = (e["mechanics"]["pool"], e["name"].lower())
        if e["mechanics"]["pool"] == "revelation":
            # la stessa revelation e' offerta da piu' mystery: unicita' su
            # (category, name) — source_id gia' disambiguato dalla category
            key = (
                e["mechanics"]["pool"],
                e["mechanics"].get("category"),
                e["name"].lower(),
            )
        assert key not in keys, f"(pool, name) duplicato: {key}"
        keys.add(key)
        assert (
            e["mechanics"]["kind"] in ALLOWED_KINDS
        ), f"{e['name']}: kind {e['mechanics']['kind']!r} non ammesso"
        assert e["description"], f"{e['name']}: description vuota"
        assert e["mechanics"]["class"] and e["mechanics"]["pool"]
    print(f"OK: {len(entries)} talenti, invarianti rispettate")
