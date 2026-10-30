"""
AI Adapter Generator Routes.
Generates, inspects, and manages adapter translation code with a human-in-the-loop approval workflow.
"""

from fastapi import APIRouter, HTTPException, Query, status
from typing import List, Optional
import json

from ..database.db import get_db
from ..schemas.models import (
    AdapterGenerateRequest,
    AdapterResponse,
    AdapterUpdateRequest,
)
from ..services.adapter_service import generate_adapter_for_changes

router = APIRouter(prefix="/api/adapters", tags=["AI Adapter Generator"])


@router.post("/generate", response_model=AdapterResponse, status_code=status.HTTP_201_CREATED)
def generate_adapter(payload: AdapterGenerateRequest):
    """
    Generates Python adapter code for detected breaking changes.
    The adapter is saved in 'DRAFT' status requiring developer review/approval before activation.
    """
    conn = get_db()
    cursor = conn.cursor()

    # Step 1: Verify API exists
    cursor.execute("SELECT id, name FROM apis WHERE id = ?", (payload.api_id,))
    api_row = cursor.fetchone()
    if not api_row:
        conn.close()
        raise HTTPException(status_code=404, detail=f"API with ID {payload.api_id} not found.")

    old_endpoint = payload.old_endpoint
    new_endpoint = payload.new_endpoint
    method = payload.method or "GET"
    changes_records = []

    # Step 2: Fetch context from recorded breaking changes
    if payload.change_id:
        cursor.execute("SELECT * FROM changes WHERE id = ?", (payload.change_id,))
        ch = cursor.fetchone()
        if ch:
            ch_dict = dict(ch)
            if ch_dict.get("details") and isinstance(ch_dict["details"], str):
                try:
                    ch_dict["details"] = json.loads(ch_dict["details"])
                except Exception:
                    pass
            changes_records.append(ch_dict)
            if not old_endpoint:
                old_endpoint = ch_dict.get("endpoint")
            if not new_endpoint and isinstance(ch_dict.get("details"), dict):
                new_endpoint = ch_dict["details"].get("new_endpoint")
    else:
        # Fetch all breaking changes for this API
        cursor.execute(
            "SELECT * FROM changes WHERE api_id = ? AND severity = 'BREAKING' ORDER BY id DESC",
            (payload.api_id,),
        )
        for row in cursor.fetchall():
            ch_dict = dict(row)
            if ch_dict.get("details") and isinstance(ch_dict["details"], str):
                try:
                    ch_dict["details"] = json.loads(ch_dict["details"])
                except Exception:
                    pass
            changes_records.append(ch_dict)

    # Infer endpoint mapping dynamically from changes if not explicitly provided
    if not old_endpoint or not new_endpoint:
        for ch in changes_records:
            ch_type = ch.get("change_type")
            det = ch.get("details") or {}
            if isinstance(det, str):
                try:
                    det = json.loads(det)
                except Exception:
                    det = {}

            if ch_type == "ENDPOINT_RENAMED":
                if not old_endpoint:
                    old_endpoint = det.get("old_endpoint") or ch.get("endpoint")
                if not new_endpoint:
                    new_endpoint = det.get("new_endpoint")
                if old_endpoint and new_endpoint:
                    break

            if ch_type in ("FIELD_RENAMED", "FIELD_REMOVED", "FIELD_ADDED"):
                if not old_endpoint:
                    old_endpoint = det.get("old_endpoint") or ch.get("endpoint")
                if not new_endpoint and det.get("new_endpoint"):
                    new_endpoint = det.get("new_endpoint")

    # If new_endpoint is still unknown, look up the active OpenAPI specifications for this service!
    if not old_endpoint or not new_endpoint:
        cursor.execute("SELECT raw_spec FROM spec_versions WHERE api_id = ? ORDER BY id ASC", (payload.api_id,))
        spec_rows = cursor.fetchall()
        if spec_rows:
            first_paths = list(json.loads(spec_rows[0]["raw_spec"]).get("paths", {}).keys())
            last_paths = list(json.loads(spec_rows[-1]["raw_spec"]).get("paths", {}).keys())
            if not old_endpoint and first_paths:
                old_endpoint = first_paths[0]
            if not new_endpoint and last_paths:
                new_endpoint = last_paths[0]

    # Universal graceful fallbacks
    old_endpoint = old_endpoint or "/users"
    new_endpoint = new_endpoint or "/customers"

    # Step 3: Generate adapter code via AI / Deterministic Engine
    code, explanation = generate_adapter_for_changes(
        old_endpoint=old_endpoint,
        new_endpoint=new_endpoint,
        method=method,
        changes=changes_records,
        custom_field_mappings=payload.field_mappings,
    )

    # Step 4: Persist adapter in DRAFT status
    cursor.execute(
        """
        INSERT INTO adapters (api_id, old_endpoint, new_endpoint, method, status, adapter_code, explanation)
        VALUES (?, ?, ?, ?, 'DRAFT', ?, ?)
        """,
        (payload.api_id, old_endpoint, new_endpoint, method, code, explanation),
    )
    conn.commit()
    adapter_id = cursor.lastrowid

    cursor.execute("SELECT * FROM adapters WHERE id = ?", (adapter_id,))
    row = cursor.fetchone()
    conn.close()

    return AdapterResponse(
        id=row["id"],
        api_id=row["api_id"],
        old_endpoint=row["old_endpoint"],
        new_endpoint=row["new_endpoint"],
        method=row["method"],
        status=row["status"],
        adapter_code=row["adapter_code"],
        explanation=row["explanation"],
        created_at=str(row["created_at"]),
    )


@router.get("", response_model=List[AdapterResponse])
def list_adapters(
    api_id: Optional[int] = Query(None, description="Filter by API ID"),
    status: Optional[str] = Query(None, description="Filter by status (e.g. DRAFT, APPROVED, ACTIVE)"),
):
    """
    Lists all adapters stored in the database.
    """
    conn = get_db()
    cursor = conn.cursor()

    query = "SELECT * FROM adapters WHERE 1=1"
    params = []

    if api_id:
        query += " AND api_id = ?"
        params.append(api_id)
    if status:
        query += " AND status = ?"
        params.append(status.upper())

    query += " ORDER BY id DESC"

    cursor.execute(query, tuple(params))
    rows = cursor.fetchall()
    conn.close()

    return [
        AdapterResponse(
            id=r["id"],
            api_id=r["api_id"],
            old_endpoint=r["old_endpoint"],
            new_endpoint=r["new_endpoint"],
            method=r["method"],
            status=r["status"],
            adapter_code=r["adapter_code"],
            explanation=r["explanation"],
            created_at=str(r["created_at"]),
        )
        for r in rows
    ]


@router.get("/{adapter_id}", response_model=AdapterResponse)
def get_adapter(adapter_id: int):
    """
    Retrieves full details and source code of an adapter.
    """
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM adapters WHERE id = ?", (adapter_id,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        raise HTTPException(status_code=404, detail=f"Adapter {adapter_id} not found.")

    return AdapterResponse(
        id=row["id"],
        api_id=row["api_id"],
        old_endpoint=row["old_endpoint"],
        new_endpoint=row["new_endpoint"],
        method=row["method"],
        status=row["status"],
        adapter_code=row["adapter_code"],
        explanation=row["explanation"],
        created_at=str(row["created_at"]),
    )


@router.post("/{adapter_id}/approve", response_model=AdapterResponse)
def approve_adapter(adapter_id: int):
    """
    Human-in-the-loop: Approves a generated adapter code for proxy deployment.
    """
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM adapters WHERE id = ?", (adapter_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail=f"Adapter {adapter_id} not found.")

    cursor.execute("UPDATE adapters SET status = 'APPROVED' WHERE id = ?", (adapter_id,))
    conn.commit()

    cursor.execute("SELECT * FROM adapters WHERE id = ?", (adapter_id,))
    updated = cursor.fetchone()
    conn.close()

    return AdapterResponse(
        id=updated["id"],
        api_id=updated["api_id"],
        old_endpoint=updated["old_endpoint"],
        new_endpoint=updated["new_endpoint"],
        method=updated["method"],
        status=updated["status"],
        adapter_code=updated["adapter_code"],
        explanation=updated["explanation"],
        created_at=str(updated["created_at"]),
    )


@router.post("/{adapter_id}/reject", response_model=AdapterResponse)
def reject_adapter(adapter_id: int):
    """
    Rejects a draft adapter.
    """
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE adapters SET status = 'REJECTED' WHERE id = ?", (adapter_id,))
    conn.commit()

    cursor.execute("SELECT * FROM adapters WHERE id = ?", (adapter_id,))
    updated = cursor.fetchone()
    conn.close()

    if not updated:
        raise HTTPException(status_code=404, detail=f"Adapter {adapter_id} not found.")

    return AdapterResponse(
        id=updated["id"],
        api_id=updated["api_id"],
        old_endpoint=updated["old_endpoint"],
        new_endpoint=updated["new_endpoint"],
        method=updated["method"],
        status=updated["status"],
        adapter_code=updated["adapter_code"],
        explanation=updated["explanation"],
        created_at=str(updated["created_at"]),
    )


@router.put("/{adapter_id}", response_model=AdapterResponse)
def update_adapter_code(adapter_id: int, payload: AdapterUpdateRequest):
    """
    Allows the developer to edit and customize the adapter Python code before approving it.
    """
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE adapters SET adapter_code = ? WHERE id = ?",
        (payload.adapter_code, adapter_id),
    )
    conn.commit()

    cursor.execute("SELECT * FROM adapters WHERE id = ?", (adapter_id,))
    updated = cursor.fetchone()
    conn.close()

    if not updated:
        raise HTTPException(status_code=404, detail=f"Adapter {adapter_id} not found.")

    return AdapterResponse(
        id=updated["id"],
        api_id=updated["api_id"],
        old_endpoint=updated["old_endpoint"],
        new_endpoint=updated["new_endpoint"],
        method=updated["method"],
        status=updated["status"],
        adapter_code=updated["adapter_code"],
        explanation=updated["explanation"],
        created_at=str(updated["created_at"]),
    )
