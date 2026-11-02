"""Test per lo scan PI con modello locale (2026-11-02).

Lo scan gemma4:e4b su feats/archetypes/spells ha trovato nomi propri di
Golarion assenti dalla lista del gate (Darklands, Red Mantis, Acadamae...).
Questi test coprono i termini nuovi nel gate e la policy A/B/C che li
applica (A nome / B prerequisiti -> pi_local_only, C solo testo -> sanitize).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from tools.legal_filter import GATE_LLM_SCAN_TERMS, _find_pi
from tools.sanitize_reference_pi import sanitize_text
from tools.apply_pi_scan_policy import apply_policy, classify, sanitize_c


def test_gate_riconosce_i_termini_dello_scan():
    hits = [h["term"] for h in _find_pi("She trained at the Acadamae in her youth.")]
    assert hits == ["Acadamae"]


def test_gate_riconosce_i_termini_dal_campione_di_controllo():
    # Sfuggito al modello, trovato rileggendo il campione delle sanitize.
    assert [h["term"] for h in _find_pi("forth from the Tanglebriar")] == [
        "Tanglebriar"
    ]
    assert [h["term"] for h in _find_pi("or Lirgeni astrologers")] == ["Lirgeni"]


def test_gate_riconosce_la_harrowed_society():
    hits = [h["term"] for h in _find_pi("the secretive Harrowed Society")]
    assert hits == ["Harrowed Society"]


def test_gate_riconosce_la_twilight_academy():
    hits = [h["term"] for h in _find_pi("a frontier land's Twilight Academy")]
    assert hits == ["Twilight Academy"]


def test_gate_riconosce_i_termini_dello_scan_degli_oggetti_magici():
    # Secondo giro dello scan (2026-11-02, items.json): gli artefatti portano
    # nomi propri di Golarion che il primo giro non aveva visto.
    hits = [h["term"] for h in _find_pi("forged by the runelord Karzoug")]
    assert "Karzoug" in hits


def test_gate_riconosce_graydirge():
    # Sfuggito al modello, trovato rileggendo il campione degli oggetti.
    hits = [h["term"] for h in _find_pi("the undead-ruled city of Graydirge")]
    assert hits == ["Graydirge"]


def test_i_titoli_dei_manuali_non_sono_violazioni():
    # Policy titoli libro separata (precedente: Sargava). Il termine nudo
    # nella prosa resta una violazione.
    assert _find_pi("Pathfinder Player Companion: Dragon Empires Primer") == []
    assert _find_pi("Heroes Of The Darklands") == []
    assert [h["term"] for h in _find_pi("Travelers in the Dragon Empires")] == [
        "Dragon Empires"
    ]


@pytest.mark.parametrize("term", sorted(GATE_LLM_SCAN_TERMS))
def test_la_sanitize_della_description_toglie_ogni_termine_nuovo(term):
    testo = f"Agents of the {term} often travel far."
    pulito = sanitize_text(testo, description=True)
    assert _find_pi(pulito) == [], pulito


def test_la_sanitize_resta_leggibile_sulle_frasi_composte():
    # Forme reali trovate nel campione di controllo (2026-11-02).
    assert sanitize_text(
        "the paladins of the Mendevian Crusades", description=True
    ) == ("the paladins of the great crusades")
    assert sanitize_text("the ancient Shory aeromancers", description=True) == (
        "the ancient sky-city aeromancers"
    )
    assert (
        sanitize_text(
            "such as the Esoteric Order of the Palatine Eye.", description=True
        )
        == "such as a society of occultists."
    )


def test_la_sanitize_degli_aggettivi_di_luogo_resta_naturale():
    # Forma reale (Veil of Attentiveness): "elven-capital diplomats" stonava.
    assert sanitize_text("popular among Iadaran diplomats", description=True) == (
        "popular among elven diplomats"
    )


def test_classify_nome_prerequisiti_testo_pulito():
    assert classify({"name": "Darklands Scholar", "description": "x"}) == "A"
    assert classify({"name": "X", "prerequisites": ["worshiper of Apsu"]}) == "B"
    assert classify({"name": "X", "description": "born in the Darklands"}) == "C"
    assert classify({"name": "X", "tags": ["race:triaxian"]}) == "C"
    assert classify({"name": "X", "description": "a plain feat"}) is None


def test_sanitize_c_ripulisce_il_testo_e_toglie_i_tag_identificativi():
    voce = {
        "name": "Deep Sailor",
        "source": "Heroes of the Darklands",
        "description": "Sailors of the Darklands know its rivers.",
        "tags": ["feat", "race:triaxian", "Dragon Empires Primer"],
    }
    pulita = sanitize_c(voce)
    assert pulita["name"] == "Deep Sailor"
    assert pulita["source"] == "Heroes of the Darklands"
    assert pulita["description"] == "Sailors of the underground realms know its rivers."
    # Tag identificativo (forma chiave:valore) tolto; il titolo di manuale
    # mascherato dal gate resta.
    assert pulita["tags"] == ["feat", "Dragon Empires Primer"]
    assert classify(pulita) is None


def _riferimento(tmp_path):
    import json

    ref = tmp_path / "reference"
    (ref / "ogl").mkdir(parents=True)
    (ref / "pi_local_only").mkdir()
    voci = [
        {"name": "Darklands Scholar", "source_id": "feats:a", "description": "x"},
        {"name": "Faithful", "source_id": "feats:b", "prerequisites": ["worship Apsu"]},
        {"name": "Deep Sailor", "source_id": "feats:c", "description": "the Darklands"},
        {"name": "Power Attack", "source_id": "feats:d", "description": "plain"},
    ]
    (ref / "ogl" / "feats.json").write_text(json.dumps({"entries": voci}), "utf-8")
    vecchia = {"name": "Old PI", "source_id": "feats:old"}
    (ref / "pi_local_only" / "feats_local.json").write_text(
        json.dumps({"entries": [vecchia]}), "utf-8"
    )
    manifest = {
        "catalogs": [
            {"file": "ogl/feats.json", "kind": "feats", "is_ogc": True, "entries": 4},
            {
                "file": "pi_local_only/feats_local.json",
                "kind": "feats_local",
                "local_only": True,
            },
        ],
        "files": {"feats": {"path": "ogl/feats.json", "entries": 4}},
    }
    (ref / "manifest.json").write_text(json.dumps(manifest), "utf-8")
    return ref, voci


def test_apply_policy_dry_run_classifica_senza_toccare_i_file(tmp_path):
    import json

    ref, voci = _riferimento(tmp_path)
    dry = apply_policy(ref, write=False)
    assert dry["moved"] == {"feats": ["Darklands Scholar", "Faithful"]}
    assert dry["sanitized"] == {"feats": ["Deep Sailor"]}
    assert (
        json.loads((ref / "ogl" / "feats.json").read_text("utf-8"))["entries"] == voci
    )


def test_apply_policy_write_sposta_aggiungendo_e_aggiorna_il_manifest(tmp_path):
    import json

    ref, _ = _riferimento(tmp_path)
    apply_policy(ref, write=True)
    pubbliche = json.loads((ref / "ogl" / "feats.json").read_text("utf-8"))["entries"]
    assert [e["name"] for e in pubbliche] == ["Deep Sailor", "Power Attack"]
    assert pubbliche[0]["description"] == "the underground realms"
    locali = json.loads((ref / "pi_local_only" / "feats_local.json").read_text("utf-8"))
    # I file locali hanno gia' le voci delle policy precedenti: si aggiunge.
    assert [e["name"] for e in locali["entries"]] == [
        "Old PI",
        "Darklands Scholar",
        "Faithful",
    ]
    m = json.loads((ref / "manifest.json").read_text("utf-8"))
    assert m["catalogs"][0]["entries"] == 2
    assert m["files"]["feats"]["entries"] == 2
    assert b"\r\n" not in (ref / "ogl" / "feats.json").read_bytes()
    # Idempotente: un secondo giro non trova niente da fare.
    assert apply_policy(ref, write=True) == {"moved": {}, "sanitized": {}}


def test_apply_policy_registra_nel_manifest_un_file_locale_nuovo(tmp_path):
    import json

    ref, _ = _riferimento(tmp_path)
    m = json.loads((ref / "manifest.json").read_text("utf-8"))
    m["catalogs"] = [c for c in m["catalogs"] if c["kind"] != "feats_local"]
    (ref / "manifest.json").write_text(json.dumps(m), "utf-8")
    (ref / "pi_local_only" / "feats_local.json").unlink()

    apply_policy(ref, write=True)
    m = json.loads((ref / "manifest.json").read_text("utf-8"))
    locale = [c for c in m["catalogs"] if c["file"] == "pi_local_only/feats_local.json"]
    assert len(locale) == 1 and locale[0]["local_only"] is True
    assert locale[0]["entries"] == 2


def test_main_dry_run_di_default_e_write_su_richiesta(tmp_path, monkeypatch, capsys):
    import json

    import tools.apply_pi_scan_policy as mod

    ref, voci = _riferimento(tmp_path)
    monkeypatch.setattr(mod, "REFERENCE_DIR", ref)
    assert mod.main([]) == 0
    assert "spostate 2, sanitizzate 1" in capsys.readouterr().out
    assert (
        json.loads((ref / "ogl" / "feats.json").read_text("utf-8"))["entries"] == voci
    )
    assert mod.main(["--write"]) == 0
    assert (
        len(json.loads((ref / "ogl" / "feats.json").read_text("utf-8"))["entries"]) == 2
    )
