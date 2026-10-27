"""Test per tools/import_pathbuilder_raw.py — parser XML raw Pathbuilder (APK).

Fixture XML inline (MAI rete): forma reale dei file
data/reference/pi_local_only/pathbuilder/*.xml (ricognizione 2026-08-01):
<Root><Row> con campi per tipo; requisiti feat strutturati nei campi r*
(rStat `idx£min` con `&` tra vincoli, mappa 0=FOR..5=CAR verificata sui dati
reali: Dodge `1£13` = "Dex 13"); specials con Special/Requirements/
RequiredSpecial1-2/LevelAP/Description/Source/Ref.

Policy: i JSON committati dei FEAT non includono mai la Description (testo
Paizo PI); il dataset grezzo resta in pi_local_only (gitignored).
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools import import_pathbuilder_raw as pb

# ---------------------------------------------------------------------------
# Fixture: forma reale (campi nell'ordine osservato nei file veri).
# ---------------------------------------------------------------------------

FEATS_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Root xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
\t<Row>
\t\t<FeatName>Dodge</FeatName>
\t\t<Category>0</Category>
\t\t<EffectMethod>dodge</EffectMethod>
\t\t<rStat>1£13</rStat>
\t\t<MaxTakable>1</MaxTakable>
\t\t<Prerequisites>Dex 13.</Prerequisites>
\t\t<Description>You gain a +1 dodge bonus to your AC.</Description>
\t\t<URL>http://www.d20pfsrd.com/feats/combat-feats/dodge-combat---final</URL>
\t\t<Source>CRB</Source>
\t</Row>
\t<Row>
\t\t<FeatName>Betrayal Sense</FeatName>
\t\t<Category>0&amp;3</Category>
\t\t<rStat>4£13</rStat>
\t\t<rClassLevel>Rogue£3&amp;Unchained Rogue£3</rClassLevel>
\t\t<rClassFeature>Trap Sense</rClassFeature>
\t\t<MaxTakable>1</MaxTakable>
\t\t<Prerequisites>Wis 13, rogue level 3rd, trap sense class feature.</Prerequisites>
\t\t<Description>x</Description>
\t\t<URL/>
\t\t<Source>UI</Source>
\t</Row>
\t<Row>
\t\t<FeatName>Augment Summoning</FeatName>
\t\t<Category>1</Category>
\t\t<rFeatsWithSpecificInfo>Spell Focus£conjuration</rFeatsWithSpecificInfo>
\t\t<MaxTakable>1</MaxTakable>
\t\t<Prerequisites>Spell Focus (conjuration).</Prerequisites>
\t\t<Description>x</Description>
\t\t<Source>CRB</Source>
\t</Row>
\t<Row>
\t\t<FeatName>Adept Channel</FeatName>
\t\t<Category>1</Category>
\t\t<rStat>5£13</rStat>
\t\t<rCasterLevel>4</rCasterLevel>
\t\t<rMagicRef>1</rMagicRef>
\t\t<rClassFeature>Familiar</rClassFeature>
\t\t<MaxTakable>1</MaxTakable>
\t\t<Prerequisites>Ability to cast divine spells, summon familiar class ability, caster level 4th, Cha 13.</Prerequisites>
\t\t<Description>x</Description>
\t\t<Source>HA</Source>
\t</Row>
\t<Row>
\t\t<FeatName>Alien Mindpaths</FeatName>
\t\t<Category>3</Category>
\t\t<rRace>Android&amp;Kasatha&amp;Lashunta&amp;Triaxian</rRace>
\t\t<rBAB>6</rBAB>
\t\t<rCharLevel>10</rCharLevel>
\t\t<MaxTakable>1</MaxTakable>
\t\t<Prerequisites>Android, kasatha, lashunta, or Triaxian.</Prerequisites>
\t\t<Description>x</Description>
\t\t<Source>People of the Stars</Source>
\t</Row>
\t<Row>
\t\t<FeatName>Spring Attack</FeatName>
\t\t<Category>0</Category>
\t\t<rFeats>Dodge&amp;Mobility</rFeats>
\t\t<rBAB>4</rBAB>
\t\t<MaxTakable>1</MaxTakable>
\t\t<Prerequisites>Dex 13, Dodge, Mobility, base attack bonus +4.</Prerequisites>
\t\t<Description>x</Description>
\t\t<Source>CRB</Source>
\t</Row>
</Root>
"""

SPECIALS_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Root xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
\t<Row>
\t\t<Special>Battle Roar</Special>
\t\t<LevelAP>5</LevelAP>
\t\t<RequiredSpecial1>Intimidating Glare</RequiredSpecial1>
\t\t<Requirements>Barbarian 6, intimidating glare</Requirements>
\t\t<Description>When the character successfully demoralizes...</Description>
\t\t<Source>ACG</Source>
\t\t<Ref>http://paizo.com/pathfinderRPG/prd/advancedClassGuide/classOptions/barbarian.html#rage-powers</Ref>
\t</Row>
\t<Row>
\t\t<Special>Reckless Abandon</Special>
\t\t<Description>While raging, the barbarian can take a -1 penalty to AC...</Description>
\t\t<Source>APG</Source>
\t\t<Ref>http://paizo.com/pathfinderRPG/prd/advancedPlayersGuide/coreClasses/barbarian.html#rage-powers</Ref>
\t</Row>
</Root>
"""


# ---------------------------------------------------------------------------
# Parser dei requisiti strutturati (r*)
# ---------------------------------------------------------------------------


def test_parse_rstat_mappa_indice_caratteristica():
    assert pb.parse_rstat("1£13") == {"DEX": 13}
    assert pb.parse_rstat("3£13") == {"INT": 13}
    assert pb.parse_rstat("5£13&1£13") == {"CHA": 13, "DEX": 13}
    assert pb.parse_rstat("0£13") == {"STR": 13}
    assert pb.parse_rstat("2£15&4£15") == {"CON": 15, "WIS": 15}
    assert pb.parse_rstat(None) == {}


def test_parse_lista_ampersand():
    assert pb.parse_amp_list("Dodge&Mobility") == ["Dodge", "Mobility"]
    assert pb.parse_amp_list("Human") == ["Human"]
    assert pb.parse_amp_list(None) == []


def test_parse_class_level():
    assert pb.parse_class_level("Rogue£3&Unchained Rogue£3") == [
        {"class": "Rogue", "level": 3},
        {"class": "Unchained Rogue", "level": 3},
    ]
    assert pb.parse_class_level("Wizard£1") == [{"class": "Wizard", "level": 1}]
    assert pb.parse_class_level(None) == []


def test_parse_feat_with_info():
    assert pb.parse_feat_with_info("Skill Focus£Stealth") == [
        {"feat": "Skill Focus", "info": "Stealth"}
    ]
    assert pb.parse_feat_with_info(
        "Spell Focus£conjuration&Spell Focus£necromancy"
    ) == [
        {"feat": "Spell Focus", "info": "conjuration"},
        {"feat": "Spell Focus", "info": "necromancy"},
    ]
    assert pb.parse_feat_with_info(None) == []


def test_parse_magic_ref():
    assert pb.parse_magic_ref("0") == "arcane"
    assert pb.parse_magic_ref("1") == "divine"
    assert pb.parse_magic_ref(None) is None


# ---------------------------------------------------------------------------
# Entita': feats (senza Description, policy OGL)
# ---------------------------------------------------------------------------


def test_feats_from_rows_campi_decodificati():
    entries = pb.feats_from_rows(pb.iter_rows(pb.parse_xml(FEATS_XML)))
    by_name = {e["name"]: e for e in entries}
    assert len(entries) == 6

    dodge = by_name["Dodge"]
    assert dodge["category"] == [0]
    assert dodge["max_takable"] == 1
    assert dodge["prerequisites_text"] == "Dex 13."
    assert dodge["requirements"]["ability_mins"] == {"DEX": 13}
    assert dodge["source"] == "CRB"
    assert dodge["url"].endswith("dodge-combat---final")
    assert dodge["effect_method"] == "dodge"

    bs = by_name["Betrayal Sense"]
    assert bs["category"] == [0, 3]
    assert bs["requirements"]["ability_mins"] == {"WIS": 13}
    assert bs["requirements"]["class_levels"] == [
        {"class": "Rogue", "level": 3},
        {"class": "Unchained Rogue", "level": 3},
    ]
    assert bs["requirements"]["class_features"] == ["Trap Sense"]

    aug = by_name["Augment Summoning"]
    assert aug["requirements"]["feats_with_info"] == [
        {"feat": "Spell Focus", "info": "conjuration"}
    ]

    ac = by_name["Adept Channel"]
    assert ac["requirements"]["magic_type"] == "divine"
    assert ac["requirements"]["caster_level_min"] == 4

    am = by_name["Alien Mindpaths"]
    assert am["requirements"]["races"] == ["Android", "Kasatha", "Lashunta", "Triaxian"]
    assert am["requirements"]["bab_min"] == 6
    assert am["requirements"]["char_level_min"] == 10

    sa = by_name["Spring Attack"]
    assert sa["requirements"]["feats"] == ["Dodge", "Mobility"]


def test_feats_mai_description():
    entries = pb.feats_from_rows(pb.iter_rows(pb.parse_xml(FEATS_XML)))
    for e in entries:
        keys = {k.lower() for k in e} | {k.lower() for k in e["requirements"]}
        assert "description" not in keys
        assert "desc" not in keys


# ---------------------------------------------------------------------------
# Entita': specials (class features) — raggruppamento per classe
# ---------------------------------------------------------------------------


def test_class_key_da_nome_file():
    assert pb.class_key_for_specials_file(
        "data_specials_barbarian_rage_powers.xml"
    ) == ("barbarian", "rage_powers")
    assert pb.class_key_for_specials_file(
        "data_specials_unchained_rogue_talents.xml"
    ) == ("unchained_rogue", "talents")
    assert pb.class_key_for_specials_file(
        "data_specials_oracle_mystery_battle.xml"
    ) == ("oracle", "mystery_battle")
    assert pb.class_key_for_specials_file(
        "data_specials_occultist_abjuration_focus_powers.xml"
    ) == ("occultist", "abjuration_focus_powers")
    assert pb.class_key_for_specials_file("data_specials_capstones.xml") == (
        "_shared",
        "capstones",
    )
    assert pb.class_key_for_specials_file("data_specials_variant_channeling.xml") == (
        "_shared",
        "variant_channeling",
    )


def test_specials_from_rows_campi():
    rows = pb.iter_rows(pb.parse_xml(SPECIALS_XML))
    feats = pb.specials_from_rows(rows)
    by_name = {f["name"]: f for f in feats}
    br = by_name["Battle Roar"]
    assert br["requirements"] == "Barbarian 6, intimidating glare"
    assert br["required_specials"] == ["Intimidating Glare"]
    assert br["level_ap"] == 5
    assert br["source"] == "ACG"
    assert br["ref"].startswith("http://paizo.com/")
    assert br["description"].startswith("When the character")
    ra = by_name["Reckless Abandon"]
    assert ra["required_specials"] == []
    assert ra["level_ap"] is None
    assert ra["requirements"] is None


def test_build_class_features_raggruppa(tmp_path):
    d = tmp_path / "raw"
    d.mkdir()
    (d / "data_specials_barbarian_rage_powers.xml").write_text(
        SPECIALS_XML, encoding="utf-8"
    )
    (d / "data_specials_capstones.xml").write_text(SPECIALS_XML, encoding="utf-8")
    payload = pb.build_class_features(d)
    classes = payload["classes"]
    assert set(classes) == {"barbarian", "_shared"}
    assert [f["name"] for f in classes["barbarian"]["rage_powers"]] == [
        "Battle Roar",
        "Reckless Abandon",
    ]
    assert payload["counts"]["barbarian"] == 2
    assert payload["counts"]["_shared"] == 2
    prov = payload["_provenance"]
    assert "Pathbuilder" in prov["source"]
    assert prov["license"]
    assert prov["generated_by"].endswith("import_pathbuilder_raw.py")


# ---------------------------------------------------------------------------
# Confronto con pcgen-feats (report, non merge)
# ---------------------------------------------------------------------------


def test_confronto_pcgen_nuovi_e_duplicati():
    pb_entries = [
        {"name": "Dodge"},
        {"name": "Reckless Abandon"},
        {"name": "Power Attack"},
        {"name": "Acrobatic  Steps"},
    ]
    pcgen_names = ["Dodge", "Power Attack", "Cleave", "acrobatic steps"]
    report = pb.compare_with_pcgen(pb_entries, pcgen_names)
    assert report["pathbuilder_count"] == 4
    assert report["pcgen_count"] == 4
    # confronto normalizzato (casefold + spazi collassati)
    assert sorted(report["duplicates"]) == ["Acrobatic  Steps", "Dodge", "Power Attack"]
    assert report["new_in_pathbuilder"] == ["Reckless Abandon"]
    assert report["new_count"] == 1


# ---------------------------------------------------------------------------
# main() end-to-end su radice finta
# ---------------------------------------------------------------------------


def _fake_raw_root(tmp_path: Path) -> Path:
    d = tmp_path / "raw"
    d.mkdir()
    (d / "data_feats.xml").write_text(FEATS_XML, encoding="utf-8")
    (d / "data_specials_barbarian_rage_powers.xml").write_text(
        SPECIALS_XML, encoding="utf-8"
    )
    return d


def test_main_scrive_i_due_json(tmp_path):
    raw = _fake_raw_root(tmp_path)
    out = tmp_path / "out"
    pcgen = {"entries": [{"name": "Dodge"}, {"name": "Power Attack"}]}
    (tmp_path / "pcgen-feats.json").write_text(json.dumps(pcgen), encoding="utf-8")
    rc = pb.main(
        [
            "--raw-dir",
            str(raw),
            "--out-dir",
            str(out),
            "--pcgen-feats",
            str(tmp_path / "pcgen-feats.json"),
        ]
    )
    assert rc == 0

    feats = json.loads((out / "pathbuilder-feats.json").read_text("utf-8"))
    assert len(feats["entries"]) == 6
    assert feats["_provenance"]["desc_policy"]
    assert "description" not in {k.lower() for e in feats["entries"] for k in e}
    cmp_ = feats["pcgen_comparison"]
    assert cmp_["duplicates"] == ["Dodge"]
    assert cmp_["new_count"] == 5

    cf = json.loads((out / "pathbuilder-class-features.json").read_text("utf-8"))
    assert cf["counts"]["barbarian"] == 2


# ---------------------------------------------------------------------------
# Provenance / licenza del dataset rilocato (policy PI)
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[1]
REAL_RAW = REPO_ROOT / "data/reference/pi_local_only/pathbuilder"


def test_pi_local_only_gitignored():
    gitignore = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "data/reference/pi_local_only/*" in gitignore


@pytest.mark.skipif(
    not (REAL_RAW / "data_feats.xml").is_file(),
    reason="dataset Pathbuilder assente (pi_local_only non committato)",
)
def test_provenance_file_dataset():
    prov = json.loads((REAL_RAW / "_provenance.json").read_text("utf-8"))
    assert "Pathbuilder" in prov["dataset"]
    assert "2026-08-02" in prov["source"]["permission"]
    assert "PI" in prov["license"]["descriptions"]
    assert "MAI" in prov["license"]["policy"]
    assert prov["contents"]["xml_datasets"] == 253


# ---------------------------------------------------------------------------
# Smoke sui dati REALI (salta se il dataset non c'e'): conteggi e spot-check.
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not (REAL_RAW / "data_feats.xml").is_file(),
    reason="dataset Pathbuilder assente (pi_local_only non committato)",
)
def test_dati_reali_conteggi_e_spot_check():
    feats = pb.feats_from_rows(
        pb.iter_rows(
            pb.parse_xml((REAL_RAW / "data_feats.xml").read_text(encoding="utf-8"))
        )
    )
    assert len(feats) == 3320
    by_name = {e["name"]: e for e in feats}
    assert by_name["Dodge"]["requirements"]["ability_mins"] == {"DEX": 13}
    assert by_name["Dodge"]["prerequisites_text"] == "Dex 13."

    cf = pb.build_class_features(REAL_RAW)
    assert cf["counts"]["barbarian"] == 228
    assert cf["counts"]["unchained_barbarian"] == 109
    rage = cf["classes"]["barbarian"]["rage_powers"]
    assert len(rage) == 228
    ra = next(f for f in rage if f["name"] == "Reckless Abandon")
    assert ra["source"] == "APG"
    assert ra["description"].startswith("While raging")

    # una classe e una razza dai dataset dedicati
    classes = pb.iter_rows(
        pb.parse_xml((REAL_RAW / "data_classes.xml").read_text(encoding="utf-8"))
    )
    assert len(classes) == 163
    barbarian = next(r for r in classes if r.findtext("Classname") == "Barbarian")
    assert barbarian.findtext("Source") == "CRB"

    races = pb.iter_rows(
        pb.parse_xml((REAL_RAW / "data_races.xml").read_text(encoding="utf-8"))
    )
    assert len(races) == 669
    dwarf_traits = [r for r in races if r.findtext("Race") == "Dwarf"]
    assert dwarf_traits
    assert any(r.findtext("Trait") == "Ability Bonus" for r in dwarf_traits)
