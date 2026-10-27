"""Test per tools/import_pathbuilder_spells.py — incantesimi Pathbuilder.

Slice D5 (piano 2026-08-02): import di data_spells.xml (2.922 righe) da
`data/reference/pi_local_only/pathbuilder/` (PI local-only, MAI committato)
verso UN JSON committato in pathmaster-dd src/data/: pathbuilder-spells.json.
La copertura PB (quali classi hanno la spell in lista) alimenta poi la
riconciliazione a tre fonti (tools/build_spell_sources.py).

Forma reale del file (ricognizione 2026-08-07): radice <spells>, una <Row>
per incantesimo. Campi: name, source, school, subschool, descriptor (lista
separata da virgole, talvolta con ';' di coda), description (testo Paizo PI
— MAI esportata), spellLevelsDisplay (stringa "cleric/oracle 2, inquisitor 2"
— la dichiarazione AUTOREVOLE dei livelli per classe), castingTime,
components, range, targets, area, effect, duration, savingThrow, sr, mythic
(testo PI — mai esportato, resta solo il flag hasMythic), piu' una COLONNA
per classe (<Wizard>3</Wizard>...) e domain/bloodline/patron
("Nome (livello), ..." grezzi).

Note di formato misurate (ricognizione 2026-08-07):

- spellLevelsDisplay: forma regolare "classe N" per segmento separato da
  virgola; la classe puo' essere combinata ("cleric/oracle",
  "summoner/unchained summoner", "sorcerer/wizard") -> split su "/", OGNI
  classe porta il livello. 4 segmenti su ~17.500 NON regolari: preservati
  raw in unparsedLevelSegments con la spell, MAI parsati a tentativi
  ('summoner/unchained summoner 2 2' x3: Aquatic Cavalry, Fey Gate,
  Snowball; 'inquisitor' senza livello: Deeper Darkness).
- Alias di classe DICHIARATI (artefatti dello scrape d20pfsrd/PB):
  'magusUM' -> 'magus' (suffisso-libro UM nella stringa, Storm of Blades —
  lo stesso artefatto esiste nel dato Taverna, 'magusum' in
  mechanics.spell_level); 'summoner (unchained)' -> 'unchained summoner'
  (PB usa entrambe le grafie nello stesso file).
- Le colonne per classe sono STALE per le spell dei manuali recenti
  (223 classi in display senza colonna, 5 livelli di colonna discordanti):
  NON esportate; la cross-check e' conteggiata nel report. NB: 'sorcerer'
  non ha MAI colonna propria (condivide la lista wizard nel dato grezzo).
- description e mythic: PI, mai esportati. Ref/URL non esiste in questo file.

Policy OGL: solo nomi + meccaniche strutturate; MAI la description.
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools import import_pathbuilder_spells as pbs

# ---------------------------------------------------------------------------
# Fixture: forma reale (campi nell'ordine osservato nel file vero).
# ---------------------------------------------------------------------------

SPELLS_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<spells xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
\t<Row>
\t\t<name>Abeyance</name>
\t\t<source>AP 82</source>
\t\t<school>Abjuration</school>
\t\t<description>Abeyance suppresses the effects of a single curse...</description>
\t\t<spellLevelsDisplay>cleric/oracle 2, inquisitor 2, paladin 2</spellLevelsDisplay>
\t\t<castingTime>1 minute</castingTime>
\t\t<components>V, S, M (a flask of holy water worth 25 gp), DF</components>
\t\t<range>touch</range>
\t\t<targets>creature touched</targets>
\t\t<duration>24 hours;</duration>
\t\t<savingThrow>Will negates (harmless)</savingThrow>
\t\t<sr>yes (harmless)</sr>
\t\t<Paladin>2</Paladin>
\t\t<Cleric>2</Cleric>
\t\t<Oracle>2</Oracle>
\t\t<Inquisitor>2</Inquisitor>
\t</Row>
\t<Row>
\t\t<name>Ablative Barrier</name>
\t\t<source>UC</source>
\t\t<school>Conjuration</school>
\t\t<subschool>creation</subschool>
\t\t<descriptor>force</descriptor>
\t\t<description>Invisible layers of solid force...</description>
\t\t<spellLevelsDisplay>alchemist 2, magus 2, sorcerer/wizard 3, summoner 2, bloodrager 2, occultist 2, psychic 3</spellLevelsDisplay>
\t\t<castingTime>1 standard action</castingTime>
\t\t<components>V, S, M (a piece of metal cut from a shield)</components>
\t\t<range>touch</range>
\t\t<targets>creature touched</targets>
\t\t<duration>1 hour/level or until discharged;</duration>
\t\t<savingThrow>Will negates (harmless)</savingThrow>
\t\t<sr>no</sr>
\t\t<mythic>Add half your tier to the spell's armor bonus...</mythic>
\t\t<Wizard>3</Wizard>
\t\t<Psychic>3</Psychic>
\t</Row>
\t<Row>
\t\t<name>Snowball</name>
\t\t<source>APG</source>
\t\t<school>Conjuration</school>
\t\t<descriptor>cold, water;</descriptor>
\t\t<description>You throw a ball of freezing water...</description>
\t\t<spellLevelsDisplay>druid 1, summoner/unchained summoner 1 1, magusUM 2</spellLevelsDisplay>
\t\t<castingTime>1 standard action</castingTime>
\t\t<components>V, S</components>
\t\t<range>close (25 ft. + 5 ft./2 levels)</range>
\t\t<effect>one ball of ice</effect>
\t\t<duration>instantaneous;</duration>
\t\t<savingThrow>Fortitude partial</savingThrow>
\t\t<sr>no</sr>
\t\t<Summoner>1</Summoner>
\t\t<Unchained_Summoner>1</Unchained_Summoner>
\t</Row>
\t<Row>
\t\t<name>Deeper Darkness</name>
\t\t<source>CRB</source>
\t\t<school>Evocation</school>
\t\t<descriptor>darkness</descriptor>
\t\t<description>This spell functions as darkness...</description>
\t\t<spellLevelsDisplay>cleric/oracle 3, inquisitor</spellLevelsDisplay>
\t\t<castingTime>1 standard action</castingTime>
\t\t<components>V, S, M/DF</components>
\t\t<range>touch</range>
\t\t<area>20-ft.-radius emanation</area>
\t\t<duration>10 min./level (D)</duration>
\t\t<savingThrow>none</savingThrow>
\t\t<sr>no</sr>
\t</Row>
\t<Row>
\t\t<name>Absorbing Barrier</name>
\t\t<source>Planes</source>
\t\t<school>Abjuration</school>
\t\t<description>Invisible layers...</description>
\t\t<spellLevelsDisplay>alchemist 4, sorcerer 4, summoner 4, summoner (unchained) 4</spellLevelsDisplay>
\t\t<castingTime>1 standard action</castingTime>
\t\t<components>V, S</components>
\t\t<range>personal</range>
\t\t<targets>you</targets>
\t\t<duration>1 round/level</duration>
\t\t<Alchemist>4</Alchemist>
\t\t<Summoner>2</Summoner>
\t\t<Unchained_Summoner>2</Unchained_Summoner>
\t\t<Wizard>4</Wizard>
\t</Row>
\t<Row>
\t\t<name>Aid</name>
\t\t<source>CRB</source>
\t\t<school>Enchantment</school>
\t\t<subschool>compulsion</subschool>
\t\t<descriptor>mind-affecting</descriptor>
\t\t<description>Aid grants the target a +1 morale bonus...</description>
\t\t<spellLevelsDisplay>cleric/oracle 2, inquisitor 2, paladin 2, alchemist 2</spellLevelsDisplay>
\t\t<domain>Luck (2), Tactics (2)</domain>
\t\t<castingTime>1 standard action</castingTime>
\t\t<components>V, S, DF</components>
\t\t<range>touch</range>
\t\t<targets>living creature touched</targets>
\t\t<duration>1 min./level</duration>
\t\t<savingThrow>Will negates (harmless)</savingThrow>
\t\t<sr>yes (harmless)</sr>
\t</Row>
\t<Row>
\t\t<name>Beast Bond</name>
\t\t<source>UW</source>
\t\t<school>Divination</school>
\t\t<description>You establish a mental link...</description>
\t\t<spellLevelsDisplay>druid 1, ranger 1</spellLevelsDisplay>
\t\t<bloodline>Destined (3), Kobold (3)</bloodline>
\t\t<patron>Animals (10)</patron>
\t\t<castingTime>1 standard action</castingTime>
\t\t<components>V, S</components>
\t\t<range>close (25 ft. + 5 ft./2 levels)</range>
\t\t<duration>10 min./level</duration>
\t</Row>
</spells>
"""


@pytest.fixture()
def raw_dir(tmp_path: Path) -> Path:
    (tmp_path / "data_spells.xml").write_text(SPELLS_XML, encoding="utf-8")
    return tmp_path


# ---------------------------------------------------------------------------
# Alias di classe dichiarati
# ---------------------------------------------------------------------------


def test_class_aliases_dichiarati():
    assert pbs.CLASS_ALIASES == {
        "magusum": "magus",
        "summoner (unchained)": "unchained summoner",
    }


# ---------------------------------------------------------------------------
# Parsing spellLevelsDisplay
# ---------------------------------------------------------------------------


def test_parse_levels_forma_regolare():
    levels, unparsed = pbs.parse_spell_levels(
        "cleric/oracle 2, inquisitor 2, paladin 2"
    )
    assert levels == {"cleric": 2, "oracle": 2, "inquisitor": 2, "paladin": 2}
    assert unparsed == []


def test_parse_levels_classe_combinata_splittata():
    levels, _ = pbs.parse_spell_levels(
        "sorcerer/wizard 3, summoner/unchained summoner 2"
    )
    assert levels == {
        "sorcerer": 3,
        "wizard": 3,
        "summoner": 2,
        "unchained summoner": 2,
    }


def test_parse_levels_segmento_irregolare_preservato_raw():
    # livello raddoppiato nel dato grezzo: MAI parsato a tentativi
    levels, unparsed = pbs.parse_spell_levels(
        "druid 1, summoner/unchained summoner 1 1"
    )
    assert levels == {"druid": 1}
    assert unparsed == ["summoner/unchained summoner 1 1"]


def test_parse_levels_segmento_senza_livello_preservato_raw():
    levels, unparsed = pbs.parse_spell_levels("cleric/oracle 3, inquisitor")
    assert levels == {"cleric": 3, "oracle": 3}
    assert unparsed == ["inquisitor"]


def test_parse_levels_alias_applicati():
    levels, _ = pbs.parse_spell_levels("magusUM 2, summoner (unchained) 4")
    assert levels == {"magus": 2, "unchained summoner": 4}


# ---------------------------------------------------------------------------
# Import righe
# ---------------------------------------------------------------------------


def test_import_spell_campi_strutturati(raw_dir):
    spells = pbs.import_spells(raw_dir)
    by_name = {s["name"]: s for s in spells}
    ab = by_name["Abeyance"]
    assert ab["source"] == "AP 82"
    assert ab["school"] == "Abjuration"
    assert ab["subschool"] is None
    assert ab["descriptors"] == []
    assert ab["spellLevels"] == {
        "cleric": 2,
        "oracle": 2,
        "inquisitor": 2,
        "paladin": 2,
    }
    assert ab["castingTime"] == "1 minute"
    assert ab["components"] == "V, S, M (a flask of holy water worth 25 gp), DF"
    assert ab["range"] == "touch"
    assert ab["targets"] == "creature touched"
    assert ab["duration"] == "24 hours;"
    assert ab["savingThrow"] == "Will negates (harmless)"
    assert ab["spellResistance"] == "yes (harmless)"
    assert ab["hasMythic"] is False
    assert "unparsedLevelSegments" not in ab


def test_import_spell_campi_opzionali(raw_dir):
    by_name = {s["name"]: s for s in pbs.import_spells(raw_dir)}
    ab = by_name["Ablative Barrier"]
    assert ab["subschool"] == "creation"
    assert ab["descriptors"] == ["force"]
    assert ab["hasMythic"] is True  # solo il flag: il testo mythic e' PI
    dd = by_name["Deeper Darkness"]
    assert dd["area"] == "20-ft.-radius emanation"
    assert dd["targets"] is None
    assert dd["effect"] is None


def test_import_spell_irregolari_flaggati(raw_dir):
    by_name = {s["name"]: s for s in pbs.import_spells(raw_dir)}
    snow = by_name["Snowball"]
    # il segmento irregolare NON entra nei livelli (mai a tentativi);
    # magusUM -> magus via alias dichiarato
    assert snow["spellLevels"] == {"druid": 1, "magus": 2}
    assert snow["unparsedLevelSegments"] == ["summoner/unchained summoner 1 1"]
    dd = by_name["Deeper Darkness"]
    assert dd["spellLevels"] == {"cleric": 3, "oracle": 3}
    assert dd["unparsedLevelSegments"] == ["inquisitor"]


def test_import_spell_alias_unchained(raw_dir):
    by_name = {s["name"]: s for s in pbs.import_spells(raw_dir)}
    ab = by_name["Absorbing Barrier"]
    assert ab["spellLevels"] == {
        "alchemist": 4,
        "sorcerer": 4,
        "summoner": 4,
        "unchained summoner": 4,
    }


def test_import_descriptors_puliti(raw_dir):
    by_name = {s["name"]: s for s in pbs.import_spells(raw_dir)}
    # "cold, water;" -> token puliti (il ';' di coda e' un artefatto del dato)
    assert by_name["Snowball"]["descriptors"] == ["cold", "water"]


def test_import_domain_bloodline_patron_grezzi(raw_dir):
    by_name = {s["name"]: s for s in pbs.import_spells(raw_dir)}
    assert by_name["Aid"]["domains"] == "Luck (2), Tactics (2)"
    assert by_name["Aid"]["bloodlines"] is None
    assert by_name["Aid"]["patrons"] is None
    bb = by_name["Beast Bond"]
    assert bb["bloodlines"] == "Destined (3), Kobold (3)"
    assert bb["patrons"] == "Animals (10)"
    assert bb["domains"] is None
    # campi opzionali assenti nel dato -> null dichiarati
    assert bb["savingThrow"] is None
    assert bb["spellResistance"] is None


def test_import_mai_description_ne_mythic(raw_dir):
    for s in pbs.import_spells(raw_dir):
        keys = {k.lower() for k in s}
        assert "description" not in keys
        assert "mythic" not in keys


# ---------------------------------------------------------------------------
# Payload completo (main) — header, conteggi, report
# ---------------------------------------------------------------------------


def test_main_scrive_json_con_header_e_report(raw_dir, tmp_path):
    out_dir = tmp_path / "out"
    rc = pbs.main(["--raw-dir", str(raw_dir), "--out-dir", str(out_dir)])
    assert rc == 0
    payload = json.loads(
        (out_dir / "pathbuilder-spells.json").read_text(encoding="utf-8")
    )
    prov = payload["_provenance"]
    assert "Pathbuilder" in prov["source"]
    assert prov["generated_by"] == (
        "Master-DD-Taverna/tools/import_pathbuilder_spells.py"
    )
    assert "OGL" in prov["license"]
    assert "description" in prov["desc_policy"].lower()
    counts = payload["counts"]
    assert counts["spells"] == 7
    assert counts["duplicateNames"] == 0
    assert counts["withUnparsedLevelSegments"] == 2
    # report: segmenti irregolari preservati raw con la spell
    segs = payload["report"]["unparsedLevelSegments"]
    assert {s["spell"] for s in segs} == {"Snowball", "Deeper Darkness"}
    # alias di classe dichiarati nel dato
    assert payload["report"]["classAliases"]["magusum"] == "magus"
    # cross-check colonne (stale) vs display: conteggi dichiarati
    cross = payload["report"]["classColumnCrosscheck"]
    # Absorbing Barrier: display summoner/unchained 4, colonne stale a 2
    assert cross["columnLevelMismatches"] == 2
    assert {m["class"] for m in cross["mismatches"]} == {
        "summoner",
        "unchained summoner",
    }
    assert cross["note"]
    # nessuna description/mythic in tutto il payload
    raw = json.dumps(payload)
    assert "suppresses the effects" not in raw
    assert "half your tier" not in raw


# ---------------------------------------------------------------------------
# Smoke sui dati REALI (skip se il dataset PI non e' presente)
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[1]
REAL_RAW = REPO_ROOT / "data/reference/pi_local_only/pathbuilder"
REAL_REASON = f"dataset PI local-only assente: {REAL_RAW}"


@pytest.mark.skipif(not (REAL_RAW / "data_spells.xml").is_file(), reason=REAL_REASON)
def test_dati_reali_conteggi_e_spot_check():
    spells = pbs.import_spells(REAL_RAW)
    assert len(spells) == 2922
    by_name = {s["name"]: s for s in spells}
    assert len(by_name) == 2922  # nessun nome duplicato nel dato grezzo
    # spot-check RAW: Cure Light Wounds (lista nota CRB+)
    clw = by_name["Cure Light Wounds"]
    assert clw["spellLevels"] == {
        "bard": 1,
        "cleric": 1,
        "oracle": 1,
        "druid": 1,
        "paladin": 1,
        "ranger": 2,
        "witch": 1,
        "inquisitor": 1,
        "alchemist": 1,
        "shaman": 1,
        "occultist": 1,
        "spiritualist": 1,
    }
    assert clw["school"] == "Conjuration"
    assert clw["subschool"] == "healing"
    assert clw["source"] == "CRB"
    # Fireball: sorcerer/wizard 3 combinati -> splittati
    fb = by_name["Fireball"]
    assert fb["spellLevels"]["sorcerer"] == 3
    assert fb["spellLevels"]["wizard"] == 3
    assert fb["descriptors"] == ["fire"]
    # forma invertita PB: la stringa originale resta com'e'
    gdm = by_name["Dispel Magic, Greater"]
    assert gdm["spellLevels"]["sorcerer"] == 6
    assert gdm["spellLevels"]["summoner"] == 5


@pytest.mark.skipif(not (REAL_RAW / "data_spells.xml").is_file(), reason=REAL_REASON)
def test_dati_reali_irregolari_e_alias():
    spells = pbs.import_spells(REAL_RAW)
    by_name = {s["name"]: s for s in spells}
    # i 4 segmenti irregolari del dataset: preservati raw, mai a tentativi
    unparsed = [
        (s["name"], seg) for s in spells for seg in s.get("unparsedLevelSegments", [])
    ]
    assert sorted(unparsed) == [
        ("Aquatic Cavalry", "summoner/unchained summoner 2 2"),
        ("Deeper Darkness", "inquisitor"),
        ("Fey Gate", "summoner/unchained summoner 6 6"),
        ("Snowball", "summoner/unchained summoner 1 1"),
    ]
    # Storm of Blades: 'magusUM' -> magus (alias dichiarato, artefatto UM)
    sob = by_name["Storm of Blades"]
    assert sob["spellLevels"]["magus"] == 2
    assert "magusum" not in sob["spellLevels"]


@pytest.mark.skipif(not (REAL_RAW / "data_spells.xml").is_file(), reason=REAL_REASON)
def test_dati_reali_mai_description():
    for s in pbs.import_spells(REAL_RAW):
        keys = {k.lower() for k in s}
        assert "description" not in keys
        assert "mythic" not in keys
