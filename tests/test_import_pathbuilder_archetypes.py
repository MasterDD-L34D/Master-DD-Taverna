"""Test per tools/import_pathbuilder_archetypes.py — archetipi PB (slice D2).

Slice D2 (piano 2026-08-02): import dei 42 `data_archetypes_*.xml` (5.069
righe, 1.361 archetipi) da `data/reference/pi_local_only/pathbuilder/` (PI
local-only, MAI committato) verso UN JSON committato in pathmaster-dd
src/data/: pathbuilder-archetypes.json — per classe, per archetipo:
source, race (archetipi razziali) ed entries {special, level, replaced[],
changed[], effectHook?}.

Forma reale dei file (ricognizione 2026-08-07): <Root><Row>; <ArchetypeName>
compare SOLO sulla prima riga del blocco archetipo (insieme a <Source>,
<Details> — PI, mai esportata — e <Ref>); le righe seguenti ereditano
l'archetipo corrente. Ogni riga e' una voce di modifica: <ArchetypeSpecial>,
<Level>, <EffectMethod> (hook interno PB, non un effetto), <Display>,
<Changed>, <Replaced> (piu' voci separate da '&', con suffissi progressivi
tipo "Trap Sense +1&Trap Sense +2"), <Completed> (sentinella di fine blocco:
righe con SOLO <Completed> sono saltate), <Race> (archetipi razziali, una
riga per archetipo). Tre righe hanno <ArchetypeSpecial> senza <Level>:
level null dichiarato.

Policy OGL: il JSON committato non include MAI <Details> (testo Paizo PI).
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools import import_pathbuilder_archetypes as pb

# ---------------------------------------------------------------------------
# Fixture: forma reale (campi nell'ordine osservato nei file veri).
# ---------------------------------------------------------------------------

BARBARIAN_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Root xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
\t<Row>
\t\t<ArchetypeName>Armored Hulk</ArchetypeName>
\t\t<ArchetypeSpecial>Armor Proficiency</ArchetypeSpecial>
\t\t<Level>1</Level>
\t\t<EffectMethod>armoredHulkArmor</EffectMethod>
\t\t<Display>false</Display>
\t\t<Changed>Proficiencies</Changed>
\t\t<Details>Some barbarians disdain the hides and leather...</Details>
\t\t<Source>UC</Source>
\t\t<Ref>http://paizo.com/pathfinderRPG/prd/ultimateCombat/classArchetypes/barbarian.html</Ref>
\t</Row>
\t<Row>
\t\t<ArchetypeSpecial>Indomitable Stance</ArchetypeSpecial>
\t\t<Level>1</Level>
\t\t<Display>true</Display>
\t\t<Replaced>Fast Movement</Replaced>
\t</Row>
\t<Row>
\t\t<ArchetypeSpecial>Resilience of Steel</ArchetypeSpecial>
\t\t<Level>3</Level>
\t\t<Display>true</Display>
\t\t<Replaced>Trap Sense +1&amp;Trap Sense +2&amp;Trap Sense +3&amp;Trap Sense +4&amp;Trap Sense +5&amp;Trap Sense +6</Replaced>
\t\t<Completed>Yes</Completed>
\t</Row>
\t<Row>
\t\t<ArchetypeName>Drunken Brute</ArchetypeName>
\t\t<ArchetypeSpecial>Raging Drunk</ArchetypeSpecial>
\t\t<Level>1</Level>
\t\t<Display>true</Display>
\t\t<Replaced>Fast Movement</Replaced>
\t\t<Details>Barbarians are known for their ability to consume potent...</Details>
\t\t<Source>APG</Source>
\t\t<Ref>http://paizo.com/pathfinderRPG/prd/advanced/coreClasses/barbarian.html</Ref>
\t</Row>
\t<Row>
\t\t<Completed>Yes</Completed>
\t</Row>
\t<Row>
\t\t<ArchetypeName>Feral Gnasher</ArchetypeName>
\t\t<ArchetypeSpecial>Savage Bite</ArchetypeSpecial>
\t\t<Level>1</Level>
\t\t<Display>true</Display>
\t\t<Replaced>Fast Movement</Replaced>
\t\t<Race>Goblin</Race>
\t\t<Details>Feral gnashers grow up in the wild...</Details>
\t\t<Source>ARG</Source>
\t</Row>
\t<Row>
\t\t<ArchetypeSpecial>Lockjaw</ArchetypeSpecial>
\t\t<Level>3</Level>
\t\t<Display>true</Display>
\t\t<Replaced>Trap Sense +1&amp;Trap Sense +2&amp;Trap Sense +3</Replaced>
\t\t<Completed>Yes</Completed>
\t</Row>
</Root>
"""

ALCHEMIST_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Root xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
\t<Row>
\t\t<ArchetypeName>Clone Master</ArchetypeName>
\t\t<ArchetypeSpecial>Bomb</ArchetypeSpecial>
\t\t<EffectMethod>cloneMasterBomb</EffectMethod>
\t\t<Display>false</Display>
\t\t<Changed>Bomb 1&amp;Bomb 2&amp;Bomb 3</Changed>
\t\t<Details>Clone masters practice duplicating existing creatures...</Details>
\t\t<Source>UM</Source>
\t\t<Ref>http://paizo.com/pathfinderRPG/prd/ultimateMagic/spellcastingClassOptions/alchemist.html</Ref>
\t</Row>
\t<Row>
\t\t<ArchetypeSpecial>Lesser Simulacrum</ArchetypeSpecial>
\t\t<Level>7</Level>
\t\t<Display>true</Display>
\t\t<Completed>Yes</Completed>
\t</Row>
</Root>
"""


def _write_raw(tmp_path, files):
    d = tmp_path / "raw"
    d.mkdir()
    for name, xml in files.items():
        (d / name).write_text(xml, encoding="utf-8")
    return d


# ---------------------------------------------------------------------------
# Raggruppamento blocchi archetipo (ArchetypeName solo sulla prima riga)
# ---------------------------------------------------------------------------


def test_group_archetype_blocks(tmp_path):
    d = _write_raw(tmp_path, {"data_archetypes_barbarian.xml": BARBARIAN_XML})
    classes = pb.import_archetypes(d)
    assert list(classes) == ["barbarian"]
    archs = classes["barbarian"]
    assert list(archs) == ["Armored Hulk", "Drunken Brute", "Feral Gnasher"]


def test_entries_forma_e_suffissi_progressivi(tmp_path):
    d = _write_raw(tmp_path, {"data_archetypes_barbarian.xml": BARBARIAN_XML})
    hulk = pb.import_archetypes(d)["barbarian"]["Armored Hulk"]
    assert hulk["source"] == "UC"
    assert hulk["race"] is None
    entries = hulk["entries"]
    assert [e["special"] for e in entries] == [
        "Armor Proficiency",
        "Indomitable Stance",
        "Resilience of Steel",
    ]
    # EffectMethod dichiarato come hook interno, non effetto
    assert entries[0]["effectHook"] == "armoredHulkArmor"
    assert "effectHook" not in entries[1]
    assert entries[0]["changed"] == ["Proficiencies"]
    assert entries[0]["replaced"] == []
    assert entries[1]["replaced"] == ["Fast Movement"]
    # i suffissi +N restano parte del nome (progressione onesta, non dedotta)
    assert entries[2]["replaced"] == [f"Trap Sense +{n}" for n in range(1, 7)]
    assert [e["level"] for e in entries] == [1, 1, 3]


def test_sentinella_completed_saltata(tmp_path):
    # la riga con SOLO <Completed>Yes</Completed> chiude il blocco: non e' una entry
    d = _write_raw(tmp_path, {"data_archetypes_barbarian.xml": BARBARIAN_XML})
    brute = pb.import_archetypes(d)["barbarian"]["Drunken Brute"]
    assert len(brute["entries"]) == 1
    assert brute["entries"][0]["special"] == "Raging Drunk"


def test_archetipo_raziale(tmp_path):
    d = _write_raw(tmp_path, {"data_archetypes_barbarian.xml": BARBARIAN_XML})
    gnasher = pb.import_archetypes(d)["barbarian"]["Feral Gnasher"]
    assert gnasher["race"] == "Goblin"


def test_special_senza_level_dichiarato(tmp_path):
    # forma reale (Clone Master alchemist): <ArchetypeSpecial> senza <Level>
    d = _write_raw(tmp_path, {"data_archetypes_alchemist.xml": ALCHEMIST_XML})
    clone = pb.import_archetypes(d)["alchemist"]["Clone Master"]
    bomb = clone["entries"][0]
    assert bomb["special"] == "Bomb"
    assert bomb["level"] is None  # assente nel dato: dichiarato, mai inventato
    assert bomb["changed"] == ["Bomb 1", "Bomb 2", "Bomb 3"]


def test_mai_details_pi(tmp_path):
    d = _write_raw(tmp_path, {"data_archetypes_barbarian.xml": BARBARIAN_XML})
    for arch in pb.import_archetypes(d)["barbarian"].values():
        assert "details" not in {k.lower() for k in arch}
        for e in arch["entries"]:
            keys = {k.lower() for k in e}
            assert "details" not in keys
            assert "description" not in keys
            assert "desc" not in keys


# ---------------------------------------------------------------------------
# main() end-to-end su radice finta
# ---------------------------------------------------------------------------


def test_main_scrive_il_json(tmp_path):
    raw = _write_raw(
        tmp_path,
        {
            "data_archetypes_barbarian.xml": BARBARIAN_XML,
            "data_archetypes_alchemist.xml": ALCHEMIST_XML,
        },
    )
    out = tmp_path / "out"
    rc = pb.main(["--raw-dir", str(raw), "--out-dir", str(out)])
    assert rc == 0

    data = json.loads((out / "pathbuilder-archetypes.json").read_text("utf-8"))
    prov = data["_provenance"]
    assert "Pathbuilder" in prov["source"]
    assert prov["license"]
    assert "MAI" in prov["desc_policy"]
    assert prov["generated_by"].endswith("import_pathbuilder_archetypes.py")
    assert data["counts"]["classes"] == 2
    assert data["counts"]["archetypes"] == 4
    assert data["counts"]["entries"] == 8
    assert data["counts"]["entriesWithoutLevel"] == 1
    assert data["report"]["skippedCompletedSentinels"] == 1
    assert data["report"]["entriesWithoutLevel"] == [
        {"class": "alchemist", "archetype": "Clone Master", "special": "Bomb"}
    ]
    # nessuna Details/desc nelle voci
    for cls in data["classes"].values():
        for arch in cls.values():
            for e in arch["entries"]:
                assert "details" not in {k.lower() for k in e}


# ---------------------------------------------------------------------------
# Smoke sui dati REALI (salta se il dataset non c'e'): conteggi e spot-check.
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[1]
REAL_RAW = REPO_ROOT / "data/reference/pi_local_only/pathbuilder"

REAL_REASON = "dataset Pathbuilder assente (pi_local_only non committato)"


@pytest.mark.skipif(
    not (REAL_RAW / "data_archetypes_barbarian.xml").is_file(), reason=REAL_REASON
)
def test_dati_reali_conteggi():
    classes = pb.import_archetypes(REAL_RAW)
    # ricognizione 2026-08-07: 42 file, 1.361 archetipi, 5.069 righe di cui
    # 6 sentinelle Completed-only e 3 entry senza <Level>
    assert len(classes) == 42
    assert sum(len(a) for a in classes.values()) == 1361
    entries = [
        e for a in classes.values() for arch in a.values() for e in arch["entries"]
    ]
    assert len(entries) == 5063
    assert sum(1 for e in entries if e["level"] is None) == 3


@pytest.mark.skipif(
    not (REAL_RAW / "data_archetypes_barbarian.xml").is_file(), reason=REAL_REASON
)
def test_dati_reali_spot_check_armored_hulk():
    classes = pb.import_archetypes(REAL_RAW)
    hulk = classes["barbarian"]["Armored Hulk"]
    assert hulk["source"] == "UC"
    by_special = {e["special"]: e for e in hulk["entries"]}
    assert by_special["Indomitable Stance"]["replaced"] == ["Fast Movement"]
    assert by_special["Armored Swiftness"]["replaced"] == ["Uncanny Dodge"]
    assert by_special["Resilience of Steel"]["replaced"] == [
        f"Trap Sense +{n}" for n in range(1, 7)
    ]
    assert by_special["Armor Proficiency"]["effectHook"] == "armoredHulkArmor"


@pytest.mark.skipif(
    not (REAL_RAW / "data_archetypes_oracle.xml").is_file(), reason=REAL_REASON
)
def test_dati_reali_spot_check_spirit_guide():
    classes = pb.import_archetypes(REAL_RAW)
    guide = classes["oracle"]["Spirit Guide"]
    assert guide["source"] == "ACG"
    bonded = next(e for e in guide["entries"] if e["special"] == "Bonded Spirit")
    assert bonded["level"] == 3
    # numerazione slot PB: Revelation 2/3/5 = gli slot di 3°/7°/15° (RAW ACG 106)
    assert bonded["replaced"] == ["Revelation 2", "Revelation 3", "Revelation 5"]


@pytest.mark.skipif(
    not (REAL_RAW / "data_archetypes_alchemist.xml").is_file(), reason=REAL_REASON
)
def test_dati_reali_homebrew_assente_e_razziali():
    classes = pb.import_archetypes(REAL_RAW)
    # "alchemist bombardier" e' homebrew di campagna (archetypes.ts): NON
    # deve esistere nel dataset PB -- se comparisse va investigato, non fuso
    assert "Bombardier" not in classes["alchemist"]
    # archetipi razziali: race dal campo <Race>, dichiarato null altrove
    gnasher = classes["barbarian"]["Feral Gnasher"]
    assert isinstance(gnasher["race"], str) and gnasher["race"]
    assert classes["barbarian"]["Armored Hulk"]["race"] is None
    # classi PB fuori dal nostro corpus classi: importate comunque (dataset)
    assert "unchained_rogue" in classes
    assert "omdura" in classes
