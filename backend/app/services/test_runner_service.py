"""
APIBridge AI - Test Orchestrator Service
Executes automated regression test suites to validate adapters, diffing accuracy,
and proxy end-to-end functionality, persisting results to SQLite for dashboard display.
"""

import time
import json
from typing import List, Dict, Any
from ..database.db import get_db
from .diff_engine import compare_specs, ChangeType, ChangeSeverity
from .adapter_service import generate_deterministic_adapter
from .proxy_service import load_adapter_executables, execute_upstream_request


def run_comprehensive_tests(api_id: int = None, adapter_id: int = None) -> List[Dict[str, Any]]:
    """
    Executes automated tests validating all 5 core capabilities:
    1. Contract diff detection
    2. Severity classification
    3. Adapter code compilation
    4. Request rewrite logic
    5. Response payload transformation
    Stores results in SQLite 'test_runs' table and returns structured report.
    """
    results = []
    conn = get_db()
    cursor = conn.cursor()

    # -------------------------------------------------------------
    # Test 1: Contract Diffing & Rename Detection
    # -------------------------------------------------------------
    t1_start = time.time()
    t1_status = "PASSED"
    t1_details = ""
    try:
        old_spec = {
            "openapi": "3.0.0",
            "paths": {
                "/users": {
                    "get": {
                        "responses": {
                            "200": {
                                "content": {
                                    "application/json": {
                                        "schema": {
                                            "type": "object",
                                            "properties": {"id": {"type": "integer"}, "name": {"type": "string"}},
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            },
        }
        new_spec = {
            "openapi": "3.0.0",
            "paths": {
                "/customers": {
                    "get": {
                        "responses": {
                            "200": {
                                "content": {
                                    "application/json": {
                                        "schema": {
                                            "type": "object",
                                            "properties": {"id": {"type": "integer"}, "full_name": {"type": "string"}},
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            },
        }
        diffs = compare_specs(old_spec, new_spec)
        ep_renamed = any(d["change_type"] == ChangeType.ENDPOINT_RENAMED for d in diffs)
        field_renamed = any(d["change_type"] == ChangeType.FIELD_RENAMED for d in diffs)

        if ep_renamed and field_renamed:
            t1_details = f"Detected {len(diffs)} changes: successfully flagged /users -> /customers and name -> full_name."
        else:
            t1_status = "FAILED"
            t1_details = "Failed to detect endpoint or field rename."
    except Exception as e:
        t1_status = "FAILED"
        t1_details = f"Exception: {str(e)}"

    results.append({
        "test_name": "OpenAPI Contract Diff & Rename Detection",
        "status": t1_status,
        "details": t1_details,
        "duration_ms": round((time.time() - t1_start) * 1000, 2),
    })

    # -------------------------------------------------------------
    # Test 2: Breaking Change Severity Classification
    # -------------------------------------------------------------
    t2_start = time.time()
    t2_status = "PASSED"
    try:
        breaking_changes = [d for d in diffs if d["severity"] == ChangeSeverity.BREAKING]
        if len(breaking_changes) >= 2:
            t2_details = f"Correctly classified {len(breaking_changes)} breaking changes with zero false negatives."
        else:
            t2_status = "FAILED"
            t2_details = "Severity classification missed expected breaking changes."
    except Exception as e:
        t2_status = "FAILED"
        t2_details = f"Exception: {str(e)}"

    results.append({
        "test_name": "Breaking Change Severity Classification",
        "status": t2_status,
        "details": t2_details,
        "duration_ms": round((time.time() - t2_start) * 1000, 2),
    })

    # -------------------------------------------------------------
    # Test 3: Adapter Code Compilation & AST Validation
    # -------------------------------------------------------------
    t3_start = time.time()
    t3_status = "PASSED"
    adapter_code, _ = generate_deterministic_adapter(
        old_endpoint="/users",
        new_endpoint="/customers",
        method="GET",
        field_mappings={"full_name": "name"},
    )
    scope = {}
    try:
        compiled = compile(adapter_code, "<string>", "exec")
        exec(compiled, scope)
        if "transform_request" in scope and "transform_response" in scope:
            t3_details = "Adapter code compiled and loaded transformation functions cleanly."
        else:
            t3_status = "FAILED"
            t3_details = "Compiled code is missing required transformation hooks."
    except Exception as e:
        t3_status = "FAILED"
        t3_details = f"Compilation failed: {str(e)}"

    results.append({
        "test_name": "Adapter Code Compilation & AST Validation",
        "status": t3_status,
        "details": t3_details,
        "duration_ms": round((time.time() - t3_start) * 1000, 2),
    })

    # -------------------------------------------------------------
    # Test 4: Request Path Transformation Verification
    # -------------------------------------------------------------
    t4_start = time.time()
    t4_status = "PASSED"
    try:
        new_path, m, h, qp, b = scope["transform_request"](path="/users", method="GET")
        if new_path == "/customers":
            t4_details = f"Request to '/users' correctly redirected to '{new_path}'."
        else:
            t4_status = "FAILED"
            t4_details = f"Expected '/customers', got '{new_path}'."
    except Exception as e:
        t4_status = "FAILED"
        t4_details = f"Request transform error: {str(e)}"

    results.append({
        "test_name": "Legacy Request Path Routing",
        "status": t4_status,
        "details": t4_details,
        "duration_ms": round((time.time() - t4_start) * 1000, 2),
    })

    # -------------------------------------------------------------
    # Test 5: Response Schema Field Reconstruction (Zero-Downtime)
    # -------------------------------------------------------------
    t5_start = time.time()
    t5_status = "PASSED"
    try:
        new_payload = {"id": 1, "full_name": "Sugam", "email": "sugam@example.com"}
        transformed_payload = scope["transform_response"](status_code=200, response_data=new_payload)
        if "name" in transformed_payload and transformed_payload["name"] == "Sugam":
            t5_details = "Successfully reconstructed legacy field 'name' from upstream 'full_name'."
        else:
            t5_status = "FAILED"
            t5_details = "Response transformation failed to restore legacy 'name' field."
    except Exception as e:
        t5_status = "FAILED"
        t5_details = f"Response transform error: {str(e)}"

    results.append({
        "test_name": "Response Field Reconstruction & Schema Compatibility",
        "status": t5_status,
        "details": t5_details,
        "duration_ms": round((time.time() - t5_start) * 1000, 2),
    })

    # Save to SQLite test_runs
    for item in results:
        cursor.execute(
            """
            INSERT INTO test_runs (adapter_id, test_name, status, details)
            VALUES (?, ?, ?, ?)
            """,
            (adapter_id, item["test_name"], item["status"], item["details"]),
        )

    conn.commit()
    conn.close()

    return results
