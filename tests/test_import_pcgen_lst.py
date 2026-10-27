"""Test per tools/import_pcgen_lst.py — parser LST PCGen -> catalogo legality.

Fixture LST inline (MAI rete): forma reale dei file
pcgen-repo/data/pathfinder/paizo/roleplaying_game/* (ricognizione
2026-08-01): TSV con primo campo = nome e tag CHIAVE:valore separati da
tab; .COPY= per gli oggetti visibili derivati da basi VISIBLE:NO; .MOD per
estensioni (es. liste di classi aggiunte); duplicati risolti last-wins.
"""

import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools import import_pcgen_lst as pc

# ---------------------------------------------------------------------------
# Fixture: forma reale (tab separati, colonne allineate come PrettyLST).
# ---------------------------------------------------------------------------

FEATS_LST = """\
# commento iniziale
SOURCELONG:Core Rulebook	SOURCESHORT:CR

Acrobatic	CATEGORY:FEAT	TYPE:General	DESC:You are skilled.	SOURCEPAGE:p.113
Dodge	CATEGORY:FEAT	TYPE:Combat	PREMULT:1,[PREVARGTEQ:PreStatScore_DEX,13],[PREVARGTEQ:FeatDexRequirement,15]	DESC:x	BONUS:COMBAT|AC|1|TYPE=Dodge	SOURCEPAGE:p.122
Power Attack	CATEGORY:FEAT	TYPE:Combat	PRETOTALAB:1	PREVARGTEQ:PreStatScore_STR,13	DESC:x	SOURCEPAGE:p.131
Great Cleave	CATEGORY:FEAT	TYPE:Combat	PREABILITY:2,CATEGORY=FEAT,Cleave,Power Attack	PRETOTALAB:4	PREVARGTEQ:PreStatScore_STR,13	DESC:x	SOURCEPAGE:p.124
Acrobatic Steps	CATEGORY:FEAT	TYPE:General	PREABILITY:1,CATEGORY=FEAT,Nimble Moves	PREMULT:1,[PREVARGTEQ:PreStatScore_DEX,15],[PREVARGTEQ:FeatDexRequirement,15]	DESC:x	SOURCEPAGE:p.113
Weapon Focus	CATEGORY:FEAT	TYPE:Combat	PRETOTALAB:1	STACK:NO	MULT:YES	CHOOSE:STRING|Dagger	DESC:x	SOURCEPAGE:p.136
Skill Focus	CATEGORY:FEAT	TYPE:General	PRESKILL:1,Acrobatics=5	DESC:x	SOURCEPAGE:p.134
Arcane Armor Training	CATEGORY:FEAT	TYPE:Combat	PREMULT:1,[PRECLASS:1,SPELLCASTER=3],[PREVARGTEQ:CasterLevel_Highest,3]	DESC:x	SOURCEPAGE:p.118
Exotic Weapon Proficiency	CATEGORY:FEAT	TYPE:Combat	PRETOTALAB:1	PREALIGN:LG,LG	DESC:x	SOURCEPAGE:p.123
Adept Channel	CATEGORY:FEAT	TYPE:General	PREFACT:1,Category=FEAT,TYPE.Channel Energy	DESC:x
Amateur Gunslinger	CATEGORY:FEAT	TYPE:Combat	!PREABILITY:1,CATEGORY=Special Ability,Gunslinger ~ Grit	DESC:x
Duplicate Old	CATEGORY:FEAT	TYPE:General	DESC:vecchia
Duplicate Old	CATEGORY:FEAT	TYPE:Combat	DESC:nuova
"""

EQUIP_LST = """\
SOURCELONG:Core Rulebook	SOURCESHORT:CR
Longsword	KEY:Longsword (Base)	SORTKEY:zzBase	PROFICIENCY:WEAPON|Longsword	TYPE:Weapon.Melee.Martial.OneHanded.Slashing	COST:15	WT:4	CRITMULT:x2	CRITRANGE:2	DAMAGE:1d8	WIELD:OneHanded	SIZE:M	SOURCEPAGE:p.147	DESC:x	VISIBLE:NO
Longsword (Base).COPY=Longsword	KEY:Longsword	SORTKEY:Longsword	BASEITEM:Longsword (Base)	EQMOD:Material ~ Steel	VISIBLE:YES
Chainmail	KEY:Chainmail (Base)	SORTKEY:zzBase	PROFICIENCY:ARMOR|Chainmail	TYPE:Armor.Medium.ArmorProfMedium.Suit	COST:150	WT:40	ACCHECK:-5	MAXDEX:2	SOURCEPAGE:p.150	SPELLFAILURE:30	BONUS:COMBAT|AC|6|TYPE=Armor|PREVAREQ:DisableArmorBonus,0	VISIBLE:NO
Chainmail (Base).COPY=Chainmail	KEY:Chainmail	BASEITEM:Chainmail (Base)	EQMOD:Material ~ Steel	VISIBLE:YES
Buckler	PROFICIENCY:SHIELD|Buckler	TYPE:Shield.Buckler	COST:5	WT:5	ACCHECK:-1	SPELLFAILURE:5	BONUS:COMBAT|AC|1|TYPE=Shield|PREVAREQ:DisableShieldBonus,0	VISIBLE:YES	SOURCEPAGE:p.152
Rations (1 day)	TYPE:Goods.Consumable	COST:0.5	WT:1	VISIBLE:YES
Masterwork Longsword	KEY:Longsword (Masterwork)	PROFICIENCY:WEAPON|Longsword	TYPE:Weapon.Melee.Martial	COST:315	WT:4	CRITMULT:x2	CRITRANGE:2	DAMAGE:1d8	WIELD:OneHanded	VISIBLE:YES
"""

SPELLS_LST = """\
SOURCELONG:Core Rulebook	SOURCESHORT:CR
Fireball	TYPE:Arcane.Divine	CLASSES:Sorcerer,Wizard=3	DOMAINS:Fire=3	SCHOOL:Evocation	DESCRIPTOR:Fire	COMPS:V, S, M	CASTTIME:1 standard action	RANGE:Long	TARGETAREA:20-ft.-radius spread	DURATION:Instantaneous	SAVEINFO:Reflex half	SPELLRES:Yes	SOURCEPAGE:p.283	DESC:x
Mass Bear's Endurance	TYPE:Arcane.Divine	CLASSES:Cleric,Druid=6|Sorcerer,Wizard=6	SCHOOL:Transmutation	COMPS:V, S, M/DF	CASTTIME:1 standard action	RANGE:Close	DURATION:1 min./level	SAVEINFO:Will negates (harmless)	SPELLRES:Yes (harmless)	SOURCEPAGE:p.203	DESC:x
Acid Arrow	TYPE:Arcane	CLASSES:Sorcerer,Wizard=2	SCHOOL:Conjuration	SUBSCHOOL:Creation	DESCRIPTOR:Acid	COMPS:V, S, M, F	CASTTIME:1 standard action	RANGE:Long	DURATION:1 round + 1 round per three levels	SAVEINFO:None	SPELLRES:No	SOURCEPAGE:p.239	DESC:x
Bless.MOD	CLASSES:Inquisitor=1
Righteous Might	TYPE:Divine	CLASSES:Cleric=5	SCHOOL:Transmutation	DURATION:(CASTERLEVEL) rounds [D]	SOURCEPAGE:p.335	DESC:x
Righteous Might.MOD	TEMPBONUS:ANYPC|SIZEMOD|NUMBER|1
"""


def _write(root: Path, rel: str, text: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Parser di linea e prerequisiti
# ---------------------------------------------------------------------------


def test_iter_lst_records_salta_commenti_e_vuote():
    records = pc.iter_lst_records(FEATS_LST)
    names = [name for name, _tags in records]
    assert "Acrobatic" in names
    # la riga SOURCELONG non e' un record entita' (tag senza nome proprio?
    # in PCGen SOURCE* va ignorato)
    assert all(not n.startswith("SOURCE") for n in names)


def test_iter_lst_records_tag_in_ordine():
    records = pc.iter_lst_records(FEATS_LST)
    dodge = next(tags for name, tags in records if name == "Dodge")
    keys = [k for k, _v in dodge]
    assert keys[0] == "CATEGORY"
    assert ("TYPE", "Combat") in dodge


def test_parse_prereq_premult_annidato():
    node = pc.parse_prereq_token(
        "PREMULT:1,[PREVARGTEQ:PreStatScore_DEX,13],[PREVARGTEQ:FeatDexRequirement,15]"
    )
    assert node["tag"] == "PREMULT"
    assert node["count"] == 1
    assert len(node["of"]) == 2
    assert node["of"][0] == {
        "tag": "PREVARGTEQ",
        "args": ["PreStatScore_DEX", "13"],
        "raw": "PREVARGTEQ:PreStatScore_DEX,13",
    }


def test_parse_prereq_foglia_generica():
    node = pc.parse_prereq_token("PRESKILL:1,Acrobatics=5")
    assert node["tag"] == "PRESKILL"
    assert node["args"] == ["1", "Acrobatics=5"]


def test_derive_prereqs_casi_reali():
    records = dict(pc.iter_lst_records(FEATS_LST))

    dodge = pc.derive_prereqs(pc.prereq_tree(records["Dodge"]))
    assert dodge["ability_mins"] == {"DEX": 13}

    pa = pc.derive_prereqs(pc.prereq_tree(records["Power Attack"]))
    assert pa["ability_mins"] == {"STR": 13}
    assert pa["bab_min"] == 1

    gc = pc.derive_prereqs(pc.prereq_tree(records["Great Cleave"]))
    assert gc["required_feats"] == ["Cleave", "Power Attack"]
    assert gc["bab_min"] == 4

    sf = pc.derive_prereqs(pc.prereq_tree(records["Skill Focus"]))
    assert sf["skill_ranks"] == [{"skill": "Acrobatics", "ranks": 5}]

    aat = pc.derive_prereqs(pc.prereq_tree(records["Arcane Armor Training"]))
    assert aat["class_levels"] == ["SPELLCASTER=3"]

    ewp = pc.derive_prereqs(pc.prereq_tree(records["Exotic Weapon Proficiency"]))
    assert ewp["alignments"] == ["LG"]

    none = pc.derive_prereqs(pc.prereq_tree(records["Acrobatic"]))
    assert none["required_feats"] == []
    assert none["ability_mins"] == {}


def test_derive_prereqs_tag_non_normalizzato_contato():
    records = dict(pc.iter_lst_records(FEATS_LST))
    derived = pc.derive_prereqs(pc.prereq_tree(records["Adept Channel"]))
    # PREFACT resta grezzo nell'albero ma non ha forma normalizzata: contato
    assert derived["other_tags"] == {"PREFACT": 1}


# ---------------------------------------------------------------------------
# Entita': feats
# ---------------------------------------------------------------------------


def test_feats_from_records_campi():
    entries, stats = pc.feats_from_records(pc.iter_lst_records(FEATS_LST), "CR")
    by_name = {e["name"]: e for e in entries}
    dodge = by_name["Dodge"]
    assert dodge["source_book"] == "CR"
    assert dodge["types"] == ["Combat"]
    assert dodge["source_page"] == "p.122"
    assert dodge["derived"]["ability_mins"] == {"DEX": 13}
    # DESC MAI esportato (policy: solo meccaniche+nomi)
    assert "desc" not in {k.lower() for e in entries for k in e}
    wf = by_name["Weapon Focus"]
    assert wf["multiple"] is True
    assert wf["stack"] is False
    assert stats["duplicates_overridden"] == 1
    assert by_name["Duplicate Old"]["types"] == ["Combat"]


def test_feats_coverage_prereq_tags():
    _entries, stats = pc.feats_from_records(pc.iter_lst_records(FEATS_LST), "CR")
    covered = stats["prereq_coverage"]["covered"]
    not_norm = stats["prereq_coverage"]["not_normalized"]
    assert covered["PREVARGTEQ"] == 7
    assert covered["PREABILITY"] == 2
    assert covered["PRETOTALAB"] == 4
    assert covered["PREMULT"] == 3
    assert covered["PRESKILL"] == 1
    assert covered["PRECLASS"] == 1
    assert covered["PREALIGN"] == 1
    assert not_norm == {"PREFACT": 1, "!PREABILITY": 1}


# ---------------------------------------------------------------------------
# Entita': equipment
# ---------------------------------------------------------------------------


def test_equipment_copy_resolution_e_stat():
    entries, stats = pc.equipment_from_records(pc.iter_lst_records(EQUIP_LST), "CR")
    by_name = {e["name"]: e for e in entries}

    ls = by_name["Longsword"]
    assert ls["kind"] == "weapon"
    assert ls["cost"] == 15
    assert ls["weight"] == 4
    assert ls["damage"] == "1d8"
    assert ls["crit_mult"] == 2
    assert ls["crit_range"] == 2
    assert ls["proficiency"] == "Longsword"
    assert ls["source_page"] == "p.147"

    cm = by_name["Chainmail"]
    assert cm["kind"] == "armor"
    assert cm["cost"] == 150
    assert cm["ac_bonus"] == 6
    assert cm["max_dex"] == 2
    assert cm["armor_check_penalty"] == -5
    assert cm["spell_failure"] == 30

    buk = by_name["Buckler"]
    assert buk["kind"] == "shield"
    assert buk["ac_bonus"] == 1

    # basi VISIBLE:NO e non-armi NON entrano
    assert "Longsword (Base)" not in by_name
    assert "Rations (1 day)" not in by_name
    assert stats["copies_resolved"] == 2
    assert stats["skipped_hidden"] >= 2


# ---------------------------------------------------------------------------
# Entita': spells
# ---------------------------------------------------------------------------


def test_spells_from_records_campi_e_merge():
    entries, stats = pc.spells_from_records(pc.iter_lst_records(SPELLS_LST), "CR")
    by_name = {e["name"]: e for e in entries}

    fb = by_name["Fireball"]
    assert fb["classes"] == {"Sorcerer": 3, "Wizard": 3}
    assert fb["domains"] == {"Fire": 3}
    assert fb["school"] == "Evocation"
    assert fb["descriptors"] == ["Fire"]
    assert fb["saving_throw"] == "Reflex half"
    assert fb["spell_resistance"] == "Yes"
    assert fb["source_page"] == "p.283"
    assert "desc" not in {k.lower() for e in entries for k in e}

    mbe = by_name["Mass Bear's Endurance"]
    assert mbe["classes"] == {"Cleric": 6, "Druid": 6, "Sorcerer": 6, "Wizard": 6}

    # .MOD con CLASSES si fonde nella base; .MOD senza campi rilevanti = no-op
    assert by_name.get("Bless") is None  # Bless non definita: MOD orfano
    assert stats["mods_merged"] == 0
    assert stats["mods_unresolved"] == 1  # Bless.MOD
    rm = by_name["Righteous Might"]
    assert rm["classes"] == {"Cleric": 5}
    assert stats["mods_noop"] == 1  # Righteous Might.MOD (solo TEMPBONUS)


# ---------------------------------------------------------------------------
# build() end-to-end su radice PCGen finta
# ---------------------------------------------------------------------------


def _fake_pcgen_root(tmp_path: Path) -> Path:
    root = tmp_path / "pcgen-repo"
    base = root / "data/pathfinder/paizo"
    _write(base, "roleplaying_game/core_rulebook/cr_feats.lst", FEATS_LST)
    _write(base, "roleplaying_game/core_rulebook/cr_equip_arms_armor.lst", EQUIP_LST)
    _write(base, "roleplaying_game/core_rulebook/cr_spells.lst", SPELLS_LST)
    # gli altri libri configurati esistono ma con un record minimo: il build
    # completo (main) e' strict sui file mancanti
    for book, cfg in pc.BOOKS.items():
        if book == "CR":
            continue
        for rel in cfg["feats"] + cfg["equipment"] + cfg["spells"]:
            _write(
                base,
                f"{cfg['dir']}/{rel}",
                f"# finto\nStub {book}	CATEGORY:FEAT	TYPE:General	DESC:x\n",
            )
    return root


def test_build_catalog_provenance_e_conteggi(tmp_path):
    root = _fake_pcgen_root(tmp_path)
    payload = pc.build_catalog(root, "feats", books=["CR"])
    prov = payload["_provenance"]
    assert prov["source"].startswith("PCGen")
    assert prov["license"]
    assert prov["desc_policy"]
    assert prov["pcgen_commit"]  # "unknown" se non e' un repo git
    assert prov["books"]["CR"] == "Core Rulebook"
    assert payload["counts"]["CR"] == len(payload["entries"])
    assert payload["entries"]  # non vuoto

    payload = pc.build_catalog(root, "equipment", books=["CR"])
    assert payload["counts"]["CR"] >= 3
    payload = pc.build_catalog(root, "spells", books=["CR"])
    assert payload["counts"]["CR"] == 4


def test_build_catalog_kind_sconosciuto_errore(tmp_path):
    with pytest.raises(ValueError):
        pc.build_catalog(_fake_pcgen_root(tmp_path), "mostri")


def test_main_scrive_i_tre_json(tmp_path):
    root = _fake_pcgen_root(tmp_path)
    out = tmp_path / "out"
    rc = pc.main(["--pcgen-repo", str(root), "--out-dir", str(out)])
    assert rc == 0
    for name in ("pcgen-feats.json", "pcgen-equipment.json", "pcgen-spells.json"):
        data = json.loads((out / name).read_text(encoding="utf-8"))
        assert data["_provenance"]["books"]
        assert isinstance(data["entries"], list)


# ---------------------------------------------------------------------------
# BONUS strutturati dei talenti (slice BONUS 2026-08-07): parse grezzo dei tag
# BONUS:* su ogni talento. Forme REALI prelevate dai file del clone
# (ricognizione 2026-08-07): letterale+TYPE (Dodge), TS (Iron Will), formula
# max(3,TL)+PRERULE (Toughness), %LIST (Skill Focus/Weapon Focus), formula con
# '=' dentro parentesi (DruidWildShape), PRE negata in coda, scope PC|STAT,
# modificatore non riconosciuto (TYPE.Sling, forma reale di uc_feats.lst).
# ---------------------------------------------------------------------------

BONUS_LST = """\
SOURCELONG:Core Rulebook	SOURCESHORT:CR
Dodge	CATEGORY:FEAT	TYPE:Combat	BONUS:COMBAT|AC|1|TYPE=Dodge
Iron Will	CATEGORY:FEAT	TYPE:General	BONUS:SAVE|Will|2
Great Fortitude	CATEGORY:FEAT	TYPE:General	BONUS:SAVE|Fortitude|2
Lightning Reflexes	CATEGORY:FEAT	TYPE:General	BONUS:SAVE|Reflex|2
Toughness	CATEGORY:FEAT	TYPE:General	BONUS:HP|CURRENTMAX|max(3,TL)|PRERULE:1,DAMAGE_HP
Skill Focus	CATEGORY:FEAT	TYPE:General.SkillFocus	STACK:NO	MULT:YES	CHOOSE:SKILL|TYPE=Base	BONUS:SKILL|%LIST|3|TYPE=SkillFocus
Weapon Focus	CATEGORY:FEAT	TYPE:Combat	STACK:NO	MULT:YES	BONUS:WEAPONPROF=%LIST|TOHIT|WeaponFocusToHit
Gritty Savant	CATEGORY:FEAT	TYPE:Combat	BONUS:SAVE|Will|CHA-WIS	BONUS:VAR|GritPoints|1
Improvisation	CATEGORY:FEAT	TYPE:General	BONUS:SKILL|Acrobatics|ImprovisationBonus|!PRESKILL:1,Acrobatics=1
Primal Physique	CATEGORY:FEAT	TYPE:General	BONUS:PC|STAT|STR,CON|2
Sling Adept	CATEGORY:FEAT	TYPE:Combat	BONUS:COMBAT|GLOBALRANGEPENALTY|2|TYPE.Sling
Wild Shape Savant	CATEGORY:FEAT	TYPE:General	BONUS:VAR|DruidWildShape|MIN(4,classlevel("TYPE=PC")+classlevel("TYPE=NPC")-classlevel("Druid"))
No Bonus	CATEGORY:FEAT	TYPE:General	DESC:x
"""


def test_parse_bonus_tag_letterale_e_type():
    node = pc.parse_bonus_tag("COMBAT|AC|1|TYPE=Dodge")
    assert node == {
        "raw": "COMBAT|AC|1|TYPE=Dodge",
        "group": "COMBAT",
        "path": ["AC"],
        "value": "1",
        "valueNumber": 1,
        "type": "Dodge",
        "recognized": True,
    }


def test_parse_bonus_tag_salvezza():
    node = pc.parse_bonus_tag("SAVE|Will|2")
    assert node["group"] == "SAVE"
    assert node["path"] == ["Will"]
    assert node["valueNumber"] == 2
    assert node["recognized"] is True
    assert "type" not in node
    assert "conditions" not in node


def test_parse_bonus_tag_formula_e_prerule():
    # Toughness PF: valore formula (mai inventato a numero) + PRERULE raw.
    node = pc.parse_bonus_tag("HP|CURRENTMAX|max(3,TL)|PRERULE:1,DAMAGE_HP")
    assert node["group"] == "HP"
    assert node["path"] == ["CURRENTMAX"]
    assert node["value"] == "max(3,TL)"
    assert "valueNumber" not in node
    assert node["conditions"] == ["PRERULE:1,DAMAGE_HP"]
    assert node["recognized"] is True


def test_parse_bonus_tag_scelta_list_con_valore_letterale():
    # Skill Focus: l'abilita' e' una SCELTA (%LIST), il 3 e' letterale.
    node = pc.parse_bonus_tag("SKILL|%LIST|3|TYPE=SkillFocus")
    assert node["group"] == "SKILL"
    assert node["path"] == ["%LIST"]
    assert node["valueNumber"] == 3
    assert node["type"] == "SkillFocus"


def test_parse_bonus_tag_gruppo_con_scelta():
    # Weapon Focus: il gruppo stesso porta la scelta, il valore e' un VAR.
    node = pc.parse_bonus_tag("WEAPONPROF=%LIST|TOHIT|WeaponFocusToHit")
    assert node["group"] == "WEAPONPROF=%LIST"
    assert node["path"] == ["TOHIT"]
    assert node["value"] == "WeaponFocusToHit"
    assert "valueNumber" not in node
    assert node["recognized"] is True


def test_parse_bonus_tag_pre_negata_preservata():
    node = pc.parse_bonus_tag(
        "SKILL|Acrobatics|ImprovisationBonus|!PRESKILL:1,Acrobatics=1"
    )
    assert node["conditions"] == ["!PRESKILL:1,Acrobatics=1"]
    assert node["recognized"] is True


def test_parse_bonus_tag_scope_pc_stat():
    node = pc.parse_bonus_tag("PC|STAT|STR,CON|2")
    assert node["group"] == "PC"
    assert node["path"] == ["STAT", "STR,CON"]
    assert node["valueNumber"] == 2
    assert node["recognized"] is True


def test_parse_bonus_tag_modificatore_sconosciuto_flaggato():
    # Forma reale (uc_feats.lst): TYPE.Sling non e' TYPE=... — dichiarato,
    # MAI scartato in silenzio ne' interpretato a tentativi.
    node = pc.parse_bonus_tag("COMBAT|GLOBALRANGEPENALTY|2|TYPE.Sling")
    assert node["recognized"] is False
    assert node["unparsed"] == ["TYPE.Sling"]
    assert node["raw"] == "COMBAT|GLOBALRANGEPENALTY|2|TYPE.Sling"


def test_parse_bonus_tag_formula_con_uguale_dentro_parentesi():
    # Il "TYPE=PC" dentro classlevel("...") NON e' il tipo del bonus: lo split
    # rispetta le parentesi tonde.
    node = pc.parse_bonus_tag(
        'VAR|DruidWildShape|MIN(4,classlevel("TYPE=PC")+classlevel("TYPE=NPC")-classlevel("Druid"))'
    )
    assert node["group"] == "VAR"
    assert node["path"] == ["DruidWildShape"]
    assert "type" not in node
    assert node["value"].startswith("MIN(4,classlevel(")
    assert node["recognized"] is True


def test_feats_from_records_bonus_campi_e_conteggi():
    entries, stats = pc.feats_from_records(pc.iter_lst_records(BONUS_LST), "CR")
    by_name = {e["name"]: e for e in entries}

    dodge = by_name["Dodge"]["bonus"]
    assert dodge == [
        {
            "raw": "COMBAT|AC|1|TYPE=Dodge",
            "group": "COMBAT",
            "path": ["AC"],
            "value": "1",
            "valueNumber": 1,
            "type": "Dodge",
            "recognized": True,
        }
    ]

    # multi-BONUS: tutti, in ordine, niente scartato
    gritty = by_name["Gritty Savant"]["bonus"]
    assert [b["raw"] for b in gritty] == ["SAVE|Will|CHA-WIS", "VAR|GritPoints|1"]

    # talento senza BONUS: lista vuota, non campo assente
    assert by_name["No Bonus"]["bonus"] == []

    bonus_stats = stats["bonus"]
    assert bonus_stats["feats_with_bonus"] == 12
    assert bonus_stats["total_tags"] == 13
    assert bonus_stats["by_group"] == {
        "COMBAT": 2,
        "SAVE": 4,
        "HP": 1,
        "SKILL": 2,
        "WEAPONPROF=%LIST": 1,
        "VAR": 2,
        "PC": 1,
    }
    assert bonus_stats["literal_value"] == 8
    assert bonus_stats["with_type"] == 2
    assert bonus_stats["recognized"] == 12
    assert bonus_stats["unrecognized"] == 1


# ---------------------------------------------------------------------------
# Smoke sui dati REALI (salta se il clone PCGen non c'e'): il parser non deve
# rompersi sui 2939 file veri e gli spot-check RAW devono reggere.
# ---------------------------------------------------------------------------

REAL_ROOT = Path(os.environ.get("PCGEN_REPO", r"C:\Users\VGit\Downloads\pcgen-repo"))


@pytest.mark.skipif(
    not (REAL_ROOT / "data/pathfinder/paizo").is_dir(), reason="clone PCGen assente"
)
def test_dati_reali_spot_check():
    feats = pc.build_catalog(REAL_ROOT, "feats")
    by_name = {e["name"]: e for e in feats["entries"]}
    assert by_name["Dodge"]["derived"]["ability_mins"] == {"DEX": 13}
    assert by_name["Power Attack"]["derived"]["ability_mins"] == {"STR": 13}
    assert by_name["Power Attack"]["derived"]["bab_min"] == 1

    spells = pc.build_catalog(REAL_ROOT, "spells")
    by_name = {e["name"]: e for e in spells["entries"]}
    assert by_name["Fireball"]["classes"]["Sorcerer"] == 3
    assert by_name["Fireball"]["classes"]["Wizard"] == 3

    equip = pc.build_catalog(REAL_ROOT, "equipment")
    by_name = {e["name"]: e for e in equip["entries"]}
    cm = by_name["Chainmail"]
    assert cm["cost"] == 150
    assert cm["ac_bonus"] == 6
    assert cm["max_dex"] == 2
    assert cm["armor_check_penalty"] == -5
    assert cm["spell_failure"] == 30

    # conteggi minimi per libro (sanita': nessun libro e' sparito)
    for book in ("CR", "APG", "ACG", "ARG", "UM", "UC", "OA"):
        assert feats["counts"][book] > 0
    assert equip["counts"]["UE"] > 0
    for book in ("CR", "APG", "ACG", "ARG", "UM", "UC", "UE", "OA"):
        assert spells["counts"][book] > 0


@pytest.mark.skipif(
    not (REAL_ROOT / "data/pathfinder/paizo").is_dir(), reason="clone PCGen assente"
)
def test_dati_reali_bonus_spot_check():
    """Slice BONUS: spot-check RAW dei tag BONUS sui dati veri."""
    feats = pc.build_catalog(REAL_ROOT, "feats")
    by_name = {e["name"]: e for e in feats["entries"]}

    def only(name):
        (node,) = by_name[name]["bonus"]
        return node

    dodge = only("Dodge")
    assert dodge["group"] == "COMBAT" and dodge["path"] == ["AC"]
    assert dodge["valueNumber"] == 1 and dodge["type"] == "Dodge"

    assert only("Iron Will")["path"] == ["Will"]
    assert only("Iron Will")["valueNumber"] == 2
    assert only("Great Fortitude")["path"] == ["Fortitude"]
    assert only("Lightning Reflexes")["path"] == ["Reflex"]

    tough = only("Toughness")
    assert tough["group"] == "HP" and tough["path"] == ["CURRENTMAX"]
    assert tough["value"] == "max(3,TL)" and "valueNumber" not in tough
    assert tough["conditions"] == ["PRERULE:1,DAMAGE_HP"]

    sf = only("Skill Focus")
    assert sf["group"] == "SKILL" and sf["path"] == ["%LIST"]
    assert sf["valueNumber"] == 3 and sf["type"] == "SkillFocus"

    wf = only("Weapon Focus")
    assert wf["group"] == "WEAPONPROF=%LIST" and wf["value"] == "WeaponFocusToHit"

    # ogni talento porta il campo bonus (lista, vuota se senza BONUS)
    for e in feats["entries"]:
        assert isinstance(e["bonus"], list)
    # sanita' aggregata: i BONUS ci sono e quasi tutti si parsano
    total = sum(s["bonus"]["total_tags"] for s in feats["stats"].values())
    unrecognized = sum(s["bonus"]["unrecognized"] for s in feats["stats"].values())
    assert total > 400
    assert unrecognized / total < 0.05


# ---------------------------------------------------------------------------
# Fase A (2026-08-08): BOOKS esteso ai manuali fuori linea core PRESENTI nel
# clone — Ultimate Intrigue (UI), Ultimate Wilderness (UW), Horror Adventures
# (HA), Pathfinder Unchained (PU), Adventurer's Guide (AG).
# Scarti DICHIARATI (presenti nel clone ma NON aggiunti): mythic_adventures
# (sistema mythic = regole alternative, stessa disciplina di words of power),
# ultimate_campaign (solo uca_feats.lst, regole di gestione campagna),
# monster_codex e bestiari (contenuto mostri/PNG, fuori scope dal perimetro
# A1), beginner_box (sottoinsieme del CR), core_essentials (plumbing PCGen,
# non contenuto). Villain Codex: NON presente nel clone sparse (dichiarato
# nell'handoff come candidato; non importabile).
# ---------------------------------------------------------------------------

NEW_BOOKS = ("UI", "UW", "HA", "PU", "AG")


def test_books_estesi_configurati():
    assert set(NEW_BOOKS) <= set(pc.BOOKS)
    for book in NEW_BOOKS:
        cfg = pc.BOOKS[book]
        assert cfg["dir"].startswith("roleplaying_game/")
        assert cfg["feats"] and cfg["equipment"] and cfg["spells"]


@pytest.mark.skipif(
    not (REAL_ROOT / "data/pathfinder/paizo").is_dir(), reason="clone PCGen assente"
)
def test_dati_reali_new_books_spot_check():
    feats = pc.build_catalog(REAL_ROOT, "feats")
    by_name = {e["name"]: e for e in feats["entries"]}
    # spot-check RAW: un talento per libro nuovo (nomi verificati nel clone)
    assert by_name["Acrobatic Spellcaster"]["source_book"] == "UI"
    assert by_name["Ambush Awareness"]["source_book"] == "UW"

    spells = pc.build_catalog(REAL_ROOT, "spells")
    spell_names = {e["name"] for e in spells["entries"]}
    assert "Alpha Instinct" in spell_names  # Ultimate Wilderness

    equip = pc.build_catalog(REAL_ROOT, "equipment")
    # conteggi minimi per libro (sanita': nessun libro nuovo e' vuoto)
    for book in NEW_BOOKS:
        assert feats["counts"][book] > 0
    for book in ("UI", "UW", "HA", "AG"):
        assert spells["counts"][book] > 0
    # PU spells = 0, verificato nel clone 2026-08-08 e DICHIARATO:
    # pu_spells.lst (lista Unchained Summoner) e' INTERAMENTE commentato
    # upstream in PCGen master -> nessun record attivo da importare.
    assert spells["counts"]["PU"] == 0
    # Equipaggiamento: UI/UW/AG portano armi/armature mundane; HA e PU no,
    # verificato nel clone 2026-08-08 e DICHIARATO:
    # - HA (ha_equip_arms_armor.lst): solo .COPY di basi "(Base)" del CR per
    #   oggetti magici specifici -> copie cross-libro non risolte (0 entry,
    #   stats.copies_unresolved le conta); l'unico item proprio e' VISIBLE:NO;
    # - PU (pu_equip.lst): file placeholder vuoto (2 righe di commento);
    # - UW: 1 arma propria (Seedpod); i .MOD "Tribal Weapon Group" su armi CR
    #   sono cross-libro non risolti (contati in mods_unresolved).
    assert equip["counts"]["UI"] > 0
    assert equip["counts"]["UW"] > 0
    assert equip["counts"]["AG"] > 0
    assert equip["counts"]["HA"] == 0
    assert equip["counts"]["PU"] == 0
