"""Test per tools/import_pathbuilder_races.py — razze e tratti alternativi PB.

Slice D1 (piano 2026-08-02): import di data_races.xml (669 righe-trait, 74
razze) e data_races_alternative_traits.xml (702 righe, 59 razze) da
`data/reference/pi_local_only/pathbuilder/` (PI local-only, MAI committato)
verso DUE JSON committati in pathmaster-dd src/data/:
pathbuilder-races.json e pathbuilder-race-traits.json.

Forma reale dei file (ricognizione 2026-08-07): <Root><Row>; il campo <Race>
compare SOLO sulla prima riga del blocco razza; ogni riga e' un tratto con
<Trait>, <Description> (PI — mai esportata), <Src> (solo su alcune righe,
uniforme per razza) o <Source> nel file alternative traits,
<ShowInSpecials>, <HasEffect>. Gli ability adjustments NON sono un campo
strutturato: vivono nella Description del tratto "Ability Bonus" e solo in
formati regolari ("Bonus +2 Constitution, +2 Wisdom, –2 Charisma.",
"They gain +2 Constitution and +2 Charisma.", "+2 Str, +2 Wis, –2 Int.").
Le razze "flex" dicono "+2 to One Ability Score" (Human, Half-Elf, Half-Orc).
Dove il dato non ha numeri: abilityAdjustments dichiarato assente (null),
MAI inventato.

Policy OGL: i JSON committati non includono mai la Description.
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools import import_pathbuilder_races as pb

# ---------------------------------------------------------------------------
# Fixture: forma reale (campi nell'ordine osservato nei file veri).
# ---------------------------------------------------------------------------

RACES_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Root xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
\t<Row>
\t\t<Race>Dwarf</Race>
\t\t<Trait>Ability Bonus</Trait>
\t\t<Description>Bonus +2 Constitution, +2 Wisdom, –2 Charisma. Dwarves are both tough and wise, but also a bit gruff.</Description>
\t\t<Src>CRB</Src>
\t\t<ShowInSpecials>false</ShowInSpecials>
\t\t<HasEffect>true</HasEffect>
\t</Row>
\t<Row>
\t\t<Trait>Medium</Trait>
\t\t<Description>Dwarves are Medium creatures and receive no bonuses or penalties due to their size.</Description>
\t\t<ShowInSpecials>false</ShowInSpecials>
\t\t<HasEffect>false</HasEffect>
\t</Row>
\t<Row>
\t\t<Trait>Darkvision</Trait>
\t\t<Description>Dwarves can see in the dark up to 60 feet.</Description>
\t\t<ShowInSpecials>true</ShowInSpecials>
\t\t<HasEffect>false</HasEffect>
\t</Row>
\t<Row>
\t\t<Race>Human</Race>
\t\t<Trait>Ability Bonus</Trait>
\t\t<Description>Bonus +2 to One Ability Score. Human characters gain a +2 racial bonus to one ability score of their choice at creation to represent their varied nature.</Description>
\t\t<ShowInSpecials>false</ShowInSpecials>
\t\t<HasEffect>true</HasEffect>
\t</Row>
\t<Row>
\t\t<Trait>Medium</Trait>
\t\t<Description>Humans are Medium creatures and receive no bonuses or penalties due to their size.</Description>
\t\t<ShowInSpecials>false</ShowInSpecials>
\t\t<HasEffect>false</HasEffect>
\t</Row>
\t<Row>
\t\t<Race>Halfling</Race>
\t\t<Trait>Ability Bonus</Trait>
\t\t<Description>Bonus +2 Dexterity, +2 Charisma, –2 Strength. Halflings are nimble and strong-willed.</Description>
\t\t<Src>CRB</Src>
\t\t<ShowInSpecials>false</ShowInSpecials>
\t\t<HasEffect>true</HasEffect>
\t</Row>
\t<Row>
\t\t<Trait>Small</Trait>
\t\t<Description>Halflings are Small creatures.</Description>
\t\t<ShowInSpecials>false</ShowInSpecials>
\t\t<HasEffect>false</HasEffect>
\t</Row>
\t<Row>
\t\t<Race>Aasimar</Race>
\t\t<Trait>Ability Bonus</Trait>
\t\t<Description>Aasimars are insightful, confident, and personable.</Description>
\t\t<Src>ARG</Src>
\t\t<ShowInSpecials>false</ShowInSpecials>
\t\t<HasEffect>true</HasEffect>
\t</Row>
\t<Row>
\t\t<Trait>Medium</Trait>
\t\t<Description>Aasimars are Medium creatures.</Description>
\t\t<ShowInSpecials>false</ShowInSpecials>
\t\t<HasEffect>false</HasEffect>
\t</Row>
\t<Row>
\t\t<Race>Shabti</Race>
\t\t<Trait>Ability Bonus</Trait>
\t\t<Description>Shabti have powerful bodies and presences to match. They gain +2 Constitution and +2 Charisma.</Description>
\t\t<Src>Bestiary 5</Src>
\t\t<ShowInSpecials>false</ShowInSpecials>
\t\t<HasEffect>true</HasEffect>
\t</Row>
\t<Row>
\t\t<Trait>Darkvision</Trait>
\t\t<Description>Shabti can see perfectly in the dark up to 60 feet.</Description>
\t\t<ShowInSpecials>true</ShowInSpecials>
\t\t<HasEffect>false</HasEffect>
\t</Row>
</Root>
"""

ALT_TRAITS_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Root xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
\t<Row>
\t\t<Race>Human</Race>
\t\t<Trait>Adoptive Parentage</Trait>
\t\t<Description>Humans are sometimes orphaned and adopted by other races. ...</Description>
\t\t<Source>ARG</Source>
\t\t<ReplacedTraits>Bonus Feat</ReplacedTraits>
\t\t<ShowInSpecials>FALSE</ShowInSpecials>
\t\t<HasEffect>true</HasEffect>
\t</Row>
\t<Row>
\t\t<Trait>Dual Talent</Trait>
\t\t<Description>Some humans are uniquely skilled at maximizing their natural gifts. ...</Description>
\t\t<Source>ARG</Source>
\t\t<ReplacedTraits>Bonus Feat&amp;Skilled</ReplacedTraits>
\t\t<ChangedTraits>Ability Bonus</ChangedTraits>
\t\t<ShowInSpecials>false</ShowInSpecials>
\t\t<HasEffect>true</HasEffect>
\t</Row>
\t<Row>
\t\t<Race>Dwarf</Race>
\t\t<Trait>Ancient Enmity</Trait>
\t\t<Description>Dwarves have long been in conflict with elves. ...</Description>
\t\t<Source>ARG</Source>
\t\t<ReplacedTraits>Hatred</ReplacedTraits>
\t\t<ShowInSpecials>true</ShowInSpecials>
\t\t<HasEffect>false</HasEffect>
\t</Row>
</Root>
"""


# ---------------------------------------------------------------------------
# Parser degli ability adjustments (SOLO dal dato, formati regolari)
# ---------------------------------------------------------------------------


def test_parse_ability_bonus_formato_standard():
    assert pb.parse_ability_bonus(
        "Bonus +2 Constitution, +2 Wisdom, –2 Charisma. Dwarves are..."
    ) == {"con": 2, "wis": 2, "cha": -2}


def test_parse_ability_bonus_doppio_spazio_e_segno_varianti():
    assert pb.parse_ability_bonus(
        "Bonus  +2 Dexterity, +2 Intelligence, –2 Constitution. Elves..."
    ) == {"dex": 2, "int": 2, "con": -2}


def test_parse_ability_bonus_gain_suffer():
    assert pb.parse_ability_bonus("They gain +2 Constitution and +2 Charisma.") == {
        "con": 2,
        "cha": 2,
    }
    assert pb.parse_ability_bonus(
        "They gain +2 Dexterity and +2 Constitution but suffer –2 Intelligence."
    ) == {"dex": 2, "con": 2, "int": -2}


def test_parse_ability_bonus_sigle():
    assert pb.parse_ability_bonus(
        "+2 Str, +2 Wis, –2 Int. Rougarous are strong and alert."
    ) == {"str": 2, "wis": 2, "int": -2}
    assert pb.parse_ability_bonus("Flexible (+2 Str, +2 Con) (2 RP)") == {
        "str": 2,
        "con": 2,
    }


def test_parse_ability_bonus_senza_numeri_e_none():
    # mai inventato: description senza numeri -> None (dichiarato assente)
    assert (
        pb.parse_ability_bonus("Aasimars are insightful, confident, and personable.")
        is None
    )
    assert pb.parse_ability_bonus(None) is None
    # numeri NON adiacenti al nome caratteristica: niente parsing
    assert (
        pb.parse_ability_bonus(
            "they gain a +2 racial bonus to either Strength, Dexterity, or "
            "Constitution (see Change Shape)."
        )
        is None
    )
    assert (
        pb.parse_ability_bonus(
            "syrinx gain a +2 bonus to Wisdom but suffer a –2 penalty to Dexterity."
        )
        is None
    )


def test_is_flexible_ability_bonus():
    assert pb.is_flexible_ability_bonus(
        "Bonus +2 to One Ability Score. Human characters gain..."
    )
    assert pb.is_flexible_ability_bonus(
        "Bonus +2 to one ability score of their choice."
    )
    assert not pb.is_flexible_ability_bonus(
        "Bonus +2 Constitution, +2 Wisdom, –2 Charisma."
    )
    assert not pb.is_flexible_ability_bonus(None)


# ---------------------------------------------------------------------------
# Raggruppamento blocchi razza (Race solo sulla prima riga del blocco)
# ---------------------------------------------------------------------------


def test_group_race_blocks():
    rows = pb.iter_rows(pb.parse_xml(RACES_XML))
    blocks = pb.group_race_blocks(rows)
    assert list(blocks) == ["Dwarf", "Human", "Halfling", "Aasimar", "Shabti"]
    assert [r.findtext("Trait") for r in blocks["Dwarf"]] == [
        "Ability Bonus",
        "Medium",
        "Darkvision",
    ]
    assert len(blocks["Shabti"]) == 2


# ---------------------------------------------------------------------------
# import_races: entita' completa
# ---------------------------------------------------------------------------


def test_import_races_fixture(tmp_path):
    d = tmp_path / "raw"
    d.mkdir()
    (d / "data_races.xml").write_text(RACES_XML, encoding="utf-8")
    races = pb.import_races(d, strict_playable=False)
    by_name = {r["name"]: r for r in races}

    dwarf = by_name["Dwarf"]
    assert dwarf["size"] == "medium"
    assert dwarf["abilityAdjustments"] == {"con": 2, "wis": 2, "cha": -2}
    assert dwarf["flexible"] is False
    assert dwarf["playable"] is True
    assert dwarf["source"] == "CRB"

    human = by_name["Human"]
    assert human["flexible"] is True
    assert human["abilityAdjustments"] is None  # scelta, non dato fisso
    assert human["playable"] is True
    assert human["source"] is None  # il blocco Human reale non ha Src: dichiarato

    halfling = by_name["Halfling"]
    assert halfling["size"] == "small"

    aasimar = by_name["Aasimar"]
    assert aasimar["abilityAdjustments"] is None  # non nel dato: dichiarato
    assert aasimar["flexible"] is False
    assert aasimar["playable"] is True

    shabti = by_name["Shabti"]
    assert shabti["size"] is None  # nessun tratto taglia: dichiarato
    assert shabti["abilityAdjustments"] == {"con": 2, "cha": 2}
    assert shabti["playable"] is False  # fuori dalla lista esplicita


def test_races_mai_description(tmp_path):
    d = tmp_path / "raw"
    d.mkdir()
    (d / "data_races.xml").write_text(RACES_XML, encoding="utf-8")
    for r in pb.import_races(d, strict_playable=False):
        assert "description" not in {k.lower() for k in r}
        assert "desc" not in {k.lower() for k in r}


def test_playable_list_esplicita_e_validata(tmp_path):
    # la lista giocabili PC e' dichiarata nell'importer, NON un'euristica:
    # ogni nome della lista deve esistere nel dataset (validazione strict)
    d = tmp_path / "raw"
    d.mkdir()
    (d / "data_races.xml").write_text(RACES_XML, encoding="utf-8")
    with pytest.raises(ValueError, match="giocabili"):
        pb.import_races(d, strict_playable=True)
    # e le razze giocabili della fixture ci sono tutte nella lista
    for name in ("Dwarf", "Human", "Halfling", "Aasimar"):
        assert name in pb.PLAYABLE_PC_RACES
    assert "Shabti" not in pb.PLAYABLE_PC_RACES


# ---------------------------------------------------------------------------
# import_alternative_traits
# ---------------------------------------------------------------------------


def test_import_alternative_traits_fixture(tmp_path):
    d = tmp_path / "raw"
    d.mkdir()
    (d / "data_races_alternative_traits.xml").write_text(
        ALT_TRAITS_XML, encoding="utf-8"
    )
    traits = pb.import_alternative_traits(d)
    assert len(traits) == 3
    by_trait = {t["trait"]: t for t in traits}

    ap = by_trait["Adoptive Parentage"]
    assert ap["race"] == "Human"
    assert ap["replaces"] == ["Bonus Feat"]
    assert ap["changes"] == []
    assert ap["source"] == "ARG"

    dt = by_trait["Dual Talent"]
    assert dt["replaces"] == ["Bonus Feat", "Skilled"]
    assert dt["changes"] == ["Ability Bonus"]

    ae = by_trait["Ancient Enmity"]
    assert ae["race"] == "Dwarf"
    assert ae["replaces"] == ["Hatred"]

    # mai description PI
    for t in traits:
        assert "description" not in {k.lower() for k in t}


# ---------------------------------------------------------------------------
# main() end-to-end su radice finta
# ---------------------------------------------------------------------------


def test_main_scrive_i_due_json(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "data_races.xml").write_text(RACES_XML, encoding="utf-8")
    (raw / "data_races_alternative_traits.xml").write_text(
        ALT_TRAITS_XML, encoding="utf-8"
    )
    out = tmp_path / "out"
    rc = pb.main(["--raw-dir", str(raw), "--out-dir", str(out), "--no-strict-playable"])
    assert rc == 0

    races = json.loads((out / "pathbuilder-races.json").read_text("utf-8"))
    prov = races["_provenance"]
    assert "Pathbuilder" in prov["source"]
    assert prov["license"]
    assert prov["generated_by"].endswith("import_pathbuilder_races.py")
    assert "MAI" in prov["desc_policy"] or "mai" in prov["desc_policy"]
    assert races["counts"]["races"] == 5
    assert races["counts"]["playable"] == 4
    assert races["counts"]["flexible"] == 1
    assert races["counts"]["withAbilityAdjustments"] == 3
    # report delle assenze dichiarate
    assert "Aasimar" in races["report"]["racesWithoutAbilityData"]
    assert "Shabti" in races["report"]["racesWithoutSize"]
    assert "Human" in races["report"]["racesWithoutSource"]
    assert "description" not in {k.lower() for r in races["races"] for k in r}

    traits = json.loads((out / "pathbuilder-race-traits.json").read_text("utf-8"))
    assert traits["_provenance"]["license"]
    assert traits["counts"]["traits"] == 3
    assert traits["counts"]["races"] == 2


# ---------------------------------------------------------------------------
# Smoke sui dati REALI (salta se il dataset non c'e'): conteggi e spot-check.
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[1]
REAL_RAW = REPO_ROOT / "data/reference/pi_local_only/pathbuilder"

REAL_REASON = "dataset Pathbuilder assente (pi_local_only non committato)"


@pytest.mark.skipif(not (REAL_RAW / "data_races.xml").is_file(), reason=REAL_REASON)
def test_dati_reali_races_conteggi_e_spot_check():
    races = pb.import_races(REAL_RAW)
    assert len(races) == 74
    by_name = {r["name"]: r for r in races}

    # spot-check RAW: Dwarf +2 Cos/+2 Sag/-2 Car; Halfling small;
    # Human flex (+2 a scelta, contratto E6-A6); Kasatha +2 Des/+2 Sag
    assert by_name["Dwarf"]["abilityAdjustments"] == {"con": 2, "wis": 2, "cha": -2}
    assert by_name["Dwarf"]["size"] == "medium"
    assert by_name["Halfling"]["size"] == "small"
    assert by_name["Halfling"]["abilityAdjustments"] == {"dex": 2, "cha": 2, "str": -2}
    assert by_name["Human"]["flexible"] is True
    assert by_name["Human"]["abilityAdjustments"] is None
    assert by_name["Kasatha"]["abilityAdjustments"] == {"dex": 2, "wis": 2}
    assert by_name["Shabti"]["abilityAdjustments"] == {"con": 2, "cha": 2}

    # conteggi dichiarati (ricognizione 2026-08-07)
    assert sum(1 for r in races if r["abilityAdjustments"]) == 15
    assert sum(1 for r in races if r["flexible"]) == 3
    assert sum(1 for r in races if r["playable"]) == 37
    assert sum(1 for r in races if r["size"] is None) == 22

    # le 26 razze del catalogo curato esistono tutte nel dataset PB
    curated = json.loads((Path(pb.DEFAULT_OUT_DIR) / "races.json").read_text("utf-8"))
    for c in curated:
        assert c["name"] in by_name, f"razza curated assente in PB: {c['name']}"


@pytest.mark.skipif(
    not (REAL_RAW / "data_races_alternative_traits.xml").is_file(), reason=REAL_REASON
)
def test_dati_reali_alternative_traits():
    traits = pb.import_alternative_traits(REAL_RAW)
    assert len(traits) == 702
    assert len({t["race"] for t in traits}) == 59
    by_trait = {t["trait"]: t for t in traits}
    dt = by_trait["Dual Talent"]
    assert dt["race"] == "Human"
    assert dt["replaces"] == ["Bonus Feat", "Skilled"]
    assert dt["changes"] == ["Ability Bonus"]
    assert dt["source"] == "ARG"
    # ogni tratto sostituisce o cambia qualcosa (verificato: nessuna riga orfana)
    assert all(t["replaces"] or t["changes"] for t in traits)
