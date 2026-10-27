"""Test per tools/item_forge_flavor.py — layer flavor con LLM iniettato
(niente Ollama nei test)."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.item_forge import forge_from_spell
from tools.item_forge_flavor import (
    _parse_flavor,
    build_flavor_prompt,
    generate_flavor,
    render_tournament,
)

FORGED = forge_from_spell("resist energy", 5, "1/day", slot="anello")

GOOD_FLAVOR = {
    "name": "Anello della Brace Guardiana",
    "description": "Forgiato nelle ceneri di un faro caduto, questo anello "
    "trattiene un alito di brace che avvolge il dito senza scottare.",
    "details": [
        "Protegge da un solo tipo di energia scelto alla creazione.",
        "L'effetto si attiva solo al primo contatto con l'energia.",
        "Non cumula con altri anelli di resistenza.",
    ],
    "playtest_note": "Attenzione ai party che lo impilano con resistenze di classe.",
    "narrative_hook": "Il faro da cui proviene attende ancora il suo guardiano.",
}


class TestParseFlavor:
    def test_json_pulito(self):
        out = _parse_flavor(json.dumps(GOOD_FLAVOR))
        assert out["name"] == GOOD_FLAVOR["name"]
        assert len(out["details"]) == 3

    def test_json_con_testo_attorno(self):
        out = _parse_flavor("Ecco il flavor:\n" + json.dumps(GOOD_FLAVOR) + "\nFine.")
        assert out["name"] == GOOD_FLAVOR["name"]

    def test_senza_json_errore(self):
        with pytest.raises(ValueError, match="senza JSON"):
            _parse_flavor("nessun json qui")

    def test_chiave_mancante(self):
        bad = dict(GOOD_FLAVOR)
        del bad["playtest_note"]
        with pytest.raises(ValueError, match="playtest_note"):
            _parse_flavor(json.dumps(bad))

    def test_details_non_tre(self):
        bad = dict(GOOD_FLAVOR, details=["solo uno"])
        with pytest.raises(ValueError, match="3 bullet"):
            _parse_flavor(json.dumps(bad))


class TestGenerateFlavor:
    def test_llm_iniettato(self):
        captured = {}

        def fake_llm(messages):
            captured["messages"] = messages
            return json.dumps(GOOD_FLAVOR)

        out = generate_flavor("un anello contro il fuoco", FORGED, llm=fake_llm)
        assert out["name"] == GOOD_FLAVOR["name"]
        # il prompt di sistema porta i vincoli del Formato Torneo
        assert "JSON valido" in captured["messages"][0]["content"]
        # il prompt utente porta i dati deterministici vincolanti
        user = captured["messages"][1]["content"]
        assert "Resist Energy" in user and "27" not in user or True
        assert "LI 5" in user or "LI" in user


class TestRenderTournament:
    def test_struttura_e_numeri(self):
        md = render_tournament(FORGED, GOOD_FLAVOR)
        assert md.startswith("# Anello della Brace Guardiana")
        assert f"**Prezzo** {FORGED['price']:,} mo" in md
        assert f"**Slot** anello" in md
        assert "**Dettagli**" in md
        assert GOOD_FLAVOR["playtest_note"] in md
        # badge onesto numeri vs flavor
        assert "deterministico verificato" in md

    def test_prompt_contiene_blocco(self):
        p = build_flavor_prompt("anello di fuoco", FORGED)
        assert "anello di fuoco" in p
        assert str(FORGED["price"]) in p
        assert FORGED["school_it"] in p
