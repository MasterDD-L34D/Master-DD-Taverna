"""Test per tools/reference_fetch.py (cache logic, nessuna rete)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.reference_fetch import cache_path, fetch


def test_cache_path_deterministic(tmp_path, monkeypatch):
    monkeypatch.setattr("tools.reference_fetch.CACHE_DIR", tmp_path)
    a = cache_path("https://aonprd.com/Rules.aspx?Name=X")
    b = cache_path("https://aonprd.com/Rules.aspx?Name=X")
    c = cache_path("https://aonprd.com/Rules.aspx?Name=Y")
    assert a == b and a != c and a.suffix == ".html"


def test_fetch_uses_cache(tmp_path, monkeypatch):
    monkeypatch.setattr("tools.reference_fetch.CACHE_DIR", tmp_path)
    url = "https://aonprd.com/Rules.aspx?Name=Fixture"
    cache_path(url).write_text("<html>cached</html>", encoding="utf-8")
    assert fetch(url, delay=0) == "<html>cached</html>"  # nessuna rete: legge la cache
    print("OK: reference_fetch cache")


def test_fetch_scarica_con_scrapling_e_salva_in_cache(tmp_path, monkeypatch):
    # Decisione owner 2026-11-01: lo scraping passa sempre da scrapling.
    monkeypatch.setattr("tools.reference_fetch.CACHE_DIR", tmp_path)
    chiamate = []

    class FintaRisposta:
        status = 200
        encoding = "utf-8"
        body = "<html>da scrapling</html>".encode("utf-8")

    class FintoFetcher:
        @staticmethod
        def get(url, **kwargs):
            chiamate.append(url)
            return FintaRisposta()

    monkeypatch.setattr("tools.reference_fetch.Fetcher", FintoFetcher)
    url = "https://aonprd.com/Rules.aspx?Name=Nuova"
    assert fetch(url, delay=0) == "<html>da scrapling</html>"
    assert chiamate == [url]
    assert cache_path(url).read_text(encoding="utf-8") == "<html>da scrapling</html>"


def test_fetch_errore_http_solleva_e_non_scrive_cache(tmp_path, monkeypatch):
    # urllib sollevava su 404/500 e gli import contano su quell'eccezione
    # ("FETCH FALLITO"); scrapling restituisce lo stato senza sollevare.
    import pytest

    monkeypatch.setattr("tools.reference_fetch.CACHE_DIR", tmp_path)

    class Risposta404:
        status = 404
        encoding = "utf-8"
        body = b"<html>not found</html>"

    class FintoFetcher:
        @staticmethod
        def get(url, **kwargs):
            return Risposta404()

    monkeypatch.setattr("tools.reference_fetch.Fetcher", FintoFetcher)
    url = "https://aonprd.com/Rules.aspx?Name=Assente"
    with pytest.raises(OSError, match="404"):
        fetch(url, delay=0)
    assert not cache_path(url).exists()
