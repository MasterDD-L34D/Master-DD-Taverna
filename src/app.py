import json
import logging
import re
import shutil
from ipaddress import ip_address
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from time import monotonic
from typing import Dict, List, Mapping

import yaml
from fastapi import (
    APIRouter,
    Body,
    Depends,
    FastAPI,
    Header,
    HTTPException,
    Query,
    Request,
    Response,
)
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, generate_latest
from jsonschema.exceptions import ValidationError

from .config import MODULES_DIR, DATA_DIR, settings
from .auth_backoff import (
    _accepted_metrics_keys,
    _failed_attempts,
    _is_metrics_ip_allowed,
    require_api_key,
    require_metrics_access,
    reset_failed_attempts as _reset_failed_attempts,
)
from .metadata_parser import (
    load_reference_manifest as _load_reference_manifest,
    parse_front_matter_metadata as _parse_front_matter_metadata,
    parse_json_module_metadata as _parse_json_module_metadata,
    parse_knowledge_pack_metadata as _parse_knowledge_pack_metadata,
    parse_module_metadata as _parse_module_metadata,
    reference_catalog_version as _reference_catalog_version,
)
from .builder.stub_builder import StubBuilderError, build_stub_payload
from .storage_helpers import list_files as _list_files, taverna_saves_metadata as _taverna_saves_metadata, taverna_saves_metrics as _taverna_saves_metrics
from .rag.router import router as rag_router


REFERENCE_MANIFEST_PATH = (
    Path(__file__).resolve().parent.parent / "data" / "reference" / "manifest.json"
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Perform startup checks using FastAPI lifespan API."""

    _validate_directories(raise_on_error=True)
    yield


router = APIRouter()

app = FastAPI(
    title="Master-DD-Taverna Core API",
    version="1.0.0",
    description="API per esporre i moduli del kernel Master-DD-Taverna ai client (RAG locale; GPT Actions come integrazione legacy).",
    lifespan=lifespan,
)


REQUEST_COUNT = Counter(
    "app_requests_total",
    "Totale richieste per endpoint, metodo e classe di status.",
    labelnames=["endpoint", "method", "status_class"],
)
ERROR_COUNT = Counter(
    "app_error_responses_total",
    "Totale risposte di errore (4xx/5xx) per endpoint, metodo e classe di status.",
    labelnames=["endpoint", "method", "status_class"],
)
AUTH_BACKOFF_TRIGGER = Counter(
    "auth_backoff_trigger_total",
    "Numero di volte in cui è stato attivato il backoff sull'autenticazione.",
)
DIRECTORY_STATUS = Gauge(
    "app_directory_status",
    "Stato delle directory configurate: 1 ok, 0 errore.",
    labelnames=["directory"],
)


REQUIRED_MODULE_FILES = [
    "base_profile.txt",
    "minmax_builder.txt",
    "Taverna_NPC.txt",
    "Encounter_Designer.txt",
    "adventurer_ledger.txt",
    "ruling_expert.txt",
    "explain_methods.txt",
    "archivist.txt",
    "narrative_flow.txt",
    "scheda_pg_markdown_template.md",
]


TAVERNA_SAVES_DIR = MODULES_DIR / "taverna_saves"
TAVERNA_SAVES_MAX_FILES = 200


@app.get("/health")
async def health() -> Dict[str, Dict]:
    """Simple healthcheck for Actions."""
    diagnostic = _validate_directories()
    status_code = 200 if diagnostic["status"] == "ok" else 503

    return JSONResponse(status_code=status_code, content=diagnostic)


_dir_validation_error: str | None = None


def _validate_directories(raise_on_error: bool = False) -> Dict[str, Dict]:
    """Ensure configured module/data directories exist and log issues.

    Parameters
    ----------
    raise_on_error: bool
        If True, a RuntimeError is raised when validation fails.
    """

    global _dir_validation_error

    directories: Dict[str, Dict[str, str | None]] = {}
    errors: list[str] = []
    for label, path in ("modules", MODULES_DIR), ("data", DATA_DIR):
        is_valid = path.exists() and path.is_dir()
        message = None
        if not is_valid:
            message = f"Directory {label} mancante o non accessibile: {path}"
            logging.error(
                "Directory validation failed",
                extra={
                    "event": "directory_validation_failed",
                    "directory": label,
                    "path": str(path),
                    "detail": message,
                },
            )
            errors.append(message)

        directories[label] = {
            "status": "ok" if is_valid else "error",
            "path": str(path),
            "message": message,
        }
        DIRECTORY_STATUS.labels(directory=label).set(1 if is_valid else 0)

    missing_required_files: list[str] = []
    required_files_status = "ok"

    if directories["modules"]["status"] == "ok":
        missing_required_files = sorted(
            name for name in REQUIRED_MODULE_FILES if not (MODULES_DIR / name).is_file()
        )
        if missing_required_files:
            required_files_status = "error"
            message = "File obbligatori mancanti in modules: " + ", ".join(
                missing_required_files
            )
            logging.error(
                "Required module files missing",
                extra={
                    "event": "required_modules_missing",
                    "path": str(MODULES_DIR),
                    "missing_files": missing_required_files,
                },
            )
            errors.append(message)
    else:
        required_files_status = "error"
        missing_required_files = sorted(REQUIRED_MODULE_FILES)

    diagnostic = {
        "status": "ok" if not errors else "error",
        "directories": directories,
        "required_module_files": {
            "status": required_files_status,
            "missing": missing_required_files,
            "path": str(MODULES_DIR),
        },
    }

    if errors:
        _dir_validation_error = "; ".join(errors)
        diagnostic["errors"] = errors
        if raise_on_error:
            raise RuntimeError(_dir_validation_error)
    else:
        _dir_validation_error = None

    return diagnostic


@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        return response
    except HTTPException as exc:
        status_code = exc.status_code
        raise
    except Exception:
        status_code = 500
        raise
    finally:
        endpoint = getattr(request.scope.get("route"), "path", request.url.path)
        status_class = f"{int(status_code) // 100}xx" if status_code else "unknown"
        REQUEST_COUNT.labels(
            endpoint=endpoint, method=request.method, status_class=status_class
        ).inc()
        if status_code >= 400:
            ERROR_COUNT.labels(
                endpoint=endpoint, method=request.method, status_class=status_class
            ).inc()


@app.get("/modules", response_model=List[Dict])
async def list_modules(_: None = Depends(require_api_key)) -> List[Dict]:
    """Return the list of available module files (txt/md/json)."""
    return _list_files(MODULES_DIR)


@app.get("/modules/{name:path}/meta")
async def get_module_meta(name: str, _: None = Depends(require_api_key)) -> Dict:
    """Return metadata (no content) for a module file."""
    name_path = Path(name)
    path = (MODULES_DIR / name_path).resolve()
    if not path.is_relative_to(MODULES_DIR):
        raise HTTPException(status_code=400, detail="Invalid module path")
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Module not found")

    metadata = {
        "name": path.name,
        "size_bytes": path.stat().st_size,
        "suffix": path.suffix,
    }

    metadata.update(_parse_module_metadata(path))

    return metadata


@app.get("/modules/taverna_saves/meta")
async def get_taverna_saves_meta(
    _: None = Depends(require_api_key),
) -> Dict[str, object]:
    """Expose metadata and quota information for the taverna_saves service directory."""

    meta = _taverna_saves_metadata(TAVERNA_SAVES_DIR)
    meta["storage_policy"] = {
        "file_naming": "{name}.json",
        "auto_name_pattern": meta.get("auto_name_policy", {}).get("pattern"),
        "on_overflow": meta.get("auto_name_policy", {}).get("on_overflow"),
    }
    return meta


@app.get("/modules/taverna_saves/quota")
async def get_taverna_saves_quota(
    _: None = Depends(require_api_key),
) -> Dict[str, object]:
    """Return a focused view on taverna_saves quota/usage metrics."""

    return _taverna_saves_metrics(TAVERNA_SAVES_DIR)


@app.get("/taverna_storage_meta")
async def taverna_storage_meta(_: None = Depends(require_api_key)) -> Dict[str, object]:
    """Expose taverna_saves metadata with quota, max_files and auto-naming policy."""

    return _taverna_saves_metadata(TAVERNA_SAVES_DIR)


@app.get("/storage_meta")
async def storage_meta(_: None = Depends(require_api_key)) -> Dict[str, object]:
    """Alias legacy per /taverna_storage_meta."""

    return await taverna_storage_meta(_)


TEXT_SUFFIXES = {".txt", ".md"}
PROTECTED_DUMP_MODULES = {"ruling_expert.txt"}


def _media_type_for_path(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".txt":
        return "text/plain"
    if suffix == ".md":
        return "text/markdown"
    return "text/plain"


@app.post("/build/stub")
async def build_stub(
    mode: str = Query(default="extended"),
    class_name: str | None = Query(default=None, alias="class"),
    race: str | None = Query(default=None),
    archetype: str | None = Query(default=None),
    level: int | None = Query(default=None),
    body: Dict | None = Body(default=None),
    _: None = Depends(require_api_key),
):
    """Return a deterministic minmax builder stub payload."""
    try:
        payload = build_stub_payload(
            class_name=class_name,
            race=race,
            archetype=archetype,
            level=level,
            mode=mode,
            body=body,
        )
    except StubBuilderError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    response_payload = {
        key: value
        for key, value in payload.items()
        if key not in {"catalog_manifest", "reference_catalog_version"}
    }
    return JSONResponse(response_payload)


@app.post("/pc/build")
async def pc_build(
    draft: Dict = Body(...),
    _: None = Depends(require_api_key),
):
    """Costruzione deterministica di un PG lv1 dai cataloghi OGL (nessun LLM)."""
    from .pc.engine import build_character
    from .pc.models import CharacterDraft

    try:
        sheet = build_character(CharacterDraft.from_dict(draft))
    except (KeyError, TypeError, AttributeError) as exc:
        raise HTTPException(status_code=400, detail=f"draft malformato: {exc}") from exc
    if sheet["errors"]:
        raise HTTPException(status_code=422, detail=sheet["errors"])
    return sheet


@app.get("/modules/{name:path}")
@app.post("/modules/{name:path}")
async def get_module_content(
    name: str,
    mode: str = Query(default="extended"),
    class_name: str | None = Query(default=None, alias="class"),
    race: str | None = Query(default=None),
    archetype: str | None = Query(default=None),
    level: int | None = Query(default=None),
    stub: bool = Query(
        default=False, description="Return stub payload for minmax builder"
    ),
    body: Dict | None = Body(default=None),
    _: None = Depends(require_api_key),
):
    """Return the raw text content of a module file or a stubbed builder payload.

    Example names:
    - base_profile.txt
    - Taverna_NPC.txt
    - minmax_builder.txt
    """
    name_path = Path(name)

    stub_requested = (
        stub
        or str(mode or "").lower() == "stub"
        or str((body or {}).get("mode", "")).lower() == "stub"
    )

    # Special-case the builder endpoint only when an explicit stub is requested
    if name_path.name == "minmax_builder.txt" and stub_requested:
        try:
            payload = build_stub_payload(
                class_name=class_name,
                race=race,
                archetype=archetype,
                level=level,
                mode=mode,
                body=body,
            )
        except StubBuilderError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

        response_payload = {
            key: value
            for key, value in payload.items()
            if key not in {"catalog_manifest", "reference_catalog_version"}
        }
        return JSONResponse(response_payload)

    path = (MODULES_DIR / name_path).resolve()
    if not path.is_relative_to(MODULES_DIR):
        raise HTTPException(status_code=400, detail="Invalid module path")
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Module not found")
    media_type = _media_type_for_path(path)
    is_text = path.suffix.lower() in TEXT_SUFFIXES

    allow_full_dump = settings.allow_module_dump and (
        path.name not in PROTECTED_DUMP_MODULES
        or path.name in settings.module_dump_whitelist
    )

    # I file non testuali richiedono ALLOW_MODULE_DUMP=true (e non protetti) per
    # essere scaricati; i moduli testuali vengono sempre serviti, al piu' troncati.
    if not is_text and not allow_full_dump:
        raise HTTPException(status_code=403, detail="Module download not allowed")

    if allow_full_dump:
        return FileResponse(path, media_type=media_type, filename=path.name)

    max_chars = 4000

    total_size = path.stat().st_size
    with path.open("r", encoding="utf-8", errors="ignore") as source:
        chunk = source.read(max_chars + 1)

    served_chunk = chunk[:max_chars]
    is_truncated = len(chunk) > max_chars
    truncated_size = len(served_chunk.encode("utf-8", errors="ignore"))
    remaining = max(total_size - truncated_size, 0)
    original_length = total_size

    def _truncated_text():
        if served_chunk:
            yield served_chunk
        yield (
            "\n\n[contenuto troncato — restano circa "
            f"{remaining} byte su {total_size}; x-truncated=true; "
            f"original-length={original_length}]"
        )

    headers = {
        "X-Content-Partial": "true",
        "X-Content-Partial-Reason": "ALLOW_MODULE_DUMP=false",
        "X-Content-Served-Bytes": str(truncated_size),
        "X-Content-Total-Bytes": str(total_size),
        "X-Content-Remaining-Bytes": str(remaining),
        "X-Content-Truncated": str(is_truncated).lower(),
        "X-Content-Original-Length": str(total_size),
        "X-Truncated": str(is_truncated).lower(),
        "X-Original-Length": str(original_length),
        "Warning": '199 - "Contenuto parziale: ALLOW_MODULE_DUMP=false"',
    }

    if is_truncated:
        headers["X-Truncation-Limit-Chars"] = str(max_chars)
        headers["X-Truncated"] = "true"
        headers["x-truncated"] = "true"
        headers["x-original-length"] = str(original_length)

    return StreamingResponse(
        _truncated_text(),
        media_type=media_type,
        headers=headers,
        status_code=206,
    )


@router.get("/knowledge", response_model=List[Dict])
async def list_knowledge(_: None = Depends(require_api_key)) -> List[Dict]:
    """List knowledge PDFs/MD available in /data."""
    return _list_files(DATA_DIR)


@router.get("/knowledge/{name:path}/meta")
async def get_knowledge_meta(name: str, _: None = Depends(require_api_key)) -> Dict:
    """Return metadata for a knowledge file (PDF/MD)."""
    name_path = Path(name)
    path = (DATA_DIR / name_path).resolve()
    if not path.is_relative_to(DATA_DIR):
        raise HTTPException(status_code=400, detail="Invalid knowledge path")
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Knowledge file not found")
    return {
        "name": path.name,
        "size_bytes": path.stat().st_size,
        "suffix": path.suffix,
    }


@router.post("/ruling-expert")
async def ruling_expert_stub(_: None = Depends(require_api_key)) -> Dict[str, object]:
    """Stub di Ruling Expert: restituisce sempre badge validato."""

    return {"ruling_badge": "validated", "sources": ["stub"], "violations": []}


@router.get("/metrics")
async def metrics(_: None = Depends(require_metrics_access)) -> Response:
    """Espone le metriche Prometheus protette da API key o allowlist IP."""

    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

app.include_router(router)
app.include_router(rag_router)
