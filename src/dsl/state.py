"""Path helpers per lo stato dell'interprete DSL."""

from __future__ import annotations

from typing import Any

_MISSING = object()


def get_path(root: dict, path: str, default: Any = None) -> Any:
    cur: Any = root
    for seg in path.split("."):
        if isinstance(cur, dict) and seg in cur:
            cur = cur[seg]
        else:
            return default
    return cur


def set_path(root: dict, path: str, value: Any) -> None:
    segs = path.split(".")
    cur = root
    for seg in segs[:-1]:
        nxt = cur.get(seg)
        if not isinstance(nxt, dict):
            nxt = {}
            cur[seg] = nxt
        cur = nxt
    cur[segs[-1]] = value
