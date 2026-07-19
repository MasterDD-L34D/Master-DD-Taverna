"""Index modules and reference catalog into the vector store."""
import hashlib
import json
import re
from pathlib import Path

import numpy as np

from .store import VectorStore


def _chunk_id(source: str, text: str) -> str:
    """Id stabile al contenuto: sha256(source::text)[:16], indipendente dalla posizione."""
    base = f"{source}::{text}"
    return hashlib.sha256(base.encode("utf-8")).hexdigest()[:16]


_REFERENCE_PREFIX = "reference::"


def _is_reference_source(source: str) -> bool:
    return source.startswith(_REFERENCE_PREFIX)


def _merge_and_save(store: VectorStore, chunks: list[dict], texts: list[str],
                    is_domain, model_name: str, encoder, label: str) -> int:
    """Salva `chunks` nello store riusando gli embedding dei chunk invariati.

    L'id di ogni chunk e' un hash del contenuto: i chunk del dominio
    `is_domain` gia' presenti nello store con lo stesso id riusano il
    vecchio embedding; solo quelli nuovi o cambiati vengono ri-encodati.
    I chunk del dominio scomparsi vengono scartati, quelli fuori dominio
    restano intatti. Ritorna il numero di chunk salvati per questo dominio.
    """
    # dedup naturale per id dentro il lotto nuovo
    seen: set[str] = set()
    unique_chunks, unique_texts = [], []
    for c, t in zip(chunks, texts):
        if c["id"] in seen:
            continue
        seen.add(c["id"])
        unique_chunks.append(c)
        unique_texts.append(t)

    keep: list = []                  # (chunk, embedding) fuori dominio
    reuse: dict = {}                 # id -> embedding nel dominio
    if store.is_ready():
        for i, old in enumerate(store.chunks):
            if is_domain(old["source"]):
                reuse[old["id"]] = store.embeddings[i]
            else:
                keep.append((old, store.embeddings[i]))

    to_encode = [i for i, c in enumerate(unique_chunks) if c["id"] not in reuse]
    print(f"  {label}: {len(to_encode)} da ri-encodare su {len(unique_chunks)}")
    new_embeddings = (
        encoder.encode([unique_texts[i] for i in to_encode], show_progress_bar=True, convert_to_numpy=True)
        if to_encode else None
    )
    it = iter(new_embeddings) if new_embeddings is not None else iter(())
    merged = [reuse[c["id"]] if c["id"] in reuse else next(it) for c in unique_chunks]

    all_chunks = [c for c, _ in keep] + unique_chunks
    if not all_chunks:
        return 0
    parts = []
    if keep:
        parts.append(np.stack([e for _, e in keep]))
    if merged:
        parts.append(np.stack(merged))
    store.save(all_chunks, np.vstack(parts), model_name)
    return len(unique_chunks)


def _split_paragraphs(text: str, max_chars: int = 1200, overlap: int = 200) -> list[str]:
    """Split text into chunks by paragraphs first, then by sentences if too long."""
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks = []
    for para in paragraphs:
        if len(para) <= max_chars:
            chunks.append(para)
            continue
        # split by sentences (rough but safe)
        sentences = re.split(r"(?<=[.!?])\s+", para)
        buf = ""
        for sent in sentences:
            if len(buf) + len(sent) + 1 > max_chars and buf:
                chunks.append(buf.strip())
                buf = buf[-overlap:] if overlap < len(buf) else ""
            buf = (buf + " " + sent).strip()
        if buf:
            chunks.append(buf.strip())
    return chunks


def index_modules(modules_dir: Path | str, store: VectorStore, model_name: str, encoder):
    modules_dir = Path(modules_dir)
    chunks = []
    texts = []
    for path in sorted(modules_dir.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in (".txt", ".md"):
            continue
        text = path.read_text(encoding="utf-8")
        # skip front matter if present
        if text.startswith("---"):
            parts = text.split("---", 2)
            if len(parts) >= 3:
                text = parts[2]
        source = str(path.relative_to(modules_dir))
        for idx, chunk_text in enumerate(_split_paragraphs(text)):
            chunks.append({
                "id": _chunk_id(source, chunk_text),
                "source": source,
                "text": chunk_text,
                "meta": {"index": idx},
            })
            texts.append(chunk_text)
    if not texts:
        raise ValueError("Nessun testo trovato da indicizzare")
    return _merge_and_save(store, chunks, texts,
                           lambda s: not _is_reference_source(s),
                           model_name, encoder, "moduli")


def _catalog_entries(catalog: dict, reference_dir: Path, include_local: bool):
    """Return the list of entries for a manifest catalog, or None if skipped."""
    path = reference_dir / catalog.get("file", "")
    if not path.exists():
        return None
    is_local = catalog.get("local_only", False) or "pi_local_only" in path.parts
    if is_local and not include_local:
        return None
    data = json.load(open(path, encoding="utf-8"))
    if isinstance(data, dict):
        return data.get("entries", [])
    return data if isinstance(data, list) else []


def index_reference_catalog(reference_dir: Path | str, store: VectorStore, model_name: str, encoder, include_local: bool = False):
    """Index structured reference entries declared in manifest.json.

    Only catalogs with is_ogc=True or cup_allowed=True are indexed.
    Catalogs with local_only=True (or inside pi_local_only/) are indexed only
    when include_local=True.
    """
    reference_dir = Path(reference_dir)
    manifest_path = reference_dir / "manifest.json"
    if not manifest_path.exists():
        raise ValueError(f"Manifest non trovato: {manifest_path}")
    manifest = json.load(open(manifest_path, encoding="utf-8"))
    catalogs = manifest.get("catalogs", []) if isinstance(manifest, dict) else []

    chunks = []
    texts = []
    for catalog in catalogs:
        if not isinstance(catalog, dict):
            continue
        is_local = catalog.get("local_only", False) or "pi_local_only" in str(catalog.get("file", ""))
        if is_local:
            if not include_local:
                continue
        elif not (catalog.get("is_ogc") or catalog.get("cup_allowed")):
            continue
        kind = catalog.get("kind") or Path(catalog.get("file", "")).stem
        entries = _catalog_entries(catalog, reference_dir, include_local)
        if entries is None:
            continue
        for idx, entry in enumerate(entries):
            if not isinstance(entry, dict):
                continue
            text_parts = [entry.get("name", "")]
            if "prerequisites" in entry:
                text_parts.append(f"Prerequisiti: {entry['prerequisites']}")
            if "description" in entry:
                text_parts.append(entry["description"])
            elif "short_description" in entry:
                text_parts.append(entry["short_description"])
            if "notes" in entry and entry["notes"]:
                text_parts.append(entry["notes"])
            if entry.get("mechanics"):
                mech_text = json.dumps(entry["mechanics"], ensure_ascii=False, sort_keys=True)
                text_parts.append(f"Mechanics: {mech_text[:2000]}")
            if "tags" in entry and entry["tags"]:
                text_parts.append("Tags: " + ", ".join(str(t) for t in entry["tags"]))
            text = "\n".join(text_parts)
            if not text.strip():
                continue
            source = f"reference::{kind}::{entry.get('name', idx)}"
            chunks.append({
                "id": _chunk_id(source, text),
                "source": source,
                "text": text,
                "meta": {"kind": kind, "entry": entry.get("name", "")},
            })
            texts.append(text)
    return _merge_and_save(store, chunks, texts,
                           _is_reference_source,
                           model_name, encoder, "reference")
