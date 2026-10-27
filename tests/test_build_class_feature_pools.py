# -*- coding: utf-8 -*-
"""Test per tools/build_class_feature_pools.py (slice D3-b).

Il tool genera `class-features-pool.json` nel repo sibling pathmaster-dd:
le feature dei POOL di scelta (rage power, rogue talent, hex, revelation,
discovery, deed, mercy, ki power, ninja/slayer/social/vigilante talent,
magus arcana, mystery, bloodline, order) come entry reali del catalogo.

Fonti:
  - appartenenza pool/nomi: Taverna data/reference/ogl/talents.json (curato);
  - meccaniche: prerequisiti grezzi + chiave PCGen dai JSON PCGen gia'
    importati (D3-a, pathmaster-dd/src/data).

Disciplina legale (garantita qui, verificata dal gate legal_filter sui
cataloghi Taverna): NESSUNA description esportata — Taverna/PB sono solo
riferimento, le description del catalogo si scrivono da noi (curated,
file separato in pathmaster-dd).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools import build_class_feature_pools as pools

REPO = Path(__file__).resolve().parents[1]
TALENTS = REPO / "data" / "reference" / "ogl" / "talents.json"
PCGEN_DIR = (
    REPO.parent / "pathmaster-dd" / "packages" / "rules-engine-v2" / "src" / "data"
)


@pytest.fixture(scope="module")
def generated(tmp_path_factory):
    out_dir = tmp_path_factory.mktemp("pool-out")
    pools.main(["--out-dir", str(out_dir)])
    return json.loads(
        (out_dir / "class-features-pool.json").read_text(encoding="utf-8")
    )


@pytest.fixture(scope="module")
def entries(generated):
    return generated["entries"]


def by_name(entries, name, pool=None):
    out = [
        e
        for e in entries
        if e["name"].lower() == name.lower() and (pool is None or e["pool"] == pool)
    ]
    return out


def test_ogni_entry_taverna_diventa_una_entry_pool(entries):
    talents = json.loads(TALENTS.read_text(encoding="utf-8"))["entries"]
    assert len(entries) == len(talents) == 1559


def test_id_unici_e_canonici(entries):
    ids = [e["id"] for e in entries]
    assert len(ids) == len(set(ids))
    for i in ids:
        assert i.startswith("pool-")
        assert i == i.lower()
        assert " " not in i and "_" not in i


def test_nessuna_description_esportata(generated, entries):
    # Mai testo di regole nei cataloghi committati: le description curate
    # vivono in un file separato scritto a mano in pathmaster-dd.
    for e in entries:
        assert "description" not in e, e["id"]


def test_campi_obbligatori(entries):
    for e in entries:
        for field in ("id", "name", "class", "pool", "prereqs_known"):
            assert field in e, (e.get("id"), field)
        assert e["prereqs_known"] is True or e["prereqs_known"] is False
        if e["prereqs_known"]:
            assert isinstance(e["prerequisites"], list)
            assert e["pcgen_key"]
        else:
            # nessun dato PCGen: dichiarato, mai inventato
            assert e["pcgen_key"] is None
            assert e["prerequisites"] == []


def test_spot_rage_power_senza_prerequisiti(entries):
    (animal_fury,) = by_name(entries, "Animal Fury", "rage power")
    assert animal_fury["class"] == "Barbarian"
    assert animal_fury["pcgen_key"] == "Rage Power ~ Animal Fury"
    assert animal_fury["prereqs_known"] is True
    assert animal_fury["prerequisites"] == []
    assert animal_fury["min_level"] is None


def test_spot_requiredspecial_catena_feature(entries):
    # Inspire Ferocity richiede il rage power Reckless Abandon (PREABILITY,
    # categoria Special Ability): la catena RequiredSpecial di D3-b.
    (inspire,) = by_name(entries, "Inspire Ferocity", "rage power")
    assert inspire["prereqs_known"] is True
    tags = [n["tag"] for n in inspire["prerequisites"]]
    assert "PREABILITY" in tags
    raw = json.dumps(inspire["prerequisites"])
    assert "Rage Power ~ Reckless Abandon" in raw


def test_spot_min_level_da_gate_pcgen(entries):
    # Clear Mind: PREVARGTEQ RagePowersPrereqLVL,8 -> min_level 8 dichiarato.
    (clear_mind,) = by_name(entries, "Clear Mind", "rage power")
    assert clear_mind["min_level"] == 8
    assert clear_mind["min_level_source"] == "pcgen-gate"


def test_spot_min_level_curato_taverna(entries):
    # Le mercy Taverna portano il livello curato (Fatigued: paladino 3).
    (fatigued,) = by_name(entries, "Fatigued", "mercy")
    assert fatigued["min_level"] == 3
    assert fatigued["min_level_source"] == "taverna"


def test_spot_revelation_disambiguata_per_mistero(entries):
    # "Spirit Walk" esiste in piu' misteri: il match PCGen usa la categoria
    # Taverna (mistero) — mai una scelta arbitraria.
    spirit_walks = by_name(entries, "Spirit Walk", "revelation")
    assert len(spirit_walks) == 3
    bones = [e for e in spirit_walks if e.get("category") == "bones"]
    assert len(bones) == 1
    assert bones[0]["pcgen_key"] == "Bone Mystery ~ Spirit Walk"
    assert bones[0]["prereqs_known"] is True


def test_copertura_dichiarata(generated):
    cov = generated["_coverage"]
    total = len(generated["entries"])
    assert (
        cov["pcgen_matched"] + cov["pcgen_ambiguous"] + cov["pcgen_unmatched"] == total
    )
    # i pool del corpus devono essere coperti dal dato PCGen nella misura
    # MISURATA e dichiarata (i dataset importati sono la linea core
    # CR/APG/ACG/ARG/UM/UC/UE/OA + Fase A 2026-08-08 UI/UW/HA/PU/AG: le
    # feature da altri manuali restano scoperte, non inventate). Soglie sui
    # valori osservati, col margine giusto perche' un miglioramento del
    # match non rompa il test.
    by_pool = {}
    for e in generated["entries"]:
        if e["pool"] in ("rage power", "rogue talent", "revelation"):
            by_pool.setdefault(e["pool"], [0, 0])
            by_pool[e["pool"]][0] += 1
            by_pool[e["pool"]][1] += 1 if e["prereqs_known"] else 0
    assert by_pool["rage power"][1] / by_pool["rage power"][0] > 0.55
    assert by_pool["rogue talent"][1] / by_pool["rogue talent"][0] > 0.35
    assert by_pool["revelation"][1] / by_pool["revelation"][0] > 0.45
    # vigilante/social: Fase A (2026-08-08) — Ultimate Intrigue e' ora nei
    # dataset PCGen importati: i pool del Vigilante hanno la meccanica
    # (matched 699 -> 825, unmatched 853 -> 727 su tutto il pool).
    vigilante = [e for e in generated["entries"] if e["class"] == "Vigilante"]
    known = sum(1 for e in vigilante if e["prereqs_known"])
    assert vigilante and known > 60


def test_provenance_dichiarata(generated):
    prov = generated["_provenance"]
    assert "talents.json" in prov["sources"][0] or "Taverna" in prov["sources"][0]
    assert "DESC" in prov["desc_policy"] or "description" in prov["desc_policy"]
