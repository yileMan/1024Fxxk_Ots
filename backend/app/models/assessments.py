from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, JSON, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.user import Base, identifier_type


class ProductAssessment(Base):
    __tablename__ = "product_assessment"
    __table_args__ = (
        UniqueConstraint("product_ots_id", "vulnerability_id", "revision_no", name="uk_assessment_revision"),
        CheckConstraint("is_current IN (0, 1)", name="ck_assessment_current"),
        CheckConstraint("status IN ('pending', 'submitted', 'returned', 'completed', 'reassess')", name="ck_assessment_status"),
        CheckConstraint("applicability IN ('affected', 'not_affected', 'partly_affected', 'pending')", name="ck_assessment_applicability"),
        CheckConstraint("cvss_version IS NULL OR cvss_version IN ('3.1', '4.0')", name="ck_assessment_cvss_version"),
        CheckConstraint("review_decision IS NULL OR review_decision IN ('approved', 'returned')", name="ck_assessment_review_decision"),
        Index("idx_assessment_current_owner", "is_current", "owner_id", "status", "updated_at"),
        Index("idx_assessment_current_review", "is_current", "status", "updated_at"),
        Index("idx_assessment_cross_product", "vulnerability_id", "is_current", "status", "product_ots_id"),
    )

    id: Mapped[int] = mapped_column(identifier_type, primary_key=True, autoincrement=True)
    product_ots_id: Mapped[int] = mapped_column(ForeignKey("product_ots.id"))
    vulnerability_id: Mapped[int] = mapped_column(ForeignKey("vulnerability.id"))
    revision_no: Mapped[int] = mapped_column(Integer)
    parent_revision_id: Mapped[int | None] = mapped_column(ForeignKey("product_assessment.id"), nullable=True)
    is_current: Mapped[bool] = mapped_column(Boolean)
    status: Mapped[str] = mapped_column(String(32))
    owner_id: Mapped[int] = mapped_column(ForeignKey("app_user.id"))
    analysis_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    trigger_conditions: Mapped[str | None] = mapped_column(Text, nullable=True)
    affected_functions: Mapped[str | None] = mapped_column(Text, nullable=True)
    applicability: Mapped[str] = mapped_column(String(32))
    applicability_basis: Mapped[str | None] = mapped_column(Text, nullable=True)
    product_impact: Mapped[str | None] = mapped_column(Text, nullable=True)
    existing_controls: Mapped[str | None] = mapped_column(Text, nullable=True)
    treatment: Mapped[str | None] = mapped_column(String(32), nullable=True)
    treatment_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    cvss_version: Mapped[str | None] = mapped_column(String(8), nullable=True)
    environmental_score: Mapped[float | None] = mapped_column(Numeric(3, 1), nullable=True)
    environmental_vector: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    cvss_metrics_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    calculator_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    based_on_source_modified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    submitted_by: Mapped[int | None] = mapped_column(ForeignKey("app_user.id"), nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_decision: Mapped[str | None] = mapped_column(String(16), nullable=True)
    review_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewer_id: Mapped[int | None] = mapped_column(ForeignKey("app_user.id"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reassess_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    row_version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)
