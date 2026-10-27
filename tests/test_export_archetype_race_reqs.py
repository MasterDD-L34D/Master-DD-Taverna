"""Test per tools/export_archetype_race_reqs.py — requisiti razziali archetipi.

Slice D6 (piano 2026-08-02): i `mechanics.race_req[]` del catalogo curato
Taverna `data/reference/ogl/archetypes.json` (fonte AoN, OGL) diventano un
dataset committato in pathmaster-dd `src/data/taverna-archetype-race-reqs.json`
per la legality archetipi del builder (ok / ko con motivo / unknown).

Policy: SOLO nomi + meccaniche strutturate (classe, nome, race_req,
source_id). MAI description (resta nel catalogo, non serve al motore).
Gli archetipi senza race_req NON compaiono: l'assenza dal dataset e' dato
("nessun requisito razziale attestato dalla fonte curata"), dichiarato dal
consumatore, non dal file.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools import export_archetype_race_reqs as ex

ARCHETYPES = {
    "_license": "OGL",
    "entries": [
        {
            "name": "Feral Gnasher",
            "source_id": "archetype:barbarian_feral_gnasher",
            "description": "Feral gnashers grow up in the wild...",
            "mechanics": {
                "class": "Barbarian",
                "race_req": ["Goblin"],
            },
        },
        {
            "name": "Armored Hulk",
            "source_id": "archetype:barbarian_armored_hulk",
            "description": "Some barbarians disdain...",
            "mechanics": {
                "class": "Barbarian",
                "race_req": None,
            },
        },
        {
            "name": "Bramble Brewer",
            "source_id": "archetype:alchemist_bramble_brewer",
            "mechanics": {
                "class": "Alchemist",
                "race_req": ["Half-Elf", "Elf"],
            },
        },
        {
            "name": "Senza Mechanics",
            "source_id": "archetype:senza",
            "mechanics": None,
        },
    ],
}


def test_extract_only_entries_with_race_req():
    out = ex.extract_race_reqs(ARCHETYPES)
    names = [(r["class"], r["name"]) for r in out]
    assert names == [
        ("Barbarian", "Feral Gnasher"),
        ("Alchemist", "Bramble Brewer"),
    ]


def test_no_description_exported():
    out = ex.extract_race_reqs(ARCHETYPES)
    blob = json.dumps(out)
    assert "description" not in blob
    assert "Feral gnashers grow up" not in blob


def test_race_req_list_preserved_verbatim():
    out = ex.extract_race_reqs(ARCHETYPES)
    bramble = next(r for r in out if r["name"] == "Bramble Brewer")
    assert bramble["race_req"] == ["Half-Elf", "Elf"]
    assert bramble["source_id"] == "archetype:alchemist_bramble_brewer"


def test_build_file_shape_and_counts():
    doc = ex.build_file(ARCHETYPES, generated_at="2026-08-08T00:00:00+00:00")
    assert doc["generated_at"] == "2026-08-08T00:00:00+00:00"
    assert doc["counts"]["with_race_req"] == 2
    assert doc["counts"]["entries_total"] == 4
    assert doc["counts"]["classes"] == {"Alchemist": 1, "Barbarian": 1}
    assert len(doc["race_reqs"]) == 2
    assert "_provenance" in doc
    assert "license" in doc["_provenance"]


def test_real_catalog_matches_declared_count(tmp_path):
    """Sul catalogo reale committato: 79 entry con race_req (ricognizione D6).

    Se il catalogo Taverna cambia, questo test fallisce e il conteggio va
    ri-verificato — mai un update silenzioso del numero."""
    catalog = Path(__file__).resolve().parents[1] / "data/reference/ogl/archetypes.json"
    data = json.loads(catalog.read_text(encoding="utf-8"))
    out = ex.extract_race_reqs(data)
    assert len(out) == 79
