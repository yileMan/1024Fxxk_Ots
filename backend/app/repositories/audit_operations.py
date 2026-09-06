from __future__ import annotations

from datetime import datetime

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.models.imports import ImportBatch
from app.models.user import AppUser, AuditLog


class AuditOperationsRepository:
    @staticmethod
    def _filters(
        *, object_type: str | None, user_id: int | None, action: str | None,
        created_from: datetime | None, created_to: datetime | None,
    ) -> list[object]:
        clauses: list[object] = []
        if object_type is not None:
            clauses.append(AuditLog.object_type == object_type)
        if user_id is not None:
            clauses.append(AuditLog.user_id == user_id)
        if action is not None:
            clauses.append(AuditLog.action == action)
        if created_from is not None:
            clauses.append(AuditLog.created_at >= created_from)
        if created_to is not None:
            clauses.append(AuditLog.created_at <= created_to)
        return clauses

    def list_logs(
        self, session: Session, *, object_type: str | None, user_id: int | None,
        action: str | None, created_from: datetime | None, created_to: datetime | None,
        cursor_time: datetime | None, cursor_id: int | None, limit: int,
    ) -> tuple[list[dict[str, object]], int]:
        clauses = self._filters(
            object_type=object_type, user_id=user_id, action=action,
            created_from=created_from, created_to=created_to,
        )
        total = int(session.scalar(select(func.count(AuditLog.id)).where(*clauses)) or 0)
        if cursor_time is not None and cursor_id is not None:
            clauses.append(or_(
                AuditLog.created_at < cursor_time,
                and_(AuditLog.created_at == cursor_time, AuditLog.id < cursor_id),
            ))
        rows = session.execute(
            select(AuditLog, AppUser.display_name)
            .outerjoin(AppUser, AppUser.id == AuditLog.user_id)
            .where(*clauses)
            .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
            .limit(limit + 1)
        ).all()
        return [
            {
                "id": log.id, "user_id": log.user_id,
                "actor_display_name": display_name, "action": log.action,
                "object_type": log.object_type, "object_id": log.object_id,
                "detail": log.detail_json, "created_at": log.created_at,
            }
            for log, display_name in rows
        ], total

    def get_log(self, session: Session, audit_log_id: int) -> dict[str, object] | None:
        row = session.execute(
            select(AuditLog, AppUser.display_name)
            .outerjoin(AppUser, AppUser.id == AuditLog.user_id)
            .where(AuditLog.id == audit_log_id)
        ).one_or_none()
        if row is None:
            return None
        log, display_name = row
        return {
            "id": log.id, "user_id": log.user_id,
            "actor_display_name": display_name, "action": log.action,
            "object_type": log.object_type, "object_id": log.object_id,
            "detail": log.detail_json, "created_at": log.created_at,
        }

    def latest_import(self, session: Session) -> ImportBatch | None:
        return session.scalar(select(ImportBatch).order_by(ImportBatch.created_at.desc(), ImportBatch.id.desc()))

    def latest_failure(self, session: Session) -> ImportBatch | None:
        return session.scalar(
            select(ImportBatch).where(ImportBatch.status == "failed")
            .order_by(ImportBatch.created_at.desc(), ImportBatch.id.desc())
        )
