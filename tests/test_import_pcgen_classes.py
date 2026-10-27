"""Test per tools/import_pcgen_classes.py — progressione e class-abilities PCGen.

Slice D3-a (2026-08-07): import della progressione per livello delle classi
(feature concesse per livello 1..20) e delle class abilities (feature vere,
con BONUS grezzi riusando parse_bonus_tag e prerequisiti grezzi come per i
feat) dai file LST PCGen dei BOOKS gia' configurati in import_pcgen_lst.

Fixture LST inline (MAI rete): forma reale ricostruita dalla ricognizione
2026-08-07 su pcgen-repo/data/pathfinder/paizo/roleplaying_game/*:

- `*_classes.lst`: righe `CLASS:Nome` (anche ripetute, tag continuazione) +
  righe livello `N<TAB>tag...` con ABILITY:pool|NATURA|nomi|condizioni e
  BONUS:ABILITYPOOL|...; righe CAST/KNOWN = tabelle spell, ignorate.
- La progressione vera vive anche nelle righe `.MOD` di
  `*_abilities_class.lst` / `*_abilities_globalvar.lst`:
  `CATEGORY=Class|X ~ Standard Class Full.MOD` / `CATEGORY=Class|X.MOD`
  (a volte CATEGORY=CLASS maiuscolo, es. OA) con gate
  PREVARGTEQ:<Classe>_CFP_Level,N (assente = concessa dal 1°, dichiarato);
  le cadenze degli slot (rage power ogni 2, ...) sono
  `CATEGORY=Special Ability|X ~ <Feature>.MOD BONUS:ABILITYPOOL|Pool|v|gate`.
"""

import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools import import_pcgen_classes as pcc

# ---------------------------------------------------------------------------
# Fixture: forma reale (tab separati).
# ---------------------------------------------------------------------------

CLASSES_LST = """\
# commento
SOURCELONG:Core Rulebook	SOURCESHORT:CR

CLASS:Barbarian	HD:12	TYPE:Base.PC	MAXLEVEL:20	DEFINE:BarbarianLVL|0
CLASS:Barbarian	STARTSKILLPTS:4
1	ABILITY:Class|AUTOMATIC|Barbarian

CLASS:Ex-Barbarian	HD:12	VISIBLE:NO	DEFINE:BarbarianLVL|0
1	ABILITY:Class|AUTOMATIC|Barbarian

CLASS:Bard	HD:8	TYPE:Base.PC	MAXLEVEL:20
1	CAST:0,1	KNOWN:4,2
1	ABILITY:Class|AUTOMATIC|Bard
2	ABILITY:Bard Class Feature|AUTOMATIC|Bard ~ Versatile Performance|PREVAREQ:Bard_CF_VersatilePerformance,0
20	BONUS:ABILITYPOOL|Bard Special Pool|1|PREVAREQ:Bard_CF_Pool,0
"""

ABILITIES_CLASS_LST = """\
SOURCELONG:Core Rulebook	SOURCESHORT:CR
Barbarian		CATEGORY:Class	DEFINE:Barbarian_CFP_Level|0	ABILITY:Class|AUTOMATIC|Barbarian ~ Standard Class
Standard Barbarian	KEY:Barbarian ~ Standard Class	CATEGORY:Class	TYPE:Internal
CATEGORY=Class|Barbarian ~ Standard Class Full.MOD	ABILITY:Barbarian Class Feature|AUTOMATIC|Barbarian ~ Rage|PREVAREQ:Barbarian_CF_Rage,0|PREVARGTEQ:Barbarian_CFP_Level,1
CATEGORY=Class|Barbarian ~ Standard Class Full.MOD	ABILITY:Barbarian Class Feature|AUTOMATIC|Barbarian ~ Trap Sense|PREVAREQ:Barbarian_CF_TrapSense,0|PREVARGTEQ:Barbarian_CFP_Level,3
CATEGORY=Class|Barbarian ~ Standard Class Full.MOD	ABILITY:Barbarian Class Feature|AUTOMATIC|Barbarian ~ Weapon and Armor Proficiency|PREVAREQ:Barbarian_CF_Proficiencies,0
CATEGORY=Special Ability|Barbarian ~ Rage Powers.MOD	BONUS:ABILITYPOOL|Rage Power|-1|PREVARGTEQ:RagePowersLVL,2|PREVAREQ:Barbarian_CF_RagePower2,1
CATEGORY=Special Ability|Barbarian ~ Rage Powers.MOD	BONUS:ABILITYPOOL|Rage Power|-1|PREVARGTEQ:RagePowersLVL,4|PREVAREQ:Barbarian_CF_RagePower4,1
CATEGORY=Special Ability|Barbarian ~ Rage Powers.MOD	BONUS:VAR|RagePowerCount|-1|PREMULT:2,[PRECLASS:1,Barbarian=6],[PREVAREQ:Barbarian_CF_RagePower6,1]
CATEGORY=Internal|Archetype Display.MOD	ABILITY:Barbarian Archetype|AUTOMATIC|Archetype Barbarian|PRECLASS:1,Barbarian=1
Rage	KEY:Barbarian ~ Rage	CATEGORY:Special Ability	TYPE:BarbarianClassFeatures.ClassFeatures	BONUS:VAR|RageLVL|BarbarianLVL	DESC:Testo Paizo che non deve MAI uscire	SOURCEPAGE:p.32
Trap Sense	KEY:Barbarian ~ Trap Sense	CATEGORY:Special Ability	TYPE:BarbarianClassFeatures	PRELEVEL:3	BONUS:SAVE|Reflex|1|TYPE=Luck	DESC:x
Bardic Knowledge	CATEGORY:Special Ability	TYPE:BardClassFeatures.SpecialQuality	BONUS:SKILL|Knowledge (History)|2	DESC:x
Fast Movement	KEY:Barbarian ~ Fast Movement	CATEGORY:Special Ability	TYPE:BarbarianClassFeatures	BONUS:MOVEADD|TYPE.Walk|10
Fast Movement	KEY:Monk ~ Fast Movement	CATEGORY:Special Ability	TYPE:MonkClassFeatures	DEFINE:MonkFastMovementLVL|0
"""

ABILITIES_GLOBALVAR_LST = """\
SOURCELONG:Advanced Player's Guide	SOURCESHORT:APG
CATEGORY=Class|Oracle.MOD	ABILITY:Oracle Class Feature|AUTOMATIC|Oracle's Curse|PREVAREQ:Oracle_CF_OraclesCurse,0|PREVARGTEQ:Oracle_CFP_Level,1
CATEGORY=CLASS|Kineticist.MOD	ABILITY:Kineticist Class Feature|AUTOMATIC|Kineticist ~ Burn|PREVAREQ:Kineticist_CF_Burn,0|PREVARGTEQ:Kineticist_CFP_Level,1
CATEGORY=Class|Oracle.MOD	DEFINE:Oracle_CF_OraclesCurse|0
"""

APG_CLASSES_LST = """\
SOURCELONG:Advanced Player's Guide	SOURCESHORT:APG
CLASS:Oracle	HD:8	TYPE:Base.PC	MAXLEVEL:20	DEFINE:OracleLVL|0
1	ABILITY:Class|AUTOMATIC|Oracle
"""

OA_CLASSES_LST = """\
SOURCELONG:Occult Adventures	SOURCESHORT:OA
CLASS:Kineticist	HD:8	TYPE:Base.PC	MAXLEVEL:20	DEFINE:KineticistLVL|0
1	ABILITY:CLASS|AUTOMATIC|Kineticist
"""


def _write(root: Path, rel: str, text: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Parse dei singoli grant
# ---------------------------------------------------------------------------


def test_parse_ability_grant_base():
    grant = pcc.parse_ability_grant("Class|AUTOMATIC|Barbarian")
    assert grant == {
        "pool": "Class",
        "nature": "AUTOMATIC",
        "names": ["Barbarian"],
        "conditions": [],
    }


def test_parse_ability_grant_con_condizioni():
    grant = pcc.parse_ability_grant(
        "Barbarian Class Feature|AUTOMATIC|Barbarian ~ Trap Sense"
        "|PREVAREQ:Barbarian_CF_TrapSense,0|PREVARGTEQ:Barbarian_CFP_Level,3"
    )
    assert grant["pool"] == "Barbarian Class Feature"
    assert grant["nature"] == "AUTOMATIC"
    assert grant["names"] == ["Barbarian ~ Trap Sense"]
    assert grant["conditions"] == [
        "PREVAREQ:Barbarian_CF_TrapSense,0",
        "PREVARGTEQ:Barbarian_CFP_Level,3",
    ]


def test_parse_ability_grant_nomi_type_e_multipli():
    # i segmenti TYPE= in posizione nome restano nomi (grezzi, dichiarati);
    # piu' nomi nello stesso tag si separano
    grant = pcc.parse_ability_grant(
        "Internal|AUTOMATIC|Armor Prof ~ Light|Shield Prof|!PREABILITY:1,CATEGORY=Archetype,TYPE.X"
    )
    assert grant["names"] == ["Armor Prof ~ Light", "Shield Prof"]
    assert grant["conditions"] == ["!PREABILITY:1,CATEGORY=Archetype,TYPE.X"]
    typed = pcc.parse_ability_grant(
        "Internal|AUTOMATIC|TYPE=ArmorProfHeavy|TYPE=ShieldProf"
    )
    assert typed["names"] == ["TYPE=ArmorProfHeavy", "TYPE=ShieldProf"]


def test_parse_ability_grant_natura_virtual_e_condizione_con_pipe_interne():
    grant = pcc.parse_ability_grant(
        "Class|VIRTUAL|Barbarian ~ Standard Class"
        "|PREMULT:1,[!PRECLASS:1,Ex-Barbarian=1],[PREVAREQ:Class_BarbarianExClass,0]"
    )
    assert grant["nature"] == "VIRTUAL"
    assert grant["names"] == ["Barbarian ~ Standard Class"]
    assert grant["conditions"] == [
        "PREMULT:1,[!PRECLASS:1,Ex-Barbarian=1],[PREVAREQ:Class_BarbarianExClass,0]"
    ]


def test_extract_level_gate():
    assert (
        pcc.extract_level_gate(["PREVAREQ:X,0", "PREVARGTEQ:Barbarian_CFP_Level,3"])
        == 3
    )
    # gate su un altro VAR di progressione (cadenze slot): lo stesso livello
    assert pcc.extract_level_gate(["PREVARGTEQ:RagePowersLVL,4"]) == 4
    # nessun gate di livello -> concessa dal 1° (dichiarato)
    assert pcc.extract_level_gate(["PREVAREQ:Bard_CF_X,0"]) == 1
    assert pcc.extract_level_gate([]) == 1
    # piu' gate: vince il minimo (la concessione parte dal primo livello)
    assert (
        pcc.extract_level_gate(["PREVARGTEQ:X_CFP_Level,5", "PREVARGTEQ:YLVL,3"]) == 3
    )
    # gate non intero (VAR/formula) non e' un livello
    assert pcc.extract_level_gate(["PREVARGTEQ:XLVL,SomeVar"]) == 1


def test_parse_pool_grant():
    grant = pcc.parse_pool_grant(
        "ABILITYPOOL|Rage Power|-1|PREVARGTEQ:RagePowersLVL,2|PREVAREQ:Barbarian_CF_RagePower2,1"
    )
    assert grant == {
        "pool": "Rage Power",
        "value": "-1",
        "conditions": [
            "PREVARGTEQ:RagePowersLVL,2",
            "PREVAREQ:Barbarian_CF_RagePower2,1",
        ],
    }


def test_parse_var_pool_grant():
    # cadenze codificate come conteggio VAR (forma reale: Investigator
    # Talents, Arcanist Exploits): catturate grezze come pool-var
    grant = pcc.parse_var_pool_grant(
        "VAR|InvestigatorTalentCount|-1"
        "|PREMULT:2,[PRECLASS:1,Investigator=5],[PREVAREQ:Investigator_CF_Talent5,1]"
    )
    assert grant == {
        "pool": "InvestigatorTalentCount",
        "value": "-1",
        "conditions": [
            "PREMULT:2,[PRECLASS:1,Investigator=5],[PREVAREQ:Investigator_CF_Talent5,1]"
        ],
    }
    assert pcc.parse_var_pool_grant("ABILITYPOOL|Rage Power|-1") is None


def test_extract_pool_level_gate_preclass():
    # cadenze Hunter/Magus/Gunslinger: il livello e' nel gate PRECLASS
    # (anche dentro PREMULT); il PREVARGTEQ intero vince se presente
    assert (
        pcc.extract_pool_level(
            ["PREMULT:2,[PRECLASS:1,Hunter=6],[PREVAREQ:Hunter_CF_TeamworkFeat6,0]"]
        )
        == 6
    )
    assert pcc.extract_pool_level(["PRECLASS:1,Magus=11", "PREVAREQ:X,1"]) == 11
    assert pcc.extract_pool_level(["PREVARGTEQ:RagePowersLVL,4"]) == 4
    # PRECLASS negati o con valore 0 / nomi puntati non sono livelli di classe
    assert pcc.extract_pool_level(["!PRECLASS:1,Barbarian=3"]) == 1
    assert pcc.extract_pool_level(["PRECLASS:1,TYPE.Base=0"]) == 1
    assert pcc.extract_pool_level([]) == 1


def test_extract_var_pool_level_solo_preclass():
    # i pool-var: MAI il PREVARGTEQ (puo' essere un CONTEGGIO, es.
    # MagusArcanaCount — non un livello); solo gate PRECLASS espliciti,
    # altrimenti livello non derivato (None, dichiarato)
    assert (
        pcc.extract_var_pool_level(
            ["PREMULT:2,[PRECLASS:1,Investigator=7],[PREVAREQ:X,1]"]
        )
        == 7
    )
    assert pcc.extract_var_pool_level(["PREVARGTEQ:MagusArcanaCount,3"]) is None
    assert pcc.extract_var_pool_level([]) is None


# ---------------------------------------------------------------------------
# Progressione da classes.lst
# ---------------------------------------------------------------------------


def test_progression_classes_lst_base():
    entries = pcc.progression_from_classes_text(CLASSES_LST, "CR")
    by_class = {e["class"]: e for e in entries}
    # Ex-Barbarian: classe di penalita' per abbandono, fuori perimetro
    assert set(by_class) == {"Barbarian", "Bard"}

    barb = by_class["Barbarian"]["grants"]
    assert barb == [
        {
            "level": 1,
            "kind": "ability",
            "pool": "Class",
            "nature": "AUTOMATIC",
            "names": ["Barbarian"],
            "conditions": [],
        }
    ]

    bard = by_class["Bard"]["grants"]
    assert bard[0] == {
        "level": 1,
        "kind": "ability",
        "pool": "Class",
        "nature": "AUTOMATIC",
        "names": ["Bard"],
        "conditions": [],
    }
    assert {
        "level": 2,
        "kind": "ability",
        "pool": "Bard Class Feature",
        "nature": "AUTOMATIC",
        "names": ["Bard ~ Versatile Performance"],
        "conditions": ["PREVAREQ:Bard_CF_VersatilePerformance,0"],
    } in bard
    # BONUS:ABILITYPOOL su riga livello -> grant di pool
    assert {
        "level": 20,
        "kind": "pool",
        "pool": "Bard Special Pool",
        "value": "1",
        "conditions": ["PREVAREQ:Bard_CF_Pool,0"],
    } in bard
    # righe CAST/KNOWN non producono grant
    assert all(g["kind"] in ("ability", "pool") for g in bard)


# ---------------------------------------------------------------------------
# Progressione dalle righe .MOD (abilities_class / abilities_globalvar)
# ---------------------------------------------------------------------------


def test_progression_mod_lines_class_target():
    known = {"Barbarian", "Oracle", "Kineticist"}
    grants, stats = pcc.progression_from_mod_text(ABILITIES_CLASS_LST, "CR", known)
    barb = [g for g in grants if g["class"] == "Barbarian"]
    by_name = {}
    for g in barb:
        for name in g.get("names", []):
            by_name[name] = g
    # gate esplicito al 1°
    assert by_name["Barbarian ~ Rage"]["level"] == 1
    assert by_name["Barbarian ~ Rage"]["pool"] == "Barbarian Class Feature"
    # gate al 3°
    assert by_name["Barbarian ~ Trap Sense"]["level"] == 3
    assert (
        "PREVARGTEQ:Barbarian_CFP_Level,3"
        in by_name["Barbarian ~ Trap Sense"]["conditions"]
    )
    # nessun gate di livello -> 1° (dichiarato)
    assert by_name["Barbarian ~ Weapon and Armor Proficiency"]["level"] == 1
    # cadenze slot: BONUS:ABILITYPOOL su MOD di Special Ability
    pools = [g for g in barb if g["kind"] == "pool"]
    assert [(g["level"], g["pool"], g["value"]) for g in pools] == [
        (2, "Rage Power", "-1"),
        (4, "Rage Power", "-1"),
    ]
    # cadenze a conteggio VAR: pool-var, livello dal gate PRECLASS
    var_pools = [g for g in barb if g["kind"] == "pool-var"]
    assert [(g["level"], g["pool"], g["value"]) for g in var_pools] == [
        (6, "RagePowerCount", "-1")
    ]
    # MOD di altre categorie: saltata e contata
    assert stats["mods_skipped_other_category"] == 1


def test_progression_mod_lines_globalvar_e_maiuscolo():
    known = {"Barbarian", "Oracle", "Kineticist"}
    grants, _stats = pcc.progression_from_mod_text(
        ABILITIES_GLOBALVAR_LST, "APG", known
    )
    oracle = [g for g in grants if g["class"] == "Oracle"]
    assert oracle == [
        {
            "class": "Oracle",
            "level": 1,
            "kind": "ability",
            "pool": "Oracle Class Feature",
            "nature": "AUTOMATIC",
            "names": ["Oracle's Curse"],
            "conditions": [
                "PREVAREQ:Oracle_CF_OraclesCurse,0",
                "PREVARGTEQ:Oracle_CFP_Level,1",
            ],
        }
    ]
    # CATEGORY=CLASS maiuscolo (forma reale OA)
    kin = [g for g in grants if g["class"] == "Kineticist"]
    assert len(kin) == 1 and kin[0]["names"] == ["Kineticist ~ Burn"]
    # MOD senza ABILITY/BONUS:ABILITYPOOL (solo DEFINE): nessun grant, no-op
    # contata
    _noop = _stats["mods_without_grants"]
    assert _noop == 1


def test_progression_mod_target_sconosciuto_contato():
    text = "CATEGORY=Class|Inventata ~ Standard Class Full.MOD\tABILITY:X|AUTOMATIC|Y\n"
    grants, stats = pcc.progression_from_mod_text(text, "CR", {"Barbarian"})
    assert grants == []
    assert stats["mods_unmapped_target"] == 1


def test_progression_dedupe():
    text = (
        "CATEGORY=Class|Barbarian ~ Standard Class Full.MOD\t"
        "ABILITY:Barbarian Class Feature|AUTOMATIC|Barbarian ~ Rage|PREVARGTEQ:Barbarian_CFP_Level,1\n"
        "CATEGORY=Class|Barbarian.MOD\t"
        "ABILITY:Barbarian Class Feature|AUTOMATIC|Barbarian ~ Rage|PREVARGTEQ:Barbarian_CFP_Level,1\n"
    )
    grants, stats = pcc.progression_from_mod_text(text, "CR", {"Barbarian"})
    assert len(grants) == 1
    assert stats["duplicates_collapsed"] == 1


# ---------------------------------------------------------------------------
# Class abilities (feature vere con BONUS grezzi e prerequisiti)
# ---------------------------------------------------------------------------


def test_abilities_from_records_campi():
    entries, stats = pcc.abilities_from_records(
        pcc.iter_lst_records(ABILITIES_CLASS_LST),
        "CR",
        known_classes={"Barbarian", "Bard", "Monk"},
    )
    by_key = {e["key"]: e for e in entries}

    rage = by_key["Barbarian ~ Rage"]
    assert rage["name"] == "Rage"
    assert rage["source_book"] == "CR"
    assert rage["category"] == "Special Ability"
    assert rage["class"] == "Barbarian"  # da KEY "Barbarian ~ ..."
    assert rage["bonus"][0]["group"] == "VAR"
    assert rage["bonus"][0]["recognized"] is True
    assert rage["source_page"] == "p.32"

    ts = by_key["Barbarian ~ Trap Sense"]
    assert ts["prerequisites"][0]["tag"] == "PRELEVEL"
    assert ts["bonus"][0]["valueNumber"] == 1
    assert ts["bonus"][0]["type"] == "Luck"

    # classe dal TYPE <X>ClassFeatures quando la KEY non la da'
    bk = next(e for e in entries if e["name"] == "Bardic Knowledge")
    assert bk["key"] == "Bardic Knowledge"
    assert bk["class"] == "Bard"

    # stesso nome, KEY diverse: due entry distinte (mai fuse)
    assert by_key["Monk ~ Fast Movement"]["class"] == "Monk"

    # righe .MOD / CATEGORY=... non producono entry
    assert all("MOD" not in e["key"] for e in entries)
    # record CATEGORY:Class (contenitori di classe) non sono feature
    assert "Barbarian" not in by_key
    assert "Barbarian ~ Standard Class" not in by_key

    # DESC MAI esportato (policy: solo meccaniche+nomi)
    assert "desc" not in {k.lower() for e in entries for k in e}

    assert stats["bonus"]["feats_with_bonus"] >= 3


def test_abilities_class_sconosciuta_dichiarata():
    text = (
        "Mystery Feature\tCATEGORY:Special Ability\tTYPE:Generic\t"
        "BONUS:COMBAT|AC|1\n"
    )
    entries, _stats = pcc.abilities_from_records(
        pcc.iter_lst_records(text), "CR", known_classes={"Barbarian"}
    )
    assert entries[0]["class"] is None


# ---------------------------------------------------------------------------
# Build end-to-end su radice PCGen finta
# ---------------------------------------------------------------------------


def _fake_pcgen_root(tmp_path: Path) -> Path:
    root = tmp_path / "pcgen-repo"
    base = root / "data/pathfinder/paizo"
    for book, cfg in pcc.BOOK_CLASS_FILES.items():
        d = base / cfg["dir"]
        if book == "CR":
            _write(d, "cr_classes.lst", CLASSES_LST)
            _write(d, "cr_abilities_class.lst", ABILITIES_CLASS_LST)
            _write(d, "cr_abilities_globalvar.lst", "# vuoto\n")
        elif book == "APG":
            _write(d, "apg_classes.lst", APG_CLASSES_LST)
            _write(d, "apg_abilities_class.lst", "# vuoto\n")
            _write(d, "apg_abilities_globalvar.lst", ABILITIES_GLOBALVAR_LST)
        elif book == "OA":
            _write(d, "oa_classes.lst", OA_CLASSES_LST)
            _write(d, "oa_abilities_class.lst", "# vuoto\n")
        else:
            # libri configurati ma senza contenuto rilevante: file stub
            for rel in (
                cfg.get("classes", [])
                + cfg.get("abilities", [])
                + cfg.get("mod_files", [])
            ):
                _write(d, rel, "# finto\n")
    return root


def test_build_progression_end_to_end(tmp_path):
    root = _fake_pcgen_root(tmp_path)
    payload = pcc.build_progression(root)
    prov = payload["_provenance"]
    assert prov["license"]
    assert prov["desc_policy"]
    assert prov["books"]
    by_class = {e["class"]: e for e in payload["entries"]}
    # classi dai tre libri finti, con grant dalle TRE sorgenti
    assert {"Barbarian", "Bard", "Oracle", "Kineticist"} <= set(by_class)
    assert any(g["kind"] == "pool" for g in by_class["Barbarian"]["grants"])
    assert by_class["Oracle"]["source_books"] == ["APG"]
    # i grant di una classe si fondono fra classi.lst e righe MOD
    rage = [
        g
        for g in by_class["Barbarian"]["grants"]
        if g.get("names") == ["Barbarian ~ Rage"]
    ]
    assert rage and rage[0]["level"] == 1


def test_build_abilities_end_to_end(tmp_path):
    root = _fake_pcgen_root(tmp_path)
    payload = pcc.build_abilities(root)
    assert payload["_provenance"]["license"]
    keys = {e["key"] for e in payload["entries"]}
    assert "Barbarian ~ Rage" in keys
    assert payload["counts"]["CR"] == len(
        [e for e in payload["entries"] if e["source_book"] == "CR"]
    )


def test_build_file_configurato_mancante_errore(tmp_path):
    root = tmp_path / "pcgen-repo"
    (root / "data/pathfinder/paizo").mkdir(parents=True)
    with pytest.raises(FileNotFoundError):
        pcc.build_progression(root, books=["CR"])
    with pytest.raises(FileNotFoundError):
        pcc.build_abilities(root, books=["CR"])


def test_main_scrive_i_due_json(tmp_path):
    root = _fake_pcgen_root(tmp_path)
    out = tmp_path / "out"
    rc = pcc.main(["--pcgen-repo", str(root), "--out-dir", str(out)])
    assert rc == 0
    prog = json.loads(
        (out / "pcgen-class-progression.json").read_text(encoding="utf-8")
    )
    abil = json.loads((out / "pcgen-class-abilities.json").read_text(encoding="utf-8"))
    assert prog["entries"] and abil["entries"]
    assert prog["_provenance"]["license"]


# ---------------------------------------------------------------------------
# Smoke sui dati REALI (salta se il clone PCGen non c'e'): spot-check RAW sul
# corpus Valdombra (barbarian, rogue, oracle, skald, fighter, cavalier) e
# sulle forme speciali (ACG righe livello, OA CATEGORY=CLASS, pool cadenze).
# ---------------------------------------------------------------------------

REAL_ROOT = Path(os.environ.get("PCGEN_REPO", r"C:\Users\VGit\Downloads\pcgen-repo"))


def _grant_levels(entry, name):
    return sorted(g["level"] for g in entry["grants"] if g.get("names") == [name])


@pytest.mark.skipif(
    not (REAL_ROOT / "data/pathfinder/paizo").is_dir(), reason="clone PCGen assente"
)
def test_dati_reali_progressione_spot_check():
    payload = pcc.build_progression(REAL_ROOT)
    by_class = {e["class"]: e for e in payload["entries"]}

    barb = by_class["Barbarian"]
    assert _grant_levels(barb, "Barbarian ~ Rage") == [1]
    assert _grant_levels(barb, "Barbarian ~ Trap Sense") == [3]
    assert _grant_levels(barb, "Barbarian ~ Greater Rage") == [11]
    assert _grant_levels(barb, "Barbarian ~ Mighty Rage") == [20]
    # cadenza rage power: pool "Rage Power" a 2,4,...,20
    rage_pool = sorted(
        g["level"]
        for g in barb["grants"]
        if g["kind"] == "pool" and g["pool"] == "Rage Power"
    )
    assert rage_pool == [2, 4, 6, 8, 10, 12, 14, 16, 18, 20]

    rogue = by_class["Rogue"]
    assert _grant_levels(rogue, "Rogue ~ Evasion") == [2]
    assert _grant_levels(rogue, "Rogue ~ Master Strike") == [20]
    talent_pool = sorted(
        g["level"]
        for g in rogue["grants"]
        if g["kind"] == "pool" and g["pool"] == "Rogue Talent"
    )
    assert talent_pool == [2, 4, 6, 8, 10, 12, 14, 16, 18, 20]

    oracle = by_class["Oracle"]
    assert _grant_levels(oracle, "Oracle's Curse") == [1]

    skald = by_class["Skald"]
    assert _grant_levels(skald, "Skald ~ Inspired Rage") == [1]
    assert _grant_levels(skald, "Skald ~ Spell Kenning") == [5]
    # NOTA divergenza documentata (INTERPRETATIONS.md di rules-engine-v2):
    # PCGen concede Dirge of Doom al 10° (anche nel suo DESC), il RAW ACG/AoN
    # lo da' all'8°. L'importer riporta fedelmente PCGen (10); la tabella
    # manuale del motore (8) resta la fonte per questa feature.
    assert _grant_levels(skald, "Skald ~ Dirge of Doom") == [10]
    assert _grant_levels(skald, "Skald ~ Master Skald") == [20]

    fighter = by_class["Fighter"]
    assert _grant_levels(fighter, "Fighter ~ Bravery") == [2]
    assert _grant_levels(fighter, "Fighter ~ Weapon Training") == [5]

    cavalier = by_class["Cavalier"]
    assert _grant_levels(cavalier, "Cavalier ~ Challenge") == [1]

    # ACG: progressione da righe livello del classes.lst
    arcanist = by_class["Arcanist"]
    assert _grant_levels(arcanist, "Arcanist ~ Greater Arcanist Exploits") == [11]
    assert _grant_levels(arcanist, "Arcanist ~ Magical Supremacy") == [20]

    # OA: MOD con CATEGORY=CLASS maiuscolo
    kineticist = by_class["Kineticist"]
    assert _grant_levels(kineticist, "Kineticist ~ Burn") == [1]

    # cadenze pool con gate PRECLASS (forma reale ACG/UC)
    hunter = by_class["Hunter"]
    assert sorted(
        g["level"]
        for g in hunter["grants"]
        if g["kind"] == "pool" and g["pool"] == "Hunter Teamwork Feats"
    ) == [3, 6, 9, 12, 15, 18]
    magus = by_class["Magus"]
    assert sorted(
        g["level"]
        for g in magus["grants"]
        if g["kind"] == "pool" and g["pool"] == "Magus Bonus Feat"
    ) == [5, 11, 17]
    gunslinger = by_class["Gunslinger"]
    assert sorted(
        g["level"]
        for g in gunslinger["grants"]
        if g["kind"] == "pool" and g["pool"] == "Gun Training Choice"
    ) == [5, 9, 13, 17]

    # cadenze a conteggio VAR (pool-var): investigator talents ogni 2 dal 3°
    investigator = by_class["Investigator"]
    assert sorted(
        g["level"]
        for g in investigator["grants"]
        if g["kind"] == "pool-var" and g["pool"] == "InvestigatorTalentCount"
    ) == [3, 5, 7, 9, 11, 13, 15, 17, 19]

    # sanita': ogni libro con classi copre almeno una classe
    for cls in ("Barbarian", "Oracle", "Arcanist", "Magus", "Gunslinger", "Kineticist"):
        assert cls in by_class


@pytest.mark.skipif(
    not (REAL_ROOT / "data/pathfinder/paizo").is_dir(), reason="clone PCGen assente"
)
def test_dati_reali_abilities_spot_check():
    payload = pcc.build_abilities(REAL_ROOT)
    by_key = {e["key"]: e for e in payload["entries"]}

    rage = by_key["Barbarian ~ Rage"]
    assert rage["class"] == "Barbarian"
    assert isinstance(rage["bonus"], list) and rage["bonus"]

    # DESC MAI esportato: nessuna chiave desc e nessun valore lungo di prosa
    for e in payload["entries"]:
        assert "desc" not in {k.lower() for k in e}

    # conteggi per libro (sanita': nessun libro e' sparito)
    for book in ("CR", "APG", "ACG", "ARG", "UM", "UC", "OA"):
        assert payload["counts"][book] > 0

    # i BONUS ci sono in massa e quasi tutti si parsano (stessa soglia feat)
    total = sum(s["bonus"]["total_tags"] for s in payload["stats"].values())
    unrecognized = sum(s["bonus"]["unrecognized"] for s in payload["stats"].values())
    assert total > 1000
    assert unrecognized / total < 0.10


# ---------------------------------------------------------------------------
# Fase A (2026-08-08): BOOK_CLASS_FILES esteso a UI/UW (classi PC Vigilante e
# Shifter), HA/PU/AG (abilities soltanto: HA ha solo il phantom "Undead
# Phantom" — non una classe PC, classes.lst NON configurato, dichiarato; PU
# non ha classes.lst — le varianti Unchained vivono negli abilities; AG ha
# solo prestige class — classes.lst NON configurato, fuori perimetro,
# dichiarato come per HA).
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not (REAL_ROOT / "data/pathfinder/paizo").is_dir(), reason="clone PCGen assente"
)
def test_dati_reali_vigilante_shifter():
    progression = pcc.build_progression(REAL_ROOT)
    by_class = {e["class"]: e for e in progression["entries"]}
    # le due classi PC dei manuali fuori linea core (D6: erano corpus_missing)
    assert "Vigilante" in by_class  # Ultimate Intrigue
    assert "Shifter" in by_class  # Ultimate Wilderness
    assert "UI" in by_class["Vigilante"]["source_books"]
    assert "UW" in by_class["Shifter"]["source_books"]
    assert by_class["Vigilante"]["grants"]
    assert by_class["Shifter"]["grants"]
    # il phantom di Horror Adventures NON e' una classe PC: fuori perimetro
    assert "Undead Phantom" not in by_class

    abilities = pcc.build_abilities(REAL_ROOT)
    by_key = {e["key"]: e for e in abilities["entries"]}
    # spot-check RAW (nomi verificati nel clone 2026-08-08)
    assert "Social Talent ~ Case The Joint" in by_key  # UI, pool vigilante
    assert by_key["Shifter ~ Weapon and Armor Proficiencies"]["class"] == "Shifter"
    # conteggi per libro (sanita': nessun libro nuovo e' sparito)
    for book in ("UI", "UW", "HA", "PU", "AG"):
        assert abilities["counts"][book] > 0
