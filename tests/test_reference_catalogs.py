"""Invarianti dei cataloghi OGL reali (dati su disco, nessuna rete)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.import_reference import _class_skill_matches

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


def test_class_skills_crossref():
    """Ogni class_skill di classes.json matcha una skill del catalogo
    (con espansione Knowledge (all) via _class_skill_matches)."""
    skills = {e["name"] for e in _load("skills.json")["entries"]}
    classes = _load("classes.json")["entries"]
    missing = []
    for cls in classes:
        for cs in cls.get("mechanics", {}).get("class_skills", []):
            if not any(_class_skill_matches(s, cs) for s in skills):
                missing.append((cls["name"], cs))
    assert not missing, f"class skills senza match nel catalogo: {missing}"
    print("OK: cross-ref class skills completo")
