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
