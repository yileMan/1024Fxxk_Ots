from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.models.user import AuditLog


AUDIT_ACTIONS = {"insert", "update", "delete", "batch_upsert"}
SENSITIVE_KEYS = {
    "password", "password_hash", "cookie", "authorization", "token", "secret",
    "review_comment", "analysis_summary", "evidence_text", "raw_content",
}
MAX_DETAIL_STRING_LENGTH = 1000


def _safe_value(key: str, value: object) -> Any:
    lowered = key.lower()
    if isinstance(value, Mapping):
        return {str(child_key): _safe_value(str(child_key), child) for child_key, child in value.items()}
    if lowered in SENSITIVE_KEYS or lowered.endswith(("_password", "_secret", "_token")):
        return {"changed": True} if value is not None else None
    if isinstance(value, str):
        if len(value) > MAX_DETAIL_STRING_LENGTH:
            return {"changed": True, "length": len(value)}
        return value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_safe_value(key, child) for child in value]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(value)


def normalize_audit_detail(detail: dict[str, object] | None) -> dict[str, object] | None:
    if detail is None:
        return None
    normalized = {key: _safe_value(key, value) for key, value in detail.items()}
    normalized.setdefault("schema_version", "1.0")
    return normalized


def record_audit(
    session: Session, *, user_id: int | None, action: str, object_type: str,
    object_id: int | str | None, detail: dict[str, object] | None,
) -> None:
    if action not in AUDIT_ACTIONS:
        raise ValueError("不支持的审计动作")
    session.add(AuditLog(
        user_id=user_id,
        action=action,
        object_type=object_type,
        object_id=str(object_id) if object_id is not None else None,
        detail_json=normalize_audit_detail(detail),
    ))
