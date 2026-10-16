import pytest
from fastapi.testclient import TestClient
from backend.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_api_list_runtimes(client):
    response = client.get("/api/runtimes")
    assert response.status_code == 200
    data = response.json()
    assert "tracks" in data
    tracks = data["tracks"]
    assert len(tracks) >= 10
    track_ids = [t["id"] for t in tracks]
    for expected in ["python", "java", "c", "cpp", "sql", "node_express", "web_foundations", "react", "tailwind", "mongodb"]:
        assert expected in track_ids


def test_api_runtimes_health(client):
    response = client.get("/api/runtimes/health")
    assert response.status_code == 200
    data = response.json()
    assert "total_tracks" in data
    assert "loaded_adapters" in data
    assert data["loaded_adapters"] >= 10
    assert "tracks" in data
    assert "python" in data["tracks"]
    assert "java" in data["tracks"]


def test_api_run_python_snippet(client):
    payload = {
        "code": "print('API Execution Verified!')",
        "timeout_sec": 10,
    }
    response = client.post("/api/runtimes/python/run", json=payload)
    assert response.status_code == 200
    res = response.json()
    assert res["status"] == "pass"
    assert res["exit_code"] == 0
    assert "API Execution Verified!" in res["stdout"]


def test_api_run_sql_snippet_with_seed(client):
    payload = {
        "code": "SELECT name FROM items WHERE price > 20;",
        "seed_sql": "CREATE TABLE items (id SERIAL, name TEXT, price INT); INSERT INTO items (name, price) VALUES ('Book', 25), ('Pen', 5);",
    }
    response = client.post("/api/runtimes/sql/run", json=payload)
    assert response.status_code == 200
    res = response.json()
    assert res["status"] == "pass"
    assert "Book" in res["stdout"]
    assert len(res["artifacts"]["table"]) == 1


def test_api_unknown_track_returns_404(client):
    payload = {"code": "unknown"}
    response = client.post("/api/runtimes/non_existent_lang/run", json=payload)
    assert response.status_code == 404
