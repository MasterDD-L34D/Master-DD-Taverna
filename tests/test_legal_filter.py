"""Test per tools/legal_filter.py (gate PI esteso word-boundary, Task 3).

Piano: planning/2026-07-19-pi-feats-triage.md. Copre:
- la fonte unica della lista (`PI_TERMS`/`DEITY_TERMS` vivono in
  legal_filter e il triage li importa: niente doppie liste);
- i match positivi ("worship Rovagug", "Shoanti tribe") e le regressioni
  word-boundary ("your next turn" NON matcha "Nex", "mental shackles" NON
  matcha: "Shackles" scartato come falso positivo nel triage);
- il masking dei replacement sanctioned ("the inner sea region" contiene
  "inner sea" ma e' testo sanitize legittimo; un "Inner Sea" nudo fallisce);
- l'esclusione documentata "Sargava" (hit solo come titolo libro in
  source/source_id; policy titoli libro separata);
- lo stato dei cataloghi committati: feats.json sanitize a 0 violazioni
  (incluse le 8 citazioni "Path Of The Hellknight" -> "a strict-order
  handbook"), traits/equipment chiusi con la policy estesa (A/B in
  pi_local_only/traits_local.json + equipment_local.json, C sanitize in
  place): il gate deve dare 0 violazioni su tutti i cataloghi OGL.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import tools.legal_filter as gate
import tools.triage_pi_feats as triage
from tools.legal_filter import _find_pi

REPO_ROOT = Path(__file__).resolve().parents[1]
FEATS_JSON = REPO_ROOT / "data" / "reference" / "ogl" / "feats.json"

HELLKNIGHT_ENTRIES = {
    "Caster's Champion", "Extended Scrying", "Gate Breaker", "Scrutinize Spell",
    "Relic Breaker", "Censoring Critical", "Dislocate", "Traditional Weapons",
}


class TestFonteUnica:
    def test_triage_importa_pi_terms_da_legal_filter(self):
        # Fonte unica: il simbolo del triage E' quello del gate (stesso
        # oggetto, non copia). Contenuto invariato: 75 termini.
        assert triage.PI_TERMS is gate.PI_TERMS
        assert len(gate.PI_TERMS) == 75

    def test_triage_importa_deity_terms_da_legal_filter(self):
        assert triage.DEITY_TERMS is gate.DEITY_TERMS
        assert len(gate.DEITY_TERMS) == 22

    def test_pi_words_copre_triage_legacy_e_candidati(self):
        # Il gate scansiona l'unione: 75 triage + legacy (iconici, marchi,
        # luoghi storici del gate) + candidati zero-hit del triage.
        assert set(gate.PI_TERMS) <= gate.PI_WORDS
        for term in ("Paizo", "Lem", "Seelah", "Azlant", "Thassilon",
                     "Stolen Lands", "Magnimar", "Aroden", "Mephistopheles",
                     "Cyth-V'sug", "Xin"):
            assert term in gate.PI_WORDS

    def test_sargava_escluso_documentato(self):
        # "Sargava" NON va in lista gate: hit solo come titolo libro in
        # source/tags (decisione documentata nel triage § Copertura).
        assert "Sargava" not in gate.PI_WORDS
        assert _find_pi("Sargava, the Lost Colony pg. 12") == []


class TestMatchPositivi:
    def test_worship_rovagug_fallisce(self):
        hits = _find_pi("worshiper of Rovagug")
        assert any(h["term"] == "Rovagug" for h in hits)

    def test_shoanti_tribe_fallisce(self):
        hits = _find_pi("Member of a Shoanti tribe")
        assert any(h["term"] == "Shoanti" for h in hits)

    def test_osiria_matcha_gate(self):
        # "Osiria" (variante di Osirion): residuo nel prereq di Bureaucrat's
        # Favored rilevato in quality review; aggiunta ai candidati del gate.
        hits = _find_pi("Associated with the court of the Black Dome in Osiria")
        assert any(h["term"] == "Osiria" for h in hits)

    def test_termine_canonico_nel_hit(self):
        # Il hit riporta il termine canonico della lista, non la forma
        # maiuscola/minuscola trovata nel testo.
        hits = _find_pi("scuole di ROVAGUG e del GOLARION")
        terms = {h["term"] for h in hits}
        assert "Rovagug" in terms
        assert "Golarion" in terms


class TestRegressioneWordBoundary:
    def test_next_non_matcha_nex(self):
        assert _find_pi("on your next turn, the next attack") == []

    def test_mental_shackles_non_matcha(self):
        # "Shackles" scartato nel triage come falso positivo (sostantivo
        # comune "catene", non la nazione pirata): non e' in lista.
        assert _find_pi("breaks free from mental shackles") == []

    def test_osiria_non_matcha_dentro_osirian(self):
        # Il termine "Osiria" (quality review Task 3) non deve matchare
        # dentro "Osirian" (gia' termine a se'): un solo hit, canonico.
        hits = _find_pi("an Osirian tradesperson")
        assert [h["term"] for h in hits] == ["Osirian"]


class TestMaskSanctioned:
    def test_the_inner_sea_region_non_matcha(self):
        # Replacement sanctioned: testo legittimo prodotto dalla sanitize.
        assert _find_pi("schools of the inner sea region and beyond") == []

    def test_inner_sea_nudo_matcha(self):
        hits = _find_pi("colleges of the Inner Sea")
        assert any(h["term"] == "Inner Sea" for h in hits)

    def test_mask_non_nasconde_pi_fuori_dal_replacement(self):
        hits = _find_pi("the inner sea region, poi verso Cheliax")
        assert [h["term"] for h in hits] == ["Cheliax"]


def _scan_cataloghi():
    """Replica la scansione del gate sui cataloghi del manifest (senza
    scrivere report): ritorna {catalog: [(entry, campo, termine)]}."""
    manifest = gate._load_manifest()
    out = {}
    for catalog in manifest.get("catalogs", []):
        if catalog.get("local_only") or "pi_local_only" in catalog.get("file", ""):
            continue
        path = gate.REFERENCE_DIR / catalog["file"]
        data = json.loads(path.read_text(encoding="utf-8"))
        if not catalog.get("is_ogc"):
            continue
        kind = catalog.get("kind") or Path(catalog["file"]).stem
        entries = data.get("entries", []) if isinstance(data, dict) else data
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            name = entry.get("name", "?")
            for field, value in entry.items():
                if field not in gate.SCANNED_FIELDS:
                    continue
                # Stessa semantica di run(): _iter_strings filtra i sotto-campi
                # non scansionati anche nei dict annidati.
                for text in gate._iter_strings({field: value}):
                    for hit in gate._find_pi(text):
                        out.setdefault(kind, []).append((name, field, hit["term"]))
    return out


class TestStatoCataloghi:
    def test_cataloghi_ogl_zero_violazioni(self):
        # Dopo la policy traits/equipment (Task 3 esteso, stessa disciplina
        # dei feats): NESSUN catalogo OGL contribuisce violazioni al gate
        # esteso. Il debito preesistente (traits 14, equipment 8) e' chiuso:
        # A/B in pi_local_only, C sanitize in place.
        assert _scan_cataloghi() == {}


class TestCataloghiLocali:
    """I cataloghi locali generati dalla policy traits/equipment (Task 3)."""

    LOCAL = REPO_ROOT / "data" / "reference" / "pi_local_only"

    def test_local_registrati_local_only(self):
        manifest = json.loads(
            (REPO_ROOT / "data/reference/manifest.json").read_text(encoding="utf-8"))
        by_file = {c["file"]: c for c in manifest["catalogs"]}
        for path, kind in (("pi_local_only/traits_local.json", "traits_local"),
                           ("pi_local_only/equipment_local.json", "equipment_local")):
            cat = by_file[path]
            assert cat["local_only"] is True and cat["is_ogc"] is False
            assert cat["kind"] == kind and cat["entries"] == 4

    def test_local_contenuto_verbatim(self):
        traits = json.loads((self.LOCAL / "traits_local.json").read_text(encoding="utf-8"))
        assert traits["_license"] == "OGL-1.0a" and traits["_source"]
        by_name = {e["name"]: e for e in traits["entries"]}
        assert set(by_name) == {"Aldori Caution", "Arodenite Sword Training",
                                "Arodenite Historian", "Gifted Smuggler"}
        # Verbatim: PI integrale conservata nel catalogo locale.
        assert "Aldori" in by_name["Aldori Caution"]["description"]
        assert by_name["Gifted Smuggler"]["prerequisites"] == ["Ostenso"]
        equip = json.loads((self.LOCAL / "equipment_local.json").read_text(encoding="utf-8"))
        assert equip["_license"] == "OGL-1.0a" and equip["_source"]
        assert {e["name"] for e in equip["entries"]} == {
            "Hellknight leather", "Hellknight half-plate",
            "Hellknight plate", "Alkenstar fortress plate"}

    def test_counts_ogl_aggiornati(self):
        traits = json.loads(
            (REPO_ROOT / "data/reference/ogl/traits.json").read_text(encoding="utf-8"))
        equip = json.loads(
            (REPO_ROOT / "data/reference/ogl/equipment_mundane.json").read_text(encoding="utf-8"))
        assert len(traits["entries"]) == 470 - 4
        assert len(equip["entries"]) == 790 - 4
        nomi_t = {e["name"] for e in traits["entries"]}
        assert not {"Aldori Caution", "Arodenite Sword Training",
                    "Arodenite Historian", "Gifted Smuggler"} & nomi_t
        nomi_e = {e["name"] for e in equip["entries"]}
        assert not {"Hellknight leather", "Hellknight half-plate",
                    "Hellknight plate", "Alkenstar fortress plate"} & nomi_e

    def test_c_sanitize_in_place(self):
        traits = json.loads(
            (REPO_ROOT / "data/reference/ogl/traits.json").read_text(encoding="utf-8"))
        by_name = {e["name"]: e for e in traits["entries"]}
        desc = {n: by_name[n]["description"] for n in (
            "Dueling Cloak Adept", "Crusader", "Divine Denier",
            "Bureaucrat's Favored", "Scholar of the Analects",
            "Stabbing Spells", "Reassuring Advice")}
        assert "a dueling sword" in desc["Dueling Cloak Adept"]
        assert "Aldori" not in desc["Dueling Cloak Adept"]
        assert "a demon-blighted land" in desc["Crusader"]
        assert "godless" in desc["Divine Denier"]
        assert "a desert metropolis" in desc["Bureaucrat's Favored"]
        assert "a dead god" in desc["Scholar of the Analects"]
        assert desc["Reassuring Advice"].count("a dead god") == 3
        # I nomi delle entry C non sono mai toccati (policy).
        assert by_name["Scholar of the Analects"]["name"] == "Scholar of the Analects"
        # Fix quality review: residuo "Osiria" nel prereq sanitizzato con la
        # forma neutra della famiglia Osirion (set base REPLACEMENTS).
        assert by_name["Bureaucrat's Favored"]["prerequisites"] == [
            "Associated with the court of the Black Dome in an ancient desert kingdom"]


class TestSanitizeHellknightFeats:
    def test_nessun_residuo_titolo(self):
        text = FEATS_JSON.read_text(encoding="utf-8")
        assert "Path Of The Hellknight" not in text
        assert "Hellknight" not in text

    def test_otto_entry_sanitizzate_source_id_intatto(self):
        data = json.loads(FEATS_JSON.read_text(encoding="utf-8"))
        hits = [e for e in data["entries"]
                if e.get("source") == "a strict-order handbook"]
        assert {e["name"] for e in hits} == HELLKNIGHT_ENTRIES
        for e in hits:
            assert e["tags"] == ["a strict-order handbook"]
            assert e["source_id"].startswith("path_of_the_hellknight:")
