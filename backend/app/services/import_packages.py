from __future__ import annotations

import hashlib
import logging
import os
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.infrastructure.settings import Settings
from app.models.imports import ImportBatch, Vulnerability
from app.models.user import AuditLog
from app.repositories.import_packages import ImportPackageRepository
from app.services.package_validation import (
    DATA_FILES,
    ExistingVulnerability,
    FileStats,
    PackageLimits,
    PackageSummary,
    PackageValidationError,
    PackageValidationResult,
    ValidationIssue,
    VulnerabilityRecord,
    errors_csv,
    select_cvss31,
    validate_package,
)


logger = logging.getLogger("ots.import_packages")
READ_CHUNK_SIZE = 64 * 1024


class ImportPackageNotFoundError(LookupError):
    pass


class ImportPackageErrorsNotAvailableError(ValueError):
    pass


class ImportPackageUploadTooLargeError(ValueError):
    pass


class ImportPackageStateError(ValueError):
    pass


class ImportPackageConflictError(ValueError):
    pass


class ImportPackageBatchConflictError(ValueError):
    def __init__(self, batch_id: int, existing_sha: str, incoming_sha: str) -> None:
        super().__init__("相同批次号对应不同数据包")
        self.batch_id = batch_id
        self.existing_sha_prefix = existing_sha[:12]
        self.incoming_sha_prefix = incoming_sha[:12]


class ImportPackageService:
    def __init__(self, session_factory: sessionmaker, settings: Settings) -> None:
        self._session_factory = session_factory
        self._settings = settings
        self._repository = ImportPackageRepository()
        self._limits = PackageLimits(
            max_upload_bytes=settings.import_max_upload_bytes,
            max_member_bytes=settings.import_max_member_bytes,
            max_total_uncompressed_bytes=settings.import_max_total_bytes,
            max_compression_ratio=settings.import_max_compression_ratio,
            max_csv_rows=settings.import_max_csv_rows,
            max_field_bytes=settings.import_max_field_bytes,
            max_errors=settings.import_max_errors,
        )

    async def validate_upload(
        self, upload: UploadFile, user_id: int
    ) -> tuple[dict[str, object], bool]:
        self._settings.import_temp_dir.mkdir(parents=True, exist_ok=True)
        self._settings.import_archive_dir.mkdir(parents=True, exist_ok=True)
        temporary_path = self._settings.import_temp_dir / f"{uuid.uuid4()}.upload"
        digest = hashlib.sha256()
        total = 0
        try:
            with temporary_path.open("xb") as output:
                while chunk := await upload.read(READ_CHUNK_SIZE):
                    total += len(chunk)
                    if total > self._limits.max_upload_bytes:
                        raise ImportPackageUploadTooLargeError()
                    digest.update(chunk)
                    output.write(chunk)
            package_sha256 = digest.hexdigest()
            existing = self._existing_by_sha(package_sha256)
            if existing is not None:
                return self._response(existing, duplicate=True), False

            placeholder = f"upload:{uuid.uuid4()}"
            batch, created = self._create_uploaded(
                placeholder,
                (Path(upload.filename or "package.zip").name or "package.zip")[:255],
                package_sha256,
                user_id,
            )
            if not created:
                return self._response(batch, duplicate=True), False
            archived_path: Path | None = None
            try:
                try:
                    result = self._validate_against_database(
                        temporary_path.read_bytes(), upload.filename or ""
                    )
                except PackageValidationError as error:
                    result = self._hard_failure_result(error, placeholder)

                if result.batch_no and result.batch_no != placeholder:
                    existing_batch = self._existing_by_batch_no(result.batch_no)
                    if existing_batch is not None and existing_batch.id != batch.id:
                        self._delete_placeholder(batch.id)
                        raise ImportPackageBatchConflictError(
                            existing_batch.id,
                            existing_batch.package_sha256,
                            package_sha256,
                        )

                archive_relative: str | None = None
                if result.is_valid:
                    archive_relative = f"{batch.id}/package.zip"
                    archived_path = self._settings.import_archive_dir / archive_relative
                    archived_path.parent.mkdir(parents=True, exist_ok=True)
                    os.replace(temporary_path, archived_path)
                try:
                    batch = self._finish_batch(batch.id, result, archive_relative)
                except IntegrityError:
                    self._cleanup_archive(archived_path)
                    existing_batch = self._existing_by_batch_no(result.batch_no or "")
                    if existing_batch is not None and existing_batch.id != batch.id:
                        self._delete_placeholder(batch.id)
                        raise ImportPackageBatchConflictError(
                            existing_batch.id,
                            existing_batch.package_sha256,
                            package_sha256,
                        )
                    raise
                logger.info(
                    "package_validation_completed batch_id=%s status=%s records=%s errors=%s",
                    batch.id,
                    batch.status,
                    result.summary.total,
                    result.total_error_count,
                )
                return self._response(batch, duplicate=False), True
            except ImportPackageBatchConflictError:
                self._cleanup_archive(archived_path)
                raise
            except Exception:
                logger.exception("package_validation_failed batch_id=%s", batch.id)
                self._cleanup_archive(archived_path)
                self._mark_internal_failure(batch.id)
                raise
        finally:
            await upload.close()
            temporary_path.unlink(missing_ok=True)

    def confirm(self, batch_id: int, user_id: int) -> dict[str, object]:
        conflict = False
        response: dict[str, object] | None = None
        try:
            with self._session_factory.begin() as session:
                batch = session.scalar(
                    select(ImportBatch)
                    .where(ImportBatch.id == batch_id)
                    .with_for_update()
                )
                if batch is None:
                    raise ImportPackageNotFoundError()
                if batch.status == "succeeded":
                    return self._response(batch, duplicate=True)
                if batch.status != "validated":
                    raise ImportPackageStateError()
                if not batch.archive_path:
                    raise RuntimeError("validated batch archive is missing")
                archive_path = self._settings.import_archive_dir / batch.archive_path
                package = archive_path.read_bytes()
                existing = self._existing_for_package(session, package, batch.package_file_name)
                result = validate_package(
                    package,
                    batch.package_file_name,
                    existing=existing,
                    limits=self._limits,
                )
                if not result.is_valid or result.summary.conflict or result.summary.error:
                    conflict = True
                    batch.status = "failed"
                    batch.finished_at = datetime.now(timezone.utc)
                    batch.error_json = {
                        "items": [asdict(item) for item in result.errors],
                        "total_count": result.total_error_count,
                        "truncated_count": result.truncated_error_count,
                    }
                    batch.result_json = self._result_json(result, final_import_diff=True)
                    response = self._response(batch, duplicate=False)
                else:
                    batch.status = "importing"
                    batch.started_at = datetime.now(timezone.utc)
                    session.flush()
                    self._apply_records(session, result.records, batch.id)
                    batch.status = "succeeded"
                    batch.finished_at = datetime.now(timezone.utc)
                    batch.result_json = self._result_json(result, final_import_diff=True)
                    batch.error_json = None
                    session.add(
                        AuditLog(
                            user_id=user_id,
                            action="batch_upsert",
                            object_type="vulnerability",
                            object_id=str(batch.id),
                            detail_json={
                                "batch_no": batch.batch_no,
                                "new": result.summary.new,
                                "update": result.summary.update,
                                "duplicate": result.summary.duplicate,
                                "rejected": sum(
                                    1 for item in result.records if item.vuln_status.lower() == "rejected"
                                ),
                            },
                        )
                    )
                    session.flush()
                    response = self._response(batch, duplicate=False)
        except (ImportPackageNotFoundError, ImportPackageStateError):
            raise
        except Exception:
            self._mark_confirmation_failure(batch_id)
            raise
        if conflict:
            raise ImportPackageConflictError()
        assert response is not None
        logger.info("package_import_completed batch_id=%s", batch_id)
        return response

    def get(self, batch_id: int) -> dict[str, object]:
        with self._session_factory() as session:
            batch = self._repository.get_by_id(session, batch_id)
            if batch is None:
                raise ImportPackageNotFoundError()
            return self._response(batch, duplicate=False)

    def error_file(self, batch_id: int) -> bytes:
        with self._session_factory() as session:
            batch = self._repository.get_by_id(session, batch_id)
            if batch is None:
                raise ImportPackageNotFoundError()
            if batch.status != "failed" or not isinstance(batch.error_json, dict):
                raise ImportPackageErrorsNotAvailableError()
            errors = [
                ValidationIssue(**item) for item in batch.error_json.get("items", [])
            ]
            if not errors:
                raise ImportPackageErrorsNotAvailableError()
            return errors_csv(errors)

    def _validate_against_database(
        self, package: bytes, file_name: str
    ) -> PackageValidationResult:
        preliminary = validate_package(package, file_name, limits=self._limits)
        if not preliminary.records:
            return preliminary
        with self._session_factory() as session:
            current = self._repository.list_vulnerabilities(
                session, {record.cve_id for record in preliminary.records}
            )
            existing = {
                cve_id: ExistingVulnerability(
                    content_sha256=item.content_sha256,
                    source_modified_at=item.source_modified_at,
                )
                for cve_id, item in current.items()
            }
        return validate_package(
            package, file_name, existing=existing, limits=self._limits
        )

    def _existing_for_package(
        self, session: Session, package: bytes, file_name: str
    ) -> dict[str, ExistingVulnerability]:
        preliminary = validate_package(package, file_name, limits=self._limits)
        current = self._repository.list_vulnerabilities(
            session, {record.cve_id for record in preliminary.records}
        )
        return {
            cve_id: ExistingVulnerability(item.content_sha256, item.source_modified_at)
            for cve_id, item in current.items()
        }

    def _apply_records(
        self, session: Session, records: list[VulnerabilityRecord], batch_id: int
    ) -> None:
        current = self._repository.list_vulnerabilities(
            session, {record.cve_id for record in records}
        )
        for record in records:
            vulnerability = current.get(record.cve_id)
            if vulnerability is not None and vulnerability.content_sha256 == record.content_sha256:
                continue
            score, severity, vector, source = select_cvss31(record.cvss)
            values = {
                "source_identifier": record.source_identifier,
                "source_status": record.vuln_status,
                "description": record.description,
                "published_at": record.published_at,
                "source_modified_at": record.last_modified_at,
                "cwe_json": record.cwes,
                "affected_ranges_json": record.affected_software,
                "references_json": record.references,
                "cvss_json": record.cvss,
                "configurations_json": record.configurations,
                "cvss31_score": score,
                "cvss31_severity": severity,
                "cvss31_vector": vector,
                "cvss31_source": source,
                "import_batch_id": batch_id,
                "content_sha256": record.content_sha256,
            }
            if vulnerability is None:
                vulnerability = Vulnerability(
                    cve_id=record.cve_id,
                    is_kev=False,
                    **values,
                )
                session.add(vulnerability)
            else:
                for name, value in values.items():
                    setattr(vulnerability, name, value)

    def _existing_by_sha(self, package_sha256: str) -> ImportBatch | None:
        with self._session_factory() as session:
            return self._repository.get_by_package_sha256(session, package_sha256)

    def _existing_by_batch_no(self, batch_no: str) -> ImportBatch | None:
        with self._session_factory() as session:
            return self._repository.get_by_batch_no(session, batch_no)

    def _create_uploaded(
        self, placeholder: str, file_name: str, package_sha256: str, user_id: int
    ) -> tuple[ImportBatch, bool]:
        try:
            with self._session_factory.begin() as session:
                batch = ImportBatch(
                    batch_no=placeholder,
                    format_version="pending",
                    package_file_name=file_name,
                    package_sha256=package_sha256,
                    status="uploaded",
                    imported_by=user_id,
                )
                session.add(batch)
                session.flush()
                return batch, True
        except IntegrityError:
            existing = self._existing_by_sha(package_sha256)
            if existing is None:
                raise
            return existing, False

    def _delete_placeholder(self, batch_id: int) -> None:
        with self._session_factory.begin() as session:
            batch = self._repository.get_by_id(session, batch_id)
            if batch is not None and batch.status == "uploaded":
                session.delete(batch)

    def _finish_batch(
        self,
        batch_id: int,
        result: PackageValidationResult,
        archive_relative: str | None,
    ) -> ImportBatch:
        with self._session_factory.begin() as session:
            batch = self._repository.get_by_id(session, batch_id)
            if batch is None:
                raise ImportPackageNotFoundError()
            batch.batch_no = result.batch_no or batch.batch_no
            batch.format_version = result.format_version or "unknown"
            batch.status = "validated" if result.is_valid else "failed"
            batch.archive_path = archive_relative
            batch.covered_from = result.window_start
            batch.covered_to = result.window_end
            batch.manifest_json = result.manifest
            batch.scope_coverage_json = None
            batch.result_json = self._result_json(result, final_import_diff=False)
            batch.error_json = (
                {
                    "items": [asdict(item) for item in result.errors],
                    "total_count": result.total_error_count,
                    "truncated_count": result.truncated_error_count,
                }
                if result.errors
                else None
            )
            session.flush()
            return batch

    @staticmethod
    def _result_json(
        result: PackageValidationResult, *, final_import_diff: bool
    ) -> dict[str, object]:
        return {
            "source_name": result.source_name,
            "source_release": result.source_release,
            "window_start": result.window_start.isoformat() if result.window_start else None,
            "window_end": result.window_end.isoformat() if result.window_end else None,
            "classification_basis": result.classification_basis,
            "final_import_diff": final_import_diff,
            "can_import": result.is_valid and not final_import_diff,
            "internal_matching_pending": final_import_diff and result.is_valid,
            "summary": asdict(result.summary),
            "file_stats": {
                name: asdict(item) for name, item in result.file_stats.items()
            },
        }

    def _mark_internal_failure(self, batch_id: int) -> None:
        issue = ValidationIssue(
            "INTERNAL_ERROR", "package.zip", None, None, "校验服务异常终止", None
        )
        self._mark_failed(batch_id, issue)

    def _mark_confirmation_failure(self, batch_id: int) -> None:
        issue = ValidationIssue(
            "PACKAGE_IMPORT_FAILED",
            "package.zip",
            None,
            None,
            "确认导入事务失败",
            None,
        )
        self._mark_failed(batch_id, issue)

    def _mark_failed(self, batch_id: int, issue: ValidationIssue) -> None:
        try:
            with self._session_factory.begin() as session:
                batch = self._repository.get_by_id(session, batch_id)
                if batch is None or batch.status == "succeeded":
                    return
                batch.status = "failed"
                batch.finished_at = datetime.now(timezone.utc)
                batch.error_json = {
                    "items": [asdict(issue)],
                    "total_count": 1,
                    "truncated_count": 0,
                }
        except Exception:
            logger.exception("package_failure_state_update_failed batch_id=%s", batch_id)

    @staticmethod
    def _cleanup_archive(archive_path: Path | None) -> None:
        if archive_path is None:
            return
        archive_path.unlink(missing_ok=True)
        try:
            archive_path.parent.rmdir()
        except OSError:
            pass

    @staticmethod
    def _hard_failure_result(
        error: PackageValidationError, placeholder: str
    ) -> PackageValidationResult:
        stats = {name: FileStats() for name in DATA_FILES}
        issue = ValidationIssue(error.code, "package.zip", None, None, str(error), None)
        return PackageValidationResult(
            is_valid=False,
            batch_no=placeholder,
            format_version="unknown",
            source_name=None,
            source_release=None,
            window_start=None,
            window_end=None,
            manifest=None,
            file_stats=stats,
            summary=PackageSummary(0, 0, 0, 0, 0, 0),
            errors=[issue],
            total_error_count=1,
            truncated_error_count=0,
        )

    @staticmethod
    def _response(batch: ImportBatch, *, duplicate: bool) -> dict[str, object]:
        result = batch.result_json if isinstance(batch.result_json, dict) else {}
        error_json = batch.error_json if isinstance(batch.error_json, dict) else {}
        return {
            "id": batch.id,
            "batch_no": batch.batch_no,
            "format_version": batch.format_version,
            "package_file_name": batch.package_file_name,
            "package_sha256": batch.package_sha256,
            "status": batch.status,
            "source_name": result.get("source_name"),
            "source_release": result.get("source_release"),
            "window_start": result.get("window_start"),
            "window_end": result.get("window_end"),
            "classification_basis": result.get(
                "classification_basis", "vulnerability_current_facts_v1"
            ),
            "final_import_diff": result.get("final_import_diff", False),
            "can_import": result.get("can_import", False),
            "internal_matching_pending": result.get(
                "internal_matching_pending", batch.status == "succeeded"
            ),
            "summary": result.get(
                "summary", asdict(PackageSummary(0, 0, 0, 0, 0, 0))
            ),
            "file_stats": result.get(
                "file_stats", {name: asdict(FileStats()) for name in DATA_FILES}
            ),
            "errors": list(error_json.get("items", []))[:100],
            "total_error_count": error_json.get("total_count", 0),
            "truncated_error_count": error_json.get("truncated_count", 0),
            "duplicate": duplicate,
        }
