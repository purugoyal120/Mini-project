"""
Automated Pytest Suite for Module 3: AI Adapter Generator.
Tests adapter generation, compilation, lifecycle (Draft -> Approved/Rejected),
and verification that transformation logic executes correctly.
"""

import pytest
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.database.db import init_db
from backend.app.services.adapter_service import generate_deterministic_adapter

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_database():
    init_db()


def test_adapter_generation_and_compilation():
    """
    Tests generating adapter code and verifying that it is valid, compilable Python.
    """
    # 1. Register API
    reg = client.post("/api/apis", json={"name": "Adapter Test API", "description": "Test"})
    api_id = reg.json()["id"] if reg.status_code == 201 else client.get("/api/apis").json()[0]["id"]

    # 2. Request Adapter Generation
    gen_payload = {
        "api_id": api_id,
        "old_endpoint": "/users",
        "new_endpoint": "/customers",
        "method": "GET",
    }
    res = client.post("/api/adapters/generate", json=gen_payload)
    assert res.status_code == 201
    data = res.json()

    assert data["status"] == "DRAFT"
    assert data["old_endpoint"] == "/users"
    assert data["new_endpoint"] == "/customers"
    assert "transform_request" in data["adapter_code"]
    assert "transform_response" in data["adapter_code"]

    # 3. Test that the generated code compiles with Python's built-in compile()
    compiled_code = compile(data["adapter_code"], "<string>", "exec")
    assert compiled_code is not None

    # 4. Execute the compiled code in a safe local namespace to verify functions work
    scope = {}
    exec(compiled_code, scope)

    assert "transform_request" in scope
    assert "transform_response" in scope

    # Test request transformation
    new_path, method, headers, qp, body = scope["transform_request"]("/users", "GET")
    assert new_path == "/customers"

    # Test response transformation (The core bridge feature!)
    # New API responds with 'full_name': 'Sugam', old client expects 'name'
    new_api_response = {"id": 1, "full_name": "Sugam"}
    transformed = scope["transform_response"](200, new_api_response)

    assert "name" in transformed
    assert transformed["name"] == "Sugam"


def test_adapter_approval_workflow():
    """
    Tests the Human-in-the-Loop lifecycle:
    Draft -> Approved or Rejected.
    """
    # Get or create an adapter
    adapters_res = client.get("/api/adapters")
    if adapters_res.json():
        adapter_id = adapters_res.json()[0]["id"]
    else:
        api_id = client.get("/api/apis").json()[0]["id"]
        res = client.post("/api/adapters/generate", json={"api_id": api_id, "old_endpoint": "/users", "new_endpoint": "/customers"})
        adapter_id = res.json()["id"]

    # Approve adapter
    appr_res = client.post(f"/api/adapters/{adapter_id}/approve")
    assert appr_res.status_code == 200
    assert appr_res.json()["status"] == "APPROVED"

    # Reject adapter
    rej_res = client.post(f"/api/adapters/{adapter_id}/reject")
    assert rej_res.status_code == 200
    assert rej_res.json()["status"] == "REJECTED"


def test_adapter_code_manual_edit():
    """
    Tests updating the adapter code manually before deployment.
    """
    adapters_res = client.get("/api/adapters")
    adapter_id = adapters_res.json()[0]["id"]

    custom_code = "# Custom reviewed adapter code\ndef transform_request(p, m): return '/v2/customers', m"
    update_res = client.put(f"/api/adapters/{adapter_id}", json={"adapter_code": custom_code})
    assert update_res.status_code == 200
    assert update_res.json()["adapter_code"] == custom_code
