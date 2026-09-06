from __future__ import annotations

import base64
import binascii
import json
import logging
import re
import shutil
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from app.infrastructure.settings import Settings
from app.models.imports import ImportBatch
from app.repositories.audit_operations import AuditOperationsRepository


logger = logging.getLogger("ots.operations")
OBJECT_TYPES = {
    "app_user", "user_product_scope", "product", "product_version", "ots_component",
    "product_ots", "import_batch", "vulnerability", "vulnerability_ots_match",
    "product_assessment",
}
STATUS_WEIGHT = {"ok": 0, "unknown": 1, "warning": 2, "error": 3}


class AuditLogNotFoundError(LookupError):
    pass


class InvalidAuditCursorError(ValueError):
    pass


class AuditOperationsService:
    def __init__(self, session_factory: sessionmaker) -> None:
        self._session_factory = session_factory
        self._repository = AuditOperationsRepository()

    @staticmethod
    def encode_cursor(created_at: datetime, audit_id: int) -> str:
        raw = f"{created_at.isoformat()}|{audit_id}".encode()
        return base64.urlsafe_b64encode(raw).decode().rstrip("=")

    @staticmethod
    def decode_cursor(cursor: str | None) -> tuple[datetime | None, int | None]:
        if cursor is None:
            return None, None
        try:
            padded = cursor + "=" * (-len(cursor) % 4)
            raw_time, raw_id = base64.urlsafe_b64decode(padded.encode()).decode().rsplit("|", 1)
            audit_id = int(raw_id)
            if audit_id <= 0:
                raise ValueError("invalid cursor id")
            return datetime.fromisoformat(raw_time), audit_id
        except (ValueError, UnicodeError, binascii.Error) as error:
            raise InvalidAuditCursorError() from error

    def list_logs(self, **filters: object) -> dict[str, object]:
        cursor_time, cursor_id = self.decode_cursor(filters.pop("cursor", None))
        limit = int(filters.pop("limit"))
        with self._session_factory() as session:
            rows, total = self._repository.list_logs(
                session, cursor_time=cursor_time, cursor_id=cursor_id, limit=limit, **filters
            )
            has_more = len(rows) > limit
            items = rows[:limit]
            next_cursor = None
            if has_more and items:
                next_cursor = self.encode_cursor(items[-1]["created_at"], int(items[-1]["id"]))
            return {
                "items": [
                    {**{key: value for key, value in item.items() if key != "detail"},
                     "detail_keys": sorted((item.get("detail") or {}).keys())}
                    for item in items
                ],
                "total": total, "next_cursor": next_cursor, "limit": limit,
            }

    def get_log(self, audit_log_id: int) -> dict[str, object]:
        with self._session_factory() as session:
            row = self._repository.get_log(session, audit_log_id)
            if row is None:
                raise AuditLogNotFoundError()
            return row


class SystemOperationsService:
    def __init__(self, session_factory: sessionmaker, settings: Settings) -> None:
        self._session_factory = session_factory
        self._settings = settings
        self._repository = AuditOperationsRepository()

    @staticmethod
    def _component(status: str, observed: datetime, summary: str, **values: object) -> dict[str, object]:
        return {"status": status, "observed_at": observed, "summary": summary, **values}

    def _application(self, observed: datetime) -> dict[str, object]:
        if not self._settings.app_version:
            return self._component("unknown", observed, "未提供构建版本")
        return self._component(
            "ok", observed, "应用版本可用", version=self._settings.app_version,
            commit=self._settings.app_commit,
        )

    def _database(self, observed: datetime) -> dict[str, object]:
        started = time.perf_counter()
        with self._session_factory() as session:
            session.execute(text("SELECT /*+ MAX_EXECUTION_TIME(2000) */ 1"))
        latency = round((time.perf_counter() - started) * 1000, 2)
        return self._component("ok", observed, "数据库连接正常", latency_ms=latency)

    def _disk(self, observed: datetime) -> dict[str, object]:
        total, _used, free = shutil.disk_usage(self._settings.persistent_root)
        used_percent = round((total - free) * 100 / total, 2) if total else 100.0
        if used_percent >= self._settings.disk_error_percent:
            status, summary = "error", "磁盘剩余空间严重不足"
        elif used_percent >= self._settings.disk_warning_percent:
            status, summary = "warning", "磁盘剩余空间不足"
        else:
            status, summary = "ok", "磁盘空间充足"
        return self._component(
            status, observed, summary, total_bytes=total, free_bytes=free,
            used_percent=used_percent,
        )

    @staticmethod
    def _parse_datetime(value: object) -> datetime:
        if not isinstance(value, str):
            raise ValueError("invalid datetime")
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)

    def _backup(self, observed: datetime) -> dict[str, object]:
        path = self._settings.backup_status_file
        if path is None:
            return self._component("unknown", observed, "备份状态未配置")
        if not path.exists():
            return self._component("unknown", observed, "暂无备份记录")
        if path.is_symlink() or path.stat().st_size > self._settings.backup_status_max_bytes:
            raise ValueError("unsafe backup status")
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or payload.get("schema_version") != "1.0":
            raise ValueError("unsupported backup status")
        status = payload.get("status")
        file_name = payload.get("file_name")
        size_bytes = payload.get("size_bytes")
        if status not in {"success", "failed"}:
            raise ValueError("invalid backup result")
        if (
            not isinstance(file_name, str) or len(file_name) > 255
            or Path(file_name).name != file_name or not file_name
        ):
            raise ValueError("invalid backup filename")
        if not isinstance(size_bytes, int) or size_bytes < 0:
            raise ValueError("invalid backup size")
        started_at = self._parse_datetime(payload.get("started_at"))
        finished_at = self._parse_datetime(payload.get("finished_at"))
        if finished_at < started_at:
            raise ValueError("invalid backup time")
        error_code = payload.get("error_code")
        if error_code is not None and (
            not isinstance(error_code, str)
            or re.fullmatch(r"[A-Z0-9_.-]{1,64}", error_code) is None
        ):
            raise ValueError("invalid backup error code")
        return self._component(
            "ok" if status == "success" else "error", observed,
            "最近备份成功" if status == "success" else "最近备份失败",
            started_at=started_at, finished_at=finished_at, file_name=file_name,
            size_bytes=size_bytes,
            error_code=error_code if status == "failed" else None,
        )

    @staticmethod
    def _batch(batch: ImportBatch | None, observed: datetime, *, failure: bool) -> dict[str, object]:
        if batch is None:
            return SystemOperationsService._component(
                "ok" if failure else "unknown", observed,
                "无失败记录" if failure else "暂无导入记录",
            )
        return SystemOperationsService._component(
            "error" if failure else ("ok" if batch.status == "succeeded" else "warning"),
            observed, "最近导入失败" if failure else "已读取最近导入状态",
            batch_no=batch.batch_no, batch_status=batch.status,
            started_at=batch.started_at, finished_at=batch.finished_at,
        )

    def _imports(self, observed: datetime) -> tuple[dict[str, object], dict[str, object]]:
        with self._session_factory() as session:
            latest = self._repository.latest_import(session)
            failure = self._repository.latest_failure(session)
            return self._batch(latest, observed, failure=False), self._batch(failure, observed, failure=True)

    def _safe(
        self, name: str, observed: datetime, probe: Callable[[datetime], dict[str, object]]
    ) -> dict[str, object]:
        started = time.perf_counter()
        try:
            return probe(observed)
        except Exception:
            logger.warning(
                "operation_probe_failed probe=%s duration_ms=%.2f",
                name, (time.perf_counter() - started) * 1000,
            )
            return self._component("error", observed, f"{name}状态不可用")

    def get_status(self) -> dict[str, object]:
        observed = datetime.now(UTC)
        application = self._safe("应用", observed, self._application)
        database = self._safe("数据库", observed, self._database)
        disk = self._safe("磁盘", observed, self._disk)
        backup = self._safe("备份", observed, self._backup)
        try:
            latest_import, latest_failure = self._imports(observed)
        except Exception:
            logger.warning("operation_probe_failed probe=import")
            latest_import = self._component("error", observed, "导入状态不可用")
            latest_failure = self._component("error", observed, "失败状态不可用")
        components = [application, database, disk, backup, latest_import, latest_failure]
        overall = max(components, key=lambda item: STATUS_WEIGHT[str(item["status"])])["status"]
        return {
            "overall_status": overall, "observed_at": observed,
            "application": application, "database": database, "disk": disk,
            "backup": backup, "latest_import": latest_import, "latest_failure": latest_failure,
        }
