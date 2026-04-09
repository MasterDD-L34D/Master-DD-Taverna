"""Utility per popolare il database locale di build MinMax Builder."""

from __future__ import annotations

import argparse
import hashlib
import asyncio
import json
import logging
import os
import random
import shutil
import textwrap
import re
from fnmatch import fnmatchcase
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from itertools import islice, product
from pathlib import Path
from typing import Any, Iterable, List, Mapping, MutableMapping, Sequence
from email.utils import parsedate_to_datetime

DEFAULT_REFERENCE_DIR = Path(__file__).resolve().parent.parent / "data" / "reference"
REFERENCE_SCHEMA = "reference_catalog.schema.json"

logger = logging.getLogger(__name__)

import yaml
from jinja2 import BaseLoader, ChainableUndefined
from jinja2.nativetypes import NativeEnvironment

import httpx
from jsonschema import Draft202012Validator, RefResolver
from jsonschema.exceptions import ValidationError

# Alcuni ambienti (o versioni precedenti dello script) si aspettano un helper
# is_aon_url in utils.aon_detector; gestiamo la mancanza con un fallback locale
# per mantenere la compatibilità e permettere l'esecuzione dello script senza
# dipendenze aggiuntive.
try:  # pragma: no cover - percorso solo in ambienti con utils disponibile
    from utils.aon_detector import is_aon_url  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - usato in CI/ambienti vanilla
    def is_aon_url(url: str) -> bool:
        return "aonprd.com" in (url or "").lower()

# Lista di classi PF1e target supportate dal builder
PF1E_CLASSES: List[str] = [
    "Alchemist",
    "Arcanist",
    "Barbarian",
    "Bard",
    "Bloodrager",
    "Brawler",
    "Cavalier",
    "Cleric",
    "Druid",
    "Fighter",
    "Gunslinger",
    "Hunter",
    "Inquisitor",
    "Investigator",
    "Kineticist",
    "Magus",
    "Medium",
    "Mesmerist",
    "Monk",
    "Ninja",
    "Occultist",
    "Oracle",
    "Paladin",
    "Psychic",
    "Ranger",
    "Rogue",
    "Samurai",
    "Shaman",
    "Skald",
    "Slayer",
    "Sorcerer",
    "Spiritualist",
    "Summoner",
    "Swashbuckler",
    "Warpriest",
    "Witch",
    "Wizard",
]

CORE_CLASSES: set[str] = {
    "Barbarian",
    "Bard",
    "Cleric",
    "Druid",
    "Fighter",
    "Monk",
    "Paladin",
    "Ranger",
    "Rogue",
    "Sorcerer",
    "Wizard",
}

# Pool di razze comuni/featured PF1e usate come fallback quando si vuole
# evitare duplicati automaticamente (può essere sovrascritto da CLI).
PF1E_RACES: Sequence[str] = (
    # Core races
    "Dwarf",
    "Elf",
    "Gnome",
    "Half-Elf",
    "Half-Orc",
    "Halfling",
    "Human",
    # Featured races
    "Aasimar",
    "Catfolk",
    "Dhampir",
    "Drow",
    "Fetchling",
    "Goblin",
    "Hobgoblin",
    "Ifrit",
    "Kobold",
    "Orc",
    "Oread",
    "Ratfolk",
    "Sylph",
    "Tengu",
    "Tiefling",
    "Undine",
    # Uncommon races
    "Changeling",
    "Gillman",
    "Grippli",
    "Kitsune",
    "Merfolk",
    "Nagaji",
    "Samsaran",
    "Strix",
    "Suli",
    "Svirfneblin",
    "Vanara",
    "Vishkanya",
    "Wayang",
    "Wyvaran",
    # Other player races from d20pfsrd
    "Advanced Android",
    "Android",
    "Aphorite",
    "Automaton",
    "Centaur",
    "Duergar",
    "Gathlain",
    "Ghoran",
    "Kasatha",
    "Lashunta",
    "Minotaur",
    "Oni-Spawn",
    "Samsaran (Reborn)",
    "Shabti",
    "Skinwalker",
    "Trox",
    "Wayang (Umbral)",
    "Wyrwood",
)

DEFAULT_MODE = "full-pg"
DEFAULT_BASE_URL = "http://localhost:8000"
DEFAULT_SPEC_FILE = (
    Path(__file__).resolve().parent.parent / "docs/examples/pg_variants.yml"
)
AUTH_BACKOFF_SECONDS = int(os.environ.get("AUTH_BACKOFF_SECONDS", "60"))
BUILD_AUDIT_PATH = Path("data/audit/build_events.jsonl")
MODULE_ENDPOINT = "/modules/minmax_builder.txt"
MODULE_DUMP_ENDPOINT = "/modules/{name}"
MODULE_META_ENDPOINT = "/modules/{name}/meta"
MODULE_LIST_ENDPOINT = "/modules"

SCHEMAS_DIR = Path(__file__).resolve().parent.parent / "schemas"
BUILD_SCHEMA_MAP = {
    "core": "build_core.schema.json",
    "extended": "build_extended.schema.json",
    "full-pg": "build_full_pg.schema.json",
}
MODULE_SCHEMA = "module_metadata.schema.json"

# Moduli "grezzi" utili per generare schede e flussi completi
DEFAULT_MODULE_TARGETS: Sequence[str] = (
    "base_profile.txt",
    "Taverna_NPC.txt",
    "narrative_flow.txt",
    "scheda_pg_markdown_template.md",
    "adventurer_ledger.txt",
)

# Moduli che vanno inclusi nel payload della scheda (solo il template da compilare)
SHEET_MODULE_TARGETS: Sequence[str] = ("scheda_pg_markdown_template.md",)


def now_iso_utc() -> str:
    return (
        datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    )


def log_build_event(event: Mapping[str, object]) -> None:
    """Append an audit event to the build_events log."""

    try:
        BUILD_AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
        with BUILD_AUDIT_PATH.open("a", encoding="utf-8") as fp:
            fp.write(json.dumps(event, ensure_ascii=False) + "\n")
    except OSError:
        logging.exception("Impossibile scrivere su %s", BUILD_AUDIT_PATH)


@dataclass(slots=True)
class BuildRequest:
    class_name: str
    mode: str = DEFAULT_MODE
    stub: bool = True
    level: int | None = None
    filename_prefix: str | None = None
    spec_id: str | None = None
    race: str | None = None
    archetype: str | None = None
    model: str | None = None
    background: str | None = None
    combo_id: str | None = None
    feat_plan: Sequence[str] | None = None
    raw_citations: Sequence[str] | None = None
    stacking_limits: Sequence[str] | None = None
    query_params: Mapping[str, object] = field(default_factory=dict)
    body_params: Mapping[str, object] = field(default_factory=dict)
    level_checkpoints: Sequence[int] = field(default_factory=lambda: (1, 5, 10))

    def http_method(self) -> str:
        return "POST" if self.body_params else "GET"

    def api_params(self, *, level: int | None = None) -> dict[str, object]:
        """Build query params for the builder API ensuring race/archetype/model are passed."""
        params: dict[str, object] = {
            "mode": self.mode,
            "class": self.class_name,
            "stub": self.stub,
        }
        if level is not None:
            params["level"] = level
        if self.race:
            params.setdefault("race", self.race)
        if self.archetype:
            params.setdefault("archetype", self.archetype)
        if self.model:
            params.setdefault("model", self.model)
        if self.query_params:
            params.update(
                {str(k): v for k, v in self.query_params.items() if v is not None}
            )
        return params

    def output_name(self) -> str:
        if self.filename_prefix:
            return self.filename_prefix
        if self.spec_id:
            return slugify(self.spec_id)
        return slugify(self.class_name)

    def metadata(self) -> Mapping[str, object | None]:
        resolved_race = (
            self.race
            or self.query_params.get("race")
            or self.body_params.get("race")
            or "Human"
        )

        resolved_archetype = (
            self.archetype
            or self.query_params.get("archetype")
            or self.query_params.get("model")
            or self.body_params.get("archetype")
            or self.body_params.get("model")
            or self.model
            or "Base"
        )

        resolved_background = (
            self.background
            or self.body_params.get("background")
            or self.body_params.get("background_hooks")
        )

        resolved_spec_id = self.spec_id or slugify(
            "_".join(
                str(part)
                for part in (
                    self.class_name,
                    resolved_race,
                    resolved_archetype,
                    resolved_background,
                )
                if part
            )
        )

        metadata = {
            "class": self.class_name,
            "race": resolved_race,
            "archetype": resolved_archetype,
            "mode": self.mode,
            "mode_normalized": normalize_mode(self.mode),
            "spec_id": resolved_spec_id,
            "model": self.model,
            "background": resolved_background,
            "level": self.level,
            "level_checkpoints": list(self.level_checkpoints),
        }

        if self.combo_id:
            metadata["combo_id"] = self.combo_id
        if self.feat_plan:
            metadata["feat_plan"] = list(self.feat_plan)
        if self.raw_citations:
            metadata["raw_citations"] = list(self.raw_citations)
        if self.stacking_limits:
            metadata["stacking_limits"] = list(self.stacking_limits)

        return metadata


class BuildFetchError(Exception):
    """Raised when the build API does not return usable data."""

    def __init__(
        self, message: str, *, completeness_errors: Sequence[str] | None = None
    ) -> None:
        super().__init__(message)
        self.completeness_errors = (
            list(completeness_errors) if completeness_errors is not None else None
        )


def slugify(name: str) -> str:
    """Filesystem-friendly slug."""
    text = str(name).strip().lower()
    if not text:
        return ""
    text = re.sub(r"\s+", "_", text)
    text = re.sub(r"[^\w-]+", "_", text, flags=re.UNICODE)
    text = re.sub(r"_+", "_", text)
    text = re.sub(r"-+", "-", text)
    return text.strip("_-")


def _record_status_from_result(status: str | None) -> str:
    status = (status or "").lower()
    if status in {"ok", "cached"}:
        return "validated"
    if status in {"pruned", "archived"}:
        return "archived"
    return "draft"


def _issues_for_record(audit: object | None, record_status: object | None) -> list[str]:
    issues: list[str] = []
    if not (isinstance(audit, Sequence) and not isinstance(audit, (str, bytes))):
        issues.append("missing_audit")
    if not (isinstance(record_status, str) and record_status.strip()):
        issues.append("missing_record_status")
    return issues


def _ensure_record_metadata(
    payload: MutableMapping[str, object] | None,
    *,
    actor: str,
    action: str,
    record_status: str,
    note: str | None = None,
    checkpoint: int | None = None,
    source: str | None = None,
) -> None:
    if not isinstance(payload, MutableMapping):
        return

    payload.setdefault("record_status", record_status)
    payload.setdefault("is_deleted", False)
    payload.setdefault("deleted_at", None)

    audit_log = payload.get("audit")
    if not (isinstance(audit_log, list)):
        audit_log = []

    audit_entry: dict[str, object] = {
        "timestamp": now_iso_utc(),
        "actor": actor,
        "action": action,
        "status": record_status,
    }
    if note:
        audit_entry["note"] = note
    if checkpoint is not None:
        audit_entry["checkpoint"] = checkpoint
    if source:
        audit_entry["source"] = source

    audit_log.append(audit_entry)
    payload["audit"] = audit_log


def _normalize_module_meta(
    meta: Mapping[str, object] | None,
    *,
    record_status: str,
    actor: str,
    note: str | None = None,
) -> dict[str, object]:
    normalized = dict(meta or {})
    normalized.setdefault("record_status", record_status)
    normalized.setdefault("is_deleted", False)
    normalized.setdefault("deleted_at", None)

    audit_log = normalized.get("audit")
    if not isinstance(audit_log, list):
        audit_log = []

    audit_entry: dict[str, object] = {
        "timestamp": now_iso_utc(),
        "actor": actor,
        "action": "module_indexed",
        "status": record_status,
    }
    if note:
        audit_entry["note"] = note
    audit_log.append(audit_entry)
    normalized["audit"] = audit_log

    return normalized


def _normalize_catalog_key(name: object | None) -> str:
    if name is None:
        return ""
    return slugify(str(name))


def _string_name(value: object | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, Mapping):
        for key in ("name", "nome", "label", "item"):
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
    return None


def load_reference_catalog(
    reference_dir: Path | None = None, *, strict: bool = False
) -> dict[str, dict[str, Mapping[str, object]]]:
    directory = reference_dir or DEFAULT_REFERENCE_DIR
    catalog: dict[str, dict[str, Mapping[str, object]]] = {}
    if not directory.exists():
        return catalog

    for filename in ("spells.json", "feats.json", "items.json"):
        path = directory / filename
        if not path.is_file():
            continue
        try:
            entries = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:  # pragma: no cover - defensive log
            logging.warning(
                "Impossibile leggere il catalogo di riferimento %s: %s", path, exc
            )
            if strict:
                raise
            continue
        validate_with_schema(REFERENCE_SCHEMA, entries, filename, strict=strict)
        normalized: dict[str, Mapping[str, object]] = {}
        for entry in entries:
            if not isinstance(entry, Mapping):
                continue
            name = _string_name(entry.get("name"))
            if not name:
                continue
            normalized[_normalize_catalog_key(name)] = entry
        catalog[filename.removesuffix(".json")] = normalized

    return catalog


def load_reference_manifest(
    reference_dir: Path | None = None,
) -> Mapping[str, object]:
    directory = reference_dir or DEFAULT_REFERENCE_DIR
    manifest_path = directory / "manifest.json"
    if not manifest_path.is_file():
        return {}

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - defensive log
        logging.warning("Impossibile leggere il manifest del catalogo: %s", exc)
        return {}

    if not isinstance(manifest, Mapping):
        return {}

    return manifest


_reference_catalog_cache: dict[
    tuple[str, bool],
    dict[str, dict[str, Mapping[str, object]]],
] = {}
_reference_manifest_cache: dict[str, Mapping[str, object]] = {}


def get_reference_catalog(
    reference_dir: Path | None = None, *, strict: bool = False
) -> dict[str, dict[str, Mapping[str, object]]]:
    directory = (reference_dir or DEFAULT_REFERENCE_DIR).resolve()
    key = (str(directory), bool(strict))
    cached = _reference_catalog_cache.get(key)
    if cached is not None:
        return cached
    catalog = load_reference_catalog(directory, strict=strict)
    _reference_catalog_cache[key] = catalog
    return catalog


def get_reference_manifest(reference_dir: Path | None = None) -> Mapping[str, object]:
    directory = (reference_dir or DEFAULT_REFERENCE_DIR).resolve()
    key = str(directory)
    cached = _reference_manifest_cache.get(key)
    if cached is not None:
        return cached
    manifest = load_reference_manifest(directory)
    _reference_manifest_cache[key] = manifest
    return manifest


def _reference_url_coverage(
    catalog: Mapping[str, Mapping[str, Mapping[str, object]]],
) -> dict[str, object]:
    coverage = {
        "total": 0,
        "aon": 0,
        "d20_only": 0,
        "missing_aon_entries": [],
    }

    for category, entries in catalog.items():
        for normalized_name, entry in entries.items():
            coverage["total"] += 1
            urls = entry.get("reference_urls") if isinstance(entry, Mapping) else []
            urls = (
                urls
                if isinstance(urls, Sequence) and not isinstance(urls, (str, bytes))
                else []
            )
            normalized_urls = [str(url).strip() for url in urls if str(url).strip()]
            has_aon = any(is_aon_url(url) for url in normalized_urls)
            has_d20 = any("d20pfsrd" in url for url in normalized_urls)

            if has_aon:
                coverage["aon"] += 1
            if has_d20 and not has_aon:
                coverage["d20_only"] += 1
                display_name = (
                    entry.get("name") if isinstance(entry, Mapping) else normalized_name
                )
                coverage["missing_aon_entries"].append(f"{category}:{display_name}")

    total = coverage["total"] or 1
    coverage["aon_ratio"] = round(coverage["aon"] / total, 3)
    coverage["status"] = "ok" if not coverage["missing_aon_entries"] else "invalid"

    return coverage


def _collect_catalog_entries(
    sheet_payload: Mapping[str, object],
) -> dict[str, list[str]]:
    def _extract_sequence_names(value: object) -> list[str]:
        names: list[str] = []
        if isinstance(value, Mapping):
            for entry in value.values():
                names.extend(_extract_sequence_names(entry))
        elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
            for entry in value:
                candidate = _string_name(entry)
                if candidate:
                    names.append(candidate)
        else:
            candidate = _string_name(value)
            if candidate:
                names.append(candidate)
        return names

    catalog_entries = {
        "spells": [],
        "feats": [],
        "items": [],
    }

    # Prefer explicit spell lists (if present) and fall back to spell_levels.
    magia = sheet_payload.get("magia")
    if isinstance(magia, Mapping):
        for key in ("spell_list", "spells_prepared", "incantesimi", "spells"):
            value = magia.get(key)
            if value:
                catalog_entries["spells"].extend(_extract_sequence_names(value))

    spell_levels = sheet_payload.get("spell_levels")
    if spell_levels:
        catalog_entries["spells"].extend(_extract_sequence_names(spell_levels))

    for key in ("talenti", "feats", "talents"):
        value = sheet_payload.get(key)
        if value:
            catalog_entries["feats"].extend(_extract_sequence_names(value))

    for key in ("equipaggiamento", "inventario", "equipment", "inventory", "items"):
        value = sheet_payload.get(key)
        if value:
            catalog_entries["items"].extend(_extract_sequence_names(value))

    return catalog_entries


def validate_sheet_with_catalog(
    sheet_payload: Mapping[str, object] | None,
    catalog: Mapping[str, Mapping[str, Mapping[str, object]]],
    ledger: Mapping[str, object] | None = None,
    catalog_manifest: Mapping[str, object] | None = None,
) -> tuple[list[str], dict[str, list[str]]]:
    if not isinstance(sheet_payload, Mapping):
        return [], {}

    available = _collect_catalog_entries(sheet_payload)
    ledger_entries = _collect_ledger_entries(ledger)

    normalized_sheet = {
        category: {_normalize_catalog_key(name): name for name in names}
        for category, names in available.items()
    }
    normalized_ledger = {
        category: {_normalize_catalog_key(name): name for name in names}
        for category, names in ledger_entries.items()
    }

    all_selected = set()
    for names in normalized_sheet.values():
        all_selected.update(names)
    for names in normalized_ledger.values():
        all_selected.update(names)

    known_catalog_keys = set()
    for entries in catalog.values():
        if isinstance(entries, Mapping):
            known_catalog_keys.update(entries.keys())

    missing: list[str] = []
    ledger_missing: list[str] = []
    prerequisite_violations: list[str] = []
    ledger_mismatch: list[str] = []

    def _collect_missing(
        normalized: Mapping[str, str], category: str, target: list[str]
    ) -> None:
        known_entries = catalog.get(category, {})
        for normalized_name, raw_name in normalized.items():
            entry = known_entries.get(normalized_name)
            if not entry:
                target.append(f"{category}:{raw_name}")
                continue
            prerequisites = entry.get("prerequisites")
            if isinstance(prerequisites, Sequence) and not isinstance(
                prerequisites, (str, bytes)
            ):
                for prerequisite in prerequisites:
                    normalized_prerequisite = _normalize_catalog_key(prerequisite)
                    if not normalized_prerequisite:
                        continue
                    if normalized_prerequisite not in known_catalog_keys:
                        # Not verifiable (ability score thresholds, class names, BAB, etc.)
                        continue
                    if normalized_prerequisite not in all_selected:
                        display_name = entry.get("name") or raw_name
                        prerequisite_violations.append(
                            f"{display_name}: {prerequisite}"
                        )

    for category, names in normalized_sheet.items():
        _collect_missing(names, category, missing)

    for category, names in normalized_ledger.items():
        _collect_missing(names, category, ledger_missing)
        sheet_names = normalized_sheet.get(category, {})
        for normalized_name, raw_name in names.items():
            if normalized_name not in sheet_names:
                ledger_mismatch.append(raw_name)

    errors: list[str] = []
    metadata: dict[str, list[str]] = {}
    version = None
    if isinstance(catalog_manifest, Mapping):
        version = catalog_manifest.get("version")
    if missing:
        errors.append(
            "Elementi non presenti nel catalogo: " + ", ".join(sorted(set(missing)))
        )
        metadata["missing_catalog_entries"] = sorted(set(missing))
    if ledger_missing:
        errors.append(
            "Voci ledger fuori catalogo: " + ", ".join(sorted(set(ledger_missing)))
        )
        metadata["ledger_unknown_entries"] = sorted(set(ledger_missing))
    if prerequisite_violations:
        errors.append(
            "Prerequisiti catalogo non soddisfatti: "
            + ", ".join(sorted(set(prerequisite_violations)))
        )
        metadata["prerequisite_violations"] = sorted(set(prerequisite_violations))
    if ledger_mismatch:
        errors.append(
            "Ledger e scheda disallineati: " + ", ".join(sorted(set(ledger_mismatch)))
        )
        metadata["ledger_sheet_mismatches"] = sorted(set(ledger_mismatch))
    if version:
        metadata["catalog_version"] = [str(version)]

    return errors, metadata


def _collect_ledger_entries(
    ledger: Mapping[str, object] | None,
) -> dict[str, list[str]]:
    if not isinstance(ledger, Mapping):
        return {"items": []}

    names: list[str] = []

    def _extract_named_entries(value: object) -> list[str]:
        collected: list[str] = []
        if value is None:
            return collected

        if isinstance(value, Mapping):
            candidate = _string_name(value)
            if candidate:
                collected.append(candidate)
            for child in value.values():
                if isinstance(child, (Mapping, Sequence)) and not isinstance(
                    child, (str, bytes)
                ):
                    collected.extend(_extract_named_entries(child))
            return collected

        if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
            for item in value:
                collected.extend(_extract_named_entries(item))
            return collected

        candidate = _string_name(value)
        if candidate:
            collected.append(candidate)
        return collected

    # Prefer itemized sections; ignore generic financial transaction labels (movimenti/voce/note).
    for container_key in (
        "equipaggiamento",
        "inventario",
        "items",
        "equipment",
        "inventory",
        "parcels",
        "crafting",
        "ledger_parcels",
        "ledger_crafting",
        "loot",
        "treasure",
        "acquisti",
        "purchases",
    ):
        value = ledger.get(container_key)
        if value:
            names.extend(_extract_named_entries(value))

    # Fallback: explicit item/name fields inside entries/transactions only (avoid movimenti stub labels).
    entries: list[object] = []
    for key in ("entries", "transactions"):
        value = ledger.get(key)
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
            entries.extend(value)

    for entry in entries:
        if not isinstance(entry, Mapping):
            continue
        for field in ("item", "nome", "name", "label", "oggetto"):
            candidate = _string_name(entry.get(field))
            if candidate:
                names.append(candidate)

    # De-duplicate while preserving order.
    seen: set[str] = set()
    unique: list[str] = []
    for name in names:
        normalized = _normalize_catalog_key(name)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        unique.append(name)

    return {"items": unique}


def catalog_combo_candidates(
    catalog: Mapping[str, Mapping[str, Mapping[str, object]]],
    *,
    max_entries: int = 2,
    class_name: str | None = None,
    archetype: str | None = None,
) -> list[dict[str, object]]:
    """Estrae combinazioni dal catalogo dando precedenza a tag rilevanti.

    I talenti e gli oggetti vengono ordinati privilegiando tag che matchano
    la classe o l'archetipo richiesto, seguiti da tag granulari come slot,
    scuola ed eventuale tipo di danno. Questo consente a ``--suggest-combos``
    di proporre varianti più aderenti al ruolo (es. un ranger con talenti da
    tiro e oggetti da slot corretti o un magus con bonus alle scuole arcane
    usate dalla build).
    """

    def _score_entry(entry: Mapping[str, object]) -> tuple[int, str]:
        tags = entry.get("tags") if isinstance(entry.get("tags"), Sequence) else []
        normalized_tags = [
            str(tag).strip().lower() for tag in tags if isinstance(tag, str)
        ]
        score = 0

        has_class_tag = any(tag.startswith("class:") for tag in normalized_tags)
        has_archetype_tag = any(tag.startswith("archetype:") for tag in normalized_tags)

        if class_name:
            class_tag = f"class:{class_name.strip().lower()}"
            if class_tag in normalized_tags:
                score += 4
            elif has_class_tag:
                score += 1

        if archetype:
            archetype_tag = f"archetype:{str(archetype).strip().lower()}"
            if archetype_tag in normalized_tags:
                score += 3
            elif has_archetype_tag:
                score += 1
        elif has_archetype_tag:
            score += 1

        if any(tag.startswith("damage:") for tag in normalized_tags):
            score += 2
        if any(tag.startswith("slot:") for tag in normalized_tags):
            score += 2
        if any(tag.startswith("school:") for tag in normalized_tags):
            score += 1
        if any(tag.startswith("attack:") for tag in normalized_tags):
            score += 1

        name = _string_name(entry.get("name")) or ""
        return score, name

    def _top_entries(catalog_entries: Mapping[str, Mapping[str, object]]) -> list[str]:
        scored: list[tuple[int, str]] = []
        for entry in catalog_entries.values():
            if not isinstance(entry, Mapping):
                continue
            name = _string_name(entry.get("name"))
            if not name:
                continue
            score, normalized_name = _score_entry(entry)
            scored.append((score, normalized_name))
        scored.sort(key=lambda item: (-item[0], item[1]))
        return [name for _, name in scored[:max_entries] if name]

    feats_catalog = catalog.get("feats", {})
    items_catalog = catalog.get("items", {})
    feat_names = _top_entries(feats_catalog)
    item_names = _top_entries(items_catalog)

    archetype_candidates: list[str | None] = [archetype] if archetype else [None]
    for entry in feats_catalog.values():
        tags = entry.get("tags") if isinstance(entry.get("tags"), Sequence) else []
        for tag in tags:
            if isinstance(tag, str) and tag.startswith("archetype:"):
                archetype_candidates.append(tag.split(":", 1)[1])
    archetype_candidates = [
        candidate
        for candidate in archetype_candidates
        if candidate is None or _string_name(candidate)
    ][: max_entries + 1]

    combos: list[dict[str, object]] = []
    for feat_name, item_name in product(feat_names or [None], item_names or [None]):
        for archetype_candidate in archetype_candidates:
            combos.append(
                {
                    "archetype": _string_name(archetype_candidate),
                    "feats": [name for name in (feat_name,) if name],
                    "items": [name for name in (item_name,) if name],
                }
            )

    return combos


def normalize_mode(mode: str) -> str:
    candidate = str(mode or DEFAULT_MODE).strip().lower()
    return "core" if candidate.startswith("core") else "extended"


def normalize_race(race: str | None) -> str | None:
    if race is None:
        return None
    return str(race).strip().lower()


def load_race_inventory(path: Path | None) -> list[str]:
    if not path:
        return []

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        logging.info("Race inventory non trovato in %s", path)
        return []
    except Exception as exc:  # pragma: no cover - log only
        logging.warning("Impossibile leggere %s: %s", path, exc)
        return []

    if isinstance(data, list):
        return [str(item) for item in data]

    races = data.get("races") if isinstance(data, Mapping) else None
    if isinstance(races, Mapping):
        return [str(name) for name in races.keys()]
    if isinstance(races, list):
        return [str(item.get("name", item)) for item in races]

    return []


def assign_missing_races(
    requests: Sequence[BuildRequest],
    race_inventory: Sequence[str],
    *,
    prefer_unused_race: bool = False,
    race_pool: Sequence[str] | None = None,
) -> list[BuildRequest]:
    used_normalized = {
        race for race in (normalize_race(r) for r in race_inventory) if race
    }
    pool = [race for race in (race_pool or []) if race]
    available_pool = [
        race for race in pool if normalize_race(race) not in used_normalized
    ]

    updated: list[BuildRequest] = []
    for request in requests:
        current_race = request.race or request.query_params.get("race")
        normalized_current = normalize_race(current_race)
        if normalized_current:
            used_normalized.add(normalized_current)
            updated.append(request)
            continue

        if prefer_unused_race and available_pool:
            next_race = available_pool.pop(0)
            used_normalized.add(normalize_race(next_race))
            merged_query = dict(request.query_params)
            merged_query.setdefault("race", next_race)
            updated.append(replace(request, race=next_race, query_params=merged_query))
        else:
            updated.append(request)

    return updated


def export_race_inventory(
    build_dir: Path, output_path: Path, *, race_pool: Sequence[str] | None = None
) -> Mapping[str, object]:
    from collections import Counter

    counter: Counter[str] = Counter()
    for json_file in build_dir.rglob("*.json"):
        try:
            data = json.loads(json_file.read_text(encoding="utf-8"))
        except Exception:
            continue

        race = (
            data.get("request", {}).get("race")
            or data.get("metadata", {}).get("race")
            or data.get("query_params", {}).get("race")
            or data.get("body_params", {}).get("race")
        )
        if race:
            counter[str(race).strip()] += 1

    races = [{"name": name, "count": count} for name, count in sorted(counter.items())]

    used_normalized = {normalize_race(name) for name in counter.keys() if name}
    preferred_pool = list(race_pool or [])
    unused_preferred = [
        race for race in preferred_pool if normalize_race(race) not in used_normalized
    ]

    payload = {"generated_at": now_iso_utc(), "races": races}
    if unused_preferred:
        payload["unused_preferred_races"] = unused_preferred

    output_path.parent.mkdir(parents=True, exist_ok=True)
    write_json(output_path, payload)
    logging.info("Inventario razze salvato in %s", output_path)
    return payload


def export_build_reports(
    build_dir: Path,
    reports_dir: Path,
    *,
    module_dir: Path | None = None,
    build_index_path: Path | None = None,
    module_index_path: Path | None = None,
    invalid_archive_dir: Path | None = None,
) -> Mapping[str, Path]:
    """Generate and persist coverage reports for local builds and modules."""

    reports_dir.mkdir(parents=True, exist_ok=True)

    review_path = reports_dir / "build_review.json"
    review_local_database(
        build_dir,
        module_dir or build_dir,
        build_index_path=build_index_path,
        module_index_path=module_index_path,
        output_path=review_path,
    )

    analysis_path = reports_dir / "index_analysis.json"
    build_index = build_index_path or Path("src/data/build_index.json")
    module_index = module_index_path or Path("src/data/module_index.json")
    analysis_payload = analyze_indices(
        build_index,
        module_index,
        archive_dir=invalid_archive_dir,
    )
    write_json(analysis_path, analysis_payload)

    return {"review": review_path, "index_analysis": analysis_path}


def expected_step_total_for_mode(mode: str) -> int:
    normalized = normalize_mode(mode)
    return 8 if normalized == "core" else 16


def ensure_output_dirs(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)


def _normalize_mapping(data: Mapping | None) -> Mapping[str, object]:
    return {str(key): value for key, value in (data or {}).items() if value is not None}


def _normalize_levels(
    levels: Sequence[int] | None, fallback: Sequence[int]
) -> list[int]:
    normalized: list[int] = []
    for level in levels or []:
        try:
            coerced = int(level)
        except (TypeError, ValueError):
            continue
        if coerced <= 0 or coerced in normalized:
            continue
        normalized.append(coerced)
    return normalized or list(fallback)


def _coerce_catalog_version(*values: object) -> str | None:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
            for candidate in value:
                if isinstance(candidate, str) and candidate.strip():
                    return candidate.strip()
    return None


def _is_placeholder(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        lowered = value.strip().lower()
        if "x-truncated=true" in lowered or "contenuto troncato" in lowered:
            return True
        if lowered.startswith(("n/d", "nd", "n/a", "na")):
            return True
        return not lowered or "stub" in lowered or lowered in {"todo", "tbd"}
    if isinstance(value, Mapping):
        return all(_is_placeholder(v) for v in value.values())
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return all(_is_placeholder(v) for v in value)
    return False


def _merge_prefer_existing(
    target: MutableMapping[str, object], *sources: Mapping
) -> MutableMapping[str, object]:
    for source in sources:
        if not isinstance(source, Mapping):
            continue
        for key, value in source.items():
            if _is_placeholder(value):
                continue
            existing = target.get(key)
            if isinstance(existing, Mapping) and isinstance(value, Mapping):
                target[key] = _merge_prefer_existing(dict(existing), value)
            elif _is_placeholder(existing):
                target[key] = value
            elif key not in target:
                target[key] = value
    return target


def _first_non_placeholder(*values: object) -> object | None:
    for value in values:
        if not _is_placeholder(value):
            return value
    return None


def _merge_unique_list(
    existing: Sequence | None, *sources: Sequence | None
) -> list[object]:
    merged: list[object] = []
    if isinstance(existing, Sequence) and not isinstance(existing, (str, bytes)):
        merged.extend(existing)
    for source in sources:
        if not isinstance(source, Sequence) or isinstance(source, (str, bytes)):
            continue
        for item in source:
            if item not in merged:
                merged.append(item)
    return merged


def _has_content(value: object) -> bool:
    if value is None:
        return False
    if _is_placeholder(value):
        return False
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, Mapping):
        return any(_has_content(v) for v in value.values())
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return any(_has_content(v) for v in value)
    return True


_local_modules_cache: dict[tuple[str, ...], Mapping[str, str]] = {}


def _load_local_modules(module_names: Sequence[str]) -> Mapping[str, str]:
    key = tuple(module_names)
    cached = _local_modules_cache.get(key)
    if cached is not None:
        return cached

    candidates = [
        Path("src/data/modules"),
        Path("src/modules"),
        Path("modules"),
    ]
    loaded: dict[str, str] = {}
    for name in module_names:
        if name in loaded:
            continue
        for base_path in candidates:
            path = base_path / name
            if path.is_file():
                loaded[name] = path.read_text(encoding="utf-8")
                break
    _local_modules_cache[key] = loaded
    return loaded


def _style_hint(label: object) -> str | None:
    return None if label is None else str(label)


def _get_total_level(classes: Sequence | None) -> int | None:
    total = 0
    for cls in classes or []:
        if isinstance(cls, Mapping):
            level = cls.get("livelli") or cls.get("levels") or cls.get("level")
        else:
            level = cls
        if level is None:
            continue
        try:
            total += int(level)
        except (TypeError, ValueError):
            continue
    return total if total > 0 else None


def _lookup_meta_badges(*_: object, **__: object) -> str | None:
    return None


def _rules_status_text(*_: object, **__: object) -> str | None:
    return None


def _source_mix_summary(*_: object, **__: object) -> str | None:
    return None


def _coerce_number(value: object, default: object | None = None) -> object:
    if isinstance(value, (int, float)):
        return value
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        try:
            return float(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return default


def _truncate_sequence_by_level(
    entries: Sequence | None, target_level: int | None
) -> list[object] | None:
    if target_level is None:
        return None
    if not isinstance(entries, Sequence) or isinstance(entries, (str, bytes)):
        return None

    kept: list[object] = []
    current_level = 0

    for entry in entries:
        if isinstance(entry, Mapping):
            absolute_level = _coerce_number(entry.get("livello"))
            if isinstance(absolute_level, (int, float)):
                try:
                    coerced = int(absolute_level)
                except (TypeError, ValueError):
                    coerced = None
                if coerced is not None:
                    if coerced > target_level:
                        break
                    kept.append(entry)
                    current_level = max(current_level, coerced)
                    continue

        level_increment: int | None = None
        if isinstance(entry, Mapping):
            for classes_key in ("classi", "classes"):
                if classes_key in entry:
                    level_increment = _get_total_level(entry.get(classes_key))
                    break
            if level_increment is None:
                level_increment = _coerce_number(
                    entry.get("livello") or entry.get("level")
                )

        try:
            increment = int(level_increment) if level_increment is not None else 1
        except (TypeError, ValueError):
            increment = 1

        if increment <= 0:
            increment = 1

        if current_level + increment > target_level:
            break

        kept.append(entry)
        current_level += increment

        if current_level >= target_level:
            break

    return kept


_sheet_template_cache: dict[str, object] = {}


_sheet_template_env = NativeEnvironment(
    loader=BaseLoader(),
    autoescape=False,
    undefined=ChainableUndefined,
    trim_blocks=True,
    lstrip_blocks=True,
)
_sheet_template_env.globals.update(
    style_hint=_style_hint,
    get_total_level=_get_total_level,
    lookup_meta_badges=_lookup_meta_badges,
    rules_status_text=_rules_status_text,
    source_mix_summary=_source_mix_summary,
)


def _render_sheet_template(template_text: str, context: Mapping[str, object]) -> str:
    cached_template = _sheet_template_cache.get(template_text)
    if cached_template is None:
        cached_template = _sheet_template_env.from_string(template_text)
        _sheet_template_cache[template_text] = cached_template
    template = cached_template
    render_ctx: dict[str, object] = dict(context)
    numeric_keys = {
        "AC_arm",
        "AC_scudo",
        "AC_des",
        "AC_defl",
        "AC_nat",
        "AC_dodge",
        "AC_misc",
        "AC_base",
        "AC_tot",
        "CA_touch",
        "CA_ff",
        "BAB",
        "pf_totali",
        "pf_per_livello",
        "speed",
        "velocita",
        "init",
        "iniziativa",
        "CMB",
        "CMD",
        "CMD_base",
        "size_mod_cmd",
        "cmb_disarm",
        "cmb_trip",
        "cmb_grapple",
        "cmd_altro",
        "gp_totali",
        "gp_investiti",
        "gp_liquidi",
        "gp",
        "pp",
        "sp",
        "cp",
        "wbl_target_gp",
        "wbl_delta_gp",
        "next_wbl_gp",
    }
    for key in numeric_keys:
        render_ctx[key] = _coerce_number(render_ctx.get(key), 0)

    stats = render_ctx.get("statistiche")
    if isinstance(stats, Mapping):
        render_ctx["statistiche"] = {
            stat_key: _coerce_number(stat_val, stat_val)
            for stat_key, stat_val in stats.items()
        }

    stats_key = render_ctx.get("statistiche_chiave")
    if isinstance(stats_key, Mapping):
        render_ctx["statistiche_chiave"] = {
            stat_key: _coerce_number(stat_val, stat_val)
            for stat_key, stat_val in stats_key.items()
        }

    rendered = template.render(**render_ctx)
    return rendered.strip()


_validator_cache: dict[str, Draft202012Validator] = {}
_schema_store: dict[str, Mapping] = {}


def _bootstrap_schema_store() -> None:
    """Preload every local schema so $id references resolve offline."""

    if _schema_store.get("__bootstrapped__"):
        return

    for path in SCHEMAS_DIR.glob("*.schema.json"):
        schema = json.loads(path.read_text(encoding="utf-8"))
        _schema_store[path.name] = schema
        if "$id" in schema:
            _schema_store[schema["$id"]] = schema

    _schema_store["__bootstrapped__"] = {"loaded": True}


def _load_validator(schema_filename: str) -> Draft202012Validator:
    _bootstrap_schema_store()
    path = SCHEMAS_DIR / schema_filename
    if not path.is_file():
        raise FileNotFoundError(f"Schema non trovato: {path}")

    schema = json.loads(path.read_text(encoding="utf-8"))
    _schema_store[schema_filename] = schema
    if "$id" in schema:
        _schema_store[schema["$id"]] = schema
    resolver = RefResolver(
        base_uri=path.resolve().as_uri(), referrer=schema, store=_schema_store
    )
    return Draft202012Validator(schema, resolver=resolver)


def get_validator(schema_filename: str) -> Draft202012Validator:
    if schema_filename not in _validator_cache:
        _validator_cache[schema_filename] = _load_validator(schema_filename)
    return _validator_cache[schema_filename]


def schema_for_mode(mode: str) -> str:
    normalized = str(mode or "").lower()
    if normalized.startswith("core"):
        return BUILD_SCHEMA_MAP["core"]
    if normalized.startswith("extended"):
        return BUILD_SCHEMA_MAP["extended"]
    return BUILD_SCHEMA_MAP["full-pg"]


def validate_with_schema(
    schema_filename: str, payload: Mapping, context: str, *, strict: bool
) -> str | None:
    augmented_payload = payload

    # Reference catalog entries are lists, not mappings; only inject metadata when
    # a mapping payload is provided. This prevents attempting to coerce a list
    # to a dict, which raises a ValueError and stops report generation.
    if isinstance(payload, Mapping) and "reference_catalog_version" not in payload:
        manifest_version = (get_reference_manifest() or {}).get("version")
        if manifest_version:
            augmented_payload = dict(payload)
            augmented_payload["reference_catalog_version"] = str(manifest_version)

    if schema_filename in BUILD_SCHEMA_MAP.values():
        needs_copy = augmented_payload is payload
        base_payload = dict(augmented_payload) if needs_copy else augmented_payload
        composite_payload: Mapping | None = None
        build_bundle: Mapping | None = None
        if isinstance(base_payload.get("composite"), Mapping):
            composite_payload = (
                dict(base_payload["composite"])
                if base_payload["composite"] is augmented_payload.get("composite")
                else base_payload["composite"]
            )
            build_bundle = (
                dict(composite_payload.get("build", {}))
                if isinstance(composite_payload.get("build"), Mapping)
                else None
            )

        build_defaults = "stub-build-id-00000000000000000000000000000000"
        if "build_id" not in base_payload:
            base_payload["build_id"] = build_defaults
            needs_copy = False
        if build_bundle is not None and "build_id" not in build_bundle:
            build_bundle["build_id"] = build_defaults

        step_audit_defaults = base_payload.get("step_audit")
        if "step_audit" not in base_payload:
            step_labels = (
                base_payload.get("build_state", {}).get("step_labels", {})
                if isinstance(base_payload.get("build_state"), Mapping)
                else {}
            )
            step_total = (
                base_payload.get("build_state", {}).get("step_total")
                if isinstance(base_payload.get("build_state"), Mapping)
                else None
            )
            mode = (
                base_payload.get("mode")
                or base_payload.get("build_state", {}).get("mode")
                if isinstance(base_payload.get("build_state"), Mapping)
                else None
            )
            step_audit_defaults = {
                "request_timestamp": now_iso_utc(),
                "client_fingerprint_hash": (
                    "stub-fingerprint-00000000000000000000000000000000"
                ),
                "outcome": "accepted",
                "attempt_count": 1,
                "backoff_reason": None,
                "normalized_mode": str(mode).lower() or None,
                "expected_step_total": step_total,
                "observed_step_total": step_total,
                "step_total_ok": bool(step_total),
                "step_labels_count": len(step_labels) if step_labels else None,
                "has_extended_steps": (str(mode).lower() == "extended"),
            }
            base_payload["step_audit"] = step_audit_defaults
            needs_copy = False
        if build_bundle is not None and "step_audit" not in build_bundle:
            build_bundle["step_audit"] = base_payload.get(
                "step_audit", step_audit_defaults
            )

        if composite_payload is not None and build_bundle is not None:
            composite_payload["build"] = build_bundle
            base_payload["composite"] = composite_payload
        augmented_payload = base_payload

    validator = get_validator(schema_filename)
    errors = sorted(validator.iter_errors(augmented_payload), key=lambda err: err.path)
    if not errors:
        return None

    message = "; ".join(error.message for error in errors)
    log_fn = logging.error if strict else logging.warning
    log_fn(
        "Payload %s non valido (%s): %s",
        context,
        schema_filename,
        message,
        extra={
            "event": "schema_validation_failed",
            "context": context,
            "schema": schema_filename,
            "errors": [error.message for error in errors],
            "paths": [
                "/".join(str(segment) for segment in error.path) for error in errors
            ],
        },
    )
    if strict:
        raise ValidationError(message)
    return message


def _empty_review_section() -> dict[str, Any]:
    return {
        "total": 0,
        "valid": 0,
        "invalid": 0,
        "errors": 0,
        "missing": 0,
        "entries": [],
    }


def _bump_review(section: MutableMapping[str, Any], status: str) -> None:
    section["total"] += 1
    if status == "ok":
        section["valid"] += 1
    elif status == "invalid":
        section["invalid"] += 1
    elif status == "missing":
        section["missing"] += 1
    else:
        section["errors"] += 1


def _bump_checkpoint(
    checkpoints: MutableMapping[str, MutableMapping[str, int]],
    level: int | str | None,
    status: str,
    *,
    schema_error: bool = False,
    completeness_error: bool = False,
) -> None:
    if level is None:
        return

    try:
        level_key = f"{int(level)}"
    except (TypeError, ValueError):
        return

    bucket = checkpoints.setdefault(
        level_key,
        {
            "total": 0,
            "invalid": 0,
            "schema_errors": 0,
            "completeness_errors": 0,
        },
    )
    bucket["total"] += 1
    if status != "ok":
        bucket["invalid"] += 1
    if schema_error:
        bucket["schema_errors"] += 1
    if completeness_error:
        bucket["completeness_errors"] += 1


def _checkpoint_summary_from_entries(
    entries: Sequence[Mapping[str, object]],
) -> dict[str, dict[str, int]]:
    checkpoints: dict[str, dict[str, int]] = {}
    for entry in entries:
        _bump_checkpoint(
            checkpoints,
            entry.get("level"),
            str(entry.get("status") or "ok"),
            schema_error=bool(entry.get("error"))
            and not entry.get("completeness_errors"),
            completeness_error=bool(entry.get("completeness_errors")),
        )

    return {
        key: checkpoints[key] for key in sorted(checkpoints, key=lambda item: int(item))
    }


def _load_build_index_entries(
    build_index_path: Path | None,
) -> dict[Path, Mapping[str, object]]:
    if not build_index_path or not build_index_path.is_file():
        return {}

    try:
        build_index_payload = json.loads(build_index_path.read_text(encoding="utf-8"))
        raw_entries: Sequence[Mapping[str, object]] = (
            build_index_payload.get("entries") or []
        )
    except Exception as exc:  # pragma: no cover - defensive logging
        logging.warning(
            "Impossibile leggere l'indice build %s: %s", build_index_path, exc
        )
        return {}

    entries: dict[Path, Mapping[str, object]] = {}
    for entry in raw_entries:
        file_path = entry.get("file")
        if not file_path:
            continue
        resolved = Path(str(file_path)).resolve()
        entries[resolved] = entry
    return entries


def _worst_status(*statuses: str | None) -> str:
    priority = {"error": 4, "missing": 3, "invalid": 2, "ok": 1, None: 0}
    return max(statuses, key=lambda status: priority.get(status, 0)) or "ok"


def _requested_level(payload: Mapping[str, object] | None) -> int | None:
    if not isinstance(payload, Mapping):
        return None

    request_ctx = (
        payload.get("request") if isinstance(payload.get("request"), Mapping) else {}
    )
    level = request_ctx.get("level") if isinstance(request_ctx, Mapping) else None
    if level is None and isinstance(payload.get("build_state"), Mapping):
        level = payload.get("build_state", {}).get("level")

    try:
        coerced = int(level)
    except (TypeError, ValueError):
        return None

    return coerced if coerced > 0 else None


def _strip_level_suffix(name: str) -> str:
    match = re.match(r"^(?P<prefix>.+)_lvl\d+$", name)
    return match.group("prefix") if match else name


def _deduce_level_from_filename(path: Path) -> int | None:
    match = re.match(r"^.+_lvl(?P<level>\d+)\.json$", path.name)
    if match:
        try:
            return int(match.group("level"))
        except ValueError:
            return None
    if path.suffix == ".json":
        # Per convenzione il file senza suffisso corrisponde al livello base
        return 1
    return None


def review_local_database(
    build_dir: Path,
    module_dir: Path,
    *,
    build_index_path: Path | None = None,
    module_index_path: Path | None = None,
    strict: bool = False,
    output_path: Path | None = None,
    reference_dir: Path | None = None,
    catalog_policy: str = "strict",
) -> Mapping[str, Any]:
    """Valida i JSON già presenti nel database locale e produce un report riassuntivo."""

    builds_section = _empty_review_section()
    modules_section = _empty_review_section()
    checkpoints: dict[str, dict[str, int]] = {}

    build_index_meta: dict[str, object] = {}
    if build_index_path and build_index_path.is_file():
        try:
            existing_index = json.loads(build_index_path.read_text(encoding="utf-8"))
            build_index_meta.update(
                {
                    "api_url": existing_index.get("api_url"),
                    "mode": existing_index.get("mode"),
                    "spec_file": existing_index.get("spec_file"),
                }
            )
        except Exception:
            pass

    build_index_entries = _load_build_index_entries(build_index_path)
    reference_catalog = get_reference_catalog(reference_dir, strict=strict)
    reference_manifest = get_reference_manifest(reference_dir)
    manifest_version = (
        str(reference_manifest.get("version"))
        if isinstance(reference_manifest, Mapping)
        else None
    )
    reference_coverage = _reference_url_coverage(reference_catalog)
    build_files: dict[Path, str] = {}
    index_entries: list[dict[str, object]] = []
    if build_dir.is_dir():
        for path in build_dir.rglob("*.json"):
            if path.is_file():
                build_files[path.resolve()] = str(path)
    for resolved_path in build_index_entries:
        build_files.setdefault(
            resolved_path,
            str(build_index_entries[resolved_path].get("file") or resolved_path),
        )

    prefix_tracker: dict[str, dict[str, Any]] = {}

    for path, display_path in sorted(build_files.items(), key=lambda item: item[1]):
        entry: dict[str, Any] = {"file": display_path}
        payload: Mapping[str, Any] | None = None
        index_entry = build_index_entries.get(path)
        target_level = index_entry.get("level") if index_entry else None
        validation_error: str | None = None
        completeness_errors: list[str] = []
        if index_entry:
            entry.update(
                {k: v for k, v in index_entry.items() if k not in {"file", "status"}}
            )

        if not path.exists():
            status = _worst_status(
                "missing", str(index_entry.get("status")) if index_entry else None
            )
            entry["status"] = status
            entry["error"] = "File mancante"
            _bump_review(builds_section, status)
            _bump_checkpoint(checkpoints, target_level, status)
            builds_section["entries"].append(entry)
            continue

        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            entry.update(
                {
                    "class": payload.get("class")
                    or (payload.get("build_state") or {}).get("class"),
                    "mode": payload.get("mode"),
                }
            )
            manifest_mismatch: str | None = None
            payload_catalog_version = payload.get("reference_catalog_version")
            if manifest_version:
                if payload_catalog_version != manifest_version:
                    manifest_mismatch = (
                        "reference_catalog_version mancante"
                        if payload_catalog_version is None
                        else (
                            "reference_catalog_version"
                            f" {payload_catalog_version} diversa da {manifest_version}"
                        )
                    )
            elif payload_catalog_version:
                manifest_mismatch = "reference_catalog_version presente ma manifest locale senza versione"
            validation_error = validate_with_schema(
                schema_for_mode(payload.get("mode", DEFAULT_MODE)),
                payload,
                f"build {path.name}",
                strict=strict,
            )
            if manifest_mismatch:
                if strict:
                    validation_error = (
                        manifest_mismatch
                        if validation_error is None
                        else f"{validation_error}; {manifest_mismatch}"
                    )
                else:
                    entry.setdefault("warnings", []).append(manifest_mismatch)
            sheet_payload = payload.get("export", {}).get(
                "sheet_payload"
            ) or payload.get("sheet_payload")
            ledger = payload.get("ledger") or payload.get("adventurer_ledger")
            sheet_error = None
            if sheet_payload is not None:
                sheet_error = validate_with_schema(
                    "scheda_pg.schema.json",
                    sheet_payload,
                    f"sheet payload {path.name}",
                    strict=strict,
                )
            if validation_error and sheet_error:
                validation_error = f"{validation_error}; {sheet_error}"
            elif validation_error is None:
                validation_error = sheet_error

            completeness_ctx = (
                payload.get("completeness")
                if isinstance(payload.get("completeness"), Mapping)
                else {}
            )
            completeness_errors = list(completeness_ctx.get("errors") or [])
            target_level = _requested_level(payload) or target_level
            progression_errors = _progression_level_errors(sheet_payload, target_level)
            for error in progression_errors:
                if error not in completeness_errors:
                    completeness_errors.append(error)

            catalog_errors, catalog_meta = validate_sheet_with_catalog(
                sheet_payload, reference_catalog, ledger, reference_manifest
            )
            if catalog_policy == "strict":
                for error in catalog_errors:
                    if error not in completeness_errors:
                        completeness_errors.append(error)
            elif catalog_policy == "warn" and catalog_errors:
                payload.setdefault("qa", {}).setdefault("catalog", {})["warnings"] = (
                    sorted(set(catalog_errors))
                )
            if catalog_meta:
                entry.update(catalog_meta)
            completeness_text: str | None = None
            if completeness_errors:
                completeness_text = "; ".join(
                    str(error) for error in completeness_errors
                )
                validation_error = (
                    completeness_text
                    if validation_error is None
                    else f"{validation_error}; {completeness_text}"
                )

            validation_status = "ok" if validation_error is None else "invalid"
            completeness_status = "invalid" if completeness_errors else "ok"
            status = _worst_status(validation_status, completeness_status)
            if completeness_errors:
                entry["completeness_errors"] = completeness_errors
            if validation_error:
                entry["error"] = validation_error
        except ValidationError:
            raise
        except Exception as exc:
            status = "error"
            entry["error"] = str(exc)

        status = _worst_status(
            status, str(index_entry.get("status")) if index_entry else None
        )
        if "error" not in entry and index_entry and index_entry.get("error"):
            entry["error"] = index_entry["error"]
        entry["status"] = status
        if target_level:
            entry["level"] = target_level
        _bump_review(builds_section, status)
        _bump_checkpoint(
            checkpoints,
            target_level,
            status,
            schema_error=bool(validation_error and not completeness_errors),
            completeness_error=bool(completeness_errors),
        )
        builds_section["entries"].append(entry)

        class_name = (
            entry.get("class")
            or (payload or {}).get("class")
            or ((payload or {}).get("build_state") or {}).get("class")
        )
        race = (payload or {}).get("race") or (
            (payload or {}).get("build_state") or {}
        ).get("race")
        archetype = (
            (payload or {}).get("archetype")
            or ((payload or {}).get("build_state") or {}).get("archetype")
            or ((payload or {}).get("build_state") or {}).get("model")
        )
        background = (payload or {}).get("background")
        mode = (payload or {}).get("mode") or (
            (payload or {}).get("build_state") or {}
        ).get("mode")
        spec_parts = [class_name, race, archetype, background]
        spec_id = (
            slugify("_".join(str(part) for part in spec_parts if part))
            if any(spec_parts)
            else None
        )

        preserved_metadata = {
            k: v
            for k, v in (index_entry or {}).items()
            if k
            not in {
                "file",
                "status",
                "error",
                "completeness_errors",
            }
        }
        level_checkpoints = _normalize_levels(
            preserved_metadata.get("level_checkpoints")
            or preserved_metadata.get("levels"),
            (1, 5, 10),
        )
        output_prefix = preserved_metadata.get("output_prefix") or spec_id
        if not output_prefix and display_path:
            output_prefix = Path(display_path).stem

        index_entry = {
            "file": display_path,
            "status": status,
            "output_prefix": output_prefix,
            "class": class_name,
            "race": race,
            "archetype": archetype,
            "mode": mode,
            "mode_normalized": normalize_mode(mode or DEFAULT_MODE),
            "spec_id": spec_id,
            "background": background or preserved_metadata.get("background"),
            "model": preserved_metadata.get("model"),
            "level_checkpoints": level_checkpoints,
        }
        if target_level:
            index_entry["level"] = target_level
        for field in (
            "step_total",
            "expected_step_total",
            "extended_steps_available",
            "step_total_ok",
        ):
            if preserved_metadata.get(field) is not None:
                index_entry[field] = preserved_metadata[field]
        if validation_error:
            index_entry["error"] = validation_error
        if completeness_errors:
            index_entry["completeness_errors"] = completeness_errors
        for field in (
            "missing_catalog_entries",
            "prerequisite_violations",
            "ledger_unknown_entries",
            "ledger_sheet_mismatches",
            "catalog_version",
        ):
            if entry.get(field):
                index_entry[field] = entry[field]
        entry.setdefault("output_prefix", index_entry.get("output_prefix"))
        entry.setdefault("level_checkpoints", index_entry.get("level_checkpoints"))
        entry.setdefault("spec_id", index_entry.get("spec_id"))
        entry.setdefault("mode_normalized", index_entry.get("mode_normalized"))
        index_entries.append(index_entry)

        normalized_prefix = _strip_level_suffix(
            output_prefix or Path(display_path).stem
        )
        tracker_entry = prefix_tracker.setdefault(
            normalized_prefix,
            {
                "expected": set(_normalize_levels(level_checkpoints, (1, 5, 10))),
                "present": set(),
                "template_file": display_path,
            },
        )
        tracker_entry["expected"].update(
            _normalize_levels(level_checkpoints, (1, 5, 10))
        )
        level_from_entry = index_entry.get("level")
        if level_from_entry is None:
            level_from_entry = _deduce_level_from_filename(Path(display_path))
        if level_from_entry:
            tracker_entry["present"].add(int(level_from_entry))

    # Segnala eventuali checkpoint di livello dichiarati ma senza file presenti sul disco
    for prefix, tracker in sorted(prefix_tracker.items()):
        expected_levels = sorted(tracker.get("expected", set()))
        present_levels = tracker.get("present", set())
        missing_levels = [lvl for lvl in expected_levels if lvl not in present_levels]
        if not missing_levels:
            continue

        template_path = Path(str(tracker.get("template_file") or build_dir / prefix))
        for missing_level in missing_levels:
            suffix = (
                ""
                if missing_level == min(expected_levels or {1})
                else f"_lvl{missing_level:02d}"
            )
            missing_path = (
                template_path.parent
                / f"{_strip_level_suffix(template_path.stem)}{suffix}.json"
            )
            entry = {
                "file": str(missing_path),
                "output_prefix": prefix,
                "level": missing_level,
                "level_checkpoints": expected_levels,
                "status": "missing",
                "error": f"Checkpoint livello {missing_level} dichiarato ma file assente",
            }
            builds_section["entries"].append(entry)
            index_entries.append(entry)
            _bump_review(builds_section, "missing")
            _bump_checkpoint(
                checkpoints,
                missing_level,
                "missing",
                completeness_error=True,
            )

    module_entries: Sequence[Mapping[str, Any]] = []
    if module_index_path and module_index_path.is_file():
        try:
            module_index_payload = json.loads(
                module_index_path.read_text(encoding="utf-8")
            )
            module_entries = module_index_payload.get("entries", []) or []
        except Exception as exc:
            modules_section["entries"].append(
                {"file": str(module_index_path), "status": "error", "error": str(exc)}
            )
            _bump_review(modules_section, "error")
            module_entries = []
    elif module_dir.is_dir():
        module_entries = [
            {
                "module": path.name,
                "file": str(path),
                "meta": {
                    "name": path.name,
                    "size_bytes": path.stat().st_size,
                    "suffix": path.suffix,
                },
            }
            for path in sorted(module_dir.iterdir())
            if path.is_file()
        ]

    for module_entry in module_entries:
        module_name = str(module_entry.get("module") or "")
        resolved_path = Path(module_entry.get("file") or module_dir / module_name)
        entry: dict[str, Any] = {
            "module": module_name or resolved_path.name,
            "file": str(resolved_path),
        }

        if not resolved_path.exists():
            entry["status"] = "missing"
            entry["error"] = "File mancante"
            _bump_review(modules_section, "missing")
            modules_section["entries"].append(entry)
            continue

        try:
            validation_error = validate_with_schema(
                MODULE_SCHEMA,
                module_entry.get("meta", {}),
                f"module meta {entry['module']}",
                strict=strict,
            )
            status = "ok" if validation_error is None else "invalid"
            if validation_error:
                entry["error"] = validation_error
        except ValidationError:
            raise
        except Exception as exc:
            status = "error"
            entry["error"] = str(exc)

        entry["status"] = status
        entry["size_bytes"] = (
            module_entry.get("meta", {}).get("size_bytes")
            or resolved_path.stat().st_size
        )
        _bump_review(modules_section, status)
        modules_section["entries"].append(entry)

    if checkpoints:
        builds_section["checkpoints"] = {
            key: checkpoints[key]
            for key in sorted(checkpoints, key=lambda item: int(item))
        }

    report = {
        "generated_at": now_iso_utc(),
        "builds": builds_section,
        "modules": modules_section,
    }
    report["reference_urls"] = reference_coverage
    if reference_coverage.get("missing_aon_entries"):
        logging.warning(
            "Reference senza AoN rilevate: %s",
            ", ".join(reference_coverage.get("missing_aon_entries", [])),
        )

    if build_index_path:
        report["build_index"] = str(build_index_path)
    if module_index_path:
        report["module_index"] = str(module_index_path)

    if build_index_path:
        index_payload: dict[str, object] = {
            "generated_at": now_iso_utc(),
            **build_index_meta,
            "entries": sorted(
                index_entries, key=lambda entry: str(entry.get("file") or "")
            ),
        }
        index_payload["checkpoints"] = _checkpoint_summary_from_entries(index_entries)
        write_json(build_index_path, index_payload)

    if output_path:
        write_json(output_path, report)
        logging.info("Report di review scritto in %s", output_path)

    return report


def apply_glob_filters(
    entries: Sequence[str], include: Sequence[str], exclude: Sequence[str]
) -> list[str]:
    def matches(patterns: Sequence[str], candidate: str) -> bool:
        return any(fnmatchcase(candidate, pattern) for pattern in patterns)

    filtered: list[str] = []
    for name in entries:
        if include and not matches(include, name):
            continue
        if exclude and matches(exclude, name):
            continue
        filtered.append(name)
    return filtered


def _combo_string_list(value: object) -> list[str]:
    normalized = _stringify_sequence(value)
    return normalized if normalized else []


def _combo_archetype_value(archetypes: object) -> str | None:
    if isinstance(archetypes, str):
        return archetypes.strip() or None
    if isinstance(archetypes, Sequence) and not isinstance(archetypes, (str, bytes)):
        candidates = [str(item).strip() for item in archetypes if str(item).strip()]
        if candidates:
            return " + ".join(candidates)
    return None


def load_combo_matrix(matrix_path: Path, default_mode: str) -> list[BuildRequest]:
    """Carica la matrice di archetipi/talenti e costruisce le richieste."""

    raw_data = yaml.safe_load(matrix_path.read_text(encoding="utf-8"))
    if not isinstance(raw_data, Mapping):
        raise ValueError(
            f"combo_matrix non valida: atteso mapping, trovato {type(raw_data)}"
        )

    default_mode = str(raw_data.get("mode", default_mode))
    default_levels = _normalize_levels(raw_data.get("level_checkpoints"), (1, 5, 10))
    class_matrix = raw_data.get("classes")
    if not isinstance(class_matrix, Mapping):
        raise ValueError("combo_matrix mancante della sezione 'classes'")

    requests: list[BuildRequest] = []
    for class_name, class_entry in class_matrix.items():
        if not isinstance(class_entry, Mapping):
            continue

        class_race = class_entry.get("race") or class_entry.get("default_race")
        class_background = class_entry.get("background")
        class_mode = str(class_entry.get("mode", default_mode))
        class_levels = _normalize_levels(
            class_entry.get("level_checkpoints"), default_levels
        )

        combos = class_entry.get("combos") or class_entry.get("variants")
        if not isinstance(combos, Sequence) or isinstance(combos, (str, bytes)):
            continue

        for combo in combos:
            if not isinstance(combo, Mapping):
                continue

            archetype_value = _combo_archetype_value(
                combo.get("archetypes") or combo.get("archetype")
            )
            feat_plan = _combo_string_list(combo.get("feats") or combo.get("talents"))
            raw_citations = _combo_string_list(
                combo.get("raw_citations") or combo.get("citations")
            )
            stacking_limits = _combo_string_list(
                combo.get("stacking_limits") or combo.get("limits")
            )
            combo_id = combo.get("id") or combo.get("name")
            if not combo_id:
                fragments = [class_name, archetype_value or "base"]
                if feat_plan:
                    fragments.append(feat_plan[0])
                combo_id = slugify("-".join(fragments))

            race = combo.get("race") or class_race
            background = (
                combo.get("background")
                or combo.get("background_hooks")
                or class_background
            )

            output_prefix = combo.get("output_prefix") or slugify(
                "-".join(
                    part
                    for part in (
                        class_name,
                        race,
                        archetype_value,
                        combo_id,
                    )
                    if part
                )
            )

            level_checkpoints = _normalize_levels(
                combo.get("level_checkpoints"), class_levels
            )

            requests.append(
                BuildRequest(
                    class_name=str(class_name),
                    mode=str(combo.get("mode", class_mode)),
                    filename_prefix=output_prefix,
                    spec_id=combo_id,
                    race=race,
                    archetype=archetype_value,
                    background=background,
                    combo_id=combo_id,
                    feat_plan=feat_plan,
                    raw_citations=raw_citations,
                    stacking_limits=stacking_limits,
                    query_params=_normalize_mapping(
                        {"race": race, "archetype": archetype_value}
                    ),
                    body_params=_normalize_mapping(
                        {
                            "background_hooks": background,
                            "feat_matrix": feat_plan,
                            "raw_citations": raw_citations,
                            "stacking_limits": stacking_limits,
                            "combo_id": combo_id,
                        }
                    ),
                    level_checkpoints=level_checkpoints,
                )
            )

    return requests


def load_spec_requests(spec_path: Path, default_mode: str) -> list[BuildRequest]:
    """Carica un file YAML/JSON e restituisce le richieste strutturate."""

    raw_data = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
    if raw_data is None:
        raise ValueError(f"File spec vuoto: {spec_path}")

    if isinstance(raw_data, Mapping):
        default_mode = str(raw_data.get("mode", default_mode))
        default_levels = _normalize_levels(
            raw_data.get("level_checkpoints"), (1, 5, 10)
        )
        entries = raw_data.get("requests")
    else:
        default_levels = _normalize_levels(None, (1, 5, 10))
        entries = raw_data

    if not isinstance(entries, Sequence) or isinstance(entries, (str, bytes)):
        raise ValueError(f"Spec {spec_path} non valida: atteso elenco di richieste")

    requests: list[BuildRequest] = []
    for entry in entries:
        if not isinstance(entry, Mapping):
            raise ValueError(f"Voce spec non valida: {entry!r}")

        class_name = entry.get("class")
        if not class_name:
            raise ValueError(f"Voce spec senza 'class': {entry}")

        request = BuildRequest(
            class_name=str(class_name),
            mode=str(entry.get("mode", default_mode)),
            filename_prefix=entry.get("output_prefix") or entry.get("filename_prefix"),
            spec_id=entry.get("id") or entry.get("name"),
            race=entry.get("race"),
            archetype=entry.get("archetype") or entry.get("model"),
            model=entry.get("model"),
            background=entry.get("background") or entry.get("background_hooks"),
            combo_id=entry.get("combo_id") or entry.get("combo"),
            feat_plan=_stringify_sequence(entry.get("feats") or entry.get("talents")),
            raw_citations=_stringify_sequence(
                entry.get("raw_citations") or entry.get("citations")
            ),
            stacking_limits=_stringify_sequence(
                entry.get("stacking_limits") or entry.get("limits")
            ),
            query_params=_normalize_mapping(
                entry.get("query") or entry.get("query_params") or entry.get("params")
            ),
            body_params=_normalize_mapping(
                entry.get("body") or entry.get("body_params") or entry.get("json")
            ),
            level_checkpoints=_normalize_levels(
                entry.get("level_checkpoints") or entry.get("levels"), default_levels
            ),
        )

        requests.append(request)

    return requests


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Genera un database JSON di build per classe."
    )
    parser.add_argument(
        "--api-url",
        default=os.environ.get("API_URL", DEFAULT_BASE_URL),
        help="Base URL dell'API Master DD (default: %(default)s)",
    )
    parser.add_argument(
        "--api-key",
        default=os.environ.get("API_KEY"),
        help="API key da passare nell'header x-api-key (default: variabile API_KEY)",
    )
    parser.add_argument(
        "--ruling-expert-url",
        dest="ruling_expert_url",
        default=os.environ.get("RULING_EXPERT_URL"),
        help="Endpoint REST del Ruling Expert per convalidare il badge (obbligatorio)",
    )
    parser.add_argument(
        "--ruling-cache",
        type=Path,
        default=None,
        help="Path a una cache JSON per i risultati del Ruling Expert (riduce chiamate ripetute).",
    )
    parser.add_argument(
        "--ruling-expert-timeout",
        dest="ruling_timeout",
        type=float,
        default=30.0,
        help="Timeout (secondi) per la chiamata verso Ruling Expert (default: %(default)s)",
    )
    parser.add_argument(
        "--ruling-expert-concurrency",
        dest="ruling_concurrency",
        type=int,
        default=2,
        help=(
            "Limite di concorrenza dedicato per le chiamate verso Ruling Expert (default: %(default)s)."
        ),
    )
    parser.add_argument(
        "--ruling-expert-max-retries",
        dest="ruling_max_retries",
        type=int,
        help="Retry massimo per la chiamata Ruling Expert (default: usa --max-retries)",
    )
    parser.add_argument(
        "--skip-ruling-expert",
        action="store_true",
        help="Debug: non valida ruling badge e non richiede --ruling-expert-url",
    )
    parser.add_argument(
        "--require-t1",
        action="store_true",
        dest="t1_filter",
        help="Genera più varianti e mantiene solo quelle con meta_tier T1 e badge validato",
    )
    parser.add_argument(
        "--suggest-combos",
        action="store_true",
        help="Genera combinazioni dal catalogo e conserva solo quelle T1 con ruling badge",
    )
    parser.add_argument(
        "--validate-combo",
        action="store_true",
        help=(
            "Valida che le combo suggerite abbiano meta_tier T1 e ruling_badge; "
            "se nessuna è valida aggiunge errori di completezza"
        ),
    )
    parser.add_argument(
        "--t1-variants",
        type=int,
        default=3,
        help="Numero di varianti da testare quando il filtro T1 è attivo (default: %(default)s)",
    )
    parser.add_argument(
        "--lazy-ruling",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "Con --require-t1 e --t1-variants > 1, valida il ruling badge solo sulla variante migliore (riduce chiamate esterne)."
        ),
    )
    parser.add_argument(
        "--mode",
        default=DEFAULT_MODE,
        choices=["core", "extended", "full-pg"],
        help="Modalità di flow da richiedere al builder (default: %(default)s)",
    )
    parser.add_argument(
        "--stub",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Passa il flag stub al builder (default: True). Usa --no-stub per richiedere output pieno se supportato.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("src/data/builds"),
        help="Directory di output per i singoli JSON",
    )
    parser.add_argument(
        "--modules-output-dir",
        type=Path,
        default=Path("src/data/modules"),
        help="Directory di output per i dump grezzi dei moduli",
    )
    parser.add_argument(
        "--index-path",
        type=Path,
        default=Path("src/data/build_index.json"),
        help="Percorso del file indice riassuntivo",
    )
    parser.add_argument(
        "--module-index-path",
        type=Path,
        default=Path("src/data/module_index.json"),
        help="Percorso del file indice per i moduli scaricati",
    )
    parser.add_argument(
        "--reference-dir",
        type=Path,
        default=Path("data/reference"),
        help="Directory con il catalogo normalizzato di incantesimi/talenti/equipaggiamento",
    )
    parser.add_argument(
        "--catalog-policy",
        choices=["strict", "warn", "off"],
        default="warn",
        help="Policy validazione catalogo: strict=blocca su mismatch, warn=solo warning, off=salta (default: warn)",
    )
    parser.add_argument(
        "--numeric-completeness",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Abilita controlli numerici minimi (PF>0, velocita>0, CA>=10, BAB>=0)",
    )
    parser.add_argument(
        "--reports-dir",
        type=Path,
        default=Path("reports"),
        help="Directory di output per i report di copertura build (default: %(default)s)",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=5,
        help="Numero massimo di richieste concorrenti (default: %(default)s)",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=3,
        help="Numero massimo di tentativi per ogni richiesta (default: %(default)s)",
    )
    parser.add_argument(
        "--modules",
        nargs="*",
        default=list(DEFAULT_MODULE_TARGETS),
        help="Elenco moduli da scaricare in parallelo alle build",
    )
    parser.add_argument(
        "--skip-modules",
        action="store_true",
        help="Salta discovery/download/validazione moduli (utile per velocizzare la sola generazione build).",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Interrompe l'esecuzione al primo errore di validazione",
    )
    parser.add_argument(
        "--warn-only",
        action="store_true",
        help="Continua l'esecuzione loggando gli errori di validazione (default)",
    )
    parser.add_argument(
        "--keep-invalid",
        action="store_true",
        help="Scrive comunque i payload non validi invece di scartarli",
    )
    parser.add_argument(
        "--fail-on-invalid",
        action="store_true",
        help="Exit non-zero se build/moduli risultano invalid/error/missing (escludendo pruned).",
    )
    parser.add_argument(
        "--require-complete",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Considera incompleti i payload privi di statistiche/narrativa/ledger e riprova automaticamente",
    )
    parser.add_argument(
        "--skip-health-check",
        action="store_true",
        help="Salta il controllo di raggiungibilità dell'API (fallback per ambienti in cui /health non è disponibile)",
    )
    parser.add_argument(
        "--health-path",
        default=os.environ.get("HEALTH_PATH", "/health"),
        help="Percorso dell'endpoint di health check (default: %(default)s)",
    )
    parser.add_argument(
        "--health-timeout",
        type=float,
        default=float(os.environ.get("HEALTH_TIMEOUT", "10")),
        help="Timeout del probe di health/metrics in secondi (default: %(default)s)",
    )
    parser.add_argument(
        "--skip-unchanged",
        action="store_true",
        help="Evita di riscrivere i payload invariati confrontando i JSON generati con i file già presenti",
    )
    parser.add_argument(
        "--dual-pass",
        action="store_true",
        help="Esegue prima un passaggio fail-fast (--strict) e poi uno tollerante con --keep-invalid",
    )
    parser.add_argument(
        "--skip-tolerant-on-success",
        action="store_true",
        help=(
            "Quando usato con --dual-pass, salta il secondo passaggio se quello strict ha"
            " successo e non sono richieste varianti o salvataggi aggiuntivi"
        ),
    )
    parser.add_argument(
        "--dual-pass-report",
        type=Path,
        help="Percorso del report riepilogativo dei due passaggi (--dual-pass)",
    )
    parser.add_argument(
        "--invalid-archive-dir",
        type=Path,
        help="Cartella in cui copiare i payload non conformi individuati negli indici",
    )
    parser.add_argument(
        "--validate-db",
        action="store_true",
        help="Valida il database locale (build e moduli) senza effettuare chiamate all'API, producendo un report per livello",
    )
    parser.add_argument(
        "--review-output",
        type=Path,
        default=Path("src/data/build_review.json"),
        help="Percorso del report di review (con riepilogo per checkpoint di livello) quando --validate-db è attivo (default: %(default)s)",
    )
    parser.add_argument(
        "--backfill-badges",
        action="store_true",
        help="Aggiorna snapshot build esistenti aggiungendo ruling_badge/ruling_sources se mancanti (usa ruling expert).",
    )
    parser.add_argument(
        "--backfill-badges-dry-run",
        action="store_true",
        help="Con --backfill-badges: non scrive file/index, mostra solo cosa verrebbe aggiornato.",
    )
    parser.add_argument(
        "--backfill-badges-max-items",
        type=int,
        default=0,
        help="Con --backfill-badges: limita numero file da processare (0=tutti).",
    )
    parser.add_argument(
        "--discover-modules",
        action="store_true",
        help="Recupera automaticamente la lista di moduli disponibili da /modules",
    )
    parser.add_argument(
        "--include",
        nargs="*",
        default=[],
        metavar="GLOB",
        help="Filtri di inclusione (glob) applicati ai moduli scoperti via /modules",
    )
    parser.add_argument(
        "--exclude",
        nargs="*",
        default=[],
        metavar="GLOB",
        help="Filtri di esclusione (glob) applicati ai moduli scoperti via /modules",
    )
    parser.add_argument(
        "--spec-file",
        type=Path,
        default=DEFAULT_SPEC_FILE,
        help="File YAML/JSON con le richieste da processare (override di --mode/--classes)",
    )
    parser.add_argument(
        "--no-default-spec",
        action="store_true",
        help="Disabilita l'uso del file spec predefinito (docs/examples/pg_variants.yml)",
    )
    parser.add_argument(
        "--combo-matrix",
        type=Path,
        default=Path("config/combo_matrix.yml"),
        help=(
            "Matrice YAML di archetipi/talenti per classe: genera richieste basate sulle combo"
        ),
    )
    parser.add_argument(
        "--races",
        nargs="*",
        default=[],
        help="Elenco di razze da combinare con le classi target (prodotto cartesiano)",
    )
    parser.add_argument(
        "--race-inventory",
        type=Path,
        default=Path("reports/build_races.json"),
        help="File JSON con l'inventario delle razze già usate; se esiste può essere usato per evitare duplicati",
    )
    parser.add_argument(
        "--race-pool",
        nargs="*",
        default=list(PF1E_RACES),
        help="Pool di razze candidate per l'assegnazione automatica quando manca la razza nella request",
    )
    parser.add_argument(
        "--prefer-unused-race",
        action="store_true",
        help="Quando la razza non è specificata assegna la prima razza non ancora presente nell'inventario",
    )
    parser.add_argument(
        "--export-races",
        action="store_true",
        help="Esporta l'elenco delle razze effettivamente usate nei build JSON e termina",
    )
    parser.add_argument(
        "--archetypes",
        nargs="*",
        default=[],
        help="Elenco di archetipi/modelli da combinare con le classi target",
    )
    parser.add_argument(
        "--background-hooks",
        nargs="*",
        default=[],
        help="Hook di background da includere nel prodotto cartesiano",
    )
    parser.add_argument(
        "--keep-all-combos",
        action="store_true",
        help="Non scarta le varianti peggiori quando la combo matrix è attiva",
    )
    parser.add_argument(
        "--classes",
        dest="filter_classes",
        nargs="*",
        help=(
            "Filtra le richieste generate a un sottoinsieme di classi PF1e (case-insensitive); "
            "applicato dopo spec/CLI"
        ),
    )
    parser.add_argument(
        "--levels",
        dest="filter_levels",
        nargs="*",
        type=int,
        help=(
            "Filtra i checkpoint di livello per ogni richiesta (es. --levels 1 5). "
            "Se una richiesta prevede un livello singolo non presente qui viene scartata"
        ),
    )
    parser.add_argument(
        "--max-items",
        type=int,
        help=(
            "Numero massimo di file di build da generare in una singola esecuzione "
            "dopo l'applicazione dei filtri di classe/livello"
        ),
    )
    parser.add_argument(
        "--offset",
        type=int,
        default=0,
        help=(
            "Numero di richieste già processate da saltare prima di applicare max-items "
            "(partendo da 0)"
        ),
    )
    parser.add_argument(
        "--page",
        type=int,
        help=(
            "Numero di pagina (1-based) da processare: calcola l'offset automaticamente "
            "se combinato con --page-size o --max-items"
        ),
    )
    parser.add_argument(
        "--page-size",
        type=int,
        help=(
            "Dimensione della pagina da usare con --page; se omessa, usa --max-items come"
            " valore di riferimento"
        ),
    )
    parser.add_argument(
        "--export-lists",
        action="store_true",
        help="Esporta i report di copertura delle build locali e termina senza chiamare l'API",
    )
    parser.add_argument(
        "classes",
        nargs="*",
        default=PF1E_CLASSES,
        help="Sovrascrive la lista di classi PF1e da generare",
    )
    return parser.parse_args()


def build_variant_matrix_requests(
    classes: Sequence[str],
    mode: str,
    races: Sequence[str],
    archetypes: Sequence[str],
    background_hooks: Sequence[str],
) -> list[BuildRequest]:
    race_options = list(races) or [None]
    archetype_options = list(archetypes) or [None]
    background_options = list(background_hooks) or [None]

    requests: list[BuildRequest] = []
    for class_name, race, archetype, background in product(
        classes, race_options, archetype_options, background_options
    ):
        spec_fragments = [class_name, race or "Human", archetype or "Base"]
        background_slug = slugify(background) if background else None
        if background_slug:
            spec_fragments.append(background_slug)

        spec_id = "::".join(spec_fragments)
        output_prefix = slugify("-".join(spec_fragments))
        query_params = _normalize_mapping({"race": race, "archetype": archetype})
        body_params = _normalize_mapping({"background_hooks": background})

        requests.append(
            BuildRequest(
                class_name=class_name,
                mode=mode,
                filename_prefix=output_prefix,
                spec_id=spec_id,
                race=race,
                archetype=archetype,
                background=background,
                query_params=query_params,
                body_params=body_params,
            )
        )

    return requests


def _ensure_spec_ids(requests: Sequence[BuildRequest], spec_path: Path | None) -> None:
    missing_spec_id = [req.class_name for req in requests if not req.spec_id]
    if not missing_spec_id:
        return

    message = f"Spec {spec_path} privo di spec_id per {len(missing_spec_id)} richieste"
    logging.error("%s: %s", message, ", ".join(sorted(set(missing_spec_id))))
    raise ValueError(message)


def build_requests_from_args(
    args: argparse.Namespace,
) -> tuple[list[BuildRequest], bool, Path | None]:
    combo_matrix_used = False
    spec_path = None if args.no_default_spec else args.spec_file
    if spec_path:
        requests = load_spec_requests(spec_path, args.mode)
        _ensure_spec_ids(requests, spec_path)
        return requests, combo_matrix_used, spec_path

    if args.races or args.archetypes or args.background_hooks:
        return (
            build_variant_matrix_requests(
                args.classes,
                args.mode,
                args.races,
                args.archetypes,
                args.background_hooks,
            ),
            combo_matrix_used,
            spec_path,
        )

    if args.combo_matrix and args.combo_matrix.is_file():
        try:
            combo_requests = load_combo_matrix(args.combo_matrix, args.mode)
            combo_matrix_used = True
            return combo_requests, combo_matrix_used, spec_path
        except Exception as exc:
            logging.warning(
                "Impossibile caricare combo_matrix %s: %s", args.combo_matrix, exc
            )

    if (not args.no_default_spec) and DEFAULT_SPEC_FILE.is_file():
        logging.info("Uso il file spec predefinito %s", DEFAULT_SPEC_FILE)
        spec_path = DEFAULT_SPEC_FILE
        requests = load_spec_requests(spec_path, args.mode)
        _ensure_spec_ids(requests, spec_path)
        return requests, combo_matrix_used, spec_path

    return (
        [
            BuildRequest(class_name=class_name, mode=args.mode)
            for class_name in args.classes
        ],
        combo_matrix_used,
        spec_path,
    )


def filter_requests(
    requests: Sequence[BuildRequest],
    class_filters: Sequence[str] | None,
    level_filters: Sequence[int] | None,
) -> list[BuildRequest]:
    class_set = (
        {slugify(name).lower() for name in class_filters if name}
        if class_filters
        else None
    )
    level_set = {int(level) for level in level_filters} if level_filters else None

    filtered_requests: list[BuildRequest] = []
    for request in requests:
        if class_set and slugify(request.class_name).lower() not in class_set:
            continue

        updated_request = request
        if level_set is not None:
            request_level = None
            try:
                request_level = (
                    int(request.level) if request.level is not None else None
                )
            except (TypeError, ValueError):
                request_level = None

            if request_level is not None and request_level not in level_set:
                continue

            filtered_levels = [
                coerced
                for coerced in (
                    int(lvl) for lvl in request.level_checkpoints if lvl is not None
                )
                if coerced in level_set
            ]
            updated_request = replace(request, level_checkpoints=filtered_levels)

        filtered_requests.append(updated_request)

    return filtered_requests


def _request_identifier(request: BuildRequest) -> str:
    return (
        request.spec_id
        or request.filename_prefix
        or request.output_name()
        or request.class_name
    )


def log_request_batch(
    requests: Sequence[BuildRequest],
    window: Mapping[str, int | None],
) -> None:
    offset = window.get("offset")
    limit = window.get("limit")
    start = window.get("start")
    end = window.get("end")
    total = window.get("total")

    if not requests:
        logging.info(
            "Nessuna richiesta selezionata (offset=%s, max_items=%s su totale %s)",
            offset,
            limit if limit is not None else "all",
            total,
        )
        return

    first = _request_identifier(requests[0])
    last = _request_identifier(requests[-1])

    logging.info(
        "Batch selezionato: offset=%s, max_items=%s, richieste %s-%s/%s (%s -> %s)",
        offset,
        limit if limit is not None else "all",
        start,
        (end - 1) if end is not None else start,
        total,
        first,
        last,
    )


def select_request_window(
    requests: Sequence[BuildRequest],
    *,
    offset: int = 0,
    max_items: int | None = None,
    page: int | None = None,
    page_size: int | None = None,
) -> tuple[list[BuildRequest], dict[str, int | None]]:
    total = len(requests)

    normalized_max_items = int(max_items) if max_items is not None else None
    effective_offset = max(0, int(offset or 0))

    if normalized_max_items is not None:
        normalized_max_items = max(0, normalized_max_items)
        if normalized_max_items == 0:
            return [], {
                "offset": effective_offset,
                "start": min(effective_offset, total),
                "end": min(effective_offset, total),
                "limit": 0,
                "total": total,
            }

    if page is not None:
        page_num = max(1, int(page))
        effective_page_size = page_size or normalized_max_items
        if effective_page_size is None or effective_page_size <= 0:
            raise ValueError(
                "--page richiede un --page-size valido o un --max-items positivo per calcolare la finestra"
            )
        effective_offset = (page_num - 1) * effective_page_size
        if normalized_max_items is None:
            normalized_max_items = effective_page_size

    start_index = min(effective_offset, total)
    end_index = (
        total
        if normalized_max_items is None
        else min(start_index + normalized_max_items, total)
    )

    selected = list(islice(requests, start_index, end_index))

    return selected, {
        "offset": effective_offset,
        "start": start_index,
        "end": end_index,
        "limit": normalized_max_items,
        "total": total,
    }


async def request_with_retry(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    headers: Mapping[str, str] | None = None,
    params: Mapping[str, object] | None = None,
    json_body: Mapping[str, object] | None = None,
    timeout: int | float | None = None,
    max_retries: int,
    backoff_factor: float = 1.0,
    max_delay: float | None = 60.0,
    jitter_ratio: float = 0.1,
) -> httpx.Response:
    max_attempts = max_retries + 1
    attempt = 0

    retryable_statuses = {401, 429}

    def _retry_after_seconds(value: str | None) -> float | None:
        if value is None:
            return None
        if value.isdigit():
            return float(value)

        try:
            parsed_date = parsedate_to_datetime(value)
        except (TypeError, ValueError):
            return None

        if parsed_date is None:
            return None

        delta = parsed_date - datetime.now(timezone.utc)
        return max(0.0, delta.total_seconds())

    while True:
        attempt += 1
        try:
            response = await client.request(
                method,
                url,
                headers=headers,
                params=params,
                json=json_body,
                timeout=timeout,
            )
        except httpx.RequestError as exc:
            if attempt >= max_attempts:
                raise

            base_delay = backoff_factor * 2 ** (attempt - 1)
            delay = min(base_delay, max_delay) if max_delay is not None else base_delay
            jitter = random.uniform(0, delay * jitter_ratio) if jitter_ratio > 0 else 0
            actual_delay = delay + jitter
            logging.warning(
                "Tentativo %s fallito per %s %s (%s). Retry in %.1fs (base %.1fs, jitter %.2fs)...",
                attempt,
                method,
                url,
                exc.__class__.__name__,
                actual_delay,
                delay,
                jitter,
            )
            await asyncio.sleep(actual_delay)
            continue

        if (
            response.status_code not in retryable_statuses
            and response.status_code < 500
        ):
            response.raise_for_status()
            return response

        if attempt >= max_attempts:
            response.raise_for_status()

        base_delay = backoff_factor * 2 ** (attempt - 1)
        retry_after_header = response.headers.get("Retry-After")
        retry_after = _retry_after_seconds(retry_after_header)

        delay = base_delay
        if retry_after is not None:
            delay = max(delay, retry_after)

        if response.status_code in retryable_statuses:
            delay = max(delay, AUTH_BACKOFF_SECONDS)
            log_build_event(
                {
                    "timestamp": now_iso_utc(),
                    "endpoint": url,
                    "method": method,
                    "status_code": response.status_code,
                    "attempt": attempt,
                    "retry_after": retry_after,
                    "reason": (
                        "auth_backoff" if response.status_code == 401 else "rate_limit"
                    ),
                }
            )

        if max_delay is not None:
            delay = min(delay, max_delay)

        jitter = random.uniform(0, delay * jitter_ratio) if jitter_ratio > 0 else 0
        actual_delay = delay + jitter
        logging.warning(
            "Tentativo %s fallito per %s %s (status %s). Retry in %.1fs (base %.1fs, jitter %.2fs, retry-after %s)...",
            attempt,
            method,
            url,
            response.status_code,
            actual_delay,
            delay,
            jitter,
            retry_after_header or "-",
        )
        await asyncio.sleep(actual_delay)


async def assert_api_reachable(
    client: httpx.AsyncClient,
    api_key: str | None,
    health_path: str = "/health",
    health_timeout: float = 10.0,
) -> None:
    """Fail fast with a clear message if the API endpoint is unreachable."""

    headers = {"x-api-key": api_key} if api_key else {}
    try:
        response = await client.get(
            health_path, headers=headers, timeout=health_timeout
        )
    except httpx.RequestError as exc:  # pragma: no cover - network dependent
        raise RuntimeError(
            f"API non raggiungibile su {client.base_url}: {exc}. "
            "Avvia il servizio localmente oppure passa --api-url verso un endpoint accessibile."
        ) from exc

    if response.status_code == 404:
        logging.info(
            "L'endpoint %s non esiste su %s ma l'host risponde: proseguo...",
            health_path,
            client.base_url,
        )
    elif response.status_code >= 500:
        logging.warning(
            "Health check %s ha risposto %s: il servizio potrebbe non essere pronto",
            client.base_url,
            response.status_code,
        )


def _enrich_sheet_payload(
    payload: Mapping[str, object],
    ledger: Mapping | None,
    source_url: str | None,
) -> MutableMapping[str, object]:
    export_ctx = payload.get("export") if isinstance(payload, Mapping) else {}
    export_ctx = export_ctx or {}

    def _as_mapping(value: object) -> Mapping | None:
        return value if isinstance(value, Mapping) else None

    def _fallback_stat(label: str) -> str:
        return f"n/d ({label} non fornito)"

    def _ability_modifier(score: object) -> int | None:
        value = _coerce_number(score)
        if isinstance(value, (int, float)):
            return int((value - 10) // 2)
        return None

    def _normalize_save_entry(
        raw: object,
        breakdown: Mapping | None,
        fallback_total: int | float | None = None,
        label: str | None = None,
    ) -> Mapping[str, object]:
        entry: dict[str, object] = {}
        as_mapping = _as_mapping(raw) or {}
        total = _first_non_placeholder(
            as_mapping.get("totale"),
            as_mapping.get("total"),
            as_mapping.get("value"),
            raw if isinstance(raw, (int, float)) else None,
        )
        entry["base"] = _first_non_placeholder(
            as_mapping.get("base"), as_mapping.get("bab"), None
        )
        entry["modificatore"] = _first_non_placeholder(
            as_mapping.get("mod"),
            as_mapping.get("abilita"),
            as_mapping.get("ability_mod"),
            None,
        )
        entry["misc"] = _first_non_placeholder(as_mapping.get("misc"), None)
        if breakdown:
            entry["breakdown"] = breakdown
        if total is None and fallback_total is not None:
            if all(
                _is_placeholder(entry.get(key))
                for key in ("base", "modificatore", "misc")
            ):
                total = fallback_total
        if total is None and not all(
            _is_placeholder(entry.get(key)) for key in ("base", "modificatore", "misc")
        ):
            numeric_parts = [
                part
                for part in (
                    entry.get("base"),
                    entry.get("modificatore"),
                    entry.get("misc"),
                )
                if isinstance(part, (int, float))
            ]
            if numeric_parts:
                total = sum(numeric_parts)
        if total is None and label:
            total = _fallback_stat(label)
        if total is not None:
            entry["totale"] = total
        return entry

    ability_alias_map = {
        "for": "FOR",
        "forza": "FOR",
        "str": "FOR",
        "des": "DES",
        "destrezza": "DES",
        "dex": "DES",
        "cos": "COS",
        "costituzione": "COS",
        "con": "COS",
        "int": "INT",
        "intelligenza": "INT",
        "sag": "SAG",
        "saggezza": "SAG",
        "wis": "SAG",
        "car": "CAR",
        "carisma": "CAR",
        "cha": "CAR",
    }

    ability_keys = set(ability_alias_map.values())

    def _normalize_stat_key(raw_key: object) -> str | None:
        if raw_key is None:
            return None
        key = str(raw_key).strip()
        if not key:
            return None

        lowered = key.lower()
        if lowered in ability_alias_map:
            return ability_alias_map[lowered]

        upper = key.upper()
        if upper in ability_keys:
            return upper

        # Preserve the original key for non-characteristic entries to avoid
        # altering unrelated statistics while still converging ability scores
        # to FOR/DES/COS/INT/SAG/CAR.
        return key

    slot_entry_re = re.compile(
        r"(\d+)\s*(?:[°º]|lvl|liv(?:ello)?|level)?\s*[:=]?\s*([+\-]?\d+)"
    )

    def _parse_slots_from_text(raw: object) -> dict[int, object]:
        if not isinstance(raw, str):
            return {}
        entries: dict[int, object] = {}
        for level_str, value_str in slot_entry_re.findall(raw):
            try:
                level = int(level_str)
            except ValueError:
                continue
            if level <= 0:
                continue
            value: object = value_str
            try:
                numeric = int(value_str)
                value = numeric
            except ValueError:
                pass
            if level not in entries:
                entries[level] = value
        return entries

    def _normalize_spell_value(value: object) -> object | None:
        if _is_placeholder(value):
            return None
        if isinstance(value, (int, float)):
            return value
        if isinstance(value, str):
            cleaned = value.strip()
            return cleaned or None
        if isinstance(value, Mapping):
            for key in ("totale", "total", "value"):
                if key in value and not _is_placeholder(value.get(key)):
                    return value.get(key)
            return None
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
            return len([item for item in value if not _is_placeholder(item)])
        return None

    def _normalize_spell_levels(
        *sources: Sequence | None,
        slots_map: Mapping | None = None,
        prepared_map: Mapping | None = None,
        known_map: Mapping | None = None,
        dc_map: Mapping | None = None,
    ) -> list[Mapping[str, object]]:
        normalized: dict[int, dict[str, object]] = {}

        def _coerce_level(value: object) -> int | None:
            coerced = _coerce_number(value)
            try:
                return int(coerced) if coerced is not None else None
            except (TypeError, ValueError):
                return None

        def _update(level: int, key: str, value: object | None) -> None:
            if value is None:
                return
            entry = normalized.setdefault(level, {"liv": level})
            if _is_placeholder(entry.get(key)) or key not in entry:
                entry[key] = value

        for source in sources:
            if not isinstance(source, Sequence) or isinstance(source, (str, bytes)):
                continue
            for item in source:
                if not isinstance(item, Mapping):
                    continue
                level = _coerce_level(item.get("liv") or item.get("level"))
                if level is None:
                    continue
                for key in ("per_day", "prepared", "known", "dc"):
                    _update(level, key, _normalize_spell_value(item.get(key)))

        for source_map, target_key in (
            (slots_map, "per_day"),
            (prepared_map, "prepared"),
            (known_map, "known"),
            (dc_map, "dc"),
        ):
            if not isinstance(source_map, Mapping):
                continue
            for raw_level, raw_value in source_map.items():
                level = _coerce_level(raw_level)
                if level is None:
                    continue
                _update(level, target_key, _normalize_spell_value(raw_value))

        return [
            entry for level, entry in sorted(normalized.items(), key=lambda kv: kv[0])
        ]

    def _populate_profile_metadata(target: MutableMapping[str, object]) -> None:
        profile_sources: list[Mapping[str, object]] = []
        for candidate in (
            _as_mapping(target.get("profilo_base")),
            _as_mapping(target.get("base_profile")),
            _as_mapping(export_ctx.get("profilo_base")),
            _as_mapping(export_ctx.get("base_profile")),
            _as_mapping(payload.get("profilo_base")),
            _as_mapping(payload.get("base_profile")),
            _as_mapping(payload.get("build_state")),
            _as_mapping(payload.get("request")),
        ):
            if candidate:
                profile_sources.append(candidate)

        profile_keys: dict[str, tuple[str, ...]] = {
            "nome": ("nome", "name", "character_name"),
            "razza": ("razza", "race"),
            "allineamento": ("allineamento", "alignment"),
            "divinita": ("divinita", "deity"),
            "taglia": ("taglia", "size"),
            "eta": ("eta", "age"),
            "sesso": ("sesso", "sex", "gender"),
            "altezza": ("altezza", "height"),
            "peso": ("peso", "weight"),
            "ruolo": ("ruolo", "role", "role_hint"),
            "player_style": ("player_style",),
            "background": ("background", "background_hooks"),
        }

        for target_key, aliases in profile_keys.items():
            if not _is_placeholder(target.get(target_key)):
                continue
            values: list[object | None] = []
            for source in profile_sources:
                for alias in aliases:
                    values.append(source.get(alias))
            resolved = _first_non_placeholder(*values)
            if resolved is not None:
                target[target_key] = resolved

    def _normalize_statistics_block(*sources: Mapping | None) -> dict[str, object]:
        normalized: dict[str, object] = {}
        for source in sources:
            if not isinstance(source, Mapping):
                continue
            for raw_key, value in source.items():
                key = _normalize_stat_key(raw_key)
                if key is None or _is_placeholder(value):
                    continue
                existing = normalized.get(key)
                if _is_placeholder(existing) or key not in normalized:
                    normalized[key] = value

        return normalized

    sheet_payload: MutableMapping[str, object] = {}
    for candidate in (
        _as_mapping(export_ctx.get("sheet_payload")),
        (
            _as_mapping(payload.get("sheet_payload"))
            if isinstance(payload, Mapping)
            else None
        ),
        _as_mapping(payload.get("sheet")) if isinstance(payload, Mapping) else None,
    ):
        if candidate:
            _merge_prefer_existing(sheet_payload, candidate)

    if ledger and "ledger" not in sheet_payload:
        sheet_payload["ledger"] = ledger

    stats_block = _normalize_statistics_block(
        _as_mapping(sheet_payload.get("statistiche")),
        _as_mapping(export_ctx.get("statistiche")),
        _as_mapping((payload.get("build_state") or {}).get("statistics")),
        _as_mapping((payload.get("benchmark") or {}).get("statistics")),
    )
    if stats_block:
        sheet_payload["statistiche"] = stats_block

    stat_key_block = _as_mapping(sheet_payload.get("statistiche_chiave")) or {}
    benchmark_stats = _as_mapping((payload.get("benchmark") or {}).get("statistics"))
    if benchmark_stats:
        for source_key, target_key in (
            ("ca", "CA"),
            ("attacco", "attacco"),
            ("danni", "danni"),
        ):
            value = benchmark_stats.get(source_key)
            if not _is_placeholder(value) and target_key not in stat_key_block:
                stat_key_block[target_key] = value
    if stat_key_block:
        sheet_payload["statistiche_chiave"] = stat_key_block

    ability_mod_map = {
        "Tempra": _ability_modifier(stats_block.get("COS")) if stats_block else None,
        "Riflessi": _ability_modifier(stats_block.get("DES")) if stats_block else None,
        "Volontà": _ability_modifier(stats_block.get("SAG")) if stats_block else None,
    }
    strength_mod = _ability_modifier(stats_block.get("FOR")) if stats_block else None

    _populate_profile_metadata(sheet_payload)

    salvezze_raw = _merge_prefer_existing(
        {},
        _as_mapping(sheet_payload.get("salvezze")) or {},
        _as_mapping(export_ctx.get("salvezze")) or {},
        _as_mapping((payload.get("build_state") or {}).get("saves")) or {},
        _as_mapping((payload.get("benchmark") or {}).get("saves")) or {},
    )
    saves_breakdown = _merge_prefer_existing(
        {},
        _as_mapping(export_ctx.get("salvezze_breakdown")) or {},
        _as_mapping((payload.get("build_state") or {}).get("saves_breakdown")) or {},
    )
    normalized_saves: dict[str, object] = {}
    for name in ("Tempra", "Riflessi", "Volontà"):
        normalized_entry = _normalize_save_entry(
            salvezze_raw.get(name),
            _as_mapping(saves_breakdown.get(name))
            or _as_mapping(saves_breakdown.get(name.lower())),
            label=f"TS {name}",
        )
        normalized_saves[name] = normalized_entry
    for extra_key, value in salvezze_raw.items():
        if extra_key in normalized_saves:
            continue
        normalized_entry = _normalize_save_entry(
            value, _as_mapping(saves_breakdown.get(extra_key))
        )
        normalized_saves[extra_key] = normalized_entry
    for save_name, save_entry in normalized_saves.items():
        total_value = _coerce_number(save_entry.get("totale"))
        if save_name in ability_mod_map and save_entry.get("modificatore") is None:
            ability_mod = ability_mod_map.get(save_name)
            if ability_mod is not None:
                save_entry["modificatore"] = ability_mod
        misc_value = _coerce_number(save_entry.get("misc"))
        if misc_value is None:
            save_entry["misc"] = 0
            misc_value = 0
        base_value = _coerce_number(save_entry.get("base"))
        if base_value is None and isinstance(total_value, (int, float)):
            mod_value = _coerce_number(save_entry.get("modificatore"))
            if isinstance(mod_value, (int, float)):
                save_entry["base"] = total_value - mod_value - (misc_value or 0)
        if total_value is None:
            base_value = _coerce_number(save_entry.get("base"))
            mod_value = _coerce_number(save_entry.get("modificatore"))
            if isinstance(base_value, (int, float)):
                parts = [base_value]
                if isinstance(mod_value, (int, float)):
                    parts.append(mod_value)
                if isinstance(misc_value, (int, float)):
                    parts.append(misc_value)
                if parts:
                    save_entry["totale"] = sum(parts)

    saves_totals: dict[str, object] = {
        key: value.get("totale") if isinstance(value, Mapping) else None
        for key, value in normalized_saves.items()
    }
    if not any(
        isinstance(value, (int, float)) and value != 0
        for value in saves_totals.values()
    ):
        for key, value in list(saves_totals.items()):
            if value in {None, 0} or _is_placeholder(value):
                placeholder_label = f"TS {key}"
                saves_totals[key] = _fallback_stat(placeholder_label)
                if key in normalized_saves:
                    normalized_saves[key]["totale"] = saves_totals[key]
    sheet_payload["salvezze_breakdown"] = normalized_saves
    sheet_payload["salvezze"] = saves_totals

    hp_block = _merge_prefer_existing(
        {},
        _as_mapping(export_ctx.get("hp")) or {},
        _as_mapping(payload.get("hp")) or {},
        _as_mapping((payload.get("build_state") or {}).get("hp")) or {},
    )
    if hp_block:
        sheet_payload["hp"] = hp_block
    pf_total = _first_non_placeholder(
        sheet_payload.get("pf_totali"),
        hp_block.get("totale") if hp_block else None,
        hp_block.get("total") if hp_block else None,
        hp_block.get("hp_total") if hp_block else None,
        (
            (sheet_payload.get("statistiche_chiave") or {}).get("PF")
            if isinstance(sheet_payload.get("statistiche_chiave"), Mapping)
            else None
        ),
    )
    if isinstance(pf_total, (int, float)) and pf_total == 0:
        pf_total = None
    if pf_total is not None:
        sheet_payload["pf_totali"] = pf_total
    elif hp_block:
        sheet_payload["pf_totali"] = hp_block.get("totale") or _fallback_stat(
            "PF totali"
        )
    else:
        sheet_payload["pf_totali"] = _fallback_stat("PF totali")
    pf_progression = _first_non_placeholder(
        sheet_payload.get("pf_per_livello"),
        hp_block.get("per_livello") if hp_block else None,
        hp_block.get("per_level") if hp_block else None,
        hp_block.get("progressione") if hp_block else None,
    )
    if pf_progression is not None:
        sheet_payload["pf_per_livello"] = pf_progression
    elif sheet_payload.get("pf_totali"):
        sheet_payload.setdefault(
            "pf_per_livello",
            _fallback_stat("PF per livello"),
        )

    derived_core = _as_mapping(export_ctx.get("derived")) or _as_mapping(
        (payload.get("build_state") or {}).get("derived")
    )
    derived_core = derived_core or _as_mapping((derived_core or {}).get("core")) or {}

    ac_breakdown = _merge_prefer_existing(
        {},
        _as_mapping(sheet_payload.get("ac_breakdown")) or {},
        _as_mapping(export_ctx.get("ac_breakdown")) or {},
        _as_mapping((payload.get("build_state") or {}).get("ac")) or {},
        _as_mapping((derived_core or {}).get("ac")) or {},
    )
    if ac_breakdown:
        sheet_payload["ac_breakdown"] = ac_breakdown
    stat_key_block = _as_mapping(sheet_payload.get("statistiche_chiave")) or {}
    ac_defaults = {
        "AC_arm": 0,
        "AC_scudo": 0,
        "AC_des": 0,
        "AC_defl": 0,
        "AC_nat": 0,
        "AC_dodge": 0,
        "AC_misc": 0,
    }
    for ac_key, default in ac_defaults.items():
        value = _first_non_placeholder(
            sheet_payload.get(ac_key),
            ac_breakdown.get(ac_key) if ac_breakdown else None,
        )
        if value is None:
            value = default
        sheet_payload[ac_key] = value
    ac_base = _first_non_placeholder(
        sheet_payload.get("AC_base"),
        ac_breakdown.get("AC_base") if ac_breakdown else None,
        10,
    )
    if ac_base is not None:
        sheet_payload["AC_base"] = ac_base
    for ca_key in ("AC_tot", "CA_touch", "CA_ff"):
        derived = _first_non_placeholder(
            ac_breakdown.get(ca_key) if ac_breakdown else None,
            (
                stat_key_block.get(ca_key.lower())
                if isinstance(stat_key_block.get(ca_key.lower()), (int, float))
                else None
            ),
            stat_key_block.get(ca_key),
            stat_key_block.get("ca") if ca_key == "AC_tot" else None,
            sheet_payload.get(ca_key),
        )
        existing_value = sheet_payload.get(ca_key)
        if derived is not None and (
            ca_key not in sheet_payload
            or _is_placeholder(existing_value)
            or ((not ac_breakdown) and existing_value in {0, 10})
        ):
            sheet_payload[ca_key] = derived

    if "AC_tot" not in sheet_payload:
        sheet_payload["AC_tot"] = ac_base + sum(
            sheet_payload.get(ac_key, 0) for ac_key in ac_defaults
        )
    if sheet_payload.get("AC_tot") in {None, 0}:
        sheet_payload["AC_tot"] = _fallback_stat("CA totale")
    if "CA_touch" not in sheet_payload:
        sheet_payload["CA_touch"] = (
            ac_base
            + sheet_payload.get("AC_des", 0)
            + sheet_payload.get("AC_defl", 0)
            + sheet_payload.get("AC_dodge", 0)
            + sheet_payload.get("AC_misc", 0)
        )
    if "CA_ff" not in sheet_payload:
        sheet_payload["CA_ff"] = (
            ac_base
            + sheet_payload.get("AC_arm", 0)
            + sheet_payload.get("AC_scudo", 0)
            + sheet_payload.get("AC_nat", 0)
            + sheet_payload.get("AC_defl", 0)
            + sheet_payload.get("AC_misc", 0)
        )

    bab = _first_non_placeholder(
        sheet_payload.get("BAB"),
        export_ctx.get("BAB") or export_ctx.get("bab"),
        (payload.get("build_state") or {}).get("bab"),
        (payload.get("benchmark") or {}).get("bab"),
        (derived_core or {}).get("bab_total"),
        (derived_core or {}).get("bab_base"),
    )
    if bab is None:
        sheet_payload["BAB"] = _fallback_stat("BAB")
    else:
        sheet_payload["BAB"] = bab

    initiative = _first_non_placeholder(
        sheet_payload.get("iniziativa"),
        export_ctx.get("iniziativa"),
        stat_key_block.get("iniziativa"),
        stat_key_block.get("init"),
        (payload.get("build_state") or {}).get("initiative"),
        (payload.get("benchmark") or {}).get("initiative"),
        (derived_core or {}).get("initiative_mod"),
        (derived_core or {}).get("initiative_total"),
    )
    if initiative is not None:
        sheet_payload["iniziativa"] = initiative
        if _is_placeholder(sheet_payload.get("init")):
            sheet_payload["init"] = initiative

    cmb_sources = _merge_prefer_existing(
        {},
        _as_mapping(export_ctx.get("cmb")) or {},
        _as_mapping((payload.get("build_state") or {}).get("cmb")) or {},
        _as_mapping((derived_core or {}).get("cmb")) or {},
    )
    size_mod_cmd = _coerce_number(sheet_payload.get("size_mod_cmd"))
    cmb_misc_bonus = _coerce_number(sheet_payload.get("cmb_misc"))
    cmb_value = _first_non_placeholder(
        sheet_payload.get("CMB"),
        cmb_sources.get("total") if cmb_sources else None,
        (derived_core or {}).get("cmb_total"),
        cmb_sources.get("base") if cmb_sources else None,
        (derived_core or {}).get("cmb_base"),
    )
    cmb_total = _coerce_number(cmb_value)
    if cmb_total is None:
        bab_value = _coerce_number(sheet_payload.get("BAB"))
        if isinstance(bab_value, (int, float)) and strength_mod is not None:
            parts = [bab_value, strength_mod]
            if isinstance(size_mod_cmd, (int, float)):
                parts.append(size_mod_cmd)
            if isinstance(cmb_misc_bonus, (int, float)):
                parts.append(cmb_misc_bonus)
            cmb_total = sum(parts)
    if cmb_total is not None and (
        "CMB" not in sheet_payload or _is_placeholder(sheet_payload.get("CMB"))
    ):
        sheet_payload["CMB"] = cmb_total
    if "CMB" not in sheet_payload:
        sheet_payload["CMB"] = _fallback_stat("CMB")

    cmb_base_value = _coerce_number(sheet_payload.get("CMB"))
    for cmb_key in ("cmb_disarm", "cmb_trip", "cmb_grapple"):
        derived_variant = _first_non_placeholder(
            sheet_payload.get(cmb_key),
            cmb_sources.get(cmb_key) if cmb_sources else None,
            (derived_core or {}).get(cmb_key),
        )
        variant_numeric = _coerce_number(derived_variant)
        if variant_numeric is None and isinstance(cmb_base_value, (int, float)):
            sheet_payload[cmb_key] = cmb_base_value
        elif derived_variant is not None and (
            cmb_key not in sheet_payload or _is_placeholder(sheet_payload.get(cmb_key))
        ):
            sheet_payload[cmb_key] = derived_variant
        elif cmb_key not in sheet_payload:
            friendly_label = cmb_key.replace("_", " ")
            sheet_payload[cmb_key] = _fallback_stat(friendly_label)

    speed = _first_non_placeholder(
        sheet_payload.get("velocita"),
        export_ctx.get("velocita") or export_ctx.get("speed"),
        stat_key_block.get("velocita"),
        stat_key_block.get("speed"),
        (payload.get("build_state") or {}).get("speed"),
        (derived_core or {}).get("speed_total"),
        (derived_core or {}).get("speed_base"),
    )
    if speed is not None:
        sheet_payload["velocita"] = speed
        if _is_placeholder(sheet_payload.get("speed")):
            sheet_payload["speed"] = speed

    skill_points = _first_non_placeholder(
        sheet_payload.get("skill_points"),
        (payload.get("build_state") or {}).get("skill_points"),
        (payload.get("benchmark") or {}).get("skill_points"),
    )
    if skill_points is not None:
        sheet_payload["skill_points"] = skill_points

    skills_map = _merge_prefer_existing(
        {},
        _as_mapping(sheet_payload.get("skills_map")) or {},
        _as_mapping(export_ctx.get("skills_map")) or {},
        _as_mapping((payload.get("build_state") or {}).get("skills_map")) or {},
        _as_mapping((derived_core or {}).get("skills_by_name")) or {},
    )
    if skills_map:
        sheet_payload["skills_map"] = skills_map

    skills_list = _merge_unique_list(
        sheet_payload.get("skills"),
        export_ctx.get("skills"),
        (payload.get("build_state") or {}).get("skills"),
    )
    if skills_list:
        sheet_payload["skills"] = skills_list

    feats = _merge_unique_list(
        sheet_payload.get("talenti"),
        export_ctx.get("talenti"),
        (payload.get("build_state") or {}).get("feats"),
        [
            p.get("talento")
            for p in sheet_payload.get("progressione", [])
            if isinstance(p, Mapping) and p.get("talento")
        ],
    )
    if feats:
        sheet_payload["talenti"] = feats

    class_features = _merge_unique_list(
        sheet_payload.get("capacita_classe"),
        export_ctx.get("capacita_classe"),
        (payload.get("build_state") or {}).get("class_features"),
        [
            priv
            for entry in sheet_payload.get("progressione", [])
            if isinstance(entry, Mapping)
            for priv in (
                entry.get("privilegi")
                if isinstance(entry.get("privilegi"), Sequence)
                and not isinstance(entry.get("privilegi"), (str, bytes))
                else [entry.get("privilegi")]
            )
            if priv
        ],
    )
    if class_features:
        sheet_payload["capacita_classe"] = class_features

    progression = _merge_unique_list(
        sheet_payload.get("progressione"),
        export_ctx.get("progressione") or export_ctx.get("progression"),
        payload.get("progressione") if isinstance(payload, Mapping) else None,
        (payload.get("build_state") or {}).get("progression"),
    )
    if progression:
        sheet_payload["progressione"] = progression

    equip_list = _merge_unique_list(
        sheet_payload.get("equipaggiamento"),
        export_ctx.get("equipaggiamento"),
        (
            (payload.get("ledger") or {}).get("equipaggiamento")
            if isinstance(payload.get("ledger"), Mapping)
            else None
        ),
    )
    if equip_list:
        sheet_payload["equipaggiamento"] = equip_list

    equipment_summary = _merge_prefer_existing(
        {},
        _as_mapping(sheet_payload.get("equipment_summary")) or {},
        _as_mapping(export_ctx.get("equipment_summary")) or {},
        (
            _as_mapping((payload.get("ledger") or {}).get("equipment_summary"))
            if isinstance(payload.get("ledger"), Mapping)
            else {}
        ),
    )
    if equipment_summary:
        sheet_payload["equipment_summary"] = equipment_summary

    inventory = _merge_unique_list(
        sheet_payload.get("inventario"),
        export_ctx.get("inventario"),
        (
            (payload.get("ledger") or {}).get("inventario")
            if isinstance(payload.get("ledger"), Mapping)
            else None
        ),
    )
    if inventory:
        sheet_payload["inventario"] = inventory

    def _normalize_currency(currency: Mapping | None) -> dict[str, object]:
        if not isinstance(currency, Mapping):
            return {}
        normalized: dict[str, object] = {}
        aliases = {
            "pp": ("pp", "platino", "platinum"),
            "gp": ("gp", "oro", "gold"),
            "sp": ("sp", "argento", "silver"),
            "cp": ("cp", "rame", "copper"),
        }
        for target, keys in aliases.items():
            for key in keys:
                if key in currency and not _is_placeholder(currency.get(key)):
                    normalized[target] = currency.get(key)
                    break
        return normalized

    if ledger:
        ledger_currency = _normalize_currency(_as_mapping(ledger.get("currency")))
        if ledger_currency:
            sheet_payload.setdefault("currency", ledger_currency)
            for key, value in ledger_currency.items():
                sheet_payload.setdefault(key, value)
        movements = _merge_unique_list(
            sheet_payload.get("ledger_movimenti"), ledger.get("movimenti")
        )
        if movements:
            sheet_payload["ledger_movimenti"] = movements

    magic_map = _merge_prefer_existing(
        {},
        _as_mapping(sheet_payload.get("magia")) or {},
        _as_mapping(export_ctx.get("magia")) or {},
        _as_mapping((payload.get("build_state") or {}).get("magia")) or {},
    )

    spell_list = _merge_prefer_existing(
        {},
        _as_mapping(magic_map.get("spell_list")) or {},
        _as_mapping(export_ctx.get("spell_list")) or {},
        _as_mapping((payload.get("build_state") or {}).get("spell_list")) or {},
    )
    if spell_list:
        magic_map["spell_list"] = spell_list

    spells_prepared = _merge_prefer_existing(
        {},
        _as_mapping(magic_map.get("spells_prepared")) or {},
        _as_mapping(export_ctx.get("spells_prepared")) or {},
        _as_mapping((payload.get("build_state") or {}).get("spells_prepared")) or {},
    )
    if spells_prepared:
        magic_map["spells_prepared"] = spells_prepared

    slots_per_day = _merge_prefer_existing(
        {},
        _as_mapping(magic_map.get("slots_per_day")) or {},
        _as_mapping(export_ctx.get("slots_per_day")) or {},
        _as_mapping((payload.get("build_state") or {}).get("slots_per_day")) or {},
        _as_mapping((payload.get("build_state") or {}).get("spell_slots")) or {},
    )
    if slots_per_day:
        magic_map["slots_per_day"] = slots_per_day

    spell_dc_map = _merge_prefer_existing(
        {},
        _as_mapping(magic_map.get("cd_by_level")) or {},
        _as_mapping(export_ctx.get("spell_dc")) or {},
        _as_mapping(export_ctx.get("cd_by_level")) or {},
    )
    if spell_dc_map:
        magic_map["cd_by_level"] = spell_dc_map

    if magic_map:
        sheet_payload["magia"] = magic_map

    slot_text = _first_non_placeholder(
        sheet_payload.get("slot_incantesimi"), export_ctx.get("slot_incantesimi")
    )
    if slot_text is not None:
        sheet_payload["slot_incantesimi"] = slot_text

    normalized_spell_levels = _normalize_spell_levels(
        _merge_unique_list(
            sheet_payload.get("spell_levels"),
            export_ctx.get("spell_levels"),
        ),
        slots_map=_as_mapping(magic_map.get("slots_per_day")) if magic_map else None,
        prepared_map=(
            _as_mapping(magic_map.get("spells_prepared")) if magic_map else None
        ),
        known_map=_as_mapping(magic_map.get("spell_list")) if magic_map else None,
        dc_map=_as_mapping(magic_map.get("cd_by_level")) if magic_map else None,
    )

    if not normalized_spell_levels and slot_text:
        normalized_spell_levels = _normalize_spell_levels(
            slots_map=_parse_slots_from_text(slot_text)
        )

    if normalized_spell_levels:
        sheet_payload["spell_levels"] = normalized_spell_levels

    if not sheet_payload.get("magia") and normalized_spell_levels:
        magia_from_levels: dict[str, object] = {}
        for entry in normalized_spell_levels:
            if not isinstance(entry, Mapping):
                continue
            level = entry.get("liv") or entry.get("level")
            spells = entry.get("known") or entry.get("prepared") or entry.get("per_day")
            if level is None or spells is None:
                continue
            magia_from_levels[str(level)] = spells
        if magia_from_levels:
            sheet_payload["magia"] = magia_from_levels

    languages = _merge_unique_list(
        sheet_payload.get("lingue"),
        export_ctx.get("lingue"),
        (payload.get("build_state") or {}).get("languages"),
    )
    if languages:
        sheet_payload["lingue"] = languages

    senses = _merge_unique_list(
        sheet_payload.get("sensi"),
        export_ctx.get("sensi"),
        (payload.get("build_state") or {}).get("senses"),
    )
    if senses:
        sheet_payload["sensi"] = senses

    conditions = _merge_unique_list(
        sheet_payload.get("condizioni"),
        export_ctx.get("condizioni"),
        (payload.get("build_state") or {}).get("conditions"),
    )
    if conditions:
        sheet_payload["condizioni"] = conditions

    module_payloads = _merge_prefer_existing(
        {},
        _as_mapping(sheet_payload.get("modules")) or {},
        _as_mapping(export_ctx.get("modules")) or {},
        _as_mapping(payload.get("modules")) or {},
        _load_local_modules(SHEET_MODULE_TARGETS),
    )

    allowed_sheet_modules = {
        name: module_payloads.get(name) for name in SHEET_MODULE_TARGETS
    }
    filtered_modules = {k: v for k, v in allowed_sheet_modules.items() if v}

    if filtered_modules:
        sheet_payload["modules"] = filtered_modules

    rendered_sheet = None
    template_source = allowed_sheet_modules.get("scheda_pg_markdown_template.md")
    if template_source:
        try:
            rendered_sheet = _render_sheet_template(template_source, sheet_payload)
        except Exception as exc:  # pragma: no cover - defensive
            error_message = f"Rendering scheda_pg_markdown_template.md fallita: {exc}"
            logging.warning(error_message)
            sheet_payload["sheet_render_error"] = error_message

    if rendered_sheet:
        rendered_sheet = textwrap.dedent(rendered_sheet).strip()
        if rendered_sheet:
            sheet_payload["sheet_markdown"] = rendered_sheet

    sources = _merge_unique_list(
        sheet_payload.get("fonti"), [source_url] if source_url else []
    )
    if sources:
        sheet_payload["fonti"] = sources

    sheet_payload.setdefault("print_mode", False)
    sheet_payload.setdefault("show_minmax", True)
    sheet_payload.setdefault("show_vtt", True)
    sheet_payload.setdefault("show_qa", True)
    sheet_payload.setdefault("show_explain", True)
    sheet_payload.setdefault("show_ledger", True)
    sheet_payload.setdefault("decimal_comma", True)
    sheet_payload.setdefault("salvezze", {})
    sheet_payload.setdefault("skills_map", {})
    sheet_payload.setdefault("skills", [])
    sheet_payload.setdefault("spell_levels", [])
    sheet_payload.setdefault("magia", {})
    sheet_payload.setdefault("lingue", [])
    sheet_payload.setdefault("sensi", [])
    sheet_payload.setdefault("condizioni", [])
    sheet_payload.setdefault("equipaggiamento", [])
    sheet_payload.setdefault("inventario", [])
    sheet_payload.setdefault("talenti", [])
    sheet_payload.setdefault("capacita_classe", [])
    sheet_payload.setdefault("progressione", [])
    sheet_payload.setdefault("velocita", 0)
    sheet_payload.setdefault("iniziativa", 0)
    sheet_payload.setdefault("pf_totali", 0)
    sheet_payload.setdefault("skill_points", 0)
    sheet_payload.setdefault("CMB", 0)
    sheet_payload.setdefault("cmb_disarm", sheet_payload.get("CMB"))
    sheet_payload.setdefault("cmb_trip", sheet_payload.get("CMB"))
    sheet_payload.setdefault("cmb_grapple", sheet_payload.get("CMB"))

    return sheet_payload


def _stringify_sequence(values: object, *, limit: int | None = None) -> list[str]:
    """Converti una sequenza generica in un elenco di stringhe pulite."""

    if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
        return []

    normalized: list[str] = []
    for item in values:
        if isinstance(item, Mapping):
            candidate = item.get("name") or item.get("label") or item.get("id")
            normalized.append(str(candidate)) if candidate else None
        else:
            normalized.append(str(item))

        if limit is not None and len(normalized) >= limit:
            break

    return [value.strip() for value in normalized if value and value.strip()]


def _normalize_badge_value(badge: object) -> str | None:
    if isinstance(badge, str):
        return badge.strip().lower() or None
    if isinstance(badge, Mapping):
        for key in ("label", "value", "badge"):
            candidate = badge.get(key)
            if isinstance(candidate, str):
                return candidate.strip().lower() or None
    return None


def _ruling_context_from_payload(
    payload: Mapping[str, Any], request: BuildRequest
) -> Mapping[str, object]:
    export = payload.get("export") if isinstance(payload, Mapping) else None
    sheet_payload = export.get("sheet_payload") if isinstance(export, Mapping) else None
    talents = []
    if isinstance(sheet_payload, Mapping):
        talents = _stringify_sequence(sheet_payload.get("talenti"), limit=5)

    hr_sources: object | None = None
    meta_sources: object | None = None
    pfs_mode: object | None = None
    if isinstance(sheet_payload, Mapping):
        hr_sources = sheet_payload.get("hr_sources")
        meta_sources = sheet_payload.get("meta_sources")
        pfs_mode = sheet_payload.get("pfs_mode")

    return {
        "class": payload.get("class") or request.class_name,
        "level": payload.get("request", {}).get("level") or request.level,
        "talenti_chiave": talents,
        "hr_sources": hr_sources,
        "meta_sources": meta_sources,
        "pfs_mode": pfs_mode,
    }


def _pfs_blocks_homebrew(context: Mapping[str, object]) -> bool:
    pfs_mode = str(context.get("pfs_mode") or "").lower()
    pfs_active = pfs_mode in {"true", "on", "yes", "1", "active", "pfs"}
    hr_present = bool(context.get("hr_sources"))
    meta_present = bool(context.get("meta_sources"))
    return bool(pfs_active and (hr_present or meta_present))


@dataclass
class RulingCache:
    path: Path
    data: dict[str, dict[str, Any]] = field(default_factory=dict)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    dirty: bool = False

    @classmethod
    def load(cls, path: Path) -> "RulingCache":
        try:
            if path.is_file():
                raw = path.read_text(encoding="utf-8")
                loaded = json.loads(raw) if raw.strip() else {}
                if isinstance(loaded, dict):
                    return cls(path=path, data=loaded)
        except Exception as exc:  # pragma: no cover - defensive logging only
            logger.warning("Impossibile leggere ruling cache %s: %s", path, exc)
        return cls(path=path)

    async def get(self, key: str) -> dict[str, Any] | None:
        async with self.lock:
            value = self.data.get(key)
            return value if isinstance(value, dict) else None

    async def set(self, key: str, value: dict[str, Any] | object) -> None:
        async with self.lock:
            self.data[key] = (
                dict(value) if isinstance(value, dict) else {"value": value}
            )
            self.dirty = True

    async def flush(self) -> None:
        async with self.lock:
            if not self.dirty:
                return
            try:
                tmp = self.path.with_suffix(self.path.suffix + ".tmp")
                tmp.write_text(
                    json.dumps(self.data, ensure_ascii=False, indent=2, sort_keys=True),
                    encoding="utf-8",
                )
                tmp.replace(self.path)
                self.dirty = False
            except Exception as exc:  # pragma: no cover - defensive logging only
                logger.warning(
                    "Impossibile scrivere ruling cache %s: %s", self.path, exc
                )


def _ruling_cache_key(
    payload: Mapping[str, Any], context: Mapping[str, Any]
) -> str | None:
    core: Any = payload.get("composite")
    if not isinstance(core, Mapping):
        core = {
            "build": payload.get("build_state"),
            "benchmark": payload.get("benchmark"),
            "export": payload.get("export"),
        }
    try:
        raw = json.dumps(
            {"context": context, "core": core},
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
            default=str,
        )
    except TypeError:
        return None
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


async def _validate_ruling_badge(
    client: httpx.AsyncClient,
    *,
    url: str | None,
    api_key: str | None,
    payload: MutableMapping,
    request: BuildRequest,
    timeout: float,
    max_retries: int,
    cache: RulingCache | None = None,
    semaphore: asyncio.Semaphore | None = None,
) -> tuple[str, object | None]:
    if not url:
        raise BuildFetchError("Endpoint Ruling Expert obbligatorio per il salvataggio")

    context = _ruling_context_from_payload(payload, request)

    if _pfs_blocks_homebrew(context):
        raise BuildFetchError(
            "PFS attivo: HR/META rilevati e non ammessi per lo snapshot",
        )

    cache_key: str | None = None
    if cache is not None:
        cache_key = _ruling_cache_key(payload, context)
        if cache_key:
            cached = await cache.get(cache_key)
            if cached:
                cached_badge = _normalize_badge_value(
                    cached.get("badge")
                    or cached.get("ruling_badge")
                    or cached.get("rulingBadge")
                )
                cached_sources = (
                    cached.get("sources")
                    or cached.get("ruling_sources")
                    or cached.get("rulingSources")
                )
                if cached_badge:
                    payload["ruling_badge"] = cached_badge
                    if cached_sources:
                        payload["ruling_sources"] = cached_sources
                    payload.setdefault("qa", {})["ruling_expert"] = {
                        "badge": cached_badge,
                        "sources": cached_sources,
                        "context": context,
                        "cached": True,
                        "cache_key": cache_key,
                    }
                    return cached_badge, cached_sources

    headers = {"x-api-key": api_key} if api_key else {}
    if semaphore is not None:
        async with semaphore:
            response = await request_with_retry(
                client,
                "POST",
                url,
                headers=headers,
                json_body={"build": payload, "context": context},
                timeout=timeout,
                max_retries=max_retries,
                backoff_factor=0.5,
            )
    else:
        response = await request_with_retry(
            client,
            "POST",
            url,
            headers=headers,
            json_body={"build": payload, "context": context},
            timeout=timeout,
            max_retries=max_retries,
            backoff_factor=0.5,
        )

    try:
        data = response.json()
    except json.JSONDecodeError as exc:  # pragma: no cover - network dependent
        raise BuildFetchError("Risposta Ruling Expert non JSON") from exc

    violations = data.get("violations") if isinstance(data, Mapping) else None
    if violations:
        raise BuildFetchError(
            "Violazioni Ruling Expert: " + "; ".join(map(str, violations))
        )

    badge = data.get("ruling_badge") if isinstance(data, Mapping) else None
    badge = badge or (data.get("badge") if isinstance(data, Mapping) else None)
    normalized_badge = _normalize_badge_value(badge)
    if not normalized_badge:
        raise BuildFetchError("Badge Ruling Expert mancante o non conforme")

    sources = data.get("sources") if isinstance(data, Mapping) else None
    sources = sources or (data.get("fonti") if isinstance(data, Mapping) else None)

    payload["ruling_badge"] = normalized_badge
    if sources:
        payload["ruling_sources"] = sources
    payload.setdefault("qa", {})["ruling_expert"] = {
        "badge": normalized_badge,
        "sources": sources,
        "context": context,
        "raw": data,
        "cached": False,
        "cache_key": cache_key,
    }
    if cache is not None and cache_key and normalized_badge:
        await cache.set(
            cache_key,
            {
                "badge": normalized_badge,
                "sources": sources,
                "validated_at": datetime.now(timezone.utc).isoformat(),
            },
        )

    return normalized_badge, sources


def _apply_level_checkpoint(
    payload: MutableMapping[str, object], target_level: int | None
) -> None:
    if target_level is None:
        return

    export_ctx = payload.get("export") if isinstance(payload, Mapping) else None
    sheet_payload = None
    if isinstance(export_ctx, Mapping):
        sheet_payload = export_ctx.get("sheet_payload")
    if sheet_payload is None and isinstance(payload.get("sheet_payload"), Mapping):
        sheet_payload = payload.get("sheet_payload")

    if not isinstance(sheet_payload, MutableMapping):
        return

    truncated_progression = _truncate_sequence_by_level(
        sheet_payload.get("progressione"), target_level
    )
    if truncated_progression is not None:
        sheet_payload["progressione"] = truncated_progression

        notes = sheet_payload.get("note_progressione")
        if isinstance(notes, Sequence) and not isinstance(notes, (str, bytes)):
            sheet_payload["note_progressione"] = list(notes)[
                : len(truncated_progression)
            ]

    for key in ("magia", "equipaggiamento"):
        truncated = _truncate_sequence_by_level(sheet_payload.get(key), target_level)
        if truncated is not None:
            sheet_payload[key] = truncated


def _normalize_build_payload(
    payload: MutableMapping[str, object],
    *,
    request: BuildRequest | None = None,
    reference_catalog_version: str | None = None,
    manifest_version: str | None = None,
    target_level: int | None = None,
    normalized_mode: str | None = None,
) -> MutableMapping[str, object]:
    if not isinstance(payload, MutableMapping):
        return payload

    catalog_version = _coerce_catalog_version(
        payload.get("reference_catalog_version"),
        reference_catalog_version,
        manifest_version,
    )
    if catalog_version:
        payload["reference_catalog_version"] = str(catalog_version)

    request_ctx: dict[str, object] = (
        request.metadata()
        if request
        else (
            dict(payload.get("request"))
            if isinstance(payload.get("request"), Mapping)
            else {}
        )
    )
    build_state = payload.get("build_state")
    build_state = dict(build_state) if isinstance(build_state, Mapping) else {}
    payload["build_state"] = build_state

    state_level = build_state.pop("level", None)
    state_checkpoints = build_state.pop("level_checkpoints", None)
    state_checkpoint = build_state.pop("checkpoint", None)

    normalized_mode_value = normalize_mode(
        request_ctx.get("mode")
        or payload.get("mode")
        or build_state.get("mode")
        or normalized_mode
        or DEFAULT_MODE
    )
    payload["mode"] = (
        payload.get("mode") or request_ctx.get("mode") or normalized_mode_value
    )
    payload.setdefault("mode_normalized", normalized_mode_value)

    if request_ctx.get("class") and not payload.get("class"):
        payload["class"] = request_ctx["class"]

    race_value = (
        payload.pop("race", None)
        or request_ctx.get("race")
        or build_state.get("race")
        or request_ctx.get("query_params", {}).get("race")
    )
    archetype_value = (
        payload.pop("archetype", None)
        or request_ctx.get("archetype")
        or build_state.get("archetype")
        or request_ctx.get("query_params", {}).get("archetype")
    )
    if race_value is not None:
        build_state.setdefault("race", race_value)
        request_ctx.setdefault("race", race_value)
    if archetype_value is not None:
        build_state.setdefault("archetype", archetype_value)
        request_ctx.setdefault("archetype", archetype_value)

    if target_level is not None:
        request_ctx.setdefault("level", target_level)
    if state_level is not None and "level" not in request_ctx:
        request_ctx["level"] = state_level
    stray_level = payload.pop("level", None)
    if stray_level is not None and "level" not in request_ctx:
        request_ctx["level"] = stray_level

    normalized_checkpoints = _normalize_levels(
        request_ctx.get("level_checkpoints"), (1, 5, 10)
    )
    if state_checkpoints and not request_ctx.get("level_checkpoints"):
        request_ctx["level_checkpoints"] = _normalize_levels(
            state_checkpoints, normalized_checkpoints or (1, 5, 10)
        )
    if normalized_checkpoints:
        request_ctx["level_checkpoints"] = normalized_checkpoints
    stray_checkpoints = payload.pop("level_checkpoints", None)
    if stray_checkpoints:
        request_ctx["level_checkpoints"] = _normalize_levels(
            stray_checkpoints, normalized_checkpoints or (1, 5, 10)
        )

    build_state.setdefault("mode", normalized_mode_value)
    if request_ctx.get("class"):
        build_state.setdefault("class", request_ctx["class"])

    step_total: int | None
    try:
        step_total = (
            int(build_state["step_total"])
            if "step_total" in build_state
            else expected_step_total_for_mode(normalized_mode_value)
        )
    except (TypeError, ValueError):
        step_total = expected_step_total_for_mode(normalized_mode_value)
    build_state["step_total"] = step_total

    step_labels = (
        build_state.get("step_labels")
        if isinstance(build_state.get("step_labels"), Mapping)
        else None
    )
    if not step_labels:
        build_state["step_labels"] = {
            str(idx): f"Step {idx}" for idx in range(1, step_total + 1)
        }
        step_labels = build_state["step_labels"]
    if isinstance(step_labels, Mapping):
        build_state.setdefault("step_labels_count", len(step_labels))

    benchmark_ctx = (
        dict(payload.get("benchmark"))
        if isinstance(payload.get("benchmark"), Mapping)
        else {}
    )
    bench_log = benchmark_ctx.pop("bench_log", None)
    payload["benchmark"] = benchmark_ctx

    completeness_ctx = (
        dict(payload.get("completeness"))
        if isinstance(payload.get("completeness"), Mapping)
        else {}
    )
    payload["completeness"] = completeness_ctx
    relocated_from_completeness: dict[str, object] = {}
    for key in (
        "bench_log",
        "missing",
        "status",
        "checkpoint",
        "checklist",
        "level",
        "level_checkpoints",
    ):
        value = completeness_ctx.pop(key, None)
        if value is not None:
            relocated_from_completeness[key] = value

    qa_ctx = dict(payload.get("qa")) if isinstance(payload.get("qa"), Mapping) else {}
    checkpoints_ctx = (
        dict(qa_ctx.get("checkpoints"))
        if isinstance(qa_ctx.get("checkpoints"), Mapping)
        else {}
    )
    state_relocations: dict[str, object] = {}
    if bench_log is not None and "bench_log" not in checkpoints_ctx:
        checkpoints_ctx["bench_log"] = bench_log
    if state_checkpoint is not None:
        state_relocations["checkpoint"] = state_checkpoint
    for key in ("bench_log", "missing", "status"):
        value = payload.pop(key, None)
        if value is not None and key not in checkpoints_ctx:
            checkpoints_ctx[key] = value
    for key, value in relocated_from_completeness.items():
        if key not in checkpoints_ctx:
            checkpoints_ctx[key] = value
    for key, value in state_relocations.items():
        if key not in checkpoints_ctx:
            checkpoints_ctx[key] = value
    if request_ctx.get("level") is not None and "level" not in checkpoints_ctx:
        checkpoints_ctx["level"] = request_ctx.get("level")
    if request_ctx.get("level_checkpoints") and "levels" not in checkpoints_ctx:
        checkpoints_ctx["levels"] = list(request_ctx["level_checkpoints"])
    if checkpoints_ctx:
        qa_ctx["checkpoints"] = checkpoints_ctx
    if qa_ctx:
        payload["qa"] = qa_ctx

    payload["request"] = request_ctx

    build_id = payload.get("build_id")
    if not isinstance(build_id, str) or not build_id.strip():
        seed = json.dumps(
            {
                "class": build_state.get("class"),
                "mode": normalized_mode_value,
                "level": request_ctx.get("level"),
                "race": build_state.get("race"),
                "archetype": build_state.get("archetype"),
                "levels": request_ctx.get("level_checkpoints"),
            },
            sort_keys=True,
            default=str,
        ).encode("utf-8")
        build_id = f"build-{hashlib.sha256(seed).hexdigest()[:24]}"
        payload["build_id"] = build_id
    else:
        payload["build_id"] = build_id.strip()

    existing_step_audit = (
        payload.get("step_audit")
        if isinstance(payload.get("step_audit"), Mapping)
        else {}
    )
    step_audit = dict(existing_step_audit)
    step_audit.setdefault("request_timestamp", now_iso_utc())
    step_audit.setdefault(
        "client_fingerprint_hash", "stub-fingerprint-00000000000000000000000000000000"
    )
    step_audit.setdefault("outcome", "accepted")
    step_audit.setdefault("attempt_count", 1)
    step_audit.setdefault("backoff_reason", None)
    step_audit.setdefault("normalized_mode", normalized_mode_value)
    step_audit.setdefault("expected_step_total", step_total)
    step_audit.setdefault(
        "observed_step_total", step_audit.get("expected_step_total") or step_total
    )
    if (
        step_audit.get("step_total_ok") is None
        and step_audit.get("observed_step_total") is not None
    ):
        step_audit["step_total_ok"] = step_audit.get(
            "observed_step_total"
        ) == step_audit.get("expected_step_total")
    step_audit.setdefault(
        "step_labels_count",
        len(step_labels) if isinstance(step_labels, Mapping) else None,
    )
    step_audit.setdefault("has_extended_steps", normalized_mode_value == "extended")
    payload["step_audit"] = step_audit

    composite = (
        dict(payload.get("composite"))
        if isinstance(payload.get("composite"), Mapping)
        else {}
    )
    export_ctx = (
        payload.get("export") if isinstance(payload.get("export"), Mapping) else {}
    )
    sheet_payload = None
    if isinstance(export_ctx, Mapping):
        sheet_payload = export_ctx.get("sheet_payload")
    if sheet_payload is None and isinstance(payload.get("sheet_payload"), Mapping):
        sheet_payload = payload.get("sheet_payload")

    composite_build = {
        "build_id": payload["build_id"],
        "build_state": build_state,
        "benchmark": payload.get("benchmark") or {},
        "export": export_ctx or {},
        "reference_catalog_version": payload.get("reference_catalog_version"),
        "step_audit": step_audit,
    }
    if "catalog_references" in payload:
        composite_build["catalog_references"] = payload["catalog_references"]
    if sheet_payload is not None:
        composite_build["sheet_payload"] = sheet_payload
    composite["build"] = composite_build

    for section in ("narrative", "sheet", "sheet_payload", "ledger"):
        if section in payload and section not in composite:
            composite[section] = payload[section]
    payload["composite"] = composite

    return payload


def _progression_level_errors(
    sheet_payload: Mapping[str, object] | None, target_level: int | None
) -> list[str]:
    if not target_level or target_level < 1:
        return []

    if not isinstance(sheet_payload, Mapping):
        return []

    progression = sheet_payload.get("progressione")
    progression_entries: Sequence | None = None
    if isinstance(progression, Sequence) and not isinstance(progression, (str, bytes)):
        progression_entries = progression

    has_progression_content = False
    if progression_entries:
        for candidate in progression_entries:
            if _has_content(candidate):
                has_progression_content = True
                break

    if not has_progression_content:
        return []

    def _entry_for_level(level: int) -> Mapping | None:
        if progression_entries is None:
            return None

        for candidate in progression_entries:
            if isinstance(candidate, Mapping) and candidate.get("livello") == level:
                return candidate

        if 0 <= level - 1 < len(progression_entries):
            candidate = progression_entries[level - 1]
            if isinstance(candidate, Mapping):
                return candidate
        return None

    errors: list[str] = []
    for level in range(1, target_level + 1):
        progression_entry = _entry_for_level(level)
        privileges = None
        feats = None
        if isinstance(progression_entry, Mapping):
            privileges = progression_entry.get("privilegi")
            feats = progression_entry.get("talenti") or progression_entry.get("talento")

        has_progression = _has_content(privileges) or _has_content(feats)
        has_core_blocks = all(
            _has_content(value)
            for value in (
                sheet_payload.get("pf_totali") or sheet_payload.get("hp"),
                sheet_payload.get("salvezze"),
                sheet_payload.get("skills_map") or sheet_payload.get("skills"),
                sheet_payload.get("skill_points"),
                sheet_payload.get("equipaggiamento") or sheet_payload.get("inventario"),
                sheet_payload.get("spell_levels")
                or sheet_payload.get("magia")
                or sheet_payload.get("slot_incantesimi"),
                sheet_payload.get("ac_breakdown"),
                sheet_payload.get("iniziativa") or sheet_payload.get("velocita"),
            )
        )

        if not (has_progression and has_core_blocks):
            errors.append(f"Progressione assente al livello {level}")

    return errors


def _ledger_entry_errors(sheet_payload: Mapping[str, object] | None) -> list[str]:
    if not isinstance(sheet_payload, Mapping):
        return ["Sheet payload mancante"]

    ledger = sheet_payload.get("ledger")
    if not isinstance(ledger, Mapping):
        return ["Ledger mancante"]

    entries = None
    for key in ("entries", "movimenti", "transactions"):
        value = ledger.get(key)
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
            entries = value
            break

    if not entries:
        return ["Ledger senza entries/movimenti"]

    # Verifica minima: almeno una entry riconoscibile
    recognized_keys = (
        "item",
        "oggetto",
        "voce",
        "name",
        "label",
        "descrizione",
        "description",
    )
    for entry in entries:
        if isinstance(entry, Mapping):
            if any(entry.get(key) for key in recognized_keys):
                return []
            if any(
                isinstance(value, (int, float))
                and value != 0
                or isinstance(value, str)
                and value.strip()
                for value in entry.values()
            ):
                return []
        if isinstance(entry, str) and entry.strip():
            return []  # entry testuale non vuota: consideriamola sufficiente

    return ["Ledger entries presenti ma senza item/oggetto riconoscibile"]


async def fetch_build(
    client: httpx.AsyncClient,
    api_key: str | None,
    request: BuildRequest,
    max_retries: int,
    require_complete: bool = True,
    target_level: int | None = None,
    ruling_expert_url: str | None = None,
    ruling_timeout: float = 30.0,
    ruling_max_retries: int | None = None,
    t1_filter: bool = False,
    t1_variants: int = 3,
    lazy_ruling: bool = True,
    reference_dir: Path | None = None,
    reference_catalog: Mapping[str, Mapping[str, Mapping[str, object]]] | None = None,
    reference_manifest: Mapping[str, object] | None = None,
    suggest_combos: bool = False,
    validate_combo: bool = False,
    catalog_policy: str = "warn",
    numeric_completeness: bool = False,
    skip_ruling_expert: bool = False,
    ruling_cache: RulingCache | None = None,
    ruling_semaphore: asyncio.Semaphore | None = None,
) -> MutableMapping:
    if reference_catalog is None:
        reference_catalog = get_reference_catalog(
            reference_dir, strict=require_complete
        )
    if reference_manifest is None:
        reference_manifest = get_reference_manifest(reference_dir)
    manifest_version = (
        str(reference_manifest.get("version"))
        if isinstance(reference_manifest, Mapping)
        else None
    )
    if manifest_version is None:
        raise BuildFetchError(
            "Manifest del catalogo di riferimento non disponibile o senza versione",
            request=request,
        )

    def _coerce_number(value: object) -> float | None:
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            match = re.search(r"-?\d+(?:\.\d+)?", value)
            if match:
                try:
                    return float(match.group())
                except ValueError:
                    return None
        return None

    def _benchmark_scores(
        benchmark: Mapping[str, object] | None,
    ) -> tuple[float, float]:
        offense = 0.0
        defense = 0.0
        if not isinstance(benchmark, Mapping):
            return offense, defense

        dpr_snapshot = benchmark.get("dpr_snapshot")
        if isinstance(dpr_snapshot, Mapping):
            for snapshot in dpr_snapshot.values():
                if not isinstance(snapshot, Mapping):
                    continue
                offense = max(
                    offense,
                    _coerce_number(snapshot.get("media")) or 0.0,
                    _coerce_number(snapshot.get("picco")) or 0.0,
                )

        statistics = benchmark.get("statistics")
        if isinstance(statistics, Mapping):
            for key, value in statistics.items():
                numeric = _coerce_number(value)
                if numeric is None:
                    continue
                key_lower = str(key).lower()
                if key_lower.startswith("ac") or key_lower.startswith("ca"):
                    defense = max(defense, numeric)
                else:
                    offense = max(offense, numeric)

        return offense, defense

    def _variant_meta(
        payload: Mapping[str, object],
    ) -> tuple[str | None, str | None, float, float, list[str]]:
        benchmark = payload.get("benchmark") if isinstance(payload, Mapping) else None
        meta_tier = None
        if isinstance(benchmark, Mapping):
            raw_tier = benchmark.get("meta_tier")
            meta_tier = str(raw_tier).strip() if raw_tier else None

        benchmark_ctx = (
            payload.get("benchmark")
            if isinstance(payload.get("benchmark"), Mapping)
            else {}
        )
        ruling_badge = payload.get("ruling_badge") or benchmark_ctx.get("ruling_badge")

        offense_score, defense_score = _benchmark_scores(benchmark)

        ruling_log: list[str] = []
        if isinstance(payload, Mapping):
            candidates: list[str] = []
            ruling_log_field = payload.get("ruling_log")
            if isinstance(ruling_log_field, Sequence) and not isinstance(
                ruling_log_field, (str, bytes)
            ):
                candidates.extend(str(entry) for entry in ruling_log_field)
            qa_ctx = (
                payload.get("qa") if isinstance(payload.get("qa"), Mapping) else None
            )
            qa_log = None
            if qa_ctx and isinstance(qa_ctx.get("ruling_expert"), Mapping):
                qa_log = qa_ctx.get("ruling_expert", {}).get("log")
            if qa_log:
                if isinstance(qa_log, Sequence) and not isinstance(
                    qa_log, (str, bytes)
                ):
                    candidates.extend(str(entry) for entry in qa_log)
                else:
                    candidates.append(str(qa_log))
            ruling_log = candidates

        return (
            meta_tier,
            str(ruling_badge) if ruling_badge else None,
            offense_score,
            defense_score,
            ruling_log,
        )

    async def _append_combo_suggestions(
        base_payload: MutableMapping,
    ) -> MutableMapping:
        if not suggest_combos:
            return base_payload

        suggested: list[Mapping[str, object]] = []
        archetype_hint = request.archetype or request.query_params.get("archetype")
        for combo in catalog_combo_candidates(
            reference_catalog,
            class_name=request.class_name,
            archetype=archetype_hint,
        ):
            combo_id_parts = [request.class_name]
            archetype_value = combo.get("archetype") or request.archetype
            if archetype_value:
                combo_id_parts.append(str(archetype_value))
            feat_names = (
                combo.get("feats") if isinstance(combo.get("feats"), Sequence) else []
            )
            item_names = (
                combo.get("items") if isinstance(combo.get("items"), Sequence) else []
            )
            combo_id_parts.extend(map(str, feat_names or []))
            combo_id_parts.extend(map(str, item_names or []))
            combo_slug = slugify("-".join(filter(None, combo_id_parts)))

            merged_query = dict(request.query_params)
            if archetype_value:
                merged_query.setdefault("archetype", archetype_value)
            merged_body = dict(request.body_params)
            if feat_names:
                merged_body["feat_matrix"] = list(feat_names)
            if item_names:
                merged_body["equipment_plan"] = list(item_names)

            combo_request = replace(
                request,
                archetype=archetype_value,
                query_params=merged_query,
                body_params=merged_body,
                combo_id=f"catalog_{combo_slug}",
            )

            try:
                combo_payload = await _fetch_single_variant(
                    combo_request, validate_ruling=True
                )
            except BuildFetchError:
                continue

            meta = _variant_meta(combo_payload)
            if validate_combo and (meta[0] != "T1" or not meta[1]):
                continue
            if meta[0] == "T1" and meta[1]:
                suggested.append(
                    {
                        "combo_id": combo_request.combo_id,
                        "archetype": archetype_value,
                        "feats": list(feat_names or []),
                        "items": list(item_names or []),
                        "meta_tier": meta[0],
                        "ruling_badge": meta[1],
                        "offense": meta[2],
                        "defense": meta[3],
                        "ruling_log": meta[4],
                    }
                )

        benchmark_ctx = base_payload.setdefault("benchmark", {})
        benchmark_ctx["suggested_combos"] = suggested
        base_meta = _variant_meta(base_payload)
        if base_meta[0] and "meta_tier" not in benchmark_ctx:
            benchmark_ctx["meta_tier"] = base_meta[0]
        if base_meta[1] and "ruling_badge" not in benchmark_ctx:
            benchmark_ctx["ruling_badge"] = base_meta[1]
        if not suggested and validate_combo:
            completeness_ctx = base_payload.setdefault("completeness", {})
            errors_list = completeness_ctx.setdefault("errors", [])
            errors_list.append(
                "Nessuna combo catalogo con meta_tier T1 e badge valido trovata"
            )
        return base_payload

    async def _fetch_single_variant(
        current_request: BuildRequest | None = None,
        *,
        validate_ruling: bool = True,
    ) -> MutableMapping:
        active_request = current_request or request
        params = active_request.api_params(level=target_level)
        headers = {"x-api-key": api_key} if api_key else {}
        method = active_request.http_method()
        response = await request_with_retry(
            client,
            method,
            MODULE_ENDPOINT,
            params=params,
            headers=headers,
            timeout=60,
            max_retries=max_retries,
            json_body=active_request.body_params or None,
        )

        try:
            payload = response.json()
        except json.JSONDecodeError as exc:  # pragma: no cover - network dependent
            raise BuildFetchError(
                f"Risposta non JSON per {request.class_name}: {exc}"
            ) from exc

        original_benchmark = (
            payload.get("benchmark")
            if isinstance(payload.get("benchmark"), Mapping)
            else {}
        )
        original_meta_tier = (
            original_benchmark.get("meta_tier")
            if isinstance(original_benchmark, Mapping)
            else None
        )
        original_ruling_badge = (
            original_benchmark.get("ruling_badge")
            if isinstance(original_benchmark, Mapping)
            else None
        )

        for required in ("build_state", "benchmark", "export"):
            if required not in payload:
                raise BuildFetchError(
                    f"Campo '{required}' mancante nella risposta per {request.class_name}. Chiavi viste: {sorted(payload.keys())}"
                )

        sheet = None
        for candidate in (
            "sheet",
            "sheet_markup",
            "sheet_markdown",
            "sheet_markdown_template",
        ):
            if candidate in payload:
                sheet = payload[candidate]
                break

        narrative = payload.get("narrative")
        ledger = payload.get("ledger") or payload.get("adventurer_ledger")

        build_state = payload.get("build_state") or {}
        normalized_mode = normalize_mode(request.mode)
        expected_step_total = expected_step_total_for_mode(normalized_mode)
        observed_step_total = build_state.get("step_total")
        step_labels = (
            build_state.get("step_labels") if isinstance(build_state, Mapping) else None
        )
        step_labels_count = (
            len(step_labels) if isinstance(step_labels, Mapping) else None
        )
        has_extended_steps = bool(step_labels_count and step_labels_count >= 16)
        if observed_step_total is None:
            logging.warning(
                "Risposta per %s (mode=%s) priva di step_total: impossibile verificare il flow",
                request.class_name,
                normalized_mode,
            )
        elif observed_step_total != expected_step_total:
            logging.warning(
                "Step total inatteso per %s (mode=%s): visto %s, atteso %s",
                request.class_name,
                normalized_mode,
                observed_step_total,
                expected_step_total,
            )
        else:
            logging.info(
                "Modalità %s confermata per %s: step_total=%s (%s step disponibili)",
                normalized_mode,
                active_request.class_name,
                observed_step_total,
                "16" if normalized_mode == "extended" else "8",
            )

        if active_request.race is None and build_state.get("race"):
            active_request.race = build_state.get("race")
        if active_request.archetype is None and build_state.get("archetype"):
            active_request.archetype = build_state.get("archetype")
        if active_request.background is None and active_request.body_params.get(
            "background_hooks"
        ):
            active_request.background = str(
                active_request.body_params.get("background_hooks")
            )

        composite = {
            "build": {
                "build_state": payload.get("build_state"),
                "benchmark": payload.get("benchmark"),
                "export": payload.get("export"),
                "reference_catalog_version": manifest_version,
            },
        }
        if narrative is not None:
            composite["narrative"] = narrative
        if sheet is not None:
            composite["sheet"] = sheet
        if ledger is not None:
            composite["ledger"] = ledger

        completeness_errors: list[str] = []
        statistics = (build_state or {}).get("statistics") or (
            payload.get("benchmark") or {}
        ).get("statistics")
        if not statistics or (
            isinstance(statistics, Mapping) and not any(statistics.values())
        ):
            completeness_errors.append("Statistiche mancanti o vuote")

        if not narrative:
            completeness_errors.append("Narrativa assente")
        else:

            def _contains_stub(value: object) -> bool:
                if isinstance(value, str):
                    return "stub" in value.lower()
                if isinstance(value, Mapping):
                    return any(_contains_stub(v) for v in value.values())
                if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
                    return any(_contains_stub(v) for v in value)
                return False

            if _contains_stub(narrative):
                completeness_errors.append("Narrativa contiene placeholder 'stub'")

        if not ledger or (isinstance(ledger, Mapping) and not any(ledger.values())):
            completeness_errors.append("Ledger assente o senza contenuti")
        source_url = str(response.url)
        export_ctx = payload.setdefault("export", {})
        sheet_payload = _enrich_sheet_payload(
            payload, ledger if isinstance(ledger, Mapping) else None, source_url
        )
        export_ctx["sheet_payload"] = sheet_payload
        sheet_markdown = sheet_payload.get("sheet_markdown")
        if isinstance(sheet_markdown, str):
            payload["sheet"] = sheet_markdown
            composite["sheet"] = sheet_markdown
        elif sheet is not None:
            composite.setdefault("sheet", sheet)

        def _require_block(label: str, *values: object) -> None:
            if not any(_has_content(value) for value in values):
                completeness_errors.append(label)

        _require_block(
            "PF mancanti o vuoti",
            sheet_payload.get("pf_totali"),
            sheet_payload.get("hp"),
        )
        _require_block("Salvezze mancanti o vuote", sheet_payload.get("salvezze"))
        _require_block(
            "Skill assenti o vuote",
            sheet_payload.get("skills_map"),
            sheet_payload.get("skills"),
            sheet_payload.get("skill_points"),
        )
        _require_block(
            "Talenti/capacità mancanti o vuote",
            sheet_payload.get("talenti"),
            sheet_payload.get("capacita_classe"),
        )
        _require_block(
            "Equipaggiamento/inventario mancante o vuoto",
            sheet_payload.get("equipaggiamento"),
            sheet_payload.get("inventario"),
        )
        _require_block(
            "Sezione incantesimi mancante o vuota",
            sheet_payload.get("spell_levels"),
            sheet_payload.get("magia"),
            sheet_payload.get("slot_incantesimi"),
        )
        _require_block(
            "CA dettagliata mancante o vuota", sheet_payload.get("ac_breakdown")
        )
        _require_block(
            "CA totale mancante o vuota",
            sheet_payload.get("AC_tot"),
            sheet_payload.get("CA_touch"),
            sheet_payload.get("CA_ff"),
        )
        _require_block(
            "Iniziativa/velocità assente o vuota",
            sheet_payload.get("iniziativa"),
            sheet_payload.get("velocita"),
        )
        _require_block(
            "Risorse/valuta mancanti o vuote",
            sheet_payload.get("currency"),
            sheet_payload.get("risorse_giornaliere"),
            sheet_payload.get("gp"),
            sheet_payload.get("sp"),
            sheet_payload.get("pp"),
            sheet_payload.get("cp"),
        )
        completeness_errors.extend(_ledger_entry_errors(sheet_payload))
        if numeric_completeness:

            def _num(x: object) -> float | None:
                if isinstance(x, (int, float)):
                    return float(x)
                if isinstance(x, str):
                    m = re.search(r"-?\d+(?:\.\d+)?", x)
                    if m:
                        try:
                            return float(m.group())
                        except ValueError:
                            return None
                return None

            pf = _num(sheet_payload.get("pf_totali"))
            if pf is None or pf <= 0:
                completeness_errors.append("PF totali non numerici o <= 0")

            spd = _num(sheet_payload.get("velocita"))
            if spd is None or spd <= 0:
                completeness_errors.append("Velocità non numerica o <= 0")

            ac = _num(sheet_payload.get("AC_tot"))
            if ac is None or ac < 10:
                completeness_errors.append("CA totale non numerica o < 10")

            bab = _num(sheet_payload.get("BAB"))
            if bab is None or bab < 0:
                completeness_errors.append("BAB non numerico o < 0")
        progression_errors = _progression_level_errors(sheet_payload, target_level)
        for error in progression_errors:
            if error not in completeness_errors:
                completeness_errors.append(error)

        catalog_errors, catalog_meta = validate_sheet_with_catalog(
            sheet_payload, reference_catalog, ledger, reference_manifest
        )
        if catalog_errors:
            if catalog_policy == "warn":
                payload.setdefault("qa", {}).setdefault("catalog", {})[
                    "warnings"
                ] = catalog_errors
            elif catalog_policy != "ignore":
                for error in catalog_errors:
                    if error not in completeness_errors:
                        completeness_errors.append(error)
        if catalog_meta:
            payload["catalog_validation"] = catalog_meta
            payload.setdefault("benchmark", {}).update(catalog_meta)
        if original_meta_tier and "meta_tier" not in payload.get("benchmark", {}):
            payload.setdefault("benchmark", {})["meta_tier"] = original_meta_tier
        if original_ruling_badge and "ruling_badge" not in payload.get("benchmark", {}):
            payload.setdefault("benchmark", {})["ruling_badge"] = original_ruling_badge

        payload.update(
            {
                "class": request.class_name,
                "mode": request.mode,
                "source_url": source_url,
                "reference_catalog_version": manifest_version,
                "fetched_at": now_iso_utc(),
                "request": active_request.metadata(),
                "composite": composite,
                "query_params": params,
                "body_params": active_request.body_params,
                "mode_normalized": normalized_mode,
                "step_audit": {
                    "normalized_mode": normalized_mode,
                    "expected_step_total": expected_step_total,
                    "observed_step_total": observed_step_total,
                    "step_total_ok": observed_step_total == expected_step_total,
                    "step_labels_count": step_labels_count,
                    "has_extended_steps": has_extended_steps,
                },
                "completeness": {
                    "errors": completeness_errors,
                    "require_complete": require_complete,
                },
            }
        )
        if reference_manifest:
            payload["catalog_manifest"] = reference_manifest

        if require_complete and completeness_errors:
            joined_errors = "; ".join(completeness_errors)
            raise BuildFetchError(
                f"Build incompleta per {active_request.class_name}: {joined_errors}",
                completeness_errors=completeness_errors,
            )

        if skip_ruling_expert:
            logging.info(
                "Salto la validazione del badge ruling per %s", request.output_name()
            )
            return payload

        ruling_retries = (
            ruling_max_retries if ruling_max_retries is not None else max_retries
        )
        if validate_ruling:
            await _validate_ruling_badge(
                client,
                url=ruling_expert_url,
                api_key=api_key,
                payload=payload,
                request=active_request,
                timeout=ruling_timeout,
                max_retries=ruling_retries,
                cache=ruling_cache,
                semaphore=ruling_semaphore,
            )

        return payload

    variants: list[
        tuple[
            int,
            MutableMapping,
            tuple[str | None, str | None, float, float, list[str]],
        ]
    ] = []
    variant_failures: list[BuildFetchError] = []
    variant_candidates: list[dict[str, object]] = []
    attempts = max(1, t1_variants if t1_filter else 1)
    use_lazy_ruling = bool(lazy_ruling and t1_filter and attempts > 1)
    for attempt_index in range(1, attempts + 1):
        try:
            payload = await _fetch_single_variant(validate_ruling=not use_lazy_ruling)
        except BuildFetchError as exc:
            if not t1_filter:
                raise
            variant_failures.append(exc)
            candidate: dict[str, object] = {
                "attempt": attempt_index,
                "status": "error",
                "error": str(exc),
            }
            if exc.completeness_errors:
                candidate["completeness_errors"] = list(exc.completeness_errors)
            variant_candidates.append(candidate)
            logging.warning(
                "Variante %d/%d fallita per %s: %s. Provo la successiva...",
                attempt_index,
                attempts,
                request.class_name,
                exc,
            )
            continue
        meta = _variant_meta(payload)
        variants.append((attempt_index, payload, meta))
        candidate = {
            "attempt": attempt_index,
            "status": "ok",
            "meta_tier": meta[0],
            "ruling_badge": meta[1],
            "offense": meta[2],
            "defense": meta[3],
        }
        if meta[4]:
            candidate["ruling_log"] = meta[4]
        completeness: object = payload.get("completeness")
        if isinstance(completeness, Mapping):
            errors = completeness.get("errors")
            if isinstance(errors, list) and errors:
                candidate["completeness_errors"] = list(errors)
        variant_candidates.append(candidate)
        if not t1_filter:
            return await _append_combo_suggestions(payload)

    if t1_filter and not variants:
        preview_errors: list[str] = []
        for exc in variant_failures[:3]:
            if exc.completeness_errors:
                preview_errors.append("; ".join(exc.completeness_errors))
            else:
                preview_errors.append(str(exc))
        preview = " | ".join(preview_errors) if preview_errors else "n/d"
        raise BuildFetchError(
            f"Filtro T1 attivo: tutte le varianti ({attempts}) sono fallite per {request.class_name}. Errori: {preview}"
        )

    def _score(
        meta: tuple[str | None, str | None, float, float, list[str]],
    ) -> tuple[float, float]:
        return meta[2], meta[3]

    if use_lazy_ruling:
        t1_candidates = [
            (payload, meta)
            for _, payload, meta in variants
            if (meta[0] or "").upper() == "T1"
        ]
        if not t1_candidates:
            observed_tiers = {meta[0] or "n/d" for _, _, meta in variants}
            raise BuildFetchError(
                f"Filtro T1 attivo: nessuna variante T1 (meta_tier osservati: {', '.join(sorted(observed_tiers))})"
            )
        best_payload, best_meta = max(t1_candidates, key=lambda item: _score(item[1]))
        ruling_retries = (
            ruling_max_retries if ruling_max_retries is not None else max_retries
        )
        await _validate_ruling_badge(
            client,
            url=ruling_expert_url,
            api_key=api_key,
            payload=best_payload,
            request=request,
            timeout=ruling_timeout,
            max_retries=ruling_retries,
            cache=ruling_cache,
            semaphore=ruling_semaphore,
        )
        return await _append_combo_suggestions(best_payload)

    valid_variants = [
        (attempt, payload, meta)
        for attempt, payload, meta in variants
        if meta[0] == "T1" and meta[1]
    ]

    if not valid_variants:
        observed_tiers = {meta[0] or "n/d" for _, _, meta in variants}
        failure_note = (
            f"; fallite: {len(variant_failures)}/{attempts}" if variant_failures else ""
        )
        raise BuildFetchError(
            f"Filtro T1 attivo: nessuna variante valida (meta_tier osservati: {', '.join(sorted(observed_tiers))}){failure_note}"
        )

    best_attempt, best_payload, best_meta = max(
        valid_variants, key=lambda item: _score(item[2])
    )
    for candidate in variant_candidates:
        if candidate.get("attempt") == best_attempt and candidate.get("status") == "ok":
            candidate["selected"] = True
            break
    best_payload.setdefault("benchmark", {})["variant_candidates"] = variant_candidates
    if best_meta[4]:
        best_payload.setdefault("qa", {}).setdefault("ruling_expert", {})["log"] = (
            best_meta[4]
        )
    return await _append_combo_suggestions(best_payload)


async def fetch_module(
    client: httpx.AsyncClient, api_key: str | None, module_name: str, max_retries: int
) -> tuple[str, Mapping]:
    headers = {"x-api-key": api_key} if api_key else {}
    content_resp = await request_with_retry(
        client,
        "GET",
        MODULE_DUMP_ENDPOINT.format(name=module_name),
        headers=headers,
        timeout=60,
        max_retries=max_retries,
        backoff_factor=0.5,
    )

    meta_resp = await request_with_retry(
        client,
        "GET",
        MODULE_META_ENDPOINT.format(name=module_name),
        headers=headers,
        timeout=30,
        max_retries=max_retries,
        backoff_factor=0.5,
    )

    return content_resp.text, meta_resp.json()


async def discover_modules(
    client: httpx.AsyncClient, api_key: str | None, max_retries: int
) -> list[str]:
    headers = {"x-api-key": api_key} if api_key else {}
    response = await request_with_retry(
        client,
        "GET",
        MODULE_LIST_ENDPOINT,
        headers=headers,
        timeout=30,
        max_retries=max_retries,
        backoff_factor=0.5,
    )

    try:
        payload = response.json()
    except json.JSONDecodeError as exc:  # pragma: no cover - network dependent
        raise ValueError("Risposta /modules non valida (JSON)") from exc

    if isinstance(payload, Mapping) and "modules" in payload:
        payload = payload.get("modules")

    if not isinstance(payload, Sequence) or isinstance(payload, (str, bytes)):
        raise ValueError(f"Formato /modules inatteso: {payload!r}")

    names: list[str] = []
    for item in payload:
        if isinstance(item, Mapping):
            name = item.get("name")
        else:
            name = item
        if not name:
            continue
        names.append(str(name))

    return names


def write_json(path: Path, data: Mapping) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _benchmark_scores_for_index(
    benchmark: Mapping[str, object] | None,
) -> tuple[float, float]:
    offense = 0.0
    defense = 0.0
    if not isinstance(benchmark, Mapping):
        return offense, defense

    dpr_snapshot = benchmark.get("dpr_snapshot")
    if isinstance(dpr_snapshot, Mapping):
        for snapshot in dpr_snapshot.values():
            if not isinstance(snapshot, Mapping):
                continue
            offense = max(
                offense,
                _coerce_number(snapshot.get("media"), 0),
                _coerce_number(snapshot.get("picco"), 0),
            )

    statistics = benchmark.get("statistics")
    if isinstance(statistics, Mapping):
        for key, value in statistics.items():
            numeric = _coerce_number(value)
            if numeric is None:
                continue
            key_lower = str(key).lower()
            if key_lower.startswith("ac") or key_lower.startswith("ca"):
                defense = max(defense, numeric)
            else:
                offense = max(offense, numeric)

    return offense, defense


def _index_meta_from_payload(payload: Mapping[str, object] | None) -> dict[str, object]:
    if not isinstance(payload, Mapping):
        return {}

    metadata: dict[str, object] = {}
    benchmark = (
        payload.get("benchmark")
        if isinstance(payload.get("benchmark"), Mapping)
        else {}
    )
    if benchmark:
        meta_tier = benchmark.get("meta_tier")
        if meta_tier:
            metadata["meta_tier"] = str(meta_tier)
        offense, defense = _benchmark_scores_for_index(benchmark)
        if offense:
            metadata["benchmark_offense"] = offense
        if defense:
            metadata["benchmark_defense"] = defense

    for field in (
        "missing_catalog_entries",
        "prerequisite_violations",
        "ledger_unknown_entries",
        "ledger_sheet_mismatches",
        "catalog_version",
    ):
        if benchmark.get(field):
            metadata[field] = benchmark[field]

    ruling_log = payload.get("ruling_log")
    if isinstance(ruling_log, Sequence) and not isinstance(ruling_log, (str, bytes)):
        metadata["ruling_log"] = list(map(str, ruling_log))
    else:
        qa_ctx = payload.get("qa") if isinstance(payload.get("qa"), Mapping) else None
        if qa_ctx and isinstance(qa_ctx.get("ruling_expert"), Mapping):
            log_value = qa_ctx.get("ruling_expert", {}).get("log")
            if isinstance(log_value, Sequence) and not isinstance(
                log_value, (str, bytes)
            ):
                metadata["ruling_log"] = list(map(str, log_value))
            elif log_value:
                metadata["ruling_log"] = [str(log_value)]

    return metadata


def path_with_suffix(path: Path, suffix: str) -> Path:
    return path.with_name(f"{path.stem}.{suffix}{path.suffix}")


def analyze_indices(
    build_index_path: Path,
    module_index_path: Path,
    *,
    archive_dir: Path | None = None,
) -> Mapping[str, Any]:
    def _load_index(path: Path) -> Mapping[str, Any]:
        if path.is_file():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except Exception as exc:  # pragma: no cover - defensive logging
                logging.warning("Impossibile leggere l'indice %s: %s", path, exc)
        return {"entries": []}

    def _archive_payload(
        source: Path, destination_dir: Path, archived: list[str]
    ) -> None:
        destination_dir.mkdir(parents=True, exist_ok=True)
        destination = destination_dir / source.name
        if destination.exists():
            destination = destination_dir / f"{source.stem}_copy{destination.suffix}"
        shutil.copy2(source, destination)
        archived.append(str(destination))

    build_index_payload = _load_index(build_index_path)
    module_index_payload = _load_index(module_index_path)

    build_entries: Sequence[Mapping[str, object]] = (
        build_index_payload.get("entries") or []
    )
    module_entries: Sequence[Mapping[str, object]] = (
        module_index_payload.get("entries") or []
    )

    build_stats = {"total": 0, "ok": 0, "invalid": 0, "errors": 0}
    module_stats = {"total": 0, "ok": 0, "invalid": 0, "errors": 0}
    invalid_builds: list[Mapping[str, object]] = []
    invalid_modules: list[Mapping[str, object]] = []
    archived_files: list[str] = []
    ok_classes: set[str] = set()

    for entry in build_entries:
        status = str(entry.get("status") or "error")
        build_stats["total"] += 1
        if status == "ok":
            build_stats["ok"] += 1
            entry_class = entry.get("class")
            if isinstance(entry_class, str) and entry_class.strip():
                ok_classes.add(entry_class.strip())
            continue
        if status == "invalid":
            build_stats["invalid"] += 1
        else:
            build_stats["errors"] += 1
        invalid_builds.append(entry)
        file_path = entry.get("file")
        if archive_dir and file_path:
            source = Path(str(file_path))
            if source.exists():
                _archive_payload(source, archive_dir / "builds", archived_files)

    for entry in module_entries:
        status = str(entry.get("status") or "error")
        module_stats["total"] += 1
        if status == "ok":
            module_stats["ok"] += 1
            continue
        if status == "invalid":
            module_stats["invalid"] += 1
        else:
            module_stats["errors"] += 1
        invalid_modules.append(entry)
        file_path = entry.get("file")
        if archive_dir and file_path:
            source = Path(str(file_path))
            if source.exists():
                _archive_payload(source, archive_dir / "modules", archived_files)

    missing_core_classes = sorted(
        core for core in CORE_CLASSES if core not in ok_classes
    )

    repeated_module_errors: list[dict[str, object]] = []
    if invalid_modules:
        from collections import Counter

        counter: Counter[str] = Counter()
        for entry in invalid_modules:
            message = str(entry.get("error") or entry.get("status") or "unknown")
            counter[message] += 1
        repeated_module_errors = [
            {"error": message, "count": count}
            for message, count in counter.items()
            if count >= 2
        ]

    report = {
        "generated_at": now_iso_utc(),
        "build_index": str(build_index_path),
        "module_index": str(module_index_path),
        "builds": {
            **build_stats,
            "invalid_entries": invalid_builds,
        },
        "modules": {
            **module_stats,
            "invalid_entries": invalid_modules,
        },
        "archived_files": archived_files,
        "alerts": {
            "missing_core_classes": missing_core_classes,
            "repeated_module_errors": repeated_module_errors,
        },
    }

    return report


def build_index_entry(
    request: BuildRequest,
    output_file: Path | None,
    status: str,
    error: str | None = None,
    step_audit: Mapping[str, object] | None = None,
    completeness_errors: Sequence[str] | None = None,
    ruling_badge: str | None = None,
    ruling_sources: object | None = None,
    meta_tier: str | None = None,
    benchmark_offense: float | None = None,
    benchmark_defense: float | None = None,
    ruling_log: Sequence[str] | None = None,
    record_status: str | None = None,
    audit: object | None = None,
    is_deleted: bool | None = None,
    deleted_at: object | None = None,
    **extra_meta: object,
) -> Mapping:
    entry: dict[str, object] = {
        "file": str(output_file) if output_file else None,
        "status": status,
        "output_prefix": request.output_name(),
        "level": request.level,
        **request.metadata(),
    }
    if error:
        entry["error"] = error
    if completeness_errors:
        entry["completeness_errors"] = list(completeness_errors)
    if ruling_badge:
        entry["ruling_badge"] = ruling_badge
    if ruling_sources:
        entry["ruling_sources"] = ruling_sources
    if meta_tier:
        entry["meta_tier"] = meta_tier
    if benchmark_offense is not None:
        entry["benchmark_offense"] = benchmark_offense
    if benchmark_defense is not None:
        entry["benchmark_defense"] = benchmark_defense
    if ruling_log:
        entry["ruling_log"] = list(ruling_log)
    if extra_meta:
        entry.update(extra_meta)
    if record_status:
        entry["record_status"] = record_status
    if is_deleted is not None:
        entry["is_deleted"] = bool(is_deleted)
    if deleted_at is not None:
        entry["deleted_at"] = deleted_at
    issues = _issues_for_record(audit, record_status)
    if audit:
        entry["audit"] = audit
    if issues:
        entry["issues"] = issues
    if step_audit:
        entry.update(
            {
                "step_total": step_audit.get("observed_step_total"),
                "expected_step_total": step_audit.get("expected_step_total"),
                "mode_normalized": step_audit.get("normalized_mode"),
                "extended_steps_available": step_audit.get("has_extended_steps"),
                "step_total_ok": step_audit.get("step_total_ok"),
                "request_timestamp": step_audit.get("request_timestamp"),
                "client_fingerprint_hash": step_audit.get("client_fingerprint_hash"),
                "request_ip": step_audit.get("request_ip"),
                "auth_outcome": step_audit.get("outcome"),
                "auth_attempt_count": step_audit.get("attempt_count"),
                "backoff_reason": step_audit.get("backoff_reason"),
            }
        )
    return entry


def module_index_entry(
    name: str,
    output_file: Path | None,
    status: str,
    meta: Mapping | None = None,
    error: str | None = None,
) -> Mapping:
    entry: dict[str, object] = {
        "module": name,
        "file": str(output_file) if output_file else None,
        "status": status,
    }
    if meta:
        entry["meta"] = meta
    issues = _issues_for_record(
        meta.get("audit") if isinstance(meta, Mapping) else None,
        meta.get("record_status") if isinstance(meta, Mapping) else None,
    )
    if issues:
        entry["issues"] = issues
    if error:
        entry["error"] = error
    return entry


async def run_harvest(
    requests: Iterable[BuildRequest],
    api_url: str,
    api_key: str | None,
    output_dir: Path,
    index_path: Path,
    modules: Sequence[str],
    modules_output_dir: Path,
    module_index_path: Path,
    concurrency: int,
    max_retries: int,
    spec_path: Path | None = None,
    discover: bool = False,
    include_filters: Sequence[str] | None = None,
    exclude_filters: Sequence[str] | None = None,
    strict: bool = False,
    keep_invalid: bool = False,
    require_complete: bool = True,
    skip_health_check: bool = False,
    health_path: str = "/health",
    health_timeout: float = 10.0,
    level_filters: Sequence[int] | None = None,
    skip_unchanged: bool = False,
    max_items: int | None = None,
    ruling_expert_url: str | None = None,
    ruling_timeout: float = 30.0,
    ruling_max_retries: int | None = None,
    skip_ruling_expert: bool = False,
    t1_filter: bool = False,
    t1_variants: int = 3,
    lazy_ruling: bool = True,
    combo_best_only: bool = False,
    reference_dir: Path | None = None,
    suggest_combos: bool = False,
    validate_combo: bool = False,
    catalog_policy: str = "warn",
    numeric_completeness: bool = False,
    ruling_cache_path: Path | None = None,
    ruling_concurrency: int | None = None,
    skip_modules: bool = False,
    fail_on_invalid: bool = False,
) -> None:
    requests = list(requests)
    max_items = int(max_items) if max_items is not None else None
    max_items = max_items if max_items and max_items > 0 else None
    ensure_output_dirs(output_dir)
    ensure_output_dirs(modules_output_dir)
    ruling_cache: RulingCache | None = None
    if ruling_cache_path:
        ruling_cache_path.parent.mkdir(parents=True, exist_ok=True)
        ruling_cache = RulingCache.load(ruling_cache_path)
    existing_build_entries: dict[str, Mapping] = {}
    existing_build_meta: dict[str, object] = {}
    if index_path.is_file():
        try:
            cached = json.loads(index_path.read_text(encoding="utf-8"))
            existing_build_meta.update(
                {
                    "api_url": cached.get("api_url"),
                    "mode": cached.get("mode"),
                    "spec_file": cached.get("spec_file"),
                }
            )
            for entry in cached.get("entries", []):
                key = (
                    entry.get("file")
                    or f"{entry.get('output_prefix')}@{entry.get('level')}"
                )
                if key:
                    existing_build_entries[str(key)] = entry
        except Exception as exc:  # pragma: no cover - defensive logging only
            logging.warning(
                "Impossibile caricare build_index esistente %s: %s", index_path, exc
            )

    builds_index: dict[str, object] = {
        "generated_at": now_iso_utc(),
        "api_url": existing_build_meta.get("api_url", api_url),
        "mode": (
            existing_build_meta.get("mode")
            or (
                requests[0].mode
                if requests and len({req.mode for req in requests}) == 1
                else "mixed" if requests else "mixed"
            )
        ),
        "spec_file": existing_build_meta.get("spec_file")
        or (str(spec_path) if spec_path else None),
        "entries": [],
    }
    modules_index: dict[str, object] = {
        "generated_at": now_iso_utc(),
        "api_url": api_url,
        "entries": [],
    }

    existing_module_entries: dict[str, Mapping] = {}
    module_index_meta: dict[str, object] = {}
    if module_index_path.is_file():
        try:
            cached = json.loads(module_index_path.read_text(encoding="utf-8"))
            module_index_meta.update(
                {
                    "catalog_version": cached.get("catalog_version"),
                    "reference_catalog": cached.get("reference_catalog"),
                }
            )
            for entry in cached.get("entries", []):
                name = entry.get("module")
                if name:
                    existing_module_entries[str(name)] = entry
        except Exception as exc:  # pragma: no cover - defensive logging only
            logging.warning(
                "Impossibile caricare module_index esistente %s: %s",
                module_index_path,
                exc,
            )

    include_filters = include_filters or []
    exclude_filters = exclude_filters or []
    reference_catalog = get_reference_catalog(reference_dir, strict=strict)
    reference_manifest = get_reference_manifest(reference_dir)
    manifest_version = (
        str(reference_manifest.get("version"))
        if isinstance(reference_manifest, Mapping)
        else None
    )
    reference_catalog_version = _coerce_catalog_version(
        module_index_meta.get("catalog_version"), manifest_version
    )
    if reference_catalog_version:
        builds_index["catalog_version"] = [reference_catalog_version]
        modules_index["catalog_version"] = [reference_catalog_version]
    discovery_info: Mapping[str, object] | None = None

    semaphore = asyncio.Semaphore(max(1, concurrency))
    ruling_limit = max(
        1, min(max(1, concurrency), max(1, (ruling_concurrency or concurrency)))
    )
    ruling_semaphore = asyncio.Semaphore(ruling_limit)

    planned_snapshots: list[tuple[BuildRequest, Path, int]] = []
    level_filter_set = (
        {int(level) for level in level_filters} if level_filters else None
    )

    best_combo_scores: dict[
        tuple[str, int], tuple[tuple[float, float, float, float], Path | None]
    ] = {}
    best_combo_lock = asyncio.Lock()

    def _tier_priority(meta_tier: str | None) -> int:
        if not meta_tier:
            return 0
        tier_match = re.search(r"t(\d+)", str(meta_tier).lower())
        if tier_match:
            try:
                return max(0, 6 - int(tier_match.group(1)))
            except ValueError:
                return 0
        return 1

    def _combo_score(
        meta_tier: str | None,
        offense: float | None,
        defense: float | None,
        badge: str | None,
    ) -> tuple[float, float, float, float]:
        return (
            1.0 if badge else 0.0,
            float(_tier_priority(meta_tier)),
            float(offense or 0.0),
            float(defense or 0.0),
        )

    snapshots_planned = 0
    skipped_for_limit = 0
    limit_reached = False
    for build_request in requests:
        if limit_reached:
            break
        seen_levels: set[int] = set()
        level_plan: list[int] = []
        levels_to_process = [1, *build_request.level_checkpoints]

        for level in levels_to_process:
            try:
                coerced = int(level)
            except (TypeError, ValueError):
                continue
            if level_filter_set is not None and coerced not in level_filter_set:
                continue
            if coerced <= 0 or coerced in seen_levels:
                continue
            seen_levels.add(coerced)
            level_plan.append(coerced)

        if not level_plan:
            logging.info(
                "Nessun livello selezionato per %s, salto la richiesta",
                build_request.output_name(),
            )
            continue

        base_level = 1

        for idx, level in enumerate(level_plan):
            if max_items is not None and snapshots_planned >= max_items:
                skipped_for_limit += len(level_plan) - idx
                limit_reached = True
                break
            task_request = replace(
                build_request,
                level=level,
                level_checkpoints=tuple(level_plan),
            )
            suffix = "" if level == 1 else f"_lvl{level:02d}"
            output_file = output_dir / f"{task_request.output_name()}{suffix}.json"
            planned_snapshots.append((task_request, output_file, base_level))
            snapshots_planned += 1

    if skipped_for_limit:
        logging.info(
            "Limite max-items=%s raggiunto: scartati %s snapshot aggiuntivi",
            max_items,
            skipped_for_limit,
        )

    all_cached = bool(
        skip_unchanged
        and planned_snapshots
        and all(destination.exists() for _, destination, _ in planned_snapshots)
    )

    async with httpx.AsyncClient(
        base_url=api_url.rstrip("/"),
        follow_redirects=True,
        http2=False,
        limits=httpx.Limits(
            max_connections=max(10, concurrency * 2),
            max_keepalive_connections=max(10, concurrency),
        ),
    ) as client:
        if skip_health_check or all_cached:
            logging.warning(
                "Salto il controllo di health check %s%s",
                "(skip-unchanged: cache completa) " if all_cached else "",
                "su richiesta dell'utente" if skip_health_check else "",
            )
        else:
            await assert_api_reachable(
                client,
                api_key,
                health_path=health_path,
                health_timeout=health_timeout,
            )
        if skip_modules:
            if discover:
                logging.info("Skip modules attivo: ignoro --discover-modules")
            filtered_discovered = []
        elif discover:
            discovered = await discover_modules(client, api_key, max_retries)
            filtered_discovered = apply_glob_filters(
                discovered, include_filters, exclude_filters
            )
            discovery_info = {
                "performed_at": now_iso_utc(),
                "include_filters": list(include_filters),
                "exclude_filters": list(exclude_filters),
                "raw": sorted(discovered),
                "raw_count": len(discovered),
                "selected": sorted(filtered_discovered),
            }
        else:
            filtered_discovered = []

        module_plan: list[str] = []
        seen: set[str] = set()
        if not skip_modules:
            for name in modules:
                if name not in seen:
                    module_plan.append(name)
                    seen.add(name)
            for name in sorted(filtered_discovered):
                if name not in seen:
                    module_plan.append(name)
                    seen.add(name)

        modules_index["module_plan"] = module_plan

        build_results: dict[str, Mapping] = {}

        async def process_class(
            request: BuildRequest, destination: Path, base_level: int
        ) -> tuple[str, Mapping]:
            async with semaphore:
                if skip_unchanged and destination.exists():
                    try:
                        payload = json.loads(destination.read_text(encoding="utf-8"))
                    except (
                        Exception
                    ) as exc:  # pragma: no cover - defensive logging only
                        logging.warning(
                            "Impossibile caricare payload esistente %s: %s, procedo con la fetch",
                            destination,
                            exc,
                        )
                    else:
                        _apply_level_checkpoint(payload, request.level)
                        normalized_payload_before = json.dumps(
                            payload, sort_keys=True, default=str
                        )
                        payload = _normalize_build_payload(
                            payload,
                            request=request,
                            reference_catalog_version=reference_catalog_version,
                            manifest_version=manifest_version,
                            target_level=request.level,
                            normalized_mode=normalize_mode(request.mode),
                        )
                        if (
                            json.dumps(payload, sort_keys=True, default=str)
                            != normalized_payload_before
                        ):
                            destination.write_text(
                                json.dumps(payload, indent=2, ensure_ascii=False),
                                encoding="utf-8",
                            )
                        validation_error = validate_with_schema(
                            schema_for_mode(request.mode),
                            payload,
                            f"build {request.output_name()} (cached)",
                            strict=strict,
                        )
                        sheet_context = payload.get("export", {}).get(
                            "sheet_payload"
                        ) or payload.get("sheet_payload")
                        sheet_validation = None
                        if sheet_context is not None:
                            sheet_validation = validate_with_schema(
                                "scheda_pg.schema.json",
                                sheet_context,
                                f"sheet payload {request.output_name()} (cached)",
                                strict=strict,
                            )
                        if validation_error and sheet_validation:
                            validation_error = f"{validation_error}; {sheet_validation}"
                        elif validation_error is None:
                            validation_error = sheet_validation

                        completeness_ctx = (
                            payload.get("completeness")
                            if isinstance(payload.get("completeness"), Mapping)
                            else {}
                        )
                        completeness_errors = list(completeness_ctx.get("errors") or [])
                        meta_data = _index_meta_from_payload(payload)

                        if completeness_errors and require_complete:
                            logging.warning(
                                "Payload esistente per %s incompleto (%s): forza refetch",
                                request.output_name(),
                                "; ".join(str(err) for err in completeness_errors),
                            )
                        elif validation_error and not keep_invalid:
                            logging.warning(
                                "Payload esistente per %s non valido (%s): forza refetch",
                                request.output_name(),
                                validation_error,
                            )
                        else:
                            status = "ok" if validation_error is None else "invalid"
                            logging.info(
                                "Riutilizzo payload esistente per %s (skip-unchanged)",
                                request.output_name(),
                            )
                            record_status = _record_status_from_result(status)
                            _ensure_record_metadata(
                                payload,
                                actor="generate_build_db",
                                action="cached_payload",
                                record_status=record_status,
                                note=validation_error,
                                checkpoint=request.level,
                                source=request.output_name(),
                            )
                            reuse_ok = True
                            if (
                                status == "ok"
                                and t1_filter
                                and isinstance(payload, MutableMapping)
                            ):
                                benchmark_ctx = payload.get("benchmark")
                                meta_tier = None
                                if isinstance(benchmark_ctx, Mapping):
                                    meta_tier = benchmark_ctx.get("meta_tier")
                                if isinstance(meta_tier, str):
                                    meta_tier = meta_tier.strip() or None

                                if meta_tier != "T1":
                                    logging.warning(
                                        "Payload esistente per %s non è T1 (meta_tier=%s) ma t1_filter è attivo: forza refetch",
                                        request.output_name(),
                                        meta_tier,
                                    )
                                    reuse_ok = False
                                else:
                                    existing_badge = payload.get("ruling_badge")
                                    if not (
                                        isinstance(existing_badge, str)
                                        and existing_badge.strip()
                                    ):
                                        if ruling_expert_url:
                                            try:
                                                validated_badge, _ = (
                                                    await _validate_ruling_badge(
                                                        client,
                                                        url=ruling_expert_url,
                                                        api_key=api_key,
                                                        payload=payload,
                                                        request=request,
                                                        timeout=ruling_timeout,
                                                        max_retries=ruling_max_retries,
                                                    )
                                                )
                                                existing_badge = validated_badge
                                            except BuildFetchError as exc:
                                                logging.warning(
                                                    "Backfill ruling badge fallito per payload esistente %s: %s",
                                                    request.output_name(),
                                                    exc,
                                                )
                                                reuse_ok = False
                                            else:
                                                if existing_badge:
                                                    payload.setdefault(
                                                        "benchmark", {}
                                                    ).setdefault(
                                                        "ruling_badge", existing_badge
                                                    )
                                                write_json(destination, payload)
                                        else:
                                            reuse_ok = False

                                    badge_now = payload.get("ruling_badge")
                                    if not (
                                        isinstance(badge_now, str) and badge_now.strip()
                                    ):
                                        logging.warning(
                                            "Payload esistente per %s è T1 ma senza ruling_badge valido e t1_filter è attivo: forza refetch",
                                            request.output_name(),
                                        )
                                        reuse_ok = False

                            if reuse_ok:
                                return destination.name, build_index_entry(
                                    request,
                                    destination,
                                    status,
                                    validation_error,
                                    (
                                        payload.get("step_audit")
                                        if isinstance(payload, Mapping)
                                        else None
                                    ),
                                    completeness_errors,
                                    (
                                        payload.get("ruling_badge")
                                        if isinstance(payload, Mapping)
                                        else None
                                    ),
                                    (
                                        payload.get("ruling_sources")
                                        if isinstance(payload, Mapping)
                                        else None
                                    ),
                                    record_status=payload.get("record_status"),
                                    audit=payload.get("audit"),
                                    is_deleted=payload.get("is_deleted"),
                                    deleted_at=payload.get("deleted_at"),
                                    **meta_data,
                                )

                method = request.http_method()
                logging.info(
                    "Recupero build per %s (mode=%s, race=%s, archetype=%s, level=%s) via %s",
                    request.class_name,
                    request.mode,
                    request.race,
                    request.archetype,
                    request.level or base_level,
                    method,
                )

                try:
                    payload: MutableMapping | None = None
                    for attempt in range(max_retries + 1):
                        try:
                            payload = await fetch_build(
                                client,
                                api_key,
                                request,
                                max_retries,
                                require_complete=require_complete,
                                target_level=request.level,
                                ruling_expert_url=ruling_expert_url,
                                ruling_timeout=ruling_timeout,
                                ruling_max_retries=ruling_max_retries,
                                skip_ruling_expert=skip_ruling_expert,
                                t1_filter=t1_filter,
                                t1_variants=t1_variants,
                                lazy_ruling=lazy_ruling,
                                reference_dir=reference_dir,
                                reference_catalog=reference_catalog,
                                reference_manifest=reference_manifest,
                                suggest_combos=suggest_combos,
                                validate_combo=validate_combo,
                                catalog_policy=catalog_policy,
                                numeric_completeness=numeric_completeness,
                                ruling_cache=ruling_cache,
                                ruling_semaphore=ruling_semaphore,
                            )
                            break
                        except BuildFetchError as exc:
                            if attempt >= max_retries:
                                raise
                            delay = 1 + attempt
                            logging.warning(
                                "Payload incompleto per %s (%s). Retry in %ss...",
                                request.class_name,
                                exc,
                                delay,
                            )
                            await asyncio.sleep(delay)

                    if payload is None:
                        raise BuildFetchError(
                            f"Impossibile recuperare payload per {request.class_name}"
                        )
                    _apply_level_checkpoint(payload, request.level)
                    payload = _normalize_build_payload(
                        payload,
                        request=request,
                        reference_catalog_version=reference_catalog_version,
                        manifest_version=manifest_version,
                        target_level=request.level,
                        normalized_mode=normalize_mode(request.mode),
                    )
                    validation_error = validate_with_schema(
                        schema_for_mode(request.mode),
                        payload,
                        f"build {request.output_name()}",
                        strict=strict,
                    )
                    sheet_context = payload.get("export", {}).get(
                        "sheet_payload"
                    ) or payload.get("sheet_payload")
                    sheet_validation = None
                    if sheet_context is not None:
                        sheet_validation = validate_with_schema(
                            "scheda_pg.schema.json",
                            sheet_context,
                            f"sheet payload {request.output_name()}",
                            strict=strict,
                        )
                    if validation_error and sheet_validation:
                        validation_error = f"{validation_error}; {sheet_validation}"
                    elif validation_error is None:
                        validation_error = sheet_validation
                    completeness_ctx = (
                        payload.get("completeness")
                        if isinstance(payload.get("completeness"), Mapping)
                        else {}
                    )
                    completeness_errors = list(completeness_ctx.get("errors") or [])
                    completeness_text: str | None = None
                    if completeness_errors:
                        completeness_text = "; ".join(
                            str(error) for error in completeness_errors
                        )
                        validation_error = (
                            completeness_text
                            if validation_error is None
                            else f"{validation_error}; {completeness_text}"
                        )
                    incomplete_payload = bool(completeness_errors)
                    status = "ok" if validation_error is None else "invalid"
                    ruling_badge = (
                        payload.get("ruling_badge")
                        if isinstance(payload, Mapping)
                        else None
                    )
                    ruling_sources = (
                        payload.get("ruling_sources")
                        if isinstance(payload, Mapping)
                        else None
                    )
                    meta_data = _index_meta_from_payload(payload)
                    combo_score: tuple[float, float, float, float] | None = None
                    previous_best_path: Path | None = None
                    combo_key: tuple[str, int] | None = None
                    is_combo_candidate = combo_best_only and bool(request.combo_id)
                    if incomplete_payload:
                        status = "invalid"
                        logging.warning(
                            "Payload per %s scartato per incompletezza: %s",
                            request.output_name(),
                            completeness_text or "dati mancanti",
                        )
                        if destination.exists():
                            destination.unlink()
                        output_path: Path | None = None
                    else:
                        if is_combo_candidate:
                            combo_key = (
                                slugify(request.class_name),
                                int(request.level or base_level),
                            )
                            if status == "ok" and ruling_badge:
                                combo_score = _combo_score(
                                    meta_data.get("meta_tier"),
                                    meta_data.get("benchmark_offense"),
                                    meta_data.get("benchmark_defense"),
                                    ruling_badge,
                                )
                                async with best_combo_lock:
                                    best_entry = best_combo_scores.get(combo_key)
                                    if (
                                        best_entry is None
                                        or combo_score > best_entry[0]
                                    ):
                                        previous_best_path = (
                                            best_entry[1] if best_entry else None
                                        )
                                        best_combo_scores[combo_key] = (
                                            combo_score,
                                            destination,
                                        )
                                    else:
                                        status = "pruned"
                                        validation_error = validation_error or (
                                            f"Scartato dalla combo matrix: score {combo_score} <= {best_entry[0]}"
                                        )
                            else:
                                status = "invalid"
                                validation_error = validation_error or (
                                    "Badge Ruling Expert mancante per combo matrix"
                                )

                    record_status = _record_status_from_result(status)
                    _ensure_record_metadata(
                        payload,
                        actor="generate_build_db",
                        action="harvest",
                        record_status=record_status,
                        note=validation_error,
                        checkpoint=request.level,
                        source=request.output_name(),
                    )
                    should_write = (
                        status == "ok" or keep_invalid
                    ) and not incomplete_payload
                    output_path: Path | None = None
                    if should_write and status != "pruned":
                        if skip_unchanged and destination.exists():
                            try:
                                existing_payload = json.loads(
                                    destination.read_text(encoding="utf-8")
                                )
                            except Exception:
                                existing_payload = None

                            comparison_payload: object = payload
                            if isinstance(payload, Mapping):
                                comparison_payload = dict(payload)
                                if isinstance(existing_payload, Mapping):
                                    comparison_payload["fetched_at"] = (
                                        existing_payload.get("fetched_at")
                                    )

                            if existing_payload == comparison_payload:
                                logging.info(
                                    "Payload invariato per %s, salto la scrittura",
                                    request.output_name(),
                                )
                                output_path = destination
                                return destination.name, build_index_entry(
                                    request,
                                    output_path,
                                    status,
                                    validation_error,
                                    payload.get("step_audit"),
                                    completeness_errors,
                                    ruling_badge,
                                    ruling_sources,
                                    record_status=payload.get("record_status"),
                                    audit=payload.get("audit"),
                                    is_deleted=payload.get("is_deleted"),
                                    deleted_at=payload.get("deleted_at"),
                                    **meta_data,
                                )

                        destination.write_text(
                            json.dumps(payload, indent=2, ensure_ascii=False),
                            encoding="utf-8",
                        )
                        output_path = destination
                        if (
                            previous_best_path
                            and previous_best_path != destination
                            and previous_best_path.exists()
                        ):
                            previous_best_path.unlink()
                    else:
                        if destination.exists():
                            destination.unlink()
                        if status != "pruned":
                            logging.warning(
                                "Payload per %s scartato per invalidazione: %s",
                                request.output_name(),
                                validation_error,
                            )
                        output_path = None
                    return destination.name, build_index_entry(
                        request,
                        output_path,
                        status,
                        validation_error,
                        payload.get("step_audit"),
                        completeness_errors,
                        ruling_badge,
                        ruling_sources,
                        record_status=payload.get("record_status"),
                        audit=payload.get("audit"),
                        is_deleted=payload.get("is_deleted"),
                        deleted_at=payload.get("deleted_at"),
                        **meta_data,
                    )
                except ValidationError:
                    raise
                except BuildFetchError as exc:
                    completeness_errors = getattr(exc, "completeness_errors", None)
                    logging.error(
                        "Build %s marcata come %s: %s",
                        request.class_name,
                        "incompleta" if completeness_errors else "errore",
                        exc,
                    )
                    if destination.exists():
                        destination.unlink()
                    meta_data = _index_meta_from_payload(payload)
                    status = "invalid" if completeness_errors else "error"
                    record_status = _record_status_from_result(status)
                    return destination.name, build_index_entry(
                        request,
                        None,
                        status,
                        str(exc),
                        (
                            payload.get("step_audit")
                            if isinstance(payload, Mapping)
                            else None
                        ),
                        completeness_errors,
                        (
                            payload.get("ruling_badge")
                            if isinstance(payload, Mapping)
                            else None
                        ),
                        (
                            payload.get("ruling_sources")
                            if isinstance(payload, Mapping)
                            else None
                        ),
                        record_status=record_status,
                        audit=(
                            payload.get("audit")
                            if isinstance(payload, Mapping)
                            else None
                        ),
                        is_deleted=(
                            payload.get("is_deleted")
                            if isinstance(payload, Mapping)
                            else None
                        ),
                        deleted_at=(
                            payload.get("deleted_at")
                            if isinstance(payload, Mapping)
                            else None
                        ),
                        **meta_data,
                    )
                except Exception as exc:  # pragma: no cover - network dependent
                    logging.exception(
                        "Errore durante la fetch di %s", request.class_name
                    )
                    meta_data = _index_meta_from_payload(payload)
                    record_status = _record_status_from_result("error")
                    return destination.name, build_index_entry(
                        request,
                        None,
                        "error",
                        str(exc),
                        (
                            payload.get("step_audit")
                            if isinstance(payload, Mapping)
                            else None
                        ),
                        (
                            (
                                completeness_errors
                                if "completeness_errors" in locals()
                                else None
                            ),
                        ),
                        (
                            payload.get("ruling_badge")
                            if isinstance(payload, Mapping)
                            else None
                        ),
                        (
                            payload.get("ruling_sources")
                            if isinstance(payload, Mapping)
                            else None
                        ),
                        record_status=record_status,
                        audit=(
                            payload.get("audit")
                            if isinstance(payload, Mapping)
                            else None
                        ),
                        is_deleted=(
                            payload.get("is_deleted")
                            if isinstance(payload, Mapping)
                            else None
                        ),
                        deleted_at=(
                            payload.get("deleted_at")
                            if isinstance(payload, Mapping)
                            else None
                        ),
                        **meta_data,
                    )

        def _record_build_result(entry: Mapping) -> None:
            combo_id = entry.get("combo_id") if isinstance(entry, Mapping) else None
            if combo_best_only and combo_id:
                class_slug = slugify(str(entry.get("class") or ""))
                try:
                    combo_level = int(entry.get("level")) if entry.get("level") else 0
                except (TypeError, ValueError):
                    combo_level = 0
                combo_key = (class_slug, combo_level)
                best_entry = best_combo_scores.get(combo_key)
                best_path = best_entry[1] if best_entry else None
                key = f"{class_slug}@{combo_level}"
                if best_path:
                    candidate_path = entry.get("file")
                    if (
                        not candidate_path
                        or Path(candidate_path).resolve() != best_path.resolve()
                    ):
                        return
                elif key in build_results:
                    return
            else:
                key = (
                    entry.get("file")
                    or f"{entry.get('output_prefix')}@{entry.get('level')}"
                )

            if key:
                build_results[str(key)] = entry

        module_results: dict[str, Mapping] = {}

        async def process_module(name: str, destination: Path) -> tuple[str, Mapping]:
            async with semaphore:
                if skip_unchanged and destination.exists():
                    logging.info("Riutilizzo modulo locale %s (skip-unchanged)", name)
                    cached_meta = None
                    if name in existing_module_entries:
                        cached_meta = existing_module_entries[name].get("meta")
                    normalized_meta = _normalize_module_meta(
                        cached_meta,
                        record_status=_record_status_from_result("ok"),
                        actor="generate_build_db",
                        note="cached module reuse",
                    )
                    return name, module_index_entry(
                        name, destination, "ok", normalized_meta
                    )

                logging.info("Scarico modulo raw %s", name)
                try:
                    content, meta = await fetch_module(
                        client, api_key, name, max_retries
                    )
                    validation_error = validate_with_schema(
                        MODULE_SCHEMA,
                        meta,
                        f"module meta {name}",
                        strict=strict,
                    )
                    status = "ok" if validation_error is None else "invalid"
                    record_status = _record_status_from_result(status)
                    destination_path: Path | None = None
                    normalized_meta = _normalize_module_meta(
                        meta,
                        record_status=record_status,
                        actor="generate_build_db",
                        note=(
                            None
                            if validation_error is None
                            else f"meta validation: {validation_error}"
                        ),
                    )
                    if status == "ok" or keep_invalid:
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        destination.write_text(content, encoding="utf-8")
                        destination_path = destination
                    elif destination.exists():
                        destination.unlink()
                    return name, module_index_entry(
                        name,
                        destination_path,
                        status,
                        (
                            normalized_meta
                            if validation_error is None
                            else normalized_meta
                        ),
                        validation_error,
                    )
                except ValidationError:
                    raise
                except Exception as exc:  # pragma: no cover - network dependent
                    logging.exception("Errore durante il download di %s", name)
                    return name, module_index_entry(name, None, "error", error=str(exc))

        async def process_plan(
            plan: Iterable[tuple[object, ...]] | Iterable[object],
            launcher: callable,
            consume_result: callable,
        ) -> None:
            iterator = iter(plan)
            in_flight: set[asyncio.Task] = set()

            def _launch_next() -> None:
                try:
                    task_args = next(iterator)
                except StopIteration:
                    return
                if not isinstance(task_args, tuple):
                    task_args = (task_args,)
                in_flight.add(asyncio.create_task(launcher(*task_args)))

            for _ in range(max(1, concurrency)):
                _launch_next()

            while in_flight:
                done, pending = await asyncio.wait(
                    in_flight, return_when=asyncio.FIRST_COMPLETED
                )
                in_flight = pending
                for task in done:
                    try:
                        result = await task
                    except Exception:
                        for pending_task in pending:
                            pending_task.cancel()
                        await asyncio.gather(*pending, return_exceptions=True)
                        raise
                    consume_result(result)
                    _launch_next()

        await process_plan(
            planned_snapshots,
            lambda req, dest, base: process_class(req, dest, base),
            lambda result: _record_build_result(result[1]),
        )

        await process_plan(
            ((name, modules_output_dir / name) for name in module_plan),
            lambda name, path: process_module(name, path),
            lambda result: module_results.__setitem__(result[0], result[1]),
        )

    new_build_entries = build_results

    merged_build_entries = []
    for key in sorted(set(new_build_entries) | set(existing_build_entries)):
        if key in new_build_entries:
            merged_build_entries.append(new_build_entries[key])
        else:
            merged_build_entries.append(existing_build_entries[key])

    builds_index["entries"] = merged_build_entries
    builds_index["checkpoints"] = _checkpoint_summary_from_entries(
        builds_index["entries"]
    )
    new_module_entries = dict(module_results)
    merged_module_entries = []
    for name in sorted(set(new_module_entries) | set(existing_module_entries)):
        if name in new_module_entries:
            merged_module_entries.append(new_module_entries[name])
        else:
            merged_module_entries.append(existing_module_entries[name])

    modules_index["entries"] = merged_module_entries
    if discovery_info:
        modules_index["discovery"] = discovery_info

    if ruling_cache is not None:
        await ruling_cache.flush()

    write_json(index_path, builds_index)
    write_json(module_index_path, modules_index)
    logging.info("Indici aggiornati: %s e %s", index_path, module_index_path)

    if fail_on_invalid:
        # NB: 'cached' è uno stato valido (es. --skip-unchanged). 'pruned' viene ignorato.
        ok_build_status = {"ok", "cached", "pruned"}
        ok_module_status = {"ok", "cached"}

        bad_builds = [
            entry
            for entry in merged_build_entries
            if entry.get("status") not in ok_build_status
        ]

        # Se l'utente ha chiesto esplicitamente di saltare i moduli, non ha senso
        # fallire per errori residui di moduli eventualmente presenti nell'indice.
        if skip_modules:
            bad_modules: list[dict[str, object]] = []
        else:
            bad_modules = [
                entry
                for entry in merged_module_entries
                if entry.get("status") not in ok_module_status
            ]

        if bad_builds or bad_modules:
            logging.error(
                "--fail-on-invalid: trovate %d build non valide e %d moduli non validi%s",
                len(bad_builds),
                len(bad_modules),
                (
                    " (controllo moduli saltato per --skip-modules)"
                    if skip_modules
                    else ""
                ),
            )

            def _format_entry_path(entry: Mapping[str, object]) -> str:
                file_value = entry.get("file") or entry.get("output_file")
                if not isinstance(file_value, str) or not file_value:
                    return "<file mancante>"
                file_path = Path(file_value)
                base_dir = modules_output_dir if entry.get("module") else output_dir
                if not file_path.is_absolute():
                    file_path = base_dir / file_path
                return str(file_path)

            for entry in bad_builds[:10]:
                logging.error(
                    "Build non valida: %s (%s)",
                    _format_entry_path(entry),
                    entry.get("status"),
                )
            for entry in bad_modules[:10]:
                module_name = entry.get("module") or entry.get("name") or "<modulo>"
                logging.error(
                    "Modulo non valido: %s @ %s (%s)",
                    module_name,
                    _format_entry_path(entry),
                    entry.get("status"),
                )

            raise SystemExit(2)


def _snapshot_request_from_payload(payload: Mapping[str, object]) -> BuildRequest:
    request_meta = payload.get("request")
    if isinstance(request_meta, Mapping):
        class_name = request_meta.get("class") or payload.get("class") or "Unknown"
        mode = request_meta.get("mode") or payload.get("mode") or DEFAULT_MODE
        race = (
            request_meta.get("race")
            if isinstance(request_meta.get("race"), str)
            else None
        )
        archetype = (
            request_meta.get("archetype")
            if isinstance(request_meta.get("archetype"), str)
            else None
        )
        model = (
            request_meta.get("model")
            if isinstance(request_meta.get("model"), str)
            else None
        )
        background = (
            request_meta.get("background")
            if isinstance(request_meta.get("background"), str)
            else None
        )
        level = (
            request_meta.get("level")
            if isinstance(request_meta.get("level"), int)
            else None
        )
        spec_id = (
            request_meta.get("spec_id")
            if isinstance(request_meta.get("spec_id"), str)
            else None
        )
        filename_prefix = (
            request_meta.get("output_prefix")
            if isinstance(request_meta.get("output_prefix"), str)
            else None
        )
        return BuildRequest(
            class_name=str(class_name),
            mode=str(mode),
            race=race,
            archetype=archetype,
            model=model,
            background=background,
            level=level,
            spec_id=spec_id,
            filename_prefix=filename_prefix,
        )
    class_name = payload.get("class") or "Unknown"
    mode = payload.get("mode") or DEFAULT_MODE
    level = payload.get("level") if isinstance(payload.get("level"), int) else None
    return BuildRequest(class_name=str(class_name), mode=str(mode), level=level)


async def backfill_ruling_badges(
    build_dir: Path,
    index_path: Path | None,
    api_key: str | None,
    ruling_expert_url: str,
    concurrency: int,
    timeout: float,
    max_retries: int,
    *,
    strict_mode: bool = False,
    dry_run: bool = False,
    max_items: int = 0,
) -> int:
    files = sorted(p for p in build_dir.rglob("*.json") if p.is_file())
    if index_path is not None:
        files = [p for p in files if p.resolve() != index_path.resolve()]
    if max_items and max_items > 0:
        files = files[:max_items]
    logging.info("Backfill ruling_badges: %d file in %s", len(files), build_dir)
    sem = asyncio.Semaphore(max(1, concurrency))
    updated: list[tuple[Path, str | None, list[str] | None]] = []

    async with httpx.AsyncClient(timeout=timeout) as client:

        async def _work(file_path: Path) -> None:
            async with sem:
                try:
                    payload = json.loads(file_path.read_text(encoding="utf-8"))
                except Exception as exc:
                    logging.warning("Backfill: JSON invalido %s (%s)", file_path, exc)
                    return
                if not isinstance(payload, MutableMapping):
                    return
                existing = payload.get("ruling_badge")
                if isinstance(existing, str) and existing.strip():
                    return

                qa = payload.get("qa")
                if isinstance(qa, Mapping):
                    re_data = qa.get("ruling_expert")
                    if isinstance(re_data, Mapping):
                        badge = re_data.get("badge")
                        if isinstance(badge, str) and badge.strip():
                            payload["ruling_badge"] = badge.strip()
                            sources = re_data.get("sources")
                            if isinstance(sources, list) and sources:
                                payload["ruling_sources"] = sources
                            payload.setdefault("benchmark", {}).setdefault(
                                "ruling_badge", badge.strip()
                            )
                            if not dry_run:
                                write_json(file_path, payload)
                            updated.append(
                                (
                                    file_path,
                                    payload.get("ruling_badge"),
                                    payload.get("ruling_sources"),
                                )
                            )
                            return

                req = _snapshot_request_from_payload(payload)
                try:
                    badge, _ = await _validate_ruling_badge(
                        client,
                        url=ruling_expert_url,
                        api_key=api_key,
                        payload=payload,
                        request=req,
                        timeout=timeout,
                        max_retries=max_retries,
                    )
                except BuildFetchError as exc:
                    logging.warning("Backfill badge fallito %s: %s", file_path, exc)
                    return
                if badge:
                    payload.setdefault("benchmark", {}).setdefault(
                        "ruling_badge", badge
                    )
                if not dry_run:
                    write_json(file_path, payload)
                updated.append((file_path, badge, payload.get("ruling_sources")))

        if files:
            await asyncio.gather(*(_work(p) for p in files))

    if (not dry_run) and index_path and index_path.is_file() and updated:
        try:
            index_data = json.loads(index_path.read_text(encoding="utf-8"))
        except Exception as exc:
            logging.warning(
                "Backfill: impossibile leggere index %s (%s)", index_path, exc
            )
        else:
            entries = index_data.get("entries")
            if isinstance(entries, list):
                base_dir = index_path.parent
                mapping: dict[Path, MutableMapping[str, object]] = {}
                for e in entries:
                    if not isinstance(e, MutableMapping):
                        continue
                    file_value = e.get("file") or e.get("output_file")
                    if not isinstance(file_value, str) or not file_value:
                        continue
                    file_path = Path(file_value)
                    if not file_path.is_absolute():
                        file_path = base_dir / file_path
                    mapping[file_path.resolve()] = e
                touched = 0
                for p, badge, sources in updated:
                    entry = mapping.get(p.resolve())
                    if not entry:
                        continue
                    if badge:
                        entry["ruling_badge"] = badge
                    if sources:
                        entry["ruling_sources"] = sources
                    touched += 1
                if touched:
                    write_json(index_path, index_data)
                    logging.info(
                        "Backfill: aggiornato index %s (%d entries)",
                        index_path,
                        touched,
                    )

    return len(updated)


def run_dual_pass_harvest(args: argparse.Namespace) -> Mapping[str, Any]:
    race_inventory = load_race_inventory(args.race_inventory)
    built_requests = build_requests_from_args(args)
    try:
        requests, combo_matrix_used, spec_path = built_requests
    except ValueError:
        requests, combo_matrix_used = built_requests
        spec_path = None
    requests = [replace(req, stub=args.stub) for req in requests]
    requests = assign_missing_races(
        requests,
        race_inventory,
        prefer_unused_race=args.prefer_unused_race,
        race_pool=args.race_pool,
    )

    combo_best_only = combo_matrix_used and not args.keep_all_combos
    requests = filter_requests(
        requests,
        args.filter_classes,
        args.filter_levels,
    )
    requests, window = select_request_window(
        requests,
        offset=args.offset,
        max_items=args.max_items,
        page=args.page,
        page_size=args.page_size,
    )
    log_request_batch(requests, window)
    strict_output_dir = args.output_dir / "strict"
    strict_modules_dir = args.modules_output_dir / "strict"
    strict_build_index = path_with_suffix(args.index_path, "strict")
    strict_module_index = path_with_suffix(args.module_index_path, "strict")

    report: dict[str, Any] = {
        "strict": {
            "output_dir": str(strict_output_dir),
            "modules_output_dir": str(strict_modules_dir),
            "build_index": str(strict_build_index),
            "module_index": str(strict_module_index),
        },
        "tolerant": {
            "output_dir": str(args.output_dir),
            "modules_output_dir": str(args.modules_output_dir),
            "build_index": str(args.index_path),
            "module_index": str(args.module_index_path),
            "keep_invalid": True,
        },
    }

    try:
        asyncio.run(
            run_harvest(
                requests,
                args.api_url,
                args.api_key,
                strict_output_dir,
                strict_build_index,
                args.modules,
                strict_modules_dir,
                strict_module_index,
                args.concurrency,
                args.max_retries,
                spec_path,
                args.discover_modules,
                args.include,
                args.exclude,
                strict=True,
                keep_invalid=False,
                require_complete=args.require_complete,
                skip_health_check=args.skip_health_check,
                health_path=args.health_path,
                health_timeout=args.health_timeout,
                level_filters=args.filter_levels,
                skip_unchanged=args.skip_unchanged,
                max_items=args.max_items,
                ruling_expert_url=args.ruling_expert_url,
                ruling_timeout=args.ruling_timeout,
                ruling_max_retries=args.ruling_max_retries,
                skip_ruling_expert=args.skip_ruling_expert,
                t1_filter=args.t1_filter,
                t1_variants=args.t1_variants,
                lazy_ruling=args.lazy_ruling,
                reference_dir=args.reference_dir,
                suggest_combos=args.suggest_combos,
                validate_combo=args.validate_combo,
                catalog_policy=args.catalog_policy,
                numeric_completeness=args.numeric_completeness,
                combo_best_only=combo_best_only,
                ruling_cache_path=args.ruling_cache,
                ruling_concurrency=args.ruling_concurrency,
                skip_modules=args.skip_modules,
                # In dual-pass la passata tolerant deve poter completare prima
                # di decidere se fallire (altrimenti lo strict può abortire presto).
                fail_on_invalid=False,
            )
        )
        report["strict"]["status"] = "ok"
    except Exception as exc:
        logging.warning(
            "Passaggio strict fallito, procedo con il run tollerante: %s", exc
        )
        report["strict"].update({"status": "failed", "error": str(exc)})

    strict_ok = report.get("strict", {}).get("status") == "ok"
    variants_requested = bool(args.t1_filter and args.t1_variants > 1)
    extra_saves_requested = bool(args.invalid_archive_dir)
    skip_tolerant = (
        args.skip_tolerant_on_success
        and strict_ok
        and not variants_requested
        and not extra_saves_requested
    )

    if skip_tolerant:
        logging.info(
            "Passaggio tollerante saltato: esecuzione strict riuscita e nessuna variante "
            "o salvataggio aggiuntivo richiesto"
        )
        report["tolerant"]["status"] = "skipped"
        report["tolerant"]["reason"] = "strict_pass_sufficient"
        if args.dual_pass_report:
            write_json(args.dual_pass_report, report)
            logging.info("Report dual-pass salvato in %s", args.dual_pass_report)
        return report

    try:
        asyncio.run(
            run_harvest(
                requests,
                args.api_url,
                args.api_key,
                args.output_dir,
                args.index_path,
                args.modules,
                args.modules_output_dir,
                args.module_index_path,
                args.concurrency,
                args.max_retries,
                spec_path,
                args.discover_modules,
                args.include,
                args.exclude,
                strict=False,
                keep_invalid=True,
                require_complete=args.require_complete,
                skip_health_check=args.skip_health_check,
                health_path=args.health_path,
                health_timeout=args.health_timeout,
                level_filters=args.filter_levels,
                skip_unchanged=args.skip_unchanged,
                max_items=args.max_items,
                ruling_expert_url=args.ruling_expert_url,
                ruling_timeout=args.ruling_timeout,
                ruling_max_retries=args.ruling_max_retries,
                skip_ruling_expert=args.skip_ruling_expert,
                t1_filter=args.t1_filter,
                t1_variants=args.t1_variants,
                lazy_ruling=args.lazy_ruling,
                reference_dir=args.reference_dir,
                suggest_combos=args.suggest_combos,
                validate_combo=args.validate_combo,
                catalog_policy=args.catalog_policy,
                numeric_completeness=args.numeric_completeness,
                combo_best_only=combo_best_only,
                ruling_cache_path=args.ruling_cache,
                ruling_concurrency=args.ruling_concurrency,
                skip_modules=args.skip_modules,
                fail_on_invalid=args.fail_on_invalid,
            )
        )
        report["tolerant"]["status"] = "ok"
        if args.invalid_archive_dir:
            analysis = analyze_indices(
                args.index_path,
                args.module_index_path,
                archive_dir=args.invalid_archive_dir,
            )
        else:
            analysis = analyze_indices(args.index_path, args.module_index_path)
        report["analysis"] = analysis
    except Exception as exc:
        logging.error("Passaggio tollerante fallito: %s", exc)
        report["tolerant"].update({"status": "failed", "error": str(exc)})

    if args.dual_pass_report:
        write_json(args.dual_pass_report, report)
        logging.info("Report dual-pass salvato in %s", args.dual_pass_report)

    return report


def main() -> None:
    args = parse_args()
    logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")

    if args.export_lists:
        outputs = export_build_reports(
            args.output_dir,
            args.reports_dir,
            module_dir=args.modules_output_dir,
            build_index_path=args.index_path,
            module_index_path=args.module_index_path,
            invalid_archive_dir=args.invalid_archive_dir,
        )
        for key, path in outputs.items():
            logging.info("Report %s esportato in %s", key, path)
        return

    if args.dual_pass and args.validate_db:
        raise ValueError("--dual-pass non è compatibile con --validate-db")

    if args.export_races:
        export_race_inventory(
            args.output_dir, args.race_inventory, race_pool=args.race_pool
        )
        return

    if (
        (not args.skip_ruling_expert)
        and (not args.ruling_expert_url)
        and (not args.validate_db)
    ):
        raise ValueError(
            "--ruling-expert-url è obbligatorio per salvare nuovi snapshot (oppure usa --skip-ruling-expert per debug)"
        )

    if args.dual_pass:
        run_dual_pass_harvest(args)
        return

    race_inventory = load_race_inventory(args.race_inventory)
    requests, combo_matrix_used, spec_path = build_requests_from_args(args)
    requests = [replace(req, stub=args.stub) for req in requests]
    requests = assign_missing_races(
        requests,
        race_inventory,
        prefer_unused_race=args.prefer_unused_race,
        race_pool=args.race_pool,
    )

    requests = filter_requests(
        requests,
        args.filter_classes,
        args.filter_levels,
    )
    requests, window = select_request_window(
        requests,
        offset=args.offset,
        max_items=args.max_items,
        page=args.page,
        page_size=args.page_size,
    )
    log_request_batch(requests, window)
    strict_mode = args.strict and not args.warn_only
    combo_best_only = combo_matrix_used and not args.keep_all_combos

    if args.backfill_badges:
        if not args.ruling_expert_url:
            raise ValueError("--ruling-expert-url è obbligatorio per --backfill-badges")
        updated = asyncio.run(
            backfill_ruling_badges(
                build_dir=args.output_dir,
                index_path=args.index_path,
                api_key=args.api_key,
                ruling_expert_url=args.ruling_expert_url,
                concurrency=args.concurrency,
                timeout=args.ruling_timeout,
                max_retries=args.ruling_max_retries,
                strict_mode=strict_mode,
                dry_run=args.backfill_badges_dry_run,
                max_items=args.backfill_badges_max_items,
            )
        )
        logging.info("Backfill completato: %d snapshot aggiornati", updated)
        if not args.validate_db:
            return

    if args.validate_db:
        review_local_database(
            args.output_dir,
            args.modules_output_dir,
            build_index_path=args.index_path,
            module_index_path=args.module_index_path,
            strict=strict_mode,
            output_path=args.review_output,
            reference_dir=args.reference_dir,
        )
        return

    asyncio.run(
        run_harvest(
            requests,
            args.api_url,
            args.api_key,
            args.output_dir,
            args.index_path,
            args.modules,
            args.modules_output_dir,
            args.module_index_path,
            args.concurrency,
            args.max_retries,
            spec_path,
            args.discover_modules,
            args.include,
            args.exclude,
            strict_mode,
            args.keep_invalid,
            args.require_complete,
            skip_health_check=args.skip_health_check,
            health_path=args.health_path,
            health_timeout=args.health_timeout,
            level_filters=args.filter_levels,
            skip_unchanged=args.skip_unchanged,
            max_items=args.max_items,
            ruling_expert_url=args.ruling_expert_url,
            ruling_timeout=args.ruling_timeout,
            ruling_max_retries=args.ruling_max_retries,
            skip_ruling_expert=args.skip_ruling_expert,
            t1_filter=args.t1_filter,
            t1_variants=args.t1_variants,
            lazy_ruling=args.lazy_ruling,
            combo_best_only=combo_best_only,
            reference_dir=args.reference_dir,
            suggest_combos=args.suggest_combos,
            validate_combo=args.validate_combo,
            catalog_policy=args.catalog_policy,
            numeric_completeness=args.numeric_completeness,
            ruling_cache_path=args.ruling_cache,
            ruling_concurrency=args.ruling_concurrency,
            skip_modules=args.skip_modules,
            fail_on_invalid=args.fail_on_invalid,
        )
    )


if __name__ == "__main__":
    main()
