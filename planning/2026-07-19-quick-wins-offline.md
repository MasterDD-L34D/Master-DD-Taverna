# Quick Wins Offline (Ricerca process-optimization) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** I 4 quick win della ricerca `docs/research/2026-07-19-process-optimization.md`: mostri v2 strutturati, spells `mechanics`, RAG con mechanics, reindex incrementale per hash contenuto. Tutto offline (fonti già in casa), nessuna nuova dipendenza.

**Architecture:** Task 1 emette `mechanics` nei mostri da fonte già strutturata; Task 2 arricchisce spells.json via join con cache gist + fallback regex; Task 3 serializza `mechanics` nel testo dei chunk RAG; Task 4 rende il reindice incrementale (chunk id = sha256 del testo).

---

### Task 1: Mostri v2 — `mechanics` da fonte strutturata

**Files:**
- Modify: `tooling/Master-DD-Taverna/tools/import_monsters.py` (convert_monsters)
- Modify (generato, NON committato, pi_local_only): `tooling/Master-DD-Taverna/data/reference/pi_local_only/monsters_local.json`
- Test: `tooling/Master-DD-Taverna/tests/test_import_monsters.py` (nuovo)

- [ ] **Step 1: Write the failing test**

Creare `tests/test_import_monsters.py`:

```python
"""Test per tools/import_monsters.py — mechanics da fonte strutturata."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.import_monsters import convert_monsters

SOURCE_SAMPLE = [{
    "name": "Apostasy Wraith",
    "sources": [{"name": "Bestiary 5", "page": 12}],
    "type": "Undead", "size": "Medium", "alignment": "CE",
    "cr": "9", "xp": 6400, "hd": "14d8+70", "hp": 133,
    "ac": 22, "touch": 15, "flat-footed": 17,
    "fort": 9, "ref": 11, "will": 12, "bab": 10,
    "ability_scores": {"str": 18, "dex": 20, "con": None, "int": 14, "wis": 16, "cha": 21},
    "attacks": [{"name": "incorporeal touch", "bonus": "+15", "damage": "6d6 negative energy"}],
    "skills": {"Stealth": 22, "Perception": 19},
    "feats": ["Dodge", "Mobility"],
    "speeds": {"base": 60, "fly": 60},
}]


def test_convert_monsters_emits_mechanics():
    entries = convert_monsters(SOURCE_SAMPLE)
    assert len(entries) == 1
    e = entries[0]
    assert e["source_id"] == "monster:apostasy-wraith"
    mech = e["mechanics"]
    assert mech["cr"] == "9" and mech["xp"] == 6400
    assert mech["ac"] == 22 and mech["hp"] == 133 and mech["hd"] == "14d8+70"
    assert mech["saves"] == {"fort": 9, "ref": 11, "will": 12}
    assert mech["bab"] == 10
    assert mech["ability_scores"]["dex"] == 20
    assert mech["attacks"][0]["name"] == "incorporeal touch"
    assert mech["speeds"]["fly"] == 60
    print("OK: mechanics mostri da fonte")
```

NOTA: la shape reale della fonte (`sessione-2026-07-16/ricerca/PathfinderMonsterDatabase/data/full/data.json`) va verificata PRIMA di scrivere il test definitivo: leggi 1-2 entry reali e adatta il fixture ai nomi campo reali (cr/xp/hd/hp/ac/fort/ref/will/bab potrebbero avere casing o nomi diversi, es. `CR`, `XP`, `AC` come stringhe o numeri). Il test deve riflettere la fonte REALE.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd tooling/Master-DD-Taverna && .venv/Scripts/python -m pytest tests/test_import_monsters.py -q`
Expected: FAIL (mechanics assente o AssertionError).

- [ ] **Step 3: Implement mechanics in convert_monsters**

In `tools/import_monsters.py`, `convert_monsters`: oltre ai campi attuali (name, source, source_id, prerequisites, tags, references, reference_urls, description, notes), aggiungere `mechanics` con il subset strutturato della fonte:

```python
    entry["mechanics"] = {
        "cr": m.get("cr"), "xp": m.get("xp"),
        "hd": m.get("hd"), "hp": m.get("hp"),
        "ac": m.get("ac"), "touch": m.get("touch"), "flat_footed": m.get("flat-footed"),
        "saves": {"fort": m.get("fort"), "ref": m.get("ref"), "will": m.get("will")},
        "bab": m.get("bab"), "cmb": m.get("cmb"), "cmd": m.get("cmd"),
        "ability_scores": m.get("ability_scores"),
        "attacks": m.get("attacks"),
        "skills": m.get("skills"), "feats": m.get("feats"),
        "special_abilities": m.get("special_abilities"),
        "speeds": m.get("speeds"), "senses": m.get("senses"),
        "sr": m.get("sr"), "dr": m.get("dr"),
        "immunities": m.get("immunities"), "resistances": m.get("resistances"),
        "weaknesses": m.get("weaknesses"),
    }
```

(adatta ai nomi campo REALI della fonte; conserva la description inline esistente — retrocompatibilità RAG.)

- [ ] **Step 4: Rigenera monsters_local + verifica**

Run: `cd tooling/Master-DD-Taverna && .venv/Scripts/python tools/import_monsters.py`
Expected: 199 entry in `data/reference/pi_local_only/monsters_local.json` (gitignored, NON committato) con mechanics. Verifica:
`.venv/Scripts/python -c "import json; d=json.load(open('data/reference/pi_local_only/monsters_local.json',encoding='utf-8')); n=sum(1 for e in d['entries'] if 'mechanics' in e); print(f'{n}/{len(d[\"entries\"])} con mechanics'); e=d['entries'][0]; print(e['name'], e['mechanics'].get('cr'), e['mechanics'].get('ac'))"`

- [ ] **Step 5: Commit**

```bash
cd tooling/Master-DD-Taverna
git add tools/import_monsters.py tests/test_import_monsters.py
git commit -F commit_msg.txt  # subject: feat(monsters): add structured mechanics from source data
# trailer ADR-0011: Coding-Agent: kimi-code-cli + Trace-Id: uuidv7
```

---

### Task 2: Spells `mechanics` (join gist cache + fallback regex)

**Files:**
- Create: `tooling/Master-DD-Taverna/tools/enrich_spells.py`
- Modify (generato): `tooling/Master-DD-Taverna/data/reference/ogl/spells.json`
- Modify: `tooling/Master-DD-Taverna/tests/test_import_reference.py` (o nuovo `tests/test_enrich_spells.py`)

- [ ] **Step 1: Ricognizione fonti**

Leggi 2 entry della cache gist `.cache/enrichment/https___gist_...PathfinderSpellsJSON...cache` (struttura: lista? dict? campi esatti: school, spell_level, components, casting_time, duration, range, saving_throw, spell_resistance?) e 2 description reali in `data/reference/ogl/spells.json` (formato righe `Key: value`). Riporta le forme esatte nel report.

- [ ] **Step 2: Write the failing test**

```python
"""Test per tools/enrich_spells.py — mechanics spells via gist join + regex."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.enrich_spells import parse_description_mechanics, merge_mechanics


def test_parse_description_mechanics():
    desc = ("School evocation [fire]; Level sorcerer/wizard 3\n\n"
            "Casting Time 1 standard action\nComponents V, S, M\n\n"
            "Range medium (100 ft. + 10 ft./level)\nDuration instantaneous\n"
            "Saving Throw Reflex half; Spell Resistance yes")
    mech = parse_description_mechanics(desc)
    assert mech["school"] == "evocation"
    assert mech["descriptors"] == ["fire"]
    assert mech["spell_level"] == {"sorcerer/wizard": 3}
    assert mech["casting_time"] == "1 standard action"
    assert mech["saving_throw"] == "Reflex half"
    assert mech["spell_resistance"] == "yes"


def test_merge_mechanics_gist_priority():
    entry = {"name": "Fireball", "description": "School evocation; Level sorcerer/wizard 3"}
    gist = {"fireball": {"school": "evocation", "spell_level": {"sorcerer/wizard": 3},
                          "components": ["V", "S", "M"], "range": "medium",
                          "saving_throw": "Reflex half", "spell_resistance": True}}
    mech = merge_mechanics(entry, gist)
    assert mech["school"] == "evocation"
    assert mech["components"] == ["V", "S", "M"]
    assert mech["spell_resistance"] in (True, "yes")
    print("OK: spells mechanics merge")
```

- [ ] **Step 3: Implement enrich_spells.py**

Tool con `--write`: carica gist cache (se esiste: altrimenti solo regex), per ogni spell in `spells.json`: `mechanics = merge(gist_data, parse_description_mechanics(description))`; report matched/unmatched; scrive in place preservando header e campi esistenti. Campi mechanics: `school, descriptors, spell_level (dict classe->liv), casting_time, components, range, duration, saving_throw, spell_resistance`.

- [ ] **Step 4: Run + verifica + commit**

Run: `cd tooling/Master-DD-Taverna && .venv/Scripts/python tools/enrich_spells.py --write`
Expected: report con >= 900/1035 spell con mechanics (match gist + regex). Verifica a campione (Fireball: school evocation, level wiz 3, Reflex half, SR yes).
Commit con trailer ADR-0011: `feat(reference): add spell mechanics from gist cache and descriptions`.

---

### Task 3: RAG chunk con `mechanics`

**Files:**
- Modify: `tooling/Master-DD-Taverna/src/rag/indexer.py`
- Modify: `tooling/Master-DD-Taverna/tests/test_rag.py` (se coperto) o test rapido inline

- [ ] **Step 1: Implement**

In `src/rag/indexer.py` (entry → testo chunk, :112-126), dopo `notes`:

```python
        if entry.get("mechanics"):
            import json as _json
            mech_text = _json.dumps(entry["mechanics"], ensure_ascii=False, sort_keys=True)
            parts.append(f"Mechanics: {mech_text[:2000]}")
```

(cap 2000 char per non gonfiare i chunk delle classi con progressione 20 livelli.)

- [ ] **Step 2: Reindice + verifica retrieval**

Run: `cd tooling/Master-DD-Taverna && .venv/Scripts/python tools/index_rag.py --include-local 2>&1 | tail -2`
Verifica: `.venv/Scripts/python -c "
from src.rag.store import VectorStore
from src.rag.retriever import Retriever
s = VectorStore.load()
r = Retriever(s)
hits = r.search('BAB fighter livello 5', top_k=3)
print([(h['source'], h['score']) for h in hits])
assert any('Fighter' in h['source'] for h in hits)
print('retrieval mechanics OK')
"`

- [ ] **Step 3: Commit** `feat(rag): include mechanics text in reference chunks` (trailer ADR-0011).

---

### Task 4: Reindex incrementale per hash contenuto (B1)

**Files:**
- Modify: `tooling/Master-DD-Taverna/src/rag/indexer.py`
- Modify: `tooling/Master-DD-Taverna/src/rag/store.py` (se serve mappa esistente)
- Modify: `tooling/Master-DD-Taverna/tests/test_rag.py`

- [ ] **Step 1: Write the failing test**

```python
def test_incremental_reindex_by_content_hash(tmp_path):
    """Il chunk id e' sha256(texto)[:16]; una seconda run ri-encoda solo i delta."""
    # vedi dettaglio implementazione sotto; il test misura che una entry
    # invariata NON venga ri-encodata e una nuova si'.
```

- [ ] **Step 2: Implement**

In `src/rag/indexer.py`:
- `_chunk_id(source, idx)` → `sha256(f"{source}::{text}")[:16]` (id stabile al contenuto, indipendente dalla posizione).
- `index_reference_catalog`: carica lo store esistente (se `is_ready()`), costruisce mappa `id -> embedding`; per ogni chunk nuovo/cambiato ri-encoda solo quelli; scarta gli id scomparsi; salva. Dedup naturale per id.

- [ ] **Step 3: Run test + full reindex finale (una tantum full) + verifica**

Il primo reindice dopo il cambio id e' full (id diversi); i successivi incrementali. Verifica chunk totali coerenti (>= 6733) e che una rilanciata senza cambi NON ri-encodi (log "0 da ri-encodare").

- [ ] **Step 4: Commit** `feat(rag): incremental reindex by content hash` (trailer ADR-0011).

---

## Note operative

- Mostri = `pi_local_only/` **NON committato** (gitignored): il commit del Task 1 tocca solo tool + test.
- Spells: join gist per nome normalizzato (`normalize_name` di enrich_reference); fallback regex sulla description se il gist non copre; report matched/unmatched.
- Task 3 e 4 toccano entrambi `src/rag/indexer.py`: fare Task 3 PRIMA, poi Task 4 sopra (il Task 4 riscrive la logica id/merge).
- Commit convenzionali + trailer ADR-0011 (`Coding-Agent: kimi-code-cli`, `Trace-Id: uuidv7`), MAI `Co-Authored-By:`.
