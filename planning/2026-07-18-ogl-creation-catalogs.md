# OGL Character-Creation Catalogs (Lotto 4, Fase 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dare a Master-DD-Taverna i dati strutturati OGC per creare davvero un PG livello 1: ability scores (point-buy), razze, classi con progressione, skill, tratti, equipaggiamento mundano, prerequisiti talenti.

**Architecture:** Pipeline fetch+parse dalle pagine PRD di `aonprd.com` (1e) in cataloghi JSON `data/reference/ogl/` nel formato esistente (`{_license, _source, entries}`), con dati strutturati in un nuovo campo opzionale `mechanics` (oggetto libero per kind) accanto ai campi testuali usati dal RAG (`description`, `tags`, `notes`). Downloader con cache su disco (`data/reference/aon_cache/`, gitignored) e rate limit cortese; parser BeautifulSoup (bs4 gia' in requirements). Merge IN PLACE per races.json/classes.json (preserva i campi curati esistenti: notes IT, status, reviewed_by), file nuovi per abilities/skills/traits/equipment_mundane, enrichment offline per feats.json. Manifest aggiornato su entrambi i nodi (`catalogs[]` per legal_filter+indexer, `files{}` per validate_schemas); legal_filter a 0 violazioni (PI: escluse categorie e sezioni Golarion by design).

**Tech Stack:** Python 3 stdlib + BeautifulSoup4 (gia' presente), pytest (gate verify: >=130 passed, esattamente 1 skipped — NON aggiungere test skipped), nessuna nuova dipendenza.

**Decisioni chiave (lette prima di implementare):**
- **Fonte**: aonprd.com sezione 1e (PRD ufficiale). Stato OGC dedotto dalla citazione fonte su ogni voce (PRPG/APG/UM/UC/UCa/ARG = OGC). Per-pagina NON c'e' marchio OGC: la copertura legale e' l'header `_license`/`_source` del catalogo + legal_filter che scansiona PI (~45 nomi setting/divinita'/iconici + frasi Paizo).
- **PI by design**: razze SOLO sezione "Racial Traits" base (niente subrazze/alternate/favored options); tratti SOLO categorie `Basic (Combat|Faith|Magic|Social)` + `Equipment` (niente Campaign/Region/Religion/Faction/Family/Race); equipment filtrato da legal_filter; niente divinita'.
- **`mechanics`**: campo oggetto opzionale per i dati strutturati per kind (progression, ability_mods, cost, ...). `schemas/reference_catalog.schema.json` va esteso con questa UNICA proprieta' opzionale (oggi ha `additionalProperties: false`; i dataset non sono validati contro lo schema, ma estendiamo per correttezza).
- **Description = prosa riassuntiva** dei mechanics (serve al retrieval RAG, che legge name/prerequisites/description/notes/tags).
- **Niente fetch nei test**: i parser si testano su fixture HTML inline (stringhe nei test).

---

### Task 1: Downloader `tools/reference_fetch.py` con cache + test

**Files:**
- Create: `tooling/Master-DD-Taverna/tools/reference_fetch.py`
- Modify: `tooling/Master-DD-Taverna/.gitignore` (aggiungere `data/reference/aon_cache/`)
- Test: `tooling/Master-DD-Taverna/tests/test_reference_fetch.py`

- [ ] **Step 1: Write the failing test**

Creare `tests/test_reference_fetch.py`:

```python
"""Test per tools/reference_fetch.py (cache logic, nessuna rete)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.reference_fetch import cache_path, fetch


def test_cache_path_deterministic(tmp_path, monkeypatch):
    monkeypatch.setattr("tools.reference_fetch.CACHE_DIR", tmp_path)
    a = cache_path("https://aonprd.com/Rules.aspx?Name=X")
    b = cache_path("https://aonprd.com/Rules.aspx?Name=X")
    c = cache_path("https://aonprd.com/Rules.aspx?Name=Y")
    assert a == b and a != c and a.suffix == ".html"


def test_fetch_uses_cache(tmp_path, monkeypatch):
    monkeypatch.setattr("tools.reference_fetch.CACHE_DIR", tmp_path)
    url = "https://aonprd.com/Rules.aspx?Name=Fixture"
    cache_path(url).write_text("<html>cached</html>", encoding="utf-8")
    assert fetch(url, delay=0) == "<html>cached</html>"  # nessuna rete: legge la cache
    print("OK: reference_fetch cache")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd tooling/Master-DD-Taverna && .venv/Scripts/python -m pytest tests/test_reference_fetch.py -q`
Expected: FAIL `ModuleNotFoundError: No module named 'tools.reference_fetch'`

- [ ] **Step 3: Implement the downloader**

Creare `tools/reference_fetch.py`:

```python
#!/usr/bin/env python3
"""Download pagine aonprd.com con cache su disco e rate limit cortese.

La cache vive in data/reference/aon_cache/ (gitignored): i dump HTML grezzi
non si committano. Uso: `python tools/reference_fetch.py <url> [<url>...]`.
Le funzioni sono importabili dai tool di import (fetch/cache_path).
"""
import argparse
import hashlib
import time
import urllib.request
from pathlib import Path

CACHE_DIR = Path(__file__).resolve().parents[1] / "data/reference/aon_cache"
UA = {"User-Agent": "MasterDD-Taverna/1.0 (cataloghi OGL locali; uso personale)"}
TIMEOUT = 30


def cache_path(url):
    """Path di cache deterministico per un URL (dentro CACHE_DIR)."""
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
    return CACHE_DIR / f"{digest}.html"


def fetch(url, delay=2.0, cache=True):
    """Ritorna l'HTML dell'URL (stringa). Se cache=True e il file esiste,
    legge da disco senza rete; altrimenti scarica (dopo `delay` secondi),
    salva in cache e ritorna."""
    path = cache_path(url)
    if cache and path.exists():
        return path.read_text(encoding="utf-8", errors="replace")
    if delay > 0:
        time.sleep(delay)
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        text = resp.read().decode("utf-8", errors="replace")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return text


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("urls", nargs="+", help="URL aonprd da scaricare in cache")
    ap.add_argument("--delay", type=float, default=2.0, help="pausa tra richieste (s)")
    args = ap.parse_args(argv)
    for url in args.urls:
        path = cache_path(url)
        fetch(url, delay=args.delay)
        print(f"OK: {url} -> {path}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: .gitignore**

Aggiungere a `.gitignore` (sezione reference):

```gitignore
data/reference/aon_cache/
```

- [ ] **Step 5: Run test to verify it passes + commit**

Run: `cd tooling/Master-DD-Taverna && .venv/Scripts/python -m pytest tests/test_reference_fetch.py -q`
Expected: 2 passed.

```bash
cd tooling/Master-DD-Taverna
git add tools/reference_fetch.py tests/test_reference_fetch.py .gitignore
git commit -m "feat(reference): add aonprd downloader with disk cache"
```

---

### Task 2: Scaffold `tools/import_reference.py` + catalogo `abilities.json`

**Files:**
- Create: `tooling/Master-DD-Taverna/tools/import_reference.py`
- Create (generato): `tooling/Master-DD-Taverna/data/reference/ogl/abilities.json`
- Test: `tooling/Master-DD-Taverna/tests/test_import_reference.py`

- [ ] **Step 1: Write the failing test (parser abilities su fixture inline)**

Creare `tests/test_import_reference.py`:

```python
"""Test per tools/import_reference.py — parser su fixture HTML inline (no rete)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.import_reference import parse_abilities, source_id, slug

ABILITIES_HTML = """
<html><body>
<table><tr><th>Score</th><th>Points</th></tr>
<tr><td>7</td><td>-4</td></tr><tr><td>10</td><td>0</td></tr>
<tr><td>14</td><td>5</td></tr><tr><td>18</td><td>17</td></tr></table>
<table><tr><th>Campaign Type</th><th>Points</th></tr>
<tr><td>Low Fantasy</td><td>10</td></tr><tr><td>Standard Fantasy</td><td>15</td></tr>
<tr><td>High Fantasy</td><td>20</td></tr><tr><td>Epic Fantasy</td><td>25</td></tr></table>
</body></html>
"""


def test_slug_and_source_id():
    assert slug("Half-Elf (Standard)") == "half_elf_standard"
    assert source_id("pfrpg_core", "Power Attack") == "pfrpg_core:power_attack"


def test_parse_abilities():
    entries = parse_abilities(ABILITIES_HTML)
    costs = {e["name"]: e["mechanics"]["cost"] for e in entries if e["mechanics"]["kind"] == "ability_cost"}
    budget = {e["name"]: e["mechanics"]["points"] for e in entries if e["mechanics"]["kind"] == "campaign_budget"}
    assert costs == {"Score 7": -4, "Score 10": 0, "Score 14": 5, "Score 18": 17}
    assert budget == {"Low Fantasy": 10, "Standard Fantasy": 15, "High Fantasy": 20, "Epic Fantasy": 25}
    assert all(e["source_id"].startswith("pfrpg_core:") for e in entries)
    print("OK: parse_abilities fixture")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd tooling/Master-DD-Taverna && .venv/Scripts/python -m pytest tests/test_import_reference.py -q`
Expected: FAIL `ModuleNotFoundError: No module named 'tools.import_reference'`

- [ ] **Step 3: Implement scaffold + abilities parser**

Creare `tools/import_reference.py`:

```python
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
    tables = soup.find_all("table")
    entries = []
    if len(tables) >= 1:
        for row in table_rows(tables[0]):
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
    if len(tables) >= 2:
        for row in table_rows(tables[1]):
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


def build_abilities(write=False):
    url = BASE + "Rules.aspx?Name=Generating%20Ability%20Scores&Category=Getting%20Started"
    entries = parse_abilities(fetch(url))
    assert len(entries) >= 16, f"abilities: attese >=16 entry, trovate {len(entries)}"
    if write:
        write_catalog(OGL_DIR / "abilities.json", entries)
    else:
        print(f"report: {len(entries)} entry (write=False, nessuna scrittura)")


DOMAINS = {"abilities": build_abilities}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--domain", required=True, choices=sorted(DOMAINS))
    ap.add_argument("--write", action="store_true", help="scrivi il catalogo (default: solo report)")
    args = ap.parse_args(argv)
    print(f"domain: {args.domain} (write={args.write})")
    DOMAINS[args.domain](write=args.write)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test + build reale**

Run: `cd tooling/Master-DD-Taverna && .venv/Scripts/python -m pytest tests/test_import_reference.py -q`
Expected: 2 passed.

Run: `cd tooling/Master-DD-Taverna && .venv/Scripts/python tools/import_reference.py --domain abilities --write`
Expected: `scritto data/reference/ogl/abilities.json (16 entry)` (12 costi + 4 budget). Verifica: `.venv/Scripts/python -c "import json; d=json.load(open('data/reference/ogl/abilities.json',encoding='utf-8')); print(len(d['entries']), d['entries'][0]['mechanics'])"`

- [ ] **Step 5: Commit**

```bash
cd tooling/Master-DD-Taverna
git add tools/import_reference.py tests/test_import_reference.py data/reference/ogl/abilities.json
git commit -m "feat(reference): add import_reference scaffold and abilities catalog"
```

---

### Task 3: Parser razze → `races.json` v2 (merge in place)

**Files:**
- Modify: `tooling/Master-DD-Taverna/tools/import_reference.py` (aggiungere parse_races/build_races + DOMAINS)
- Modify (generato): `tooling/Master-DD-Taverna/data/reference/ogl/races.json`
- Modify: `tooling/Master-DD-Taverna/tests/test_import_reference.py`

- [ ] **Step 1: Write the failing test**

Aggiungere a `tests/test_import_reference.py`:

```python
from tools.import_reference import parse_race

RACE_HTML = """
<html><body>
<h2>Dwarf</h2>
<h3>Racial Traits</h3>
<p><b>+2 Constitution, +2 Wisdom, -2 Charisma</b>: Dwarves are both tough and wise.</p>
<p><b>Medium</b>: Dwarves are Medium creatures.</p>
<p><b>Slow and Steady</b>: Dwarves have a base speed of 20 feet.</p>
<p><b>Darkvision</b>: Dwarves can see in the dark up to 60 feet.</p>
<p><b>Defensive Training</b>: Dwarves gain a +4 dodge bonus to AC against giants.</p>
<p><b>Languages</b>: Dwarves begin play speaking Common and Dwarven. Dwarves with high Intelligence can choose from Giant, Gnome, Goblin, Orc, Terran, and Undercommon.</p>
</body></html>
"""


def test_parse_race():
    entry = parse_race(RACE_HTML, "Dwarf")
    mech = entry["mechanics"]
    assert mech["ability_mods"] == {"con": 2, "wis": 2, "cha": -2}
    assert mech["size"] == "Medium"
    assert mech["speed"] == 20
    assert any(t["name"] == "Darkvision" for t in mech["traits"])
    assert mech["languages"]["auto"] == ["Common", "Dwarven"]
    assert "Gnome" in mech["languages"]["bonus"]
    assert entry["source_id"] == "pfrpg_core:dwarf"
    assert "Darkvision" in entry["description"]
    print("OK: parse_race fixture")


def test_parse_race_any_bonus():
    html = ("<html><body><h3>Racial Traits</h3>"
            "<p><b>+2 to One Ability Score</b>: Humans get a bonus feat.</p></body></html>")
    entry = parse_race(html, "Human")
    assert entry["mechanics"]["ability_mods"] == {"any": 2}
    print("OK: parse_race any-bonus")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd tooling/Master-DD-Taverna && .venv/Scripts/python -m pytest tests/test_import_reference.py -q`
Expected: FAIL `ImportError: cannot import name 'parse_race'`

- [ ] **Step 3: Implement race parser + merge builder**

Aggiungere a `tools/import_reference.py` (dopo `parse_abilities`):

```python
RACES_CORE = ["Dwarf", "Elf", "Gnome", "Half-Elf", "Half-Orc", "Halfling", "Human"]
ABILITY_KEYS = {"strength": "str", "dexterity": "dex", "constitution": "con",
                "intelligence": "int", "wisdom": "wis", "charisma": "cha"}


def _parse_ability_mods(text):
    """'+2 Constitution, +2 Wisdom, -2 Charisma' -> {'con': 2, 'wis': 2, 'cha': -2}.
    '+2 to one ability score (your choice)' -> {'any': 2}."""
    mods = {}
    for value, ability in re.findall(r"([+-]\d+)\s+([A-Za-z]+)", text):
        key = ABILITY_KEYS.get(ability.lower())
        if key:
            mods[key] = int(value)
    if not mods and "to one ability" in text.lower():
        mods = {"any": 2}
    return mods


def parse_race(html, race_name):
    """Pagina RacesDisplay: sezione 'Racial Traits' con righe bold-led.

    SOLO tratti base CRB (OGC): subrazze/alternate/favored options NON parse
    (PI Golarion)."""
    soup = BeautifulSoup(html, "html.parser")
    mech = {"ability_mods": {}, "size": None, "speed": None, "traits": [],
            "languages": {"auto": [], "bonus": []}}
    for bold in soup.find_all("b"):
        label = clean(bold.get_text())
        parent_text = clean(bold.parent.get_text()) if bold.parent else label
        detail = clean(parent_text[len(label):].lstrip(" :")) if parent_text.startswith(label) else ""
        if re.match(r"^[+-]\d+\s", label):
            mech["ability_mods"] = _parse_ability_mods(label)
        elif label in ("Medium", "Small"):
            mech["size"] = label
        elif label == "Slow and Steady" or label.startswith("Normal Speed"):
            m = re.search(r"(\d+)\s+feet", parent_text)
            if m:
                mech["speed"] = int(m.group(1))
        elif label == "Languages":
            langs = re.search(r"speaking\s+([^.]+)", parent_text)
            if langs:
                mech["languages"]["auto"] = [clean(x) for x in langs.group(1).split(" and ")]
            bonus = re.search(r"choose from\s+([^.]+)", parent_text)
            if bonus:
                mech["languages"]["bonus"] = [clean(x) for x in re.split(r",| and ", bonus.group(1)) if clean(x)]
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


def build_races():
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
    write_catalog(path, catalog["entries"],
                  license_text=catalog.get("_license", LICENSE), source_text=source_text)
```

E aggiornare `DOMAINS`:

```python
DOMAINS = {"abilities": build_abilities, "races": build_races}
```

- [ ] **Step 4: Run test + build reale**

Run: `cd tooling/Master-DD-Taverna && .venv/Scripts/python -m pytest tests/test_import_reference.py -q`
Expected: 4 passed.

Run: `cd tooling/Master-DD-Taverna && .venv/Scripts/python tools/import_reference.py --domain races --write`
Expected: `scritto data/reference/ogl/races.json (7 entry)`; ogni entry ha `mechanics.ability_mods` non vuoto (Human/Half-Elf/Half-Orc hanno `{"any": 2}` dal fallback gia' nel parser). Verifica a campione: `python -c "import json; d=json.load(open('data/reference/ogl/races.json',encoding='utf-8')); print([ (e['name'], e['mechanics']['ability_mods']) for e in d['entries']])"`

- [ ] **Step 5: legal check + commit**

Run: `cd tooling/Master-DD-Taverna && .venv/Scripts/python tools/legal_filter.py`
Expected: `Violazioni rilevate: 0` (i tratti base sono OGC; se compaiono violazioni PI su races.json, rimuovere il tratto flaggato e rilanciare).

```bash
cd tooling/Master-DD-Taverna
git add tools/import_reference.py tests/test_import_reference.py data/reference/ogl/races.json
git commit -m "feat(reference): structure core races mechanics from aonprd"
```

---

### Task 4: Parser classi → `classes.json` v2 (progressione per livello)

**Files:**
- Modify: `tooling/Master-DD-Taverna/tools/import_reference.py` (parse_class/build_classes + DOMAINS)
- Modify (generato): `tooling/Master-DD-Taverna/data/reference/ogl/classes.json`
- Modify: `tooling/Master-DD-Taverna/tests/test_import_reference.py`

- [ ] **Step 1: Write the failing test**

Aggiungere a `tests/test_import_reference.py`:

```python
from tools.import_reference import parse_class

CLASS_HTML = """
<html><body>
<h2>Barbarian</h2>
<p><b>Hit Die</b>: d12.</p>
<p><b>Starting Wealth</b>: 3d6 x 10 gp (average 105 gp).</p>
<h3>Class Skills</h3>
<p>The barbarian's class skills are Acrobatics (Dex), Climb (Str), Intimidate (Cha), Perception (Wis).</p>
<p><b>Skill Points per Level</b>: 4 + Int modifier.</p>
<table><tr><th>Level</th><th>Base Attack Bonus</th><th>Fort Save</th><th>Ref Save</th><th>Will Save</th><th>Special</th></tr>
<tr><td>1st</td><td>+1</td><td>+2</td><td>+0</td><td>+0</td><td>Fast movement, rage</td></tr>
<tr><td>2nd</td><td>+2</td><td>+3</td><td>+0</td><td>+0</td><td>Rage power, uncanny dodge</td></tr></table>
</body></html>
"""


def test_parse_class():
    entry = parse_class(CLASS_HTML, "Barbarian")
    mech = entry["mechanics"]
    assert mech["hd"] == "d12"
    assert mech["skill_points_per_level"] == 4
    assert "Acrobatics" in mech["class_skills"] and "Perception" in mech["class_skills"]
    lvl1 = mech["progression"][0]
    assert lvl1["level"] == 1 and lvl1["bab"] == 1 and lvl1["fort"] == 2 and lvl1["ref"] == 0
    assert "rage" in lvl1["special"]
    assert mech["progression"][1]["level"] == 2
    assert entry["source_id"] == "pfrpg_core:barbarian"
    print("OK: parse_class fixture")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd tooling/Master-DD-Taverna && .venv/Scripts/python -m pytest tests/test_import_reference.py -q`
Expected: FAIL `ImportError: cannot import name 'parse_class'`

- [ ] **Step 3: Implement class parser + merge builder**

Aggiungere a `tools/import_reference.py`:

```python
CLASSES_CORE = ["Barbarian", "Bard", "Cleric", "Druid", "Fighter", "Monk",
                "Paladin", "Ranger", "Rogue", "Sorcerer", "Wizard", "Magus"]
SAVE_KEYS = {"Fort Save": "fort", "Ref Save": "ref", "Will Save": "will"}


def _to_bonus(text):
    """'+3' -> 3, '+0' -> 0, '-' -> None."""
    m = re.match(r"^\+(\d+)$", text)
    return int(m.group(1)) if m else None


def _parse_level(label):
    """'1st' -> 1, '2nd' -> 2, '3rd' -> 3, '4th' -> 4."""
    m = re.match(r"(\d+)", label)
    return int(m.group(1)) if m else None


def parse_class(html, class_name):
    """Pagina ClassDisplay: HD, wealth, class skills, skill points, tabella progressione."""
    soup = BeautifulSoup(html, "html.parser")
    mech = {"hd": None, "starting_wealth": None, "class_skills": [],
            "skill_points_per_level": None, "proficiencies": None, "progression": []}
    text = clean(soup.get_text(" "))
    hd = re.search(r"Hit Die\D{0,3}(d\d+)", text)
    if hd:
        mech["hd"] = hd.group(1)
    wealth = re.search(r"Starting Wealth\D{0,3}([\ddx ]+ gp(?:\s*\(average [\d,]+ gp\))?)", text)
    if wealth:
        mech["starting_wealth"] = wealth.group(1).strip()
    sp = re.search(r"Skill Points per (?:Level|lvl)\D{0,3}(\d+)", text)
    if sp:
        mech["skill_points_per_level"] = int(sp.group(1))
    skills_match = re.search(r"class skills (?:are|of [^:]+:)\s*([^.]+)\.", text, re.I)
    if skills_match:
        mech["class_skills"] = [clean(re.sub(r"\s*\([A-Z][a-z]{2}\)$", "", s))
                                for s in skills_match.group(1).split(",")]
    prof = re.search(r"Weapon and Armor Proficien\w+\s*:?\s*([^.]+)\.", text, re.I)
    if prof:
        mech["proficiencies"] = clean(prof.group(1))
    table = soup.find("table")
    if table:
        for row in table_rows(table):
            lvl = _parse_level(row.get("Level", ""))
            if not lvl:
                continue
            entry = {"level": lvl,
                     "bab": _to_bonus(row.get("Base Attack Bonus", "")),
                     "fort": _to_bonus(row.get("Fort Save", "")),
                     "ref": _to_bonus(row.get("Ref Save", "")),
                     "will": _to_bonus(row.get("Will Save", "")),
                     "special": [clean(s) for s in row.get("Special", "").split(",") if clean(s)]}
            spells = {k: v for k, v in row.items()
                      if k not in ("Level", "Base Attack Bonus", "Fort Save", "Ref Save",
                                   "Will Save", "Special") and v and v != "-"}
            if spells:
                entry["spells_per_day"] = spells
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


def build_classes():
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
    write_catalog(path, catalog["entries"],
                  license_text=catalog.get("_license", LICENSE), source_text=source_text)
```

E aggiornare `DOMAINS`:

```python
DOMAINS = {"abilities": build_abilities, "races": build_races, "classes": build_classes}
```

- [ ] **Step 4: Run test + build reale**

Run: `cd tooling/Master-DD-Taverna && .venv/Scripts/python -m pytest tests/test_import_reference.py -q`
Expected: 5 passed.

Run: `cd tooling/Master-DD-Taverna && .venv/Scripts/python tools/import_reference.py --domain classes --write`
Expected: `scritto data/reference/ogl/classes.json (12 entry)`; assert interni su 20 livelli e HD. Se una pagina ha la tabella con header diversi (es. Cleric con colonne spells), il parser le cattura in `spells_per_day`. Verifica a campione: `python -c "import json; d=json.load(open('data/reference/ogl/classes.json',encoding='utf-8')); print([(e['name'], e['mechanics']['hd'], len(e['mechanics']['progression'])) for e in d['entries']])"`

- [ ] **Step 5: legal check + commit**

Run: `cd tooling/Master-DD-Taverna && .venv/Scripts/python tools/legal_filter.py`
Expected: 0 violazioni. Se feature di classe citano PI (es. nomi di archetipi Golarion nelle prosa `special`): ripulire la stringa incriminata o accettare la rimozione della entry Special corrispondente.

```bash
cd tooling/Master-DD-Taverna
git add tools/import_reference.py tests/test_import_reference.py data/reference/ogl/classes.json
git commit -m "feat(reference): structure core classes progression from aonprd"
```

---

### Task 5: Parser skill → `skills.json` (nuovo)

**Files:**
- Modify: `tooling/Master-DD-Taverna/tools/import_reference.py` (parse_skill/build_skills + DOMAINS)
- Create (generato): `tooling/Master-DD-Taverna/data/reference/ogl/skills.json`
- Modify: `tooling/Master-DD-Taverna/tests/test_import_reference.py`

- [ ] **Step 1: Write the failing test**

```python
from tools.import_reference import parse_skill, SKILL_HEADER_RE


def test_skill_header_regex():
    name, key, trained, acp = SKILL_HEADER_RE("Disable Device (Int; Trained Only)")
    assert (name, key, trained, acp) == ("Disable Device", "int", True, False)
    name, key, trained, acp = SKILL_HEADER_RE("Acrobatics (Dex; Armor Check Penalty)")
    assert (name, key, trained, acp) == ("Acrobatics", "dex", False, True)
    name, key, trained, acp = SKILL_HEADER_RE("Perception (Wis)")
    assert (name, key, trained, acp) == ("Perception", "wis", False, False)


def test_parse_skill():
    html = "<html><body><h2>Acrobatics (Dex; Armor Check Penalty)</h2><p>You can keep your balance.</p></body></html>"
    entry = parse_skill(html, "Acrobatics")
    assert entry["mechanics"] == {"key_ability": "dex", "trained_only": False,
                                  "armor_check_penalty": True, "class_skills_of": []}
    print("OK: parse_skill fixture")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd tooling/Master-DD-Taverna && .venv/Scripts/python -m pytest tests/test_import_reference.py -q`
Expected: FAIL `ImportError: cannot import name 'parse_skill'`

- [ ] **Step 3: Implement skill parser + builder (con cross-ref class skills da classes.json)**

Aggiungere a `tools/import_reference.py`:

```python
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
    """Pagina skill singola: header con caratteristica/flags nel titolo."""
    soup = BeautifulSoup(html, "html.parser")
    header = ""
    for tag in soup.find_all(["h1", "h2", "h3"]):
        if skill_name.lower() in tag.get_text().lower():
            header = clean(tag.get_text())
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


def build_skills():
    """Crea skills.json; poi popola mechanics.class_skills_of incrociando
    classes.json v2 (mechanics.class_skills di ogni classe)."""
    entries = []
    for skill in SKILL_NAMES:
        url = BASE + f"Skills.aspx?ItemName={skill.replace(' ', '%20')}"
        entries.append(parse_skill(fetch(url), skill))
    classes_path = OGL_DIR / "classes.json"
    with open(classes_path, encoding="utf-8") as f:
        classes = json.load(f)["entries"]
    for entry in entries:
        for cls in classes:
            if entry["name"] in cls.get("mechanics", {}).get("class_skills", []):
                entry["mechanics"]["class_skills_of"].append(cls["name"])
    write_catalog(OGL_DIR / "skills.json", entries)
```

E aggiornare `DOMAINS` aggiungendo `"skills": build_skills`.

- [ ] **Step 4: Run test + build reale**

Run: `cd tooling/Master-DD-Taverna && .venv/Scripts/python -m pytest tests/test_import_reference.py -q`
Expected: 7 passed.

Run: `cd tooling/Master-DD-Taverna && .venv/Scripts/python tools/import_reference.py --domain skills --write`
Expected: `scritto data/reference/ogl/skills.json (35 entry)`. NOTA: Craft/Perform/Profession sono famiglie — la pagina AoN singola esiste ("Craft (Int)" ecc.), la entry unica va bene; Knowledge sono 10 entry distinte. Verifica: `python -c "import json; d=json.load(open('data/reference/ogl/skills.json',encoding='utf-8')); e=[x for x in d['entries'] if x['name']=='Perception'][0]; print(e['mechanics']['key_ability'], len(e['mechanics']['class_skills_of']))"` → `wis` + >= 4 classi.

- [ ] **Step 5: legal check + commit**

Run: `cd tooling/Master-DD-Taverna && .venv/Scripts/python tools/legal_filter.py` → 0 violazioni.

```bash
cd tooling/Master-DD-Taverna
git add tools/import_reference.py tests/test_import_reference.py data/reference/ogl/skills.json
git commit -m "feat(reference): add skills catalog with class-skills cross-reference"
```

---

### Task 6: Parser equipment mundano → `equipment_mundane.json` (nuovo)

**Files:**
- Modify: `tooling/Master-DD-Taverna/tools/import_reference.py` (parse_equipment_table/build_equipment + DOMAINS)
- Create (generato): `tooling/Master-DD-Taverna/data/reference/ogl/equipment_mundane.json`
- Modify: `tooling/Master-DD-Taverna/tests/test_import_reference.py`

- [ ] **Step 1: Write the failing test**

```python
from tools.import_reference import parse_equipment_table

WEAPONS_HTML = """
<html><body><table>
<tr><th>Name</th><th>Cost</th><th>Dmg (S)</th><th>Dmg (M)</th><th>Critical</th><th>Range</th><th>Weight</th><th>Type</th><th>Special</th></tr>
<tr><td>Longsword</td><td>15 gp</td><td>1d6</td><td>1d8</td><td>19-20/x2</td><td>-</td><td>4 lbs.</td><td>S</td><td>-</td></tr>
<tr><td>Shortbow</td><td>30 gp</td><td>1d4</td><td>1d6</td><td>x3</td><td>60 ft.</td><td>2 lbs.</td><td>P</td><td>-</td></tr>
</table></body></html>
"""


def test_parse_equipment_table():
    entries = parse_equipment_table(WEAPONS_HTML, "weapon", "simple")
    ls = entries[0]
    assert ls["mechanics"]["cost"] == "15 gp"
    assert ls["mechanics"]["dmg_m"] == "1d8"
    assert ls["mechanics"]["critical"] == "19-20/x2"
    assert ls["mechanics"]["weight"] == "4 lbs."
    assert ls["tags"] == ["equipment", "weapon", "simple"]
    assert entries[1]["mechanics"]["range"] == "60 ft."
    print("OK: parse_equipment_table fixture")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd tooling/Master-DD-Taverna && .venv/Scripts/python -m pytest tests/test_import_reference.py -q`
Expected: FAIL `ImportError: cannot import name 'parse_equipment_table'`

- [ ] **Step 3: Implement equipment parser + builder**

Aggiungere a `tools/import_reference.py`:

```python
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


def _mech_key(header):
    """Header tabella -> chiave mechanics snake_case ('Dmg (M)' -> 'dmg_m')."""
    return slug(re.sub(r"[()]", "", header).replace(" ", "_"))


def parse_equipment_table(html, kind, group):
    """Tabella equipment AoN -> entry con mechanics dai header della tabella."""
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table")
    entries = []
    if not table:
        return entries
    for row in table_rows(table):
        name = row.pop("Name", "")
        if not name:
            continue
        mech = {_mech_key(k): (None if v in ("-", "") else v) for k, v in row.items()}
        desc_parts = [f"{name} ({kind}, {group})"]
        if mech.get("cost"):
            desc_parts.append(f"costo {mech['cost']}")
        if mech.get("dmg_m"):
            desc_parts.append(f"danno {mech['dmg_m']}")
        if mech.get("weight"):
            desc_parts.append(f"peso {mech['weight']}")
        entries.append({
            "name": name,
            "source": "PFRPG Core",
            "source_id": source_id("pfrpg_core", name),
            "prerequisites": [],
            "tags": ["equipment", kind, group],
            "references": [f"AoN: Equipment ({kind} {group})"],
            "reference_urls": [BASE + "Equipment.aspx"],
            "description": ", ".join(desc_parts) + ".",
            "mechanics": mech,
        })
    return entries


def build_equipment():
    entries = []
    for page, kind, group in EQUIPMENT_PAGES:
        entries.extend(parse_equipment_table(fetch(BASE + page), kind, group))
    assert len(entries) >= 150, f"equipment: attese >=150 entry, trovate {len(entries)}"
    write_catalog(OGL_DIR / "equipment_mundane.json", entries)
```

E aggiornare `DOMAINS` aggiungendo `"equipment": build_equipment`.

- [ ] **Step 4: Run test + build reale**

Run: `cd tooling/Master-DD-Taverna && .venv/Scripts/python -m pytest tests/test_import_reference.py -q`
Expected: 8 passed.

Run: `cd tooling/Master-DD-Taverna && .venv/Scripts/python tools/import_reference.py --domain equipment --write`
Expected: `scritto data/reference/ogl/equipment_mundane.json (>=150 entry)` (armi ~120, armature ~30, gear ~50). Se una categoria torna 0 entry (header tabella diverso), ispezionare il dump in `data/reference/aon_cache/` e adattare `_mech_key`/`table_rows`.

- [ ] **Step 5: legal check + commit**

Run: `cd tooling/Master-DD-Taverna && .venv/Scripts/python tools/legal_filter.py`
Expected: 0 violazioni. Armi/armature con nomi PI (es. "Aldori dueling sword") vengono flaggate da legal_filter: rimuovere quelle entry dal catalogo (filtro manuale nel builder: `entries = [e for e in entries if not _is_pi(e)]` NON serve — legal_filter segnala e si rimuove a mano) e rilanciare.

```bash
cd tooling/Master-DD-Taverna
git add tools/import_reference.py tests/test_import_reference.py data/reference/ogl/equipment_mundane.json
git commit -m "feat(reference): add mundane equipment catalog from aonprd tables"
```

---

### Task 7: Parser tratti → `traits.json` (nuovo, categorie OGC-only)

**Files:**
- Modify: `tooling/Master-DD-Taverna/tools/import_reference.py` (parse_traits/build_traits + DOMAINS)
- Create (generato): `tooling/Master-DD-Taverna/data/reference/ogl/traits.json`
- Modify: `tooling/Master-DD-Taverna/tests/test_import_reference.py`

- [ ] **Step 1: Write the failing test**

```python
from tools.import_reference import parse_traits

TRAITS_HTML = """
<html><body>
<h3><a href="TraitDisplay.aspx?ItemName=Reactionary">Reactionary</a></h3>
<p><b>Source</b> Ultimate Campaign pg. 63</p>
<p>You were bullied as a child. You gain a +2 trait bonus on initiative checks.</p>
<h3><a href="TraitDisplay.aspx?ItemName=Indomitable+Faith">Indomitable Faith</a></h3>
<p><b>Source</b> Ultimate Campaign pg. 60</p>
<p><b>Requirement(s)</b> None</p>
<p>You gain a +1 trait bonus on Will saves.</p>
</body></html>
"""


def test_parse_traits():
    entries = parse_traits(TRAITS_HTML, "Basic (Combat)")
    assert entries[0]["name"] == "Reactionary"
    assert entries[0]["mechanics"]["category"] == "Basic (Combat)"
    assert "initiative" in entries[0]["description"]
    assert entries[1]["name"] == "Indomitable Faith"
    assert len(entries) == 2
    print("OK: parse_traits fixture")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd tooling/Master-DD-Taverna && .venv/Scripts/python -m pytest tests/test_import_reference.py -q`
Expected: FAIL `ImportError: cannot import name 'parse_traits'`

- [ ] **Step 3: Implement traits parser + builder (categorie conservative)**

Aggiungere a `tools/import_reference.py`:

```python
TRAIT_CATEGORIES = ["Basic (Combat)", "Basic (Faith)", "Basic (Magic)", "Basic (Social)", "Equipment"]


def parse_traits(html, category):
    """Pagina Traits.aspx?Type=<category>: voci nome + source + requirement + beneficio.

    Il markup elenca i tratti come header con link seguiti da paragrafi."""
    soup = BeautifulSoup(html, "html.parser")
    entries = []
    for header in soup.find_all(["h2", "h3", "h4"]):
        link = header.find("a")
        if not link or not clean(link.get_text()):
            continue
        name = clean(link.get_text())
        texts = []
        sib = header.find_next_sibling()
        while sib and sib.name == "p":
            texts.append(clean(sib.get_text()))
            sib = sib.find_next_sibling()
        body = " ".join(texts)
        if not body:
            continue
        req = re.search(r"Requirement\(s\)\s*([^.]+)\.", body)
        source = re.search(r"Source\s+(.+?)(?:\s+pg\.?\s*\d+)?(?:\s|$)", body)
        description = re.sub(r"^(Source|Requirement\(s\))\s*", "", body).strip()
        entries.append({
            "name": name,
            "source": clean(source.group(1)) if source else "Ultimate Campaign",
            "source_id": source_id("ultimate_campaign", name),
            "prerequisites": [clean(req.group(1))] if req and clean(req.group(1)).lower() != "none" else [],
            "tags": ["trait", slug(category)],
            "references": [f"AoN: Traits ({category})"],
            "reference_urls": [BASE + f"TraitDisplay.aspx?ItemName={name.replace(' ', '%20')}"],
            "description": description,
            "mechanics": {"category": category},
        })
    return entries


def build_traits():
    """SOLO categorie Basic UCa + Equipment (OGC). Campaign/Region/Religion/
    Faction/Family/Race/Cosmic/Exemplar/Mount/Drawbacks: ESCLUSE (PI Golarion)."""
    entries = []
    for category in TRAIT_CATEGORIES:
        url = BASE + f"Traits.aspx?Type={category.replace(' ', '%20')}"
        entries.extend(parse_traits(fetch(url), category))
    assert len(entries) >= 60, f"traits: attese >=60 entry, trovate {len(entries)}"
    write_catalog(OGL_DIR / "traits.json", entries)
```

E aggiornare `DOMAINS` aggiungendo `"traits": build_traits`.

- [ ] **Step 4: Run test + build reale**

Run: `cd tooling/Master-DD-Taverna && .venv/Scripts/python -m pytest tests/test_import_reference.py -q`
Expected: 9 passed.

Run: `cd tooling/Master-DD-Taverna && .venv/Scripts/python tools/import_reference.py --domain traits --write`
Expected: `scritto data/reference/ogl/traits.json (>=60 entry)`. Se il markup reale non usa h2/h3/h4 con link, ispezionare il dump in cache e adattare il selettore (i tratti su AoN sono liste con `<b><a ...>` o header: verificare sul dump reale e fissare il parser).

- [ ] **Step 5: legal check + commit (QUESTO CATALOGO E' IL PIU' A RISCHIO PI)**

Run: `cd tooling/Master-DD-Taverna && .venv/Scripts/python tools/legal_filter.py`
Expected: 0 violazioni. Se compaiono violazioni (tratti che citano divinita'/luoghi Golarion anche nei Basic, es. nomi di divinita' nei requisiti Faith): rimuovere le entry flaggate dal catalogo e rilanciare finche' pulito; registrare il conteggio rimosso nel commit message.

```bash
cd tooling/Master-DD-Taverna
git add tools/import_reference.py tests/test_import_reference.py data/reference/ogl/traits.json
git commit -m "feat(reference): add traits catalog (basic and equipment categories)"
```

---

### Task 8: Enrichment prerequisiti feats (offline, da descriptions locali)

**Files:**
- Modify: `tooling/Master-DD-Taverna/tools/import_reference.py` (enrich_feat_prerequisites + DOMAINS)
- Modify (generato): `tooling/Master-DD-Taverna/data/reference/ogl/feats.json`
- Modify: `tooling/Master-DD-Taverna/tests/test_import_reference.py`

- [ ] **Step 1: Write the failing test**

```python
from tools.import_reference import extract_prerequisites


def test_extract_prerequisites():
    d1 = "You increase the damage of your attacks.\n\nPrerequisites: Str 13, base attack bonus +1.\n\nBenefit: You can choose to take a -1 penalty."
    assert extract_prerequisites(d1) == ["Str 13", "base attack bonus +1"]
    d2 = "Benefit: You gain a +2 bonus.\n\nNormal: Without this feat, nothing."
    assert extract_prerequisites(d2) == []
    d3 = "Prerequisite: Dex 15, Nimble Moves, base attack bonus +7.\n\nBenefit: X."
    assert extract_prerequisites(d3) == ["Dex 15", "Nimble Moves", "base attack bonus +7"]
    print("OK: extract_prerequisites fixture")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd tooling/Master-DD-Taverna && .venv/Scripts/python -m pytest tests/test_import_reference.py -q`
Expected: FAIL `ImportError: cannot import name 'extract_prerequisites'`

- [ ] **Step 3: Implement extractor + builder offline**

Aggiungere a `tools/import_reference.py`:

```python
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


def enrich_feats():
    """Riempie prerequisites vuoti in feats.json parsando le descriptions locali.
    NON sovrascrive prerequisiti gia' presenti ne' l'header (fonte d20PFSRD
    invariata: nessun dato esterno aggiunto). Report di copertura a video."""
    path = OGL_DIR / "feats.json"
    with open(path, encoding="utf-8") as f:
        catalog = json.load(f)
    filled = already = no_info = 0
    for entry in catalog["entries"]:
        if entry.get("prerequisites"):
            already += 1
            continue
        found = extract_prerequisites(entry.get("description", ""))
        if found:
            entry["prerequisites"] = found
            filled += 1
        else:
            no_info += 1
    print(f"feats: gia' presenti {already}, riempiti {filled}, senza info {no_info}")
    assert filled >= 500, f"feats: attesi >=500 prerequisiti riempiti, ottenuti {filled}"
    write_catalog(path, catalog["entries"],
                  license_text=catalog.get("_license", LICENSE),
                  source_text=catalog.get("_source", SOURCE))
```

E aggiornare `DOMAINS` aggiungendo `"feats": enrich_feats`.

- [ ] **Step 4: Run test + build reale**

Run: `cd tooling/Master-DD-Taverna && .venv/Scripts/python -m pytest tests/test_import_reference.py -q`
Expected: 10 passed.

Run: `cd tooling/Master-DD-Taverna && .venv/Scripts/python tools/import_reference.py --domain feats --write`
Expected: report con `riempiti` >= 500 (atteso ~1700, i 1743 vuoti meno i feat senza prerequisiti reali). Se `filled` e' basso (< 500), il regex non matcha il formato reale delle descriptions: ispezionare 3-4 descriptions reali (`python -c "import json; d=json.load(open('data/reference/ogl/feats.json',encoding='utf-8')); print([e['description'][:200] for e in d['entries'][:5] if not e['prerequisites']])"`) e adattare `extract_prerequisites` al formato trovato, aggiornando il test di conseguenza.

- [ ] **Step 5: legal check + commit**

Run: `cd tooling/Master-DD-Taverna && .venv/Scripts/python tools/legal_filter.py` → 0 violazioni (i prerequisiti sono campo SCANNED: se un prerequisito contiene PI, es. "worshiper of Iomedae", legal_filter lo segnalava gia' nella description — nessuna novita' attesa).

```bash
cd tooling/Master-DD-Taverna
git add tools/import_reference.py tests/test_import_reference.py data/reference/ogl/feats.json
git commit -m "feat(reference): fill feat prerequisites from local descriptions"
```

---

### Task 9: Manifest + schema `mechanics` + test invarianti cataloghi

**Files:**
- Modify: `tooling/Master-DD-Taverna/data/reference/manifest.json`
- Modify: `tooling/Master-DD-Taverna/schemas/reference_catalog.schema.json`
- Create: `tooling/Master-DD-Taverna/tests/test_reference_catalogs.py`

- [ ] **Step 1: Write the failing test (invarianti sui cataloghi reali)**

Creare `tests/test_reference_catalogs.py`:

```python
"""Invarianti dei cataloghi OGL reali (dati su disco, nessuna rete)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

OGL = Path("data/reference/ogl")
MANIFEST = Path("data/reference/manifest.json")

NEW_KINDS = {
    "abilities.json": ("abilities", 16),
    "skills.json": ("skills", 35),
    "traits.json": ("traits", 60),
    "equipment_mundane.json": ("equipment", 150),
}
REQUIRED_FIELDS = {"name", "source", "source_id", "prerequisites", "tags",
                   "references", "reference_urls", "description"}


def _load(name):
    with open(OGL / name, encoding="utf-8") as f:
        return json.load(f)


def test_new_catalogs_structure():
    for fname, (kind, min_entries) in NEW_KINDS.items():
        catalog = _load(fname)
        assert catalog["_license"] and catalog["_source"], f"{fname}: header mancante"
        entries = catalog["entries"]
        assert len(entries) >= min_entries, f"{fname}: {len(entries)} < {min_entries}"
        for e in entries:
            assert REQUIRED_FIELDS <= set(e), f"{fname}: entry senza campi obbligatori: {e.get('name')}"
            assert e["references"] and e["reference_urls"], f"{fname}: {e['name']} senza riferimenti"
            assert "mechanics" in e, f"{fname}: {e['name']} senza mechanics"
    print("OK: struttura nuovi cataloghi")


def test_source_id_unique_globally():
    seen = {}
    for path in sorted(OGL.glob("*.json")):
        with open(path, encoding="utf-8") as f:
            catalog = json.load(f)
        for e in catalog.get("entries", catalog if isinstance(catalog, list) else []):
            sid = e.get("source_id")
            if not sid:
                continue
            assert sid not in seen, f"source_id duplicato: {sid} ({path.name} e {seen[sid]})"
            seen[sid] = path.name
    print(f"OK: {len(seen)} source_id unici")


def test_manifest_counts():
    with open(MANIFEST, encoding="utf-8") as f:
        manifest = json.load(f)
    files = manifest["files"]
    for fname, (kind, _) in NEW_KINDS.items():
        assert kind in files, f"manifest.files manca {kind}"
        with open(OGL / fname, encoding="utf-8") as f:
            real = len(json.load(f)["entries"])
        assert files[kind]["entries"] == real, f"{kind}: manifest {files[kind]['entries']} != reale {real}"
    catalogs_kinds = {c["kind"] for c in manifest["catalogs"]}
    for _, (kind, _) in NEW_KINDS.items():
        assert kind in catalogs_kinds, f"manifest.catalogs manca {kind}"
    monsters = [c for c in manifest["catalogs"] if c["kind"] == "monsters"][0]
    assert monsters["entries"] == 199, "manifest: monsters entries non aggiornato a 199"
    print("OK: manifest allineato ai cataloghi")


def test_classes_races_mechanics():
    classes = _load("classes.json")["entries"]
    for e in classes:
        mech = e.get("mechanics", {})
        assert mech.get("hd"), f"{e['name']}: hd mancante"
        assert len(mech.get("progression", [])) == 20, f"{e['name']}: progressione != 20 livelli"
        assert mech.get("class_skills"), f"{e['name']}: class_skills mancanti"
    races = _load("races.json")["entries"]
    for e in races:
        assert e.get("mechanics", {}).get("ability_mods"), f"{e['name']}: ability_mods mancanti"
    feats = _load("feats.json")["entries"]
    empty = sum(1 for e in feats if not e.get("prerequisites"))
    assert empty < 800, f"feats: ancora {empty} prerequisiti vuoti"
    print("OK: mechanics classes/races + prerequisiti feats")
```

- [ ] **Step 2: Run test to verify it fails (manifest non ancora aggiornato)**

Run: `cd tooling/Master-DD-Taverna && .venv/Scripts/python -m pytest tests/test_reference_catalogs.py -q`
Expected: FAIL su `test_manifest_counts` (kinds mancanti in files) e/o `test_new_catalogs_structure` (mechanics assente se qualche builder non lo ha scritto).

- [ ] **Step 3: Aggiornare `data/reference/manifest.json`**

Nel nodo `catalogs[]` aggiungere (stesso shape degli esistenti):

```json
    {
      "file": "ogl/abilities.json",
      "kind": "abilities",
      "source": "Archives of Nethys (PRD)",
      "license": "OGL-1.0a",
      "is_ogc": true,
      "is_pi": false,
      "cup_allowed": false,
      "entries": 16,
      "notes": "Point-buy costs e campaign budgets (Generating Ability Scores).",
      "last_verified": "2026-07-18"
    },
    {
      "file": "ogl/skills.json",
      "kind": "skills",
      "source": "Archives of Nethys (PRD)",
      "license": "OGL-1.0a",
      "is_ogc": true,
      "is_pi": false,
      "cup_allowed": false,
      "entries": 35,
      "notes": "Skill con caratteristica, flags e cross-ref class skills.",
      "last_verified": "2026-07-18"
    },
    {
      "file": "ogl/traits.json",
      "kind": "traits",
      "source": "Archives of Nethys (PRD)",
      "license": "OGL-1.0a",
      "is_ogc": true,
      "is_pi": false,
      "cup_allowed": false,
      "entries": 60,
      "notes": "Tratti Basic (Combat/Faith/Magic/Social) + Equipment; categorie PI escluse by design.",
      "last_verified": "2026-07-18"
    },
    {
      "file": "ogl/equipment_mundane.json",
      "kind": "equipment",
      "source": "Archives of Nethys (PRD)",
      "license": "OGL-1.0a",
      "is_ogc": true,
      "is_pi": false,
      "cup_allowed": false,
      "entries": 150,
      "notes": "Armi/armature/gear mundane con costi/pesi/danni strutturati.",
      "last_verified": "2026-07-18"
    }
```

e nel nodo `files{}` aggiungere:

```json
    "abilities": {"path": "ogl/abilities.json", "entries": 16},
    "skills": {"path": "ogl/skills.json", "entries": 35},
    "traits": {"path": "ogl/traits.json", "entries": 60},
    "equipment": {"path": "ogl/equipment_mundane.json", "entries": 150}
```

Inoltre:
- aggiornare `files.races.entries` e `files.classes.entries` ai count reali (7 e 12, salvo aggiunte) e i count in `catalogs[]` corrispondenti; aggiornare `files.feats.entries` (immutato, 2839);
- aggiornare il catalogo monsters in `catalogs[]`: `"entries": 0` → `"entries": 199` (fix staleness nota);
- i count `entries` dei nuovi cataloghi nel JSON qui sopra sono i MINIMI attesi: scrivere i count REALI prodotti dai builder (leggerli dai file generati).

- [ ] **Step 4: Estendere `schemas/reference_catalog.schema.json`**

Nella definition `reference_entry`, dentro `properties`, aggiungere:

```json
    "mechanics": {"type": "object"},
```

(lasciare `additionalProperties: false` com'e': tutti i campi usati dai builder sono nel set esistente + `mechanics`.)

- [ ] **Step 5: Run test + validate_schemas + legal**

Run: `cd tooling/Master-DD-Taverna && .venv/Scripts/python -m pytest tests/test_reference_catalogs.py -q`
Expected: 4 passed.

Run: `cd tooling/Master-DD-Taverna && .venv/Scripts/python tools/validate_schemas.py`
Expected: exit 0 ("Schemi ... validi e contratto versioni reference coerente").

Run: `cd tooling/Master-DD-Taverna && .venv/Scripts/python tools/legal_filter.py` → 0 violazioni.

- [ ] **Step 6: Commit**

```bash
cd tooling/Master-DD-Taverna
git add data/reference/manifest.json schemas/reference_catalog.schema.json tests/test_reference_catalogs.py
git commit -m "feat(reference): register creation catalogs in manifest and schema"
```

---

### Task 10: Wiring moduli + reindice + verifica completa + handoff

**Files:**
- Modify: `tooling/Master-DD-Taverna/src/modules/minmax_builder.txt`
- Modify: `tooling/Master-DD-Taverna/src/modules/Encounter_Designer.txt`
- Modify: `tooling/Master-DD-Taverna/src/modules/ruling_expert.txt`
- Modify: `tooling/Master-DD-Taverna/src/modules/archivist.txt`
- Modify: `tooling/Master-DD-Taverna/src/modules/adventurer_ledger.txt`
- Modify: `sessione-2026-07-16/HANDOFF_ATTIVO.md`

- [ ] **Step 1: minmax_builder — RAW anchoring su reference://ogl/**

In `minmax_builder.txt` (:53) sostituire `citation_policy` e nel blocco SOURCE_GOVERNANCE (:61-86) lo STEP 0, dichiarando il catalogo locale come fonte RAW primaria:

```yaml
  ruling_policy:
    citation_policy: "Riferimenti obbligatori: catalogo locale reference://ogl/ (abilities, races, classes, skills, traits, equipment, feats, spells, items, archetypes); permalink AoN solo come citazione secondaria quando la navigazione e' disponibile."
```

e nello STEP 0 del blocco governance:

```yaml
      STEP 0 — RAW anchoring: catalogo locale reference://ogl/ (abilities, races, classes, skills, traits, equipment, feats, spells, items, archetypes) come fonte primaria; AoN/Paizo solo come permalink secondario. Se una regola non e' nel catalogo locale, dichiarala NON VERIFICABILE prima di usarla.
```

Bump: `version: 5.1` → `5.2`, `last_updated: 2026-07-18T00:00:00.000Z`.

- [ ] **Step 2: Encounter_Designer — dichiarare mostri locali + nuovi kind**

In `Encounter_Designer.txt:38` sostituire `offline_disclaimer`:

```yaml
  offline_disclaimer: "Offline supportato: i riferimenti RAW sono ancorati al catalogo locale reference://ogl/ (abilities, races, classes, skills, traits, equipment, feats, spells, items, classes, archetypes). Per i nemici usa i 199 mostri locali in data/reference/pi_local_only/monsters_local.json (indicizzati nel RAG con --include-local) con statblock testuali; se una fonte non e' disponibile offline, marca il contenuto come NON VERIFICABILE."
```

Bump: `version: 1.1` → `1.2`, `last_updated: 2026-07-18`.

- [ ] **Step 3: ruling_expert / archivist / adventurer_ledger — aggiornare elenchi kind**

Sostituire in TUTTI i punti in cui i moduli elencano i kind del catalogo `(feats, spells, items, classes, races, archetypes)` con `(abilities, races, classes, skills, traits, equipment, feats, spells, items, archetypes)`:
- `ruling_expert.txt`: `offline_mode.local_index` (:~60), output di `/offline_check` (:~449), `/status` example (:~486) — grep `feats, spells, items` per trovarli tutti.
- `archivist.txt`: `web_policy.offline_mode` (:~46) e `aon_policy` (:~113).
- `adventurer_ledger.txt`: principles (:~53).

Bump versioni: ruling_expert `3.2-hybrid` → `3.3-hybrid`; archivist `3.7.0` → `3.7.1`; adventurer_ledger `1.6` → `1.7`. `last_updated: 2026-07-18` in tutti. In adventurer_ledger aggiungere anche la voce di changelog (sezione `changelog:` esiste, in coda):

```yaml
  - version: 1.7
    date: 2026-07-18
    notes: >
      • Catalogo OGL esteso: abilities, skills, traits, equipment mundane strutturati; feats con prerequisiti riempiti; classes/races con mechanics (progressione, ability mods).
```

- [ ] **Step 4: YAML check sui 5 moduli modificati**

Run: `cd tooling/Master-DD-Taverna && .venv/Scripts/python -c "
import yaml
for f in ['src/modules/minmax_builder.txt','src/modules/Encounter_Designer.txt','src/modules/ruling_expert.txt','src/modules/archivist.txt','src/modules/adventurer_ledger.txt']:
    yaml.safe_load(open(f, encoding='utf-8'))
    print('YAML OK', f)
"`

- [ ] **Step 5: Reindice RAG + verifica completa**

Run: `cd tooling/Master-DD-Taverna && .venv/Scripts/python tools/index_rag.py --include-local 2>&1 | tail -2`
Expected: `Totale chunk:` > 5.405 (i nuovi cataloghi aggiungono ~300+ entry indicizzate).

Run: `cd C:/dev/pathfinder && python launch.py test`
Expected: `TUTTE LE VERIFICHE OK` (legal_filter 0, pytest >=130 passed & 1 skipped, validate_schemas OK, RAG >=5000 chunk).

- [ ] **Step 6: Commit moduli + handoff**

```bash
cd tooling/Master-DD-Taverna
git add src/modules/minmax_builder.txt src/modules/Encounter_Designer.txt src/modules/ruling_expert.txt src/modules/archivist.txt src/modules/adventurer_ledger.txt
git commit -m "feat(modules): wire creation catalogs as primary RAW source"
git push origin main
```

Aggiornare `sessione-2026-07-16/HANDOFF_ATTIVO.md` (timestamp + riga stato Master-DD-Taverna con lotto 4 Fase 1 completato + voce in "Cosa e' stato completato").

- [ ] **Step 7: Push dati + verifica finale**

I commit dei Task 1-9 possono essere pushati insieme al Task 10 in un'unica volta: `git push origin main` (verificare `git log origin/main..HEAD --oneline` prima: attesi ~10 commit).

---

## Note operative

- **Emendamenti post-review (vincolanti per tutti i builder)**: (a) `import_reference.py` ha lo shim `sys.path.insert(0, parents[1])` in cima — il run diretto `python tools/import_reference.py --domain X` funziona; (b) OGNI `build_<domain>()` prende il parametro `write=False` e chiama `write_catalog(...)` SOLO `if write:`, altrimenti stampa un report (`main` passa `args.write`) — i Task 3-8 devono seguire questa firma anche se gli snippet li mostrano senza parametro; (c) `table_rows` ha il guard `if not rows: return []`; (d) i parser selezionano le tabelle per HEADER, non per posizione.
- **Emendamenti registrati dopo i Task 3-8** (stato reale dell'implementazione): races/classes = merge in place con header `_source` esteso ad AoN (tags curati sostituiti dai nuovi, notes/status preservati); classes: `spells_per_day` solo colonne cerchio `^(0|[1-9](st|nd|rd|th))$`, altre extra in `extra_progression`; skills: cross-ref class skills case-insensitive + espansione "Knowledge (all)"; equipment: attribuzione source per-voce dalle pagine di dettaglio (preferenza PRPG Core in multi-fonte); traits: `TRAITS_PI_SUPPLEMENT` (32 termini Golarion/demonimi) + strip code "Suggested Characters" + `reports/pi_removed_traits.txt` persistito; **Task 8 (feats): premessa originale FALSA** — le descriptions locali non contengono sezioni "Prerequisites:", quindi il fill avviene dall'INDICE `Feats.aspx` (una pagina, tabella Name|Prerequisite) con `parse_feats_index` + `split_prereq_string` (buffer parentesi) + gate PI fail-closed (61 saltati); copertura finale 90.2%, invariante `already+filled+filled_index+no_info == 2839` al posto di `assert >= 500`.
- **Per il Task 9**: aggiungere al test invarianti anche il check "ogni `mechanics.class_skills` di classes.json matcha una skill di skills.json (con espansione Knowledge (all))" (suggerimento quality review Task 5).

- **Ordine consigliato**: i Task 1-2 creano l'infrastruttura; 3-7 sono parser indipendenti tra loro (stessa forma: test fixture → parser → build → legal); 8 offline; 9 allinea manifest/schema/test; 10 wiring+verifica. NON parallelizzare i builder su disco (scrivono lo stesso import_reference.py): un task alla volta.
- **Rate limit**: il fetcher dorme 2s tra richieste (~70 pagine totali ≈ 2.5 min). Se AoN risponde 403/captcha (mxguarddog), aumentare `--delay` a 5 e rilanciare: la cache conserva quanto gia' scaricato.
- **Se una pagina cambia markup**: i dump HTML sono in `data/reference/aon_cache/` (gitignored) per il debug; i parser si riparano rieseguendo dopo fix (la cache NON si invalida da sola: cancellare il file cache della pagina per forzare il re-download).
- **Fallback d20pfsrd**: se AoN non e' raggiungibile, le stesse tabelle esistono su d20pfsrd (marca OGC per pagina; vedi mappa fonti nel report di ricognizione). Cambiare `BASE` e gli URL builder di conseguenza.
- **Fuori scope (YAGNI)**: niente archetipi/classi base-advanced-hybrid-occult (Fase 1 = 11 core + Magus); niente favored class options/subrazze (PI); niente divinita' (PI); niente builder deterministico del PG (Fase 2); niente re-scraping periodico (i dati CRB sono stabili).
- **Gate verify**: NON aggiungere test skipped; il verify esige >=130 passed ed esattamente 1 skipped.
- **Policy commit**: convenzionali (hook commit-guard), MAI `Co-Authored-By:`.
