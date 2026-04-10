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
from .storage_helpers import list_files as _list_files, taverna_saves_metadata as _taverna_saves_metadata, taverna_saves_metrics as _taverna_saves_metrics
from tools.generate_build_db import schema_for_mode, validate_with_schema


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
    title="Pathfinder 1E Master DD Core API",
    version="1.0.0",
    description="API minimale per esporre i moduli del kernel Master DD a un GPT tramite Actions.",
    lifespan=lifespan,
)


_legacy_failed_attempts: Dict[str, Dict[str, float | int]] = {}


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
]


TAVERNA_SAVES_DIR = MODULES_DIR / "taverna_saves"
TAVERNA_SAVES_MAX_FILES = 200


def _legacy_reset_failed_attempts() -> None:
    """Utility to clear the in-memory tracker (mainly for tests)."""

    _failed_attempts.clear()


def _legacy_cleanup_failed_attempts(now: float) -> None:
    """Remove stale backoff entries older than configured TTL."""

    ttl_seconds = settings.auth_backoff_state_ttl_seconds
    if ttl_seconds <= 0:
        return

    expired_clients = [
        client_id
        for client_id, state in _failed_attempts.items()
        if now - float(state.get("last_seen", 0.0)) > ttl_seconds
    ]
    for client_id in expired_clients:
        _failed_attempts.pop(client_id, None)


def _legacy_evict_failed_attempts_if_needed(current_client_id: str) -> None:
    """Ensure the tracker never grows beyond AUTH_BACKOFF_MAX_CLIENTS."""

    max_clients = settings.auth_backoff_max_clients
    if max_clients <= 0:
        _failed_attempts.clear()
        return

    while (
        len(_failed_attempts) >= max_clients
        and current_client_id not in _failed_attempts
    ):
        client_id_to_evict = min(
            _failed_attempts.items(),
            key=lambda item: float(item[1].get("last_seen", 0.0)),
        )[0]
        _failed_attempts.pop(client_id_to_evict, None)


def _legacy_record_failed_attempt(
    client_id: str, *, count: int, blocked_until: float, now: float
) -> None:
    if client_id not in _failed_attempts:
        _evict_failed_attempts_if_needed(client_id)

    _failed_attempts[client_id] = {
        "count": count,
        "blocked_until": blocked_until,
        "last_seen": now,
    }


def _legacy_load_reference_manifest() -> Mapping[str, object]:
    try:
        manifest = json.loads(REFERENCE_MANIFEST_PATH.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - safety net for missing fixtures
        logging.error("Impossibile leggere il manifest di riferimento: %s", exc)
        return {}

    return manifest if isinstance(manifest, Mapping) else {}


def _legacy_reference_catalog_version() -> str | None:
    manifest = _load_reference_manifest()
    version = manifest.get("version") if isinstance(manifest, Mapping) else None
    return str(version) if version else None


def _legacy_client_identifier(request: Request) -> str:
    if request.client and request.client.host:
        return _forwarded_for_client_ip(request) or request.client.host
    return "unknown"


def _legacy_is_trusted_proxy(request: Request) -> bool:
    if not settings.trust_proxy_headers:
        return False
    if not request.client or not request.client.host:
        return False
    return request.client.host in settings.trusted_proxy_ips


def _legacy_extract_first_valid_ip(value: str) -> str | None:
    for candidate in value.split(","):
        ip_candidate = candidate.strip()
        if not ip_candidate:
            continue
        try:
            return str(ip_address(ip_candidate))
        except ValueError:
            continue
    return None


def _legacy_forwarded_for_client_ip(request: Request) -> str | None:
    if not _is_trusted_proxy(request):
        return None
    forwarded_for = request.headers.get("x-forwarded-for")
    if not forwarded_for:
        return None
    return _extract_first_valid_ip(forwarded_for)


def _legacy_retry_after_for_active_backoff(client_id: str, now: float) -> int | None:
    attempt_state = _failed_attempts.get(
        client_id, {"count": 0, "blocked_until": 0.0, "last_seen": now}
    )
    blocked_until = float(attempt_state.get("blocked_until", 0.0))
    if now >= blocked_until:
        return None

    _record_failed_attempt(
        client_id,
        count=int(attempt_state.get("count", 0)),
        blocked_until=blocked_until,
        now=now,
    )
    return max(int(blocked_until - now), 0)


def _legacy_raise_backoff_active(client_id: str, retry_after: int) -> None:
    logging.warning(
        "Authentication backoff active",
        extra={
            "event": "auth_backoff_active",
            "client_ip": client_id,
            "retry_after": retry_after,
        },
    )
    raise HTTPException(
        status_code=429,
        detail="Troppi tentativi non autorizzati, riprova più tardi",
        headers={"Retry-After": str(retry_after)},
    )


def _legacy_raise_auth_backoff_triggered(
    client_id: str, now: float, updated_count: int
) -> None:
    blocked_until = now + settings.auth_backoff_seconds
    logging.warning(
        "Authentication backoff triggered",
        extra={
            "event": "auth_backoff_triggered",
            "client_ip": client_id,
            "fail_count": updated_count,
            "retry_after": settings.auth_backoff_seconds,
        },
    )
    AUTH_BACKOFF_TRIGGER.inc()
    _record_failed_attempt(
        client_id,
        count=updated_count,
        blocked_until=blocked_until,
        now=now,
    )
    raise HTTPException(
        status_code=429,
        detail="Troppi tentativi non autorizzati, riprova più tardi",
        headers={"Retry-After": str(settings.auth_backoff_seconds)},
    )


def _legacy_accepted_metrics_keys() -> set[str]:
    return {k for k in (settings.metrics_api_key, settings.api_key) if k}


_SENSITIVE_HEADER_NAMES = {
    "authorization",
    "cookie",
    "set-cookie",
    "x-api-key",
}


def _legacy_redact_header_value(header_name: str, header_value: str) -> str:
    if header_name in _SENSITIVE_HEADER_NAMES:
        return "***REDACTED***"

    normalized = header_value.strip()
    if not normalized:
        return normalized

    if len(normalized) <= 8:
        return "***"

    return f"{normalized[:4]}...{normalized[-2:]}"


def _legacy_redacted_request_headers(request: Request) -> Dict[str, str]:
    redacted_headers: Dict[str, str] = {}
    for header_name, header_value in request.headers.items():
        normalized_name = header_name.lower()
        redacted_headers[normalized_name] = _redact_header_value(
            normalized_name, header_value
        )
    return redacted_headers


async def _legacyrequire_api_key(
    request: Request, x_api_key: str | None = Header(default=None, alias="x-api-key")
) -> None:
    """Validate the provided API key header against settings and apply backoff."""

    client_id = _client_identifier(request)
    now = monotonic()
    _cleanup_failed_attempts(now)
    attempt_state = _failed_attempts.get(
        client_id, {"count": 0, "blocked_until": 0.0, "last_seen": now}
    )
    retry_after = _retry_after_for_active_backoff(client_id, now)
    if retry_after is not None:
        _raise_backoff_active(client_id, retry_after)

    if settings.allow_anonymous:
        _failed_attempts.pop(client_id, None)
        return

    if settings.api_key is None:
        raise HTTPException(
            status_code=401,
            detail=(
                "API key non configurata. Imposta API_KEY oppure abilita ALLOW_ANONYMOUS=true"
            ),
        )

    if x_api_key != settings.api_key:
        updated_count = int(attempt_state.get("count", 0)) + 1
        route = request.url.path if request.url else "unknown"
        user_agent = request.headers.get("user-agent", "")
        logging.warning(
            "Authentication failed",
            extra={
                "event": "auth_failed",
                "client_ip": client_id,
                "fail_count": updated_count,
                "route": route,
                "user_agent": _redact_header_value("user-agent", user_agent),
                "headers": _redacted_request_headers(request),
            },
        )
        blocked_until = attempt_state.get("blocked_until", 0.0)
        if updated_count >= settings.auth_backoff_threshold:
            _raise_auth_backoff_triggered(client_id, now, updated_count)

        _record_failed_attempt(
            client_id,
            count=updated_count,
            blocked_until=float(blocked_until),
            now=now,
        )
        raise HTTPException(status_code=401, detail="Invalid or missing API key")

    _failed_attempts.pop(client_id, None)


def _legacy_is_metrics_ip_allowed(request: Request) -> bool:
    if not settings.metrics_ip_allowlist:
        return False
    if request.client and request.client.host in settings.metrics_ip_allowlist:
        return True
    forwarded_for = _forwarded_for_client_ip(request)
    if forwarded_for and forwarded_for in settings.metrics_ip_allowlist:
        return True
    return False


async def _legacyrequire_metrics_access(
    request: Request, x_api_key: str | None = Header(default=None, alias="x-api-key")
) -> None:
    """Restrict access to the metrics endpoint via API key or IP allowlist."""

    provided_key = x_api_key or ""
    accepted_keys = _accepted_metrics_keys()
    if accepted_keys and provided_key in accepted_keys:
        return
    if _is_metrics_ip_allowed(request):
        return
    raise HTTPException(status_code=403, detail="Accesso alle metriche non autorizzato")


def _legacy_list_files(base: Path) -> List[Dict]:
    out: List[Dict] = []
    if not base.exists() or not base.is_dir():
        raise HTTPException(
            status_code=503,
            detail=f"Directory di configurazione non trovata: {base}",
        )
    for p in sorted(base.iterdir()):
        if p.is_file():
            out.append(
                {
                    "name": p.name,
                    "size_bytes": p.stat().st_size,
                    "suffix": p.suffix,
                }
            )
    return out


def _legacy_parse_json_module_metadata(
    text: str, *, source: Path | None = None
) -> Dict[str, object]:
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        logging.warning(
            "Impossibile analizzare il modulo JSON",
            extra={"path": str(source or "<inline>")},
        )
        return {}

    if not isinstance(parsed, Mapping):
        return {}

    metadata: Dict[str, object] = {}
    candidates: List[Mapping] = [parsed]
    meta_block = parsed.get("meta")
    if isinstance(meta_block, Mapping):
        candidates.append(meta_block)

    for block in candidates:
        version = block.get("version")
        if version is not None and "version" not in metadata:
            metadata["version"] = version

        compatibility = block.get("compatibility")
        if compatibility is not None and "compatibility" not in metadata:
            metadata["compatibility"] = compatibility

    return metadata


def _legacy_taverna_saves_metrics() -> Dict[str, object]:
    if not TAVERNA_SAVES_DIR.exists() or not TAVERNA_SAVES_DIR.is_dir():
        raise HTTPException(
            status_code=503,
            detail=f"Directory taverna_saves non trovata: {TAVERNA_SAVES_DIR}",
        )

    files = [p for p in TAVERNA_SAVES_DIR.iterdir() if p.is_file()]
    file_count = len(files)
    total_size = sum(p.stat().st_size for p in files)
    disk_usage = shutil.disk_usage(TAVERNA_SAVES_DIR)

    return {
        "path": str(TAVERNA_SAVES_DIR),
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


def _legacy_taverna_saves_metadata() -> Dict[str, object]:
    metrics = _taverna_saves_metrics()

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
            "remediation": {
                "echo_gate": "Echo gate <8.5 blocca export/salvataggi: ripeti /grade finché lo score non supera la soglia, applica /refine_npc e in sandbox puoi disattivare temporaneamente con /echo off.",
                "qa_check": "QA CHECK bloccante: esegui /self_check (o la routine QA CHECK/repair), poi se Echo resta sotto soglia ripeti /grade e riprova /save_hub o l'export verso taverna_saves.",
            },
        }
    )

    return metrics


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


def _legacy_parse_front_matter_metadata(
    text: str, *, source: Path | None = None
) -> Dict[str, object]:
    """Extract `version` and `compatibility` from YAML-like headers."""

    metadata: Dict[str, object] = {}
    version_match = re.search(
        r"^version:\s*\"?(?P<version>[^\n#]+)\"?\s*$", text, re.MULTILINE
    )
    if version_match:
        metadata["version"] = version_match.group("version").strip().strip('"')

    lines = text.splitlines()
    for idx, line in enumerate(lines):
        if not line.startswith("compatibility:"):
            continue

        inline_value = line.partition(":")[2].strip()
        if inline_value:
            metadata["compatibility"] = inline_value.strip(' "')
            break

        block_lines: List[str] = []
        for block_line in lines[idx + 1 :]:
            if block_line.startswith((" ", "\t")):
                block_lines.append(block_line)
            else:
                break

        if block_lines:
            snippet = "compatibility:\n" + "\n".join(block_lines)
            try:
                parsed = yaml.safe_load(snippet)
                compatibility = (
                    parsed.get("compatibility") if isinstance(parsed, dict) else None
                )
                if compatibility is not None:
                    metadata["compatibility"] = compatibility
            except yaml.YAMLError:
                logging.warning(
                    "Impossibile analizzare il blocco compatibility",
                    extra={"path": str(source or "<inline>")},
                )
        break

    return metadata


def _legacy_parse_knowledge_pack_metadata(text: str) -> Dict[str, str]:
    match = re.search(
        r"\*\*Versione:\*\*\s*(?P<version>[^•\n]+).*?\*\*Compatibilit\u00e0:\*\*\s*(?P<compatibility>[^\n<]+)",
        text,
    )

    if not match:
        return {}

    return {
        "version": match.group("version").strip(),
        "compatibility": match.group("compatibility").strip(),
    }


def _legacy_parse_module_metadata(path: Path) -> Dict[str, object]:
    """Extract optional metadata fields from a module file."""

    text = path.read_text(encoding="utf-8", errors="ignore")
    metadata: Dict[str, object] = {}

    if path.suffix.lower() == ".json":
        metadata.update(_parse_json_module_metadata(text, source=path))
        return metadata

    metadata.update(_parse_front_matter_metadata(text, source=path))

    if path.name == "knowledge_pack.md":
        metadata.update(_parse_knowledge_pack_metadata(text))

    return metadata


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


@app.get("/storage_meta")
async def storage_meta(_: None = Depends(require_api_key)) -> Dict[str, object]:
    """Expose storage metadata with quota, max_files and auto-naming policy."""

    return _taverna_saves_metadata(TAVERNA_SAVES_DIR)


TEXT_SUFFIXES = {".txt", ".md"}
PROTECTED_DUMP_MODULES = {"ruling_expert.txt"}
STRICT_TRUNCATION_MODULES = {"adventurer_ledger.txt", "narrative_flow.txt"}
LEDGER_TEXT_MODULES = {"adventurer_ledger.txt"}


def _media_type_for_path(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".txt":
        return "text/plain"
    if suffix == ".md":
        return "text/markdown"
    return "text/plain"


@app.api_route("/modules/{name:path}", methods=["GET", "POST"])
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
        resolved_race = race or (body or {}).get("race") or "Human"
        resolved_archetype = (
            archetype
            or (body or {}).get("archetype")
            or (body or {}).get("model")
            or "Base"
        )

        builder_mode = (
            (body or {}).get("builder_mode") or (body or {}).get("mode") or mode
        )
        normalized_mode = (
            "core" if str(builder_mode or "").lower().startswith("core") else "extended"
        )
        step_total = 8 if normalized_mode == "core" else 16
        resolved_level = int((body or {}).get("level") or level or 1)
        step_labels = {
            "1": "Profilo Base",
            "2": "Razza & Classe",
            "3": "Archetipi & Multiclasse",
            "4": "Feats & Talenti",
            "5": "Spell & Power Set",
            "6": "Equip & Risorse",
            "7": "Benchmark & Simulazioni",
            "8": "QA & Export",
        }
        if normalized_mode == "extended":
            step_labels.update(
                {
                    "9": "Dummies Sheet",
                    "10": "Esportazione",
                    "11": "Fork/Varianti",
                    "12": "Comparativa",
                    "13": "Meta Rating",
                    "14": "Companion",
                    "15": "Report",
                    "16": "Chiusura",
                }
            )

        base_build_state = {
            "class": class_name or "Unknown",
            "mode": normalized_mode,
            "race": resolved_race,
            "archetype": resolved_archetype,
            "step": 1,
            "step_total": step_total,
            "step_labels": step_labels,
        }

        benchmark = {
            "meta_tier": "T3",
            "ruling_badge": "validated",
            "dpr_snapshot": {
                "livello_1": {"media": 6, "picco": 9},
                "livello_5": {"media": 18, "picco": 26},
            },
        }

        is_wizard_evoker = (
            str(class_name or "").lower() == "wizard"
            and str(resolved_archetype or "").lower() == "evoker"
        )

        wizard_progression_plan: list[dict[str, object]] = [
            {
                "livello": 1,
                "talenti": ["Iniziativa migliorata"],
                "slot": "1°: 4",
                "equip": ["Bastone ferrato", "Spellbook", "Abito da viaggiatore"],
                "pf": 12,
                "salvezze": {"Tempra": 2, "Riflessi": 3, "Volontà": 4},
                "skills": {
                    "Conoscenze (arcana)": 6,
                    "Sapienza Magica": 6,
                    "Percezione": 5,
                },
                "ca": {
                    "totale": 15,
                    "armatura": 3,
                    "destrezza": 2,
                    "deflessione": 0,
                    "misc": 0,
                },
                "privilegi": [
                    "Legame arcano (famiglio)",
                    "Scuola di Invocazione — Intensified Spells",
                    "PF 12 | TS +2/+3/+4 | CA 15",
                    "Slot 1°:4 | Equip: bastone ferrato, spellbook, abito da viaggiatore",
                ],
            },
            {
                "livello": 2,
                "talenti": ["Metamagia (Incantesimi Estesi)"],
                "slot": "1°: 5 / 2°: 2",
                "equip": ["Pagina di pergamena", "Mantello resistente +1"],
                "pf": 20,
                "salvezze": {"Tempra": 3, "Riflessi": 4, "Volontà": 5},
                "skills": {
                    "Conoscenze (arcana)": 7,
                    "Sapienza Magica": 7,
                    "Percezione": 6,
                },
                "ca": {
                    "totale": 15,
                    "armatura": 3,
                    "destrezza": 2,
                    "deflessione": 0,
                    "misc": 0,
                },
                "privilegi": [
                    "Potere di scuola (Evoker's Admixture)",
                    "PF 20 | TS +3/+4/+5 | CA 15",
                    "Slot 1°:5 / 2°:2 | Equip: pergamene aggiuntive, mantello resistente +1",
                ],
            },
            {
                "livello": 3,
                "talenti": ["Incantesimi focalizzati (Invocazione)"],
                "slot": "1°: 6 / 2°: 4 / 3°: 2",
                "equip": ["Bacchetta di dardo incantato (CL3)"],
                "pf": 28,
                "salvezze": {"Tempra": 3, "Riflessi": 4, "Volontà": 6},
                "skills": {
                    "Conoscenze (arcana)": 9,
                    "Sapienza Magica": 9,
                    "Percezione": 6,
                },
                "ca": {
                    "totale": 16,
                    "armatura": 3,
                    "destrezza": 2,
                    "deflessione": 1,
                    "misc": 0,
                },
                "privilegi": [
                    "Talento bonus del mago",
                    "PF 28 | TS +3/+4/+6 | CA 16",
                    "Slot 1°:6 / 2°:4 / 3°:2 | Equip: bacchetta di dardo incantato (CL3)",
                ],
            },
            {
                "livello": 4,
                "talenti": ["Magia focalizzata superiore (Invocazione)"],
                "slot": "1°: 6 / 2°: 5 / 3°: 4",
                "equip": ["Veste da mago rinforzata"],
                "pf": 36,
                "salvezze": {"Tempra": 4, "Riflessi": 5, "Volontà": 7},
                "skills": {
                    "Conoscenze (arcana)": 10,
                    "Sapienza Magica": 10,
                    "Percezione": 7,
                },
                "ca": {
                    "totale": 16,
                    "armatura": 3,
                    "destrezza": 2,
                    "deflessione": 1,
                    "misc": 0,
                },
                "privilegi": [
                    "Scoperta arcana: specializzazione intensificata",
                    "PF 36 | TS +4/+5/+7 | CA 16",
                    "Slot 1°:6 / 2°:5 / 3°:4 | Equip: veste da mago rinforzata",
                ],
            },
            {
                "livello": 5,
                "talenti": ["Incantesimi massimizzati (metamagia)"],
                "slot": "1°: 7 / 2°: 6 / 3°: 5 / 4°: 3",
                "equip": ["Perla di potere I", "Anello di protezione +1"],
                "pf": 44,
                "salvezze": {"Tempra": 4, "Riflessi": 5, "Volontà": 8},
                "skills": {
                    "Conoscenze (arcana)": 12,
                    "Sapienza Magica": 12,
                    "Percezione": 8,
                },
                "ca": {
                    "totale": 17,
                    "armatura": 3,
                    "destrezza": 2,
                    "deflessione": 1,
                    "misc": 1,
                },
                "privilegi": [
                    "Scuola di opposizione consolidata",
                    "PF 44 | TS +4/+5/+8 | CA 17",
                    "Slot 1°:7 / 2°:6 / 3°:5 / 4°:3 | Equip: perla di potere I, anello di protezione +1",
                ],
            },
            {
                "livello": 6,
                "talenti": ["Talento bonus (Mago) — Incantesimi rapidi"],
                "slot": "1°: 7 / 2°: 6 / 3°: 6 / 4°: 4",
                "equip": ["Bacchetta di palla di fuoco (CL6)"],
                "pf": 52,
                "salvezze": {"Tempra": 5, "Riflessi": 6, "Volontà": 9},
                "skills": {
                    "Conoscenze (arcana)": 13,
                    "Sapienza Magica": 13,
                    "Percezione": 9,
                },
                "ca": {
                    "totale": 17,
                    "armatura": 3,
                    "destrezza": 2,
                    "deflessione": 1,
                    "misc": 1,
                },
                "privilegi": [
                    "Potere di scuola avanzato (Force Missile)",
                    "PF 52 | TS +5/+6/+9 | CA 17",
                    "Slot 1°:7 / 2°:6 / 3°:6 / 4°:4 | Equip: bacchetta di palla di fuoco (CL6)",
                ],
            },
            {
                "livello": 7,
                "talenti": [
                    "Incantesimi focalizzati superiori (Invocazione)",
                    "Talento bonus (Difensivo)",
                ],
                "slot": "1°: 8 / 2°: 7 / 3°: 7 / 4°: 5 / 5°: 3",
                "equip": ["Cintura della destrezza +2"],
                "pf": 60,
                "salvezze": {"Tempra": 5, "Riflessi": 6, "Volontà": 10},
                "skills": {
                    "Conoscenze (arcana)": 14,
                    "Sapienza Magica": 14,
                    "Percezione": 9,
                },
                "ca": {
                    "totale": 18,
                    "armatura": 3,
                    "destrezza": 3,
                    "deflessione": 1,
                    "misc": 1,
                },
                "privilegi": [
                    "Talento bonus del mago (difesa arcana)",
                    "PF 60 | TS +5/+6/+10 | CA 18",
                    "Slot 1°:8 / 2°:7 / 3°:7 / 4°:5 / 5°:3 | Equip: cintura della destrezza +2",
                ],
            },
            {
                "livello": 8,
                "talenti": ["Penetrare resistenza magica"],
                "slot": "1°: 8 / 2°: 7 / 3°: 7 / 4°: 6 / 5°: 4",
                "equip": ["Pergamena di muro di forza"],
                "pf": 68,
                "salvezze": {"Tempra": 6, "Riflessi": 7, "Volontà": 11},
                "skills": {
                    "Conoscenze (arcana)": 15,
                    "Sapienza Magica": 15,
                    "Percezione": 10,
                },
                "ca": {
                    "totale": 18,
                    "armatura": 3,
                    "destrezza": 3,
                    "deflessione": 1,
                    "misc": 1,
                },
                "privilegi": [
                    "Ricerca superiore (arcane discovery)",
                    "PF 68 | TS +6/+7/+11 | CA 18",
                    "Slot 1°:8 / 2°:7 / 3°:7 / 4°:6 / 5°:4 | Equip: pergamena di muro di forza",
                ],
            },
            {
                "livello": 9,
                "talenti": ["Incantesimi rapidi migliorati"],
                "slot": "1°: 8 / 2°: 7 / 3°: 7 / 4°: 7 / 5°: 5",
                "equip": ["Bacchetta di fulmine (CL9)"],
                "pf": 76,
                "salvezze": {"Tempra": 6, "Riflessi": 7, "Volontà": 12},
                "skills": {
                    "Conoscenze (arcana)": 17,
                    "Sapienza Magica": 17,
                    "Percezione": 10,
                },
                "ca": {
                    "totale": 19,
                    "armatura": 3,
                    "destrezza": 3,
                    "deflessione": 2,
                    "misc": 1,
                },
                "privilegi": [
                    "Talento bonus (metamagia di scuola)",
                    "PF 76 | TS +6/+7/+12 | CA 19",
                    "Slot 1°:8 / 2°:7 / 3°:7 / 4°:7 / 5°:5 | Equip: bacchetta di fulmine (CL9)",
                ],
            },
            {
                "livello": 10,
                "talenti": [
                    "Incantesimi potenziati (metamagia)",
                    "Penetrare resistenza magica migliorato",
                ],
                "slot": "1°: 8 / 2°: 7 / 3°: 7 / 4°: 7 / 5°: 6",
                "equip": ["Testa di bacco runica", "Perla di potere IV"],
                "pf": 84,
                "salvezze": {"Tempra": 7, "Riflessi": 8, "Volontà": 13},
                "skills": {
                    "Conoscenze (arcana)": 18,
                    "Sapienza Magica": 18,
                    "Percezione": 11,
                },
                "ca": {
                    "totale": 20,
                    "armatura": 3,
                    "destrezza": 3,
                    "deflessione": 2,
                    "misc": 2,
                },
                "privilegi": [
                    "Potere di scuola maggiore (elemental mastery)",
                    "PF 84 | TS +7/+8/+13 | CA 20",
                    "Slot 1°:8 / 2°:7 / 3°:7 / 4°:7 / 5°:6 | Equip: perla di potere IV, focus arcani runici",
                ],
            },
        ]

        is_cutpurse = (
            str(class_name or "").lower() == "rogue"
            and str(resolved_archetype or "").lower() == "cutpurse"
        )

        cutpurse_progression_plan: list[dict[str, object]] = [
            {
                "livello": 1,
                "stats": {
                    "FOR": 12,
                    "DES": 18,
                    "COS": 12,
                    "INT": 14,
                    "SAG": 10,
                    "CAR": 8,
                },
                "talenti": ["Arma accurata"],
                "pf": 11,
                "attacco": "+6 (pugnale) / +5 (fionda)",
                "danni": "1d4+2 (pugnale) / 1d3+2 (fionda)",
                "salvezze": {"Tempra": 2, "Riflessi": 4, "Volontà": 1},
                "skills": {
                    "Furtività": 9,
                    "Rapidità di mano": 9,
                    "Percezione": 6,
                    "Acrobazia": 8,
                    "Disattivare Congegni": 9,
                },
                "ca": {"totale": 18, "armatura": 3, "destrezza": 4, "misc": 1},
                "equip": [
                    "Armatura di cuoio borchiato",
                    "Pugnale bilanciato",
                    "Fionda con 20 proiettili",
                    "Attrezzi da scasso di qualità",
                ],
                "privilegi": [
                    "Attacco furtivo +1d6",
                    "Percepire trappole +1",
                    "Cutpurse: Mano lesta (Pickpocket)",
                    "PF 11 | TS +2/+4/+1 | CA 18",
                ],
            },
            {
                "livello": 2,
                "talenti": ["Schivare prodigioso"],
                "pf": 18,
                "attacco": "+7 (pugnale)",
                "danni": "1d4+2 (pugnale) +1d6 furtivo",
                "salvezze": {"Tempra": 3, "Riflessi": 5, "Volontà": 1},
                "skills": {
                    "Furtività": 10,
                    "Rapidità di mano": 10,
                    "Percezione": 7,
                    "Acrobazia": 9,
                    "Disattivare Congegni": 10,
                },
                "ca": {"totale": 19, "armatura": 3, "destrezza": 4, "misc": 2},
                "equip": ["Cappa elfica grigia", "Mantello della resistenza +1"],
                "privilegi": [
                    "Talento ladresco: Furtività rapida",
                    "Cutpurse: Afferrare oggetti (Quick Steal)",
                    "PF 18 | TS +3/+5/+1 | CA 19",
                ],
            },
            {
                "livello": 3,
                "talenti": ["Schivare"],
                "pf": 26,
                "attacco": "+8 (pugnale)",
                "danni": "1d4+3 (pugnale) +2d6 furtivo",
                "salvezze": {"Tempra": 3, "Riflessi": 6, "Volontà": 2},
                "skills": {
                    "Furtività": 11,
                    "Rapidità di mano": 11,
                    "Percezione": 8,
                    "Acrobazia": 10,
                    "Intimidire": 5,
                },
                "ca": {
                    "totale": 19,
                    "armatura": 3,
                    "destrezza": 4,
                    "schivare": 1,
                    "misc": 1,
                },
                "equip": ["Pugnale masterwork", "Anello di protezione +1"],
                "privilegi": [
                    "Attacco furtivo +2d6",
                    "Scherma agile (Finesse Training)",
                    "PF 26 | TS +3/+6/+2 | CA 19",
                ],
            },
            {
                "livello": 4,
                "talenti": ["Arma focalizzata (pugnale)"],
                "pf": 34,
                "attacco": "+10 (pugnale)",
                "danni": "1d4+4 (pugnale) +2d6 furtivo",
                "salvezze": {"Tempra": 4, "Riflessi": 7, "Volontà": 2},
                "skills": {
                    "Furtività": 12,
                    "Rapidità di mano": 12,
                    "Percezione": 9,
                    "Acrobazia": 11,
                    "Diplomazia": 5,
                },
                "ca": {
                    "totale": 20,
                    "armatura": 4,
                    "destrezza": 4,
                    "schivare": 1,
                    "misc": 1,
                },
                "equip": ["Giaco di maglia ombreggiato", "Guanti da ladro"],
                "privilegi": [
                    "Talento ladresco: Arma improvvisata",
                    "Uncanny Dodge",
                    "PF 34 | TS +4/+7/+2 | CA 20",
                ],
            },
            {
                "livello": 5,
                "talenti": ["Combattere con due armi"],
                "pf": 42,
                "attacco": "+11/+11 (pugnali)",
                "danni": "1d4+4 (pugnale) +3d6 furtivo",
                "salvezze": {"Tempra": 4, "Riflessi": 8, "Volontà": 3},
                "skills": {
                    "Furtività": 13,
                    "Rapidità di mano": 13,
                    "Percezione": 10,
                    "Acrobazia": 12,
                    "Disattivare Congegni": 13,
                },
                "ca": {
                    "totale": 21,
                    "armatura": 4,
                    "destrezza": 4,
                    "schivare": 1,
                    "misc": 2,
                },
                "equip": ["Pugnale +1", "Cintura dell'agilità +2"],
                "privilegi": [
                    "Attacco furtivo +3d6",
                    "Talento ladresco: Attacco debilitante",
                    "PF 42 | TS +4/+8/+3 | CA 21",
                ],
            },
            {
                "livello": 6,
                "talenti": ["Riflessi in combattimento"],
                "pf": 50,
                "attacco": "+13/+13 (pugnali)",
                "danni": "1d4+5 (pugnale) +3d6 furtivo",
                "salvezze": {"Tempra": 5, "Riflessi": 9, "Volontà": 3},
                "skills": {
                    "Furtività": 14,
                    "Rapidità di mano": 14,
                    "Percezione": 11,
                    "Acrobazia": 13,
                    "Raggirare": 9,
                },
                "ca": {
                    "totale": 22,
                    "armatura": 4,
                    "destrezza": 5,
                    "schivare": 1,
                    "misc": 2,
                },
                "equip": ["Stivali dell'agilità", "Mantello della resistenza +2"],
                "privilegi": [
                    "Talento ladresco: Furtività leggendaria",
                    "Evasione migliorata",
                    "PF 50 | TS +5/+9/+3 | CA 22",
                ],
            },
            {
                "livello": 7,
                "talenti": ["Mobilità"],
                "pf": 58,
                "attacco": "+15/+15 (pugnali)",
                "danni": "1d4+6 (pugnale) +4d6 furtivo",
                "salvezze": {"Tempra": 5, "Riflessi": 10, "Volontà": 4},
                "skills": {
                    "Furtività": 15,
                    "Rapidità di mano": 15,
                    "Percezione": 12,
                    "Acrobazia": 14,
                    "Disattivare Congegni": 15,
                },
                "ca": {
                    "totale": 23,
                    "armatura": 5,
                    "destrezza": 5,
                    "schivare": 1,
                    "misc": 2,
                },
                "equip": ["Pugnale +2 bilanciato", "Bracciali dell'armatura +1"],
                "privilegi": [
                    "Attacco furtivo +4d6",
                    "Cutpurse: Ruba arma (Steal Weapon)",
                    "PF 58 | TS +5/+10/+4 | CA 23",
                ],
            },
            {
                "livello": 8,
                "stats": {
                    "FOR": 12,
                    "DES": 20,
                    "COS": 12,
                    "INT": 14,
                    "SAG": 10,
                    "CAR": 8,
                },
                "talenti": [
                    "Arma focalizzata superiore (pugnale)",
                    "Talento ladresco: Opportunista",
                ],
                "pf": 66,
                "attacco": "+17/+17 (pugnali)",
                "danni": "1d4+6 (pugnale) +4d6 furtivo",
                "salvezze": {"Tempra": 6, "Riflessi": 11, "Volontà": 4},
                "skills": {
                    "Furtività": 17,
                    "Rapidità di mano": 17,
                    "Percezione": 13,
                    "Acrobazia": 15,
                    "Intuizione": 11,
                },
                "ca": {
                    "totale": 24,
                    "armatura": 5,
                    "destrezza": 6,
                    "schivare": 1,
                    "misc": 2,
                },
                "equip": ["Cintura dell'agilità +4", "Pugnale agile +2"],
                "privilegi": [
                    "Schivare prodigioso migliorato",
                    "Attacco furtivo +4d6",
                    "PF 66 | TS +6/+11/+4 | CA 24",
                ],
            },
            {
                "livello": 9,
                "talenti": ["Arma accurata superiore"],
                "pf": 74,
                "attacco": "+19/+19 (pugnali)",
                "danni": "1d4+7 (pugnale) +5d6 furtivo",
                "salvezze": {"Tempra": 6, "Riflessi": 12, "Volontà": 5},
                "skills": {
                    "Furtività": 18,
                    "Rapidità di mano": 18,
                    "Percezione": 14,
                    "Acrobazia": 16,
                    "Diplomazia": 8,
                },
                "ca": {
                    "totale": 25,
                    "armatura": 5,
                    "destrezza": 6,
                    "schivare": 1,
                    "misc": 3,
                },
                "equip": ["Pugnale velocità +2", "Anello di protezione +2"],
                "privilegi": [
                    "Attacco furtivo +5d6",
                    "Talento ladresco: Debilitare difese",
                    "PF 74 | TS +6/+12/+5 | CA 25",
                ],
            },
            {
                "livello": 10,
                "talenti": ["Colpo senz'armi migliorato"],
                "pf": 82,
                "attacco": "+21/+21 (pugnali)",
                "danni": "1d4+8 (pugnale) +5d6 furtivo",
                "salvezze": {"Tempra": 7, "Riflessi": 13, "Volontà": 5},
                "skills": {
                    "Furtività": 19,
                    "Rapidità di mano": 19,
                    "Percezione": 15,
                    "Acrobazia": 17,
                    "Disattivare Congegni": 19,
                },
                "ca": {
                    "totale": 26,
                    "armatura": 6,
                    "destrezza": 6,
                    "schivare": 1,
                    "misc": 3,
                },
                "equip": [
                    "Giaco di maglia ombreggiato +2",
                    "Guanti della destrezza +4",
                ],
                "privilegi": [
                    "Attacco furtivo +5d6",
                    "Talento ladresco: Bleeding Attack",
                    "Cutpurse: Maestro borseggiatore",
                    "PF 82 | TS +7/+13/+5 | CA 26",
                ],
            },
        ]

        progression: list[dict[str, object]] = []
        base_hp = 12 + 5 * max(resolved_level - 1, 0)

        wizard_levels = (
            [
                entry
                for entry in wizard_progression_plan
                if entry["livello"] <= resolved_level
            ]
            if is_wizard_evoker
            else []
        )
        wizard_snapshot = wizard_levels[-1] if wizard_levels else None

        cutpurse_levels = (
            [
                entry
                for entry in cutpurse_progression_plan
                if entry["livello"] <= resolved_level
            ]
            if is_cutpurse
            else []
        )
        cutpurse_snapshot = cutpurse_levels[-1] if cutpurse_levels else None

        if is_wizard_evoker:
            for entry in wizard_levels:
                progression.append(
                    {
                        "livello": entry["livello"],
                        "privilegi": entry["privilegi"],
                        "talenti": entry["talenti"],
                    }
                )
            if progression:
                base_hp = (
                    wizard_snapshot.get("pf", base_hp) if wizard_snapshot else base_hp
                )
        elif is_cutpurse:
            for entry in cutpurse_levels:
                progression.append(
                    {
                        "livello": entry["livello"],
                        "privilegi": entry.get("privilegi", []),
                        "talenti": entry.get("talenti", []),
                    }
                )
            if progression and cutpurse_snapshot:
                base_hp = cutpurse_snapshot.get("pf", base_hp)
        else:
            for lvl in range(1, resolved_level + 1):
                progression.append(
                    {
                        "livello": lvl,
                        "privilegi": [
                            f"Privilegio {lvl}",
                            (
                                f"Tecnica distintiva {resolved_archetype}"
                                if resolved_archetype
                                else "Tecnica distintiva"
                            ),
                        ],
                        "talenti": [f"Talento di livello {lvl}"],
                    }
                )

        hp_progression: list[object] = []
        if is_wizard_evoker:
            hp_progression = [entry.get("pf", base_hp) for entry in wizard_levels]
        elif is_cutpurse:
            hp_progression = [entry.get("pf", base_hp) for entry in cutpurse_levels]
        if not hp_progression:
            hp_progression = [base_hp]

        snapshot = wizard_snapshot or cutpurse_snapshot
        saves_block = (
            snapshot.get("salvezze")
            if snapshot
            else {"Tempra": 4, "Riflessi": 3, "Volontà": 4}
        )
        skills_map = (
            {
                name: {"totale": value}
                for name, value in (snapshot.get("skills") if snapshot else {}).items()
            }
            if snapshot
            else {
                "Percezione": {"totale": 5},
                "Acrobazia": {"totale": 4},
                "Conoscenze": {"totale": 3},
            }
        )
        slot_text = (
            snapshot.get("slot")
            if snapshot and not is_cutpurse
            else ("Non incantatore" if is_cutpurse else "Liv1:4/Liv2:3")
        )
        spell_levels: list[dict[str, object]] = []
        slot_pattern = re.compile(
            r"(\d+)\s*(?:[°º]|lvl|liv(?:ello)?|level)?\s*[:=]?\s*(\d+)"
        )
        for level_str, per_day_str in slot_pattern.findall(slot_text or ""):
            try:
                level = int(level_str)
                per_day = int(per_day_str)
            except ValueError:
                continue
            if level <= 0:
                continue
            spell_levels.append({"liv": level, "per_day": per_day})
        ac_block = (
            snapshot.get("ca")
            if snapshot
            else {"totale": 18, "armatura": 5, "destrezza": 2, "scudo": 1}
        )
        if isinstance(ac_block, Mapping) and "scudo" not in ac_block:
            ac_block = {**ac_block, "scudo": 0}
        equip_full = []
        if wizard_levels:
            for entry in wizard_levels:
                equip_full.extend(entry.get("equip", []))
        elif cutpurse_levels:
            for entry in cutpurse_levels:
                equip_full.extend(entry.get("equip", []))
        else:
            equip_full.extend(["Arma preferita", "Armatura leggera"])
        inventory_full = ["Kit da avventuriero", "Pozione di cura x2"]
        talents_full: list[str] = []
        if wizard_levels:
            for entry in wizard_levels:
                talents_full.extend(entry.get("talenti", []))
        elif cutpurse_levels:
            for entry in cutpurse_levels:
                talents_full.extend(entry.get("talenti", []))
        else:
            talents_full.extend(["Colpo possente", "Iniziativa migliorata"])
        class_features: list[str] = []
        if wizard_levels:
            for entry in wizard_levels:
                class_features.extend(entry.get("privilegi", []))
        elif cutpurse_levels:
            for entry in cutpurse_levels:
                class_features.extend(entry.get("privilegi", []))
        else:
            class_features.extend(["Addestramento marziale", "Specializzazione"])

        base_cutpurse_stats = None
        if is_cutpurse:
            for entry in cutpurse_progression_plan:
                stats_candidate = entry.get("stats")
                if isinstance(stats_candidate, Mapping):
                    base_cutpurse_stats = stats_candidate
                    break
        stats_block = (
            snapshot.get("stats")
            if snapshot and isinstance(snapshot.get("stats"), Mapping)
            else (
                base_cutpurse_stats
                if base_cutpurse_stats is not None
                else {
                    "FOR": 16,
                    "DES": 14,
                    "COS": 14,
                    "INT": 10,
                    "SAG": 12,
                    "CAR": 8,
                }
            )
        )
        attack_text = snapshot.get("attacco") if snapshot else "+4"
        damage_text = snapshot.get("danni") if snapshot else "1d8+3"
        initiative_bonus = 4 if is_cutpurse else 2
        speed_value = 6 if is_cutpurse else 9
        skill_points = max(5 * resolved_level, 4 * resolved_level)
        if is_cutpurse:
            int_mod = (
                int((stats_block.get("INT") or 10) - 10) // 2
                if isinstance(stats_block.get("INT"), (int, float))
                else 0
            )
            skill_points = (8 + max(int_mod, 0)) * resolved_level

        sheet_payload = {
            "classi": [
                {
                    "nome": class_name or "Unknown",
                    "livelli": resolved_level,
                    "archetipi": [resolved_archetype] if resolved_archetype else [],
                }
            ],
            "statistiche": stats_block,
            "statistiche_chiave": {
                "attacco": attack_text,
                "danni": damage_text,
                "ca": (
                    ac_block.get("totale", 17) if isinstance(ac_block, Mapping) else 17
                ),
            },
            "pf_totali": base_hp,
            "hp": {"totali": base_hp, "per_livello": hp_progression},
            "salvezze": saves_block,
            "skills_map": skills_map,
            "skill_points": skill_points,
            "talenti": sorted(set(talents_full)),
            "capacita_classe": sorted(set(class_features)),
            "equipaggiamento": sorted(set(equip_full)),
            "inventario": sorted(set(inventory_full + equip_full)),
            "spell_levels": spell_levels,
            "slot_incantesimi": slot_text,
            "ac_breakdown": (
                ac_block
                if isinstance(ac_block, Mapping)
                else {"totale": 18, "armatura": 5, "destrezza": 2, "scudo": 1}
            ),
            "iniziativa": initiative_bonus,
            "velocita": speed_value,
            "progressione": progression,
            "benchmarks": {"meta_tier": "T3"},
            "hooks": (body or {}).get("hooks"),
        }

        export_block = {"sheet_payload": sheet_payload}

        base_build_state["statistics"] = sheet_payload["statistiche"]
        benchmark["statistics"] = sheet_payload["statistiche_chiave"]

        narrative = (
            f"{resolved_race or 'Avventuriero'} {resolved_archetype or 'Base'} pronta/o per il campo, "
            f"specializzata/o in tattiche da {class_name or 'classe'}."
        )
        ledger = {
            "movimenti": [
                {"voce": "Equipaggiamento iniziale", "importo": -150},
                {"voce": "Ricompensa missione", "importo": 250},
            ],
            "currency": {"oro": 100, "argento": 25, "rame": 40},
        }

        catalog_manifest = _load_reference_manifest()
        catalog_version = (
            str(catalog_manifest.get("version"))
            if isinstance(catalog_manifest, Mapping)
            else None
        )
        if not catalog_version:
            raise HTTPException(
                status_code=503,
                detail="Reference catalog manifest non disponibile",
            )

        payload: Dict = {
            "build_state": base_build_state,
            "benchmark": benchmark,
            "export": export_block,
            "narrative": narrative,
            "sheet": sheet_payload,
            "ledger": ledger,
            "class": class_name,
            "mode": normalized_mode,
            "reference_catalog_version": catalog_version,
            "catalog_manifest": catalog_manifest,
        }

        payload["composite"] = {
            "build": {
                "build_state": payload["build_state"],
                "benchmark": payload["benchmark"],
                "export": payload["export"],
                "sheet_payload": sheet_payload,
                "reference_catalog_version": catalog_version,
            },
            "narrative": narrative,
            "sheet": payload["sheet"],
            "sheet_payload": sheet_payload,
            "ledger": ledger,
        }

        schema_filename = schema_for_mode(normalized_mode)
        try:
            validate_with_schema(
                schema_filename,
                payload,
                "minmax_builder_stub",
                strict=True,
            )
        except ValidationError as exc:
            raise HTTPException(
                status_code=500,
                detail=f"Stub payload non valido per {schema_filename}: {exc}",
            ) from exc

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
    is_ledger_text = path.name in LEDGER_TEXT_MODULES

    allow_full_dump = settings.allow_module_dump and (
        path.name not in PROTECTED_DUMP_MODULES
        or path.name in settings.module_dump_whitelist
    )

    if (not is_text or is_ledger_text) and not allow_full_dump:
        raise HTTPException(status_code=403, detail="Module download not allowed")

    if not is_text and allow_full_dump:
        return FileResponse(path, media_type=media_type, filename=path.name)

    if allow_full_dump:
        return FileResponse(path, media_type=media_type, filename=path.name)

    max_chars = 4000

    total_size = path.stat().st_size
    strict_truncation = (not settings.allow_module_dump) or (
        path.name in STRICT_TRUNCATION_MODULES
    )

    if strict_truncation:
        served_chunk = ""
        is_truncated = True
        truncated_size = 0
    else:
        with path.open("r", encoding="utf-8", errors="ignore") as source:
            chunk = source.read(max_chars + 1)

        served_chunk = chunk[:max_chars]
        # Anche con ALLOW_MODULE_DUMP=false serviamo un estratto iniziale, mantenendo
        # l'header di parzialità per indicare il troncamento forzato.
        is_truncated = (not settings.allow_module_dump) or len(chunk) > max_chars
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
