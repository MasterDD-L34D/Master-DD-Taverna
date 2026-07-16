#!/usr/bin/env python3
"""Benchmark modelli Ollama per il RAG di Master-DD-Pathfinder-GPT.

Misura tempi di risposta e qualita' delle risposte per diverse query
usando lo stesso indice RAG ma modelli LLM diversi.
"""
import json
import os
import sys
import time
from pathlib import Path

import httpx

API_URL = os.getenv("BENCHMARK_API_URL", "http://localhost:8766")
API_KEY = os.getenv("BENCHMARK_API_KEY", "test")

QUERIES = [
    {
        "id": "furious_focus_prereq",
        "text": "quali sono i prerequisiti del talento Furious Focus in Pathfinder 1E?",
        "expected": "Strength 13, Power Attack, Base Attack Bonus +1",
    },
    {
        "id": "power_attack_mechanic",
        "text": "cosa fa il talento Power Attack in Pathfinder 1E?",
        "expected": "trade penalty to hit for bonus damage",
    },
    {
        "id": "magus_class",
        "text": "come funziona la classe Magus in Pathfinder 1E?",
        "expected": "spell combat, spellstrike",
    },
]

MODELS = [
    "qwen2.5-coder:7b",
    "qwen2.5-coder:14b",
    "qwen2.5:0.5b",
    "mistral:latest",
    "gemma3:12b",
    "qwen3:8b",
    "deepseek-coder-v2:16b",
]


def ask(query: str, model: str, top_k: int = 3):
    url = f"{API_URL}/rag/ask"
    payload = {
        "query": query,
        "top_k": top_k,
        "provider": "ollama",
        "ollama_model": model,
    }
    headers = {
        "Content-Type": "application/json",
        "x-api-key": API_KEY,
    }
    start = time.perf_counter()
    try:
        resp = httpx.post(url, json=payload, headers=headers, timeout=300)
        resp.raise_for_status()
        elapsed = time.perf_counter() - start
        data = resp.json()
        return {
            "ok": True,
            "elapsed_seconds": round(elapsed, 2),
            "answer": data.get("answer", ""),
            "results": [
                {"source": r.get("source"), "score": r.get("score")}
                for r in data.get("results", [])
            ],
        }
    except Exception as exc:
        elapsed = time.perf_counter() - start
        return {
            "ok": False,
            "elapsed_seconds": round(elapsed, 2),
            "error": str(exc),
        }


def main():
    out_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("../../sessione-2026-07-16/rapporti/model_benchmark.json")
    report = {
        "api_url": API_URL,
        "models": [],
    }
    for model in MODELS:
        print(f"\n=== Modello: {model} ===")
        model_result = {"model": model, "queries": []}
        for q in QUERIES:
            print(f"  Query: {q['id']}", end="", flush=True)
            res = ask(q["text"], model)
            model_result["queries"].append({
                "id": q["id"],
                "query": q["text"],
                "expected": q["expected"],
                **res,
            })
            status = "OK" if res["ok"] else "ERR"
            print(f" -> {status} in {res['elapsed_seconds']}s")
        report["models"].append(model_result)

    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nReport salvato in: {out_path}")


if __name__ == "__main__":
    main()
