"""
Automated Pytest Suite for Module 2: Breaking Change Detection Engine.
Validates classification of BREAKING, NON_BREAKING, and COSMETIC changes.
"""

import json
import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.database.db import init_db
from backend.app.services.diff_engine import compare_specs, ChangeSeverity, ChangeType

client = TestClient(app)

SAMPLES_DIR = Path(__file__).resolve().parent.parent / "samples"
V1_PATH = SAMPLES_DIR / "users_v1.json"
V2_PATH = SAMPLES_DIR / "customers_v2.json"


@pytest.fixture(autouse=True)
def setup_database():
    init_db()


def test_sample_v1_v2_diff_detection():
    """
    Tests comparing the exact sample from user:
    Old: GET /users -> {id, name}
    New: GET /customers -> {id, full_name}
    Must detect breaking endpoint rename and breaking response field rename.
    """
    with open(V1_PATH, "r", encoding="utf-8") as f:
        v1_spec = json.loads(f.read())
    with open(V2_PATH, "r", encoding="utf-8") as f:
        v2_spec = json.loads(f.read())

    changes = compare_specs(v1_spec, v2_spec)

    # 1. Must detect endpoint rename (/users -> /customers)
    endpoint_changes = [c for c in changes if c["change_type"] in (ChangeType.ENDPOINT_RENAMED, ChangeType.ENDPOINT_REMOVED)]
    assert len(endpoint_changes) >= 1
    assert endpoint_changes[0]["severity"] == ChangeSeverity.BREAKING
    assert "/users" in endpoint_changes[0]["description"]

    # 2. Must detect response field rename/removal (name -> full_name)
    field_changes = [c for c in changes if c["change_type"] in (ChangeType.FIELD_RENAMED, ChangeType.FIELD_REMOVED)]
    assert len(field_changes) >= 1
    assert field_changes[0]["severity"] == ChangeSeverity.BREAKING
    assert "name" in field_changes[0]["description"]


def test_diff_api_endpoint_integration():
    """
    Tests the POST /api/changes/diff endpoint end-to-end with SQLite persistence.
    """
    # 1. Register API
    api_res = client.post("/api/apis", json={"name": "Diff Test API", "description": "Testing diff engine"})
    api_id = api_res.json()["id"] if api_res.status_code == 201 else client.get("/api/apis").json()[0]["id"]

    # 2. Upload V1
    with open(V1_PATH, "r", encoding="utf-8") as f:
        v1_text = f.read()
    v1_upload = client.post(f"/api/apis/{api_id}/versions", json={"version_tag": "v1.0", "spec_content": v1_text})
    if v1_upload.status_code == 201:
        v1_id = v1_upload.json()["id"]
    else:
        v1_id = client.get(f"/api/apis/{api_id}/versions").json()[-1]["id"]

    # 3. Upload V2
    with open(V2_PATH, "r", encoding="utf-8") as f:
        v2_text = f.read()
    v2_upload = client.post(f"/api/apis/{api_id}/versions", json={"version_tag": "v2.0", "spec_content": v2_text})
    if v2_upload.status_code == 201:
        v2_id = v2_upload.json()["id"]
    else:
        v2_id = client.get(f"/api/apis/{api_id}/versions").json()[0]["id"]

    # 4. Trigger Diff
    diff_res = client.post("/api/changes/diff", json={"api_id": api_id, "old_version_id": v1_id, "new_version_id": v2_id})
    assert diff_res.status_code == 200
    data = diff_res.json()
    assert data["api_id"] == api_id
    assert data["summary"]["breaking"] >= 2
    assert len(data["changes"]) >= 2

    # 5. Check changes saved to DB
    list_changes_res = client.get(f"/api/changes?api_id={api_id}")
    assert list_changes_res.status_code == 200
    assert len(list_changes_res.json()) >= 2


def test_cosmetic_change_detection():
    """Test that summary/documentation changes are classified as COSMETIC."""
    old_spec = {
        "openapi": "3.0.0",
        "paths": {
            "/status": {
                "get": {
                    "summary": "Check server status",
                    "responses": {"200": {"description": "OK"}}
                }
            }
        }
    }
    new_spec = {
        "openapi": "3.0.0",
        "paths": {
            "/status": {
                "get": {
                    "summary": "Healthcheck ping probe",
                    "responses": {"200": {"description": "OK"}}
                }
            }
        }
    }

    changes = compare_specs(old_spec, new_spec)
    assert len(changes) == 1
    assert changes[0]["severity"] == ChangeSeverity.COSMETIC
    assert changes[0]["change_type"] == ChangeType.DOC_UPDATED


def test_non_breaking_new_endpoint():
    """Test that adding a new endpoint is classified as NON_BREAKING."""
    old_spec = {
        "openapi": "3.0.0",
        "paths": {
            "/items": {"get": {"responses": {"200": {"description": "OK"}}}}
        }
    }
    new_spec = {
        "openapi": "3.0.0",
        "paths": {
            "/items": {"get": {"responses": {"200": {"description": "OK"}}}},
            "/items/search": {"get": {"responses": {"200": {"description": "Search"}}}}
        }
    }

    changes = compare_specs(old_spec, new_spec)
    assert len(changes) == 1
    assert changes[0]["severity"] == ChangeSeverity.NON_BREAKING
    assert changes[0]["change_type"] == ChangeType.ENDPOINT_ADDED
