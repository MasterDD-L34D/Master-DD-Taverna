"""Test per tools/import_pcgen_proficiencies.py — proficienze di classe PCGen.

Slice D6 (piano 2026-08-02): le proficienze (armi semplici/comuni/esotiche/
da fuoco, armature leggere/medie/pesanti, scudi, scudi torre, armi esplicite,
arma della divinita') sono nel raw PCGen in TRE forme (ricognizione
2026-08-08):

1. righe `CATEGORY=Class|<Classe>[ ~ Standard ...].MOD` con grant
   `ABILITY:Internal|AUTOMATIC|<nomi>` ("Weapon Prof ~ Simple",
   "TYPE=ArmorProfMedium", "Shield Prof", "Weapon Proficiencies ~ Bard", ...);
2. i record ability `KEY:<Classe> ~ Weapon and Armor Proficiency` (o
   `Weapon and Armor Proficiency ~ <Classe>`) con ABILITY:Internal e
   AUTO:WEAPONPROF/AUTO:ARMORPROF propri (Wizard, Cleric, ...);
3. i record Internal `Weapon Proficiencies ~ <Classe>` con la lista
   esplicita AUTO:WEAPONPROF (Bard, Druid, Monk, Rogue, ...).

I gate PREVARGTEQ:<var>,<N> danno il livello di concessione (Magus: armatura
media al 7°). !PREABILITY sugli archetipi = "se non sostituito": il grant di
base resta (gli swap degli archetipi sono fuori scope D6, dichiarati).
DEITYWEAPONS -> flag deity (la divinita' non e' sulla scheda: unknown dal
motore). %LIST (scelte) e segmenti non mappati -> report, MAI buttati via.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools import import_pcgen_proficiencies as imp

LST = """\
# Class Name	Hit Dice	Type
CLASS:Wizard	HD:6	TYPE:Base.PC
Weapon and Armor Proficiency	KEY:Wizard ~ Weapon and Armor Proficiency	CATEGORY:Special Ability	AUTO:WEAPONPROF|Club|Dagger|Crossbow (Heavy)|Crossbow (Light)|Quarterstaff	ABILITY:Internal|AUTOMATIC|Weapon Prof ~ Auto
CATEGORY=Class|Fighter.MOD	ABILITY:Internal|AUTOMATIC|Weapon Prof ~ Martial|Weapon Prof ~ Simple|PREVAREQ:Fighter_CF_Proficiencies,0
CATEGORY=Class|Fighter.MOD	ABILITY:Internal|AUTOMATIC|Armor Prof ~ Heavy|Armor Prof ~ Medium|Armor Prof ~ Light|Shield Prof|Shield Prof ~ Tower
Weapon and Armor Proficiency	KEY:Weapon and Armor Proficiency ~ Cleric	CATEGORY:Special Ability	ABILITY:Internal|AUTOMATIC|Weapon Prof ~ Simple|Weapon Proficiencies ~ Cleric	ABILITY:Internal|AUTOMATIC|Shield Prof|TYPE=ArmorProfMedium|TYPE=ArmorProfLight
Weapon Proficiencies ~ Cleric	CATEGORY:Internal	AUTO:WEAPONPROF|DEITYWEAPONS
CATEGORY=Class|Magus.MOD	ABILITY:Internal|AUTOMATIC|Armor Prof ~ Medium|PREVARGTEQ:Magus_CFP_Level,7
CATEGORY=Class|Gunslinger.MOD	ABILITY:Internal|AUTOMATIC|Exotic Weapon Proficiency ~ Firearms
Weapon Proficiencies ~ Monk	CATEGORY:Internal	AUTO:WEAPONPROF|Club|Dagger|TYPE=Auto
CATEGORY=Class|Monk.MOD	ABILITY:Internal|AUTOMATIC|Weapon Proficiencies ~ Monk
CATEGORY=Class|Bard ~ Standard Class Full.MOD	ABILITY:Internal|AUTOMATIC|Weapon Prof ~ Simple
"""


def _parse():
    return imp.parse_lst_text(LST, source_book="XX")


def test_simple_and_martial_from_mod_lines():
    classes = _parse()
    fighter = classes["Fighter"]
    kinds = {(g["kind"], g.get("value")) for g in fighter["grants"]}
    assert ("weapon_type", "simple") in kinds
    assert ("weapon_type", "martial") in kinds
    assert ("armor_type", "light") in kinds
    assert ("armor_type", "medium") in kinds
    assert ("armor_type", "heavy") in kinds
    assert ("shield", None) in kinds
    assert ("tower_shield", None) in kinds


def test_explicit_weapons_from_ability_record():
    classes = _parse()
    wizard = classes["Wizard"]
    explicit = sorted(g["value"] for g in wizard["grants"] if g["kind"] == "weapon")
    assert explicit == [
        "Club",
        "Crossbow (Heavy)",
        "Crossbow (Light)",
        "Dagger",
        "Quarterstaff",
    ]
    assert any(g["kind"] == "auto_weapons" for g in wizard["grants"])


def test_deity_weapons_flagged_via_internal_record():
    classes = _parse()
    cleric = classes["Cleric"]
    assert any(g["kind"] == "deity_weapons" for g in cleric["grants"])
    kinds = {(g["kind"], g.get("value")) for g in cleric["grants"]}
    assert ("weapon_type", "simple") in kinds
    assert ("armor_type", "medium") in kinds
    assert ("armor_type", "light") in kinds
    assert ("shield", None) in kinds


def test_level_gate_from_prevargteq():
    classes = _parse()
    magus = classes["Magus"]
    medium = next(
        g
        for g in magus["grants"]
        if g["kind"] == "armor_type" and g["value"] == "medium"
    )
    assert medium["level"] == 7


def test_standard_class_full_suffix_stripped():
    classes = _parse()
    assert "Bard" in classes


def test_firearms_from_named_grant():
    classes = _parse()
    assert any(
        g["kind"] == "weapon_type" and g["value"] == "firearm"
        for g in classes["Gunslinger"]["grants"]
    )


def test_type_auto_segment_in_explicit_list_becomes_auto_not_weapon():
    """TYPE=Auto dentro un AUTO:WEAPONPROF esplicito: categoria, non nome."""
    classes = _parse()
    monk = classes["Monk"]
    assert any(g["kind"] == "auto_weapons" for g in monk["grants"])
    explicit = sorted(g["value"] for g in monk["grants"] if g["kind"] == "weapon")
    assert explicit == ["Club", "Dagger"]


def test_unmapped_grant_names_reported_not_dropped():
    lst = "CATEGORY=Class|Odd.MOD\tABILITY:Internal|AUTOMATIC|Something Weird ~ X\n"
    report: dict = {}
    classes = imp.parse_lst_text(lst, source_book="XX", report=report)
    # Unmapped: SOLO report, mai nel dataset e mai indovinato.
    assert classes.get("Odd") is None
    assert report["unmapped_names"] == {"Something Weird ~ X": 1}


# ---------------------------------------------------------------------------
# Fase A (2026-08-08): con UI/UW in BOOK_CLASS_FILES anche Vigilante e
# Shifter hanno i grant di proficienza (erano corpus_missing dichiarati D6).
# Smoke sui dati REALI (salta se il clone PCGen non c'e').
# ---------------------------------------------------------------------------

import os  # noqa: E402

import pytest  # noqa: E402

REAL_ROOT = Path(os.environ.get("PCGEN_REPO", r"C:\Users\VGit\Downloads\pcgen-repo"))


@pytest.mark.skipif(
    not (REAL_ROOT / "data/pathfinder/paizo").is_dir(), reason="clone PCGen assente"
)
def test_dati_reali_vigilante_shifter_proficiencies():
    doc = imp.build_file(REAL_ROOT)
    classes = doc["classes"]
    assert "Vigilante" in classes  # Ultimate Intrigue
    assert "Shifter" in classes  # Ultimate Wilderness

    vig = {(g["kind"], g.get("value")) for g in classes["Vigilante"]["grants"]}
    # record reale ui_abilities_class.lst (verificato 2026-08-08):
    # TYPE=WeaponProfMartial + TYPE=ArmorProfMedium + TYPE=ShieldProf
    assert ("weapon_type", "martial") in vig
    assert ("armor_type", "medium") in vig
    assert ("shield", None) in vig
    # GAP DEL DATO PCGen colmato da SUPPLEMENTO CURATO (flag "curated": true,
    # mai silenzioso): il record PCGen del Vigilante NON concede
    # "Weapon Prof ~ Simple" ne' "Armor Prof ~ Light" come grant separati,
    # ma il RAW si' — "proficient with all simple and martial weapons,
    # light armor, medium armor, and shields (except tower shields)"
    # (UI p.9, AoN ClassDisplay Vigilante verificato 2026-08-08).
    vig_simple = [
        g
        for g in classes["Vigilante"]["grants"]
        if g["kind"] == "weapon_type" and g.get("value") == "simple"
    ]
    vig_light = [
        g
        for g in classes["Vigilante"]["grants"]
        if g["kind"] == "armor_type" and g.get("value") == "light"
    ]
    assert len(vig_simple) == 1 and vig_simple[0]["curated"] is True
    assert len(vig_light) == 1 and vig_light[0]["curated"] is True

    shifter = classes["Shifter"]["grants"]
    explicit = {g.get("value") for g in shifter if g["kind"] == "weapon"}
    # record reale uw_abilities_class.lst: lista esplicita di 10 armi
    assert {"Club", "Scimitar", "Sickle", "Quarterstaff"} <= explicit
    kinds = {(g["kind"], g.get("value")) for g in shifter}
    assert ("armor_type", "medium") in kinds
    assert ("shield", None) in kinds
    # stesso supplemento curato per l'armatura leggera (UW p.26, AoN
    # ClassDisplay Shifter verificato 2026-08-08: "proficient with light
    # and medium armor"); il divieto del metallo resta NON modellato
    # (dichiarato, come le restrizioni druidiche D6)
    light = [
        g for g in shifter if g["kind"] == "armor_type" and g.get("value") == "light"
    ]
    assert len(light) == 1 and light[0]["curated"] is True
