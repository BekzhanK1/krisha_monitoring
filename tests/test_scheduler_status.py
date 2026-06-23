from fastapi.testclient import TestClient

from app.main import app


def test_scheduler_status_has_expected_fields() -> None:
    client = TestClient(app)
    response = client.get("/scheduler/status")
    assert response.status_code == 200
    data = response.json()

    assert "running" in data
    assert "jobs" in data
    assert "analytics" in data
    assert "hunter" in data
    assert isinstance(data["running"], bool)
    assert isinstance(data["jobs"], list)

    for job in data["jobs"]:
        assert "id" in job
        assert "next_run" in job
        assert "trigger" in job
