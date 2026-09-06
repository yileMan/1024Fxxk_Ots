from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.api.authorization import require_admin
from app.schemas.audit_operations import (
    AuditLogDetailResponse, AuditLogPageResponse, SystemOperationsResponse,
)
from app.services.audit_operations import (
    OBJECT_TYPES, AuditLogNotFoundError, AuditOperationsService,
    InvalidAuditCursorError, SystemOperationsService,
)
from app.services.authentication import PublicUser


router = APIRouter(tags=["audit-and-system-operations"])


def _normalized(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.astimezone(UTC) if value.tzinfo is not None else value.replace(tzinfo=UTC)


@router.get("/audit-logs", response_model=AuditLogPageResponse)
def list_audit_logs(
    request: Request,
    _admin: PublicUser = Depends(require_admin),
    object_type: str | None = None,
    user_id: int | None = Query(None, ge=1),
    action: Literal["insert", "update", "delete", "batch_upsert"] | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    cursor: str | None = Query(None, max_length=500),
    limit: int = Query(20, ge=1, le=100),
) -> AuditLogPageResponse:
    if object_type is not None and object_type not in OBJECT_TYPES:
        raise HTTPException(422, detail={"code": "VALIDATION_ERROR", "message": "对象类型无效"})
    start, end = _normalized(created_from), _normalized(created_to)
    if start is not None and end is not None and start > end:
        raise HTTPException(422, detail={"code": "VALIDATION_ERROR", "message": "时间范围无效"})
    service: AuditOperationsService = request.app.state.audit_operations_service
    try:
        result = service.list_logs(
            object_type=object_type, user_id=user_id, action=action,
            created_from=start, created_to=end, cursor=cursor, limit=limit,
        )
    except InvalidAuditCursorError as error:
        raise HTTPException(422, detail={"code": "VALIDATION_ERROR", "message": "分页游标无效"}) from error
    return AuditLogPageResponse.model_validate(result)


@router.get("/audit-logs/{audit_log_id}", response_model=AuditLogDetailResponse)
def get_audit_log(
    audit_log_id: int, request: Request, _admin: PublicUser = Depends(require_admin),
) -> AuditLogDetailResponse:
    try:
        return AuditLogDetailResponse.model_validate(
            request.app.state.audit_operations_service.get_log(audit_log_id)
        )
    except AuditLogNotFoundError as error:
        raise HTTPException(404, detail={"code": "AUDIT_LOG_NOT_FOUND", "message": "变更记录不存在"}) from error


@router.get("/system/operations", response_model=SystemOperationsResponse)
def system_operations(
    request: Request, _admin: PublicUser = Depends(require_admin),
) -> SystemOperationsResponse:
    service: SystemOperationsService = request.app.state.system_operations_service
    return SystemOperationsResponse.model_validate(service.get_status())
