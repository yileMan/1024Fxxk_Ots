from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel


AuditAction = Literal["insert", "update", "delete", "batch_upsert"]
OperationStatus = Literal["ok", "warning", "error", "unknown"]


class AuditLogListItemResponse(BaseModel):
    id: int
    user_id: int | None
    actor_display_name: str | None
    action: AuditAction
    object_type: str
    object_id: str | None
    detail_keys: list[str]
    created_at: datetime


class AuditLogPageResponse(BaseModel):
    items: list[AuditLogListItemResponse]
    total: int
    next_cursor: str | None
    limit: int


class AuditLogDetailResponse(BaseModel):
    id: int
    user_id: int | None
    actor_display_name: str | None
    action: AuditAction
    object_type: str
    object_id: str | None
    detail: dict[str, Any] | None
    created_at: datetime


class OperationComponentResponse(BaseModel):
    status: OperationStatus
    observed_at: datetime
    summary: str
    version: str | None = None
    commit: str | None = None
    latency_ms: float | None = None
    total_bytes: int | None = None
    free_bytes: int | None = None
    used_percent: float | None = None
    batch_no: str | None = None
    batch_status: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    file_name: str | None = None
    size_bytes: int | None = None
    error_code: str | None = None


class SystemOperationsResponse(BaseModel):
    overall_status: OperationStatus
    observed_at: datetime
    application: OperationComponentResponse
    database: OperationComponentResponse
    disk: OperationComponentResponse
    backup: OperationComponentResponse
    latest_import: OperationComponentResponse
    latest_failure: OperationComponentResponse
