#!/usr/bin/env python3
"""Download pagine aonprd.com con cache su disco e rate limit cortese.

La cache vive in data/reference/aon_cache/ (gitignored): i dump HTML grezzi
non si committano. Uso: `python tools/reference_fetch.py <url> [<url>...]`.
Le funzioni sono importabili dai tool di import (fetch/cache_path).
"""
import argparse
import hashlib
import time
import urllib.request
from pathlib import Path

CACHE_DIR = Path("data/reference/aon_cache")
UA = {"User-Agent": "MasterDD-Taverna/1.0 (cataloghi OGL locali; uso personale)"}
TIMEOUT = 30


def cache_path(url):
    """Path di cache deterministico per un URL (dentro CACHE_DIR)."""
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
    return CACHE_DIR / f"{digest}.html"


def fetch(url, delay=2.0, cache=True):
    """Ritorna l'HTML dell'URL (stringa). Se cache=True e il file esiste,
    legge da disco senza rete; altrimenti scarica (dopo `delay` secondi),
    salva in cache e ritorna."""
    path = cache_path(url)
    if cache and path.exists():
        return path.read_text(encoding="utf-8", errors="replace")
    if delay > 0:
        time.sleep(delay)
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        text = resp.read().decode("utf-8", errors="replace")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return text


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("urls", nargs="+", help="URL aonprd da scaricare in cache")
    ap.add_argument("--delay", type=float, default=2.0, help="pausa tra richieste (s)")
    args = ap.parse_args(argv)
    for url in args.urls:
        path = cache_path(url)
        fetch(url, delay=args.delay)
        print(f"OK: {url} -> {path}")


if __name__ == "__main__":
    main()
