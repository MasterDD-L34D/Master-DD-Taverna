import json
import logging
import re
from pathlib import Path
from typing import Dict, List, Mapping

import yaml

REFERENCE_MANIFEST_PATH = Path(__file__).resolve().parent.parent / "data" / "reference" / "manifest.json"


def load_reference_manifest() -> Mapping[str, object]:
    try:
        manifest = json.loads(REFERENCE_MANIFEST_PATH.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover
        logging.error("Impossibile leggere il manifest di riferimento: %s", exc)
        return {}
    return manifest if isinstance(manifest, Mapping) else {}


def reference_catalog_version() -> str | None:
    manifest = load_reference_manifest()
    version = manifest.get("version") if isinstance(manifest, Mapping) else None
    return str(version) if version else None


def parse_json_module_metadata(text: str, *, source: Path | None = None) -> Dict[str, object]:
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        logging.warning("Impossibile analizzare il modulo JSON", extra={"path": str(source or "<inline>")})
        return {}

    if not isinstance(parsed, Mapping):
        return {}

    metadata: Dict[str, object] = {}
    candidates: List[Mapping] = [parsed]
    meta_block = parsed.get("meta")
    if isinstance(meta_block, Mapping):
        candidates.append(meta_block)

    for block in candidates:
        version = block.get("version")
        if version is not None and "version" not in metadata:
            metadata["version"] = version

        compatibility = block.get("compatibility")
        if compatibility is not None and "compatibility" not in metadata:
            metadata["compatibility"] = compatibility

    return metadata


def parse_front_matter_metadata(text: str, *, source: Path | None = None) -> Dict[str, object]:
    metadata: Dict[str, object] = {}
    version_match = re.search(r"^version:\s*\"?(?P<version>[^\n#]+)\"?\s*$", text, re.MULTILINE)
    if version_match:
        metadata["version"] = version_match.group("version").strip().strip('"')

    lines = text.splitlines()
    for idx, line in enumerate(lines):
        if not line.startswith("compatibility:"):
            continue

        inline_value = line.partition(":")[2].strip()
        if inline_value:
            metadata["compatibility"] = inline_value.strip(' "')
            break

        block_lines: List[str] = []
        for block_line in lines[idx + 1 :]:
            if block_line.startswith((" ", "\t")):
                block_lines.append(block_line)
            else:
                break

        if block_lines:
            snippet = "compatibility:\n" + "\n".join(block_lines)
            try:
                parsed = yaml.safe_load(snippet)
                compatibility = parsed.get("compatibility") if isinstance(parsed, dict) else None
                if compatibility is not None:
                    metadata["compatibility"] = compatibility
            except yaml.YAMLError:
                logging.warning(
                    "Impossibile analizzare il blocco compatibility",
                    extra={"path": str(source or "<inline>")},
                )
        break

    return metadata


def parse_knowledge_pack_metadata(text: str) -> Dict[str, str]:
    match = re.search(
        r"\*\*Versione:\*\*\s*(?P<version>[^•\n]+).*?\*\*Compatibilità:\*\*\s*(?P<compatibility>[^\n<]+)",
        text,
    )
    if not match:
        return {}
    return {
        "version": match.group("version").strip(),
        "compatibility": match.group("compatibility").strip(),
    }


def parse_module_metadata(path: Path) -> Dict[str, object]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    metadata: Dict[str, object] = {}

    if path.suffix.lower() == ".json":
        metadata.update(parse_json_module_metadata(text, source=path))
        return metadata

    metadata.update(parse_front_matter_metadata(text, source=path))

    if path.name == "knowledge_pack.md":
        metadata.update(parse_knowledge_pack_metadata(text))

    return metadata
