"""
Pydantic Models for Request and Response validation.
Keeps data clean, type-checked, and self-documenting in Swagger UI.
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any


class ApiCreate(BaseModel):
    name: str = Field(..., description="Unique name of the API (e.g. Users Service)")
    description: Optional[str] = Field(None, description="Optional brief description")


class ApiResponse(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    created_at: str
    version_count: int = 0


class SpecVersionCreate(BaseModel):
    version_tag: str = Field(..., description="Version label, e.g., '1.0.0' or 'v1'")
    spec_content: str = Field(..., description="OpenAPI specification content (JSON or YAML string)")


class SpecVersionResponse(BaseModel):
    id: int
    api_id: int
    version_tag: str
    raw_spec: str
    created_at: str


class ChangeItem(BaseModel):
    id: Optional[int] = None
    api_id: Optional[int] = None
    endpoint: str
    method: str
    change_type: str
    severity: str
    description: str
    details: Optional[Dict[str, Any]] = None
    created_at: Optional[str] = None


class DiffSummary(BaseModel):
    total: int
    breaking: int
    non_breaking: int
    cosmetic: int


class DiffRequest(BaseModel):
    api_id: int
    old_version_id: int
    new_version_id: int


class DiffResponse(BaseModel):
    api_id: int
    old_version_tag: str
    new_version_tag: str
    summary: DiffSummary
    changes: List[ChangeItem]


class AdapterGenerateRequest(BaseModel):
    api_id: int = Field(..., description="ID of the API service")
    change_id: Optional[int] = Field(None, description="Optional specific change ID to solve")
    old_endpoint: Optional[str] = Field(None, description="Legacy endpoint path (e.g. /users)")
    new_endpoint: Optional[str] = Field(None, description="Target new endpoint path (e.g. /customers)")
    method: Optional[str] = Field("GET", description="HTTP method (default GET)")
    field_mappings: Optional[Dict[str, str]] = Field(None, description="Optional explicit field transformations, e.g., {'new_field': 'old_field'}")


class AdapterResponse(BaseModel):
    id: int
    api_id: int
    old_endpoint: str
    new_endpoint: str
    method: str
    status: str  # 'DRAFT', 'APPROVED', 'REJECTED', 'ACTIVE'
    adapter_code: str
    explanation: Optional[str] = None
    created_at: str


class AdapterUpdateRequest(BaseModel):
    adapter_code: str = Field(..., description="Updated adapter Python code reviewed by developer")


class DashboardStats(BaseModel):
    total_apis: int
    total_versions: int
    total_changes: int
    breaking_changes: int
    non_breaking_changes: int
    total_adapters: int
    recent_activities: List[dict] = []
