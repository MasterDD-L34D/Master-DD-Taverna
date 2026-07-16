#!/usr/bin/env python3
"""CLI per generare build Pathfinder 1E con il Build Agent.

Uso:
  .venv/Scripts/python tools/build_agent.py --class Fighter --race Human --level 5 --focus DPR
  .venv/Scripts/python tools/build_agent.py --class Wizard --race Elf --level 10 --focus control --provider ollama
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sentence_transformers import SentenceTransformer

from src.config import DATA_DIR
from src.rag.retriever import Retriever
from src.rag.store import VectorStore
from src.agents.builder import generate_build


def main():
    ap = argparse.ArgumentParser(description="Build Agent CLI")
    ap.add_argument("--class", dest="class_name", required=True, help="Classe del personaggio")
    ap.add_argument("--race", default="Human", help="Razza")
    ap.add_argument("--level", type=int, default=5, help="Livello (1-20)")
    ap.add_argument("--archetype", default=None, help="Archetipo")
    ap.add_argument("--focus", default="balanced", help="Focus della build (DPR, tank, control, support)")
    ap.add_argument("--provider", default=None, help="Provider LLM: mock, ollama, openai")
    ap.add_argument("--output", default=None, help="File JSON di output (opzionale)")
    args = ap.parse_args()

    store_dir = Path(DATA_DIR / "vector_store")
    store = VectorStore(store_dir)
    if not store.is_ready():
        print("ERRORE: indice RAG non trovato. Esegui: python tools/index_rag.py", file=sys.stderr)
        sys.exit(1)

    model = "paraphrase-multilingual-MiniLM-L12-v2"
    encoder = SentenceTransformer(model)
    retriever = Retriever(store, encoder)

    request = {
        "class": args.class_name,
        "race": args.race,
        "level": args.level,
        "archetype": args.archetype,
        "focus": args.focus,
    }

    payload = generate_build(request, retriever=retriever, provider_name=args.provider)
    out = json.dumps(payload, ensure_ascii=False, indent=2)

    if args.output:
        Path(args.output).write_text(out, encoding="utf-8")
        print(f"Build salvata in: {args.output}")
    else:
        print(out)


if __name__ == "__main__":
    main()
