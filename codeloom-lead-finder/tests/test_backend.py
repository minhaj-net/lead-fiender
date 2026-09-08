"""
tests/test_backend.py
──────────────────────
Integration tests for FastAPI endpoints using TestClient.
These tests mock the DB and automation service so no real infrastructure needed.
Run with: pytest tests/test_backend.py -v
"""
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from backend.main import app


@pytest.fixture
def client():
    """FastAPI test client that skips the lifespan DB init."""
    with patch("backend.database.init_db"), \
         patch("backend.database._get_pool"):
        with TestClient(app, raise_server_exceptions=True) as c:
            yield c


class TestHealthEndpoint:

    def test_health_ok_db_connected(self, client):
        with patch("backend.routers.health.get_connection") as mock_gc:
            mock_conn   = MagicMock()
            mock_cursor = MagicMock()
            mock_cursor.fetchone.return_value = (1,)
            mock_conn.cursor.return_value = mock_cursor
            mock_gc.return_value = mock_conn

            resp = client.get("/health")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["database"] == "connected"

    def test_health_db_error(self, client):
        from mysql.connector import Error as MySQLError
        with patch("backend.routers.health.get_connection", side_effect=MySQLError("fail")):
            resp = client.get("/health")

        assert resp.status_code == 200
        data = resp.json()
        assert data["database"] == "error"


class TestAutomationEndpoints:

    def test_start_automation(self, client):
        with patch("backend.routers.automation.auto_svc.is_running", return_value=False), \
             patch("backend.routers.automation.auto_svc.start_automation") as mock_start:
            mock_run = MagicMock()
            mock_run.id         = 1
            mock_run.started_at = None
            mock_run.status     = "RUNNING"
            mock_start.return_value = mock_run

            resp = client.post("/automation/start", json={
                "source_url": "https://www.facebook.com/groups/testgroup",
                "max_leads":  10,
            })

        assert resp.status_code == 200
        data = resp.json()
        assert data["running"] is True

    def test_start_automation_already_running(self, client):
        with patch("backend.routers.automation.auto_svc.is_running", return_value=True):
            resp = client.post("/automation/start", json={
                "source_url": "https://www.facebook.com/groups/testgroup",
                "max_leads":  10,
            })
        assert resp.status_code == 409

    def test_stop_automation_not_running(self, client):
        with patch("backend.routers.automation.auto_svc.stop_automation", return_value="not_running"):
            resp = client.post("/automation/stop")
        assert resp.status_code == 400

    def test_stop_automation_running(self, client):
        with patch("backend.routers.automation.auto_svc.stop_automation", return_value="stopping"), \
             patch("backend.routers.automation.auto_svc.get_current_run") as mock_run:
            run = MagicMock()
            run.id          = 1
            run.leads_found = 5
            run.leads_saved = 3
            mock_run.return_value = run

            resp = client.post("/automation/stop")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "STOPPED"

    def test_get_status_no_run(self, client):
        with patch("backend.routers.automation.auto_svc.get_current_run", return_value=None):
            resp = client.get("/automation/status")
        assert resp.status_code == 200
        assert resp.json()["running"] is False


class TestRootEndpoint:

    def test_root(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert "Codeloom" in resp.json()["service"]
