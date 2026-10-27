#!/usr/bin/env python3
"""Import del dataset raw Pathbuilder 1e (APK) verso i cataloghi rules-engine-v2.

Task PB-1: parse dei 253 XML in
`data/reference/pi_local_only/pathbuilder/` (estratto da res/raw dell'APK
Pathbuilder 1e, BlueStacks dell'utente, permesso concesso 2026-08-02 —
dataset PI local-only, MAI committato) ed emissione di DUE JSON committati in
`pathmaster-dd/packages/rules-engine-v2/src/data/`:

- pathbuilder-class-features.json — feature di classe dai data_specials_*.xml,
  raggruppate per classe (chiave dal nome file) e tipo di feature:
  {name, requirements, required_specials, level_ap, description, source, ref}.
  Dato di SUPPORTO per arricchire description/alias degli slot M4 dichiarati
  in pathmaster (src/catalogs/class-features.ts): NON applicato
  automaticamente, nessun consumer TS lo legge ancora.
- pathbuilder-feats.json — talenti da data_feats.xml:
  {name, category, max_takable, prerequisites_text, requirements (strutturati
  decodificati dai campi r*), source, url, effect_method, requirement_method}.
  SENZA description (testo Paizo PI: resta nel dataset locale, disciplina OGL
  del progetto come per l'import PCGen A1). Include `pcgen_comparison`:
  confronto nomi vs pcgen-feats.json (report, NON merge cieco).

Formato requisiti strutturati feat (ricognizione 2026-08-01, vedi
docs/pathbuilder-dataset.md): `£` separa chiave/valore, `&` separa vincoli
multipli. rStat = `idx£min` con mappa 0=FOR 1=DES 2=COS 3=INT 4=SAG 5=CAR
(verificata: Dodge `1£13` = "Dex 13", Abeyance `3£13` = "Int 13");
rClassLevel = `Classe£livello` (& = alternative); rFeatsWithSpecificInfo =
`Talento£scelta`; rMagicRef 0=arcana 1=divina; rFeats/rRace/rClassFeature =
nomi (& = lista); rBAB/rCasterLevel/rCharLevel = interi.

Uso:
  python tools/import_pathbuilder_raw.py                  # scrive i 2 JSON + report
  python tools/import_pathbuilder_raw.py --report-only    # solo report a stdout
  --raw-dir PATH       (default data/reference/pi_local_only/pathbuilder)
  --out-dir PATH       (default <pathmaster sibling>/packages/rules-engine-v2/src/data)
  --pcgen-feats PATH   (default <out-dir>/pcgen-feats.json; se assente, niente confronto)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RAW_DIR = REPO_ROOT / "data/reference/pi_local_only/pathbuilder"
DEFAULT_OUT_DIR = (
    REPO_ROOT.parent / "pathmaster-dd" / "packages/rules-engine-v2/src/data"
)

STAT_INDEX = {0: "STR", 1: "DEX", 2: "CON", 3: "INT", 4: "WIS", 5: "CHA"}

# Classi riconosciute dal prefisso del nome file data_specials_<classe>_<tipo>.
# Il match e' longest-first, quindi le varianti (unchained_*, adaptive_shifter)
# precedono i nomi base. Includiamo anche le classi di prestigio/3pp che
# Pathbuilder supporta come "classe" a se' (hellknight, loremaster, ...).
CLASS_PREFIXES = sorted(
    [
        # classi base e varianti
        "unchained_barbarian",
        "unchained_monk",
        "unchained_rogue",
        "adaptive_shifter",
        "alchemist",
        "antipaladin",
        "arcanist",
        "barbarian",
        "bard",
        "bloodrager",
        "brawler",
        "cavalier",
        "cleric",
        "druid",
        "fighter",
        "gunslinger",
        "hunter",
        "inquisitor",
        "investigator",
        "kineticist",
        "kinetic",
        "magus",
        "medium",
        "mesmerist",
        "monk",
        "ninja",
        "occultist",
        "omdura",
        "oracle",
        "paladin",
        "psychic",
        "ranger",
        "rogue",
        "samurai",
        "shaman",
        "shifter",
        "skald",
        "slayer",
        "sorcerer",
        "spiritualist",
        "summoner",
        "swashbuckler",
        "vigilante",
        "warpriest",
        "witch",
        "wizard",
        # classi di prestigio / 3pp supportate da Pathbuilder
        "battle_herald",
        "brewkeeper",
        "constructed_pugilist",
        "cyphermage",
        "darechaser",
        "dawn_anchorite",
        "deep_sea_pirate",
        "divine_scion",
        "dragonscale_loyalist",
        "envoy",
        "field_agent",
        "furious_guardian",
        "guild_agent",
        "guild_poisoner",
        "havocker",
        "hellknight",
        "interrogator",
        "kinslayer",
        "lore_warden",
        "loremaster",
        "malice_binder",
        "master_chymist",
        "mutation_mind",
        "natural_alchemist",
        "noble_scion",
        "opportunist",
        "pain_taster",
        "planar_scout",
        "psychic_duelist",
        "rose_warden",
        "runeguard",
        "sanguine_angel",
        "scar_seeker",
        "season_witch",
        "stalwart_defender",
        "stargazer",
        "tattooed_mystic",
        "toxicant",
        "toxitician",
        "vampire_hunter",
        "vexing_dodger",
        "warrior_poet",
    ],
    key=len,
    reverse=True,
)

LICENSE_TEXT = (
    "Pathbuilder 1e raw data (APK da BlueStacks utente, permesso concesso "
    "2026-08-02). Meccaniche e nomi: OGL 1.0a. Description: testo Paizo "
    "(Product Identity) — per i feats MAI esportata; per le class features "
    "inclusa solo come dato di supporto agli slot M4 gia' dichiarati in "
    "pathmaster (stesso criterio di src/catalogs/class-features.ts). Il "
    "dataset grezzo completo resta in data/reference/pi_local_only/ "
    "(gitignored, mai redistribuito)."
)
DESC_POLICY = (
    "Description dei feat omessa per policy: solo meccaniche + nomi, mai "
    "testo di regole Paizo redistribuito (resta nel dataset PI local-only)."
)


# ---------------------------------------------------------------------------
# Parse XML generico
# ---------------------------------------------------------------------------


def parse_xml(text: str) -> ET.Element:
    """Radice <Root> di un dataset raw Pathbuilder."""
    return ET.fromstring(text)


def iter_rows(root: ET.Element) -> list:
    """Le righe <Row> di una radice parsata."""
    return root.findall("Row")


def _text(row: ET.Element, tag: str):
    value = row.findtext(tag)
    if value is None:
        return None
    value = value.strip()
    return value or None


# ---------------------------------------------------------------------------
# Requisiti strutturati (campi r* di data_feats.xml)
# ---------------------------------------------------------------------------


def parse_amp_list(value):
    """Lista di nomi separati da `&` (rFeats, rRace, rClassFeature)."""
    if not value:
        return []
    return [part.strip() for part in value.split("&") if part.strip()]


def parse_rstat(value) -> dict:
    """`idx£min` (& tra vincoli) -> {SIGLA: min} con mappa 0=FOR..5=CAR."""
    mins = {}
    for part in parse_amp_list(value):
        if "£" not in part:
            continue
        idx, _, raw_min = part.partition("£")
        try:
            stat = STAT_INDEX[int(idx.strip())]
            mins[stat] = int(raw_min.strip())
        except (KeyError, ValueError):
            continue
    return mins


def parse_class_level(value) -> list:
    """`Classe£livello` (& = alternative) -> [{class, level}]."""
    out = []
    for part in parse_amp_list(value):
        if "£" not in part:
            continue
        name, _, raw_level = part.partition("£")
        try:
            out.append({"class": name.strip(), "level": int(raw_level.strip())})
        except ValueError:
            continue
    return out


def parse_feat_with_info(value) -> list:
    """`Talento£scelta` (& = lista) -> [{feat, info}]."""
    out = []
    for part in parse_amp_list(value):
        if "£" not in part:
            continue
        feat, _, info = part.partition("£")
        out.append({"feat": feat.strip(), "info": info.strip()})
    return out


def parse_magic_ref(value):
    """rMagicRef: 0 = arcana, 1 = divina."""
    if value is None:
        return None
    return {"0": "arcane", "1": "divine"}.get(value.strip())


def _int_or_none(value):
    if value is None:
        return None
    try:
        return int(value.strip())
    except ValueError:
        return None


def build_requirements(row: ET.Element) -> dict:
    """Requisiti decodificati di una riga feat (tutte le chiavi sempre presenti)."""
    return {
        "ability_mins": parse_rstat(_text(row, "rStat")),
        "feats": parse_amp_list(_text(row, "rFeats")),
        "feats_with_info": parse_feat_with_info(_text(row, "rFeatsWithSpecificInfo")),
        "class_features": parse_amp_list(_text(row, "rClassFeature")),
        "class_levels": parse_class_level(_text(row, "rClassLevel")),
        "races": parse_amp_list(_text(row, "rRace")),
        "bab_min": _int_or_none(_text(row, "rBAB")),
        "caster_level_min": _int_or_none(_text(row, "rCasterLevel")),
        "char_level_min": _int_or_none(_text(row, "rCharLevel")),
        "magic_type": parse_magic_ref(_text(row, "rMagicRef")),
    }


# ---------------------------------------------------------------------------
# Entita': feats (SENZA description — policy OGL)
# ---------------------------------------------------------------------------


def feats_from_rows(rows: list) -> list:
    entries = []
    for row in rows:
        name = _text(row, "FeatName")
        if not name:
            continue
        category = _text(row, "Category") or ""
        entries.append(
            {
                "name": name,
                "category": [int(p) for p in category.split("&") if p.strip()],
                "max_takable": _int_or_none(_text(row, "MaxTakable")),
                "prerequisites_text": _text(row, "Prerequisites"),
                "requirements": build_requirements(row),
                "source": _text(row, "Source"),
                "url": _text(row, "URL"),
                "effect_method": _text(row, "EffectMethod"),
                "requirement_method": _text(row, "RequirementMethod"),
            }
        )
    return entries


# ---------------------------------------------------------------------------
# Entita': specials (class features)
# ---------------------------------------------------------------------------


def specials_from_rows(rows: list) -> list:
    features = []
    for row in rows:
        name = _text(row, "Special")
        if not name:
            continue
        required = [
            r
            for r in (_text(row, "RequiredSpecial1"), _text(row, "RequiredSpecial2"))
            if r
        ]
        features.append(
            {
                "name": name,
                "requirements": _text(row, "Requirements"),
                "required_specials": required,
                "level_ap": _int_or_none(_text(row, "LevelAP")),
                "description": _text(row, "Description"),
                "source": _text(row, "Source"),
                "ref": _text(row, "Ref"),
            }
        )
    return features


def class_key_for_specials_file(filename: str) -> tuple:
    """data_specials_<classe>_<tipo>.xml -> (classe, tipo); `_shared` se il
    file non e' riconducibile a una classe (capstones, variant_channeling...)."""
    stem = filename
    for prefix in ("data_specials_",):
        if stem.startswith(prefix):
            stem = stem[len(prefix) :]
    stem = re.sub(r"\.xml$", "", stem)
    for class_key in CLASS_PREFIXES:
        if stem == class_key:
            return class_key, "_misc"
        if stem.startswith(class_key + "_"):
            return class_key, stem[len(class_key) + 1 :]
    return "_shared", stem


def build_class_features(raw_dir) -> dict:
    """Tutti i data_specials_*.xml raggruppati per classe e tipo di feature."""
    raw_dir = Path(raw_dir)
    classes = {}
    counts = {}
    files = 0
    for path in sorted(raw_dir.glob("data_specials_*.xml")):
        files += 1
        class_key, feature_type = class_key_for_specials_file(path.name)
        rows = iter_rows(ET.parse(path).getroot())
        features = specials_from_rows(rows)
        bucket = classes.setdefault(class_key, {})
        bucket.setdefault(feature_type, []).extend(features)
        counts[class_key] = counts.get(class_key, 0) + len(features)
    return {
        "_provenance": {
            "source": (
                "Pathbuilder 1e raw data (res/raw dell'APK), " "data_specials_*.xml"
            ),
            "generated_by": "Master-DD-Taverna/tools/import_pathbuilder_raw.py",
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "license": LICENSE_TEXT,
            "usage": (
                "Dato di supporto per description/alias degli slot M4 "
                "di pathmaster (src/catalogs/class-features.ts): NON "
                "applicato automaticamente."
            ),
            "specials_files": files,
        },
        "counts": counts,
        "classes": classes,
    }


# ---------------------------------------------------------------------------
# Confronto con pcgen-feats (report, NON merge)
# ---------------------------------------------------------------------------


def _norm_name(name: str) -> str:
    return re.sub(r"\s+", " ", name).strip().casefold()


def compare_with_pcgen(pb_entries: list, pcgen_names: list) -> dict:
    """Nomi Pathbuilder nuovi vs duplicati rispetto a pcgen-feats (match
    normalizzato: casefold + spazi collassati)."""
    pcgen_norm = {_norm_name(n) for n in pcgen_names}
    duplicates = sorted(
        {e["name"] for e in pb_entries if _norm_name(e["name"]) in pcgen_norm}
    )
    new = sorted(
        {e["name"] for e in pb_entries if _norm_name(e["name"]) not in pcgen_norm}
    )
    return {
        "pathbuilder_count": len(pb_entries),
        "pcgen_count": len(pcgen_names),
        "duplicate_count": len(duplicates),
        "new_count": len(new),
        "duplicates": duplicates,
        "new_in_pathbuilder": new,
    }


def build_feats(raw_dir, pcgen_names=None) -> dict:
    raw_dir = Path(raw_dir)
    rows = iter_rows(ET.parse(raw_dir / "data_feats.xml").getroot())
    entries = feats_from_rows(rows)
    payload = {
        "_provenance": {
            "source": ("Pathbuilder 1e raw data (res/raw dell'APK), " "data_feats.xml"),
            "generated_by": "Master-DD-Taverna/tools/import_pathbuilder_raw.py",
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "license": LICENSE_TEXT,
            "desc_policy": DESC_POLICY,
            "requirement_fields_doc": "docs/pathbuilder-dataset.md",
        },
        "counts": {"feats": len(entries)},
        "entries": entries,
    }
    if pcgen_names is not None:
        payload["pcgen_comparison"] = compare_with_pcgen(entries, pcgen_names)
    return payload


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def _print_report(feats: dict, class_features: dict) -> None:
    print(f"[feats] totale: {feats['counts']['feats']} voci")
    cmp_ = feats.get("pcgen_comparison")
    if cmp_:
        print(
            f"[confronto pcgen] pathbuilder {cmp_['pathbuilder_count']} vs "
            f"pcgen {cmp_['pcgen_count']}: "
            f"{cmp_['duplicate_count']} duplicati, "
            f"{cmp_['new_count']} nomi nuovi in pathbuilder"
        )
        print(f"  esempi nuovi: {cmp_['new_in_pathbuilder'][:10]}")
    else:
        print("[confronto pcgen] SALTATO (pcgen-feats.json non trovato)")
    total = sum(class_features["counts"].values())
    files = class_features["_provenance"]["specials_files"]
    print(
        f"[class-features] {total} feature da {files} file specials, "
        f"{len(class_features['counts'])} classi/gruppi"
    )
    for class_key, n in sorted(class_features["counts"].items(), key=lambda kv: -kv[1])[
        :10
    ]:
        print(f"  {class_key}: {n}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--raw-dir", default=str(DEFAULT_RAW_DIR))
    ap.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    ap.add_argument("--pcgen-feats", default=None)
    ap.add_argument("--report-only", action="store_true")
    args = ap.parse_args(argv)

    raw_dir = Path(args.raw_dir)
    if not (raw_dir / "data_feats.xml").is_file():
        print(
            f"ERRORE: dataset Pathbuilder non trovato in {raw_dir} "
            "(pi_local_only e' local-only: vedi docs/pathbuilder-dataset.md)",
            file=sys.stderr,
        )
        return 1

    out_dir = Path(args.out_dir)
    pcgen_path = (
        Path(args.pcgen_feats) if args.pcgen_feats else out_dir / "pcgen-feats.json"
    )
    pcgen_names = None
    if pcgen_path.is_file():
        data = json.loads(pcgen_path.read_text(encoding="utf-8"))
        pcgen_names = [e["name"] for e in data.get("entries", [])]

    feats = build_feats(raw_dir, pcgen_names)
    class_features = build_class_features(raw_dir)
    _print_report(feats, class_features)

    if args.report_only:
        return 0
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, payload in (
        ("pathbuilder-feats.json", feats),
        ("pathbuilder-class-features.json", class_features),
    ):
        path = out_dir / name
        path.write_text(
            json.dumps(payload, indent=1, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        size = "entries" if "entries" in payload else "counts"
        print(f"scritto {path} ({len(payload[size])} {size})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
