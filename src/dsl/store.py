"""Archivio sessione (ADR 009): porta di persistenza per i verbi sessione.

JsonFilePort e' la porta concreta di default: un unico file JSON, scrittura
atomica (tmp + os.replace), caricamento all'init. Il path si sovrascrive con
la env MASTERS_DD_SESSIONS_PATH; default: var/sessions/store.json sotto repo.

Confine fiducia: la validazione delle chiavi NON vive qui ma nei verbi
dell'interprete — la porta si fida dei chiamanti (in-process, moduli solo
dal repo, vedi modello di minaccia in interpreter.py).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

_ENV_PATH = "MASTERS_DD_SESSIONS_PATH"


def default_path() -> Path:
    """Repo root = genitore di src/dsl; var/ e' gitignored (git clean -fdx
    lo cancella: vedi README)."""
    return Path(__file__).resolve().parents[2] / "var" / "sessions" / "store.json"


class JsonFilePort:
    """Porta JSON su file unico: save/load/list + emit in memoria.

    emit non persiste perche' gli eventi hanno gia' il loro canale nel
    runtime (it.events); la firma serve ai verbi per restare indiretti."""

    def __init__(self, path: os.PathLike | str | None = None) -> None:
        self.path = Path(path) if path is not None else default_path()
        self._data: dict[str, Any] = {}
        self.events_log: list[dict[str, Any]] = []
        if self.path.exists():
            self._data = json.loads(self.path.read_text(encoding="utf-8"))

    def save(self, key: str, value: Any) -> None:
        """Scrittura atomica (tmp + os.replace). TypeError da json.dumps
        (valore non serializzabile) propagate: l'interprete li converte in
        evento, mai str() silenzioso (ADR 009)."""
        self._data[key] = value
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=1), encoding="utf-8"
        )
        os.replace(tmp, self.path)

    def load(self, key: str) -> Any:
        return self._data.get(key)

    def list(self, prefix: str) -> list[str]:
        return sorted(k for k in self._data if k.startswith(prefix))

    def emit(self, topic: str, payload: Any) -> None:
        self.events_log.append({"topic": topic, "payload": payload})
