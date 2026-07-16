"""Index modules and reference catalog into the vector store."""
import hashlib
import json
import re
from pathlib import Path

import numpy as np

from .store import VectorStore


def _chunk_id(source: str, idx: int) -> str:
    base = f"{source}::{idx}"
    return hashlib.sha256(base.encode("utf-8")).hexdigest()[:16]


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
    sources = []
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
                "id": _chunk_id(source, idx),
                "source": source,
                "text": chunk_text,
                "meta": {"index": idx},
            })
            texts.append(chunk_text)
            sources.append(source)
    if not texts:
        raise ValueError("Nessun testo trovato da indicizzare")
    embeddings = encoder.encode(texts, show_progress_bar=True, convert_to_numpy=True)
    store.save(chunks, embeddings, model_name)
    return len(chunks)


def index_reference_catalog(reference_dir: Path | str, store: VectorStore, model_name: str, encoder):
    """Index structured reference entries (feats, spells, items) as short documents."""
    reference_dir = Path(reference_dir)
    files = {
        "feats": reference_dir / "feats.json",
        "spells": reference_dir / "spells.json",
        "items": reference_dir / "items.json",
    }
    chunks = []
    texts = []
    for kind, path in files.items():
        if not path.exists():
            continue
        data = json.load(open(path, encoding="utf-8"))
        entries = data if isinstance(data, list) else data.get("entries", [])
        for idx, entry in enumerate(entries):
            text_parts = [entry.get("name", "")]
            if "prerequisites" in entry:
                text_parts.append(f"Prerequisiti: {entry['prerequisites']}")
            if "description" in entry:
                text_parts.append(entry["description"])
            elif "short_description" in entry:
                text_parts.append(entry["short_description"])
            text = "\n".join(text_parts)
            if not text.strip():
                continue
            source = f"reference::{kind}::{entry.get('name', idx)}"
            chunks.append({
                "id": _chunk_id(source, idx),
                "source": source,
                "text": text,
                "meta": {"kind": kind, "entry": entry.get("name", "")},
            })
            texts.append(text)
    if not texts:
        return 0
    embeddings = encoder.encode(texts, show_progress_bar=True, convert_to_numpy=True)
    # merge with existing store if present
    if store.is_ready():
        store.chunks.extend(chunks)
        store.embeddings = np.vstack([store.embeddings, embeddings])
        store.meta["count"] = len(store.chunks)
        store.save(store.chunks, store.embeddings, model_name)
    else:
        store.save(chunks, embeddings, model_name)
    return len(chunks)
