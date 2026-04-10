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
from src.app import app
from src.config import MODULES_DIR, DATA_DIR, settings
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
    assert response.headers["X-Content-Served-Bytes"] == "0"


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
    assert payload"ledger"]["currency"]["oro"] >= 0
    assert payload["composite"]["build"]["export"]["sheet_payload"]
