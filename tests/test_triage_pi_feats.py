"""Test per tools/triage_pi_feats.py.

Fixture sintetiche in memoria: nessun IO su data/reference/ogl/feats.json.
Copre la categorizzazione A/B/C/D (severita' D > A > B > C), le regressioni
word-boundary ("next" vs "Nex", "mental shackles") e i dangling refs
(esatto vs embedded, esclusione sotto-nomi tipo "Aldori Style Aegis").
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.triage_pi_feats import _categorize, _dangling_refs


def entry(name, prereq=None, desc="", refs=None):
    """Entry sintetica minima nel formato catalogo feats."""
    return {
        "name": name,
        "prerequisites": prereq if prereq is not None else [],
        "description": desc,
        "references": refs if refs is not None else [],
    }


class TestCategorize:
    def test_artifact_vince_su_match_pi(self):
        # Nome corrotto da sanitize storica (artifact) + termine PI in
        # description: vince la categoria piu' severa (D).
        cat, matches, artifacts = _categorize(
            entry("Noble Scion a fading empire", desc="le scuole della Inner Sea region"))
        assert cat == "D"
        assert artifacts
        assert "inner sea" in matches["description"]

    def test_match_nome_e_description_a(self):
        cat, matches, _ = _categorize(
            entry("Aldori Style", desc="tradizione di spada Aldori"))
        assert cat == "A"
        assert "aldori" in matches["name"]

    def test_match_nome_vince_su_deita_nei_prereq(self):
        # PI sia nel nome sia (deita') nei prereq: A vince su B.
        cat, _, _ = _categorize(
            entry("Hellknight Aegis", prereq=["worshiper of Rovagug"]))
        assert cat == "A"

    def test_deita_nei_prereq_b(self):
        cat, matches, _ = _categorize(
            entry("Squash Flat", prereq=["Improved Bull Rush", "worshiper of Rovagug"]))
        assert cat == "B"
        assert "rovagug" in matches["prerequisites"]

    def test_solo_description_c(self):
        cat, _, _ = _categorize(
            entry("Scholar", desc="scuole sparse per la Inner Sea region"))
        assert cat == "C"

    def test_prereq_non_deita_c(self):
        cat, _, _ = _categorize(entry("Loyal To The Death", prereq=["Human (Tian)"]))
        assert cat == "C"

    def test_nessun_match_ignora_entry(self):
        cat, _, _ = _categorize(entry("Acrobatic", desc="ti muovi con grazia"))
        assert cat is None


class TestRegressioneWordBoundary:
    def test_next_non_matcha_nex(self):
        # Regressione storica: senza boundary "Nex" matchava "next".
        cat, _, _ = _categorize(
            entry("Rapid Strike", desc="your next turn, the next attack"))
        assert cat is None

    def test_mental_shackles_non_matcha(self):
        # "Shackles" scartato come falso positivo (sostantivo comune
        # "catene", non la nazione pirata): non e' in lista termini.
        cat, _, _ = _categorize(
            entry("Heroic Will", desc="breaks free from mental shackles"))
        assert cat is None

    def test_shoanti_tribe_matcha(self):
        cat, matches, _ = _categorize(
            entry("Totem Spirit", prereq=["Member of a Shoanti tribe"]))
        assert cat == "C"
        assert "shoanti" in matches["prerequisites"]


class TestDanglingRefs:
    def test_match_esatto(self):
        entries = [entry("Aldori Style Aegis", prereq=["Aldori Style"])]
        res = _dangling_refs(entries, ["Aldori Style"], {"Aldori Style"})
        assert res["Aldori Style"]["exact"] == [
            ("Aldori Style Aegis", "prerequisites", "Aldori Style")]

    def test_escluso_sotto_nome_piu_lungo(self):
        # "Aldori Style" dentro il riferimento ad "Aldori Style Aegis"
        # (entry piu' lunga del catalogo): non e' un ref al target.
        entries = [entry("Aldori Style Aegis",
                         refs=["Archives of a deity of magic: Aldori Style Aegis"])]
        res = _dangling_refs(entries, ["Aldori Style"], set())
        assert "Aldori Style" not in res

    def test_embedded_tag_incollato(self):
        entries = [entry("Djinni Spin", prereq=["Ea bardental Fist**"])]
        res = _dangling_refs(entries, ["Ea bardental Fist"], set())
        embedded = res["Ea bardental Fist"]["embedded"]
        assert embedded == [("Djinni Spin", "prerequisites", "Ea bardental Fist**")]

    def test_prereq_non_lista_non_esplode(self):
        # Guard isinstance: campo malformato (stringa, non lista) trattato
        # come elemento singolo, senza iterare i caratteri.
        malformed = entry("Qualcosa", prereq="Aldori Style")
        res = _dangling_refs([malformed], ["Aldori Style"], set())
        assert res["Aldori Style"]["exact"] == [
            ("Qualcosa", "prerequisites", "Aldori Style")]

    def test_self_reference_ignorata(self):
        entries = [entry("Aldori Style", prereq=["Aldori Style"])]
        res = _dangling_refs(entries, ["Aldori Style"], {"Aldori Style"})
        assert "Aldori Style" not in res
