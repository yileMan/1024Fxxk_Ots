from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Boolean, CHAR, JSON, CheckConstraint, Date, DateTime, ForeignKey, Index, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.user import Base, identifier_type


class ImportBatch(Base):
    __tablename__ = "import_batch"
    __table_args__ = (
        UniqueConstraint("batch_no", name="uk_import_batch_no"),
        UniqueConstraint("package_sha256", name="uk_import_package_sha"),
        CheckConstraint("status IN ('uploaded', 'validated', 'importing', 'succeeded', 'failed')", name="ck_import_batch_status"),
        Index("idx_import_status_time", "status", "created_at"),
        Index("idx_import_covered_to", "covered_to"),
    )

    id: Mapped[int] = mapped_column(identifier_type, primary_key=True, autoincrement=True)
    batch_no: Mapped[str] = mapped_column(String(100))
    format_version: Mapped[str] = mapped_column(String(32))
    package_file_name: Mapped[str] = mapped_column(String(255))
    package_sha256: Mapped[str] = mapped_column(CHAR(64))
    archive_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    covered_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    covered_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(32), index=False)
    result_json: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    error_json: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    scope_coverage_json: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    manifest_json: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    imported_by: Mapped[int] = mapped_column(ForeignKey("app_user.id"))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)


class Vulnerability(Base):
    __tablename__ = "vulnerability"
    __table_args__ = (
        UniqueConstraint("cve_id", name="uk_vulnerability_cve"),
        Index("idx_vulnerability_modified", "source_modified_at"),
        Index("idx_vulnerability_kev", "is_kev", "published_at"),
        Index("idx_vulnerability_cvss31", "cvss31_score"),
        Index("idx_vulnerability_cvss40", "cvss40_score"),
    )

    id: Mapped[int] = mapped_column(identifier_type, primary_key=True, autoincrement=True)
    cve_id: Mapped[str] = mapped_column(String(32))
    source_identifier: Mapped[str] = mapped_column(String(200))
    source_status: Mapped[str] = mapped_column(String(32))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_analysis_suggestion: Mapped[str | None] = mapped_column(Text, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source_modified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cwe_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    affected_ranges_json: Mapped[list] = mapped_column(JSON)
    references_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    cvss_json: Mapped[list] = mapped_column(JSON)
    configurations_json: Mapped[list] = mapped_column(JSON)
    cvss31_score: Mapped[float | None] = mapped_column(Numeric(3, 1), nullable=True)
    cvss31_severity: Mapped[str | None] = mapped_column(String(16), nullable=True)
    cvss31_vector: Mapped[str | None] = mapped_column(String(500), nullable=True)
    cvss31_source: Mapped[str | None] = mapped_column(String(200), nullable=True)
    cvss40_score: Mapped[float | None] = mapped_column(Numeric(3, 1), nullable=True)
    cvss40_severity: Mapped[str | None] = mapped_column(String(16), nullable=True)
    cvss40_vector: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    cvss40_source: Mapped[str | None] = mapped_column(String(200), nullable=True)
    is_kev: Mapped[bool] = mapped_column(Boolean, default=False)
    kev_date_added: Mapped[date | None] = mapped_column(Date, nullable=True)
    kev_due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    kev_required_action: Mapped[str | None] = mapped_column(Text, nullable=True)
    import_batch_id: Mapped[int] = mapped_column(ForeignKey("import_batch.id"))
    content_sha256: Mapped[str] = mapped_column(CHAR(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)
