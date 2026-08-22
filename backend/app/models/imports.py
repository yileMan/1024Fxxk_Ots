from __future__ import annotations

from datetime import datetime

from sqlalchemy import CHAR, JSON, CheckConstraint, DateTime, ForeignKey, Index, String, UniqueConstraint
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
