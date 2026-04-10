import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.append(str(Path(__file__).resolve().parent.parent))

import src.app as app_module
import src.auth_backoff as auth_backoff_module
from src.app import app
from src.config import settings


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def reset_failed_attempts():
    app_module._reset_failed_attempts()
    yield
    app_module._reset_failed_attempts()


@pytest.fixture(autouse=True)
def configure_api_key():
    original_api_key = settings.api_key
    original_allow_anonymous = settings.allow_anonymous
    settings.api_key = "test-api-key"
    settings.allow_anonymous = False
    yield
    settings.api_key = original_api_key
    settings.allow_anonymous = original_allow_anonymous


@pytest.fixture
def backoff_config(monkeypatch):
    original_threshold = settings.auth_backoff_threshold
    original_seconds = settings.auth_backoff_seconds

    def apply(threshold: int = 2, seconds: int = 3):
        settings.auth_backoff_threshold = threshold
        settings.auth_backoff_seconds = seconds

    apply()  # apply defaults for the test
    yield apply

    settings.auth_backoff_threshold = original_threshold
    settings.auth_backoff_seconds = original_seconds


@pytest.fixture
def controllable_monotonic(monkeypatch):
    current = {"value": 0.0}

    def fake_monotonic():
        return current["value"]

    def advance(delta: float):
        current["value"] += delta

    monkeypatch.setattr(auth_backoff_module, "monotonic", fake_monotonic)
    return advance


@pytest.fixture
def auth_headers():
    return {"x-api-key": "test-api-key"}


def test_allows_anonymous_access_when_enabled(client, auth_headers):
    settings.allow_anonymous = True
    settings.api_key = None

    first_response = client.get("/modules")
    assert first_response.status_code == 200

    # wrong keys should not accumulate failures when anonymous is allowed
    second_response = client.get("/modules", headers={"x-api-key": "wrong"})
    assert second_response.status_code == 200

    assert app_module._failed_attempts == {}


def test_missing_key_is_rejected_when_api_key_configured(client):
    settings.allow_anonymous = False
    response = client.get("/modules")

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid or missing API key"
    assert app_module._failed_attempts  # failure recorded for caller


def test_backoff_blocks_and_expires(
    client, backoff_config, controllable_monotonic, auth_headers
):
    # exhaust the threshold to trigger backoff
    first = client.get("/modules", headers={"x-api-key": "wrong"})
    assert first.status_code == 401

    blocked = client.get("/modules", headers={"x-api-key": "wrong"})
    assert blocked.status_code == 429
    assert blocked.headers.get("Retry-After") == str(settings.auth_backoff_seconds)

    # still blocked without advancing time
    still_blocked = client.get("/modules", headers={"x-api-key": "wrong"})
    assert still_blocked.status_code == 429

    # advance beyond the backoff window and ensure access works again
    controllable_monotonic(settings.auth_backoff_seconds + 1)
    unblocked = client.get("/modules", headers=auth_headers)
    assert unblocked.status_code == 200

    # tracker is cleared after a successful authenticated request
    assert app_module._failed_attempts == {}
