"""
Automated Pytest Suite for Module 1: API Registration and Spec Management.
Tests core functionality, data integrity, and error handling.
"""

import json
import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.database.db import init_db

client = TestClient(app)

# Paths to sample OpenAPI files
SAMPLES_DIR = Path(__file__).resolve().parent.parent / "samples"
V1_PATH = SAMPLES_DIR / "users_v1.json"
V2_PATH = SAMPLES_DIR / "customers_v2.json"


@pytest.fixture(autouse=True)
def setup_database():
    """Ensure database tables exist before running tests."""
    init_db()


def test_health_check():
    """Test health check endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "service" in data


def test_dashboard_stats_empty():
    """Test dashboard stats endpoint returns proper schema even when empty."""
    response = client.get("/api/dashboard/stats")
    assert response.status_code == 200
    data = response.json()
    assert "total_apis" in data
    assert "total_versions" in data
    assert "breaking_changes" in data
    assert "recent_activities" in data


def test_register_and_list_api():
    """Test registering a new API and listing registered APIs."""
    api_name = "User Management Service"
    payload = {
        "name": api_name,
        "description": "Central user identity and authentication service",
    }
    response = client.post("/api/apis", json=payload)
    # Could be 201 if first time, or 400 if already exists from prior run
    if response.status_code == 201:
        data = response.json()
        assert data["name"] == api_name
        assert data["id"] > 0
    else:
        assert response.status_code == 400

    # Verify API is present in list
    list_response = client.get("/api/apis")
    assert list_response.status_code == 200
    apis = list_response.json()
    assert any(a["name"] == api_name for a in apis)


def test_upload_sample_spec_versions():
    """Test uploading v1 and v2 sample OpenAPI specs."""
    # Register a dedicated API for testing samples
    reg_response = client.post(
        "/api/apis",
        json={"name": "Sample E-Commerce API", "description": "API for testing breaking changes"},
    )
    if reg_response.status_code == 201:
        api_id = reg_response.json()["id"]
    else:
        # Find existing ID
        all_apis = client.get("/api/apis").json()
        api_id = [a["id"] for a in all_apis if a["name"] == "Sample E-Commerce API"][0]

    # Upload Version 1.0.0
    with open(V1_PATH, "r", encoding="utf-8") as f:
        v1_content = f.read()

    v1_res = client.post(
        f"/api/apis/{api_id}/versions",
        json={"version_tag": "1.0.0", "spec_content": v1_content},
    )
    # If not already uploaded, expect 201
    if v1_res.status_code == 201:
        v1_data = v1_res.json()
        assert v1_data["version_tag"] == "1.0.0"
        assert v1_data["api_id"] == api_id

    # Upload Version 2.0.0
    with open(V2_PATH, "r", encoding="utf-8") as f:
        v2_content = f.read()

    v2_res = client.post(
        f"/api/apis/{api_id}/versions",
        json={"version_tag": "2.0.0", "spec_content": v2_content},
    )
    if v2_res.status_code == 201:
        v2_data = v2_res.json()
        assert v2_data["version_tag"] == "2.0.0"
        assert v2_data["api_id"] == api_id

    # Verify both versions exist
    versions_res = client.get(f"/api/apis/{api_id}/versions")
    assert versions_res.status_code == 200
    versions = versions_res.json()
    tags = [v["version_tag"] for v in versions]
    assert "1.0.0" in tags
    assert "2.0.0" in tags


def test_invalid_spec_upload_rejection():
    """Test that invalid OpenAPI content is properly rejected with a clear message."""
    reg = client.post("/api/apis", json={"name": "Faulty API", "description": "Test"})
    api_id = reg.json()["id"] if reg.status_code == 201 else client.get("/api/apis").json()[0]["id"]

    # Upload completely invalid content (not valid JSON or missing paths)
    bad_res = client.post(
        f"/api/apis/{api_id}/versions",
        json={"version_tag": "99.9.9", "spec_content": "random non-json plain text here"},
    )
    assert bad_res.status_code == 400
    assert "Invalid" in bad_res.json()["detail"] or "Failed" in bad_res.json()["detail"]
