"""Test per tools/build_spell_sources.py — riconciliazione spell a 3 fonti.

Slice D5 (piano 2026-08-02): indice per nome canonico -> {taverna?, pcgen?,
pb?} con i livelli per classe di OGNI fonte, MAI fusi (nessun merge
silenzioso). Policy (scritta in docs/superpowers/pcgen-import.md): ampiezza
Taverna, struttura PCGen, copertura PB; la fonte OPERATIVA del motore resta
`spellLevelFor` Taverna, INVARIATA da questa slice.

Fonti:
- Taverna `data/reference/ogl/spells.json` (2.820 entry OGL; livelli da
  mechanics.spell_level, chiavi combinate splittate — come il loader TS).
- PCGen `pathmaster-dd/.../pcgen-spells.json` (1.740 entry, 1.720 nomi
  unici: 20 nomi compaiono in 2 libri con classi COMPLEMENTARI — merge a
  unione di classi dichiarato, conflitti segnalati: oggi zero).
- PB `pathmaster-dd/.../pathbuilder-spells.json` (2.922 entry, livelli da
  spellLevelsDisplay — import D5).

Normalizzazione nomi ESPLICITA (dichiarata nel JSON):
- NFKD + strip combining + casefold + apostrofo tipografico -> dritto +
  collasso spazi;
- forma invertita "Base, Qualifier" <-> "Base (Qualifier)" per i
  qualificatori DICHIARATI (greater, lesser, mass, communal, improved,
  supreme, giant, greater communal): Taverna/PB usano la forma con virgola
  (es. "Dispel Magic, Greater"), PCGen quella con parentesi ("Dispel Magic
  (Greater)"). Le parentesi PCGen NON di qualificatore ("(Chaos Only)",
  "(Acid)", "(1)") sono VARIANTI separate: mai fuse.
Alias di classe dichiarati: magusum -> magus, summoner (unchained) ->
unchained summoner.

Divergenze di livello per classe (cuore D5): dove >=2 fonti coprono la
stessa spell+classe con livelli diversi, la divergenza e' registrata con
CLASSIFICAZIONE (pcgen-outlier / taverna-pb-divergence / raw-homonym /
declared-unresolved) e VERDETTO da tabella dichiarata (verifiche AoN
2026-08-07) — MAI risolta a tentativi: il dato resta com'e', la fonte
operativa non cambia.
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools import build_spell_sources as bss

# ---------------------------------------------------------------------------
# Fixture: mini-fonti nella forma reale dei tre JSON.
# ---------------------------------------------------------------------------

TAVERNA = {
    "_license": "OGL",
    "entries": [
        {
            "name": "Acid Arrow",
            "source": "Pathfinder SRD",
            "tags": [],
            "mechanics": {
                "school": "conjuration",
                "spell_level": {"sorcerer/wizard": 2, "magus": 2},
            },
        },
        # forma invertita Taverna + chiave combinata
        {
            "name": "Dispel Magic, Greater",
            "source": "Pathfinder SRD",
            "tags": [],
            "mechanics": {
                "school": "abjuration",
                "spell_level": {"cleric/oracle": 6, "sorcerer/wizard": 6},
            },
        },
        # divergenza tre fonti: Taverna e PB concordi, PCGen difforme
        {
            "name": "Commune with Nature",
            "source": "Pathfinder SRD",
            "tags": [],
            "mechanics": {
                "school": "divination",
                "spell_level": {"druid": 5, "ranger": 4},
            },
        },
        # divergenza Taverna<->PB (PCGen assente)
        {
            "name": "Soul Transfer",
            "source": "Book of the Damned",
            "tags": [],
            "mechanics": {
                "school": "necromancy",
                "spell_level": {"sorcerer/wizard": 7, "witch": 7},
            },
        },
        # solo Taverna
        {
            "name": "Taverna Only Spell",
            "source": "X",
            "tags": [],
            "mechanics": {"school": "abjuration", "spell_level": {"bard": 1}},
        },
        # artefatto magusum (alias dichiarato)
        {
            "name": "Storm of Blades",
            "source": "X",
            "tags": [],
            "mechanics": {
                "school": "conjuration",
                "spell_level": {"magusum": 2, "sorcerer/wizard": 2},
            },
        },
    ],
}

PCGEN = {
    "_provenance": {"source": "PCGen"},
    "entries": [
        {
            "name": "Acid Arrow",
            "source_book": "CR",
            "classes": {"Sorcerer": 2, "Wizard": 2},
            "school": "Conjuration",
        },
        # forma PCGen con parentesi
        {
            "name": "Dispel Magic (Greater)",
            "source_book": "CR",
            "classes": {"Cleric": 6, "Sorcerer": 6, "Wizard": 6},
            "school": "Abjuration",
        },
        {
            "name": "Commune with Nature",
            "source_book": "CR",
            "classes": {"Druid": 4, "Ranger": 4},
            "school": "Divination",
        },
        # duplicato interno PCGen su due libri: classi complementari
        {
            "name": "Summon Monster I",
            "source_book": "CR",
            "classes": {"Bard": 1, "Cleric": 1},
            "school": "Conjuration",
        },
        {
            "name": "Summon Monster I",
            "source_book": "APG",
            "classes": {"Witch": 1, "Antipaladin": 1},
            "school": "Conjuration",
        },
        # variante PCGen-only: NON una forma invertita, mai fusa
        {
            "name": "Align Weapon (Chaos Only)",
            "source_book": "CR",
            "classes": {"Cleric": 2},
            "school": "Transmutation",
        },
    ],
}

PB = {
    "_provenance": {"source": "Pathbuilder"},
    "spells": [
        {
            "name": "Acid Arrow",
            "source": "CRB",
            "school": "Conjuration",
            "spellLevels": {"sorcerer": 2, "wizard": 2, "magus": 2},
        },
        {
            "name": "Dispel Magic, Greater",
            "source": "CRB",
            "school": "Abjuration",
            "spellLevels": {"cleric": 6, "oracle": 6, "sorcerer": 6, "wizard": 6},
        },
        {
            "name": "Commune with Nature",
            "source": "CRB",
            "school": "Divination",
            "spellLevels": {"druid": 5, "ranger": 4},
        },
        {
            "name": "Soul Transfer",
            "source": "BotD",
            "school": "Necromancy",
            "spellLevels": {"sorcerer": 8, "wizard": 8, "witch": 8},
        },
        # solo PB
        {
            "name": "Pb Only Spell",
            "source": "X",
            "school": "Evocation",
            "spellLevels": {"arcanist": 2},
        },
    ],
}


@pytest.fixture()
def sources(tmp_path: Path) -> dict:
    tav = tmp_path / "taverna.json"
    pcg = tmp_path / "pcgen.json"
    pb = tmp_path / "pb.json"
    tav.write_text(json.dumps(TAVERNA), encoding="utf-8")
    pcg.write_text(json.dumps(PCGEN), encoding="utf-8")
    pb.write_text(json.dumps(PB), encoding="utf-8")
    return {"taverna": tav, "pcgen": pcg, "pb": pb}


# ---------------------------------------------------------------------------
# Normalizzazione nomi
# ---------------------------------------------------------------------------


def test_norm_base():
    assert bss.norm_name("  Acid   Arrow ") == "acid arrow"
    assert bss.norm_name("Fool\u2019s Gold") == "fool's gold"


def test_canon_forma_invertita():
    # Taverna/PB: "Dispel Magic, Greater"; PCGen: "Dispel Magic (Greater)"
    assert bss.canon_key("Dispel Magic, Greater") == "dispel magic (greater)"
    assert bss.canon_key("Dispel Magic (Greater)") == "dispel magic (greater)"
    assert bss.canon_key("Air Walk, Communal") == "air walk (communal)"


def test_canon_solo_qualificatori_dichiarati():
    # virgola NON da qualificatore dichiarato: nessuna inversione
    assert bss.canon_key("Foo, Bananas") == "foo, bananas"
    # parentesi NON da qualificatore: resta una variante separata
    assert bss.canon_key("Align Weapon (Chaos Only)") == "align weapon (chaos only)"


def test_qualifiers_dichiarati():
    assert set(bss.QUALIFIERS) == {
        "greater",
        "lesser",
        "mass",
        "communal",
        "improved",
        "supreme",
        "giant",
        "greater communal",
    }


def test_class_id_alias():
    assert bss.class_id("magusUM") == "magus"
    assert bss.class_id("Summoner (Unchained)") == "unchained summoner"
    assert bss.class_id("Sorcerer") == "sorcerer"


# ---------------------------------------------------------------------------
# Loaders per fonte
# ---------------------------------------------------------------------------


def test_load_taverna_chiavi_combinate_splittate(sources):
    tav = bss.load_taverna(sources["taverna"])
    assert tav["acid arrow"]["levels"] == {"sorcerer": 2, "wizard": 2, "magus": 2}
    # chiave canonica dalla forma invertita
    assert "dispel magic (greater)" in tav
    # alias magusum applicato
    assert tav["storm of blades"]["levels"]["magus"] == 2


def test_load_pcgen_duplicati_merged_unione_classi(sources):
    pcg, dup_report = bss.load_pcgen(sources["pcgen"])
    assert pcg["summon monster i"]["levels"] == {
        "bard": 1,
        "cleric": 1,
        "witch": 1,
        "antipaladin": 1,
    }
    assert dup_report["mergedNames"] == ["summon monster i"]
    assert dup_report["conflicts"] == []


def test_load_pb(sources):
    pb = bss.load_pb(sources["pb"])
    assert pb["dispel magic (greater)"]["levels"]["oracle"] == 6


# ---------------------------------------------------------------------------
# Indice riconciliato: conteggi, nessun merge silenzioso
# ---------------------------------------------------------------------------


def test_build_index_provenance_per_fonte(sources):
    index = bss.build(sources["taverna"], sources["pcgen"], sources["pb"])
    entry = index["spells"]["acid arrow"]
    assert set(entry["sources"]) == {"taverna", "pcgen", "pb"}
    # i livelli di ogni fonte restano SEPARATI: mai un merge
    assert entry["sources"]["taverna"]["levels"]["magus"] == 2
    assert "magus" not in entry["sources"]["pcgen"]["levels"]
    # displayName dalla prima fonte per priorita' dichiarata
    assert entry["displayName"] == "Acid Arrow"


def test_build_conteggi(sources):
    index = bss.build(sources["taverna"], sources["pcgen"], sources["pb"])
    counts = index["counts"]
    assert counts["taverna"] == 6
    assert counts["pcgen"] == 5  # 6 entry, 1 duplicato fuso
    assert counts["pb"] == 5
    union = counts["union"]
    assert union == len(index["spells"])
    # align weapon (chaos only) resta una voce a parte (variante PCGen)
    assert "align weapon (chaos only)" in index["spells"]
    # acid arrow + dispel magic (greater) + commune with nature + soul transfer
    assert counts["intersection"]["tavernaPb"] == 4
    assert counts["intersection"]["allThree"] == 3
    assert counts["only"]["taverna"] == 2  # taverna only + storm of blades
    assert counts["only"]["pb"] == 1
    assert counts["only"]["pcgen"] == 2  # summon monster i + align weapon variant


# ---------------------------------------------------------------------------
# Divergenze di livello per classe: il cuore D5
# ---------------------------------------------------------------------------


def test_divergenze_tre_fonti_pcgen_outlier(sources):
    index = bss.build(sources["taverna"], sources["pcgen"], sources["pb"])
    divs = {(d["spell"], d["class"]): d for d in index["report"]["divergences"]}
    d = divs[("commune with nature", "druid")]
    assert d["levels"] == {"taverna": 5, "pcgen": 4, "pb": 5}
    assert d["classification"] == "pcgen-outlier"
    # nessuna divergenza dove le fonti concordano
    assert ("acid arrow", "sorcerer") not in divs
    # ranger: tutte e tre concordano a 4
    assert ("commune with nature", "ranger") not in divs


def test_divergenze_taverna_pb(sources):
    index = bss.build(sources["taverna"], sources["pcgen"], sources["pb"])
    divs = {(d["spell"], d["class"]): d for d in index["report"]["divergences"]}
    for cls in ("sorcerer", "wizard", "witch"):
        d = divs[("soul transfer", cls)]
        assert d["levels"] == {"taverna": 7, "pb": 8}
        assert d["classification"] == "taverna-pb-divergence"


def test_divergenze_mai_risolte_a_tentativi(sources):
    # una divergenza senza verdetto in tabella: classification declared-unresolved,
    # verdict null — il dato resta com'e'
    tav = json.loads(json.dumps(TAVERNA))
    tav["entries"].append(
        {
            "name": "Mystery Spell",
            "source": "X",
            "tags": [],
            "mechanics": {"school": "abjuration", "spell_level": {"bard": 2}},
        }
    )
    pb = json.loads(json.dumps(PB))
    pb["spells"].append(
        {
            "name": "Mystery Spell",
            "source": "X",
            "school": "Abjuration",
            "spellLevels": {"bard": 3},
        }
    )
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        tavp = Path(td) / "t.json"
        pb_p = Path(td) / "p.json"
        pcg_p = Path(td) / "c.json"
        tavp.write_text(json.dumps(tav), encoding="utf-8")
        pb_p.write_text(json.dumps(pb), encoding="utf-8")
        pcg_p.write_text(json.dumps(PCGEN), encoding="utf-8")
        index = bss.build(tavp, pcg_p, pb_p)
    d = {(x["spell"], x["class"]): x for x in index["report"]["divergences"]}[
        ("mystery spell", "bard")
    ]
    assert d["classification"] == "declared-unresolved"
    assert d["verdict"] is None
    # e la spell resta con ENTRAMBI i livelli per fonte (nessun merge)
    entry = index["spells"]["mystery spell"]
    assert entry["sources"]["taverna"]["levels"]["bard"] == 2
    assert entry["sources"]["pb"]["levels"]["bard"] == 3


def test_verdetti_dichiarati_per_divergenze_note(sources):
    index = bss.build(sources["taverna"], sources["pcgen"], sources["pb"])
    divs = {(d["spell"], d["class"]): d for d in index["report"]["divergences"]}
    v = divs[("commune with nature", "druid")]["verdict"]
    assert v is not None
    assert "aonprd.com" in v["source"]
    v2 = divs[("soul transfer", "witch")]["verdict"]
    assert v2 is not None


# ---------------------------------------------------------------------------
# Payload completo (main)
# ---------------------------------------------------------------------------


def test_main_scrive_json(sources, tmp_path):
    out_dir = tmp_path / "out"
    rc = bss.main(
        [
            "--taverna",
            str(sources["taverna"]),
            "--pcgen",
            str(sources["pcgen"]),
            "--pb",
            str(sources["pb"]),
            "--out-dir",
            str(out_dir),
        ]
    )
    assert rc == 0
    payload = json.loads((out_dir / "spell-sources.json").read_text(encoding="utf-8"))
    prov = payload["_provenance"]
    for key in ("taverna", "pcgen", "pathbuilder"):
        assert key in prov["sources"]
    assert "Taverna" in prov["operative_source"]
    # normalizzazione dichiarata nel dato
    assert payload["normalization"]["qualifiers"]
    assert payload["normalization"]["classAliases"]["magusum"] == "magus"
    # mai description: nessuna entry dell'indice porta testo descrittivo
    for entry in payload["spells"].values():
        for src in entry["sources"].values():
            assert "description" not in {k.lower() for k in src}


# ---------------------------------------------------------------------------
# Smoke sui dati REALI (skip se i JSON non ci sono)
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[1]
REAL_TAVERNA = REPO_ROOT / "data/reference/ogl/spells.json"
REAL_PCGEN = (
    REPO_ROOT.parent
    / "pathmaster-dd"
    / "packages/rules-engine-v2/src/data/pcgen-spells.json"
)
REAL_PB = (
    REPO_ROOT.parent
    / "pathmaster-dd"
    / "packages/rules-engine-v2/src/data/pathbuilder-spells.json"
)
REAL_REASON = "JSON sorgente assente (Taverna OGL o output import)"

_real_ok = REAL_TAVERNA.is_file() and REAL_PCGEN.is_file() and REAL_PB.is_file()


@pytest.mark.skipif(not _real_ok, reason=REAL_REASON)
def test_dati_reali_conteggi_e_copertura():
    index = bss.build(REAL_TAVERNA, REAL_PCGEN, REAL_PB)
    counts = index["counts"]
    assert counts["taverna"] == 2820
    assert counts["pcgen"] == 2001  # 2.023 entry (Fase A: +UI/UW/HA/AG),
    # 22 nomi in 2 libri
    assert counts["pb"] == 2922
    assert counts["union"] == 3092
    assert counts["intersection"]["tavernaPcgen"] == 1868
    assert counts["intersection"]["tavernaPb"] == 2749
    assert counts["intersection"]["pcgenPb"] == 1900
    assert counts["intersection"]["allThree"] == 1866
    # copertura aggiunta: PB porta 139 spell nuove (fuori Taverna+PCGen),
    # PCGen 99 (varianti e spell fuori catalogo Taverna)
    assert counts["only"]["pb"] == 139
    assert counts["only"]["pcgen"] == 99
    assert counts["only"]["taverna"] == 69
    # duplicati interni PCGen: 22 nomi fusi a unione di classi, 0 conflitti
    dup = index["report"]["pcgenInternalDuplicates"]
    assert len(dup["mergedNames"]) == 22
    assert dup["conflicts"] == []


@pytest.mark.skipif(not _real_ok, reason=REAL_REASON)
def test_dati_reali_divergenze_esatte_classificate():
    index = bss.build(REAL_TAVERNA, REAL_PCGEN, REAL_PB)
    divs = {(d["spell"], d["class"]): d for d in index["report"]["divergences"]}
    assert set(divs) == {
        ("commune with nature", "druid"),
        ("geas (lesser)", "bard"),
        ("nondetection", "ranger"),
        ("withdraw affliction", "spiritualist"),
        ("fool's gold", "sorcerer"),
        ("fool's gold", "wizard"),
        ("soul transfer", "sorcerer"),
        ("soul transfer", "wizard"),
        ("soul transfer", "witch"),
    }
    # le 4 tre-fonti: Taverna==PB, PCGen difforme (AoN: Taverna/PB RAW-corrette)
    for key in [
        ("commune with nature", "druid"),
        ("geas (lesser)", "bard"),
        ("nondetection", "ranger"),
        ("withdraw affliction", "spiritualist"),
    ]:
        assert divs[key]["classification"] == "pcgen-outlier"
        assert divs[key]["verdict"] is not None
    # Fool's Gold: omonimia RAW reale (spell diverse AA vs VC), non un errore
    for cls in ("sorcerer", "wizard"):
        assert divs[("fool's gold", cls)]["classification"] == "raw-homonym"
    # ogni divergenza ha un verdetto dichiarato (mai risolta a tentativi)
    for d in divs.values():
        assert d["verdict"] is not None
        assert d["verdict"]["source"]


@pytest.mark.skipif(not _real_ok, reason=REAL_REASON)
def test_dati_reali_overwhelming_presence_correzione_curata():
    """Fase A (2026-08-08): la divergenza D5 ("overwhelming presence",
    psychic: Taverna 4 vs PB 9) si e' CHIUSA con la correzione curata sul
    dato Taverna (4 -> 9, RAW AoN verificato 2026-08-07) — non e' sparita
    in silenzio: il dato porta la nota di correzione e il registro e' in
    INTERPRETATIONS.md di rules-engine-v2."""
    spells = json.loads(REAL_TAVERNA.read_text(encoding="utf-8"))["entries"]
    op = next(e for e in spells if e["name"] == "Overwhelming Presence")
    assert op["mechanics"]["spell_level"]["psychic"] == 9
    assert "CORREZIONE CURATA" in op["notes"]
    assert "slot:6" in op["tags"] and "slot:4" not in op["tags"]

    index = bss.build(REAL_TAVERNA, REAL_PCGEN, REAL_PB)
    entry = index["spells"]["overwhelming presence"]
    # dove una fonte copre lo psychic, concorda a 9: nessuna divergenza.
    # PCGen NON copre psychic per questa spell (dato UM, verificato
    # 2026-08-08): assenza di copertura, non divergenza — dichiarato.
    assert "psychic" not in entry["sources"]["pcgen"]["levels"]
    for name, src in entry["sources"].items():
        if "psychic" in src["levels"]:
            assert src["levels"]["psychic"] == 9, name
    divs = {(d["spell"], d["class"]) for d in index["report"]["divergences"]}
    assert ("overwhelming presence", "psychic") not in divs
    # il verdetto storico e' rimosso dalla tabella (la divergenza e' chiusa):
    # la correzione vive nel commento CORREZIONI CURATE del builder
    assert ("overwhelming presence", "psychic") not in bss.DIVERGENCE_VERDICTS
