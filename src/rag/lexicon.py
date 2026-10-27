"""Lessico query-translation IT->EN per il retrieval (finding RAG eval
2026-07-25: hit rate 33% su query italiane -> 78% con traduzione).

Il lessico vive in `data/it_en_lexicon.json` (estendibile senza toccare il
codice). La traduzione preserva il case del testo non tradotto: il boost
nome del retriever e' case-sensitive sui nomi propri inglesi.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

LEXICON_PATH = Path(__file__).resolve().parents[2] / "data" / "it_en_lexicon.json"


def load_lexicon(path: Path | None = None) -> dict[str, str]:
    """Carica il lessico IT->EN; {} se il file non esiste."""
    p = path or LEXICON_PATH
    if not p.exists():
        return {}
    return {k.lower(): v for k, v in json.loads(p.read_text(encoding="utf-8")).items()}


def translate_query(query: str, lexicon: dict[str, str]) -> str:
    """Sostituisce i termini IT noti con l'inglese (frasi piu' lunghe prima,
    case-insensitive), preservando il case del resto."""
    out = query
    for it, en in sorted(lexicon.items(), key=lambda kv: -len(kv[0])):
        out = re.sub(re.escape(it), en, out, flags=re.IGNORECASE)
    return out
