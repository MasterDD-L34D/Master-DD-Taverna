#!/usr/bin/env python3
"""Import PCGen delle proficienze di classe (armi/armature/scudi).

Slice D6 (2026-08-08) del piano
`sessione-2026-07-16/rapporti/2026-08-02-piano-completamento-db-pcgen-pathbuilder.md`.

Serve alla legality equipaggiamento del builder (D6): "il personaggio e'
competente in quest'arma/armatura?" e' un FATTO del dato PCGen, non una
euristica sui nomi. Il plumbing PCGen usa forme DIVERSE per classe
(ricognizione 2026-08-08):

1. righe `CATEGORY=Class|<Classe>[ ~ Standard ...].MOD` con grant
   `ABILITY:Internal|AUTOMATIC|...` ("Weapon Prof ~ Simple",
   "TYPE=ArmorProfMedium", "Shield Prof", "Weapon Proficiencies ~ Bard"),
   `ABILITY:FEAT|AUTOMATIC|Armor Proficiency (Light)` (Ninja, Samurai) e
   `ABILITY:Special Ability|AUTOMATIC|All Martial Weapon Proficiencies|...`;
2. record ability della classe con AUTO:WEAPONPROF/AUTO:ARMORPROF propri:
   `<Classe> ~ Weapon and Armor Proficiency` (Wizard, Cleric),
   `Weapon and Armor Proficiency ~ <Classe>` (Fighter, Paladin),
   `<Classe> ~ Proficiencies` (Gunslinger), `<Classe> ~ Weapon Proficiencies`
   (Ninja), `<Classe> ~ Weapon and Armor Proficiencies` (Vigilante, fuori
   perimetro libri: NON importato, corpus_missing dichiarato);
3. record condivisi referenziati dai grant: `Weapon Proficiencies ~ <Classe>`
   (Bard, Druid, Monk, Rogue), `All Martial Weapon Proficiencies`,
   `All Automatic Proficiencies` (Unarmed Strike + ray/touch),
   `Samurai Proficiencies`, `Martial Weapon Proficiency Output`.

Regole dichiarate:
- il livello di concessione e' il gate PREVARGTEQ intero minimo sul grant
  referenziante (stessa regola di import_pcgen_classes): Magus medium al 7°;
- `!PREABILITY ...CATEGORY=Archetype...` = "se non sostituito da archetipo":
  il grant di base resta; gli swap da archetipo sono FUORI SCOPE D6;
- DEITYWEAPONS -> grant `deity_weapons` (la divinita' non e' un fatto della
  scheda: il motore lo dichiara unknown, mai indovinato);
- `%LIST` e feat di proficienza NUDI a scelta ("Exotic Weapon Proficiency")
  -> grant `choice` (scelta non registrata: unknown dal motore);
- nomi di grant non risolti -> SOLO report (counts.unmapped_names), mai
  indovinati e mai nel dataset;
- i segmenti espliciti restano VERBATIM ("Flurry of Blows" del Monk e' nel
  dato: non matcha mai un'arma del catalogo, innocuo; niente curatela);
- i grant ABILITY di feature NON di proficienza (Class Skills, tracker,
  spellbook) sono fuori dominio di QUESTO dataset: non raccolti, non
  contati uno a uno (scope dichiarato: solo proficienze).

Perimetro: i BOOK_CLASS_FILES di import_pcgen_classes (CR/APG/ACG/ARG/UM/UC/
OA + Fase A 2026-08-08: UI/UW con Vigilante e Shifter, HA/PU/AG abilities).
Gap del dato colmati SOLO da supplemento curato dichiarato (vedi
CURATED_SUPPLEMENT: grant con "curated": true e puntamento RAW AoN, mai
silenziosi). DESC/BENEFIT MAI letti.

Uso:
  python tools/import_pcgen_proficiencies.py                 # scrive il JSON
  python tools/import_pcgen_proficiencies.py --report-only   # solo stdout
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
    DATA_SUBDIR,
    DEFAULT_OUT_DIR,
    DEFAULT_PCGEN_REPO,
    DESC_POLICY,
    LICENSE_TEXT,
    _pcgen_commit,
    _split_pipes,
    iter_lst_records,
)
from tools.import_pcgen_classes import (  # noqa: E402
    BOOK_CLASS_FILES,
    _known_classes,
    extract_level_gate,
    parse_ability_grant,
)

OUTPUT_FILE = "pcgen-class-proficiencies.json"

# ---------------------------------------------------------------------------
# Mappe DICHIARATE nome di grant -> fatto di proficienza.
# Un nome fuori mappa e' unmapped (report), mai indovinato.
# ---------------------------------------------------------------------------

GRANT_NAME_MAP = {
    "Weapon Prof ~ Simple": ("weapon_type", "simple"),
    "TYPE=WeaponProfSimple": ("weapon_type", "simple"),
    "Weapon Prof ~ Martial": ("weapon_type", "martial"),
    "TYPE=WeaponProfMartial": ("weapon_type", "martial"),
    "Weapon Prof ~ Exotic": ("weapon_type", "exotic"),
    "TYPE=WeaponProfExotic": ("weapon_type", "exotic"),
    "Exotic Weapon Proficiency ~ Firearms": ("weapon_type", "firearm"),
    "TYPE=WeaponProfFirearm": ("weapon_type", "firearm"),
    "TYPE=Firearm": ("weapon_type", "firearm"),
    "Weapon Prof ~ Auto": ("auto_weapons", None),
    "TYPE=WeaponProfAuto": ("auto_weapons", None),
    "Weapon Prof ~ Deity Weapons": ("deity_weapons", None),
    "Armor Prof ~ Light": ("armor_type", "light"),
    "TYPE=ArmorProfLight": ("armor_type", "light"),
    "Armor Prof ~ Medium": ("armor_type", "medium"),
    "TYPE=ArmorProfMedium": ("armor_type", "medium"),
    "Armor Prof ~ Heavy": ("armor_type", "heavy"),
    "TYPE=ArmorProfHeavy": ("armor_type", "heavy"),
    "Shield Prof": ("shield", None),
    "TYPE=ShieldProf": ("shield", None),
    "TYPE=ArmorProfShield": ("shield", None),
    "Shield Prof ~ Tower": ("tower_shield", None),
    "TYPE=ArmorProfTower": ("tower_shield", None),
    # Buckler-only (Swashbuckler): NON e' "tutti gli scudi" — kind separato,
    # il motore lo applica solo all'item Buckler (dichiarato).
    "Shield Prof ~ Buckler": ("buckler", None),
    # Record FEAT PCGen "Martial Weapon Proficiency Output" (VISIBLE:EXPORT,
    # "all martial weapons"): concesso per nome dal MOD del Samurai.
    "Martial Weapon Proficiency Output": ("weapon_type", "martial"),
}

# Talenti di proficienza concessi come ABILITY:FEAT (Ninja, Samurai, ...).
# Forma nuda "Martial Weapon Proficiency" = TUTTE le marziali (il record FEAT
# PCGen "Martial Weapon Proficiency Output" conferma: AUTO:WEAPONPROF|
# TYPE=Martial). "Exotic Weapon Proficiency" nuda = scelta non registrata
# (il feat e' per-arma): choice, unknown dal motore.
FEAT_PROF_MAP = {
    "Simple Weapon Proficiency": ("weapon_type", "simple"),
    "Martial Weapon Proficiency": ("weapon_type", "martial"),
    "Exotic Weapon Proficiency": ("choice", "Exotic Weapon Proficiency"),
    "Armor Proficiency (Light)": ("armor_type", "light"),
    "Armor Proficiency (Medium)": ("armor_type", "medium"),
    "Armor Proficiency (Heavy)": ("armor_type", "heavy"),
    "Shield Proficiency": ("shield", None),
    "Tower Shield Proficiency": ("tower_shield", None),
}

# "Exotic Weapon Proficiency (Katana)" -> arma esplicita.
_FEAT_CHOICE_RE = re.compile(r"^(?:Exotic|Martial) Weapon Proficiency \((.+)\)$")

# SUPPLEMENTO CURATO (Fase A 2026-08-08): gap del dato PCGen colmati a mano
# col RAW verificato su AoN — MAI silenzioso: ogni grant porta
# "curated": true e il puntamento RAW in "raw". Il record PCGen del
# Vigilante (ui_abilities_class.lst) concede SOLO marziali/medie/scudo,
# ma il RAW e' "proficient with all simple and martial weapons, light
# armor, medium armor, and shields (except tower shields)" (Ultimate
# Intrigue p.9, AoN ClassDisplay Vigilante, verificato 2026-08-08). Stesso
# gap per l'armatura leggera dello Shifter (Ultimate Wilderness p.26, AoN
# ClassDisplay Shifter, verificato 2026-08-08: "proficient with light and
# medium armor"; il divieto del metallo resta NON modellato, dichiarato
# come le restrizioni druidiche D6).
CURATED_SUPPLEMENT: dict[str, list[dict]] = {
    "Vigilante": [
        {
            "kind": "weapon_type",
            "value": "simple",
            "level": 1,
            "curated": True,
            "raw": "CURATO: RAW UI p.9 (AoN ClassDisplay Vigilante, 2026-08-08) "
            "— il record PCGen omette il grant separato delle semplici",
        },
        {
            "kind": "armor_type",
            "value": "light",
            "level": 1,
            "curated": True,
            "raw": "CURATO: RAW UI p.9 (AoN ClassDisplay Vigilante, 2026-08-08) "
            "— il record PCGen omette il grant separato delle leggere",
        },
    ],
    "Shifter": [
        {
            "kind": "armor_type",
            "value": "light",
            "level": 1,
            "curated": True,
            "raw": "CURATO: RAW UW p.26 (AoN ClassDisplay Shifter, 2026-08-08) "
            "— il record PCGen omette il grant separato delle leggere",
        },
    ],
}

# Valori ARMORTYPE= (con e senza prefisso ArmorProf, entrambe attestate).
ARMORTYPE_MAP = {
    "Light": ("armor_type", "light"),
    "ArmorProfLight": ("armor_type", "light"),
    "Medium": ("armor_type", "medium"),
    "ArmorProfMedium": ("armor_type", "medium"),
    "Heavy": ("armor_type", "heavy"),
    "ArmorProfHeavy": ("armor_type", "heavy"),
    "Shield": ("shield", None),
    "ArmorProfShield": ("shield", None),
    "Tower": ("tower_shield", None),
    "ArmorProfTower": ("tower_shield", None),
    "TowerShield": ("tower_shield", None),
}

# Segmenti TYPE= degli AUTO:WEAPONPROF. "Auto" = attacchi automatici della
# classe (unarmed/ray/touch — dato, significato dichiarato nel JSON).
WEAPONPROF_TYPE_MAP = {
    "Simple": ("weapon_type", "simple"),
    "Martial": ("weapon_type", "martial"),
    "Exotic": ("weapon_type", "exotic"),
    "Firearm": ("weapon_type", "firearm"),
    "Auto": ("auto_weapons", None),
    # PCGen TYPE:Monk = gruppo armi Monk (gli item portano il type "Monk").
    "Monk": ("weapon_group", "Monk"),
}

_MOD_NAME = re.compile(r"^CATEGORY=([^|]+)\|(.+)\.MOD$")
_STANDARD_SUFFIXES = (
    " ~ Standard Class Full",
    " ~ Standard Class",
    " ~ Standard Ex-Class",
)

# Parti di KEY (dopo split " ~ ") che identificano il record proficienze di
# una classe: l'ALTRA parte e' la classe. Forme attestate (ricognizione
# 2026-08-08). I record degli archetipi matchano ma li filtra known_classes.
_PROF_RECORD_PARTS = {
    "weapon and armor proficiency",
    "weapon and armor proficiencies",
    "armor and weapon proficiencies",
    "proficiencies",
    "weapon proficiencies",
}


def _prof_record_class(key: str) -> str | None:
    parts = key.split(" ~ ")
    if len(parts) != 2:
        return None
    for i, part in enumerate(parts):
        if part.lower() in _PROF_RECORD_PARTS:
            return parts[1 - i]
    return None


def _grant(kind: str, value: str | None, level: int, raw: str) -> dict:
    g = {"kind": kind, "level": level, "raw": raw}
    if value is not None:
        g["value"] = value
    return g


def parse_auto_weaponprof(
    value: str, raw: str, report: dict | None = None
) -> list[dict]:
    """Segmenti di un AUTO:WEAPONPROF (senza il prefisso) -> grants."""
    grants: list[dict] = []
    conditions: list[str] = []
    for seg in _split_pipes(value):
        if not seg:
            continue
        if seg.startswith("PRE") or seg.startswith("!PRE"):
            conditions.append(seg)
        elif seg == "%LIST":
            grants.append(_grant("choice", "%LIST", 1, raw))
        elif seg == "DEITYWEAPONS":
            grants.append(_grant("deity_weapons", None, 1, raw))
        elif seg.startswith("TYPE=Weapon Group "):
            grants.append(
                _grant("weapon_group", seg[len("TYPE=Weapon Group ") :], 1, raw)
            )
        elif seg.startswith("TYPE="):
            mapped = WEAPONPROF_TYPE_MAP.get(seg[len("TYPE=") :])
            if mapped:
                grants.append(_grant(*mapped, 1, raw))
            else:
                _report_unmapped(report, seg)
        else:
            grants.append(_grant("weapon", seg, 1, raw))
    level = extract_level_gate(conditions)
    if level != 1:
        for g in grants:
            g["level"] = level
    return grants


def parse_auto_armorprof(
    value: str, raw: str, report: dict | None = None
) -> list[dict]:
    grants: list[dict] = []
    conditions: list[str] = []
    for seg in _split_pipes(value):
        if not seg:
            continue
        if seg.startswith("PRE") or seg.startswith("!PRE"):
            conditions.append(seg)
            continue
        name = seg[len("ARMORTYPE=") :] if seg.startswith("ARMORTYPE=") else seg
        mapped = ARMORTYPE_MAP.get(name)
        if mapped:
            grants.append(_grant(*mapped, 1, raw))
        else:
            _report_unmapped(report, seg)
    level = extract_level_gate(conditions)
    if level != 1:
        for g in grants:
            g["level"] = level
    return grants


def _report_unmapped(report: dict | None, name: str) -> None:
    if report is not None:
        report.setdefault("unmapped_names", {})[name] = (
            report.setdefault("unmapped_names", {}).get(name, 0) + 1
        )


def resolve_grant_name(
    name: str, level: int, raw: str, shared: dict, report: dict | None = None
) -> list[dict]:
    """Un nome di grant ABILITY -> fatti di proficienza (o report)."""
    if name in GRANT_NAME_MAP:
        kind, value = GRANT_NAME_MAP[name]
        g = _grant(kind, value, level, raw)
        return [g]
    if name.startswith("TYPE=Weapon Group "):
        return [_grant("weapon_group", name[len("TYPE=Weapon Group ") :], level, raw)]
    if name == "TYPE=Monk":
        # Forma attestata (1 occorrenza): gruppo armi Monk come TYPE nudo.
        return [_grant("weapon_group", "Monk", level, raw)]
    if name in FEAT_PROF_MAP:
        kind, value = FEAT_PROF_MAP[name]
        return [_grant(kind, value, level, raw)]
    m = _FEAT_CHOICE_RE.match(name)
    if m:
        return [_grant("weapon", m.group(1), level, raw)]
    if name in shared:
        facts = shared[name]
        out = []
        for f in facts:
            g = dict(f)
            if level != 1:
                g["level"] = level
            g["raw"] = raw
            out.append(g)
        return out
    _report_unmapped(report, name)
    return []


def record_prof_facts(
    tags, raw: str, shared: dict, report: dict | None = None
) -> list[dict]:
    """I fatti di proficienza PORTATI da un record (AUTO + grant Internal/
    FEAT suoi propri), senza attribuzione di classe."""
    grants: list[dict] = []
    for k, value in tags:
        if k == "AUTO" and value.startswith("WEAPONPROF|"):
            grants.extend(
                parse_auto_weaponprof(value[len("WEAPONPROF|") :], raw, report)
            )
        elif k == "AUTO" and value.startswith("ARMORPROF|"):
            grants.extend(parse_auto_armorprof(value[len("ARMORPROF|") :], raw, report))
        elif k == "ABILITY":
            grant = parse_ability_grant(value)
            if grant["pool"] not in ("Internal", "FEAT"):
                continue
            level = extract_level_gate(grant["conditions"])
            for n in grant["names"]:
                grants.extend(resolve_grant_name(n, level, raw, shared, report))
    return grants


def parse_lst_text(
    text: str,
    source_book: str,
    shared: dict | None = None,
    known_classes: set | None = None,
    report: dict | None = None,
) -> dict:
    """Un file LST -> {classe: {"grants": [...]}} (solo fatti di proficienza).

    `shared` = tabella nome-record -> fatti (record condivisi, liste
    Internal): il chiamante la costruisce su TUTTI i file (un grant puo'
    referenziare un record di un altro libro); standalone si usa il testo.
    """
    if shared is None:
        shared = collect_shared_records(iter_lst_records(text), source_book)
    out: dict[str, dict] = {}

    def add(class_name: str, grants: list[dict]) -> None:
        if not grants:
            return
        out.setdefault(class_name, {"grants": []})["grants"].extend(grants)

    # -- righe MOD CATEGORY=Class|Target.MOD ---------------------------------
    for raw in text.splitlines():
        line = raw.strip("\n")
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        fields = [f.strip() for f in line.split("\t")]
        m = _MOD_NAME.match(fields[0])
        if not m or m.group(1).strip().lower() != "class":
            continue
        target = m.group(2)
        class_name = None
        for suffix in _STANDARD_SUFFIXES:
            if target.endswith(suffix):
                class_name = target[: -len(suffix)]
                break
        if class_name is None:
            class_name = target
        if known_classes is not None and class_name not in known_classes:
            continue
        for field in fields[1:]:
            key, sep, value = field.partition(":")
            if not sep or key != "ABILITY":
                continue
            grant = parse_ability_grant(value)
            level = extract_level_gate(grant["conditions"])
            raw_ref = f"{source_book}:{line[:120]}"
            if grant["pool"] in ("Internal", "FEAT"):
                for n in grant["names"]:
                    add(
                        class_name,
                        resolve_grant_name(n, level, raw_ref, shared, report),
                    )
            else:
                # Altri pool (Special Ability, pool di classe come "Magus
                # Class Feature"): si risolvono SOLO i nomi che portano fatti
                # di proficienza (record condivisi tipo "Magus ~ Medium
                # Armor" @7, "All Martial Weapon Proficiencies"). Il resto
                # sono feature di classe: fuori dominio, non contate.
                for n in grant["names"]:
                    if n in shared or n in GRANT_NAME_MAP or n in FEAT_PROF_MAP:
                        add(
                            class_name,
                            resolve_grant_name(n, level, raw_ref, shared, report),
                        )

    # -- record proficienze della classe (KEY "<Classe> ~ <prof>") -----------
    for name, tags in iter_lst_records(text):
        key = dict(tags).get("KEY", name)
        class_name = _prof_record_class(key)
        if class_name is None:
            continue
        if known_classes is not None and class_name not in known_classes:
            continue
        add(class_name, record_prof_facts(tags, f"{source_book}:{key}", shared, report))
    # Dedupe per classe: un record "Weapon Proficiencies ~ X" e' sia
    # attribuito direttamente sia risolto via grant che lo referenzia.
    for cls in out:
        out[cls]["grants"] = _dedupe(out[cls]["grants"])
    return out


def collect_shared_records(
    records, source_book: str, report: dict | None = None
) -> dict:
    """Nome/KEY -> fatti di proficienza, per OGNI record che ne porta.

    Copre le liste Internal ("Weapon Proficiencies ~ Monk"), i record
    condivisi ("All Martial Weapon Proficiencies", "Samurai Proficiencies",
    "Martial Weapon Proficiency Output") e i record di classe (la lookup
    per nome e' innocua: ci si arriva solo se referenziati). Le chiavi sono
    sia il NAME sia la KEY (le referenze usano entrambe, attestato).
    La ricorsione (record che referenzia record) e' risolta in DUE passate:
    prima i fatti AUTO diretti, poi i grant che puntano ad altri record.
    """
    indexed: list[tuple[str, list, str]] = []
    for name, tags in records:
        key = dict(tags).get("KEY")
        indexed.append((name, tags, key or name))

    shared: dict[str, list[dict]] = {}

    def auto_facts(tags, raw):
        facts: list[dict] = []
        for k, value in tags:
            if k == "AUTO" and value.startswith("WEAPONPROF|"):
                facts.extend(
                    parse_auto_weaponprof(value[len("WEAPONPROF|") :], raw, report)
                )
            elif k == "AUTO" and value.startswith("ARMORPROF|"):
                facts.extend(
                    parse_auto_armorprof(value[len("ARMORPROF|") :], raw, report)
                )
        return facts

    for name, tags, key in indexed:
        facts = auto_facts(tags, f"{source_book}:{key}")
        if facts:
            shared.setdefault(name, []).extend(facts)
            if key != name:
                shared.setdefault(key, []).extend(facts)
    # Seconda passata: grant ABILITY del record risolti contro la tabella.
    for name, tags, key in indexed:
        facts = record_prof_facts(tags, f"{source_book}:{key}", shared, report)
        direct = auto_facts(tags, f"{source_book}:{key}")
        extra = [f for f in facts if f not in direct]
        if extra:
            shared.setdefault(name, []).extend(extra)
            if key != name:
                shared.setdefault(key, []).extend(extra)
    return shared


def _dedupe(grants: list[dict]) -> list[dict]:
    seen = set()
    out = []
    for g in grants:
        key = (g["kind"], g.get("value"), g["level"])
        if key in seen:
            continue
        seen.add(key)
        out.append(g)
    out.sort(key=lambda g: (g["kind"], str(g.get("value")), g["level"]))
    return out


def build_file(
    pcgen_root: Path,
    corpus_classes: list[str] | None = None,
    generated_by: str = "Master-DD-Taverna/tools/import_pcgen_proficiencies.py",
) -> dict:
    known = _known_classes(pcgen_root)
    report: dict = {"unmapped_names": {}}
    by_class: dict[str, dict] = {}

    files: list[tuple[str, Path]] = []
    for book, cfg in BOOK_CLASS_FILES.items():
        for rel in cfg["classes"] + cfg["abilities"] + cfg["mod_files"]:
            path = pcgen_root / DATA_SUBDIR / cfg["dir"] / rel
            if not path.is_file():
                raise FileNotFoundError(f"file LST mancante: {path}")
            files.append((book, path))
    seen_files: set[Path] = set()
    unique_files: list[tuple[str, Path]] = []
    for book, path in files:
        if path not in seen_files:
            seen_files.add(path)
            unique_files.append((book, path))

    # Prima passata: la tabella dei record condivisi su TUTTI i file.
    # NIENTE report qui: i nomi non risolti dei record qualunque (feature di
    # classe) sono fuori dominio; il report conta solo i nomi REFERENZIATI
    # dai grant di classe (seconda passata).
    shared: dict[str, list[dict]] = {}
    for book, path in unique_files:
        for name, facts in collect_shared_records(
            iter_lst_records(path.read_text(encoding="utf-8", errors="replace")), book
        ).items():
            shared.setdefault(name, []).extend(facts)

    # Seconda passata: i grant veri (MOD + record di classe).
    for book, path in unique_files:
        parsed = parse_lst_text(
            path.read_text(encoding="utf-8", errors="replace"),
            book,
            shared=shared,
            known_classes=known,
            report=report,
        )
        for cls, data in parsed.items():
            by_class.setdefault(cls, {"grants": []})["grants"].extend(data["grants"])

    classes_out = {}
    all_grants = 0
    choices: dict[str, int] = {}
    deity: list[str] = []
    curated_applied = 0
    for cls in sorted(by_class):
        grants = _dedupe(by_class[cls]["grants"])
        # Supplemento curato (gap PCGen dichiarati): aggiunto SOLO se il
        # fatto non e' gia' nel dato verbatim — il dato vince sempre.
        for supp in CURATED_SUPPLEMENT.get(cls, []):
            key = (supp["kind"], supp.get("value"), supp["level"])
            if (supp["kind"], supp.get("value")) not in {
                (g["kind"], g.get("value")) for g in grants
            }:
                grants.append(dict(supp))
                grants.sort(key=lambda g: (g["kind"], str(g.get("value")), g["level"]))
                curated_applied += 1
        classes_out[cls] = {"grants": grants}
        all_grants += len(grants)
        for g in grants:
            if g["kind"] == "choice":
                choices[cls] = choices.get(cls, 0) + 1
            if g["kind"] == "deity_weapons":
                deity.append(cls)

    corpus_covered, corpus_missing = [], []
    if corpus_classes:
        have = {c.lower() for c in classes_out}
        for c in corpus_classes:
            (corpus_covered if c.lower() in have else corpus_missing).append(c)

    return {
        "_provenance": {
            "source": (
                "PCGen data sets (github.com/PCGen/pcgen), "
                f"{DATA_SUBDIR}/roleplaying_game/* "
                "(AUTO:WEAPONPROF/AUTO:ARMORPROF + grant Internal/FEAT "
                "dei file di classe, record condivisi risolti)"
            ),
            "pcgen_commit": _pcgen_commit(pcgen_root),
            "generated_by": generated_by,
            "license": LICENSE_TEXT,
            "desc_policy": DESC_POLICY,
            "semantics": (
                "Proficienze della CLASSE BASE (archetipi esclusi: i grant "
                "condizionati !PREABILITY-Archetype sono importati come grant "
                "di base — gli swap da archetipo sono fuori scope D6). "
                "level = gate PREVARGTEQ intero minimo (1 se assente). "
                "deity_weapons = arma della divinita': non un fatto della "
                "scheda, il motore lo dichiara unknown. choice = scelta non "
                "registrata (%LIST o feat nudo a scelta). auto_weapons = "
                "attacchi automatici della classe (unarmed/ray/touch). "
                "I nomi di grant non risolti sono SOLO in "
                "counts.unmapped_names, mai indovinati. I grant ABILITY di "
                "feature non di proficienza sono fuori dominio (scope: solo "
                "proficienze)."
            ),
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "counts": {
            "classes": len(classes_out),
            "grants": all_grants,
            "curated_supplements": curated_applied,
            "corpus_covered": sorted(corpus_covered),
            "corpus_missing": sorted(corpus_missing),
            "unmapped_names": dict(sorted(report["unmapped_names"].items())),
            "classes_with_choice": dict(sorted(choices.items())),
            "classes_with_deity_weapons": sorted(set(deity)),
        },
        "classes": classes_out,
    }


def _corpus_classes(out_dir: Path) -> list[str]:
    """Le 40 classi del corpus motore (classes.json), per il report di
    copertura: una classe corpus senza dato e' unknown DICHIARATO dal
    motore, mai indovinata."""
    data = json.loads((out_dir / "classes.json").read_text(encoding="utf-8"))
    return [c["name"] for c in data]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--pcgen-repo", type=Path, default=DEFAULT_PCGEN_REPO)
    ap.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    ap.add_argument("--report-only", action="store_true")
    args = ap.parse_args(argv)

    corpus = _corpus_classes(args.out_dir)
    doc = build_file(args.pcgen_repo, corpus_classes=corpus)
    counts = dict(doc["counts"])
    counts["unmapped_names"] = f"{len(counts['unmapped_names'])} nomi"
    print(json.dumps(counts, indent=1, ensure_ascii=False))
    if args.report_only:
        return 0
    out_path = args.out_dir / OUTPUT_FILE
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"scritto {out_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
