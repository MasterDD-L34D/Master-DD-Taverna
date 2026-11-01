from fastapi.testclient import TestClient

from tools.mock_builder_server import app


def test_mock_ruling_refuses_validation():
    response = TestClient(app).post("/ruling", json={"build": {}})
    assert response.status_code == 501
    assert "non esegue validazioni" in response.json()["detail"]
