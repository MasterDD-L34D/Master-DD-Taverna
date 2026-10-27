"""Test per tools/import_pathbuilder_equipment.py — equipaggiamento PB.

Slice D4 (piano 2026-08-02): import di data_weapons.xml (313 righe),
data_armor.xml (58 righe) e data_equipment_slotted.xml (2.855 righe) da
`data/reference/pi_local_only/pathbuilder/` (PI local-only, MAI committato)
verso UN JSON committato in pathmaster-dd src/data/: pathbuilder-equipment.json.

Forma reale dei file (ricognizione 2026-08-07): <Root><Row>.

- data_weapons.xml: <Weapon>, <DamageType> (S/P/B, combo "B and P", o '0' =
  nessun danno), <Proficiency> (-1 naturale/disarmato, 0 semplice, 1 da guerra,
  2 esotica, 3 da fuoco), <Category> (0 leggera, 1 a una mano, 2 a due mani,
  3 da tiro, 4 da fuoco a una mano, 5 da fuoco a due mani, 6 naturale),
  <Damage> ('-1' = nessun danno: touch attack, reti, blast cinetici),
  <CritRange> (minimo del dado: 19 = 19-20; -1 = nessun critico),
  <CritMultiplier>, <Finessable>, <WeaponGroup> (gruppi separati da '&'),
  <Hands> (0 = una mano o leggera, 1 = due mani), <RangeIncrement> (0 = n/a),
  <UsesAmmo> (opzionale), <naturalWeapon> (FALSE/false/true/TRUE).
  NESSUN costo/peso nel dato: dichiarati assenti, mai da inventare.
- data_armor.xml: <Armor>, <Bonus>, <MaxDex> (99 = nessun cap),
  <CheckPenalty> (MAGNITUDINE positiva: 5 = ACP -5 RAW), <Arcane_Spell>
  (frazione: 0.3 = 30%), <Speed_30ft> (-1 = n/a, scudi), <Weight1>,
  <Category> (0 leggera, 1 media, 2 pesante, 3 scudo, 4 scudo torre,
  5 accessorio magico — Bracers of Armor). NESSUN costo nel dato.
- data_equipment_slotted.xml: <Name>, <Cost> (mo), <Ref> (URL d20pfsrd, mai
  esportato: riferimento PI), <Slot> (codice numerico 0-25, mappa etichette
  DICHIARATA nel dato, derivata da ispezione dei membri), <Description>
  (testo Paizo PI — MAI esportato), <Source>, <Finished>. 72 righe SENZA
  Name sono template di bonus (BonusType/Amount), non oggetti: saltate e
  conteggiate nel report. 6 nomi compaiono due volte con slot/fonte diversi
  (Darkflare, Pantograph, ...): entrambe le voci restano, duplicati
  dichiarati nel report.

Policy OGL: il JSON committato non include mai la Description ne' il Ref.
Gli enhancement magici restano preset di nome+stat base: MAI bonus inventato.
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools import import_pathbuilder_equipment as pbe

# ---------------------------------------------------------------------------
# Fixture: forma reale (campi nell'ordine osservato nei file veri).
# ---------------------------------------------------------------------------

WEAPONS_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Root xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
\t<Row>
\t\t<Weapon>Longsword</Weapon>
\t\t<DamageType>S</DamageType>
\t\t<Proficiency>1</Proficiency>
\t\t<Category>1</Category>
\t\t<Damage>1d8</Damage>
\t\t<CritRange>19</CritRange>
\t\t<CritMultiplier>2</CritMultiplier>
\t\t<Finessable>false</Finessable>
\t\t<WeaponGroup>Blades&amp;Heavy</WeaponGroup>
\t\t<Hands>0</Hands>
\t\t<DefaultDamage>2</DefaultDamage>
\t\t<RangeIncrement>0</RangeIncrement>
\t\t<naturalWeapon>FALSE</naturalWeapon>
\t</Row>
\t<Row>
\t\t<Weapon>Longbow</Weapon>
\t\t<DamageType>P</DamageType>
\t\t<Proficiency>1</Proficiency>
\t\t<Category>3</Category>
\t\t<Damage>1d8</Damage>
\t\t<CritRange>20</CritRange>
\t\t<CritMultiplier>3</CritMultiplier>
\t\t<Finessable>false</Finessable>
\t\t<WeaponGroup>Bows</WeaponGroup>
\t\t<Hands>1</Hands>
\t\t<DefaultDamage>2</DefaultDamage>
\t\t<RangeIncrement>100</RangeIncrement>
\t\t<naturalWeapon>FALSE</naturalWeapon>
\t</Row>
\t<Row>
\t\t<Weapon>Kukri</Weapon>
\t\t<DamageType>S</DamageType>
\t\t<Proficiency>1</Proficiency>
\t\t<Category>0</Category>
\t\t<Damage>1d4</Damage>
\t\t<CritRange>18</CritRange>
\t\t<CritMultiplier>2</CritMultiplier>
\t\t<Finessable>true</Finessable>
\t\t<WeaponGroup>Blades&amp;Light</WeaponGroup>
\t\t<Hands>0</Hands>
\t\t<DefaultDamage>2</DefaultDamage>
\t\t<RangeIncrement>0</RangeIncrement>
\t\t<naturalWeapon>FALSE</naturalWeapon>
\t</Row>
\t<Row>
\t\t<Weapon>Net</Weapon>
\t\t<DamageType>0</DamageType>
\t\t<Proficiency>2</Proficiency>
\t\t<Category>3</Category>
\t\t<Damage>-1</Damage>
\t\t<CritRange>-1</CritRange>
\t\t<CritMultiplier>-1</CritMultiplier>
\t\t<Finessable>false</Finessable>
\t\t<WeaponGroup>0</WeaponGroup>
\t\t<Hands>1</Hands>
\t\t<DefaultDamage>2</DefaultDamage>
\t\t<RangeIncrement>10</RangeIncrement>
\t\t<naturalWeapon>FALSE</naturalWeapon>
\t</Row>
\t<Row>
\t\t<Weapon>Bite (1d6)</Weapon>
\t\t<DamageType>B and P and S</DamageType>
\t\t<Proficiency>-1</Proficiency>
\t\t<Category>6</Category>
\t\t<Damage>1d6</Damage>
\t\t<CritRange>20</CritRange>
\t\t<CritMultiplier>2</CritMultiplier>
\t\t<Finessable>true</Finessable>
\t\t<WeaponGroup>Natural</WeaponGroup>
\t\t<Hands>0</Hands>
\t\t<DefaultDamage>2</DefaultDamage>
\t\t<naturalWeapon>true</naturalWeapon>
\t</Row>
\t<Row>
\t\t<Weapon>Gnome hooked hammer</Weapon>
\t\t<DamageType>B and P</DamageType>
\t\t<Proficiency>2</Proficiency>
\t\t<Category>2</Category>
\t\t<Damage>1d8&amp;1d6</Damage>
\t\t<CritRange>20</CritRange>
\t\t<CritMultiplier>3&amp;4</CritMultiplier>
\t\t<Finessable>false</Finessable>
\t\t<WeaponGroup>Hammers&amp;Double</WeaponGroup>
\t\t<Hands>1</Hands>
\t\t<DefaultDamage>2</DefaultDamage>
\t\t<RangeIncrement>0</RangeIncrement>
\t\t<naturalWeapon>FALSE</naturalWeapon>
\t</Row>
\t<Row>
\t\t<Weapon>Pistol</Weapon>
\t\t<DamageType>B and P</DamageType>
\t\t<Proficiency>3</Proficiency>
\t\t<Category>4</Category>
\t\t<Damage>1d8</Damage>
\t\t<CritRange>20</CritRange>
\t\t<CritMultiplier>4</CritMultiplier>
\t\t<Finessable>false</Finessable>
\t\t<WeaponGroup>Firearms</WeaponGroup>
\t\t<Hands>0</Hands>
\t\t<DefaultDamage>2</DefaultDamage>
\t\t<RangeIncrement>20</RangeIncrement>
\t\t<UsesAmmo>true</UsesAmmo>
\t\t<naturalWeapon>FALSE</naturalWeapon>
\t</Row>
</Root>
"""

ARMOR_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Root xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
\t<Row>
\t\t<Armor>Padded</Armor>
\t\t<Bonus>1</Bonus>
\t\t<MaxDex>8</MaxDex>
\t\t<CheckPenalty>0</CheckPenalty>
\t\t<Arcane_Spell>0.05</Arcane_Spell>
\t\t<Speed_30ft>30</Speed_30ft>
\t\t<Weight1>10</Weight1>
\t\t<Category>0</Category>
\t</Row>
\t<Row>
\t\t<Armor>Chainmail</Armor>
\t\t<Bonus>6</Bonus>
\t\t<MaxDex>2</MaxDex>
\t\t<CheckPenalty>5</CheckPenalty>
\t\t<Arcane_Spell>0.3</Arcane_Spell>
\t\t<Speed_30ft>20</Speed_30ft>
\t\t<Weight1>40</Weight1>
\t\t<Category>1</Category>
\t</Row>
\t<Row>
\t\t<Armor>Haramaki</Armor>
\t\t<Bonus>1</Bonus>
\t\t<MaxDex>99</MaxDex>
\t\t<CheckPenalty>0</CheckPenalty>
\t\t<Arcane_Spell>0</Arcane_Spell>
\t\t<Speed_30ft>30</Speed_30ft>
\t\t<Weight1>1</Weight1>
\t\t<Category>0</Category>
\t</Row>
\t<Row>
\t\t<Armor>Tower shield</Armor>
\t\t<Bonus>4</Bonus>
\t\t<MaxDex>2</MaxDex>
\t\t<CheckPenalty>10</CheckPenalty>
\t\t<Arcane_Spell>0.5</Arcane_Spell>
\t\t<Speed_30ft>-1</Speed_30ft>
\t\t<Weight1>45</Weight1>
\t\t<Category>4</Category>
\t</Row>
\t<Row>
\t\t<Armor>Bracers of Armor +5</Armor>
\t\t<Bonus>5</Bonus>
\t\t<MaxDex>99</MaxDex>
\t\t<CheckPenalty>0</CheckPenalty>
\t\t<Arcane_Spell>0</Arcane_Spell>
\t\t<Speed_30ft>-1</Speed_30ft>
\t\t<Weight1>1</Weight1>
\t\t<Category>5</Category>
\t</Row>
</Root>
"""

SLOTTED_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Root xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
\t<Row>
\t\t<Name>Amulet of natural armor +1</Name>
\t\t<Cost>2000</Cost>
\t\t<Ref>http://www.d20pfsrd.com/magic-items/wondrous-items/wondrous-items/a-b/amulet-of-natural-armor</Ref>
\t\t<EffectType>9</EffectType>
\t\t<Item>Enhancement</Item>
\t\t<BonusType>Natural</BonusType>
\t\t<Amount>1</Amount>
\t\t<Slot>8</Slot>
\t\t<Description>This amulet toughens the wearer's body and flesh...</Description>
\t\t<Source>Core Rulebook</Source>
\t\t<Finished>Yes</Finished>
\t</Row>
\t<Row>
\t\t<Name>Acrobat slippers</Name>
\t\t<Cost>3000</Cost>
\t\t<Ref>http://www.d20pfsrd.com/magic-items/wondrous-items/wondrous-items/r-z/slippers-acrobat</Ref>
\t\t<Slot>4</Slot>
\t\t<Description>These supple gray leather slippers...</Description>
\t\t<Source>Ultimate Equipment</Source>
\t\t<Finished>Yes</Finished>
\t</Row>
\t<Row>
\t\t<Name>Abjurant salt</Name>
\t\t<Cost>600</Cost>
\t\t<Ref>http://www.d20pfsrd.com/magic-items/wondrous-items/wondrous-items/a-b/abjurant-salt</Ref>
\t\t<Slot>11</Slot>
\t\t<Description>Carried in a tube of beaten silver...</Description>
\t\t<Source>Ultimate Equipment</Source>
\t\t<Finished>Yes</Finished>
\t</Row>
\t<Row>
\t\t<EffectType>4</EffectType>
\t\t<Item>1</Item>
\t\t<BonusType>Enhancement</BonusType>
\t\t<Amount>2</Amount>
\t\t<Finished>Yes</Finished>
\t</Row>
\t<Row>
\t\t<Name>Candle</Name>
\t\t<Cost>0.01</Cost>
\t\t<Ref>http://www.d20pfsrd.com/equipment/goods-and-services</Ref>
\t\t<Slot>15</Slot>
\t\t<Description>A candle dimly illuminates...</Description>
\t\t<Source>Core Rulebook</Source>
\t\t<Finished>Yes</Finished>
\t</Row>
\t<Row>
\t\t<Name>Belt of giant strength +2</Name>
\t\t<Cost>4000</Cost>
\t\t<Ref>http://www.d20pfsrd.com/magic-items/wondrous-items/wondrous-items/a-b/belt-of-giant-strength</Ref>
\t\t<EffectType>4</EffectType>
\t\t<Item>1</Item>
\t\t<BonusType>Enhancement</BonusType>
\t\t<Amount>2</Amount>
\t\t<Slot>0</Slot>
\t\t<Description>This belt grants the wearer an enhancement bonus to Strength...</Description>
\t\t<Source>Core Rulebook</Source>
\t\t<Finished>Yes</Finished>
\t</Row>
</Root>
"""


@pytest.fixture()
def raw_dir(tmp_path: Path) -> Path:
    (tmp_path / "data_weapons.xml").write_text(WEAPONS_XML, encoding="utf-8")
    (tmp_path / "data_armor.xml").write_text(ARMOR_XML, encoding="utf-8")
    (tmp_path / "data_equipment_slotted.xml").write_text(SLOTTED_XML, encoding="utf-8")
    return tmp_path


# ---------------------------------------------------------------------------
# Mappe dichiarate (codici numerici PB -> etichette)
# ---------------------------------------------------------------------------


def test_weapon_categories_dichiarate():
    assert pbe.WEAPON_CATEGORIES == {
        0: "light",
        1: "one-handed",
        2: "two-handed",
        3: "ranged",
        4: "firearm-one-handed",
        5: "firearm-two-handed",
        6: "natural",
    }


def test_weapon_proficiencies_dichiarate():
    assert pbe.WEAPON_PROFICIENCIES == {
        -1: "none",
        0: "simple",
        1: "martial",
        2: "exotic",
        3: "firearm",
    }


def test_armor_categories_dichiarate():
    assert pbe.ARMOR_CATEGORIES == {
        0: "light",
        1: "medium",
        2: "heavy",
        3: "shield",
        4: "tower-shield",
        5: "magic-accessory",
    }


def test_slot_labels_dichiarate_e_complete():
    # mappa derivata da ispezione dei membri (ricognizione 2026-08-07),
    # dichiarata nel dato: tutti i codici 0-25 devono avere etichetta
    assert set(pbe.SLOT_LABELS) == set(range(26))
    assert pbe.SLOT_LABELS[0] == "belt"
    assert pbe.SLOT_LABELS[4] == "feet"
    assert pbe.SLOT_LABELS[8] == "neck"
    assert pbe.SLOT_LABELS[11] == "slotless"
    assert pbe.SLOT_LABELS[12] == "ring"


# ---------------------------------------------------------------------------
# Weapons
# ---------------------------------------------------------------------------


def test_import_weapons_stat_strutturate(raw_dir):
    weapons = pbe.import_weapons(raw_dir)
    by_name = {w["name"]: w for w in weapons}
    ls = by_name["Longsword"]
    assert ls["damage"] == "1d8"
    assert ls["damageType"] == "S"
    assert ls["critRange"] == 19
    assert ls["critMultiplier"] == 2
    assert ls["category"] == 1
    assert ls["categoryLabel"] == "one-handed"
    assert ls["proficiency"] == 1
    assert ls["proficiencyLabel"] == "martial"
    assert ls["finesse"] is False
    assert ls["weaponGroups"] == ["Blades", "Heavy"]
    assert ls["hands"] == 1
    assert ls["rangeIncrement"] is None  # 0 nel dato = n/a
    assert ls["naturalWeapon"] is False


def test_import_weapons_ranged_e_finesse(raw_dir):
    by_name = {w["name"]: w for w in pbe.import_weapons(raw_dir)}
    bow = by_name["Longbow"]
    assert bow["categoryLabel"] == "ranged"
    assert bow["hands"] == 2  # Hands 1 -> due mani
    assert bow["rangeIncrement"] == 100
    kukri = by_name["Kukri"]
    assert kukri["finesse"] is True
    assert kukri["categoryLabel"] == "light"


def test_import_weapons_senza_danno_dichiarato_assente(raw_dir):
    # Net: Damage '-1', DamageType '0', CritRange -1 -> null DICHIARATI,
    # mai inventati. Resta nel dataset (e' un'arma vera), il picker la
    # filtra lato consumatore.
    net = {w["name"]: w for w in pbe.import_weapons(raw_dir)}["Net"]
    assert net["damage"] is None
    assert net["damageType"] is None
    assert net["critRange"] is None
    assert net["critMultiplier"] is None
    assert net["rangeIncrement"] == 10


def test_import_weapons_natural_e_firearm(raw_dir):
    by_name = {w["name"]: w for w in pbe.import_weapons(raw_dir)}
    bite = by_name["Bite (1d6)"]
    assert bite["naturalWeapon"] is True
    assert bite["proficiencyLabel"] == "none"
    assert bite["categoryLabel"] == "natural"
    pistol = by_name["Pistol"]
    assert pistol["proficiencyLabel"] == "firearm"
    assert pistol["categoryLabel"] == "firearm-one-handed"
    assert pistol["usesAmmo"] is True


def test_import_weapons_doppia_valori_per_estremita(raw_dir):
    # armi doppie: Damage e CritMultiplier sono per estremita', separati da
    # '&' nel dato. damage resta la stringa grezza strutturata; critMultiplier
    # singolo e' null DICHIARATO e la coppia va in critMultipliers.
    ghh = {w["name"]: w for w in pbe.import_weapons(raw_dir)}["Gnome hooked hammer"]
    assert ghh["damage"] == "1d8&1d6"
    assert ghh["critMultiplier"] is None
    assert ghh["critMultipliers"] == [3, 4]
    # armi normali: critMultipliers assente (non None)
    ls = {w["name"]: w for w in pbe.import_weapons(raw_dir)}["Longsword"]
    assert "critMultipliers" not in ls


def test_import_weapons_niente_costo_inventato(raw_dir):
    # il dato PB non ha costo/peso per le armi: il campo non esiste proprio
    for w in pbe.import_weapons(raw_dir):
        assert "cost" not in w
        assert "weight" not in w


# ---------------------------------------------------------------------------
# Armor
# ---------------------------------------------------------------------------


def test_import_armor_stat_strutturate(raw_dir):
    armor = pbe.import_armor(raw_dir)
    by_name = {a["name"]: a for a in armor}
    cm = by_name["Chainmail"]
    assert cm["acBonus"] == 6
    assert cm["maxDex"] == 2
    # PB memorizza la MAGNITUDINE positiva: 5 = ACP -5 RAW
    assert cm["armorCheckPenalty"] == -5
    # Arcane_Spell e' una frazione: 0.3 = 30%
    assert cm["arcaneSpellFailure"] == 30
    assert cm["speed30ft"] == 20
    assert cm["weight"] == 40
    assert cm["categoryLabel"] == "medium"


def test_import_armor_maxdex_99_e_speed_meno1_null(raw_dir):
    by_name = {a["name"]: a for a in pbe.import_armor(raw_dir)}
    # MaxDex 99 = nessun cap -> null dichiarato (come ArmorItem.maxDex)
    assert by_name["Haramaki"]["maxDex"] is None
    # Speed_30ft -1 = n/a (scudi) -> null dichiarato
    assert by_name["Tower shield"]["speed30ft"] is None
    ts = by_name["Tower shield"]
    assert ts["categoryLabel"] == "tower-shield"
    assert ts["armorCheckPenalty"] == -10
    boa = by_name["Bracers of Armor +5"]
    assert boa["categoryLabel"] == "magic-accessory"
    assert boa["acBonus"] == 5


def test_import_armor_niente_costo_inventato(raw_dir):
    for a in pbe.import_armor(raw_dir):
        assert "cost" not in a


# ---------------------------------------------------------------------------
# Slotted
# ---------------------------------------------------------------------------


def test_import_slotted_nome_costo_slot_fonte(raw_dir):
    items, skipped = pbe.import_slotted(raw_dir)
    assert skipped == 1  # la riga senza Name (template di bonus)
    by_name = {i["name"]: i for i in items}
    amulet = by_name["Amulet of natural armor +1"]
    assert amulet["cost"] == 2000  # mo, numero
    assert amulet["slot"] == 8
    assert amulet["slotLabel"] == "neck"
    assert amulet["source"] == "Core Rulebook"
    assert by_name["Abjurant salt"]["slotLabel"] == "slotless"
    assert by_name["Belt of giant strength +2"]["slotLabel"] == "belt"
    # costi frazionari nel dato reale (0.01 mo): numero, mai arrotondato
    assert by_name["Candle"]["cost"] == 0.01


def test_import_slotted_mai_description_ne_ref(raw_dir):
    items, _ = pbe.import_slotted(raw_dir)
    for i in items:
        for key in i:
            assert key.lower() not in ("description", "desc", "ref")
    # niente bonus inventato: Amount/BonusType NON entrano nel preset
    for i in items:
        assert "amount" not in {k.lower() for k in i}
        assert "bonustype" not in {k.lower() for k in i}


# ---------------------------------------------------------------------------
# Payload completo (main) — header, conteggi, report
# ---------------------------------------------------------------------------


def test_main_scrive_json_con_header_e_report(raw_dir, tmp_path):
    out_dir = tmp_path / "out"
    rc = pbe.main(["--raw-dir", str(raw_dir), "--out-dir", str(out_dir)])
    assert rc == 0
    payload = json.loads(
        (out_dir / "pathbuilder-equipment.json").read_text(encoding="utf-8")
    )
    prov = payload["_provenance"]
    assert "Pathbuilder" in prov["source"]
    assert prov["generated_by"] == (
        "Master-DD-Taverna/tools/import_pathbuilder_equipment.py"
    )
    assert "OGL" in prov["license"]
    assert "Description" in prov["desc_policy"]
    # mappe dichiarate nel dato
    assert payload["slotLabels"]["11"] == "slotless"
    assert payload["weaponCategories"]["1"] == "one-handed"
    assert payload["armorCategories"]["4"] == "tower-shield"
    counts = payload["counts"]
    assert counts["weapons"] == 7
    assert counts["weaponsWithDamage"] == 6  # Net senza danno
    assert counts["armor"] == 5
    assert counts["slotted"] == 5
    assert counts["slottedUnnamedSkipped"] == 1
    # report: armi senza danno elencate per nome (dichiarato)
    assert payload["report"]["weaponsWithoutDamage"] == ["Net"]
    # nessuna Description/Ref in tutto il payload
    raw = json.dumps(payload)
    assert "This amulet toughens" not in raw
    assert "d20pfsrd.com" not in raw


# ---------------------------------------------------------------------------
# Smoke sui dati REALI (skip se il dataset PI non e' presente)
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[1]
REAL_RAW = REPO_ROOT / "data/reference/pi_local_only/pathbuilder"
REAL_REASON = f"dataset PI local-only assente: {REAL_RAW}"


@pytest.mark.skipif(not (REAL_RAW / "data_weapons.xml").is_file(), reason=REAL_REASON)
def test_dati_reali_weapons_conteggi_e_spot_check():
    weapons = pbe.import_weapons(REAL_RAW)
    assert len(weapons) == 313
    by_name = {w["name"]: w for w in weapons}
    # spot-check RAW: Longsword 1d8, critico 19-20/x2, da guerra, una mano
    ls = by_name["Longsword"]
    assert ls["damage"] == "1d8"
    assert ls["critRange"] == 19
    assert ls["critMultiplier"] == 2
    assert ls["proficiencyLabel"] == "martial"
    assert ls["hands"] == 1
    # Kukri: 18-20/x2, finesse
    assert by_name["Kukri"]["critRange"] == 18
    assert by_name["Kukri"]["finesse"] is True
    # le 13 armi senza danno (touch attack, reti, blast, 'Firearms') dichiarate
    without = [w["name"] for w in weapons if w["damage"] is None]
    assert len(without) == 13
    assert "Net" in without
    # le 2 armi doppie: critMultiplier per estremita' dichiarato in lista
    ghh = by_name["Gnome hooked hammer"]
    assert ghh["damage"] == "1d8&1d6"
    assert ghh["critMultiplier"] is None
    assert ghh["critMultipliers"] == [3, 4]


@pytest.mark.skipif(not (REAL_RAW / "data_armor.xml").is_file(), reason=REAL_REASON)
def test_dati_reali_armor_conteggi_e_spot_check():
    armor = pbe.import_armor(REAL_RAW)
    assert len(armor) == 58
    by_name = {a["name"]: a for a in armor}
    # spot-check RAW: Chainmail CA +6, maxDex 2, ACP -5, fallimento 30%
    cm = by_name["Chainmail"]
    assert cm["acBonus"] == 6
    assert cm["maxDex"] == 2
    assert cm["armorCheckPenalty"] == -5
    assert cm["arcaneSpellFailure"] == 30
    # Full plate +9; Tower shield ACP -10
    assert by_name["Full plate"]["acBonus"] == 9
    assert by_name["Tower shield"]["armorCheckPenalty"] == -10


@pytest.mark.skipif(
    not (REAL_RAW / "data_equipment_slotted.xml").is_file(), reason=REAL_REASON
)
def test_dati_reali_slotted_conteggi_e_spot_check():
    items, skipped = pbe.import_slotted(REAL_RAW)
    assert len(items) == 2783
    assert skipped == 72  # righe senza Name: template di bonus, non oggetti
    by_name = {}
    for i in items:
        by_name.setdefault(i["name"], []).append(i)
    amulet = by_name["Amulet of natural armor +1"][0]
    assert amulet["cost"] == 2000
    assert amulet["slotLabel"] == "neck"
    # 6 nomi duplicati (slot/fonte diversi) dichiarati, mai fusi
    dups = {n for n, v in by_name.items() if len(v) > 1}
    assert dups == {
        "Darkflare",
        "Pantograph",
        "Troll styptic",
        "Goblinvine",
        "Leechwort",
        "Winterbite",
    }
    # 11 voci con Name ma senza Slot nel dato: null DICHIARATI, mai dedotti
    no_slot = [i["name"] for i in items if i["slot"] is None]
    assert len(no_slot) == 11
    assert all(i["slotLabel"] is None for i in items if i["slot"] is None)
    # unica riga con separatore migliaia nel dato: "25,000" -> 25000
    assert by_name["Ambrosial Lotus"][0]["cost"] == 25000
