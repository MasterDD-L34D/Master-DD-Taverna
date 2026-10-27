"""Prerequisiti RAG per la campagna Valdombra (CAM-04).

Gli incontri E1-E4 (campaigns/valdombra/02-avventura) usano 3 creature SRD:
se il dataset locale perde una di queste, il prereq campagna deve saltare
in modo VISIBILE, non ritrovarsi al tavolo senza statblock.
"""

import json
from pathlib import Path

BUILDS = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "reference"
    / "pi_local_only"
    / "monsters_local.json"
)


def _entries():
    data = json.loads(BUILDS.read_text(encoding="utf-8"))
    return data.get("entries", data if isinstance(data, list) else [])


def test_srd_creatures_for_valdombra_e1_e4_presenti_con_meccaniche():
    entries = _entries()
    by_name = {e.get("name", "").lower(): e for e in entries}
    for want in ("wolf", "dog", "spider, giant crab spider"):
        assert want in by_name, f"creatura SRD mancante dal dataset locale: {want}"
        mech = by_name[want].get("mechanics") or {}
        assert mech.get("ac") and mech.get("hp"), f"meccaniche incomplete per {want}"
