"""
API Registration and Specification Version Management Routes.
Handles creating APIs, uploading OpenAPI specs, and retrieving dashboard statistics.
"""

from fastapi import APIRouter, HTTPException, UploadFile, File, Form, status
from typing import List, Optional
import json

from ..database.db import get_db
from ..schemas.models import (
    ApiCreate,
    ApiResponse,
    SpecVersionCreate,
    SpecVersionResponse,
    DashboardStats,
)
from ..services.spec_service import (
    save_spec_version,
    get_spec_version,
    list_specs_for_api,
)

router = APIRouter(prefix="/api", tags=["APIs & Specifications"])


# ---------------------------------------------------------
# 1. Dashboard Statistics
# ---------------------------------------------------------
@router.get("/dashboard/stats", response_model=DashboardStats)
def get_dashboard_stats():
    """
    Returns real-time summary statistics for the dashboard directly from SQLite.
    """
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) AS count FROM apis")
    total_apis = cursor.fetchone()["count"]

    cursor.execute("SELECT COUNT(*) AS count FROM spec_versions")
    total_versions = cursor.fetchone()["count"]

    cursor.execute("SELECT COUNT(*) AS count FROM changes")
    total_changes = cursor.fetchone()["count"]

    cursor.execute("SELECT COUNT(*) AS count FROM changes WHERE severity = 'BREAKING'")
    breaking_changes = cursor.fetchone()["count"]

    cursor.execute("SELECT COUNT(*) AS count FROM changes WHERE severity != 'BREAKING'")
    non_breaking_changes = cursor.fetchone()["count"]

    cursor.execute("SELECT COUNT(*) AS count FROM adapters")
    total_adapters = cursor.fetchone()["count"]

    # Recent activities (latest 5 registered APIs + latest 5 uploaded versions)
    activities = []
    cursor.execute("SELECT id, name, created_at FROM apis ORDER BY id DESC LIMIT 5")
    for row in cursor.fetchall():
        activities.append({
            "type": "API_REGISTERED",
            "title": f"Registered API: {row['name']}",
            "time": row["created_at"],
        })

    cursor.execute("""
        SELECT v.id, v.version_tag, v.created_at, a.name AS api_name
        FROM spec_versions v
        JOIN apis a ON v.api_id = a.id
        ORDER BY v.id DESC LIMIT 5
    """)
    for row in cursor.fetchall():
        activities.append({
            "type": "VERSION_UPLOADED",
            "title": f"Uploaded {row['api_name']} (v{row['version_tag']})",
            "time": row["created_at"],
        })

    conn.close()

    return DashboardStats(
        total_apis=total_apis,
        total_versions=total_versions,
        total_changes=total_changes,
        breaking_changes=breaking_changes,
        non_breaking_changes=non_breaking_changes,
        total_adapters=total_adapters,
        recent_activities=activities,
    )


# ---------------------------------------------------------
# 2. Register and List APIs
# ---------------------------------------------------------
@router.post("/apis", response_model=ApiResponse, status_code=status.HTTP_201_CREATED)
def register_api(payload: ApiCreate):
    """
    Registers a new API service with a name and optional description.
    """
    conn = get_db()
    cursor = conn.cursor()

    try:
        cursor.execute(
            "INSERT INTO apis (name, description) VALUES (?, ?)",
            (payload.name.strip(), payload.description.strip() if payload.description else None),
        )
        conn.commit()
        api_id = cursor.lastrowid
        cursor.execute("SELECT id, name, description, created_at FROM apis WHERE id = ?", (api_id,))
        row = cursor.fetchone()
        return ApiResponse(
            id=row["id"],
            name=row["name"],
            description=row["description"],
            created_at=str(row["created_at"]),
            version_count=0,
        )
    except Exception as e:
        conn.rollback()
        if "UNIQUE constraint failed" in str(e):
            raise HTTPException(status_code=400, detail=f"API named '{payload.name}' already exists.")
        raise HTTPException(status_code=500, detail=f"Failed to register API: {str(e)}")
    finally:
        conn.close()


@router.get("/apis", response_model=List[ApiResponse])
def list_apis():
    """
    Returns a list of all registered APIs along with their uploaded version count.
    """
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT a.id, a.name, a.description, a.created_at,
               COUNT(v.id) AS version_count
        FROM apis a
        LEFT JOIN spec_versions v ON a.id = v.api_id
        GROUP BY a.id
        ORDER BY a.id DESC
    """)
    rows = cursor.fetchall()
    conn.close()

    return [
        ApiResponse(
            id=r["id"],
            name=r["name"],
            description=r["description"],
            created_at=str(r["created_at"]),
            version_count=r["version_count"],
        )
        for r in rows
    ]


@router.get("/apis/{api_id}", response_model=ApiResponse)
def get_api(api_id: int):
    """
    Retrieves details for a specific API by its ID.
    """
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT a.id, a.name, a.description, a.created_at,
               COUNT(v.id) AS version_count
        FROM apis a
        LEFT JOIN spec_versions v ON a.id = v.api_id
        WHERE a.id = ?
        GROUP BY a.id
    """, (api_id,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        raise HTTPException(status_code=404, detail=f"API with ID {api_id} not found.")

    return ApiResponse(
        id=row["id"],
        name=row["name"],
        description=row["description"],
        created_at=str(row["created_at"]),
        version_count=row["version_count"],
    )


# ---------------------------------------------------------
# 3. Spec Version Upload (JSON body or File Upload)
# ---------------------------------------------------------
@router.post("/apis/{api_id}/versions", response_model=SpecVersionResponse, status_code=status.HTTP_201_CREATED)
def upload_spec_version_json(api_id: int, payload: SpecVersionCreate):
    """
    Uploads an OpenAPI specification via JSON payload.
    """
    try:
        new_version_id = save_spec_version(api_id, payload.version_tag, payload.spec_content)
        saved = get_spec_version(new_version_id)
        return SpecVersionResponse(
            id=saved["id"],
            api_id=saved["api_id"],
            version_tag=saved["version_tag"],
            raw_spec=saved["raw_spec"],
            created_at=str(saved["created_at"]),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")


@router.post("/apis/{api_id}/versions/upload-file", response_model=SpecVersionResponse, status_code=status.HTTP_201_CREATED)
async def upload_spec_version_file(
    api_id: int,
    version_tag: str = Form(...),
    file: UploadFile = File(...),
):
    """
    Uploads an OpenAPI specification by directly uploading a .json or .yaml file.
    """
    try:
        content_bytes = await file.read()
        content_str = content_bytes.decode("utf-8")
        new_version_id = save_spec_version(api_id, version_tag, content_str)
        saved = get_spec_version(new_version_id)
        return SpecVersionResponse(
            id=saved["id"],
            api_id=saved["api_id"],
            version_tag=saved["version_tag"],
            raw_spec=saved["raw_spec"],
            created_at=str(saved["created_at"]),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="Uploaded file is not a valid UTF-8 text file.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")


@router.get("/apis/{api_id}/versions", response_model=List[dict])
def list_versions(api_id: int):
    """
    Lists all specification versions uploaded for an API.
    """
    # Verify API exists
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM apis WHERE id = ?", (api_id,))
    if not cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail=f"API with ID {api_id} not found.")
    conn.close()

    return list_specs_for_api(api_id)


# ---------------------------------------------------------
# Database Reset & Seed Controls
# ---------------------------------------------------------
@router.post("/database/reset")
def reset_database():
    """
    Clears all database tables to provide a completely blank slate for live demonstration.
    """
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM test_runs")
    cursor.execute("DELETE FROM adapters")
    cursor.execute("DELETE FROM changes")
    cursor.execute("DELETE FROM spec_versions")
    cursor.execute("DELETE FROM apis")
    conn.commit()
    conn.close()
    return {"message": "Database reset to blank successfully. Ready for live ingestion."}


@router.post("/database/seed")
def seed_database():
    """
    Seeds the 3 verified sample services (Identity, E-Commerce, Banking).
    """
    import subprocess
    import sys
    from pathlib import Path

    script = Path("setup_demo_db.py").resolve()
    if script.exists():
        subprocess.run([sys.executable, str(script)], check=True)
        return {"message": "Database seeded with 3 diverse services."}
    return {"message": "Seed script not found."}


@router.get("/apis/{api_id}/versions/{version_id}", response_model=SpecVersionResponse)
def get_version(api_id: int, version_id: int):
    """
    Retrieves full details and raw OpenAPI content of a specific version.
    """
    try:
        spec = get_spec_version(version_id)
        if spec["api_id"] != api_id:
            raise HTTPException(status_code=404, detail="Version does not belong to this API.")
        return SpecVersionResponse(
            id=spec["id"],
            api_id=spec["api_id"],
            version_tag=spec["version_tag"],
            raw_spec=spec["raw_spec"],
            created_at=str(spec["created_at"]),
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
