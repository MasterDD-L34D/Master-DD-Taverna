import json
from pathlib import Path
import re


def extract_documented_modules(index_path: Path) -> set[str]:
    content = index_path.read_text(encoding="utf-8")
    pattern = re.compile(r"^- `([^`]+)`", re.MULTILINE)
    return set(pattern.findall(content))


def list_module_files(modules_dir: Path) -> set[str]:
    files = {path.name for path in modules_dir.iterdir() if path.is_file()}
    directories = {
        f"src/modules/{path.name}/" for path in modules_dir.iterdir() if path.is_dir()
    }
    return files | directories


def load_json_module_index(index_path: Path) -> set[str]:
    content = json.loads(index_path.read_text(encoding="utf-8"))
    return {
        entry.get("module")
        for entry in content.get("entries", [])
        if entry.get("module")
    }


def test_module_index_matches_filesystem():
    index_path = Path("docs/module_index.md")
    modules_dir = Path("src/modules")

    documented_modules = extract_documented_modules(index_path)
    filesystem_modules = list_module_files(modules_dir)

    missing_in_index = filesystem_modules - documented_modules
    missing_on_disk = documented_modules - filesystem_modules

    messages = []
    if missing_in_index:
        messages.append(
            "File presenti in src/modules non elencati in docs/module_index.md: "
            + ", ".join(sorted(missing_in_index))
        )
    if missing_on_disk:
        messages.append(
            "Voci in docs/module_index.md senza file corrispondente in src/modules: "
            + ", ".join(sorted(missing_on_disk))
        )

    assert not messages, "; ".join(messages)


def test_data_module_index_is_valid_json():
    """src/data/module_index.json is a build artifact; we only check it parses."""
    index_path = Path("src/data/module_index.json")
    if not index_path.is_file():
        return
    load_json_module_index(index_path)
