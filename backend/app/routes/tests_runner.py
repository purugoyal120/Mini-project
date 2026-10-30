"""
Automated Test Orchestrator Routes.
Runs regression tests, records results in SQLite, and provides dashboard metrics.
"""

from fastapi import APIRouter, Query, status
from typing import List, Optional
from ..database.db import get_db
from ..services.test_runner_service import run_comprehensive_tests

router = APIRouter(prefix="/api/tests", tags=["Automated Regression Testing"])


@router.post("/run")
def trigger_tests(
    api_id: Optional[int] = Query(None, description="Optional API ID"),
    adapter_id: Optional[int] = Query(None, description="Optional Adapter ID"),
):
    """
    Executes automated regression testing suite and logs results to SQLite.
    """
    results = run_comprehensive_tests(api_id=api_id, adapter_id=adapter_id)
    passed_count = sum(1 for r in results if r["status"] == "PASSED")
    total_count = len(results)

    return {
        "total_tests": total_count,
        "passed": passed_count,
        "failed": total_count - passed_count,
        "pass_rate_percent": round((passed_count / total_count) * 100, 1) if total_count > 0 else 0,
        "results": results,
    }


@router.get("/runs")
def list_test_runs(limit: int = Query(20, description="Max records to return")):
    """
    Retrieves recent test run logs from SQLite.
    """
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT id, adapter_id, test_name, status, details, executed_at
        FROM test_runs
        ORDER BY id DESC
        LIMIT ?
        """,
        (limit,),
    )
    rows = cursor.fetchall()
    conn.close()

    return [
        {
            "id": r["id"],
            "adapter_id": r["adapter_id"],
            "test_name": r["test_name"],
            "status": r["status"],
            "details": r["details"],
            "executed_at": str(r["executed_at"]),
        }
        for r in rows
    ]


@router.get("/summary")
def get_test_summary():
    """
    Returns high-level test metrics for dashboard KPI cards.
    """
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) AS count FROM test_runs")
    total_runs = cursor.fetchone()["count"]

    cursor.execute("SELECT COUNT(*) AS count FROM test_runs WHERE status = 'PASSED'")
    passed_runs = cursor.fetchone()["count"]

    conn.close()

    pass_rate = round((passed_runs / total_runs) * 100, 1) if total_runs > 0 else 100.0

    return {
        "total_runs": total_runs,
        "passed_runs": passed_runs,
        "failed_runs": total_runs - passed_runs,
        "pass_rate": pass_rate,
    }
