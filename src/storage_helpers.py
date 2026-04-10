import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from fastapi import HTTPException

from .config import settings

TAVERNA_SAVES_MAX_FILES = 200


def list_files(base: Path) -> List[Dict]:
    out: List[Dict] = []
    if not base.exists() or not base.is_dir():
        raise HTTPException(status_code=503, detail=f"Directory di configurazione non trovata: {base}")
    for p in sorted(base.iterdir()):
        if p.is_file():
            out.append({"name": p.name, "size_bytes": p.stat().st_size, "suffix": p.suffix})
    return out


def taverna_saves_metrics(taverna_saves_dir: Path) -> Dict[str, object]:
    if not taverna_saves_dir.exists() or not taverna_saves_dir.is_dir():
        raise HTTPException(status_code=503, detail=f"Directory taverna_saves non trovata: {taverna_saves_dir}")

    files = [p for p in taverna_saves_dir.iterdir() if p.is_file()]
    file_count = len(files)
    total_size = sum(p.stat().st_size for p in files)
    disk_usage = shutil.disk_usage(taverna_saves_dir)

    return {
        "path": str(taverna_saves_dir),
        "max_files": TAVERNA_SAVES_MAX_FILES,
        "current_files": file_count,
        "remaining_files": max(TAVERNA_SAVES_MAX_FILES - file_count, 0),
        "total_size_bytes": total_size,
        "disk_usage": {
            "total_bytes": disk_usage.total,
            "used_bytes": disk_usage.used,
            "free_bytes": disk_usage.free,
        },
        "quota_ok": file_count < TAVERNA_SAVES_MAX_FILES and disk_usage.free > 0,
    }


def taverna_saves_metadata(taverna_saves_dir: Path) -> Dict[str, object]:
    metrics = taverna_saves_metrics(taverna_saves_dir)

    auto_name_policy = {
        "pattern": "NPC-YYYYMMDD-HHMM",
        "example": datetime.utcnow().strftime("NPC-%Y%m%d-%H%M"),
        "max_files": TAVERNA_SAVES_MAX_FILES,
        "on_overflow": "delete_oldest",
    }

    metrics.update(
        {
            "remaining_bytes": metrics.get("disk_usage", {}).get("free_bytes", 0),
            "auto_name_policy": auto_name_policy,
            "module_dump_allowed": settings.allow_module_dump,
            "partial_dump_notice": (
                "Output limitato: ALLOW_MODULE_DUMP=false — i dump testo sono tronchi a 4k char con header X-Content-Partial/X-Content-Remaining-Bytes"
                if not settings.allow_module_dump
                else None
            ),
        }
    )
    return metrics
