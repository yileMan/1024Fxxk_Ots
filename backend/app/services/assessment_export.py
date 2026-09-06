from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import UTC, datetime
from io import StringIO
from typing import Iterator

from sqlalchemy.orm import Session, sessionmaker

from app.repositories.assessment_export import AssessmentExportRepository
from app.services.authentication import PublicUser


CSV_HEADERS = (
    "产品", "产品版本", "OTS 名称", "OTS 版本", "CVE", "来源评分", "来源向量",
    "环境评分", "环境向量", "适用性", "分析依据", "处置建议", "评估状态",
    "提交人", "提交时间", "审核结论", "审核人", "审核时间", "审核意见",
)
BATCH_SIZE = 200
TEXT_COLUMNS = {0, 1, 2, 3, 4, 6, 8, 9, 10, 11, 12, 13, 15, 16, 18}


class AssessmentExportError(ValueError):
    code = "ASSESSMENT_EXPORT_ERROR"


class AssessmentExportForbiddenError(AssessmentExportError):
    code = "ASSESSMENT_EXPORT_FORBIDDEN"


class AssessmentExportScopeNotFoundError(AssessmentExportError):
    code = "ASSESSMENT_EXPORT_SCOPE_NOT_FOUND"


class AssessmentExportEmptyError(AssessmentExportError):
    code = "ASSESSMENT_EXPORT_EMPTY"


@dataclass(frozen=True)
class AssessmentExportPreview:
    product_version_id: int
    product_name: str
    version_no: str
    ots_id: int
    ots_name: str
    ots_version: str
    row_count: int
    previewed_at: datetime


@dataclass(frozen=True)
class AssessmentCsvExport:
    chunks: Iterator[bytes]
    file_name: str


class AssessmentExportService:
    def __init__(self, session_factory: sessionmaker) -> None:
        self._session_factory = session_factory
        self._repository = AssessmentExportRepository()

    def preview(self, user: PublicUser, version_id: int, ots_id: int) -> AssessmentExportPreview:
        with self._session_factory() as session:
            scope = self._resolve_scope(session, user, version_id, ots_id)
            return self._preview(session, scope)

    def export_csv(self, user: PublicUser, version_id: int, ots_id: int) -> AssessmentCsvExport:
        session = self._session_factory()
        try:
            scope = self._resolve_scope(session, user, version_id, ots_id)
            first = self._repository.list_rows(session, int(scope["product_ots_id"]), after_cve=None, after_id=None, limit=BATCH_SIZE)
            if not first:
                raise AssessmentExportEmptyError()
        except Exception:
            session.close()
            raise

        file_name = f"assessment_export_pv-{version_id}_ots-{ots_id}_{datetime.now(UTC):%Y%m%d}.csv"
        return AssessmentCsvExport(self._stream(session, int(scope["product_ots_id"]), first), file_name)

    def _resolve_scope(self, session: Session, user: PublicUser, version_id: int, ots_id: int) -> dict[str, object]:
        if "admin" not in user.roles and version_id not in self._repository.effective_version_ids(session, user.id):
            raise AssessmentExportForbiddenError()
        scope = self._repository.get_scope(session, version_id, ots_id)
        if scope is None:
            raise AssessmentExportScopeNotFoundError()
        return scope

    def _preview(self, session: Session, scope: dict[str, object]) -> AssessmentExportPreview:
        return AssessmentExportPreview(
            product_version_id=int(scope["product_version_id"]), product_name=str(scope["product_name"]),
            version_no=str(scope["version_no"]), ots_id=int(scope["ots_id"]),
            ots_name=str(scope["ots_name"]), ots_version=str(scope["ots_version"]),
            row_count=self._repository.count_rows(session, int(scope["product_ots_id"])),
            previewed_at=datetime.now(UTC),
        )

    def _stream(self, session: Session, product_ots_id: int, first: list[dict[str, object]]) -> Iterator[bytes]:
        try:
            yield b"\xef\xbb\xbf" + self._csv_line(CSV_HEADERS)
            batch = first
            while batch:
                for row in batch:
                    yield self._csv_line(self._values(row))
                last = batch[-1]
                batch = self._repository.list_rows(
                    session, product_ots_id, after_cve=str(last["cve_id"]),
                    after_id=int(last["assessment_id"]), limit=BATCH_SIZE,
                )
        finally:
            session.close()

    @staticmethod
    def _values(row: dict[str, object]) -> tuple[object, ...]:
        return (
            row["product_name"], row["version_no"], row["ots_name"], row["ots_version"], row["cve_id"],
            row["cvss31_score"], row["cvss31_vector"], row["environmental_score"], row["environmental_vector"],
            row["applicability"], row["applicability_basis"], row["treatment"], row["status"],
            row["submitter_name"], AssessmentExportService._time(row["submitted_at"]), row["review_decision"],
            row["reviewer_name"], AssessmentExportService._time(row["reviewed_at"]), row["review_comment"],
        )

    @staticmethod
    def _time(value: object) -> str:
        if not isinstance(value, datetime):
            return ""
        aware = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
        return aware.isoformat(timespec="seconds").replace("+00:00", "Z")

    @staticmethod
    def _csv_line(values: tuple[object, ...]) -> bytes:
        safe = []
        for index, value in enumerate(values):
            text = "" if value is None else str(value)
            if index in TEXT_COLUMNS and text.startswith(("=", "+", "-", "@", "\t", "\r")):
                text = "'" + text
            safe.append(text)
        output = StringIO(newline="")
        csv.writer(output, lineterminator="\r\n").writerow(safe)
        return output.getvalue().encode("utf-8")
