#!/usr/bin/env python3
"""Import PCGen delle classi: progressione per livello + class abilities.

Slice D3-a (2026-08-07) del piano
`sessione-2026-07-16/rapporti/2026-08-02-piano-completamento-db-pcgen-pathbuilder.md`.
Stesso stile di `import_pcgen_lst.py` (riusa parser di linea, prereq_tree,
parse_bonus_tag, provenance): parse dei file class-related dei BOOKS gia'
configurati ed emissione di DUE JSON committati in
`pathmaster-dd/packages/rules-engine-v2/src/data/`:

- pcgen-class-progression.json — per classe, i grant per livello 1..20:
  feature concesse (tag ABILITY: pool + natura + nomi + condizioni grezze)
  e pool di scelta concessi (BONUS:ABILITYPOOL, cadenze degli slot);
- pcgen-class-abilities.json — le feature di classe vere (record di
  `*_abilities_class.lst`): nome, key, classe di appartenenza dove
  ricavabile, BONUS grezzi parsati, prerequisiti grezzi. Per D3-b (pool di
  scelta + legality RequiredSpecial).

Le TRE sorgenti della progressione (ricognizione 2026-08-07):
1. righe livello di `*_classes.lst` (`N<TAB>ABILITY:pool|NATURA|nomi|cond...`,
   dominante in ACG);
2. righe `CATEGORY=Class|<Target>.MOD` di `*_abilities_class.lst` /
   `*_abilities_globalvar.lst` (dominante in CR/APG/UM/UC; in OA la categoria
   e' `CLASS` maiuscolo). Target -> classe: si stacca il suffisso
   ` ~ Standard Class Full` / ` ~ Standard Class` (catena PCGen collassata,
   dichiarato) o il target e' il nome stesso della classe;
3. righe `CATEGORY=Special Ability|<Classe> ~ <Feature>.MOD`: SOLO i
   BONUS:ABILITYPOOL (le cadenze degli slot, es. rage power a 2,4,...,20);
   i loro ABILITY sono plumbing PCGen e restano fuori (dichiarato).

Livello di un grant da riga MOD: il gate `PREVARGTEQ:<var>,<N>` con N intero
(minimo se piu' di uno); senza gate il grant vale dal 1° (dichiarato: le
concessioni non gated — es. Weapon and Armor Proficiency — sono di 1°).
I gate restano comunque grezzi in `conditions`: niente buttato via.

Perimetro DECISO (come import_pcgen_lst): libri CR/APG/ACG/ARG/UM/UC/OA +
(Fase A 2026-08-08) UI/UW/HA/PU/AG — vedi il commento di BOOK_CLASS_FILES
per gli scarti dichiarati su classes.lst (HA: solo phantom; PU: nessun
classes.lst; AG: solo prestige class).
(ARG non ha classes.lst; UE non ha file di classe: configurati vuoti, non
errori). DESC/BENEFIT MAI esportati. I `.MOD` sui record ability (bonus
aggiunti a feature esistenti) NON si fondono — stessa scelta dei feat,
dichiarata. Le classi `Ex-*` (penalita' per abbandono) sono fuori perimetro.

Uso:
  python tools/import_pcgen_classes.py                 # scrive i 2 JSON + report
  python tools/import_pcgen_classes.py --report-only   # solo report a stdout
  --pcgen-repo PATH  (default %PCGEN_REPO% o C:/Users/VGit/Downloads/pcgen-repo)
  --out-dir PATH     (default <pathmaster sibling>/packages/rules-engine-v2/src/data)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.import_pcgen_lst import (  # noqa: E402
    BOOKS,
    DATA_SUBDIR,
    DEFAULT_OUT_DIR,
    DEFAULT_PCGEN_REPO,
    DESC_POLICY,
    LICENSE_TEXT,
    _bonus_stats_add,
    _coverage_add,
    _empty_bonus_stats,
    _pcgen_commit,
    _split_pipes,
    _tag_value,
    _tag_values,
    iter_lst_records,
    parse_bonus_tag,
    prereq_tree,
)

REPO_ROOT = Path(__file__).resolve().parents[1]

# File di classe per libro (dir ereditata da BOOKS di import_pcgen_lst).
# "classes": classes.lst (righe livello); "abilities": record feature;
# "mod_files": file scanditi per le righe CATEGORY=*.MOD della progressione.
# Estensione futura = aggiungere una riga qui (e i file esistono nel clone).
BOOK_CLASS_FILES = {
    "CR": {
        "dir": BOOKS["CR"]["dir"],
        "classes": ["cr_classes.lst"],
        "abilities": ["cr_abilities_class.lst"],
        "mod_files": ["cr_abilities_class.lst", "cr_abilities_globalvar.lst"],
    },
    "APG": {
        "dir": BOOKS["APG"]["dir"],
        "classes": ["apg_classes.lst"],
        "abilities": ["apg_abilities_class.lst"],
        "mod_files": ["apg_abilities_class.lst", "apg_abilities_globalvar.lst"],
    },
    "ACG": {
        "dir": BOOKS["ACG"]["dir"],
        "classes": ["acg_classes.lst"],
        "abilities": ["acg_abilities_class.lst"],
        "mod_files": ["acg_abilities_class.lst", "acg_abilities_globalvar.lst"],
    },
    "ARG": {
        "dir": BOOKS["ARG"]["dir"],
        "classes": [],
        "abilities": ["arg_abilities_class.lst"],
        "mod_files": ["arg_abilities_class.lst", "arg_abilities_globalvar.lst"],
    },
    "UM": {
        "dir": BOOKS["UM"]["dir"],
        "classes": ["um_classes.lst"],
        "abilities": ["um_abilities_class.lst"],
        "mod_files": ["um_abilities_class.lst", "um_abilities_globalvar.lst"],
    },
    "UC": {
        "dir": BOOKS["UC"]["dir"],
        "classes": ["uc_classes.lst"],
        "abilities": ["uc_abilities_class.lst"],
        "mod_files": ["uc_abilities_class.lst", "uc_abilities_globalvar.lst"],
    },
    "UE": {"dir": BOOKS["UE"]["dir"], "classes": [], "abilities": [], "mod_files": []},
    "OA": {
        "dir": BOOKS["OA"]["dir"],
        "classes": ["oa_classes.lst"],
        "abilities": ["oa_abilities_class.lst"],
        "mod_files": ["oa_abilities_class.lst"],
    },
    # Fase A (2026-08-08): manuali fuori linea core. UI/UW portano le classi
    # PC Vigilante e Shifter (corpus_missing D6). Scarti DICHIARATI:
    # - HA: il suo classes.lst definisce solo "Undead Phantom" (un phantom,
    #   TYPE:Monster — NON una classe PC): classes non configurato;
    # - PU: nessun classes.lst (le varianti Unchained vivono negli abilities
    #   come record/MOD sulle classi base);
    # - AG: il suo classes.lst definisce solo prestige class (il corpus
    #   classes.json non ne ha): classes non configurato.
    "UI": {
        "dir": BOOKS["UI"]["dir"],
        "classes": ["ui_classes.lst"],
        "abilities": ["ui_abilities_class.lst"],
        "mod_files": ["ui_abilities_class.lst"],
    },
    "UW": {
        "dir": BOOKS["UW"]["dir"],
        "classes": ["uw_classes.lst"],
        "abilities": ["uw_abilities_class.lst"],
        "mod_files": ["uw_abilities_class.lst"],
    },
    "HA": {
        "dir": BOOKS["HA"]["dir"],
        "classes": [],
        "abilities": ["ha_abilities_class.lst"],
        "mod_files": ["ha_abilities_class.lst"],
    },
    "PU": {
        "dir": BOOKS["PU"]["dir"],
        "classes": [],
        "abilities": ["pu_abilities_class.lst"],
        "mod_files": ["pu_abilities_class.lst"],
    },
    "AG": {
        "dir": BOOKS["AG"]["dir"],
        "classes": [],
        "abilities": ["ag_abilities_class.lst"],
        "mod_files": ["ag_abilities_class.lst"],
    },
}

OUTPUT_FILES = {
    "progression": "pcgen-class-progression.json",
    "abilities": "pcgen-class-abilities.json",
}


# ---------------------------------------------------------------------------
# Parse dei singoli grant
# ---------------------------------------------------------------------------


def parse_ability_grant(value: str) -> dict:
    """Un tag ABILITY (senza il prefisso 'ABILITY:') -> grant strutturato.

    Forma: `pool|NATURA|nome1|nome2|...|condizioni`. I segmenti che iniziano
    con PRE/!PRE sono condizioni (grezze, PREMULT con parentesi quadre
    preservato dallo split); i segmenti `TYPE=...` in posizione nome restano
    nomi (forma reale dei grant Internal, dichiarata).
    """
    segments = _split_pipes(value)
    pool = segments[0] if segments else ""
    nature = segments[1] if len(segments) > 1 else ""
    names, conditions = [], []
    for seg in segments[2:]:
        if seg.startswith("PRE") or seg.startswith("!PRE"):
            conditions.append(seg)
        else:
            names.append(seg)
    return {"pool": pool, "nature": nature, "names": names, "conditions": conditions}


def parse_pool_grant(value: str) -> dict | None:
    """Un tag BONUS (senza 'BONUS:') -> grant di pool, o None se non ABILITYPOOL."""
    segments = _split_pipes(value)
    if not segments or segments[0] != "ABILITYPOOL":
        return None
    conditions = [
        s for s in segments[3:] if s.startswith("PRE") or s.startswith("!PRE")
    ]
    return {
        "pool": segments[1] if len(segments) > 1 else "",
        "value": segments[2] if len(segments) > 2 else "",
        "conditions": conditions,
    }


def parse_var_pool_grant(value: str) -> dict | None:
    """Un tag BONUS (senza 'BONUS:') -> grant pool-var, o None se non VAR.

    Alcune cadenze di slot sono codificate come conteggio VAR (forma reale:
    `BONUS:VAR|InvestigatorTalentCount|-1|PREMULT:...` per gli investigator
    talents, `ArcanistExploitPool` per gli exploit). Catturate grezze come
    grant di kind "pool-var": il livello si deriva SOLO dai gate PRECLASS
    (extract_var_pool_level) — un PREVARGTEQ qui puo' essere un CONTEGGIO
    (es. MagusArcanaCount), non un livello, e non viene mai letto come tale.
    """
    segments = _split_pipes(value)
    if not segments or segments[0] != "VAR":
        return None
    conditions = [
        s for s in segments[3:] if s.startswith("PRE") or s.startswith("!PRE")
    ]
    return {
        "pool": segments[1] if len(segments) > 1 else "",
        "value": segments[2] if len(segments) > 2 else "",
        "conditions": conditions,
    }


_LEVEL_GATE = re.compile(r"^PREVARGTEQ:[A-Za-z0-9_]+,(-?\d+)$")
_CLASS_GATE = re.compile(r"(?<!!)PRECLASS:1,([^,.\[\]]+)=(\d+)")


def _class_gate_levels(conditions: list) -> list:
    """Livelli dai gate PRECLASS:1,<Classe>=<N> (N>=1) non negati, anche
    dentro PREMULT (la condizione resta grezza: qui si cerca solo il numero).
    Nomi puntati (TYPE.Base) e valori 0 non sono livelli di classe."""
    levels = []
    for cond in conditions:
        for m in _CLASS_GATE.finditer(cond):
            n = int(m.group(2))
            if n >= 1:
                levels.append(n)
    return levels


def extract_level_gate(conditions: list) -> int:
    """Livello di concessione dai gate PREVARGTEQ grezzi.

    N intero minimo fra i gate (la concessione parte dal primo livello
    gated); gate non interi (VAR/formule) non sono livelli; nessun gate ->
    concessa dal 1° (dichiarato: le proficiency e simili non gated sono di
    1° livello).
    """
    levels = [int(m.group(1)) for c in conditions if (m := _LEVEL_GATE.match(c))]
    return min(levels) if levels else 1


def extract_pool_level(conditions: list) -> int:
    """Livello di un grant di pool (ABILITYPOOL): PREVARGTEQ intero come
    extract_level_gate, altrimenti gate PRECLASS:1,Classe=N (forma reale
    delle cadenze Hunter/Magus/Gunslinger), altrimenti 1 (dichiarato)."""
    levels = [int(m.group(1)) for c in conditions if (m := _LEVEL_GATE.match(c))]
    levels += _class_gate_levels(conditions)
    return min(levels) if levels else 1


def extract_var_pool_level(conditions: list):
    """Livello di un grant pool-var: SOLO gate PRECLASS:1,Classe=N espliciti;
    altrimenti None (livello non derivato, dichiarato — i PREVARGTEQ dei
    pool-var possono essere conteggi, mai letti come livelli)."""
    levels = _class_gate_levels(conditions)
    return min(levels) if levels else None


def _grant_key(grant: dict) -> tuple:
    return (
        grant["level"],
        grant["kind"],
        grant.get("pool", ""),
        grant.get("nature", ""),
        tuple(grant.get("names", [])),
        grant.get("value", ""),
        tuple(grant.get("conditions", [])),
    )


# ---------------------------------------------------------------------------
# Sorgente 1: righe livello dei classes.lst
# ---------------------------------------------------------------------------


def progression_from_classes_text(text: str, book: str) -> list:
    """Testo classes.lst -> [{class, source_books, grants}].

    Righe `CLASS:Nome` aprono/continuano una classe (le `Ex-*` sono fuori
    perimetro); righe `N<TAB>tag` le attaccano alla classe corrente. CAST/
    KNOWN/altri tag non producono grant.
    """
    by_class: dict[str, dict] = {}
    current = None
    for raw in text.splitlines():
        line = raw.strip("\n")
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        fields = [f.strip() for f in line.split("\t")]
        head = fields[0]
        if head.startswith("CLASS:"):
            name = head[len("CLASS:") :].strip()
            if name.endswith((".MOD", ".FORGET")) or ".COPY" in name:
                current = None
                continue
            current = None if name.startswith("Ex-") else name
            if current and current not in by_class:
                by_class[current] = {
                    "class": current,
                    "source_books": [book],
                    "grants": [],
                }
            continue
        if current is None or not head.isdigit():
            continue
        level = int(head)
        grants = by_class[current]["grants"]
        for field in fields[1:]:
            key, sep, value = field.partition(":")
            if not sep:
                continue
            if key == "ABILITY":
                grant = parse_ability_grant(value)
                grants.append({"level": level, "kind": "ability", **grant})
            elif key == "BONUS":
                pool = parse_pool_grant(value)
                if pool:
                    grants.append({"level": level, "kind": "pool", **pool})
    return list(by_class.values())


# ---------------------------------------------------------------------------
# Sorgenti 2-3: righe CATEGORY=*.MOD di abilities_class / abilities_globalvar
# ---------------------------------------------------------------------------

_MOD_NAME = re.compile(r"^CATEGORY=([^|]+)\|(.+)\.MOD$")
_STANDARD_SUFFIXES = (" ~ Standard Class Full", " ~ Standard Class")


def _mod_target_class(category: str, target: str, known_classes: set):
    """(categoria, target) di una riga MOD -> (classe, cattura) o (None, ...).

    cattura: "all" per CATEGORY=Class (ABILITY + pool), "pool" per
    CATEGORY=Special Ability (solo BONUS:ABILITYPOOL — cadenze slot),
    None per le altre categorie (saltate, contate dal chiamante).
    """
    cat = category.strip().lower()
    if cat == "class":
        for suffix in _STANDARD_SUFFIXES:
            if target.endswith(suffix):
                candidate = target[: -len(suffix)]
                return (
                    (candidate, "all") if candidate in known_classes else (None, None)
                )
        if target in known_classes:
            return target, "all"
        return None, None
    if cat == "special ability":
        prefix = target.split(" ~ ", 1)[0]
        if prefix in known_classes:
            return prefix, "pool"
    return None, None


def _empty_mod_stats() -> dict:
    return {
        "mods_skipped_other_category": 0,
        "mods_unmapped_target": 0,
        "mods_without_grants": 0,
        "duplicates_collapsed": 0,
    }


def progression_from_mod_text(text: str, book: str, known_classes: set):
    """Testo abilities_* -> ([grant con chiave 'class'], stats).

    Solo le righe `CATEGORY=...|<target>.MOD`; le altre righe del file sono
    record ability (gestiti da abilities_from_records) o metadati.
    """
    grants = []
    stats = _empty_mod_stats()
    seen = set()
    for raw in text.splitlines():
        line = raw.strip("\n")
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        fields = [f.strip() for f in line.split("\t")]
        m = _MOD_NAME.match(fields[0])
        if not m:
            continue
        cls, capture = _mod_target_class(m.group(1), m.group(2), known_classes)
        if cls is None:
            if m.group(1).strip().lower() in ("class", "special ability"):
                stats["mods_unmapped_target"] += 1
            else:
                stats["mods_skipped_other_category"] += 1
            continue
        before = len(grants)
        for field in fields[1:]:
            key, sep, value = field.partition(":")
            if not sep:
                continue
            grant = None
            if key == "ABILITY" and capture == "all":
                parsed = parse_ability_grant(value)
                grant = {
                    **parsed,
                    "kind": "ability",
                    "level": extract_level_gate(parsed["conditions"]),
                }
            elif key == "BONUS":
                parsed = parse_pool_grant(value)
                if parsed:
                    grant = {
                        **parsed,
                        "kind": "pool",
                        "level": extract_pool_level(parsed["conditions"]),
                    }
                elif capture == "pool":
                    parsed_var = parse_var_pool_grant(value)
                    if parsed_var:
                        grant = {
                            **parsed_var,
                            "kind": "pool-var",
                            "level": extract_var_pool_level(parsed_var["conditions"]),
                        }
            if grant is None:
                continue
            grant["class"] = cls
            gk = _grant_key(grant) + (cls,)
            if gk in seen:
                stats["duplicates_collapsed"] += 1
                continue
            seen.add(gk)
            grants.append(grant)
        if len(grants) == before:
            stats["mods_without_grants"] += 1
    return grants, stats


# ---------------------------------------------------------------------------
# Class abilities (record feature di *_abilities_class.lst)
# ---------------------------------------------------------------------------


def _derive_class(key: str, tags, known_classes: set):
    """Classe di appartenenza: KEY `X ~ ...` con X classe nota, altrimenti
    TYPE `<X>ClassFeatures` (euristica dichiarata), altrimenti None."""
    if " ~ " in key:
        prefix = key.split(" ~ ", 1)[0]
        if prefix in known_classes:
            return prefix
    for k, v in tags:
        if k != "TYPE":
            continue
        for t in v.split("."):
            m = re.fullmatch(r"(.+)ClassFeatures", t)
            if m and m.group(1) in known_classes:
                return m.group(1)
    return None


def abilities_from_records(records, book: str, known_classes: set):
    """Record LST -> (entries feature di classe, stats).

    I record CATEGORY:Class (contenitori di classe, es. `Barbarian` e
    `Standard Barbarian`/`X ~ Standard Class`) NON sono feature: saltati e
    contati. Come per i feat: .MOD/.COPY/.FORGET ignorati (i BONUS dei .MOD
    non entrano, dichiarato), duplicati last-wins per KEY. DESC mai esportato.
    """
    by_key = {}
    order = []
    stats = {
        "duplicates_overridden": 0,
        "class_containers_skipped": 0,
        "prereq_coverage": {"covered": {}, "not_normalized": {}},
        "bonus": _empty_bonus_stats(),
    }
    for name, tags in records:
        if not name or name.endswith((".MOD", ".FORGET")) or ".COPY=" in name:
            continue
        category = _tag_value(tags, "CATEGORY") or ""
        key = _tag_value(tags, "KEY") or name
        if category.lower() == "class" or key.endswith(" ~ Standard Class"):
            stats["class_containers_skipped"] += 1
            continue
        nodes = prereq_tree(tags)
        _coverage_add(stats["prereq_coverage"], nodes)
        bonus = [parse_bonus_tag(v) for v in _tag_values(tags, "BONUS")]
        _bonus_stats_add(stats["bonus"], bonus)
        stack = _tag_value(tags, "STACK")
        if key in by_key:
            stats["duplicates_overridden"] += 1
        else:
            order.append(key)
        by_key[key] = {
            "name": name,
            "key": key,
            "source_book": book,
            "category": category or None,
            "types": (
                (_tag_value(tags, "TYPE") or "").split(".")
                if _tag_value(tags, "TYPE")
                else []
            ),
            "class": _derive_class(key, tags, known_classes),
            "multiple": _tag_value(tags, "MULT") == "YES",
            "stack": (stack == "YES") if stack else None,
            "choose": _tag_value(tags, "CHOOSE"),
            "prerequisites": nodes,
            "bonus": bonus,
            "source_page": _tag_value(tags, "SOURCEPAGE"),
        }
    return [by_key[k] for k in order], stats


# ---------------------------------------------------------------------------
# Build dei cataloghi
# ---------------------------------------------------------------------------


def _read_records(path: Path):
    return iter_lst_records(path.read_text(encoding="utf-8", errors="replace"))


def _known_classes(pcgen_root: Path, books=None) -> set:
    """Nomi di classe da tutti i classes.lst configurati (anche fuori dal
    filtro `books`: i MOD di un libro possono targettare classi di un altro)."""
    known = set()
    for book, cfg in BOOK_CLASS_FILES.items():
        if books is not None and book not in books:
            continue
        for rel in cfg["classes"]:
            path = pcgen_root / DATA_SUBDIR / cfg["dir"] / rel
            if not path.is_file():
                raise FileNotFoundError(f"file LST mancante: {path}")
            for entry in progression_from_classes_text(
                path.read_text(encoding="utf-8", errors="replace"), book
            ):
                known.add(entry["class"])
    return known


def _provenance(pcgen_root: Path, generated_by: str, books=None) -> dict:
    return {
        "source": (
            "PCGen data sets (github.com/PCGen/pcgen), "
            f"{DATA_SUBDIR}/roleplaying_game/*"
        ),
        "pcgen_commit": _pcgen_commit(pcgen_root),
        "generated_by": generated_by,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "license": LICENSE_TEXT,
        "desc_policy": DESC_POLICY,
        "books": {
            b: BOOKS[b]["title"]
            for b, cfg in BOOK_CLASS_FILES.items()
            if books is None or b in books
        },
    }


def build_progression(pcgen_root, books=None) -> dict:
    """Progressione per classe: righe livello dei classes.lst + righe MOD di
    abilities_class/abilities_globalvar. Grant fusi per classe, ordinati per
    (livello, kind, pool), deduplicati (contati)."""
    pcgen_root = Path(pcgen_root)
    known = _known_classes(pcgen_root)
    by_class: dict[str, dict] = {}
    counts, stats = {}, {}
    duplicates = 0
    for book, cfg in BOOK_CLASS_FILES.items():
        if books is not None and book not in books:
            continue
        book_grants = []
        for rel in cfg["classes"]:
            path = pcgen_root / DATA_SUBDIR / cfg["dir"] / rel
            if not path.is_file():
                raise FileNotFoundError(f"file LST mancante: {path}")
            for entry in progression_from_classes_text(
                path.read_text(encoding="utf-8", errors="replace"), book
            ):
                for grant in entry["grants"]:
                    book_grants.append({"class": entry["class"], **grant})
        book_mod_stats = _empty_mod_stats()
        for rel in cfg["mod_files"]:
            path = pcgen_root / DATA_SUBDIR / cfg["dir"] / rel
            if not path.is_file():
                raise FileNotFoundError(f"file LST mancante: {path}")
            grants, mod_stats = progression_from_mod_text(
                path.read_text(encoding="utf-8", errors="replace"), book, known
            )
            book_grants.extend(grants)
            for k, v in mod_stats.items():
                book_mod_stats[k] += v
        seen = set()
        classes_in_book = set()
        for grant in book_grants:
            cls = grant["class"]
            classes_in_book.add(cls)
            entry = by_class.setdefault(
                cls, {"class": cls, "source_books": [], "grants": []}
            )
            if book not in entry["source_books"]:
                entry["source_books"].append(book)
            gk = _grant_key(grant)
            key = (cls,) + gk
            if key in seen:
                duplicates += 1
                continue
            seen.add(key)
            entry["grants"].append(grant)
        counts[book] = len(classes_in_book)
        stats[book] = book_mod_stats
    for entry in by_class.values():
        # i pool-var senza gate PRECLASS hanno level None (dichiarato):
        # in coda, non mescolati ai grant con livello derivato
        entry["grants"].sort(
            key=lambda g: (
                g["level"] is None,
                g["level"] or 0,
                g["kind"],
                g.get("pool", ""),
                tuple(g.get("names", [])),
            )
        )
    stats["_duplicates_collapsed_across_books"] = duplicates
    return {
        "_provenance": _provenance(
            pcgen_root, "Master-DD-Taverna/tools/import_pcgen_classes.py", books
        ),
        "counts": counts,
        "stats": stats,
        "entries": sorted(by_class.values(), key=lambda e: e["class"]),
    }


def build_abilities(pcgen_root, books=None) -> dict:
    """Le class abilities (record feature) dei *_abilities_class.lst."""
    pcgen_root = Path(pcgen_root)
    known = _known_classes(pcgen_root)
    entries = []
    counts, stats = {}, {}
    for book, cfg in BOOK_CLASS_FILES.items():
        if books is not None and book not in books:
            continue
        book_records = []
        for rel in cfg["abilities"]:
            path = pcgen_root / DATA_SUBDIR / cfg["dir"] / rel
            if not path.is_file():
                raise FileNotFoundError(f"file LST mancante: {path}")
            book_records.extend(_read_records(path))
        book_entries, book_stats = abilities_from_records(book_records, book, known)
        entries.extend(book_entries)
        counts[book] = len(book_entries)
        stats[book] = book_stats
    return {
        "_provenance": _provenance(
            pcgen_root, "Master-DD-Taverna/tools/import_pcgen_classes.py", books
        ),
        "counts": counts,
        "stats": stats,
        "entries": entries,
    }


# ---------------------------------------------------------------------------
# Report e main
# ---------------------------------------------------------------------------


def _print_report(progression: dict, abilities: dict) -> None:
    commit = progression["_provenance"]["pcgen_commit"][:12]
    print(
        f"[progressione] {len(progression['entries'])} classi "
        f"(commit pcgen {commit})"
    )
    for book, n in progression["counts"].items():
        if n:
            print(f"  {book}: {n} classi")
    total_grants = sum(len(e["grants"]) for e in progression["entries"])
    pool_grants = sum(
        1 for e in progression["entries"] for g in e["grants"] if g["kind"] == "pool"
    )
    print(f"  grant: {total_grants} (di cui pool: {pool_grants})")
    dup = progression["stats"].get("_duplicates_collapsed_across_books", 0)
    if dup:
        print(f"  duplicati collassati cross-libro: {dup}")
    print(f"[abilities] {len(abilities['entries'])} feature di classe")
    for book, n in abilities["counts"].items():
        if n:
            print(f"  {book}: {n}")
    bonus = _empty_bonus_stats()
    for book_stats in abilities["stats"].values():
        bs = book_stats["bonus"]
        bonus["feats_with_bonus"] += bs["feats_with_bonus"]
        bonus["total_tags"] += bs["total_tags"]
        for group, n in bs["by_group"].items():
            bonus["by_group"][group] = bonus["by_group"].get(group, 0) + n
        for k in ("literal_value", "with_type", "recognized", "unrecognized"):
            bonus[k] += bs[k]
    total = bonus["total_tags"] or 1
    print(
        f"  BONUS: {bonus['total_tags']} tag su {bonus['feats_with_bonus']} feature | "
        f"valore letterale {bonus['literal_value']} ({bonus['literal_value'] / total:.0%}) | "
        f"non riconosciuti {bonus['unrecognized']} ({bonus['unrecognized'] / total:.1%})"
    )
    skipped = sum(
        s.get("class_containers_skipped", 0) for s in abilities["stats"].values()
    )
    print(f"  contenitori CATEGORY:Class saltati: {skipped}")


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

    progression = build_progression(pcgen_root)
    abilities = build_abilities(pcgen_root)
    _print_report(progression, abilities)

    if args.report_only:
        return 0
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for kind, payload in (("progression", progression), ("abilities", abilities)):
        path = out_dir / OUTPUT_FILES[kind]
        path.write_text(
            json.dumps(payload, indent=1, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        print(f"scritto {path} ({len(payload['entries'])} voci)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
