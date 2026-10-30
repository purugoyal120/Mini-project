"""
Automated Pytest Suite for Module 5: Test Orchestrator.
Validates test suite execution, database persistence, and summary metrics.
"""

import pytest
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.database.db import init_db

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_database():
    init_db()


def test_trigger_automated_tests():
    """
    Triggers automated tests via API and asserts that all 5 tests pass.
    """
    res = client.post("/api/tests/run")
    assert res.status_code == 200
    data = res.json()

    assert data["total_tests"] == 5
    assert data["passed"] == 5
    assert data["failed"] == 0
    assert data["pass_rate_percent"] == 100.0
    assert len(data["results"]) == 5


def test_list_test_runs_and_summary():
    """
    Verifies test run history and metric aggregation.
    """
    client.post("/api/tests/run")

    runs_res = client.get("/api/tests/runs?limit=10")
    assert runs_res.status_code == 200
    runs = runs_res.json()
    assert len(runs) >= 5

    summary_res = client.get("/api/tests/summary")
    assert summary_res.status_code == 200
    summary = summary_res.json()
    assert summary["total_runs"] >= 5
    assert summary["passed_runs"] >= 5
    assert summary["pass_rate"] == 100.0
