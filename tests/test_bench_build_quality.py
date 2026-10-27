"""Gate A2-a2 (piano planning/2026-10-27-a2a-banco-qualita-build.md): banco.

Il banco ricalcola con src/pc le statistiche dichiarate dalle build e
riporta quattro esiti distinti (concorda/diverge/non_verificabile/rifiutato).
Gate: corpus smoke deterministico (seed fisso), livello 1 sempre presente e
separato, DPR dichiarato non verificabile, exit 0 (D6: riporta non giudica).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from bench_build_quality import (
    SAVES_MAP,
    classi_complete,
    confronta,
    corpus_smoke,
    main,
    razze_complete,
    report,
)


def test_censimento_coerente_con_engine():
    # le classi "complete" devono avere hd + progression 1-5 (verificato a mano)
    assert len(classi_complete()) == 40
    assert len(razze_complete()) == 63
    assert "Fighter" in classi_complete() and "Human" in razze_complete()


def test_corpus_smoke_deterministico_e_stratificato():
    def triple(p):
        return (p["request"]["class"], p["request"]["race"], p["pc_draft"]["level"])

    a, b = corpus_smoke(), corpus_smoke()
    assert [triple(p) for p in a] == [triple(p) for p in b]  # seed fisso: niente scelta a mano (P3)
    assert len(a) == 20
    livelli = {p["pc_draft"]["level"] for p in a}
    assert livelli == {1, 2, 3, 4, 5}


def test_confronta_esiti_validi_e_mapping_saves():
    for p in corpus_smoke(n=8):
        r = confronta(p)
        assert r["esito"] in ("concorda", "diverge", "non_verificabile", "rifiutato")
        assert set(SAVES_MAP) == {"Tempra", "Riflessi", "Volonta"}
        if r["esito"] == "concorda":
            for k, d in r["dettaglio"].items():
                if k != "DPR":
                    assert d["esito"] == "concorda"


def test_dpr_sempre_non_verificabile():
    r = confronta(corpus_smoke(n=1)[0])
    assert r["dettaglio"]["DPR"]["esito"] == "non_verificabile"


def test_report_separa_livello_1():
    risultati = [confronta(p) for p in corpus_smoke()]
    txt = report(risultati)
    assert "== livello 1 (4 build) ==" in txt
    assert "== livelli 2-5 (16 build) ==" in txt
    assert "tier/meta_tier NON verificato" in txt


def test_exit_sempre_zero_su_smoke():
    assert main(["--n", "5"]) == 0  # D6: soglia exit 1 solo dopo baseline fixture


def _draft_pc(equipment=None, race="Human", class_="Fighter"):
    return {
        "name": "t", "method": "point-buy", "campaign_type": "Standard Fantasy",
        "abilities": {"str": 13, "dex": 13, "con": 13, "int": 12, "wis": 10, "cha": 10},
        "race": race, "class": class_, "favored_class_bonus": "hp", "level": 5,
        "hp_method": "average", "skills": {}, "feats": [], "traits": [],
        "equipment": equipment or [], "spells": [], "race_bonus_ability": "con",
    }


def test_razza_incompleta_non_verificabile():
    # P2 Codex: razze come Android (senza ability_mods/size/speed) devono
    # risultare non_verificabili, non concordare/divergere con default falsati
    r = confronta({"pc_draft": _draft_pc(race="Android")})
    assert r["esito"] == "non_verificabile"
    assert "Android" in r["motivo"]


def test_equip_non_modellato_rende_ca_non_verificabile():
    # P2 Codex: oggetti fuori catalogo ignorati dall'engine — la CA non e'
    # confrontabile anche se la tolleranza +-1 coprirebbe la differenza
    payload = {
        "pc_draft": _draft_pc(equipment=["Ring of Protection +3"]),
        "benchmark": {"statistics": {"PF": 49, "CA": 14, "DPR": 9,
                                     "saves": {"Tempra": 6, "Riflessi": 2, "Volonta": 1}}},
    }
    r = confronta(payload)
    assert r["dettaglio"]["CA"]["esito"] == "non_verificabile"
    assert "Ring of Protection +3" in r["dettaglio"]["CA"]["motivo"]


def test_rifiutate_ricomparsi_nel_report():
    # P2 Codex: le build rifiutate dall'engine sparivano dal report (nessun
    # level nei ritorni anticipati) — ora sono rendicontate col loro livello
    buona = confronta({"pc_draft": _draft_pc()})
    rifiutata = confronta({"pc_draft": _draft_pc(class_="FakeClass")})
    assert rifiutata["esito"] == "rifiutato"
    assert rifiutata["level"] == 5
    txt = report([buona, rifiutata])
    assert "rifiutato=1" in txt  # conteggiata nel gruppo livelli 2-5, non sparita


def test_bonus_razziale_ts_non_verificabile():
    # P2 Codex g2: Svirfneblin ha "Fortunate: +2 racial bonus on all saving
    # throws" che l'engine non applica — la tolleranza +-1 attribuirebbe alla
    # build un errore dell'engine: tutto il gruppo TS e' non_verificabile
    r = confronta({"pc_draft": _draft_pc(race="Svirfneblin")})
    for ita in SAVES_MAP:
        assert r["dettaglio"][f"TS {ita}"]["esito"] == "non_verificabile", ita


def test_bozza_malformata_non_rompe_il_corpus():
    # P2 Codex g2: skills:null fa AttributeError dentro build_character — la
    # bozza deve risultare rifiutata, non interrompere l'intero corpus
    bozza = _draft_pc()
    bozza["skills"] = None
    r = confronta({"pc_draft": bozza})
    assert r["esito"] == "rifiutato"
    assert r["level"] == 5


def test_bonus_razziale_ca_non_verificabile():
    # P2 Codex g3: Sahuagin ha +3 natural armor non modellato dall'engine —
    # CA corretta dichiarata verrebbe classificata diverge: non_verificabile.
    # Dwarf/Gnome hanno dodge SOLO condizionale (against giants): verificabili
    r = confronta({
        "pc_draft": _draft_pc(race="Sahuagin"),
        "benchmark": {"statistics": {"PF": 49, "CA": 14, "DPR": 9,
                                     "saves": {"Tempra": 6, "Riflessi": 2, "Volonta": 1}}},
    })
    assert r["dettaglio"]["CA"]["esito"] == "non_verificabile"
    assert "razziale" in r["dettaglio"]["CA"]["motivo"]
    for razza_condizionale in ("Dwarf", "Gnome"):
        payload = {
            "pc_draft": _draft_pc(race=razza_condizionale),
            "benchmark": {"statistics": {"PF": 49, "CA": 11, "DPR": 9,
                                         "saves": {"Tempra": 6, "Riflessi": 2, "Volonta": 1}}},
        }
        # CA 11 = 10 + dex 1: senza bonus condizionali il confronto resta valido
        assert confronta(payload)["dettaglio"]["CA"]["esito"] in ("concorda", "diverge")
