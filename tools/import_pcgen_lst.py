#!/usr/bin/env python3
"""Import dei dataset LST PCGen (Pathfinder 1e) verso il catalogo legality.

Fondazione del builder completo PF1e (task A1): parse dei file .lst della
catena CORE Paizo (clone sparse di github.com/PCGen/pcgen, master 6.09.x) e
emissione di TRE JSON committati in
`pathmaster-dd/packages/rules-engine-v2/src/data/`:

- pcgen-feats.json     — talenti con prerequisiti GREZZI strutturati
                         + effetti BONUS grezzi parsati (slice BONUS)
- pcgen-equipment.json — armi/armature/scudi con stat RAW
- pcgen-spells.json    — incantesimi con livelli per classe

Perimetro DECISO (dichiarato, estensione = aggiungere righe a BOOKS):
- libri: CR, APG, ACG, ARG, UM, UC, UE, OA + (Fase A 2026-08-08) UI, UW,
  HA, PU, AG. Scarti dichiarati nel commento di BOOKS: mythic/campaign/
  codex+bestiari/beginner_box/core_essentials NON importati; Villain Codex
  non presente nel clone. Niente um_*_wordsofpower.lst: sistema alternativo
  PRERULE WORDSOFPOWER;
- classi: SOLO report a stdout (conteggi/nomi per libro): il nostro
  classes.json (40 classi, E6-A7) resta la fonte — niente pcgen-classes.json;
- DESC/BENEFIT MAI esportati: policy del progetto = solo meccaniche + nomi,
  mai testo di regole completo redistribuito (come i cataloghi AoN
  description-brevi; qui ancora piu' stretto: zero prosa).

Formato LST (ricognizione 2026-08-01): TSV, primo campo = nome, poi tag
`CHIAVE:valore`; `X.COPY=Y` crea Y copiando X (le basi sono VISIBLE:NO, gli
oggetti in vendita sono le copie VISIBLE:YES); `X.MOD` estende X; duplicati
= last-wins (ordine di caricamento PCGen), contati.

Prerequisiti: albero grezzo COMPLETO di ogni tag PRE* (niente buttato via),
piu' livello "derived" normalizzato per i tag principali:
PREABILITY(CATEGORY=FEAT)->required_feats, PREVARGTEQ:PreStatScore_*->mins,
PRESTAT->mins, PRETOTALAB->bab_min, PRELEVEL/PREPCLEVEL/PRELEVELMAX->level,
PRECLASS->class_levels, PRESKILL->skill_ranks, PREALIGN->alignments,
PREMULT->nodo ricorsivo. Gli altri tag restano nell'albero grezzo e sono
CONTATI in other_tags / prereq_coverage.not_normalized (copertura reale
stampata nel report e nella doc). Nota semantica dichiarata: il derived
raccoglie i vincoli ANCHE dentro i PREMULT senza valutare AND/OR — e' un
inventario per il builder, non un valutatore (il motore v2 ha gia' il suo
prerequisites.ts curato a mano per la validazione).

Uso:
  python tools/import_pcgen_lst.py                 # scrive i 3 JSON + report
  python tools/import_pcgen_lst.py --report-only   # solo report a stdout
  --pcgen-repo PATH  (default %PCGEN_REPO% o C:/Users/VGit/Downloads/pcgen-repo)
  --out-dir PATH     (default <pathmaster sibling>/packages/rules-engine-v2/src/data)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PCGEN_REPO = Path(
    os.environ.get("PCGEN_REPO", r"C:\Users\VGit\Downloads\pcgen-repo")
)
DEFAULT_OUT_DIR = (
    REPO_ROOT.parent / "pathmaster-dd" / "packages/rules-engine-v2/src/data"
)

DATA_SUBDIR = "data/pathfinder/paizo"

LICENSE_TEXT = (
    "PCGen data sets: OGL 1.0a (Open Game Content di Paizo) distribuiti nel "
    "progetto PCGen (LGPL per il codice). Solo meccaniche e nomi: nessun "
    "testo di regole (DESC/BENEFIT) esportato. Paizo Community Use Policy."
)
DESC_POLICY = (
    "DESC/BENEFIT omessi per policy: solo meccaniche + nomi, mai testo di "
    "regole completo redistribuito."
)

# Libri CORE PF1e (sigla -> dir relativa a data/pathfinder/paizo, titolo, file).
# Estensione futura = aggiungere una riga qui (e i file esistono nel clone).
BOOKS = {
    "CR": {
        "dir": "roleplaying_game/core_rulebook",
        "title": "Core Rulebook",
        "feats": ["cr_feats.lst"],
        "equipment": ["cr_equip_arms_armor.lst"],
        "spells": ["cr_spells.lst"],
    },
    "APG": {
        "dir": "roleplaying_game/advanced_players_guide",
        "title": "Advanced Player's Guide",
        "feats": ["apg_feats.lst"],
        "equipment": ["apg_equip_arms_armor.lst"],
        "spells": ["apg_spells.lst"],
    },
    "ACG": {
        "dir": "roleplaying_game/advanced_class_guide",
        "title": "Advanced Class Guide",
        "feats": ["acg_feats.lst"],
        "equipment": ["acg_equip.lst"],
        "spells": ["acg_spells.lst"],
    },
    "ARG": {
        "dir": "roleplaying_game/advanced_race_guide",
        "title": "Advanced Race Guide",
        "feats": ["arg_feats.lst"],
        "equipment": ["arg_equip_arms_armor.lst"],
        "spells": ["arg_spells.lst"],
    },
    "UM": {
        "dir": "roleplaying_game/ultimate_magic",
        "title": "Ultimate Magic",
        "feats": ["um_feats.lst"],
        "equipment": ["um_equip_arms_armor.lst"],
        "spells": ["um_spells.lst"],
    },
    "UC": {
        "dir": "roleplaying_game/ultimate_combat",
        "title": "Ultimate Combat",
        "feats": ["uc_feats.lst"],
        "equipment": ["uc_equip_arms_armor.lst"],
        "spells": ["uc_spells.lst"],
    },
    "UE": {
        "dir": "roleplaying_game/ultimate_equipment",
        "title": "Ultimate Equipment",
        "feats": [],
        "equipment": ["ue_equip_arms_armor.lst"],
        "spells": ["ue_spells.lst"],
    },
    "OA": {
        "dir": "roleplaying_game/occult_adventures",
        "title": "Occult Adventures",
        "feats": ["oa_feats.lst"],
        "equipment": ["oa_equip.lst"],
        "spells": ["oa_spells.lst"],
    },
    # Fase A (2026-08-08): manuali fuori linea core PRESENTI nel clone.
    # Scarti DICHIARATI (nel clone, NON importati): mythic_adventures
    # (sistema mythic = regole alternative, come words of power),
    # ultimate_campaign (solo uca_feats.lst, gestione campagna),
    # monster_codex + bestiari (contenuto mostri/PNG, fuori scope A1),
    # beginner_box (sottoinsieme del CR), core_essentials (plumbing).
    # Villain Codex: NON presente nel clone sparse (dichiarato).
    "UI": {
        "dir": "roleplaying_game/ultimate_intrigue",
        "title": "Ultimate Intrigue",
        "feats": ["ui_feats.lst"],
        "equipment": ["ui_equip_arms_armor.lst"],
        "spells": ["ui_spells.lst"],
    },
    "UW": {
        "dir": "roleplaying_game/ultimate_wilderness",
        "title": "Ultimate Wilderness",
        "feats": ["uw_feats.lst"],
        "equipment": ["uw_equip_arms_armor.lst"],
        "spells": ["uw_spells.lst"],
    },
    "HA": {
        "dir": "roleplaying_game/horror_adventures",
        "title": "Horror Adventures",
        "feats": ["ha_feats.lst"],
        "equipment": ["ha_equip_arms_armor.lst"],
        "spells": ["ha_spells.lst"],
    },
    "PU": {
        "dir": "roleplaying_game/pathfinder_unchained",
        "title": "Pathfinder Unchained",
        "feats": ["pu_feats.lst"],
        "equipment": ["pu_equip.lst"],
        "spells": ["pu_spells.lst"],
    },
    "AG": {
        "dir": "roleplaying_game/adventurers_guide",
        "title": "Adventurer's Guide",
        "feats": ["ag_feats.lst"],
        "equipment": ["ag_equip_arms_armor.lst"],
        "spells": ["ag_spells.lst"],
    },
}

OUTPUT_FILES = {
    "feats": "pcgen-feats.json",
    "equipment": "pcgen-equipment.json",
    "spells": "pcgen-spells.json",
}

ABILITY_KEYS = ("STR", "DEX", "CON", "INT", "WIS", "CHA")


# ---------------------------------------------------------------------------
# Parser di linea LST
# ---------------------------------------------------------------------------


def iter_lst_records(text: str):
    """Testo .lst -> lista di (nome, [(chiave, valore), ...]).

    Salta commenti (#) e righe vuote. Le righe SOURCE*/CAMPAIGN sono
    metadati di file, non entita': scartate (il nome di un record entita'
    non contiene mai ':', quelle righe si').
    """
    records = []
    for raw in text.splitlines():
        line = raw.strip("\n")
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        fields = [f.strip() for f in line.split("\t")]
        name = fields[0]
        if not name or ":" in name:
            continue
        tags = []
        for field in fields[1:]:
            if not field:
                continue
            key, sep, value = field.partition(":")
            tags.append((key.strip(), value.strip() if sep else ""))
        records.append((name, tags))
    return records


# ---------------------------------------------------------------------------
# Prerequisiti: albero grezzo + derived
# ---------------------------------------------------------------------------


def _split_top_level(text: str, sep: str = ","):
    """Split rispettando la profondita' delle parentesi quadre."""
    parts, depth, current = [], 0, []
    for ch in text:
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
        if ch == sep and depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(ch)
    parts.append("".join(current))
    return [p.strip() for p in parts if p.strip()]


def parse_prereq_token(token: str) -> dict:
    """Un tag PRE* (stringa completa, es. 'PREVARGTEQ:X,13') -> nodo albero.

    PREMULT e' ricorsivo: 'PREMULT:n,[A],[B]' -> {tag, count, of:[...]}.
    Ogni foglia conserva il raw: niente informazione buttata via.
    """
    key, _sep, value = token.partition(":")
    if key == "PREMULT":
        count, _comma, rest = value.partition(",")
        items = re.findall(r"\[([^\]]*)\]", rest)
        return {
            "tag": "PREMULT",
            "count": int(count or 0),
            "of": [parse_prereq_token(item) for item in items],
        }
    return {"tag": key, "args": _split_top_level(value), "raw": token}


def prereq_tree(tags) -> list:
    """Tutti i tag PRE* di un record, in ordine, come albero di nodi.

    Cattura anche i negati `!PRE*` (es. '!PREABILITY:1,...': il personaggio
    NON deve avere X) — restano grezzi nell'albero e contati nei non
    normalizzati; la negazione e' visibile nel tag stesso.
    """
    return [
        parse_prereq_token(f"{k}:{v}")
        for k, v in tags
        if k.startswith("PRE") or k.startswith("!PRE")
    ]


def _empty_derived() -> dict:
    return {
        "required_feats": [],
        "ability_mins": {},
        "bab_min": None,
        "level_min": None,
        "level_max": None,
        "class_levels": [],
        "skill_ranks": [],
        "alignments": [],
        "other_tags": {},
    }


def derive_prereqs(nodes: list) -> dict:
    """Forma normalizzata dei tag principali, raccolta RICORSIVA.

    Dichiarato: i vincoli dentro PREMULT sono raccolti senza valutare
    AND/OR (inventario per il builder, non valutatore). I tag senza forma
    normalizzata sono contati in other_tags.
    """
    derived = _empty_derived()

    def visit(node: dict) -> None:
        tag = node["tag"]
        if tag == "PREMULT":
            for child in node["of"]:
                visit(child)
            return
        args = node.get("args", [])
        if tag == "PREABILITY":
            # args: [n, "CATEGORY=FEAT", Nome1, Nome2, ...] (o TYPE.X / altra
            # CATEGORY: filtri grezzi, non nomi di talenti)
            if any(a == "CATEGORY=FEAT" for a in args):
                for a in args[1:]:
                    if "=" in a or a.startswith("TYPE.") or a.isdigit():
                        continue
                    if a not in derived["required_feats"]:
                        derived["required_feats"].append(a)
            else:
                derived["other_tags"][tag] = derived["other_tags"].get(tag, 0) + 1
        elif tag == "PREVARGTEQ" and len(args) >= 2:
            var, val = args[0], args[1]
            m = re.fullmatch(r"PreStatScore_([A-Z]+)", var)
            if m and m.group(1) in ABILITY_KEYS and val.lstrip("-").isdigit():
                ab = m.group(1)
                derived["ability_mins"][ab] = max(
                    int(val), derived["ability_mins"].get(ab, 0)
                )
            else:
                derived["other_tags"][tag] = derived["other_tags"].get(tag, 0) + 1
        elif tag == "PRESTAT":
            # args: [n, "STR=13", ...]
            for a in args[1:]:
                k, eq, v = a.partition("=")
                if eq and k in ABILITY_KEYS and v.isdigit():
                    derived["ability_mins"][k] = max(
                        int(v), derived["ability_mins"].get(k, 0)
                    )
        elif tag == "PRETOTALAB" and args and args[0].isdigit():
            n = int(args[0])
            derived["bab_min"] = max(n, derived["bab_min"] or 0)
        elif tag in ("PRELEVEL", "PREPCLEVEL") and args and args[0].isdigit():
            n = int(args[0])
            derived["level_min"] = max(n, derived["level_min"] or 0)
        elif tag == "PRELEVELMAX" and args and args[0].isdigit():
            n = int(args[0])
            derived["level_max"] = min(n, derived["level_max"] or n)
        elif tag == "PRECLASS" and len(args) >= 2:
            for a in args[1:]:
                if a not in derived["class_levels"]:
                    derived["class_levels"].append(a)
        elif tag == "PRESKILL" and len(args) >= 2:
            for a in args[1:]:
                skill, eq, ranks = a.partition("=")
                if eq and ranks.isdigit():
                    derived["skill_ranks"].append({"skill": skill, "ranks": int(ranks)})
                else:
                    derived["other_tags"][tag] = derived["other_tags"].get(tag, 0) + 1
        elif tag == "PREALIGN" and args:
            for a in args:
                if a not in derived["alignments"]:
                    derived["alignments"].append(a)
        elif tag == "PREVARGTEQ":
            pass  # gia' gestito sopra
        else:
            derived["other_tags"][tag] = derived["other_tags"].get(tag, 0) + 1

    for node in nodes:
        visit(node)
    return derived


# Tag con forma normalizzata nel derived (copertura dichiarata in doc).
COVERED_PRE_TAGS = (
    "PREMULT",
    "PREABILITY",
    "PREVARGTEQ",
    "PRESTAT",
    "PRETOTALAB",
    "PRELEVEL",
    "PREPCLEVEL",
    "PRELEVELMAX",
    "PRECLASS",
    "PRESKILL",
    "PREALIGN",
)


# ---------------------------------------------------------------------------
# BONUS strutturati (slice BONUS 2026-08-07)
# ---------------------------------------------------------------------------
#
# I tag BONUS:* dei talenti codificano gli EFFETTI meccanici (es.
# `BONUS:COMBAT|AC|1|TYPE=Dodge`). Prima erano letti solo per `ac_bonus`
# dell'equipment; ora ogni talento porta l'albero grezzo parsato in `bonus`.
# Come per i prerequisiti: niente buttato via, niente interpretato a
# tentativi — cio' che non rientra nella forma riconosciuta resta RAW col
# flag `recognized: false` e i segmenti non classificati in `unparsed`.
#
# Forma riconosciuta: segmenti posizionali `GRUPPO|...path...|VALORE` seguiti
# da modificatori `TYPE=...` e condizioni `PRE*`/`!PRE*` raw. `valueNumber` e'
# presente SOLO se il valore e' un intero letterale (le formule `max(3,TL)`,
# i riferimenti a VAR e i `%LIST` restano stringhe raw).


def _split_pipes(text: str) -> list:
    """Split su '|' rispettando la profondita' di () e [].

    Serve perche' le formule possono contenere '=' e virgole dentro chiamate
    (`MIN(4,classlevel("TYPE=PC")+...)`) e i PREMULT contengono '[...],[...]'.
    """
    parts, depth, current = [], 0, []
    for ch in text:
        if ch in "([":
            depth += 1
        elif ch in ")]":
            depth -= 1
        if ch == "|" and depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(ch)
    parts.append("".join(current))
    return parts


_INT_LITERAL = re.compile(r"-?\d+")


def parse_bonus_tag(value: str) -> dict:
    """Un tag BONUS (senza il prefisso 'BONUS:') -> nodo grezzo strutturato.

    Chiavi: raw/group/path/value/recognized sempre; valueNumber solo se
    intero letterale; type solo se `TYPE=...`; conditions solo se ci sono
    PRE* in coda; unparsed solo se ci sono segmenti non classificati (->
    recognized False).
    """
    segments = _split_pipes(value)
    positional = []
    node = {"raw": value, "recognized": True}
    conditions = []
    unparsed = []
    seen_modifier = False
    for seg in segments:
        if seg.startswith("TYPE="):
            node["type"] = seg[len("TYPE=") :]
            seen_modifier = True
        elif seg.startswith("PRE") or seg.startswith("!PRE"):
            conditions.append(seg)
            seen_modifier = True
        elif seen_modifier or seg.startswith("TYPE."):
            # Un modificatore dopo i modificatori, o una forma TYPE.x (reale:
            # `BONUS:COMBAT|GLOBALRANGEPENALTY|2|TYPE.Sling`): non la
            # interpretiamo, la dichiariamo.
            unparsed.append(seg)
        else:
            positional.append(seg)
    if unparsed or len(positional) < 2:
        node["recognized"] = False
    node["group"] = positional[0] if positional else ""
    node["path"] = positional[1:-1] if len(positional) >= 2 else []
    node["value"] = positional[-1] if positional else ""
    if _INT_LITERAL.fullmatch(node["value"]):
        node["valueNumber"] = int(node["value"])
    if conditions:
        node["conditions"] = conditions
    if unparsed:
        node["unparsed"] = unparsed
    return node


def _empty_bonus_stats() -> dict:
    return {
        "feats_with_bonus": 0,
        "total_tags": 0,
        "by_group": {},
        "literal_value": 0,
        "with_type": 0,
        "recognized": 0,
        "unrecognized": 0,
    }


def _bonus_stats_add(stats: dict, nodes: list) -> None:
    if nodes:
        stats["feats_with_bonus"] += 1
    for node in nodes:
        stats["total_tags"] += 1
        group = node["group"] or "(vuoto)"
        stats["by_group"][group] = stats["by_group"].get(group, 0) + 1
        if "valueNumber" in node:
            stats["literal_value"] += 1
        if "type" in node:
            stats["with_type"] += 1
        stats["recognized" if node["recognized"] else "unrecognized"] += 1


def _coverage_add(cov: dict, nodes: list) -> None:
    """Conta le occorrenze per tag: covered vs not_normalized."""

    def visit(node: dict) -> None:
        tag = node["tag"]
        bucket = "covered" if tag in COVERED_PRE_TAGS else "not_normalized"
        cov[bucket][tag] = cov[bucket].get(tag, 0) + 1
        for child in node.get("of", []):
            visit(child)

    for node in nodes:
        visit(node)


# ---------------------------------------------------------------------------
# Entita'
# ---------------------------------------------------------------------------


def _tag_values(tags, key: str) -> list:
    return [v for k, v in tags if k == key]


def _tag_value(tags, key: str):
    vals = _tag_values(tags, key)
    return vals[-1] if vals else None


def _number(value):
    """'150' -> 150, '0.5' -> 0.5, altro/None -> None."""
    if value is None:
        return None
    try:
        n = float(value)
    except ValueError:
        return None
    return int(n) if n == int(n) else n


def feats_from_records(records, book: str):
    """Record LST -> (entries talenti, stats).

    I tag BONUS:* (effetti meccanici) finiscono in `bonus` come nodi grezzi
    parsati (parse_bonus_tag): niente scartato, le forme non riconosciute
    restano raw col flag dichiarato. Nota perimetro: i `.MOD` dei talenti
    (es. `CATEGORY=FEAT|X.MOD`, varianti condizionali) sono ignorati qui come
    gia' per i prerequisiti — i loro BONUS NON entrano (dichiarato in doc).
    """
    by_name = {}
    order = []
    stats = {
        "duplicates_overridden": 0,
        "prereq_coverage": {"covered": {}, "not_normalized": {}},
        "bonus": _empty_bonus_stats(),
    }
    for name, tags in records:
        if not name or name.endswith((".MOD", ".FORGET")) or ".COPY=" in name:
            continue
        nodes = prereq_tree(tags)
        _coverage_add(stats["prereq_coverage"], nodes)
        bonus = [parse_bonus_tag(v) for v in _tag_values(tags, "BONUS")]
        _bonus_stats_add(stats["bonus"], bonus)
        stack = _tag_value(tags, "STACK")
        if name in by_name:
            stats["duplicates_overridden"] += 1
        else:
            order.append(name)
        by_name[name] = {
            "name": name,
            "key": _tag_value(tags, "KEY") or name,
            "source_book": book,
            "category": (_tag_value(tags, "CATEGORY") or "").lower() or None,
            "types": (
                (_tag_value(tags, "TYPE") or "").split(".")
                if _tag_value(tags, "TYPE")
                else []
            ),
            "multiple": _tag_value(tags, "MULT") == "YES",
            "stack": (stack == "YES") if stack else None,
            "choose": _tag_value(tags, "CHOOSE"),
            "prerequisites": nodes,
            "derived": derive_prereqs(nodes),
            "bonus": bonus,
            "source_page": _tag_value(tags, "SOURCEPAGE"),
        }
    return [by_name[n] for n in order], stats


def _resolve_equip_records(records):
    """Risolve .COPY (eredita i tag della base) e .MOD. Ritorna
    {nome_output: tags_effettivi} + stats."""
    raw = {}
    copies = []
    mods = []
    stats = {
        "copies_resolved": 0,
        "copies_unresolved": 0,
        "mods_applied": 0,
        "mods_unresolved": 0,
        "forgets": 0,
        "skipped_hidden": 0,
        "duplicates_overridden": 0,
    }
    for name, tags in records:
        if ".COPY=" in name:
            base, _sep, _new = name.partition(".COPY=")
            copies.append((base.strip(), tags))
        elif name.endswith(".MOD"):
            mods.append((name[:-4].strip(), tags))
        elif name.endswith(".FORGET"):
            if raw.pop(name[:-7].strip(), None) is not None:
                stats["forgets"] += 1
        else:
            # .COPY= referenzia la KEY della base (es. la riga si chiama
            # "Longsword" ma la sua KEY e' "Longsword (Base)"): indicizza per
            # KEY quando c'e', altrimenti per nome di riga.
            key = _tag_value(tags, "KEY") or name
            if key in raw:
                stats["duplicates_overridden"] += 1
            raw[key] = list(tags)

    resolved = {}

    def resolve(name: str, seen=()) -> list:
        if name in resolved:
            return resolved[name]
        if name in seen or name not in raw:
            return []
        resolved[name] = raw[name]
        return raw[name]

    effective = {}
    for name, tags in raw.items():
        effective[name] = list(resolve(name))
    for base, tags in copies:
        base_tags = resolve(base)
        if not base_tags:
            stats["copies_unresolved"] += 1
            continue
        out_name = _tag_value(tags, "KEY")
        if not out_name:
            stats["copies_unresolved"] += 1
            continue
        merged = list(base_tags) + list(tags)
        effective[out_name] = merged
        stats["copies_resolved"] += 1
    for target, tags in mods:
        if target in effective:
            effective[target] = effective[target] + list(tags)
            stats["mods_applied"] += 1
        else:
            stats["mods_unresolved"] += 1
    return effective, stats


def equipment_from_records(records, book: str):
    """Record LST -> (entries armi/armature/scudi, stats).

    Solo oggetti VISIBLE (le basi sono VISIBLE:NO) il cui TYPE effettivo
    contiene Weapon/Armor/Shield. TYPE:.CLEAR azzera i tipi ereditati
    (semantica PCGen minima).
    """
    effective, stats = _resolve_equip_records(records)
    entries = []
    for name, tags in effective.items():
        types = []
        for k, v in tags:
            if k == "TYPE":
                if v == ".CLEAR":
                    types = []
                else:
                    types.extend(t for t in v.split(".") if t)
        kind = (
            "weapon"
            if "Weapon" in types
            else (
                "armor" if "Armor" in types else "shield" if "Shield" in types else None
            )
        )
        if kind is None:
            continue
        if _tag_value(tags, "VISIBLE") == "NO":
            stats["skipped_hidden"] += 1
            continue
        ac_bonus = None
        for bonus in _tag_values(tags, "BONUS"):
            parts = bonus.split("|")
            if len(parts) >= 4 and parts[0] == "COMBAT" and parts[1] == "AC":
                if parts[3] in ("TYPE=Armor", "TYPE=Shield"):
                    n = _number(parts[2])
                    if n is not None:
                        ac_bonus = n if ac_bonus is None else max(ac_bonus, n)
        proficiency = _tag_value(tags, "PROFICIENCY")
        if proficiency and "|" in proficiency:
            proficiency = proficiency.split("|", 1)[1]
        entry = {
            "name": name,
            "key": _tag_value(tags, "KEY") or name,
            "source_book": book,
            "kind": kind,
            "types": types,
            "proficiency": proficiency,
            "cost": _number(_tag_value(tags, "COST")),
            "weight": _number(_tag_value(tags, "WT")),
            "source_page": _tag_value(tags, "SOURCEPAGE"),
        }
        if kind == "weapon":
            entry.update(
                {
                    "damage": _tag_value(tags, "DAMAGE"),
                    "crit_mult": _number(
                        (_tag_value(tags, "CRITMULT") or "").lstrip("xX")
                    )
                    or None,
                    "crit_range": _number(_tag_value(tags, "CRITRANGE")),
                    "range_increment": _number(_tag_value(tags, "RANGE")),
                    "wield": _tag_value(tags, "WIELD"),
                }
            )
        else:
            entry.update(
                {
                    "ac_bonus": ac_bonus,
                    "max_dex": _number(_tag_value(tags, "MAXDEX")),
                    "armor_check_penalty": _number(_tag_value(tags, "ACCHECK")),
                    "spell_failure": _number(_tag_value(tags, "SPELLFAILURE")),
                }
            )
        entries.append(entry)
    entries.sort(key=lambda e: (e["kind"], e["name"]))
    return entries, stats


def _parse_level_groups(value: str) -> dict:
    """'Cleric,Druid=6|Sorcerer,Wizard=6' -> {Classe: livello}."""
    out = {}
    for group in value.split("|"):
        names, eq, level = group.partition("=")
        if not eq or not level.strip().isdigit():
            continue
        for name in names.split(","):
            name = name.strip()
            if name:
                out[name] = int(level)
    return out


def spells_from_records(records, book: str):
    """Record LST -> (entries incantesimi, stats).

    .MOD con CLASSES/DOMAINS si fonde nella base (stesso file); .MOD senza
    campi rilevanti = no-op contato; .MOD orfano = contato. Le .COPY di
    classe (es. 'Occultist Spell ~ X') sono scartate (non sono spell da
    lista). Duplicati cross-file: last-wins, contati.
    """
    by_name = {}
    order = []
    mods = []
    stats = {
        "duplicates_overridden": 0,
        "mods_merged": 0,
        "mods_noop": 0,
        "mods_unresolved": 0,
        "copies_skipped": 0,
    }
    for name, tags in records:
        if ".COPY=" in name:
            stats["copies_skipped"] += 1
            continue
        if name.endswith(".MOD"):
            mods.append((name[:-4].strip(), tags))
            continue
        if name.endswith(".FORGET"):
            by_name.pop(name[:-7].strip(), None)
            continue
        if name in by_name:
            stats["duplicates_overridden"] += 1
        else:
            order.append(name)
        by_name[name] = {
            "name": name,
            "key": _tag_value(tags, "KEY") or name,
            "source_book": book,
            "types": (
                (_tag_value(tags, "TYPE") or "").split(".")
                if _tag_value(tags, "TYPE")
                else []
            ),
            "classes": _parse_level_groups(_tag_value(tags, "CLASSES") or ""),
            "domains": _parse_level_groups(_tag_value(tags, "DOMAINS") or ""),
            "school": _tag_value(tags, "SCHOOL"),
            "subschool": _tag_value(tags, "SUBSCHOOL"),
            "descriptors": [
                d.strip()
                for d in (_tag_value(tags, "DESCRIPTOR") or "").split(",")
                if d.strip()
            ],
            "components": _tag_value(tags, "COMPS"),
            "casting_time": _tag_value(tags, "CASTTIME"),
            "range": _tag_value(tags, "RANGE"),
            "target_area": _tag_value(tags, "TARGETAREA"),
            "duration": _tag_value(tags, "DURATION"),
            "saving_throw": _tag_value(tags, "SAVEINFO"),
            "spell_resistance": _tag_value(tags, "SPELLRES"),
            "source_page": _tag_value(tags, "SOURCEPAGE"),
        }
    for target, tags in mods:
        if target not in by_name:
            stats["mods_unresolved"] += 1
            continue
        added = False
        for key in ("CLASSES", "DOMAINS"):
            extra = _parse_level_groups(_tag_value(tags, key) or "")
            if extra:
                by_name[target][key.lower()].update(extra)
                added = True
        stats["mods_merged" if added else "mods_noop"] += 1
    return [by_name[n] for n in order], stats


# ---------------------------------------------------------------------------
# Classi: SOLO report (decisione dichiarata: niente pcgen-classes.json)
# ---------------------------------------------------------------------------


def class_names_in_file(path: Path) -> list:
    """Nomi delle classi definite (righe 'CLASS:Nome') in un classes.lst."""
    names = []
    if not path.is_file():
        return names
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("CLASS:"):
            name = line.split("\t", 1)[0][len("CLASS:") :].strip()
            if name and not name.endswith((".MOD", ".COPY", ".FORGET")):
                names.append(name)
    return names


# ---------------------------------------------------------------------------
# Build dei cataloghi
# ---------------------------------------------------------------------------

PARSERS = {
    "feats": (lambda b: BOOKS[b]["feats"], feats_from_records),
    "equipment": (lambda b: BOOKS[b]["equipment"], equipment_from_records),
    "spells": (lambda b: BOOKS[b]["spells"], spells_from_records),
}


def _pcgen_commit(pcgen_root: Path) -> str:
    try:
        out = subprocess.run(
            ["git", "-C", str(pcgen_root), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if out.returncode == 0:
            return out.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass
    return "unknown"


def build_catalog(pcgen_root, kind: str, books=None) -> dict:
    """Catalogo completo di un tipo sui BOOKS configurati (o sul sottoinsieme
    `books`, usato dai test su radici finte: un libro configurato ma assente
    sul disco e' un errore, non una resa silenziosa)."""
    if kind not in PARSERS:
        raise ValueError(
            f"kind sconosciuto: {kind!r} (atteso uno di {sorted(PARSERS)})"
        )
    pcgen_root = Path(pcgen_root)
    files_for, parser = PARSERS[kind]
    entries = []
    counts = {}
    stats = {}
    for book, cfg in BOOKS.items():
        if books is not None and book not in books:
            continue
        book_records = []
        for rel in files_for(book):
            path = pcgen_root / DATA_SUBDIR / cfg["dir"] / rel
            if not path.is_file():
                raise FileNotFoundError(f"file LST mancante: {path}")
            book_records.extend(
                iter_lst_records(path.read_text(encoding="utf-8", errors="replace"))
            )
        book_entries, book_stats = parser(book_records, book)
        entries.extend(book_entries)
        counts[book] = len(book_entries)
        stats[book] = book_stats
    return {
        "_provenance": {
            "source": (
                "PCGen data sets (github.com/PCGen/pcgen), "
                f"{DATA_SUBDIR}/roleplaying_game/*"
            ),
            "pcgen_commit": _pcgen_commit(pcgen_root),
            "generated_by": "Master-DD-Taverna/tools/import_pcgen_lst.py",
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "license": LICENSE_TEXT,
            "desc_policy": DESC_POLICY,
            "books": {
                b: cfg["title"]
                for b, cfg in BOOKS.items()
                if books is None or b in books
            },
        },
        "counts": counts,
        "stats": stats,
        "entries": entries,
    }


def _print_report(payloads: dict, classes_report: dict) -> None:
    for kind, payload in payloads.items():
        print(
            f"[{kind}] totale: {len(payload['entries'])} voci "
            f"(commit pcgen {payload['_provenance']['pcgen_commit'][:12]})"
        )
        for book, n in payload["counts"].items():
            print(f"  {book}: {n}")
        if kind == "feats":
            covered, not_norm = {}, {}
            for book_stats in payload["stats"].values():
                for tag, n in book_stats["prereq_coverage"]["covered"].items():
                    covered[tag] = covered.get(tag, 0) + n
                for tag, n in book_stats["prereq_coverage"]["not_normalized"].items():
                    not_norm[tag] = not_norm.get(tag, 0) + n
            print(
                f"  PRE* normalizzati: {dict(sorted(covered.items(), key=lambda kv: -kv[1]))}"
            )
            print(
                f"  PRE* grezzi (non normalizzati): {dict(sorted(not_norm.items(), key=lambda kv: -kv[1]))}"
            )
            bonus = _empty_bonus_stats()
            for book_stats in payload["stats"].values():
                bs = book_stats["bonus"]
                bonus["feats_with_bonus"] += bs["feats_with_bonus"]
                bonus["total_tags"] += bs["total_tags"]
                for group, n in bs["by_group"].items():
                    bonus["by_group"][group] = bonus["by_group"].get(group, 0) + n
                for k in ("literal_value", "with_type", "recognized", "unrecognized"):
                    bonus[k] += bs[k]
            total = bonus["total_tags"] or 1
            print(
                f"  BONUS: {bonus['total_tags']} tag su {bonus['feats_with_bonus']} talenti | "
                f"gruppi {dict(sorted(bonus['by_group'].items(), key=lambda kv: -kv[1]))}"
            )
            print(
                f"  BONUS: valore letterale {bonus['literal_value']}/{bonus['total_tags']} "
                f"({bonus['literal_value'] / total:.0%}) | "
                f"TYPE= {bonus['with_type']} ({bonus['with_type'] / total:.0%}) | "
                f"non riconosciuti {bonus['unrecognized']} ({bonus['unrecognized'] / total:.1%})"
            )
    if classes_report:
        print("[classi] SOLO REPORT (classes.json curato resta la fonte):")
        for book, names in classes_report.items():
            print(f"  {book}: {len(names)} classi PCGen")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--pcgen-repo", default=str(DEFAULT_PCGEN_REPO))
    ap.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    ap.add_argument("--report-only", action="store_true")
    args = ap.parse_args(argv)

    pcgen_root = Path(args.pcgen_repo)
    if not (pcgen_root / DATA_SUBDIR).is_dir():
        print(
            f"ERRORE: dataset PCGen non trovato in {pcgen_root / DATA_SUBDIR}",
            file=sys.stderr,
        )
        return 1

    payloads = {kind: build_catalog(pcgen_root, kind) for kind in PARSERS}
    classes_report = {
        book: class_names_in_file(pcgen_root / DATA_SUBDIR / cfg["dir"] / f)
        for book, cfg in BOOKS.items()
        for f in [
            next(
                (
                    x
                    for x in [
                        "cr_classes.lst",
                        "apg_classes.lst",
                        "acg_classes.lst",
                        "um_classes.lst",
                        "uc_classes.lst",
                        "oa_classes.lst",
                        "ui_classes.lst",
                        "uw_classes.lst",
                    ]
                    if (pcgen_root / DATA_SUBDIR / cfg["dir"] / x).is_file()
                ),
                None,
            )
        ]
        if f
    }
    _print_report(payloads, classes_report)

    if args.report_only:
        return 0
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for kind, payload in payloads.items():
        path = out_dir / OUTPUT_FILES[kind]
        path.write_text(
            json.dumps(payload, indent=1, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        print(f"scritto {path} ({len(payload['entries'])} voci)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
