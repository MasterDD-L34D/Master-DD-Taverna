"""Test per tools/import_feats_aon.py -- talenti mancanti da AoN (2026-11-01).

Il censimento AoN vs catalogo (2026-11-01) ha trovato ~690 talenti OGL
assenti da feats.json: l'import li aggiunge, senza toccare le voci esistenti.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.import_feats_aon import (
    build_new_entries,
    feat_entry,
    index_feat_names,
    missing_feats,
)

URL = "https://aonprd.com/FeatDisplay.aspx?ItemName=Pack%20Flanking"


def test_feat_entry_tipo_nei_tag_e_nome_pulito():
    page = {
        "name": "Pack Flanking (Combat, Teamwork)",
        "source": "PRPG Advanced Class Guide",
        "flavor": "You and your companion are adept at flanking.",
        "prerequisites": ["Int 13", "Combat Expertise"],
        "benefit": "When you and your companion flank, you gain +2.",
    }
    e = feat_entry(page, URL)
    assert e["name"] == "Pack Flanking"
    assert e["tags"] == ["combat", "teamwork"]
    assert e["source"] == "PRPG Advanced Class Guide"
    assert e["source_id"] == "feats:pack_flanking"
    assert e["prerequisites"] == ["Int 13", "Combat Expertise"]
    assert e["reference_urls"] == [URL]
    assert "Benefit: When you and your companion flank" in e["description"]


def test_missing_feats_confronto_normalizzato():
    catalogo = [
        {"name": "Power Attack"},
        {"name": "Vital Strike, Greater"},
        {"name": "Erastil's Blessing"},
    ]
    indice = [
        "power attack",
        "Greater Vital Strike",
        "Erastil’s  Blessing",
        "Pack Flanking",
    ]
    assert missing_feats(indice, catalogo) == ["Pack Flanking"]


def test_missing_feats_numero_romano_finale_come_arabo():
    catalogo = [{"name": "Summon Nature's Ally 3"}]
    assert missing_feats(["Summon Nature's Ally III", "Fey Form I"], catalogo) == [
        "Fey Form I"
    ]


def test_index_feat_names_dai_link_featdisplay():
    # Forma dell'indice reale Feats.aspx: un link FeatDisplay per riga,
    # nome codificato nell'URL, lo stesso talento puo' comparire due volte.
    html = (
        "<table><tr><td><a href='FeatDisplay.aspx?ItemName=Power%20Attack'>"
        "Power Attack</a></td></tr>"
        '<tr><td><a href="FeatDisplay.aspx?ItemName=Erastil\'s%20Blessing">'
        "Erastil's Blessing</a></td></tr>"
        "<tr><td><a href='FeatDisplay.aspx?ItemName=Power%20Attack'>x</a></td></tr>"
        "<tr><td><a href='Rules.aspx?Name=Feats'>Feats</a></td></tr></table>"
    )
    assert index_feat_names(html) == ["Power Attack", "Erastil's Blessing"]


def test_build_new_entries_divide_pi_e_registra_i_fallimenti():
    pagine = {
        "Pack Flanking": {
            "name": "Pack Flanking (Combat)",
            "source": "ACG",
            "flavor": "",
            "prerequisites": [],
            "benefit": "B.",
        },
        "Aldori Dueling Mastery": {
            "name": "Aldori Dueling Mastery (Combat)",
            "source": "ISWG",
            "flavor": "",
            "prerequisites": [],
            "benefit": "B.",
        },
    }

    def scarica_e_analizza(nome):
        if nome not in pagine:
            raise OSError("HTTP 404")
        return pagine[nome]

    ogl, local, falliti = build_new_entries(
        ["Pack Flanking", "Aldori Dueling Mastery", "Assente"], scarica_e_analizza
    )
    assert [e["name"] for e in ogl] == ["Pack Flanking"]
    assert [e["name"] for e in local] == ["Aldori Dueling Mastery"]  # nome PI
    assert len(falliti) == 1 and "Assente" in falliti[0]


def test_build_new_entries_pi_nella_descrizione_va_in_locale():
    # Stessa regola degli archetipi (is_pi_entry): nome neutro, descrizione
    # con un luogo di Golarion che la sanitize non toglie -> local-only.
    pagina = {
        "name": "Loyal Retainer",
        "source": "X",
        "flavor": "You serve the throne of Brevoy.",
        "prerequisites": [],
        "benefit": "B.",
    }
    ogl, local, _ = build_new_entries(["Loyal Retainer"], lambda nome: pagina)
    assert ogl == []
    assert [e["name"] for e in local] == ["Loyal Retainer"]


def test_main_write_aggiunge_in_coda_e_aggiorna_manifest(tmp_path, monkeypatch):
    import json

    import tools.import_feats_aon as mod

    feats = tmp_path / "feats.json"
    feats.write_text(json.dumps({"entries": [{"name": "Power Attack"}]}), "utf-8")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "files": {"feats": {"entries": 1}},
                "catalogs": [
                    {"kind": "feats", "entries": 1},
                    {"kind": "feats_local", "entries": 0},
                ],
            }
        ),
        "utf-8",
    )
    monkeypatch.setattr(mod, "FEATS_PATH", feats)
    monkeypatch.setattr(mod, "LOCAL_PATH", tmp_path / "local" / "feats_local.json")
    monkeypatch.setattr(mod, "MANIFEST_PATH", manifest)
    indice = (
        "<a href='FeatDisplay.aspx?ItemName=Power%20Attack'>a</a>"
        "<a href='FeatDisplay.aspx?ItemName=Pack%20Flanking'>b</a>"
    )
    monkeypatch.setattr(mod, "fetch", lambda url, delay=0: indice)
    monkeypatch.setattr(
        mod,
        "parse_feat_page",
        lambda html: {
            "name": "Pack Flanking (Combat)",
            "source": "ACG",
            "flavor": "",
            "prerequisites": [],
            "benefit": "B.",
        },
    )

    assert mod.main(["--write"]) == 0
    nomi = [e["name"] for e in json.loads(feats.read_text("utf-8"))["entries"]]
    assert nomi == ["Power Attack", "Pack Flanking"]
    m = json.loads(manifest.read_text("utf-8"))
    assert m["files"]["feats"]["entries"] == 2
    assert [c["entries"] for c in m["catalogs"] if c["kind"] == "feats"] == [2]
