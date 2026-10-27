"""Test per tools/export_race_standard_traits.py — tratti razziali standard.

Slice D6 (piano 2026-08-02): la legality dei tratti ALTERNATIVI Pathbuilder
("un tratto che sostituisce X richiede che la razza abbia X") ha bisogno dei
tratti STANDARD per razza. Fonte curata: `data/reference/ogl/races.json`
(Taverna, mechanics.traits[].name). Export di SOLI NOMI in pathmaster-dd
`src/data/taverna-race-standard-traits.json`.

Policy: mai i testi dei tratti (description Paizo, restano nel catalogo).
Le razze senza lista tratti nel catalogo compaiono nel report `without_traits`
— dichiarate, mai inventate.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools import export_race_standard_traits as ex

RACES = {
    "entries": [
        {
            "name": "Human",
            "mechanics": {
                "traits": [
                    {"name": "Bonus Feat", "text": "Humans select one extra feat..."},
                    {
                        "name": "Skilled",
                        "text": "Humans gain an additional skill rank...",
                    },
                ],
            },
        },
        {
            "name": "Dwarf",
            "mechanics": {
                "traits": [
                    {"name": "Darkvision", "text": "Dwarves can see in the dark..."},
                    {"name": "Greed", "text": "Dwarves gain a +2 racial bonus..."},
                ],
            },
        },
        {
            "name": "Senza Tratti",
            "mechanics": {},
        },
    ],
}


def test_extract_names_only():
    out = ex.extract_traits(RACES)
    assert out["Human"] == ["Bonus Feat", "Skilled"]
    assert out["Dwarf"] == ["Darkvision", "Greed"]
    blob = json.dumps(out)
    assert "Humans select one extra feat" not in blob
    assert "text" not in blob


def test_races_without_traits_are_reported_not_invented():
    doc = ex.build_file(RACES, generated_at="2026-08-08T00:00:00+00:00")
    assert "Senza Tratti" not in doc["races"]
    assert doc["counts"]["without_traits"] == ["Senza Tratti"]
    assert doc["counts"]["races_with_traits"] == 2


def test_file_shape():
    doc = ex.build_file(RACES, generated_at="2026-08-08T00:00:00+00:00")
    assert "_provenance" in doc
    assert "license" in doc["_provenance"]
    assert doc["generated_at"] == "2026-08-08T00:00:00+00:00"


def test_real_catalog_covers_pb_playable_races():
    """Sul catalogo reale: le 37 razze giocabili PB devono avere i tratti.

    Il match per nome normalizzato e' lo stesso del motore (trim+casefold):
    una razza giocabile PB assente dal curato Taverna e' un buco DICHIARATO
    che questo test blocca — la legality dei suoi tratti sarebbe tutta
    unknown non detta."""
    catalog = Path(__file__).resolve().parents[1] / "data/reference/ogl/races.json"
    data = json.loads(catalog.read_text(encoding="utf-8"))
    doc = ex.build_file(data)
    playable = [
        "Dwarf",
        "Elf",
        "Gnome",
        "Half-Elf",
        "Half-Orc",
        "Halfling",
        "Human",
        "Aasimar",
        "Catfolk",
        "Dhampir",
        "Drow",
        "Fetchling",
        "Goblin",
        "Hobgoblin",
        "Ifrit",
        "Kobold",
        "Orc",
        "Oread",
        "Ratfolk",
        "Sylph",
        "Tengu",
        "Tiefling",
        "Undine",
        "Changeling",
        "Duergar",
        "Gillman",
        "Grippli",
        "Kitsune",
        "Merfolk",
        "Nagaji",
        "Samsaran",
        "Strix",
        "Suli",
        "Svirfneblin",
        "Vanara",
        "Vishkanya",
        "Wayang",
    ]
    have = {k.strip().lower() for k in doc["races"]}
    missing = [r for r in playable if r.strip().lower() not in have]
    assert missing == []
