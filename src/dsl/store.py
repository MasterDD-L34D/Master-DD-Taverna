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
        # ponytail: env prima del default repo — l'override di deployment e'
        # un solo getenv, non una config class
        if path is None:
            env = os.environ.get(_ENV_PATH)
            path = env if env else default_path()
        self.path = Path(path)
        self._data: dict[str, Any] = {}
        self.events_log: list[dict[str, Any]] = []
        if self.path.exists():
            self._data = json.loads(self.path.read_text(encoding="utf-8"))

    def save(self, key: str, value: Any) -> None:
        """Scrittura atomica (tmp + os.replace) in read-modify-write: ogni
        save rilegge il file dal disco prima di fondere — due istanze sulla
        stessa path non si sovrascrivono a vicenda (review Codex P1, PR #554
        giro 2; rimane TOCTOU tra processi concorrenti: out of scope, il
        modello e' sequenziale in-process). Il commit in memoria avviene SOLO
        dopo la serializzazione: un valore non serializzabile (TypeError da
        json.dumps) non resta ne' in _data ne' su disco (giro 1). Lo snapshot
        e' deepcopy del chiamante (verb), non qui."""
        fresh: dict[str, Any] = {}
        if self.path.exists():
            fresh = json.loads(self.path.read_text(encoding="utf-8"))
        fresh[key] = value
        payload = json.dumps(fresh, ensure_ascii=False, indent=1)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(payload, encoding="utf-8")
        os.replace(tmp, self.path)
        self._data = fresh

    def load(self, key: str) -> Any:
        return self._data.get(key)

    def list(self, prefix: str) -> list[str]:
        return sorted(k for k in self._data if k.startswith(prefix))

    def emit(self, topic: str, payload: Any) -> None:
        self.events_log.append({"topic": topic, "payload": payload})
