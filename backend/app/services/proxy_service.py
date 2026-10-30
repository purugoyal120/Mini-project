"""
APIBridge AI - Dynamic Proxy Engine
Loads approved adapters from the database, executes transformation logic,
and forwards requests between legacy clients and modern API endpoints.
"""

import httpx
from typing import Dict, Any, Tuple, Optional, Callable
from ..database.db import get_db


def load_adapter_executables(api_id: int, path: str, method: str) -> Optional[Tuple[int, Callable, Callable]]:
    """
    Finds and executes the approved adapter for the given API, path, and method.
    Returns (adapter_id, transform_request_fn, transform_response_fn) or None if no active adapter.
    """
    normalized_path = "/" + path.strip("/")
    method = method.upper()

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT id, adapter_code, old_endpoint, new_endpoint, method, status
        FROM adapters
        WHERE api_id = ? AND status IN ('APPROVED', 'ACTIVE')
        ORDER BY id DESC
        """,
        (api_id,),
    )
    rows = cursor.fetchall()
    conn.close()

    for row in rows:
        adapter_old_ep = "/" + row["old_endpoint"].strip("/")
        if adapter_old_ep == normalized_path:
            code = row["adapter_code"]
            scope = {}
            try:
                exec(code, scope)
                req_fn = scope.get("transform_request")
                res_fn = scope.get("transform_response")

                if req_fn and res_fn:
                    return row["id"], req_fn, res_fn
            except Exception as e:
                print(f"[ProxyService] Error compiling adapter {row['id']}: {e}")

    return None


async def execute_upstream_request(
    target_url: str,
    method: str,
    headers: Dict[str, str],
    query_params: Dict[str, Any],
    body: Optional[Any] = None,
    app_instance: Optional[Any] = None,
) -> Tuple[int, Any, Dict[str, str]]:
    """
    Forwards the transformed request to the target destination.
    Uses in-process ASGITransport if app_instance is available, avoiding network/port lockups.
    """
    forward_headers = {
        k: v for k, v in headers.items()
        if k.lower() not in ("host", "content-length", "transfer-encoding", "connection")
    }

    client_kwargs = {"timeout": 10.0}
    if app_instance is not None:
        client_kwargs["transport"] = httpx.ASGITransport(app=app_instance)

    async with httpx.AsyncClient(**client_kwargs) as client:
        req_kwargs: Dict[str, Any] = {
            "method": method,
            "url": target_url,
            "headers": forward_headers,
            "params": query_params,
        }
        if body is not None and method in ("POST", "PUT", "PATCH"):
            req_kwargs["json"] = body

        resp = await client.request(**req_kwargs)

        try:
            resp_data = resp.json()
        except Exception:
            resp_data = resp.text

        return resp.status_code, resp_data, dict(resp.headers)
