"""Logical URI resolver for modules and bundled assets.

The modules in ``src/modules/`` historically contained hard-coded relative
paths such as ``src/modules/archivist.txt`` or ``src/data/The Gear Guide.pdf``.
This resolver introduces a small logical URI scheme so that modules can refer
to resources without assuming the repository layout:

- ``module://{name}`` resolves to ``src/modules/{name}``
- ``asset://{name}`` resolves to ``src/data/{name}``
- ``template://{name}`` resolves to ``templates/{name}`` (project root)
- ``reference://{type}/{name}`` resolves to ``src/data/reference/{type}/{name}``

Plain filesystem paths are accepted as a legacy fallback.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Pattern

from ..config import BASE_DIR, DATA_DIR, MODULES_DIR


MODULE_URI_PATTERN: Pattern[str] = re.compile(
    r"^(module|asset|template|reference)://(.+)$"
)


def resolve_module_uri(uri: str) -> Path | None:
    """Resolve a logical URI to a filesystem path.

    Returns ``None`` for empty/whitespace URIs. Plain paths are returned
    as-is without checking existence.

    For ``module://`` URIs, if the resolved path has no suffix and does not
    exist, common module suffixes (``.txt``, ``.md``, ``.json``) are tried
    so that ``module://archivist`` resolves to ``src/modules/archivist.txt``.
    """
    if not uri or not uri.strip():
        return None

    match = MODULE_URI_PATTERN.match(uri)
    if not match:
        return Path(uri)

    scheme, rest = match.groups()
    rest = rest.lstrip("/")

    if scheme == "module":
        candidate = MODULES_DIR / rest
        if candidate.suffix:
            return candidate
        for suffix in (".txt", ".md", ".json"):
            with_suffix = candidate.with_suffix(suffix)
            if with_suffix.is_file():
                return with_suffix
        return candidate
    if scheme == "asset":
        return DATA_DIR / rest
    if scheme == "template":
        return BASE_DIR.parent / "templates" / rest
    if scheme == "reference":
        return DATA_DIR / "reference" / rest

    return Path(uri)


def list_module_uris(text: str) -> list[str]:
    """Return all logical module/asset/template/reference URIs found in *text*."""
    return MODULE_URI_PATTERN.findall(text)
