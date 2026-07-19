"""Test endpoint POST /pc/build."""
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.app import app
from src.config import settings

VALID = {
    "name": "Seelah", "method": "point-buy", "campaign_type": "Standard Fantasy",
    "abilities": {"str": 13, "dex": 12, "con": 13, "int": 10, "wis": 14, "cha": 12},
    "race": "Human", "race_bonus_ability": "dex", "class": "Fighter",
    "skills": {"Climb": 1, "Perception": 1, "Survival": 1},
    "feats": ["Power Attack", "Dodge", "Cleave"],
    "traits": ["Reactionary", "Indomitable Faith"],
    "equipment": ["Longsword", "Chain shirt"],
}


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def setup_api_key():
    original = settings.api_key
    original_allow_anonymous = settings.allow_anonymous
    settings.api_key = "test-api-key"
    settings.allow_anonymous = False
    yield
    settings.api_key = original
    settings.allow_anonymous = original_allow_anonymous


@pytest.fixture
def auth_headers():
    return {"x-api-key": "test-api-key"}


def test_pc_build_ok(client, auth_headers):
    resp = client.post("/pc/build", json=VALID, headers=auth_headers)
    assert resp.status_code == 200, resp.text
    sheet = resp.json()
    assert sheet["errors"] == []
    assert sheet["hp"] == 12 and sheet["ac"] == 17  # CA 16 base + 1 Dodge (feat effects)
    assert sheet["abilities"]["str"] == 13
    assert sheet["abilities"]["dex"] == 14


def test_pc_build_invalid(client, auth_headers):
    bad = dict(VALID, abilities={"str": 14, "dex": 12, "con": 13, "int": 10, "wis": 15, "cha": 11})
    resp = client.post("/pc/build", json=bad, headers=auth_headers)
    assert resp.status_code == 422
    assert "budget" in resp.text.lower()


def test_pc_build_bad_request(client, auth_headers):
    resp = client.post("/pc/build", json=dict(VALID, bogus=1), headers=auth_headers)
    assert resp.status_code == 400


def test_pc_build_nested_type_error(client, auth_headers):
    resp = client.post("/pc/build", json=dict(VALID, abilities=[1, 2, 3]), headers=auth_headers)
    assert resp.status_code == 400
