#!/usr/bin/env python3
"""Import reference data OGC da aonprd.com (1e) in cataloghi OGL strutturati.

Ogni dominio ha un parser parse_<domain>(html) -> list[dict] (entry nel
formato catalogo) e un builder build_<domain>() che scarica le pagine via
tools.reference_fetch e scrive/aggiorna il catalogo JSON.

Uso:
  python tools/import_reference.py --domain abilities
  python tools/import_reference.py --domain races --write
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bs4 import BeautifulSoup

from tools.reference_fetch import fetch

OGL_DIR = Path(__file__).resolve().parents[1] / "data/reference/ogl"
LICENSE = "Open Game Content under OGL 1.0a. See LICENSE-OGL.txt and COPYRIGHT_NOTICE.txt."
SOURCE = "Pathfinder RPG Reference Document © 2011 Paizo Publishing, LLC; Archives of Nethys (aonprd.com)."

BASE = "https://aonprd.com/"


def slug(name):
    """Nome -> slug snake_case per source_id."""
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def source_id(source_slug, name):
    """Pattern catalogo: <slug_sorgente>:<slug_nome>."""
    return f"{source_slug}:{slug(name)}"


def clean(text):
    """Normalizza whitespace."""
    return " ".join(text.split())


def table_rows(table):
    """<table> -> lista di dict {header: cella} (header dal primo <tr>)."""
    rows = table.find_all("tr")
    if not rows:
        return []
    headers = [clean(c.get_text()) for c in rows[0].find_all(["th", "td"])]
    out = []
    for row in rows[1:]:
        cells = [clean(c.get_text()) for c in row.find_all(["th", "td"])]
        if len(cells) == len(headers) and any(cells):
            out.append(dict(zip(headers, cells)))
    return out


def write_catalog(path, entries, license_text=LICENSE, source_text=SOURCE):
    """Scrive il catalogo con header _license/_source (default: costanti AoN;
    i builder di merge passano gli header originali del catalogo esistente)."""
    payload = {"_license": license_text, "_source": source_text, "entries": entries}
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"scritto {path} ({len(entries)} entry)")


def parse_abilities(html):
    """Pagina 'Generating Ability Scores': tabella costi + budget campagna."""
    soup = BeautifulSoup(html, "html.parser")
    entries = []
    for table in soup.find_all("table"):
        trs = table.find_all("tr")
        headers = [clean(c.get_text()) for c in trs[0].find_all(["th", "td"])] if trs else []
        if "Score" in headers and "Points" in headers:
            for row in table_rows(table):
                if row.get("Score", "").isdigit():
                    name = f"Score {row['Score']}"
                    entries.append({
                        "name": name,
                        "source": "PFRPG Core",
                        "source_id": source_id("pfrpg_core", name),
                        "prerequisites": [],
                        "tags": ["ability", "point-buy"],
                        "references": ["AoN: Generating Ability Scores"],
                        "reference_urls": [BASE + "Rules.aspx?Name=Generating%20Ability%20Scores&Category=Getting%20Started"],
                        "description": f"Point-buy: il punteggio di caratteristica {row['Score']} costa {row['Points']} punti.",
                        "mechanics": {"kind": "ability_cost", "score": int(row["Score"]), "cost": int(row["Points"])},
                    })
        elif "Campaign Type" in headers:
            for row in table_rows(table):
                name = row.get("Campaign Type", "")
                if name and row.get("Points", "").lstrip("-").isdigit():
                    entries.append({
                        "name": name,
                        "source": "PFRPG Core",
                        "source_id": source_id("pfrpg_core", name),
                        "prerequisites": [],
                        "tags": ["ability", "point-buy", "campaign"],
                        "references": ["AoN: Generating Ability Scores"],
                        "reference_urls": [BASE + "Rules.aspx?Name=Generating%20Ability%20Scores&Category=Getting%20Started"],
                        "description": f"Point-buy: la campagna {name} assegna {row['Points']} punti.",
                        "mechanics": {"kind": "campaign_budget", "points": int(row["Points"])},
                    })
    return entries


RACES_CORE = ["Dwarf", "Elf", "Gnome", "Half-Elf", "Half-Orc", "Halfling", "Human"]
ABILITY_KEYS = {"strength": "str", "dexterity": "dex", "constitution": "con",
                "intelligence": "int", "wisdom": "wis", "charisma": "cha"}


def _parse_ability_mods(text):
    """'+2 Constitution, +2 Wisdom, -2 Charisma' -> {'con': 2, 'wis': 2, 'cha': -2}.
    '+2 to one ability score (your choice)' -> {'any': 2}."""
    # AoN usa l'en-dash nei modificatori negativi ("–2 Charisma"): normalizza.
    text = text.replace("–", "-")
    mods = {}
    for value, ability in re.findall(r"([+-]\d+)\s+([A-Za-z]+)", text):
        key = ABILITY_KEYS.get(ability.lower())
        if key:
            mods[key] = int(value)
    if not mods and "to one ability" in text.lower():
        mods = {"any": 2}
    return mods


def _racial_traits_bolds(soup):
    """<b> del blocco tratti base: dal heading '*Racial Traits' al prossimo
    heading (h1/h2/h3). Fallback fail-closed: se nessun heading corrisponde,
    lista vuota (su markup inatteso NON si ingoiano subrazze/alternate = PI)."""
    header = None
    for h in soup.find_all(["h1", "h2", "h3"]):
        if "racial traits" in clean(h.get_text()).lower():
            header = h
            break
    if header is None:
        return []
    bolds = []
    for sib in header.next_siblings:
        if getattr(sib, "name", None) in ("h1", "h2", "h3"):
            break
        if getattr(sib, "name", None) == "b":
            bolds.append(sib)
        elif hasattr(sib, "find_all"):
            bolds.extend(sib.find_all("b"))
    return bolds


def _bold_detail(bold, label):
    """Testo che segue il label bold.

    Markup reale AoN (flat): <b>Label</b>: testo fino a <br/> -> dai sibling.
    Markup a paragrafi (fixture): <p><b>Label</b>: testo</p> -> dal parent."""
    parts = []
    for sib in bold.next_siblings:
        if getattr(sib, "name", None) in ("br", "b"):
            break
        parts.append(sib.get_text() if hasattr(sib, "get_text") else str(sib))
    text = clean("".join(parts))
    if text:
        return clean(text.lstrip(" :"))
    parent_text = clean(bold.parent.get_text()) if bold.parent else label
    if parent_text.startswith(label):
        return clean(parent_text[len(label):].lstrip(" :"))
    return ""


def parse_race(html, race_name):
    """Pagina RacesDisplay: sezione 'Racial Traits' con righe bold-led.

    SOLO tratti base CRB (OGC): subrazze/alternate/favored options NON parse
    (PI Golarion)."""
    soup = BeautifulSoup(html, "html.parser")
    mech = {"ability_mods": {}, "size": None, "speed": None, "traits": [],
            "languages": {"auto": [], "bonus": []}}
    for bold in _racial_traits_bolds(soup):
        # I label bold reali possono chiudere con i due punti ("Darkvision:").
        label = clean(bold.get_text()).rstrip(":").strip()
        detail = _bold_detail(bold, label)
        if re.match(r"^[+-]\d+\s", label):
            mech["ability_mods"] = _parse_ability_mods(label)
        elif label in ("Medium", "Small"):
            mech["size"] = label
        elif label in ("Slow and Steady", "Slow Speed") or label.startswith("Normal Speed"):
            m = re.search(r"(\d+)\s+feet", detail)
            if m:
                mech["speed"] = int(m.group(1))
        elif label == "Languages":
            langs = re.search(r"speaking\s+([^.]+)", detail)
            if langs:
                mech["languages"]["auto"] = [clean(x) for x in re.split(r",| and ", langs.group(1)) if clean(x)]
            bonus = re.search(r"choose from\s+([^.]+)", detail)
            if bonus:
                bonus_text = re.sub(r"^the following( languages)?:\s*", "", clean(bonus.group(1)))
                mech["languages"]["bonus"] = [clean(x) for x in re.split(r",| and ", bonus_text) if clean(x)]
        elif label and label[0].isupper() and detail:
            mech["traits"].append({"name": label, "text": detail})
    traits_desc = "; ".join(t["name"] for t in mech["traits"])
    return {
        "name": race_name,
        "source": "PFRPG Core",
        "source_id": source_id("pfrpg_core", race_name),
        "prerequisites": [],
        "tags": ["race", "core", mech["size"].lower() if mech["size"] else "race"],
        "references": [f"AoN: {race_name} (Races)"],
        "reference_urls": [BASE + f"RacesDisplay.aspx?ItemName={race_name.replace(' ', '%20')}"],
        "description": (f"{race_name}: modificatori {mech['ability_mods']}, taglia {mech['size']}, "
                        f"velocita' {mech['speed']} ft. Tratti razziali: {traits_desc}."),
        "mechanics": mech,
    }


def build_races(write=False):
    """Merge in place: aggiorna le entry esistenti di races.json preservando
    i campi curati (notes, status, reviewed_by, short_description) e l'header
    (alla fonte originale si aggiunge AoN)."""
    path = OGL_DIR / "races.json"
    with open(path, encoding="utf-8") as f:
        catalog = json.load(f)
    source_text = catalog.get("_source", SOURCE)
    if "aonprd" not in source_text:
        source_text = source_text.rstrip(".") + "; Archives of Nethys (aonprd.com)."
    by_name = {e["name"]: e for e in catalog["entries"]}
    for race in RACES_CORE:
        url = BASE + f"RacesDisplay.aspx?ItemName={race.replace(' ', '%20')}"
        parsed = parse_race(fetch(url), race)
        assert parsed["mechanics"]["ability_mods"], f"{race}: ability_mods non parsati"
        if race in by_name:
            by_name[race].update(parsed)
        else:
            catalog["entries"].append(parsed)
    if write:
        write_catalog(path, catalog["entries"],
                      license_text=catalog.get("_license", LICENSE), source_text=source_text)
    else:
        print(f"report: {len(catalog['entries'])} entry (write=False, nessuna scrittura)")


CLASSES_CORE = ["Barbarian", "Bard", "Cleric", "Druid", "Fighter", "Monk",
                "Paladin", "Ranger", "Rogue", "Sorcerer", "Wizard", "Magus"]


def _to_bonus(text):
    """'+3' -> 3, '+0' -> 0, '+6/+1' -> 6 (primo attacco), '-' -> None."""
    m = re.match(r"^\+(\d+)", text)
    return int(m.group(1)) if m else None


def _parse_level(label):
    """'1st' -> 1, '2nd' -> 2, '3rd' -> 3, '4th' -> 4."""
    m = re.match(r"(\d+)", label)
    return int(m.group(1)) if m else None


def _header_index(table):
    """(indice, headers) del <tr> con gli header di colonna della tabella di
    progressione (contiene 'Level' + 'Base Attack Bonus'). Le tabelle caster
    hanno una riga di gruppo ('Spells Per Day' con colspan) sopra gli header;
    i wrapper di layout annidano la tabella: celle dirette, non ricorsive."""
    for idx, tr in enumerate(table.find_all("tr", recursive=False)[:3]):
        headers = [clean(c.get_text()) for c in tr.find_all(["th", "td"], recursive=False)]
        if "Level" in headers and "Base Attack Bonus" in headers:
            return idx, headers
    return None, []


def parse_class(html, class_name):
    """Pagina ClassDisplay: HD, wealth, class skills, skill points, tabella progressione."""
    soup = BeautifulSoup(html, "html.parser")
    mech = {"hd": None, "starting_wealth": None, "class_skills": [],
            "skill_points_per_level": None, "proficiencies": None, "progression": []}
    text = clean(soup.get_text(" ")).replace("×", "x")
    hd = re.search(r"Hit Die\D{0,3}(d\d+)", text)
    if hd:
        mech["hd"] = hd.group(1)
    wealth = re.search(r"Starting Wealth\D{0,3}([\ddx ]+ gp(?:\s*\(average [\d,]+ gp\.?\))?)", text)
    if wealth:
        mech["starting_wealth"] = wealth.group(1).strip()
    sp = re.search(r"Skill (?:Points|Ranks) (?:per|at Each) (?:Level|lvl)\D{0,3}(\d+)", text, re.I)
    if sp:
        mech["skill_points_per_level"] = int(sp.group(1))
    skills_match = re.search(r"class skills (?:are|of [^:]+:)\s*([^.]+)\.", text, re.I)
    if skills_match:
        mech["class_skills"] = [clean(re.sub(r"\s*\([A-Z][a-z]{2}\)$", "", re.sub(r"^and\s+", "", s.strip())))
                                for s in skills_match.group(1).split(",")]
    prof = re.search(r"Weapon and Armor Proficien\w+\s*:?\s*([^.]+)\.", text, re.I)
    if prof:
        mech["proficiencies"] = clean(prof.group(1))
    # La pagina puo' contenere altre tabelle (layout, Spells Known): seleziona
    # per header (celle dirette: i wrapper di layout annidano la tabella
    # progressione e con find_all ricorsivo matcherebbero per primi).
    table, header_idx, headers = None, None, []
    for candidate in soup.find_all("table"):
        idx, found = _header_index(candidate)
        if idx is not None:
            table, header_idx, headers = candidate, idx, found
            break
    if table:
        trs = table.find_all("tr", recursive=False)
        for tr in trs[header_idx + 1:]:
            cells = [clean(c.get_text()) for c in tr.find_all(["th", "td"], recursive=False)]
            if len(cells) != len(headers) or not any(cells):
                continue
            row = dict(zip(headers, cells))
            lvl = _parse_level(row.get("Level", ""))
            if not lvl:
                continue
            entry = {"level": lvl,
                     "bab": _to_bonus(row.get("Base Attack Bonus", "")),
                     "fort": _to_bonus(row.get("Fort Save", "")),
                     "ref": _to_bonus(row.get("Ref Save", "")),
                     "will": _to_bonus(row.get("Will Save", "")),
                     "special": [clean(s) for s in row.get("Special", "").split(",") if clean(s)]}
            spells = {}
            extra = {}
            for k, v in row.items():
                if k in ("Level", "Base Attack Bonus", "Fort Save", "Ref Save",
                         "Will Save", "Special") or not v or v in ("-", "—"):
                    continue
                # spells_per_day solo per colonne-cerchio (0-9); le altre
                # colonne di classe (Monk: Unarmed Damage, AC Bonus...) vanno
                # in extra_progression, non sono slot incantesimi.
                if re.match(r"^(0|[1-9](?:st|nd|rd|th))$", k):
                    spells[k] = v
                else:
                    extra[k] = v
            if spells:
                entry["spells_per_day"] = spells
            if extra:
                entry["extra_progression"] = extra
            mech["progression"].append(entry)
    desc = (f"{class_name}: HD {mech['hd']}, skill points {mech['skill_points_per_level']}+Int. "
            f"Class skills: {', '.join(mech['class_skills'][:8])}. "
            f"Progressione su {len(mech['progression'])} livelli.")
    return {
        "name": class_name,
        "source": "PFRPG Core" if class_name != "Magus" else "Ultimate Magic",
        "source_id": source_id("pfrpg_core", class_name),
        "prerequisites": [],
        "tags": ["class", "core" if class_name != "Magus" else "base"],
        "references": [f"AoN: {class_name} (Classes)"],
        "reference_urls": [BASE + f"ClassDisplay.aspx?ItemName={class_name}"],
        "description": desc,
        "mechanics": mech,
    }


def build_classes(write=False):
    """Merge in place su classes.json preservando i campi curati e l'header."""
    path = OGL_DIR / "classes.json"
    with open(path, encoding="utf-8") as f:
        catalog = json.load(f)
    source_text = catalog.get("_source", SOURCE)
    if "aonprd" not in source_text:
        source_text = source_text.rstrip(".") + "; Archives of Nethys (aonprd.com)."
    by_name = {e["name"]: e for e in catalog["entries"]}
    for cls in CLASSES_CORE:
        url = BASE + f"ClassDisplay.aspx?ItemName={cls}"
        parsed = parse_class(fetch(url), cls)
        assert len(parsed["mechanics"]["progression"]) == 20, (
            f"{cls}: attesi 20 livelli, trovati {len(parsed['mechanics']['progression'])}")
        assert parsed["mechanics"]["hd"], f"{cls}: HD non parsato"
        if cls in by_name:
            by_name[cls].update(parsed)
        else:
            catalog["entries"].append(parsed)
    if write:
        write_catalog(path, catalog["entries"],
                      license_text=catalog.get("_license", LICENSE), source_text=source_text)
    else:
        print(f"report: {len(catalog['entries'])} entry (write=False, nessuna scrittura)")


def build_abilities(write=False):
    url = BASE + "Rules.aspx?Name=Generating%20Ability%20Scores&Category=Getting%20Started"
    entries = parse_abilities(fetch(url))
    assert len(entries) >= 16, f"abilities: attese >=16 entry, trovate {len(entries)}"
    if write:
        write_catalog(OGL_DIR / "abilities.json", entries)
    else:
        print(f"report: {len(entries)} entry (write=False, nessuna scrittura)")


DOMAINS = {"abilities": build_abilities, "races": build_races, "classes": build_classes}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--domain", required=True, choices=sorted(DOMAINS))
    ap.add_argument("--write", action="store_true", help="scrivi il catalogo (default: solo report)")
    args = ap.parse_args(argv)
    print(f"domain: {args.domain} (write={args.write})")
    DOMAINS[args.domain](write=args.write)


if __name__ == "__main__":
    main()
