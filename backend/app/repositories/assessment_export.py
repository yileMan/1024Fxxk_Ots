from __future__ import annotations

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session, aliased

from app.models.assessments import ProductAssessment
from app.models.imports import Vulnerability
from app.models.ots import OtsComponent, ProductOts
from app.models.products import Product, ProductVersion
from app.models.user import AppUser
from app.repositories.scopes import ScopeRepository


class AssessmentExportRepository:
    def __init__(self) -> None:
        self._scopes = ScopeRepository()

    def effective_version_ids(self, session: Session, user_id: int) -> list[int]:
        return self._scopes.effective_version_ids(session, user_id)

    @staticmethod
    def get_scope(session: Session, version_id: int, ots_id: int) -> dict[str, object] | None:
        row = session.execute(
            select(
                ProductOts.id.label("product_ots_id"), ProductVersion.id.label("product_version_id"),
                Product.product_name, ProductVersion.version_no, OtsComponent.id.label("ots_id"),
                OtsComponent.ots_name, OtsComponent.ots_version,
            )
            .select_from(ProductOts)
            .join(ProductVersion, ProductVersion.id == ProductOts.product_version_id)
            .join(Product, Product.id == ProductVersion.product_id)
            .join(OtsComponent, OtsComponent.id == ProductOts.ots_component_id)
            .where(ProductVersion.id == version_id, OtsComponent.id == ots_id, ProductOts.status == "active")
        ).mappings().first()
        return dict(row) if row else None

    @staticmethod
    def count_rows(session: Session, product_ots_id: int) -> int:
        return int(session.scalar(select(func.count()).select_from(ProductAssessment).where(
            ProductAssessment.product_ots_id == product_ots_id,
            ProductAssessment.is_current.is_(True),
        )) or 0)

    @staticmethod
    def list_rows(
        session: Session,
        product_ots_id: int,
        *,
        after_cve: str | None,
        after_id: int | None,
        limit: int,
    ) -> list[dict[str, object]]:
        submitter = aliased(AppUser)
        reviewer = aliased(AppUser)
        statement = (
            select(
                Product.product_name, ProductVersion.version_no, OtsComponent.ots_name,
                OtsComponent.ots_version, Vulnerability.cve_id, Vulnerability.cvss31_score,
                Vulnerability.cvss31_vector, ProductAssessment.environmental_score,
                ProductAssessment.environmental_vector, ProductAssessment.applicability,
                ProductAssessment.applicability_basis, ProductAssessment.treatment,
                ProductAssessment.status, submitter.display_name.label("submitter_name"),
                ProductAssessment.submitted_at, ProductAssessment.review_decision,
                reviewer.display_name.label("reviewer_name"), ProductAssessment.reviewed_at,
                ProductAssessment.review_comment, ProductAssessment.id.label("assessment_id"),
            )
            .select_from(ProductAssessment)
            .join(ProductOts, ProductOts.id == ProductAssessment.product_ots_id)
            .join(ProductVersion, ProductVersion.id == ProductOts.product_version_id)
            .join(Product, Product.id == ProductVersion.product_id)
            .join(OtsComponent, OtsComponent.id == ProductOts.ots_component_id)
            .join(Vulnerability, Vulnerability.id == ProductAssessment.vulnerability_id)
            .outerjoin(submitter, submitter.id == ProductAssessment.submitted_by)
            .outerjoin(reviewer, reviewer.id == ProductAssessment.reviewer_id)
            .where(ProductAssessment.product_ots_id == product_ots_id, ProductAssessment.is_current.is_(True))
        )
        if after_cve is not None and after_id is not None:
            statement = statement.where(or_(
                Vulnerability.cve_id > after_cve,
                and_(Vulnerability.cve_id == after_cve, ProductAssessment.id > after_id),
            ))
        statement = statement.order_by(Vulnerability.cve_id, ProductAssessment.id).limit(limit)
        return [dict(row) for row in session.execute(statement).mappings().all()]
