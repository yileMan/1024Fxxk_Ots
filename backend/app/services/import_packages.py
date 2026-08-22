from __future__ import annotations

import hashlib
import logging
import os
import uuid
from dataclasses import asdict
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.infrastructure.settings import Settings
from app.models.imports import ImportBatch
from app.repositories.import_packages import ImportPackageRepository
from app.services.package_validation import (
    DATA_FILES,
    FileStats,
    PackageLimits,
    PackageSummary,
    PackageValidationError,
    PackageValidationResult,
    ValidationIssue,
    errors_csv,
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

    async def validate_upload(self, upload: UploadFile, user_id: int) -> tuple[dict[str, object], bool]:
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
                with self._session_factory() as session:
                    known_ots_ids = self._repository.list_ots_ids(session)
                try:
                    result = validate_package(
                        temporary_path.read_bytes(),
                        upload.filename or "",
                        known_ots_ids,
                        limits=self._limits,
                    )
                except PackageValidationError as error:
                    result = self._hard_failure_result(error, placeholder)

                if result.batch_no and result.batch_no != placeholder:
                    existing_batch = self._existing_by_batch_no(result.batch_no)
                    if existing_batch is not None and existing_batch.id != batch.id:
                        self._delete_placeholder(batch.id)
                        return self._response(existing_batch, duplicate=True), False

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
                        return self._response(existing_batch, duplicate=True), False
                    raise
                logger.info(
                    "package_validation_completed batch_id=%s status=%s errors=%s",
                    batch.id,
                    batch.status,
                    result.total_error_count,
                )
                return self._response(batch, duplicate=False), True
            except Exception:
                logger.exception("package_validation_failed batch_id=%s", batch.id)
                self._cleanup_archive(archived_path)
                self._mark_internal_failure(batch.id)
                raise
        finally:
            await upload.close()
            temporary_path.unlink(missing_ok=True)

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
            errors = [ValidationIssue(**item) for item in batch.error_json.get("items", [])]
            if not errors:
                raise ImportPackageErrorsNotAvailableError()
            return errors_csv(errors)

    def _existing_by_sha(self, package_sha256: str) -> ImportBatch | None:
        with self._session_factory() as session:
            return self._repository.get_by_package_sha256(session, package_sha256)

    def _existing_by_batch_no(self, batch_no: str) -> ImportBatch | None:
        with self._session_factory() as session:
            return self._repository.get_by_batch_no(session, batch_no)

    def _create_uploaded(
        self,
        placeholder: str,
        file_name: str,
        package_sha256: str,
        user_id: int,
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

    def _mark_internal_failure(self, batch_id: int) -> None:
        try:
            with self._session_factory.begin() as session:
                batch = self._repository.get_by_id(session, batch_id)
                if batch is None or batch.status != "uploaded":
                    return
                issue = ValidationIssue(
                    "INTERNAL_ERROR",
                    "package.zip",
                    None,
                    None,
                    "校验服务异常终止",
                    None,
                )
                batch.status = "failed"
                batch.format_version = "unknown"
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
            batch.manifest_json = result.manifest
            batch.scope_coverage_json = result.scope_coverage or None
            batch.result_json = {
                "scope_export_id": result.scope_export_id,
                "scope_count": result.scope_count,
                "classification_basis": result.classification_basis,
                "final_import_diff": result.final_import_diff,
                "can_import": result.can_import,
                "summary": asdict(result.summary),
                "file_stats": {name: asdict(item) for name, item in result.file_stats.items()},
            }
            batch.error_json = {
                "items": [asdict(item) for item in result.errors],
                "total_count": result.total_error_count,
                "truncated_count": result.truncated_error_count,
            } if result.errors else None
            session.flush()
            return batch

    @staticmethod
    def _hard_failure_result(error: PackageValidationError, placeholder: str) -> PackageValidationResult:
        stats = {name: FileStats() for name in DATA_FILES}
        issue = ValidationIssue(error.code, "package.zip", None, None, str(error), None)
        return PackageValidationResult(
            False,
            placeholder,
            "unknown",
            None,
            0,
            None,
            [],
            [],
            stats,
            PackageSummary(0, 0, 0, 0, 0, 0),
            [issue],
            1,
            0,
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
            "scope_export_id": result.get("scope_export_id"),
            "scope_count": result.get("scope_count", 0),
            "classification_basis": result.get("classification_basis", "package_structure_v1"),
            "final_import_diff": result.get("final_import_diff", False),
            "can_import": result.get("can_import", False),
            "summary": result.get("summary", asdict(PackageSummary(0, 0, 0, 0, 0, 0))),
            "file_stats": result.get("file_stats", {name: asdict(FileStats()) for name in DATA_FILES}),
            "errors": list(error_json.get("items", []))[:100],
            "total_error_count": error_json.get("total_count", 0),
            "truncated_error_count": error_json.get("truncated_count", 0),
            "duplicate": duplicate,
        }
