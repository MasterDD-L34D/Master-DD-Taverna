"""Mock MinMax Builder API serving local fixtures for generate_build_db."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Response

ROOT = Path(__file__).resolve().parent.parent
BUILDS_DIR = ROOT / "src" / "data" / "builds"
MODULES_DIR = ROOT / "src" / "modules"
MODULE_INDEX = ROOT / "src" / "data" / "module_index.json"

app = FastAPI(title="Mock Builder API", version="0.1.0")


def _slugify(name: str) -> str:
    return name.strip().lower().replace(" ", "_").replace("-", "")


def _load_json(path: Path) -> Any:
    if not path.is_file():
        raise HTTPException(status_code=404, detail=f"File non trovato: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.api_route("/modules/minmax_builder.txt", methods=["GET", "POST"])
async def fetch_build(
    class_: str | None = Query(default=None, alias="class"),
    race: str | None = Query(default=None),
    archetype: str | None = Query(default=None),
    level: int | None = Query(default=None),
) -> Any:
    if not class_:
        raise HTTPException(status_code=400, detail="Parametro 'class' mancante")

    slug_parts = [_slugify(class_)]
    if race:
        slug_parts.append(_slugify(race))
    if archetype:
        slug_parts.append(_slugify(archetype))

    base_slug = "_".join(slug_parts)

    slug_variants = [base_slug]
    hyphen_variant = base_slug.replace("_", "-")
    if hyphen_variant not in slug_variants:
        slug_variants.append(hyphen_variant)

    if level and level > 0:
        for variant in slug_variants:
            level_slug = f"{variant}_lvl{int(level):02d}"
            level_path = BUILDS_DIR / f"{level_slug}.json"
            if level_path.is_file():
                return _load_json(level_path)

    for variant in slug_variants:
        build_path = BUILDS_DIR / f"{variant}.json"
        if build_path.is_file():
            return _load_json(build_path)

    build_path = BUILDS_DIR / f"{_slugify(class_)}.json"

    return _load_json(build_path)


@app.get("/modules")
async def list_modules() -> list[str]:
    index_payload = _load_json(MODULE_INDEX)
    entries = (
        index_payload.get("entries", []) if isinstance(index_payload, dict) else []
    )
    names: list[str] = []
    for entry in entries:
        name = None
        if isinstance(entry, dict):
            name = entry.get("module") or entry.get("name")
        if name:
            names.append(str(name))
    if not names:
        names = sorted(path.name for path in MODULES_DIR.glob("**/*") if path.is_file())
    return names


@app.get("/modules/{name:path}/meta")
async def module_meta(name: str) -> dict[str, Any]:
    index_payload = _load_json(MODULE_INDEX)
    entries = (
        index_payload.get("entries", []) if isinstance(index_payload, dict) else []
    )
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        if entry.get("module") == name and entry.get("meta"):
            return entry["meta"]
    module_path = MODULES_DIR / name
    if not module_path.is_file():
        raise HTTPException(status_code=404, detail=f"Modulo non trovato: {name}")
    return {
        "name": name,
        "size_bytes": module_path.stat().st_size,
        "suffix": module_path.suffix,
    }


@app.get("/modules/{name:path}")
async def fetch_module(name: str) -> Response:
    module_path = MODULES_DIR / name
    if not module_path.is_file():
        raise HTTPException(status_code=404, detail=f"Modulo non trovato: {name}")
    content = module_path.read_text(encoding="utf-8")
    media_type = "text/plain"
    if module_path.suffix.lower() in {".md", ".markdown"}:
        media_type = "text/markdown"
    return Response(content=content, media_type=media_type)


@app.post("/ruling")
async def ruling_expert_stub(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """Minimal stub for Ruling Expert validation used in local harvest runs."""

    return {
        "status": "ok",
        "ruling_badge": "validated",
        "violations": [],
        "payload_echo": payload or {},
    }
