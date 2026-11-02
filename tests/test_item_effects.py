"""Effetti strutturati degli oggetti a slot dalle descrizioni AoN (E8-bis).

Solo bonus statici tipizzati, nel vocabolario dei bersagli del motore
pathmaster (BonusTarget): il resto dell'oggetto resta testo, mai inventato.
"""

from tools.item_effects import apply_effects, extract_bonuses, extract_item_effects

PAGINA_AON = "https://aonprd.com/MagicBeltsDisplay.aspx?ItemName=Belt"


def test_bonus_di_potenziamento_a_una_caratteristica():
    testo = "The belt grants the wearer a +2 enhancement bonus to Strength."
    assert extract_bonuses(testo) == [
        {"type": "enhancement", "target": "str", "value": 2}
    ]


def test_resistenza_su_tutti_i_tiri_salvezza_diventa_tre_bonus():
    testo = "This cloak offers a +3 resistance bonus on all saving throws."
    assert extract_bonuses(testo) == [
        {"type": "resistance", "target": "save.fort", "value": 3},
        {"type": "resistance", "target": "save.ref", "value": 3},
        {"type": "resistance", "target": "save.will", "value": 3},
    ]


def test_bonus_condizionato_non_produce_effetti():
    # "contro le malattie" non e' un bersaglio del motore: mai un +4 a tutti i TS
    testo = "It grants a +4 resistance bonus on saving throws against disease."
    assert extract_bonuses(testo) == []


def test_condizione_prima_del_bonus_nella_stessa_frase_lo_scarta():
    # Moss Cloak: il +10 vale solo in foresta; "When worn," invece e' il
    # semplice indossare e il bonus resta.
    moss = (
        "When donned in forest or jungle terrain, a moss cloak gives its "
        "wearer a +10 competence bonus on Stealth checks."
    )
    assert extract_bonuses(moss) == []
    stag = "When worn, the helm grants a +2 competence bonus on Perception checks."
    assert extract_bonuses(stag) == [
        {"type": "competence", "target": "skill.perception", "value": 2}
    ]


def test_attivazione_nella_frase_precedente_scarta_il_bonus():
    # Ring of Chameleon Power: il +10 c'e' solo dopo l'attivazione
    testo = (
        "As a free action, the wearer of this ring can gain the ability to "
        "magically blend in with her surroundings. This provides a +10 "
        "competence bonus on her Stealth checks."
    )
    assert extract_bonuses(testo) == []


def test_bonus_di_un_aura_non_e_un_bonus_dell_oggetto_indossato():
    testo = (
        "This aura provides a +4 deflection bonus to AC and a +4 resistance "
        "bonus on saving throws against attacks made by evil creatures."
    )
    assert extract_bonuses(testo) == []


def test_bonus_alla_ca_per_tipo():
    testo = "This ring offers a +2 deflection bonus to AC."
    assert extract_bonuses(testo) == [
        {"type": "deflection", "target": "ac", "value": 2}
    ]


def test_competenza_su_abilita_anche_di_piu_parole():
    testo = (
        "The wearer gains a +5 competence bonus on Sleight of Hand checks "
        "and a +5 competence bonus on Stealth checks."
    )
    assert extract_bonuses(testo) == [
        {"type": "competence", "target": "skill.sleight-of-hand", "value": 5},
        {"type": "competence", "target": "skill.stealth", "value": 5},
    ]


def test_caratteristica_con_possessivo_e_score():
    testo = "The headband grants the wearer a +2 enhancement bonus to her Wisdom score."
    assert extract_bonuses(testo) == [
        {"type": "enhancement", "target": "wis", "value": 2}
    ]


def test_tiri_salvezza_singoli_e_in_coppia():
    testo = (
        "While worn, the cloak imparts a +1 resistance bonus on Fortitude and "
        "Reflex saves and a +2 resistance bonus on Will saves."
    )
    assert extract_bonuses(testo) == [
        {"type": "resistance", "target": "save.fort", "value": 1},
        {"type": "resistance", "target": "save.ref", "value": 1},
        {"type": "resistance", "target": "save.will", "value": 2},
    ]


def test_lista_di_abilita_un_bonus_per_abilita():
    testo = (
        "They provide a +2 competence bonus on Acrobatics, Climb, and Stealth checks."
    )
    assert extract_bonuses(testo) == [
        {"type": "competence", "target": "skill.acrobatics", "value": 2},
        {"type": "competence", "target": "skill.climb", "value": 2},
        {"type": "competence", "target": "skill.stealth", "value": 2},
    ]


def test_armatura_e_armatura_naturale_vanno_nelle_loro_componenti_di_ca():
    assert extract_bonuses("These bracers grant a +3 armor bonus to AC.") == [
        {"type": "armor", "target": "acArmor", "value": 3}
    ]
    assert extract_bonuses(
        "The amulet grants a +2 enhancement bonus to natural armor."
    ) == [{"type": "enhancement", "target": "acNatural", "value": 2}]


def test_apply_scrive_effects_solo_sugli_oggetti_a_slot_del_corpo():
    cintura = {
        "name": "Belt of Giant Strength +2",
        "tags": ["wondrous", "slot:belt"],
        "reference_urls": [PAGINA_AON],
        "description": "It grants a +2 enhancement bonus to Strength.",
    }
    artefatto = {
        "name": "Crown of X",
        "tags": ["artifact", "slot:head"],
        "description": "It grants a +2 enhancement bonus to Strength.",
    }
    apply_effects([cintura, artefatto])
    assert cintura["mechanics"]["effects"] == [
        {
            "variant": None,
            "bonuses": [{"type": "enhancement", "target": "str", "value": 2}],
        }
    ]
    assert "mechanics" not in artefatto


def test_main_write_riscrive_il_catalogo_nello_stesso_formato(tmp_path):
    import json

    from tools.item_effects import main

    path = tmp_path / "items.json"
    data = {
        "_license": "OGL",
        "entries": [
            {
                "name": "Cintura della forza +2",
                "tags": ["slot:belt"],
                "reference_urls": [PAGINA_AON],
                "description": "Conferisce un bonus di miglioramento +2 al punteggio di Forza.",
            }
        ],
    }
    path.write_bytes(json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8"))
    main([str(path), "--write"])
    raw = path.read_bytes().decode("utf-8")
    assert not raw.endswith("\n") and "\r\n" not in raw
    assert json.loads(raw)["entries"][0]["mechanics"]["effects"][0]["bonuses"] == [
        {"type": "enhancement", "target": "str", "value": 2}
    ]


def test_apply_solo_su_voci_attestate_da_una_pagina_oggetto_aon():
    # "Guanti della destrezza +4" non esiste in PF1: ha solo un link di
    # RICERCA AoN. Regola C9-S3: un nome non attestato non diventa meccanica.
    inventato = {
        "name": "Guanti della destrezza +4",
        "tags": ["slot:hands"],
        "reference_urls": ["https://aonprd.com/Search.aspx?Query=Guanti"],
        "description": "Conferisce un bonus di miglioramento +4 al punteggio di Destrezza.",
    }
    vero = {
        "name": "Ring of Protection +1",
        "tags": ["slot:ring"],
        "reference_urls": ["https://aonprd.com/MagicRingsDisplay.aspx?ItemName=Ring"],
        "description": "Conferisce un bonus di deviazione +1 alla CA.",
    }
    apply_effects([inventato, vero])
    assert "mechanics" not in inventato
    assert vero["mechanics"]["effects"][0]["bonuses"] == [
        {"type": "deflection", "target": "ac", "value": 1}
    ]


def test_voce_con_piu_nel_nome_prende_il_suo_valore_dal_testo_a_varianti():
    entry = {
        "name": "Belt of Giant Strength +2",
        "description": "It grants the wearer an enhancement bonus to Strength "
        "of +2, +4, or +6.",
    }
    assert extract_item_effects(entry) == [
        {
            "variant": None,
            "bonuses": [{"type": "enhancement", "target": "str", "value": 2}],
        }
    ]


def test_varianti_con_nome_non_ricevono_effetti():
    # Ring of Swimming: il testo descrive la base (+5), la variante
    # "improved" e' un'altra cosa (+10). Assegnarle il +5 sarebbe inventare.
    entry = {
        "name": "Ring of Swimming",
        "description": "It grants the wearer a +5 competence bonus on Swim checks.",
        "mechanics": {"variants": ["improved"]},
    }
    assert extract_item_effects(entry) == []


def test_forma_italiana_delle_voci_storiche():
    testo = "Conferisce un bonus di resistenza +2 a tutti i tiri salvezza."
    assert extract_bonuses(testo) == [
        {"type": "resistance", "target": "save.fort", "value": 2},
        {"type": "resistance", "target": "save.ref", "value": 2},
        {"type": "resistance", "target": "save.will", "value": 2},
    ]


def test_voce_aon_con_varianti_un_effetto_per_variante():
    entry = {
        "name": "Belt of Mighty Constitution",
        "description": "The belt grants the wearer an enhancement bonus to "
        "Constitution of +2, +4, or +6.",
        "mechanics": {"variants": ["+2", "+4", "+6"]},
    }
    assert extract_item_effects(entry) == [
        {
            "variant": "+2",
            "bonuses": [{"type": "enhancement", "target": "con", "value": 2}],
        },
        {
            "variant": "+4",
            "bonuses": [{"type": "enhancement", "target": "con", "value": 4}],
        },
        {
            "variant": "+6",
            "bonuses": [{"type": "enhancement", "target": "con", "value": 6}],
        },
    ]
