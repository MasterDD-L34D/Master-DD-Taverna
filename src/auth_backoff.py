import logging
from ipaddress import ip_address
from time import monotonic
from typing import Dict

from fastapi import Header, HTTPException, Request

from .config import settings

_failed_attempts: Dict[str, Dict[str, float | int]] = {}


def reset_failed_attempts() -> None:
    _failed_attempts.clear()


def _cleanup_failed_attempts(now: float) -> None:
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


def _evict_failed_attempts_if_needed(current_client_id: str) -> None:
    max_clients = settings.auth_backoff_max_clients
    if max_clients <= 0:
        _failed_attempts.clear()
        return

    while len(_failed_attempts) >= max_clients and current_client_id not in _failed_attempts:
        client_id_to_evict = min(
            _failed_attempts.items(), key=lambda item: float(item[1].get("last_seen", 0.0))
        )[0]
        _failed_attempts.pop(client_id_to_evict, None)


def _record_failed_attempt(client_id: str, *, count: int, blocked_until: float, now: float) -> None:
    if client_id not in _failed_attempts:
        _evict_failed_attempts_if_needed(client_id)

    _failed_attempts[client_id] = {
        "count": count,
        "blocked_until": blocked_until,
        "last_seen": now,
    }


def _is_trusted_proxy(request: Request) -> bool:
    if not settings.trust_proxy_headers:
        return False
    if not request.client or not request.client.host:
        return False
    return request.client.host in settings.trusted_proxy_ips


def _extract_first_valid_ip(value: str) -> str | None:
    for candidate in value.split(","):
        ip_candidate = candidate.strip()
        if not ip_candidate:
            continue
        try:
            return str(ip_address(ip_candidate))
        except ValueError:
            continue
    return None


def _forwarded_for_client_ip(request: Request) -> str | None:
    if not _is_trusted_proxy(request):
        return None
    forwarded_for = request.headers.get("x-forwarded-for")
    if not forwarded_for:
        return None
    return _extract_first_valid_ip(forwarded_for)


def _client_identifier(request: Request) -> str:
    if request.client and request.client.host:
        return _forwarded_for_client_ip(request) or request.client.host
    return "unknown"


def _retry_after_for_active_backoff(client_id: str, now: float) -> int | None:
    attempt_state = _failed_attempts.get(client_id, {"count": 0, "blocked_until": 0.0, "last_seen": now})
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


def _accepted_metrics_keys() -> set[str]:
    return {k for k in (settings.metrics_api_key, settings.api_key) if k}


def _is_metrics_ip_allowed(request: Request) -> bool:
    if not settings.metrics_ip_allowlist:
        return False
    if request.client and request.client.host in settings.metrics_ip_allowlist:
        return True
    forwarded_for = _forwarded_for_client_ip(request)
    if forwarded_for and forwarded_for in settings.metrics_ip_allowlist:
        return True
    return False



_SENSITIVE_HEADER_NAMES = {
    "authorization",
    "cookie",
    "set-cookie",
    "x-api-key",
}


def _redact_header_value(header_name: str, header_value: str) -> str:
    if header_name in _SENSITIVE_HEADER_NAMES:
        return "***REDACTED***"
    normalized = header_value.strip()
    if not normalized:
        return normalized
    if len(normalized) <= 8:
        return "***"
    return f"{normalized[:4]}...{normalized[-2:]}"


def _redacted_request_headers(request: Request) -> Dict[str, str]:
    redacted_headers: Dict[str, str] = {}
    for header_name, header_value in request.headers.items():
        normalized_name = header_name.lower()
        redacted_headers[normalized_name] = _redact_header_value(normalized_name, header_value)
    return redacted_headers


async def require_api_key(request: Request, x_api_key: str | None = Header(default=None, alias="x-api-key")) -> None:
    client_id = _client_identifier(request)
    now = monotonic()
    _cleanup_failed_attempts(now)
    attempt_state = _failed_attempts.get(client_id, {"count": 0, "blocked_until": 0.0, "last_seen": now})
    retry_after = _retry_after_for_active_backoff(client_id, now)
    if retry_after is not None:
        logging.warning("Authentication backoff active", extra={"event": "auth_backoff_active", "client_ip": client_id, "retry_after": retry_after})
        raise HTTPException(
            status_code=429,
            detail="Troppi tentativi non autorizzati, riprova più tardi",
            headers={"Retry-After": str(retry_after)},
        )

    if settings.allow_anonymous:
        _failed_attempts.pop(client_id, None)
        return

    if settings.api_key is None:
        raise HTTPException(
            status_code=401,
            detail="API key non configurata. Imposta API_KEY oppure abilita ALLOW_ANONYMOUS=true",
        )

    if x_api_key != settings.api_key:
        updated_count = int(attempt_state.get("count", 0)) + 1
        blocked_until = float(attempt_state.get("blocked_until", 0.0))

        if updated_count >= settings.auth_backoff_threshold:
            blocked_until = now + settings.auth_backoff_seconds
            logging.warning("Authentication backoff triggered", extra={"event": "auth_backoff_triggered", "client_ip": client_id, "fail_count": updated_count, "retry_after": settings.auth_backoff_seconds})
            _record_failed_attempt(client_id, count=updated_count, blocked_until=blocked_until, now=now)
            raise HTTPException(
                status_code=429,
                detail="Troppi tentativi non autorizzati, riprova più tardi",
                headers={"Retry-After": str(settings.auth_backoff_seconds)},
            )

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
        _record_failed_attempt(client_id, count=updated_count, blocked_until=blocked_until, now=now)
        raise HTTPException(status_code=401, detail="Invalid or missing API key")

    _failed_attempts.pop(client_id, None)


async def require_metrics_access(request: Request, x_api_key: str | None = Header(default=None, alias="x-api-key")) -> None:
    provided_key = x_api_key or ""
    accepted_keys = _accepted_metrics_keys()
    if accepted_keys and provided_key in accepted_keys:
        return
    if _is_metrics_ip_allowed(request):
        return
    raise HTTPException(status_code=403, detail="Accesso alle metriche non autorizzato")
