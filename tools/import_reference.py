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
from urllib.parse import quote, unquote_plus, urljoin

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bs4 import BeautifulSoup

from tools.legal_filter import _find_pi
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


def _cell_text(cell):
    """Testo normalizzato di una cella, senza i <sup> (footnote marker AoN:
    '2 lbs.<sup>1</sup>' -> '2 lbs.')."""
    for sup in cell.find_all("sup"):
        sup.decompose()
    return clean(cell.get_text())


def table_rows(table):
    """<table> -> lista di dict {header: cella} (header dal primo <tr>)."""
    rows = table.find_all("tr")
    if not rows:
        return []
    headers = [_cell_text(c) for c in rows[0].find_all(["th", "td"])]
    out = []
    for row in rows[1:]:
        cells = [_cell_text(c) for c in row.find_all(["th", "td"])]
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


SKILL_NAMES = ["Acrobatics", "Appraise", "Bluff", "Climb", "Craft", "Diplomacy",
               "Disable Device", "Disguise", "Escape Artist", "Fly", "Handle Animal",
               "Heal", "Intimidate", "Knowledge (Arcana)", "Knowledge (Dungeoneering)",
               "Knowledge (Engineering)", "Knowledge (Geography)", "Knowledge (History)",
               "Knowledge (Local)", "Knowledge (Nature)", "Knowledge (Nobility)",
               "Knowledge (Planes)", "Knowledge (Religion)", "Linguistics", "Perception",
               "Perform", "Profession", "Ride", "Sense Motive", "Sleight of Hand",
               "Spellcraft", "Stealth", "Survival", "Swim", "Use Magic Device"]


def SKILL_HEADER_RE(header):
    """'Disable Device (Int; Trained Only)' -> (name, key_ability, trained_only, acp)."""
    m = re.match(r"^(.+?)\s*\(([^)]+)\)", header)
    if not m:
        return header, None, False, False
    name = clean(m.group(1))
    parts = [clean(p) for p in m.group(2).split(";")]
    key = parts[0].lower()[:3] if parts and re.match(r"^(Str|Dex|Con|Int|Wis|Cha)$", parts[0]) else None
    trained = any("Trained Only" in p for p in parts[1:])
    acp = any("Armor Check Penalty" in p for p in parts[1:])
    return name, key, trained, acp


def parse_skill(html, skill_name):
    """Pagina skill singola: header con caratteristica/flags nel titolo.

    La pagina reale AoN ha un h2 di navigazione con l'elenco di tutte le skill
    ('Acrobatics | Appraise | ...'): si accetta solo l'heading con nome esatto
    (case-insensitive) da cui esce una caratteristica valida."""
    soup = BeautifulSoup(html, "html.parser")
    header = ""
    for tag in soup.find_all(["h1", "h2", "h3"]):
        if skill_name.lower() not in tag.get_text().lower():
            continue
        candidate = clean(tag.get_text())
        # Nome esatto (case-insensitive): evita match substring ("craft" in
        # "spellcraft") e l'h2 di navigazione con l'elenco di tutte le skill.
        if SKILL_HEADER_RE(candidate)[1] and SKILL_HEADER_RE(candidate)[0].lower() == skill_name.lower():
            header = candidate
            break
    header = header or skill_name
    name, key, trained, acp = SKILL_HEADER_RE(header)
    assert key, f"{skill_name}: caratteristica non parsata da {header!r}"
    return {
        "name": name,
        "source": "PFRPG Core",
        "source_id": source_id("pfrpg_core", name),
        "prerequisites": [],
        "tags": ["skill", key] + (["trained-only"] if trained else []) + (["acp"] if acp else []),
        "references": [f"AoN: {name} (Skills)"],
        "reference_urls": [BASE + f"Skills.aspx?ItemName={name.replace(' ', '%20')}"],
        "description": (f"{name} ({key.upper()}): skill{' trained only' if trained else ''}"
                        f"{' con armor check penalty' if acp else ''}."),
        "mechanics": {"key_ability": key, "trained_only": trained,
                      "armor_check_penalty": acp, "class_skills_of": []},
    }


def _class_skill_matches(skill_name, class_skill):
    """Match skill del catalogo vs etichetta class_skills di classes.json.
    Case-insensitive; 'Knowledge (all)' matcha ogni Knowledge specifica."""
    s = skill_name.lower()
    c = class_skill.lower()
    if c == "knowledge (all)":
        return s.startswith("knowledge (")
    return s == c


def build_skills(write=False):
    """Crea skills.json; poi popola mechanics.class_skills_of incrociando
    classes.json v2 (mechanics.class_skills di ogni classe).

    AoN 1e non ha pagine per le Knowledge specifiche (404 mascherata: pagina
    senza heading skill): per quelle entry si usano le meccaniche della pagina
    generica 'Knowledge', mantenendo il nome specifico."""
    entries = []
    knowledge_html = None
    for skill in SKILL_NAMES:
        url = BASE + f"Skills.aspx?ItemName={skill.replace(' ', '%20')}"
        try:
            entries.append(parse_skill(fetch(url), skill))
            continue
        except AssertionError:
            if not skill.startswith("Knowledge"):
                raise
        if knowledge_html is None:
            knowledge_html = fetch(BASE + "Skills.aspx?ItemName=Knowledge")
        entry = parse_skill(knowledge_html, "Knowledge")
        mech = entry["mechanics"]
        print(f"nota: {skill}: pagina specifica assente su AoN, meccaniche da 'Knowledge' generica")
        entry["name"] = skill
        entry["source_id"] = source_id("pfrpg_core", skill)
        entry["references"] = ["AoN: Knowledge (Skills)"]
        entry["reference_urls"] = [BASE + "Skills.aspx?ItemName=Knowledge"]
        entry["description"] = (f"{skill} ({mech['key_ability'].upper()}): skill"
                                f"{' trained only' if mech['trained_only'] else ''}"
                                f"{' con armor check penalty' if mech['armor_check_penalty'] else ''}"
                                f" (campo di Knowledge).")
        entries.append(entry)
    classes_path = OGL_DIR / "classes.json"
    with open(classes_path, encoding="utf-8") as f:
        classes = json.load(f)["entries"]
    for entry in entries:
        for cls in classes:
            if any(_class_skill_matches(entry["name"], cs)
                   for cs in cls.get("mechanics", {}).get("class_skills", [])):
                entry["mechanics"]["class_skills_of"].append(cls["name"])
    if write:
        write_catalog(OGL_DIR / "skills.json", entries)
    else:
        print(f"report: {len(entries)} entry (write=False, nessuna scrittura)")


EQUIPMENT_PAGES = [
    ("EquipmentWeapons.aspx?Proficiency=Simple", "weapon", "simple"),
    ("EquipmentWeapons.aspx?Proficiency=Martial", "weapon", "martial"),
    ("EquipmentWeapons.aspx?Proficiency=Exotic", "weapon", "exotic"),
    ("EquipmentArmor.aspx?Category=Light", "armor", "light"),
    ("EquipmentArmor.aspx?Category=Medium", "armor", "medium"),
    ("EquipmentArmor.aspx?Category=Heavy", "armor", "heavy"),
    ("EquipmentArmor.aspx?Category=Shield", "armor", "shield"),
    ("EquipmentMisc.aspx?Category=AdventuringGear", "gear", "adventuring"),
]

# Nomi equipment con Product Identity Golarion-specifica: filtrati dal builder
# (non coperti da legal_filter.PI_WORDS: 'Aldori', 'Kasatha', 'Shoanti',
# 'Varisian' non matchano le word boundary di 'Varisia' ecc.).
PI_EQUIPMENT = {
    "Aldori dueling sword",
    "Kasatha spinal sword",
    "Shoanti bolas",
    "Varisian dancing scarves",
    "Varisian idol",
}


def _mech_key(header):
    """Header tabella -> chiave mechanics snake_case ('Dmg (M)' -> 'dmg_m')."""
    return slug(re.sub(r"[()]", "", header).replace(" ", "_"))


def parse_equipment_table(html, kind, group):
    """Tabelle equipment AoN -> entry con mechanics dai header della tabella.

    Le pagine weapon hanno piu' tabelle (es. Simple Unarmed, Light Melee...):
    si accumulano le righe di tutte quelle con header 'Name' (il gear usa
    'Item'). Le celle '-'/vuote diventano None. Se la cella nome ha un link,
    il suo URL di dettaglio (assoluto) e' il primo di reference_urls."""
    soup = BeautifulSoup(html, "html.parser")
    entries = []
    for table in soup.find_all("table"):
        trs = table.find_all("tr")
        if not trs:
            continue
        headers = [_cell_text(c) for c in trs[0].find_all(["th", "td"])]
        name_idx = next((headers.index(k) for k in ("Name", "Item") if k in headers), None)
        if name_idx is None:
            continue
        for tr in trs[1:]:
            cells = tr.find_all(["th", "td"])
            texts = [_cell_text(c) for c in cells]
            if len(texts) != len(headers) or not any(texts):
                continue
            row = dict(zip(headers, texts))
            name = row.pop("Name", "") or row.pop("Item", "")
            if not name:
                continue
            mech = {_mech_key(k): (None if v in ("-", "", "—") else v) for k, v in row.items()}
            desc_parts = [f"{name} ({kind}, {group})"]
            if mech.get("cost"):
                desc_parts.append(f"costo {mech['cost']}")
            if mech.get("dmg_m"):
                desc_parts.append(f"danno {mech['dmg_m']}")
            if mech.get("weight"):
                desc_parts.append(f"peso {mech['weight']}")
            urls = [BASE + "Equipment.aspx"]
            link = cells[name_idx].find("a", href=True)
            if link:
                # href AoN con spazi letterali ('ItemName=Battle aspergillum'):
                # quote li rende URL validi senza ri-encodare quelli gia' ok.
                urls.insert(0, quote(urljoin(BASE, link["href"]), safe=":/?=&()%';,+%"))
            entries.append({
                "name": name,
                "source": "PFRPG Core",
                "source_id": source_id("pfrpg_core", name),
                "prerequisites": [],
                "tags": ["equipment", kind, group],
                "references": [f"AoN: Equipment ({kind} {group})"],
                "reference_urls": urls,
                "description": ", ".join(desc_parts).rstrip(".") + ".",
                "mechanics": mech,
            })
    return entries


# Alias libro AoN -> etichetta fonte dei cataloghi (es. il dettaglio Core
# riporta 'PRPG Core Rulebook', il catalogo usa 'PFRPG Core').
SOURCE_ALIASES = {"PRPG Core Rulebook": "PFRPG Core"}


def parse_item_source(html):
    """Pagina di dettaglio item AoN -> libro fonte.

    La riga 'Source' puo' elencare piu' manuali ('Source Ultimate Equipment
    pg. 18, PRPG Core Rulebook pg. 142'): si preferisce 'PRPG Core Rulebook'
    (se l'item e' nel Core le altre sono ristampe), altrimenti la prima
    fonte elencata. Ritorna None se il pattern non e' presente."""
    text = clean(BeautifulSoup(html, "html.parser").get_text(" "))
    m = re.search(r"Source\s+(.+?)\s+pg\.?", text)
    if not m:
        return None
    books = [clean(b) for b in re.findall(r"([^,]+?)\s+pg\.?\s*\d+", text[m.start(1):])]
    if not books:
        return None
    for book in books:
        if book in SOURCE_ALIASES:
            return SOURCE_ALIASES[book]
    return books[0]


def build_equipment(write=False):
    """Crea equipment_mundane.json dalle tabelle equipment AoN (armi per
    proficiency, armature per categoria, gear da avventura).

    La fonte di ogni voce e' attribuita dalla sua pagina di dettaglio (le
    tabelle aggregate non la espongono): ~800 fetch da 2s ~= 30 min al primo
    run; la cache su disco rende i rilanci incrementali (idempotente)."""
    entries = []
    for page, kind, group in EQUIPMENT_PAGES:
        entries.extend(parse_equipment_table(fetch(BASE + page), kind, group))
    total = len(entries)
    found, missing = 0, []
    for i, e in enumerate(entries, 1):
        if i % 100 == 0:
            print(f"fetch detail {i}/{total}")
        detail = e["reference_urls"][0]
        if detail == BASE + "Equipment.aspx":
            missing.append(e["name"])
            print(f"warning: nessun link di dettaglio per {e['name']}")
            continue
        book = parse_item_source(fetch(detail))
        if book:
            e["source"] = book
            e["source_id"] = source_id(slug(book), e["name"])
            found += 1
        else:
            missing.append(e["name"])
            print(f"warning: fonte non trovata per {e['name']}")
    print(f"attribuzione: {found}/{total} fonti da pagine dettaglio, "
          f"{len(missing)} fallback 'PFRPG Core'")
    # Stesso oggetto in piu' tabelle (es. Klar weapon+shield): source_id
    # univoco nel catalogo, vince la prima occorrenza.
    seen, unique = set(), []
    for e in entries:
        if e["source_id"] in seen:
            print(f"nota: duplicato scartato {e['source_id']} ({'/'.join(e['tags'][1:])})")
            continue
        seen.add(e["source_id"])
        unique.append(e)
    entries = unique
    pi = [e["name"] for e in entries if e["name"] in PI_EQUIPMENT]
    if pi:
        entries = [e for e in entries if e["name"] not in PI_EQUIPMENT]
        print(f"nota: filtrate {len(pi)} entry PI: {', '.join(pi)}")
    assert len(entries) >= 150, f"equipment: attese >=150 entry, trovate {len(entries)}"
    if write:
        write_catalog(OGL_DIR / "equipment_mundane.json", entries)
    else:
        print(f"report: {len(entries)} entry (write=False, nessuna scrittura)")


TRAIT_CATEGORIES = ["Basic (Combat)", "Basic (Faith)", "Basic (Magic)", "Basic (Social)", "Equipment"]


def _trait_body_lines(header):
    """Righe di testo fra l'header del tratto e il tratto successivo.

    Markup reale AoN: <span ...><h2 class="title"><img/> Nome [<a>Link</a>]</h2>
    <b>Source</b> <a><i>Libro pg. N</i></a><br/> [<b>Requirement(s)</b> ...<br/>]
    descrizione<br/><br/></span> — i sibling dell'h2 dentro lo span, spezzati
    sui <br/>. Markup fixture: <h3><a>Nome</a></h3><p>Source ...</p><p>desc</p>
    — i <p> sibling fino al prossimo header. Stop al prossimo h1-h4 o alla
    fine del contenitore."""
    lines, current = [], []

    def flush():
        line = clean(" ".join(current))
        if line:
            lines.append(line)
        current.clear()

    for sib in header.next_siblings:
        tag = getattr(sib, "name", None)
        if tag in ("h1", "h2", "h3", "h4"):
            break
        if tag == "br":
            flush()
            continue
        if tag == "p":
            flush()
            current.append(sib.get_text())
            flush()
            continue
        current.append(sib.get_text() if hasattr(sib, "get_text") else str(sib))
    flush()
    return lines


def _strip_suggested(text):
    """Taglia la coda 'Suggested Characters : ...' (flavor per il gioco online
    pieno di demonimi Golarion — 'Iomedaeans', 'Chelaxians' — non coperti da
    PI_WORDS per via della word boundary)."""
    return clean(re.split(r"Suggested Characters\s*:", text)[0])


def parse_traits(html, category):
    """Pagina Traits.aspx?Type=<category>: voci nome + source + requirement + beneficio.

    I tratti sono individuati dai link 'TraitDisplay.aspx?ItemName=': il nome
    canonico e' ItemName nell'href (il testo del link e' 'Link' nel markup
    reale, il nome nel markup fixture)."""
    soup = BeautifulSoup(html, "html.parser")
    entries = []
    seen_headers = set()
    for link in soup.find_all("a", href=re.compile(r"TraitDisplay\.aspx\?ItemName=", re.I)):
        header = link.find_parent(["h1", "h2", "h3", "h4"])
        if header is None or id(header) in seen_headers:
            continue
        seen_headers.add(id(header))
        m = re.search(r"ItemName=([^&]+)", link["href"])
        if not m:
            continue
        name = clean(unquote_plus(m.group(1)))
        if not name:
            continue
        source, req, desc_lines = None, None, []
        for line in _trait_body_lines(header):
            src = re.match(r"^Source\s+(.+)$", line)
            if src and source is None:
                # Primo libro = prefisso fino al primo 'pg. N': la virgola puo'
                # far parte del titolo ('Sargava, the Lost Colony pg. 12');
                # in multi-fonte ('A pg. 5, B pg. 62') si prende il primo.
                book = re.match(r"^(.+?)\s+pg\.?\s*\d+", src.group(1))
                source = clean(book.group(1)) if book else clean(src.group(1))
                continue
            r = re.match(r"^Requirement\(s\)\s*(.+)$", line)
            if r and req is None:
                req = _strip_suggested(r.group(1))
                continue
            desc_lines.append(line)
        description = _strip_suggested(" ".join(desc_lines))
        if not description:
            continue
        entries.append({
            "name": name,
            "source": source or "Ultimate Campaign",
            "source_id": source_id(slug(source) if source else "ultimate_campaign", name),
            "prerequisites": [req] if req and req.lower() != "none" else [],
            "tags": ["trait", slug(category)],
            "references": [f"AoN: Traits ({category})"],
            "reference_urls": [quote(urljoin(BASE, link["href"]), safe=":/?=&()%';,+%")],
            "description": description,
            "mechanics": {"category": category},
        })
    return entries


# Supplemento PI Golarion specifico per i tratti (toponimi/etnie/fazioni/
# forme aggettivali non coperte da legal_filter.PI_WORDS). NON aggiungerle a
# PI_WORDS: impatterebbe i cataloghi gia' committati (triage separato futuro).
TRAITS_PI_SUPPLEMENT = frozenset({
    "Korvosa", "Magnimar", "Riddleport", "Lastwall", "Mendev", "Nidal",
    "Westcrown", "Cassomir", "Sargava", "Thrune", "Mwangi", "Shackles",
    "Linnorm", "Kelesh", "Ulfen", "Shoanti", "Varisian", "Chelish", "Taldan",
    "Qadiran", "Inner Sea", "Hellknight", "Red Mantis", "Whispering Way",
    "Technic League", "Eagle Knight", "Tar-Baphon", "Acadamae", "Mediogalti",
    "Sargavan", "Garundi", "Vudrani",
})

_TRAITS_PI_SUPPLEMENT_RES = {
    term: re.compile(rf"\b{re.escape(term)}\b", re.IGNORECASE)
    for term in TRAITS_PI_SUPPLEMENT
}


def _trait_pi_hits(entry):
    """Occorrenze PI in name/description/prerequisites del tratto.

    Tre fonti di match: legal_filter._find_pi (PI_WORDS + PI_PHRASES), i
    termini TRAITS_PI_SUPPLEMENT (word boundary, case-insensitive) e il campo
    source che contiene 'Pathfinder Society' (es. 'Pathfinder Society
    Primer'). Filtrati dal builder, come PI_EQUIPMENT per equipment."""
    texts = [entry["name"], entry["description"], *entry["prerequisites"]]
    hits = [hit for text in texts for hit in _find_pi(text)]
    for text in texts:
        for term, pattern in _TRAITS_PI_SUPPLEMENT_RES.items():
            m = pattern.search(text)
            if m:
                hits.append({"type": "word", "term": term,
                             "context": text[max(0, m.start() - 30):m.end() + 30]})
    if "pathfinder society" in entry.get("source", "").lower():
        hits.append({"type": "phrase", "term": "Pathfinder Society",
                     "context": entry["source"]})
    return hits


def build_traits(write=False):
    """SOLO categorie Basic UCa + Equipment (OGC). Campaign/Region/Religion/
    Faction/Family/Race/Cosmic/Exemplar/Mount/Drawbacks: ESCLUSE (PI Golarion).
    Le entry con PI residua in name/description/prerequisites (scansione
    legal_filter._find_pi) sono rimosse e conteggiate; in write mode l'elenco
    delle rimozioni (nome, categoria, termini PI) e' persistito in
    reports/pi_removed_traits.txt."""
    entries = []
    for category in TRAIT_CATEGORIES:
        url = BASE + f"Traits.aspx?Type={category.replace(' ', '%20')}"
        entries.extend(parse_traits(fetch(url), category))
    # Ristampe dello stesso tratto da fonti diverse: source_id univoco, vince
    # la prima occorrenza.
    seen, unique = set(), []
    for e in entries:
        if e["source_id"] in seen:
            print(f"nota: duplicato scartato {e['source_id']}")
            continue
        seen.add(e["source_id"])
        unique.append(e)
    entries = unique
    removed = [(e, _trait_pi_hits(e)) for e in entries]
    removed = [(e, hits) for e, hits in removed if hits]
    if removed:
        pi_names = {e["name"] for e, _ in removed}
        entries = [e for e in entries if e["name"] not in pi_names]
        print(f"nota: filtrate {len(removed)} entry PI: {', '.join(sorted(pi_names))}")
    assert len(entries) >= 60, f"traits: attese >=60 entry, trovate {len(entries)}"
    if write:
        write_catalog(OGL_DIR / "traits.json", entries)
        if removed:
            lines = []
            for e, hits in sorted(removed, key=lambda x: x[0]["name"]):
                terms = sorted({h["term"] for h in hits})
                lines.append(f"{e['name']} [{e['mechanics']['category']}]: {', '.join(terms)}")
            path = OGL_DIR.parents[2] / "reports" / "pi_removed_traits.txt"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            print(f"scritto {path} ({len(lines)} entry rimosse)")
    else:
        print(f"report: {len(entries)} entry (write=False, nessuna scrittura)")


def extract_prerequisites(description):
    """Estrae i prerequisiti da una description testuale (riga 'Prerequisite(s): ...').
    Ritorna lista di stringhe (split su virgola), [] se assenti."""
    m = re.search(r"Prerequisites?:\s*(.+?)(?:\.\s*(?:\n|$)|\.$)", description, re.S)
    if not m:
        return []
    raw = clean(m.group(1))
    if not raw or raw.lower() == "none":
        return []
    return [clean(p) for p in raw.split(",") if clean(p)]


def split_prereq_string(text):
    """'Str 13, base attack bonus +1' -> ['Str 13', 'base attack bonus +1'].

    Split su virgola + clean; scarta '—'/'-'/segmenti vuoti. Una virgola
    dentro parentesi NON spezza: un segmento con '(' non bilanciata e'
    concatenato al successivo finche' il buffer non torna bilanciato."""
    parts, buf = [], ""
    for seg in text.split(","):
        buf = f"{buf},{seg}" if buf else seg
        if buf.count("(") <= buf.count(")"):
            parts.append(buf)
            buf = ""
    if buf:
        parts.append(buf)
    out = []
    for p in parts:
        p = clean(p)
        # La fonte puo' chiudere la frase col punto: rimosso, stessa regola
        # di clean_existing_prerequisites.
        if p.endswith("."):
            p = p[:-1]
        if p and p not in ("—", "-"):
            out.append(p)
    return out


def clean_existing_prerequisites(entry):
    """Ripulisce i prerequisites gia' presenti in una entry feats:
    (a) scarta i segmenti autoreferenziali (uguali al nome entry,
        case-insensitive, con o senza punto finale): artefatti dell'import
        d20pfsrd per talenti che in realta' non hanno prerequisiti
        ('Improved Initiative.' su Improved Initiative, indice AoN: '—');
    (b) rimuove il punto finale dai segmenti ('base attack bonus +1.' ->
        'base attack bonus +1'), solo se ultimo carattere.
    Ritorna la lista ripulita; NON modifica la entry (ci pensa il builder)."""
    name = entry.get("name", "").lower()
    cleaned = []
    for p in entry.get("prerequisites", []):
        base = p[:-1] if p.endswith(".") else p
        if base.lower() == name:
            continue
        cleaned.append(base)
    return cleaned


def parse_feats_index(html):
    """Indice gigante Feats.aspx: tabella(e) Name | Prerequisite | Description
    con TUTTI i talenti. Ritorna {normalize_name(nome): prereq_string} (solo
    righe con prerequisito non vuoto/'—'; in caso di duplicati vince la prima
    occorrenza). I marcatori finali del nome ('*' combat, '⊤' mastery...) sono
    rimossi prima di normalizzare."""
    from tools.enrich_reference import normalize_name

    soup = BeautifulSoup(html, "html.parser")
    lookup = {}
    for table in soup.find_all("table"):
        rows = table_rows(table)
        if not rows or "Name" not in rows[0]:
            continue
        prereq_header = next((h for h in rows[0] if h.startswith("Prerequisite")), None)
        if prereq_header is None:
            continue
        for row in rows:
            name = re.sub(r"[^A-Za-z0-9]+$", "", row.get("Name", ""))
            prereq = clean(row.get(prereq_header, ""))
            if not name or prereq in ("", "—", "-"):
                continue
            key = normalize_name(name)
            if key and key not in lookup:
                lookup[key] = prereq
    return lookup


def _feat_card_prereq_lookup():
    """Lookup offline nome -> prerequisiti dal dataset PFRPG_Feat_card in cache
    locale (.cache/enrichment, la stessa fonte OGL da cui le descriptions di
    feats.json sono state arricchite: nessun dato esterno aggiunto, nessuna
    fetch di rete).

    Le descriptions attuali di feats.json NON contengono la riga
    'Prerequisite(s):' (il dataset separa i prerequisiti in una property
    dedicata): questa cache e' l'unica fonte offline che li conserva.
    Cache assente o incompleta -> lookup parziale/vuoto, mai errore."""
    from tools.enrich_reference import normalize_name, parse_feat_card

    cache_dir = Path(__file__).resolve().parents[1] / ".cache" / "enrichment"
    lookup = {}
    for path in sorted(cache_dir.glob("*PFRPG_Feat_card*.cache")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(data, list):
            continue
        for entry in data:
            name = entry.get("title", "")
            if not name:
                continue
            contents = entry.get("contents", [])
            # Le carte Mythic riusano il titolo del talento base (subtitle
            # 'Mythic', prerequisito il talento stesso): il catalogo non ha
            # entry '(Mythic)' omonime, quindi matcherebbero il talento base
            # con prerequisiti sbagliati. Saltate.
            if any(line.strip().lower() == "subtitle | mythic" for line in contents):
                continue
            text = parse_feat_card(contents).get("prerequisites_text", "")
            key = normalize_name(name)
            if text and key not in lookup:
                # Il dataset chiude la frase col punto finale: rimosso dai
                # segmenti, stessa regola di clean_existing_prerequisites.
                parts = [clean(p) for p in text.split(",") if clean(p)]
                lookup[key] = [p[:-1] if p.endswith(".") else p for p in parts]
    return lookup


def enrich_feats(write=False):
    """Riempie prerequisites vuoti in feats.json da tre fonti, in ordine:
    1. parsing delle descriptions locali (extract_prerequisites);
    2. cache locale PFRPG_Feat_card (_feat_card_prereq_lookup);
    3. indice AoN Feats.aspx (parse_feats_index: UNA pagina, ~2s, poi cache
       su disco) — la fonte di copertura principale.
    Prima dei fill, bonifica i prerequisiti esistenti con
    clean_existing_prerequisites (drop delle self-reference d20pfsrd + strip
    del punto finale; conteggi selfref_dropped/dots_stripped nel report).
    A parte questa pulizia NON altera ne' integra prerequisiti gia' presenti
    (no-overwrite: i dati noti incompleti, es. Power Attack ['Strength 13'],
    restano come sono — limite noto, fuori scope) e non tocca l'header
    (fonte d20PFSRD invariata: nessun dato esterno aggiunto). Report di
    copertura a video (filled = descriptions+feat-card, filled_index =
    indice AoN).

    NOTA copertura: le descriptions locali non includono la riga
    'Prerequisite(s):' e la cache feat-card copre quasi solo talenti i cui
    prerequisiti sono gia' compilati: i passaggi 1-2 riempiono dell'ordine
    delle unita'. Il grosso della copertura viene dall'indice AoN; i vuoti
    residui sono talenti genuinamente senza prerequisiti o non matchati.
    I prerequisiti dell'indice con Product Identity (divinita'/luoghi
    Golarion, Pathfinder Society) sono scartati fail-closed (entry lasciata
    vuota, conteggiata in skipped_pi): stesso criterio dei filtri PI di
    traits/equipment."""
    path = OGL_DIR / "feats.json"
    with open(path, encoding="utf-8") as f:
        catalog = json.load(f)
    card_lookup = card_key = index_lookup = None
    filled = filled_index = already = no_info = skipped_pi = 0
    selfref_dropped = dots_stripped = 0
    for entry in catalog["entries"]:
        # Bonifica prerequisiti esistenti PRIMA dei fill: le self-reference
        # d20pfsrd sono scartate (l'entry svuotata rientra nel flusso di fill;
        # l'indice AoN dice '—' e resta vuota, corretto) e il punto finale e'
        # rimosso dai segmenti mantenuti.
        before = entry.get("prerequisites", [])
        entry["prerequisites"] = clean_existing_prerequisites(entry)
        selfref_dropped += len(before) - len(entry["prerequisites"])
        dots_stripped += sum(1 for p in entry["prerequisites"] if p + "." in before)
        if entry["prerequisites"]:
            already += 1
            continue
        found = extract_prerequisites(entry.get("description", ""))
        source = "desc"
        if not found:
            # Fallback lazy: cache feat-card e indice AoN si caricano solo se
            # una description non basta (e la cache feat-card solo se esiste).
            if card_lookup is None:
                from tools.enrich_reference import normalize_name
                card_lookup, card_key = _feat_card_prereq_lookup(), normalize_name
            found = card_lookup.get(card_key(entry.get("name", "")), [])
            source = "card"
        if not found:
            if index_lookup is None:
                index_lookup = parse_feats_index(fetch(BASE + "Feats.aspx"))
            found = split_prereq_string(index_lookup.get(card_key(entry.get("name", "")), ""))
            source = "index"
        if found and source == "index" and any(_find_pi(p) for p in found):
            skipped_pi += 1
            found = []
        if found:
            entry["prerequisites"] = found
            if source == "index":
                filled_index += 1
            else:
                filled += 1
        else:
            no_info += 1
    print(f"feats: gia' presenti {already}, riempiti {filled}, "
          f"da indice AoN {filled_index}, senza info {no_info} "
          f"(di cui saltati per PI {skipped_pi}); autoreferenziali scartati "
          f"{selfref_dropped}, punti finali rimossi {dots_stripped}")
    assert already + filled + filled_index + no_info == len(catalog["entries"])
    if write:
        write_catalog(path, catalog["entries"],
                      license_text=catalog.get("_license", LICENSE),
                      source_text=catalog.get("_source", SOURCE))


DOMAINS = {"abilities": build_abilities, "races": build_races, "classes": build_classes,
           "skills": build_skills, "equipment": build_equipment, "traits": build_traits,
           "feats": enrich_feats}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--domain", required=True, choices=sorted(DOMAINS))
    ap.add_argument("--write", action="store_true", help="scrivi il catalogo (default: solo report)")
    args = ap.parse_args(argv)
    print(f"domain: {args.domain} (write={args.write})")
    DOMAINS[args.domain](write=args.write)


if __name__ == "__main__":
    main()
