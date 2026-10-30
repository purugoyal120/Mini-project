"""
Breaking Change Detection Routes.
Compares two OpenAPI versions, stores detected diffs in SQLite, and provides changelogs.
"""

from fastapi import APIRouter, HTTPException, Query, status
from typing import List, Optional
import json

from ..database.db import get_db
from ..schemas.models import DiffRequest, DiffResponse, DiffSummary, ChangeItem
from ..services.diff_engine import compare_specs

router = APIRouter(prefix="/api/changes", tags=["Breaking Change Detection"])


@router.post("/diff", response_model=DiffResponse)
def compute_diff(payload: DiffRequest):
    """
    Compares two registered versions of an API, detects breaking/non-breaking/cosmetic
    changes, persists them to SQLite, and returns an actionable report.
    """
    conn = get_db()
    cursor = conn.cursor()

    # Step 1: Fetch Old Version
    cursor.execute(
        "SELECT id, api_id, version_tag, raw_spec FROM spec_versions WHERE id = ? AND api_id = ?",
        (payload.old_version_id, payload.api_id),
    )
    old_row = cursor.fetchone()
    if not old_row:
        conn.close()
        raise HTTPException(
            status_code=404,
            detail=f"Base version ID {payload.old_version_id} not found for API {payload.api_id}.",
        )

    # Step 2: Fetch New Version
    cursor.execute(
        "SELECT id, api_id, version_tag, raw_spec FROM spec_versions WHERE id = ? AND api_id = ?",
        (payload.new_version_id, payload.api_id),
    )
    new_row = cursor.fetchone()
    if not new_row:
        conn.close()
        raise HTTPException(
            status_code=404,
            detail=f"Target version ID {payload.new_version_id} not found for API {payload.api_id}.",
        )

    old_spec = json.loads(old_row["raw_spec"])
    new_spec = json.loads(new_row["raw_spec"])

    # Step 3: Run the Breaking Change Detection Engine
    raw_changes = compare_specs(old_spec, new_spec)

    # Step 4: Clear prior diffs for this exact pair to prevent duplicate records
    cursor.execute(
        "DELETE FROM changes WHERE api_id = ? AND old_version_id = ? AND new_version_id = ?",
        (payload.api_id, payload.old_version_id, payload.new_version_id),
    )

    # Step 5: Save detected changes to SQLite
    saved_items: List[ChangeItem] = []
    breaking_count = 0
    non_breaking_count = 0
    cosmetic_count = 0

    for ch in raw_changes:
        cursor.execute(
            """
            INSERT INTO changes (api_id, old_version_id, new_version_id, endpoint, method, change_type, severity, description, details)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload.api_id,
                payload.old_version_id,
                payload.new_version_id,
                ch["endpoint"],
                ch["method"],
                ch["change_type"],
                ch["severity"],
                ch["description"],
                json.dumps(ch.get("details") or {}),
            ),
        )
        ch_id = cursor.lastrowid

        if ch["severity"] == "BREAKING":
            breaking_count += 1
        elif ch["severity"] == "NON_BREAKING":
            non_breaking_count += 1
        else:
            cosmetic_count += 1

        saved_items.append(
            ChangeItem(
                id=ch_id,
                api_id=payload.api_id,
                endpoint=ch["endpoint"],
                method=ch["method"],
                change_type=ch["change_type"],
                severity=ch["severity"],
                description=ch["description"],
                details=ch.get("details"),
            )
        )

    conn.commit()
    conn.close()

    summary = DiffSummary(
        total=len(saved_items),
        breaking=breaking_count,
        non_breaking=non_breaking_count,
        cosmetic=cosmetic_count,
    )

    return DiffResponse(
        api_id=payload.api_id,
        old_version_tag=old_row["version_tag"],
        new_version_tag=new_row["version_tag"],
        summary=summary,
        changes=saved_items,
    )


@router.get("", response_model=List[ChangeItem])
def list_changes(api_id: Optional[int] = Query(None, description="Optional API ID filter")):
    """
    Retrieves all detected changes stored in SQLite, optionally filtered by API ID.
    """
    conn = get_db()
    cursor = conn.cursor()

    if api_id:
        cursor.execute(
            """
            SELECT id, api_id, endpoint, method, change_type, severity, description, details, created_at
            FROM changes WHERE api_id = ? ORDER BY id DESC
            """,
            (api_id,),
        )
    else:
        cursor.execute(
            """
            SELECT id, api_id, endpoint, method, change_type, severity, description, details, created_at
            FROM changes ORDER BY id DESC
            """
        )

    rows = cursor.fetchall()
    conn.close()

    results: List[ChangeItem] = []
    for r in rows:
        det = None
        if "details" in r.keys() and r["details"]:
            try:
                det = json.loads(r["details"])
            except Exception:
                det = None
        results.append(
            ChangeItem(
                id=r["id"],
                api_id=r["api_id"],
                endpoint=r["endpoint"],
                method=r["method"],
                change_type=r["change_type"],
                severity=r["severity"],
                description=r["description"],
                details=det,
                created_at=str(r["created_at"]),
            )
        )
    return results
