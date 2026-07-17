import asyncio
import json
import logging
import re
from pathlib import Path
from urllib.parse import quote

import pytest
import httpx
from fastapi.testclient import TestClient
from prometheus_client import CONTENT_TYPE_LATEST

import sys

sys.path.append(str(Path(__file__).resolve().parent.parent))

import src.app as app_module
import src.auth_backoff as auth_backoff_module
from src.app import REQUIRED_MODULE_FILES, app
from src.config import MODULES_DIR, DATA_DIR, settings
from src.utils.module_resolver import resolve_module_uri
from tools.generate_build_db import schema_for_mode, validate_with_schema


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def disable_module_dump():
    original = settings.allow_module_dump
    settings.allow_module_dump = False
    yield
    settings.allow_module_dump = original


@pytest.fixture
def enable_module_dump():
    original = settings.allow_module_dump
    settings.allow_module_dump = True
    yield
    settings.allow_module_dump = original


@pytest.fixture
def missing_modules_dir(monkeypatch, tmp_path):
    missing_dir = tmp_path / "missing_modules"
    monkeypatch.setattr(app_module, "MODULES_DIR", missing_dir)
    return missing_dir


@pytest.fixture
def missing_data_dir(monkeypatch, tmp_path):
    missing_dir = tmp_path / "missing_data"
    monkeypatch.setattr(app_module, "DATA_DIR", missing_dir)
    return missing_dir


@pytest.fixture
def data_dir_file(monkeypatch, tmp_path):
    data_file = tmp_path / "data_file"
    data_file.write_text("not a directory")
    monkeypatch.setattr(app_module, "DATA_DIR", data_file)
    return data_file


@pytest.fixture
def temp_data_dir(monkeypatch, tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setattr(app_module, "DATA_DIR", data_dir)
    return data_dir


@pytest.fixture
def allow_missing_directories(monkeypatch):
    def fake_validate(raise_on_error: bool = False):
        directories = {}
        errors = []
        for label, path in ("modules", app_module.MODULES_DIR), (
            "data",
            app_module.DATA_DIR,
        ):
            is_valid = path.exists() and path.is_dir()
            message = None
            if not is_valid:
                message = f"Directory {label} mancante o non accessibile: {path}"
                errors.append(message)
            directories[label] = {
                "status": "ok" if is_valid else "error",
                "path": str(path),
                "message": message,
            }

        diagnostic = {
            "status": "ok" if not errors else "error",
            "directories": directories,
        }
        if errors:
            diagnostic["errors"] = errors

        app_module._dir_validation_error = "; ".join(errors) if errors else None
        return diagnostic

    monkeypatch.setattr(app_module, "_validate_directories", fake_validate)
    return fake_validate


@pytest.fixture(autouse=True)
def reset_backoff_state():
    app_module._reset_failed_attempts()
    yield
    app_module._reset_failed_attempts()


@pytest.fixture(autouse=True)
def setup_api_key():
    original = settings.api_key
    original_allow_anonymous = settings.allow_anonymous
    original_trust_proxy_headers = settings.trust_proxy_headers
    original_trusted_proxy_ips = list(settings.trusted_proxy_ips)
    settings.api_key = "test-api-key"
    settings.allow_anonymous = False
    settings.trust_proxy_headers = False
    settings.trusted_proxy_ips = []
    yield
    settings.api_key = original
    settings.allow_anonymous = original_allow_anonymous
    settings.trust_proxy_headers = original_trust_proxy_headers
    settings.trusted_proxy_ips = original_trusted_proxy_ips


@pytest.fixture
def short_backoff(monkeypatch):
    original_threshold = settings.auth_backoff_threshold
    original_seconds = settings.auth_backoff_seconds
    settings.auth_backoff_threshold = 2
    settings.auth_backoff_seconds = 30
    yield
    settings.auth_backoff_threshold = original_threshold
    settings.auth_backoff_seconds = original_seconds


@pytest.fixture
def backoff_tracker_limits():
    original_ttl = settings.auth_backoff_state_ttl_seconds
    original_max_clients = settings.auth_backoff_max_clients
    settings.auth_backoff_state_ttl_seconds = 3600
    settings.auth_backoff_max_clients = 10000
    yield
    settings.auth_backoff_state_ttl_seconds = original_ttl
    settings.auth_backoff_max_clients = original_max_clients


@pytest.fixture
def auth_headers():
    return {"x-api-key": "test-api-key"}


@pytest.fixture
def metrics_security_settings():
    original_metrics_key = settings.metrics_api_key
    original_allowlist = list(settings.metrics_ip_allowlist)
    yield
    settings.metrics_api_key = original_metrics_key
    settings.metrics_ip_allowlist = original_allowlist


@pytest.fixture
async def allowlisted_http_client():
    transport = httpx.ASGITransport(app=app, client=("203.0.113.5", 8000))
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as http_client:
        yield http_client


def test_get_module_content_valid_file(client, auth_headers):
    response = client.get("/modules/base_profile.txt", headers=auth_headers)
    assert response.status_code == 206
    assert response.headers["X-Content-Partial"] == "true"
    assert "[contenuto troncato" in response.text


def test_get_module_content_sets_text_content_type(client, auth_headers):
    response = client.get("/modules/base_profile.txt", headers=auth_headers)
    assert response.status_code == 206
    assert response.headers["content-type"].startswith("text/plain")


def test_minmax_builder_returns_file_content_by_default(client, auth_headers):
    response = client.get("/modules/minmax_builder.txt", headers=auth_headers)
    assert response.status_code == 206
    assert response.headers["content-type"].startswith("text/plain")
    assert "[contenuto troncato" in response.text
    served = int(response.headers["X-Content-Served-Bytes"])
    assert 0 < served <= 4200


def test_minmax_builder_stub_is_opt_in(client, auth_headers):
    response = client.get("/modules/minmax_builder.txt?mode=stub", headers=auth_headers)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    payload = response.json()
    assert payload["build_state"]["mode"] in {"core", "extended"}
    assert payload["sheet"]["classi"][0]["nome"] == "Unknown"


def test_minmax_builder_stub_contains_full_payload(client, auth_headers):
    response = client.get("/modules/minmax_builder.txt?mode=stub", headers=auth_headers)
    assert response.status_code == 200
    payload = response.json()

    expected_keys = {
        "build_state",
        "benchmark",
        "export",
        "narrative",
        "sheet",
        "ledger",
        "class",
        "mode",
        "composite",
    }
    assert set(payload.keys()) == expected_keys
    assert "sheet_payload" in payload["export"]
    assert payload["ledger"]["currency"]["oro"] >= 0
    assert payload["composite"]["build"]["export"]["sheet_payload"]


def test_minmax_builder_stub_payload_matches_schema(client, auth_headers):
    response = client.get("/modules/minmax_builder.txt?mode=stub", headers=auth_headers)
    assert response.status_code == 200
    payload = response.json()

    schema_filename = schema_for_mode(payload.get("mode", ""))
    validate_with_schema(
        schema_filename,
        payload,
        "test_minmax_builder_stub",
        strict=True,
    )


def test_build_stub_endpoint_returns_json(client, auth_headers):
    response = client.post("/build/stub", headers=auth_headers)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    payload = response.json()
    assert payload["build_state"]["mode"] in {"core", "extended"}
    assert payload["sheet"]["classi"][0]["nome"] == "Unknown"


def test_build_stub_endpoint_with_params(client, auth_headers):
    response = client.post(
        "/build/stub?class=wizard&race=Elf&archetype=evoker&level=5&mode=extended",
        headers=auth_headers,
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["class"] == "wizard"
    assert payload["build_state"]["race"] == "Elf"
    assert payload["build_state"]["archetype"] == "evoker"
    assert payload["build_state"]["step_total"] == 16


def test_build_stub_endpoint_payload_matches_schema(client, auth_headers):
    response = client.post(
        "/build/stub?class=rogue&archetype=cutpurse&level=3",
        headers=auth_headers,
    )
    assert response.status_code == 200
    payload = response.json()

    schema_filename = schema_for_mode(payload.get("mode", ""))
    validate_with_schema(
        schema_filename,
        payload,
        "test_build_stub_endpoint",
        strict=True,
    )


def test_get_module_content_path_traversal(client, auth_headers):
    response = client.get(
        f"/modules/{quote('../config.py', safe='')}", headers=auth_headers
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid module path"


def test_get_module_content_path_traversal_double_back(client, auth_headers):
    traversal = quote("nested/../../secret.txt", safe="")

    response = client.get(f"/modules/{traversal}", headers=auth_headers)

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid module path"


def test_runtime_preload_guard_present():
    content = (MODULES_DIR / "base_profile.txt").read_text(encoding="utf-8")

    assert "flag: runtime.preload_done" in content
    assert "set: [runtime.preload_done: true]" in content


def test_get_module_content_not_found(client, auth_headers):
    response = client.get("/modules/missing_module.txt", headers=auth_headers)
    assert response.status_code == 404
    assert response.json()["detail"] == "Module not found"


def test_get_module_content_binary_streamed_without_text_property(
    client, auth_headers, enable_module_dump
):
    binary_path = MODULES_DIR / "binary_test.bin"
    binary_path.write_bytes(b"\x00\x01" * 2048)

    try:
        with client.stream(
            "GET", "/modules/binary_test.bin", headers=auth_headers
        ) as response:
            assert response.status_code == 200
            assert response.headers["content-type"].startswith("text/plain")
            assert response.is_stream_consumed is False
    finally:
        binary_path.unlink(missing_ok=True)


def test_allow_module_dump_disabled_by_default():
    assert settings.allow_module_dump is False


def test_get_module_content_binary_blocked_when_dump_disabled(
    client, auth_headers, disable_module_dump
):
    binary_path = MODULES_DIR / "binary_blocked.bin"
    binary_path.write_bytes(b"binary-content")

    try:
        response = client.get("/modules/binary_blocked.bin", headers=auth_headers)
        assert response.status_code == 403
        payload = response.json()
        assert payload["detail"] == "Module download not allowed"
        assert "contenuto troncato" not in response.text
    finally:
        binary_path.unlink(missing_ok=True)


def test_get_module_content_pdf_blocked_when_dump_disabled(
    client, auth_headers, disable_module_dump
):
    pdf_path = MODULES_DIR / "blocked_module.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 dummy content")

    try:
        response = client.get("/modules/blocked_module.pdf", headers=auth_headers)
        assert response.status_code == 403
        assert response.json()["detail"] == "Module download not allowed"
    finally:
        pdf_path.unlink(missing_ok=True)


def test_text_module_truncated_when_dump_disabled(
    client, auth_headers, disable_module_dump
):
    large_module = MODULES_DIR / "large_module.txt"
    large_module.write_text("A" * 5001)

    try:
        response = client.get("/modules/large_module.txt", headers=auth_headers)
        assert response.status_code == 206
        assert response.headers["content-type"].startswith("text/plain")
        assert response.headers["X-Content-Truncated"] == "true"
        assert response.headers["X-Content-Original-Length"] == "5001"
        assert response.headers["X-Truncation-Limit-Chars"] == "4000"
        assert "[contenuto troncato" in response.text
        assert "x-truncated=true" in response.text
        served = int(response.headers["X-Content-Served-Bytes"])
        assert 0 < served <= 4000
    finally:
        large_module.unlink(missing_ok=True)


def test_narrative_flow_exposes_truncation_headers(
    client, auth_headers, disable_module_dump
):
    target = MODULES_DIR / "narrative_flow.txt"
    original = target.read_text(encoding="utf-8")
    padded = original + ("\n" + ("B" * 4100))
    target.write_text(padded, encoding="utf-8")
    expected_length = target.stat().st_size

    try:
        response = client.get("/modules/narrative_flow.txt", headers=auth_headers)
        assert response.status_code == 206
        truncation_header = response.headers["x-truncated"]
        assert "true" in {value.strip() for value in truncation_header.split(",")}
        length_header_values = {
            value.strip() for value in response.headers["x-original-length"].split(",")
        }
        assert str(expected_length) in length_header_values
        served = int(response.headers["X-Content-Served-Bytes"])
        assert 0 < served <= 4200
        assert "[contenuto troncato" in response.text
        assert original.splitlines()[0] in response.text
    finally:
        target.write_text(original, encoding="utf-8")


def test_ruling_expert_truncated_when_dump_enabled_without_whitelist(
    client, auth_headers
):
    original_allow = settings.allow_module_dump
    original_whitelist = settings.module_dump_whitelist
    settings.allow_module_dump = True
    settings.module_dump_whitelist = set()

    try:
        total_size = (MODULES_DIR / "ruling_expert.txt").stat().st_size
        response = client.get("/modules/ruling_expert.txt", headers=auth_headers)
        assert response.status_code == 206
        assert response.headers["X-Content-Partial"] == "true"
        assert response.headers["X-Content-Partial-Reason"] == "ALLOW_MODULE_DUMP=false"
        served_bytes = int(response.headers["X-Content-Served-Bytes"])
        remaining_bytes = int(response.headers["X-Content-Remaining-Bytes"])
        assert served_bytes <= total_size
        assert served_bytes + remaining_bytes == total_size
        assert response.headers["X-Content-Truncated"] == "true"
        assert response.headers["X-Truncation-Limit-Chars"] == "4000"
        assert "[contenuto troncato" in response.text
    finally:
        settings.allow_module_dump = original_allow
        settings.module_dump_whitelist = original_whitelist


def test_adventurer_ledger_truncated_when_dump_disabled(
    client, auth_headers, disable_module_dump
):
    target = MODULES_DIR / "adventurer_ledger.txt"
    expected_header = target.read_text(encoding="utf-8").splitlines()[0]

    response = client.get("/modules/adventurer_ledger.txt", headers=auth_headers)

    assert response.status_code == 206
    assert response.headers["X-Content-Partial"] == "true"
    assert expected_header in response.text
    served = int(response.headers["X-Content-Served-Bytes"])
    assert 0 < served <= 4200


def test_ruling_expert_full_dump_requires_whitelist(client, auth_headers):
    original_allow = settings.allow_module_dump
    original_whitelist = settings.module_dump_whitelist
    settings.allow_module_dump = True
    settings.module_dump_whitelist = {"ruling_expert.txt"}

    try:
        expected = (MODULES_DIR / "ruling_expert.txt").read_text(encoding="utf-8")
        response = client.get("/modules/ruling_expert.txt", headers=auth_headers)
        assert response.status_code == 200
        # FileResponse preserves raw line endings, while read_text() applies
        # universal newline translation on Windows. Normalize both sides.
        assert response.text.replace("\r\n", "\n") == expected.replace("\r\n", "\n")
    finally:
        settings.allow_module_dump = original_allow
        settings.module_dump_whitelist = original_whitelist


def test_get_module_meta_valid_file(client, auth_headers):
    sample_file = next(p for p in MODULES_DIR.iterdir() if p.is_file())
    response = client.get(
        f"/modules/{quote(sample_file.name)}/meta", headers=auth_headers
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["name"] == sample_file.name
    assert payload["size_bytes"] == sample_file.stat().st_size
    assert payload["suffix"] == sample_file.suffix


def test_get_knowledge_pack_meta_includes_version_and_compatibility(
    client, auth_headers
):
    sample_file = MODULES_DIR / "knowledge_pack.md"
    response = client.get(
        f"/modules/{quote(sample_file.name)}/meta", headers=auth_headers
    )

    assert response.status_code == 200
    payload = response.json()

    match = re.search(
        r"\*\*Versione:\*\*\s*(?P<version>[^•\n]+).*?\*\*Compatibilit\u00e0:\*\*\s*(?P<compatibility>[^\n<]+)",
        sample_file.read_text(encoding="utf-8"),
    )

    assert payload["version"] == match.group("version").strip()
    assert payload["compatibility"] == match.group("compatibility").strip()


def test_get_module_meta_includes_front_matter_fields(client, auth_headers):
    sample_file = MODULES_DIR / "ruling_expert.txt"
    response = client.get(
        f"/modules/{quote(sample_file.name)}/meta", headers=auth_headers
    )

    assert response.status_code == 200
    payload = response.json()

    expected = app_module._parse_front_matter_metadata(
        sample_file.read_text(encoding="utf-8"), source=sample_file
    )

    assert payload["version"] == expected["version"]
    assert payload["compatibility"] == expected["compatibility"]


def test_get_module_meta_reads_json_metadata(client, auth_headers):
    sample_file = MODULES_DIR / "tavern_hub.json"
    parsed = json.loads(sample_file.read_text(encoding="utf-8"))
    response = client.get(
        f"/modules/{quote(sample_file.name)}/meta", headers=auth_headers
    )

    assert response.status_code == 200
    payload = response.json()

    meta_block = parsed.get("meta", {}) if isinstance(parsed, dict) else {}
    expected_version = meta_block.get("version") or parsed.get("version")
    expected_compatibility = meta_block.get("compatibility") or parsed.get(
        "compatibility"
    )

    assert payload.get("version") == expected_version
    if expected_compatibility is not None:
        assert payload["compatibility"] == expected_compatibility
    else:
        assert "compatibility" not in payload


def test_get_module_meta_not_found(client, auth_headers):
    response = client.get("/modules/missing_module.txt/meta", headers=auth_headers)
    assert response.status_code == 404
    assert response.json()["detail"] == "Module not found"


@pytest.mark.parametrize(
    "data_fixture",
    ["missing_data_dir", "data_dir_file"],
)
def test_list_knowledge_returns_503_for_invalid_data_dir(
    client, auth_headers, allow_missing_directories, request, data_fixture
):
    invalid_path = request.getfixturevalue(data_fixture)

    response = client.get("/knowledge", headers=auth_headers)

    assert response.status_code == 503
    assert (
        response.json()["detail"]
        == f"Directory di configurazione non trovata: {invalid_path}"
    )


def test_get_knowledge_meta_returns_404_for_traversal_inside_data_dir(
    client, auth_headers, temp_data_dir
):
    traversal_target = f"../{temp_data_dir.name}/ghost.md"
    encoded_target = quote(traversal_target, safe="")

    response = client.get(f"/knowledge/{encoded_target}/meta", headers=auth_headers)

    assert response.status_code == 404
    assert response.json()["detail"] == "Knowledge file not found"


def test_get_module_meta_path_traversal(client, auth_headers):
    response = client.get(
        f"/modules/{quote('../config.py', safe='')}/meta", headers=auth_headers
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid module path"


def test_get_module_rejects_symlink_outside_modules(client, auth_headers, tmp_path):
    external_file = tmp_path / "outside.txt"
    external_file.write_text("top-secret")

    symlink_path = MODULES_DIR / "outside_link.txt"
    try:
        symlink_path.symlink_to(external_file)
    except OSError as exc:
        # Symlink creation requires privileges on Windows without Developer Mode.
        pytest.skip(f"Cannot create symlink in this environment: {exc}")

    try:
        response = client.get("/modules/outside_link.txt", headers=auth_headers)
        assert response.status_code == 400
        assert response.json()["detail"] == "Invalid module path"
    finally:
        symlink_path.unlink(missing_ok=True)


def test_get_knowledge_meta_valid_file(client, auth_headers):
    sample_file = next(p for p in DATA_DIR.iterdir() if p.is_file())
    response = client.get(
        f"/knowledge/{quote(sample_file.name)}/meta", headers=auth_headers
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["name"] == sample_file.name
    assert payload["size_bytes"] == sample_file.stat().st_size


def test_get_knowledge_meta_path_traversal(client, auth_headers):
    response = client.get(
        f"/knowledge/{quote('../config.py', safe='')}/meta", headers=auth_headers
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid knowledge path"


def test_missing_api_key_returns_unauthorized(client):
    response = client.get("/modules")
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid or missing API key"


def test_wrong_api_key_returns_unauthorized(client, auth_headers):
    response = client.get("/modules", headers={"x-api-key": "wrong"})
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid or missing API key"


def test_auth_failed_log_redacts_sensitive_headers(client, caplog):
    leaked_secret = "live-secret-value"
    settings.trust_proxy_headers = True
    settings.trusted_proxy_ips = ["198.51.100.1"]
    client._transport.client = ("198.51.100.1", 50000)
    with caplog.at_level(logging.WARNING):
        response = client.get(
            "/modules",
            headers={
                "x-api-key": leaked_secret,
                "authorization": "Bearer super-secret-token",
                "cookie": "sessionid=secret-cookie",
                "set-cookie": "token=another-secret",
                "user-agent": "AuditClient/1.2.3 very-long-agent",
                "x-forwarded-for": "198.51.100.20",
            },
        )

    assert response.status_code == 401
    assert leaked_secret not in caplog.text
    assert "super-secret-token" not in caplog.text
    assert "secret-cookie" not in caplog.text
    assert "another-secret" not in caplog.text

    auth_failed_record = next(
        record
        for record in caplog.records
        if getattr(record, "event", None) == "auth_failed"
    )
    assert auth_failed_record.client_ip == "198.51.100.20"
    assert auth_failed_record.fail_count == 1
    assert auth_failed_record.route == "/modules"
    assert auth_failed_record.user_agent == "Audi...nt"
    assert auth_failed_record.headers["x-api-key"] == "***REDACTED***"
    assert auth_failed_record.headers["authorization"] == "***REDACTED***"
    assert auth_failed_record.headers["cookie"] == "***REDACTED***"
    assert auth_failed_record.headers["set-cookie"] == "***REDACTED***"


def test_repeated_wrong_api_key_triggers_backoff(client, short_backoff):
    first_response = client.get("/modules", headers={"x-api-key": "wrong"})
    assert first_response.status_code == 401

    blocked_response = client.get("/modules", headers={"x-api-key": "wrong"})
    assert blocked_response.status_code == 429
    assert "Troppi tentativi" in blocked_response.json()["detail"]
    assert blocked_response.headers.get("Retry-After") == str(
        settings.auth_backoff_seconds
    )

    still_blocked = client.get("/modules", headers={"x-api-key": "wrong"})
    assert still_blocked.status_code == 429


def test_failed_attempts_tracker_records_last_seen_timestamp(
    client, monkeypatch, backoff_tracker_limits
):
    current = {"now": 10.0}

    monkeypatch.setattr(auth_backoff_module, "monotonic", lambda: current["now"])
    response = client.get("/modules", headers={"x-api-key": "wrong"})

    assert response.status_code == 401
    state = app_module._failed_attempts["testclient"]
    assert state["count"] == 1
    assert state["last_seen"] == 10.0


def test_failed_attempts_cleanup_respects_ttl(
    client, monkeypatch, backoff_tracker_limits
):
    settings.auth_backoff_state_ttl_seconds = 5
    current = {"now": 0.0}

    def fake_monotonic():
        return current["now"]

    monkeypatch.setattr(auth_backoff_module, "monotonic", fake_monotonic)
    first = client.get("/modules", headers={"x-api-key": "wrong"})
    assert first.status_code == 401
    assert "testclient" in app_module._failed_attempts

    current["now"] = 6.0
    second = client.get("/modules", headers={"x-api-key": "wrong"})
    assert second.status_code == 401

    state = app_module._failed_attempts["testclient"]
    assert state["count"] == 1
    assert state["last_seen"] == 6.0


def test_failed_attempts_eviction_when_max_clients_exceeded(
    client, short_backoff, backoff_tracker_limits
):
    settings.auth_backoff_max_clients = 2
    settings.trust_proxy_headers = True
    settings.trusted_proxy_ips = ["198.51.100.1"]
    client._transport.client = ("198.51.100.1", 50000)

    first_client = {"x-api-key": "wrong", "x-forwarded-for": "203.0.113.10"}
    second_client = {"x-api-key": "wrong", "x-forwarded-for": "203.0.113.11"}
    third_client = {"x-api-key": "wrong", "x-forwarded-for": "203.0.113.12"}

    assert client.get("/modules", headers=first_client).status_code == 401
    assert client.get("/modules", headers=second_client).status_code == 401
    assert set(app_module._failed_attempts) == {"203.0.113.10", "203.0.113.11"}

    assert client.get("/modules", headers=third_client).status_code == 401
    assert set(app_module._failed_attempts) == {"203.0.113.11", "203.0.113.12"}

    response = client.get("/modules", headers=first_client)
    assert response.status_code == 401


def test_backoff_isolated_across_multiple_forwarded_ips(client, short_backoff):
    settings.trust_proxy_headers = True
    settings.trusted_proxy_ips = ["198.51.100.1"]
    client._transport.client = ("198.51.100.1", 50000)

    blocked_ip_headers = {"x-api-key": "wrong", "x-forwarded-for": "203.0.113.10"}
    allowed_ip_headers = {"x-api-key": "wrong", "x-forwarded-for": "203.0.113.11"}

    first_attempt = client.get("/modules", headers=blocked_ip_headers)
    assert first_attempt.status_code == 401

    blocked_attempt = client.get("/modules", headers=blocked_ip_headers)
    assert blocked_attempt.status_code == 429

    independent_attempt = client.get("/modules", headers=allowed_ip_headers)
    assert independent_attempt.status_code == 401


def test_correct_api_key_allows_access(client, auth_headers):
    response = client.get("/modules", headers=auth_headers)
    assert response.status_code == 200


def test_preload_bundle_protected_and_partial(client, auth_headers):
    unauthorized = client.get("/modules/preload_all_modules.txt")
    assert unauthorized.status_code == 401

    response = client.get("/modules/preload_all_modules.txt", headers=auth_headers)

    assert response.status_code == 206
    assert response.headers["X-Content-Partial"] == "true"
    served = int(response.headers["X-Content-Served-Bytes"])
    assert 0 < served <= 4200


def test_preload_bundle_lists_core_modules(client, auth_headers, enable_module_dump):
    response = client.get("/modules/preload_all_modules.txt", headers=auth_headers)

    assert response.status_code == 200

    module_uris = {
        line.lstrip("- ").strip()
        for line in response.text.splitlines()
        if line.startswith("-")
    }
    expected_uris = {
        "module://archivist",
        "module://ruling_expert",
        "module://Taverna_NPC",
        "module://narrative_flow",
        "module://explain_methods",
        "module://minmax_builder",
        "module://Encounter_Designer",
        "module://adventurer_ledger",
        "module://meta_doc",
    }

    assert module_uris == expected_uris
    for uri in module_uris:
        binding_path = resolve_module_uri(uri)
        assert binding_path is not None
        assert binding_path.is_file()


def test_module_uri_bindings_resolve(client, auth_headers, enable_module_dump):
    """All logical URIs embedded in canonical modules must resolve to existing files."""
    from src.utils.module_resolver import MODULE_URI_PATTERN

    unresolved = []
    for module_name in REQUIRED_MODULE_FILES:
        response = client.get(f"/modules/{module_name}", headers=auth_headers)
        assert response.status_code in (200, 206)
        for match in MODULE_URI_PATTERN.finditer(response.text):
            uri = f"{match.group(1)}://{match.group(2)}"
            resolved = resolve_module_uri(uri)
            if resolved is None or not resolved.is_file():
                unresolved.append((module_name, uri, str(resolved) if resolved else None))

    assert not unresolved, f"Unresolved URIs: {unresolved}"


def test_knowledge_requires_api_key(client):
    response = client.get("/knowledge")
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid or missing API key"


def test_knowledge_with_valid_api_key(client, auth_headers):
    response = client.get("/knowledge", headers=auth_headers)
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_missing_configured_api_key_is_rejected(client):
    settings.api_key = None
    response = client.get("/modules")
    assert response.status_code == 401
    assert (
        response.json()["detail"]
        == "API key non configurata. Imposta API_KEY oppure abilita ALLOW_ANONYMOUS=true"
    )


def test_allow_anonymous_access(client):
    settings.api_key = None
    settings.allow_anonymous = True
    response = client.get("/modules")
    assert response.status_code == 200


def test_metrics_allows_valid_api_key(client, metrics_security_settings):
    settings.metrics_api_key = "metrics-secret"

    response = client.get("/metrics", headers={"x-api-key": "metrics-secret"})

    assert response.status_code == 200
    assert response.headers["content-type"] == CONTENT_TYPE_LATEST


def test_metrics_rejects_invalid_api_key(client, metrics_security_settings):
    settings.metrics_api_key = "metrics-secret"

    response = client.get("/metrics", headers={"x-api-key": "wrong"})

    assert response.status_code == 403
    assert response.json()["detail"] == "Accesso alle metriche non autorizzato"


def test_metrics_rejects_unauthorized_client(
    client, metrics_security_settings, monkeypatch
):
    monkeypatch.setattr(settings, "metrics_api_key", None)
    monkeypatch.setattr(settings, "metrics_ip_allowlist", ["203.0.113.5"])
    monkeypatch.setattr(client._transport, "client", ("198.51.100.1", 50000))

    response = client.get("/metrics")

    assert response.status_code == 403
    assert response.json()["detail"] == "Accesso alle metriche non autorizzato"


def test_metrics_allows_metrics_api_key(client, metrics_security_settings, monkeypatch):
    monkeypatch.setattr(settings, "metrics_api_key", "metrics-secret")
    monkeypatch.setattr(settings, "metrics_ip_allowlist", [])

    response = client.get("/metrics", headers={"x-api-key": "metrics-secret"})

    assert response.status_code == 200
    assert response.headers["content-type"] == CONTENT_TYPE_LATEST


def test_metrics_allows_allowlisted_client_host(
    client, metrics_security_settings, monkeypatch
):
    monkeypatch.setattr(settings, "metrics_api_key", None)
    monkeypatch.setattr(settings, "metrics_ip_allowlist", ["203.0.113.5"])
    monkeypatch.setattr(client._transport, "client", ("203.0.113.5", 50000))

    response = client.get("/metrics")

    assert response.status_code == 200
    assert response.headers["content-type"] == CONTENT_TYPE_LATEST


@pytest.mark.anyio
async def test_metrics_allowlisted_client_host(
    metrics_security_settings, allowlisted_http_client
):
    settings.metrics_api_key = None
    settings.metrics_ip_allowlist = ["203.0.113.5"]

    response = await allowlisted_http_client.get("/metrics")

    assert response.status_code == 200
    assert response.headers["content-type"] == CONTENT_TYPE_LATEST


def test_metrics_allowlisted_forwarded_for(client, metrics_security_settings):
    settings.metrics_api_key = None
    settings.metrics_ip_allowlist = ["203.0.113.5"]
    settings.trust_proxy_headers = True
    settings.trusted_proxy_ips = ["198.51.100.8"]
    client._transport.client = ("198.51.100.8", 50000)

    response = client.get("/metrics", headers={"x-forwarded-for": "203.0.113.5"})
    assert response.status_code == 200
    assert response.headers["content-type"] == CONTENT_TYPE_LATEST

    blocked_response = client.get("/metrics")
    assert blocked_response.status_code == 403
    assert blocked_response.json()["detail"] == "Accesso alle metriche non autorizzato"


def test_metrics_allowlist_uses_first_forwarded_for_hop(
    client, metrics_security_settings, monkeypatch
):
    monkeypatch.setattr(settings, "metrics_api_key", None)
    monkeypatch.setattr(settings, "metrics_ip_allowlist", ["203.0.113.5"])
    monkeypatch.setattr(settings, "trust_proxy_headers", True)
    monkeypatch.setattr(settings, "trusted_proxy_ips", ["198.51.100.8"])
    monkeypatch.setattr(client._transport, "client", ("198.51.100.8", 50000))

    allowed = client.get(
        "/metrics",
        headers={"x-forwarded-for": "203.0.113.5, 198.51.100.77, 198.51.100.8"},
    )
    assert allowed.status_code == 200

    blocked = client.get(
        "/metrics",
        headers={"x-forwarded-for": "198.51.100.77, 203.0.113.5, 198.51.100.8"},
    )
    assert blocked.status_code == 403
    assert blocked.json()["detail"] == "Accesso alle metriche non autorizzato"


def test_client_identifier_ignores_forwarded_for_when_proxy_not_trusted(
    client, short_backoff
):
    settings.trust_proxy_headers = True
    settings.trusted_proxy_ips = ["198.51.100.1"]
    client._transport.client = ("198.51.100.99", 50000)

    first_response = client.get(
        "/modules",
        headers={"x-api-key": "wrong", "x-forwarded-for": "203.0.113.10"},
    )
    assert first_response.status_code == 401

    second_response = client.get(
        "/modules",
        headers={"x-api-key": "wrong", "x-forwarded-for": "203.0.113.11"},
    )
    assert second_response.status_code == 429


def test_client_identifier_skips_spoofed_forwarded_for_values(client, short_backoff):
    settings.trust_proxy_headers = True
    settings.trusted_proxy_ips = ["198.51.100.1"]
    client._transport.client = ("198.51.100.1", 50000)

    first_response = client.get(
        "/modules",
        headers={
            "x-api-key": "wrong",
            "x-forwarded-for": "spoofed-value,not-an-ip,2001:db8::25",
        },
    )
    assert first_response.status_code == 401

    second_response = client.get(
        "/modules",
        headers={"x-api-key": "wrong", "x-forwarded-for": "2001:db8::25"},
    )
    assert second_response.status_code == 429


def test_modules_directory_missing_returns_error(
    auth_headers, missing_modules_dir, allow_missing_directories
):
    with TestClient(app) as local_client:
        response = local_client.get("/modules", headers=auth_headers)

    assert response.status_code == 503
    assert str(missing_modules_dir) in response.json()["detail"]


def test_data_directory_missing_returns_error(
    auth_headers, missing_data_dir, allow_missing_directories
):
    with TestClient(app) as local_client:
        response = local_client.get("/knowledge", headers=auth_headers)

    assert response.status_code == 503
    assert str(missing_data_dir) in response.json()["detail"]


def test_health_reports_missing_directories(monkeypatch, tmp_path):
    missing_dir = tmp_path / "missing_anything"

    with TestClient(app) as local_client:
        monkeypatch.setattr(app_module, "MODULES_DIR", missing_dir)
        monkeypatch.setattr(app_module, "DATA_DIR", missing_dir)

        response = local_client.get("/health")

    payload = response.json()
    assert response.status_code == 503
    assert payload["status"] == "error"
    assert payload["directories"]["modules"]["status"] == "error"
    assert payload["directories"]["data"]["status"] == "error"
    assert any("mancante" in msg for msg in payload["errors"])


def test_health_reports_missing_required_module_files(monkeypatch, tmp_path):
    modules_dir = tmp_path / "modules"
    data_dir = tmp_path / "data"
    modules_dir.mkdir()
    data_dir.mkdir()

    required_files = app_module.REQUIRED_MODULE_FILES
    missing_file = required_files[0]

    for name in required_files[1:]:
        (modules_dir / name).write_text("placeholder")

    with TestClient(app) as local_client:
        monkeypatch.setattr(app_module, "MODULES_DIR", modules_dir)
        monkeypatch.setattr(app_module, "DATA_DIR", data_dir)

        response = local_client.get("/health")

    payload = response.json()

    assert response.status_code == 503
    assert payload["status"] == "error"
    assert payload["required_module_files"]["status"] == "error"
    assert missing_file in payload["required_module_files"]["missing"]


def test_validate_directories_returns_error_for_missing_paths(monkeypatch, tmp_path):
    missing_modules = tmp_path / "missing_modules"
    missing_data = tmp_path / "missing_data"

    monkeypatch.setattr(app_module, "MODULES_DIR", missing_modules)
    monkeypatch.setattr(app_module, "DATA_DIR", missing_data)

    diagnostic = app_module._validate_directories()

    assert diagnostic["status"] == "error"
    assert diagnostic["directories"]["modules"]["status"] == "error"
    assert diagnostic["directories"]["data"]["status"] == "error"
    assert diagnostic["required_module_files"]["status"] == "error"
    assert diagnostic["required_module_files"]["missing"] == sorted(
        app_module.REQUIRED_MODULE_FILES
    )

    response = asyncio.run(app_module.health())

    payload = json.loads(response.body)
    assert response.status_code == 503
    assert payload["status"] == "error"
    assert payload["required_module_files"]["missing"] == sorted(
        app_module.REQUIRED_MODULE_FILES
    )


def test_validate_directories_reports_missing_required_files(monkeypatch, tmp_path):
    modules_dir = tmp_path / "modules"
    data_dir = tmp_path / "data"
    modules_dir.mkdir()
    data_dir.mkdir()

    # Crea tutti i file richiesti tranne il secondo
    for name in app_module.REQUIRED_MODULE_FILES:
        if name != app_module.REQUIRED_MODULE_FILES[1]:
            (modules_dir / name).write_text("placeholder")

    monkeypatch.setattr(app_module, "MODULES_DIR", modules_dir)
    monkeypatch.setattr(app_module, "DATA_DIR", data_dir)

    diagnostic = app_module._validate_directories()

    assert diagnostic["status"] == "error"
    assert diagnostic["directories"]["modules"]["status"] == "ok"
    assert diagnostic["directories"]["data"]["status"] == "ok"
    assert diagnostic["required_module_files"]["status"] == "error"
    assert diagnostic["required_module_files"]["missing"] == [
        app_module.REQUIRED_MODULE_FILES[1]
    ]

    response = asyncio.run(app_module.health())

    payload = json.loads(response.body)
    assert response.status_code == 503
    assert payload["status"] == "error"
    assert payload["required_module_files"]["missing"] == [
        app_module.REQUIRED_MODULE_FILES[1]
    ]


def test_health_reports_valid_directories(client):
    response = client.get("/health")

    payload = response.json()
    assert response.status_code == 200
    assert payload == {
        "status": "ok",
        "directories": {
            "modules": {
                "status": "ok",
                "path": str(MODULES_DIR),
                "message": None,
            },
            "data": {
                "status": "ok",
                "path": str(DATA_DIR),
                "message": None,
            },
        },
        "required_module_files": {
            "status": "ok",
            "missing": [],
            "path": str(MODULES_DIR),
        },
    }


def test_health_with_temp_directories_sets_directory_metrics(
    monkeypatch, tmp_path, metrics_security_settings
):
    modules_dir = tmp_path / "modules"
    data_dir = tmp_path / "data"
    modules_dir.mkdir()
    data_dir.mkdir()

    for name in app_module.REQUIRED_MODULE_FILES:
        (modules_dir / name).write_text("placeholder")

    monkeypatch.setattr(app_module, "MODULES_DIR", modules_dir)
    monkeypatch.setattr(app_module, "DATA_DIR", data_dir)

    settings.metrics_api_key = "metrics-secret"
    settings.metrics_ip_allowlist = []

    diagnostic = app_module._validate_directories()

    assert diagnostic["status"] == "ok"
    assert diagnostic["directories"]["modules"]["status"] == "ok"
    assert diagnostic["directories"]["data"]["status"] == "ok"
    assert diagnostic["required_module_files"]["missing"] == []

    with TestClient(app) as local_client:
        health_response = local_client.get("/health")
        metrics_response = local_client.get(
            "/metrics", headers={"x-api-key": "metrics-secret"}
        )

    payload = health_response.json()
    assert health_response.status_code == 200
    assert payload["status"] == "ok"

    assert metrics_response.status_code == 200
    assert 'app_directory_status{directory="modules"} 1.0' in metrics_response.text
    assert 'app_directory_status{directory="data"} 1.0' in metrics_response.text


def test_backoff_reset_after_successful_auth(client, short_backoff, auth_headers):
    first_response = client.get("/modules", headers={"x-api-key": "wrong"})
    assert first_response.status_code == 401
    assert app_module._failed_attempts

    success_response = client.get("/modules", headers=auth_headers)
    assert success_response.status_code == 200
    assert app_module._failed_attempts == {}


def test_metrics_accepts_primary_api_key_when_metrics_key_missing(client, metrics_security_settings):
    settings.metrics_api_key = None

    response = client.get("/metrics", headers={"x-api-key": "test-api-key"})

    assert response.status_code == 200
    assert response.headers["content-type"] == CONTENT_TYPE_LATEST


def test_auth_backoff_counter_increments_when_threshold_is_hit(client, short_backoff, auth_headers):
    baseline_response = client.get("/metrics", headers=auth_headers)
    baseline_metric = next(
        line for line in baseline_response.text.splitlines() if line.startswith("auth_backoff_trigger_total ")
    )
    baseline_value = float(baseline_metric.rsplit(" ", 1)[1])

    assert client.get("/modules", headers={"x-api-key": "wrong"}).status_code == 401
    blocked_response = client.get("/modules", headers={"x-api-key": "wrong"})

    assert blocked_response.status_code == 429

    metrics_response = client.get("/metrics", headers=auth_headers)
    metric_line = next(
        line for line in metrics_response.text.splitlines() if line.startswith("auth_backoff_trigger_total ")
    )
    assert float(metric_line.rsplit(" ", 1)[1]) == baseline_value + 1


def test_truncation_headers_include_remaining_bytes(client, auth_headers):
    response = client.get("/modules/base_profile.txt", headers=auth_headers)

    assert response.status_code == 206
    assert int(response.headers["X-Content-Remaining-Bytes"]) >= 0
    assert response.headers["X-Content-Partial"] == "true"


def test_storage_meta_preserves_remediation_contract(client, auth_headers):
    response = client.get("/storage_meta", headers=auth_headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["remediation"]["echo_gate"].startswith("Echo gate <8.5")
    assert "/self_check" in payload["remediation"]["qa_check"]


def test_storage_meta_returns_503_when_taverna_dir_missing(client, auth_headers, monkeypatch, tmp_path):
    missing = tmp_path / "missing_taverna"
    monkeypatch.setattr(app_module, "TAVERNA_SAVES_DIR", missing)

    response = client.get("/storage_meta", headers=auth_headers)

    assert response.status_code == 503
    assert "Directory taverna_saves non trovata" in response.json()["detail"]
