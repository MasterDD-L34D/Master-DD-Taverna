"""Test per tools/sanitize_reference_pi.py (fix word-boundary, Task 2 policy PI).

Copre la regressione storica della sanitize naive (sostituzioni sottostringa
senza boundary: "Lem" -> "a bard" dentro "elemental" -> "ea bardental",
"Varisia" dentro "Varisian"), il divieto di sanitize del nome (policy: i nomi
con PI vanno in pi_local_only, mai neutralizzati), i possessivi, l'ordine
frasi-prima-di-parole ("Archives of Nethys" prima di "Nethys") e
l'idempotenza sui testi gia' parzialmente sanitize ("the inner sea region").
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import tools.sanitize_reference_pi as sanitize_mod
from tools.sanitize_reference_pi import sanitize_entry, sanitize_text


def entry(name, prereq=None, desc="", refs=None, **extra):
    """Entry sintetica minima nel formato catalogo feats."""
    base = {
        "name": name,
        "prerequisites": prereq if prereq is not None else [],
        "description": desc,
        "references": refs if refs is not None else [],
    }
    base.update(extra)
    return base


class TestWordBoundary:
    def test_lem_non_corrompe_elemental(self):
        # Regressione storica: "Lem" -> "a bard" dentro "elemental",
        # "settlement", "implement", "golems" ("ea bardental", "setta bardent",
        # "impa bardent", "goa bards").
        text = "elemental plane, a settlement, an implement, two golems"
        assert sanitize_text(text) == text

    def test_varisia_non_corrompe_varisian(self):
        # Regressione storica: "Varisia" -> "a frontier land" dentro
        # "Varisian" -> "a frontier landn".
        text = "a Varisian wanderer"
        assert sanitize_text(text) == text

    def test_next_non_matcha_nex(self):
        # "Nex" (termine description-only) non deve matchare "next".
        text = "on your next turn, the next attack"
        assert sanitize_text(text, description=True) == text

    def test_archives_of_nethys_prima_di_nethys(self):
        # Ordine frasi-prima-di-parole: la regola frase-level deve scattare
        # prima di "Nethys" -> "a deity of magic" (bug storico documentato nel
        # triage: "Archives of a deity of magic" in tutto il catalogo).
        assert sanitize_text("Archives of Nethys: Acrobatics") == "Pathfinder PRD: Acrobatics"


class TestInnerSea:
    def test_inner_sea_base(self):
        assert sanitize_text("Inner Sea", description=True) == "the inner sea region"

    def test_inner_sea_con_articolo(self):
        # "the Inner Sea" non deve raddoppiare l'articolo.
        assert sanitize_text("colleges of the Inner Sea", description=True) == \
            "colleges of the inner sea region"

    def test_inner_sea_region_con_articolo(self):
        # Forma originale AoN "the Inner Sea region": normalizzata senza
        # raddoppi ("the the inner sea region region" e' la corruzione naive).
        assert sanitize_text("throughout the Inner Sea region", description=True) == \
            "throughout the inner sea region"

    def test_inner_sea_idempotente(self):
        # Testo gia' sanitize: non raddoppiare ("the the inner sea region region").
        text = "throughout the inner sea region"
        assert sanitize_text(text, description=True) == text

    def test_inner_sea_ripara_raddoppio_storico(self):
        # Corruzione da sanitize parziale storica: riportata alla forma canonica.
        assert sanitize_text("scattered throughout the the inner sea region region.",
                             description=True) == \
            "scattered throughout the inner sea region."

    def test_doppia_applicazione_identica(self):
        text = "schools of the Inner Sea and beyond"
        once = sanitize_text(text, description=True)
        assert sanitize_text(once, description=True) == once

    def test_an_inner_sea_articolo(self):
        # Edge case da review: "an Inner Sea" non deve produrre il raddoppio
        # d'articolo "an the inner sea region".
        assert sanitize_text("an Inner Sea port", description=True) == \
            "the inner sea region port"

    def test_an_inner_sea_region_articolo(self):
        assert sanitize_text("an Inner Sea region port", description=True) == \
            "the inner sea region port"


class TestNomeMaiToccato:
    def test_name_taldor_non_modificato(self):
        # Policy: il nome con PI non si sanitizza MAI (va in pi_local_only).
        e = entry("Taldor's Chosen", desc="cavaliere di Taldor")
        out = sanitize_entry(e)
        assert out["name"] == "Taldor's Chosen"
        assert out["description"] != e["description"]

    def test_name_termine_description_only_non_modificato(self):
        # Anche i termini description-only (Aldori, ...) non toccano il nome.
        e = entry("Aldori Style", desc="tradizione di spada Aldori")
        out = sanitize_entry(e)
        assert out["name"] == "Aldori Style"

    def test_name_varisian_tattoo_non_corrotto(self):
        e = entry("Varisian Tattoo", desc="a tattoo")
        assert sanitize_entry(e)["name"] == "Varisian Tattoo"


class TestPossessivi:
    def test_erastils(self):
        assert sanitize_text("Erastil's Blessing") == "a god of the hunt's Blessing"

    def test_taldors(self):
        assert sanitize_text("Taldor's armies") == "a fading empire's armies"

    def test_apostrofo_finale_senza_s(self):
        # Termine che finisce con apostrofo: il boundary regex deve reggerlo.
        # (L'articolo "the" residuo e' comportamento storico del replacement,
        # fuori scope correggerlo qui.)
        assert sanitize_text("the Sodden Lands' coast") == "the a storm-ravaged coast's coast"


class TestTerminiDescriptionOnly:
    def test_aldori_solo_in_description(self):
        # I nuovi termini (Aldori, Hellknight, Nex, ...) si applicano SOLO al
        # campo description, mai ai prerequisites (policy Task 2).
        e = entry("Duelist", prereq=["Aldori Dueling Disciple"],
                  desc="the Roaring Falls method of Aldori swordplay")
        out = sanitize_entry(e)
        assert out["prerequisites"] == ["Aldori Dueling Disciple"]
        assert "Aldori" not in out["description"]

    def test_aldori_dueling_sword_articolo(self):
        assert sanitize_text("wielding an Aldori dueling sword", description=True) == \
            "wielding a dueling sword"

    def test_hellknight_con_articolo(self):
        assert sanitize_text("your status as a Hellknight", description=True) == \
            "your status as a knight of a strict order"

    def test_nex(self):
        assert sanitize_text("the Arclords of Nex", description=True) == \
            "the Arclords of a mage-ruled realm"

    def test_worldwound_con_articolo(self):
        assert sanitize_text("such as the Worldwound or the Abyss", description=True) == \
            "such as a demon-blighted land or the Abyss"


class TestCampiTecniciIntoccati:
    def test_campi_tecnici_non_sanitizzati(self):
        e = entry(
            "Scholar",
            desc="schools of the Inner Sea",
            refs=["Archives of Nethys: Scholar"],
            source="Inner Sea World Guide",
            source_id="inner_sea_world_guide:scholar",
            reference_urls=["https://aonprd.com/FeatDisplay.aspx?ItemName=Scholar"],
            _license="OGL-1.0a",
        )
        out = sanitize_entry(e)
        assert out["source"] == "Inner Sea World Guide"
        assert out["source_id"] == "inner_sea_world_guide:scholar"
        assert out["reference_urls"] == ["https://aonprd.com/FeatDisplay.aspx?ItemName=Scholar"]
        assert out["_license"] == "OGL-1.0a"
        assert out["description"] == "schools of the inner sea region"


class TestIdempotenzaEntry:
    def test_sanitize_entry_idempotente(self):
        e = entry(
            "Scholar",
            prereq=["worshiper of Calistria"],
            desc="throughout the Inner Sea region, from Absalom to Varisia",
            refs=["Archives of Nethys: Scholar"],
        )
        once = sanitize_entry(e)
        assert sanitize_entry(once) == once


class TestMainRepoWide:
    def test_main_non_applica_description_only(self, tmp_path, monkeypatch):
        # Fix quality review 2026-07-19: main() (run repo-wide su tutti i
        # cataloghi OGL) applica SOLO le sostituzioni base REPLACEMENTS; le
        # regole description-only (Aldori, ...) restano ad uso chirurgico
        # via apply_pi_feats_policy.
        catalog = {
            "_license": "OGL-1.0a",
            "_source": "test",
            "entries": [{
                "name": "Aldori Style",
                "description": "tradizione di spada Aldori nelle terre della Inner Sea",
                "prerequisites": [],
            }],
        }
        ogl = tmp_path / "ogl"
        ogl.mkdir()
        (ogl / "feats.json").write_text(
            json.dumps(catalog, ensure_ascii=False), encoding="utf-8")
        monkeypatch.setattr(sanitize_mod, "OGL_DIR", ogl)
        assert sanitize_mod.main() == 0
        out = json.loads((ogl / "feats.json").read_text(encoding="utf-8"))
        desc = out["entries"][0]["description"]
        # Regola base applicata repo-wide (Inner Sea -> the inner sea region)...
        assert "the inner sea region" in desc
        # ...ma il termine description-only NON e' stato toccato.
        assert "Aldori" in desc
        # Il nome non e' mai sanitizzato.
        assert out["entries"][0]["name"] == "Aldori Style"
