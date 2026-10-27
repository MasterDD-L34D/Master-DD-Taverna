#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Genera `class-features-pool.json` (slice D3-b) nel repo sibling pathmaster-dd.

Le feature dei POOL di scelta (rage power, rogue talent, hex, revelation,
discovery, deed, mercy, ki power, ninja/slayer/social/vigilante talent,
magus arcana, mystery, bloodline, order) diventano entry reali del catalogo
class-features del motore v2 — non piu' solo slot generici.

Fonti e disciplina:
  - NOMI e APPARTENENZA POOL: Taverna `data/reference/ogl/talents.json`
    (curato). La membership NON si deriva mai dai type PCGen (rumorosi).
  - MECCANICHE: `pcgen-class-abilities.json` (prerequisiti grezzi PRE*, per la
    legality RequiredSpecial) e `pcgen-class-progression.json` (grant per
    livello), entrambi importati in D3-a nel repo pathmaster-dd.
  - NESSUNA description: Taverna/PB/Paizo sono solo riferimento. Le
    description curate si scrivono a mano in pathmaster-dd
    (`class-features-pool-curated.json`). Qui non esce testo di regole.

Match Taverna -> PCGen (regole anti-falso-positivo, come PB-2):
  - nome NORMALIZZATO uguale (niente parentetici/due-punti, casefold) E key
    PCGen col prefisso del pool giusto ("Rage Power ~", "Witch Hex ~", ...);
  - revelation/bloodline: la categoria Taverna (mistero/bloodline) deve
    coincidere col qualifier della key PCGen ("Bone Mystery ~" ~ "bones"),
    altrimenti omonimi di misteri diversi sarebbero falsi match;
  - zero candidati -> "absent" (Ultimate Intrigue non e' nei dataset
    importati: vigilante/social talent restano scoperti, dichiarato);
  - piu' candidati -> "ambiguous": dichiarato, mai scelta arbitraria.

Livello minimo (precedenza dichiarata, come D3-a):
  1. `mechanics.level` Taverna (curato)             -> "taverna";
  2. grant nella progressione PCGen per la classe    -> "pcgen-grant";
  3. gate grezzo: PREVARGTEQ su var di pool-note /
     PRECLASS non negato sulla classe dell'entry     -> "pcgen-gate"
     (minimo se multipli, stessa regola di D3-a);
  4. altrimenti assente (mai inventato).

Uso:
  python tools/build_class_feature_pools.py [--out-dir PATH]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TALENTS_PATH = REPO_ROOT / "data" / "reference" / "ogl" / "talents.json"
PCGEN_DATA_DIR = (
    REPO_ROOT.parent / "pathmaster-dd" / "packages" / "rules-engine-v2" / "src" / "data"
)
DEFAULT_OUT_DIR = PCGEN_DATA_DIR

# Var PCGen "livello del pool" che sappiamo leggere come livello di classe.
# Mappa dichiarata (INTERPRETATIONS.md di rules-engine-v2): la var e' il
# livello della classe che concede il pool.
POOL_LEVEL_VARS = {
    "RagePowersLVL": "Barbarian",
    "RagePowersPrereqLVL": "Barbarian",
    "RogueTalentLVL": "Rogue",
    "RogueLVL": "Rogue",
    "MercyLVL": "Paladin",
    "MHMercyLVL": "Paladin",
    "SlayerTalentLVL": "Slayer",
    "NinjaTrickLVL": "Ninja",
    "WitchHexAbilityLVL": "Witch",
    "ArcanaQualifyLVL": "Magus",
}

# Classe Taverna -> classe nel dato PCGen/progressione.
CLASS_TO_PCGEN = {"Monk (Unchained)": "Monk"}


def norm(text: str) -> str:
    """Normalizza un nome per il match (casefold, solo alfanumerico).

    I qualifier tra parentesi diventano PAROLE, non vengono scartati:
    "Beast Totem (Lesser)" -> "beast totem lesser", come la forma Taverna
    "Beast Totem, Lesser". Scartarli fonderebbe il totem base col Lesser/
    Greater (falso match) e lascerebbe il Lesser senza candidato pulito.
    """
    text = text.split(":")[0]
    text = re.sub(r"[()]", " ", text)
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def entry_id(source_id: str) -> str:
    # "talent:rage_power_animal_fury" -> "pool-rage-power-animal-fury"
    tail = source_id.split(":", 1)[1] if ":" in source_id else source_id
    return "pool-" + slug(tail.replace("_", "-"))


def pool_key_predicates(pool: str):
    """Predicato sulla KEY PCGen per il pool Taverna (prefix matching)."""
    prefixes = {
        "rage power": ("Rage Power ~",),
        "rogue talent": ("Rogue Talent ~",),
        "advanced rogue talent": ("Rogue Talent ~",),
        "discovery": ("Discovery ~",),
        "grand discovery": ("Discovery ~",),
        "hex": ("Witch Hex ~",),
        "major hex": ("Witch Major Hex ~",),
        "grand hex": ("Witch Grand Hex ~",),
        "mercy": ("Mercy ~",),
        "deed": ("Deed ~", "Swashbuckler ~"),
        "ki power": ("Ki Power ~",),
        "ninja trick": ("Ninja Trick ~",),
        "advanced ninja trick": ("Ninja Trick ~",),
        "slayer talent": ("Slayer Talent ~",),
        "advanced slayer talent": ("Slayer Talent ~",),
        "social talent": ("Social Talent ~",),
        "vigilante talent": ("Vigilante Talent ~",),
        "magus arcana": ("Magus Arcana ~",),
    }.get(pool)
    if prefixes is not None:
        return lambda key: key.startswith(prefixes)
    if pool == "revelation":
        # "<Mystery> Mystery ~ <Name>" (il qualifier finisce in "Mystery")
        return lambda key: " ~ " in key and key.split(" ~ ")[0].endswith("Mystery")
    if pool == "mystery":
        # container: "Oracle's Mystery" e' l'unica nuda vista; i contenitori
        # per mistero non hanno key proprie nel dataset -> quasi sempre absent
        return lambda key: "~" not in key and "Mystery" in key
    if pool == "bloodline":
        return lambda key: key.startswith("Sorcerer Bloodline ~")
    if pool == "order":
        # il container dell'ordine: key nuda "Order of the Lion"
        return lambda key: "~" not in key and key.startswith("Order")
    return lambda key: False


def qualifier_matches_category(category: str, pcgen_key: str) -> bool:
    """Revelation: la categoria Taverna ("bones") col qualifier PCGen ("Bone Mystery ~").

    Uguaglianza o prefisso in entrambi i versi dopo la normalizzazione
    ("bone" vs "bones"): deterministico e dichiarato, mai fuzzy oltre.
    """
    if " ~ " not in pcgen_key:
        return False
    qualifier = pcgen_key.split(" ~ ")[0]
    qual = norm(re.sub(r"\bMystery\b", "", qualifier))
    cat = norm(category)
    return bool(cat) and (qual == cat or qual.startswith(cat) or cat.startswith(qual))


def find_pcgen_match(
    talent: dict, pcgen_entries: list[dict]
) -> tuple[str, dict | None]:
    """Ritorna ("matched"|"ambiguous"|"absent", entry PCGen o None)."""
    mech = talent.get("mechanics", {})
    pool = mech.get("pool", "")
    name = norm(talent["name"])
    category = mech.get("category")
    key_ok = pool_key_predicates(pool)
    # Il nome semplice PCGen non e' affidabile: per alcuni pool (hex,
    # bloodline) e' la key intera ("Witch Hex ~ Blight", "Aberrant
    # Bloodline"). Il riferimento stabile e' la CODA della key dopo "~ ".
    candidates = [
        e
        for e in pcgen_entries
        if key_ok(e.get("key", ""))
        and name in (norm(e.get("name", "")), norm(e.get("key", "").split(" ~ ")[-1]))
    ]
    if pool == "order":
        # il nome Taverna ("Order of Vengeance") e' la key nuda PCGen
        candidates = [
            e
            for e in pcgen_entries
            if norm(e.get("key", "")) == name and key_ok(e.get("key", ""))
        ]
    if not candidates:
        return "absent", None
    if category:
        preferred = [
            e for e in candidates if qualifier_matches_category(category, e["key"])
        ]
        if len(preferred) == 1:
            return "matched", preferred[0]
        if len(preferred) > 1:
            return "ambiguous", None
    if len(candidates) == 1:
        return "matched", candidates[0]
    # senza categoria disambiguante: stesso nome su piu' key -> mai a tentativi
    keys = {e["key"] for e in candidates}
    if len(keys) == 1:
        return "matched", candidates[0]
    return "ambiguous", None


def gate_min_level(prerequisites: list[dict], entry_class: str) -> int | None:
    """Livello dai gate grezzi (stessa regola di D3-a: minimo se multipli).

    Legge PREVARGTEQ su var di pool note e PRECLASS non negato sulla classe
    dell'entry, ovunque nell'albero. I gate restano comunque grezzi in
    `prerequisites` per la legality: qui e' solo il min-level informativo.
    """
    values: list[int] = []

    def walk(node: dict) -> None:
        tag = node.get("tag", "")
        args = node.get("args", [])
        if tag == "PREVARGTEQ" and args and args[0] in POOL_LEVEL_VARS:
            try:
                values.append(int(args[1]))
            except (IndexError, ValueError):
                pass
        if tag == "PRECLASS" and args:
            items = [a for a in args[1:] if "=" in a]
            for a in items:
                cls, _, lvl = a.rpartition("=")
                if cls.strip().lower() == entry_class.lower():
                    try:
                        values.append(int(lvl))
                    except ValueError:
                        pass
        for child in node.get("of", []):
            walk(child)

    for n in prerequisites or []:
        walk(n)
    return min(values) if values else None


def grant_min_level(pcgen_key: str, entry_class: str, progression: dict) -> int | None:
    """Il livello del primo grant della feature nella progressione PCGen."""
    pcgen_class = CLASS_TO_PCGEN.get(entry_class, entry_class)
    for cls_entry in progression.get("entries", []):
        if cls_entry.get("class", "").lower() != pcgen_class.lower():
            continue
        levels = [
            g["level"]
            for g in cls_entry.get("grants", [])
            if g.get("kind") == "ability" and pcgen_key in (g.get("names") or [])
        ]
        if levels:
            return min(levels)
    return None


def build(talents_path: Path, pcgen_dir: Path) -> dict:
    talents = json.loads(talents_path.read_text(encoding="utf-8"))["entries"]
    pcgen_abilities = json.loads(
        (pcgen_dir / "pcgen-class-abilities.json").read_text(encoding="utf-8")
    )["entries"]
    progression = json.loads(
        (pcgen_dir / "pcgen-class-progression.json").read_text(encoding="utf-8")
    )

    entries: list[dict] = []
    coverage = {
        "pcgen_matched": 0,
        "pcgen_ambiguous": 0,
        "pcgen_unmatched": 0,
        "min_level": {"taverna": 0, "pcgen-grant": 0, "pcgen-gate": 0, "none": 0},
        "pools": {},
    }

    for t in talents:
        mech = t.get("mechanics", {})
        pool = mech.get("pool", "")
        cls = mech.get("class", "")
        status, pcgen = find_pcgen_match(t, pcgen_abilities)

        min_level = None
        min_level_source = None
        if isinstance(mech.get("level"), int):
            min_level = mech["level"]
            min_level_source = "taverna"
        elif pcgen is not None:
            granted = grant_min_level(pcgen["key"], cls, progression)
            gated = gate_min_level(
                pcgen.get("prerequisites", []), CLASS_TO_PCGEN.get(cls, cls)
            )
            candidates = [
                (s, v)
                for s, v in (("pcgen-grant", granted), ("pcgen-gate", gated))
                if v is not None
            ]
            if candidates:
                # a parita' di presenza: il grant (concessione) vale piu' del
                # gate (requisito); fra due valori il MINIMO (regola D3-a)
                min_level_source = candidates[0][0]
                min_level = min(v for _, v in candidates)

        coverage[f"pcgen_{status if status != 'absent' else 'unmatched'}"] += 1
        coverage["min_level"][min_level_source or "none"] += 1
        coverage["pools"][pool] = coverage["pools"].get(pool, 0) + 1

        entry = {
            "id": entry_id(t["source_id"]),
            "name": t["name"],
            "class": cls,
            "pool": pool,
            "kind": mech.get("kind"),
            "category": mech.get("category"),
            "source": t.get("source"),
            "min_level": min_level,
            "min_level_source": min_level_source,
            "pcgen_match": status,
            "pcgen_key": pcgen["key"] if pcgen is not None else None,
            "prereqs_known": pcgen is not None,
            "prerequisites": (
                pcgen.get("prerequisites", []) if pcgen is not None else []
            ),
        }
        entries.append(entry)

    ids = [e["id"] for e in entries]
    if len(ids) != len(set(ids)):
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        raise SystemExit(f"id duplicati nel catalogo pool: {dupes}")

    return {
        "_provenance": {
            "sources": [
                "Master-DD-Taverna data/reference/ogl/talents.json (nomi e appartenenza pool, curato OGL)",
                "pathmaster-dd packages/rules-engine-v2/src/data/pcgen-class-abilities.json (prerequisiti grezzi, D3-a)",
                "pathmaster-dd packages/rules-engine-v2/src/data/pcgen-class-progression.json (grant per livello, D3-a)",
            ],
            "generated_by": "Master-DD-Taverna/tools/build_class_feature_pools.py",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "license": "OGL 1.0a (Open Game Content). Solo meccaniche e nomi.",
            "desc_policy": "NESSUNA description esportata: il testo di regole (Taverna/PB/Paizo) e' solo riferimento; le description curate del catalogo sono scritte a mano in pathmaster-dd (class-features-pool-curated.json).",
        },
        "_coverage": {"entries": len(entries), **coverage},
        "entries": entries,
    }


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--talents", default=str(TALENTS_PATH))
    ap.add_argument("--pcgen-dir", default=str(PCGEN_DATA_DIR))
    ap.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    args = ap.parse_args(argv)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    data = build(Path(args.talents), Path(args.pcgen_dir))
    out_path = out_dir / "class-features-pool.json"
    out_path.write_text(
        json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    cov = data["_coverage"]
    print(f"entry pool: {cov['entries']}")
    print(
        f"pcgen: matched={cov['pcgen_matched']} "
        f"ambiguous={cov['pcgen_ambiguous']} unmatched={cov['pcgen_unmatched']}"
    )
    print(f"min_level: {cov['min_level']}")
    print(f"scritto {out_path}")


if __name__ == "__main__":
    sys.exit(main())
