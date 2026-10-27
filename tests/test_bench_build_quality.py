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
