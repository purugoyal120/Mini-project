"""
Automated Pytest Suite for Module 4: Dynamic Adapter Proxy.
Verifies intercepting legacy calls, applying approved adapters,
routing to the modern endpoint, and translating responses.
"""

import pytest
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.database.db import init_db

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_database():
    init_db()


def test_mock_upstream_api_behavior():
    """
    Verifies that calling the removed legacy endpoint fails with 404,
    while the modern endpoint succeeds with 'full_name'.
    """
    # 1. Calling old endpoint directly in v2 fails
    removed_res = client.get("/mock/users")
    assert removed_res.status_code == 404
    assert "removed" in removed_res.json()["detail"].lower()

    # 2. Calling new endpoint directly works
    modern_res = client.get("/mock/customers")
    assert modern_res.status_code == 200
    data = modern_res.json()
    assert data["id"] == 1
    assert data["full_name"] == "Sugam"
    assert "name" not in data  # Proves legacy field 'name' is missing!


def test_dynamic_proxy_end_to_end():
    """
    Core End-to-End Test for the entire APIBridge AI premise:
    1. Register API
    2. Generate and Approve Adapter (/users -> /customers)
    3. Legacy client calls GET /proxy/{api_id}/users
    4. Proxy transforms request to /customers and restores 'name' in response!
    """
    # 1. Setup API
    reg = client.post("/api/apis", json={"name": "Proxy Live Test API", "description": "End to End"})
    api_id = reg.json()["id"] if reg.status_code == 201 else client.get("/api/apis").json()[0]["id"]

    # 2. Generate and Approve Adapter
    gen_res = client.post(
        "/api/adapters/generate",
        json={"api_id": api_id, "old_endpoint": "/users", "new_endpoint": "/customers", "method": "GET"},
    )
    assert gen_res.status_code == 201
    adapter_id = gen_res.json()["id"]

    appr_res = client.post(f"/api/adapters/{adapter_id}/approve")
    assert appr_res.status_code == 200
    assert appr_res.json()["status"] == "APPROVED"

    # 3. Old client calls legacy route through the proxy!
    proxy_res = client.get(f"/proxy/{api_id}/users")
    assert proxy_res.status_code == 200

    # 4. Check that response has the legacy 'name' field restored!
    body = proxy_res.json()
    assert body["id"] == 1
    assert body["full_name"] == "Sugam"
    assert "name" in body
    assert body["name"] == "Sugam"  # ZERO-DOWNTIME SUCCESS!

    # 5. Check proxy diagnostic headers
    assert proxy_res.headers.get("x-apibridge-proxied") == "true"
    assert proxy_res.headers.get("x-apibridge-original-path") == "/users"
    assert proxy_res.headers.get("x-apibridge-target-path") == "/customers"


def test_proxy_pass_through_when_no_adapter():
    """
    When no approved adapter exists, proxy operates in pass-through mode.
    """
    api_id = client.get("/api/apis").json()[0]["id"]
    # Calling /mock/customers through proxy directly
    res = client.get(f"/proxy/{api_id}/customers")
    assert res.status_code == 200
    assert res.headers.get("x-apibridge-proxied") == "false"
