from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.models.assessments import ProductAssessment
from app.models.imports import Vulnerability
from app.models.ots import OtsComponent, ProductOts
from app.models.products import Product, ProductVersion
from app.repositories.scopes import ScopeRepository


EDITABLE_STATUSES = {"pending", "returned", "reassess"}


class AssessmentEditorRepository:
    def __init__(self) -> None:
        self._scopes = ScopeRepository()

    def effective_version_ids(self, session: Session, user_id: int) -> list[int]:
        return self._scopes.effective_version_ids(session, user_id)

    @staticmethod
    def get_context(session: Session, assessment_id: int) -> dict[str, object] | None:
        statement = (
            select(
                ProductAssessment,
                Product.id.label("product_id"),
                Product.product_name,
                ProductVersion.id.label("product_version_id"),
                ProductVersion.version_no,
                ProductVersion.owner_id.label("version_owner_id"),
                ProductVersion.reviewer_id.label("version_reviewer_id"),
                OtsComponent.id.label("ots_component_id"),
                OtsComponent.ots_name,
                OtsComponent.ots_version,
                Vulnerability.id.label("vulnerability_id"),
                Vulnerability.cve_id,
                Vulnerability.source_status,
                Vulnerability.description,
                Vulnerability.cvss31_score,
                Vulnerability.cvss31_severity,
                Vulnerability.cvss31_vector,
                Vulnerability.cvss31_source,
                Vulnerability.is_kev,
            )
            .select_from(ProductAssessment)
            .join(ProductOts, ProductOts.id == ProductAssessment.product_ots_id)
            .join(ProductVersion, ProductVersion.id == ProductOts.product_version_id)
            .join(Product, Product.id == ProductVersion.product_id)
            .join(OtsComponent, OtsComponent.id == ProductOts.ots_component_id)
            .join(Vulnerability, Vulnerability.id == ProductAssessment.vulnerability_id)
            .where(ProductAssessment.id == assessment_id)
        )
        row = session.execute(statement).mappings().first()
        return dict(row) if row is not None else None

    @staticmethod
    def get_context_for_update(
        session: Session, assessment_id: int
    ) -> dict[str, object] | None:
        statement = (
            select(ProductAssessment.id)
            .where(ProductAssessment.id == assessment_id)
            .with_for_update()
        )
        if session.scalar(statement) is None:
            return None
        return AssessmentEditorRepository.get_context(session, assessment_id)

    @staticmethod
    def current_revision_id(
        session: Session, *, product_ots_id: int, vulnerability_id: int
    ) -> int | None:
        return session.scalar(
            select(ProductAssessment.id).where(
                ProductAssessment.product_ots_id == product_ots_id,
                ProductAssessment.vulnerability_id == vulnerability_id,
                ProductAssessment.is_current.is_(True),
            )
        )

    @staticmethod
    def next_revision_no(
        session: Session, *, product_ots_id: int, vulnerability_id: int
    ) -> int:
        current = session.scalar(
            select(func.max(ProductAssessment.revision_no)).where(
                ProductAssessment.product_ots_id == product_ots_id,
                ProductAssessment.vulnerability_id == vulnerability_id,
            )
        )
        return int(current or 0) + 1

    @staticmethod
    def list_revisions(
        session: Session, *, product_ots_id: int, vulnerability_id: int
    ) -> list[ProductAssessment]:
        return list(
            session.scalars(
                select(ProductAssessment)
                .where(
                    ProductAssessment.product_ots_id == product_ots_id,
                    ProductAssessment.vulnerability_id == vulnerability_id,
                )
                .order_by(ProductAssessment.revision_no.desc(), ProductAssessment.id.desc())
            ).all()
        )

    @staticmethod
    def update_draft_if_version(
        session: Session,
        *,
        assessment_id: int,
        owner_id: int,
        row_version: int,
        values: dict[str, object],
        updated_at: datetime,
    ) -> bool:
        result = session.execute(
            update(ProductAssessment)
            .where(
                ProductAssessment.id == assessment_id,
                ProductAssessment.is_current.is_(True),
                ProductAssessment.status.in_(EDITABLE_STATUSES),
                ProductAssessment.owner_id == owner_id,
                ProductAssessment.row_version == row_version,
            )
            .values(
                **values,
                row_version=ProductAssessment.row_version + 1,
                updated_at=updated_at,
            )
        )
        return result.rowcount == 1

    @staticmethod
    def transition_if_version(
        session: Session,
        *,
        assessment_id: int,
        expected_status: str,
        row_version: int,
        values: dict[str, object],
        updated_at: datetime,
    ) -> bool:
        result = session.execute(
            update(ProductAssessment)
            .where(
                ProductAssessment.id == assessment_id,
                ProductAssessment.is_current.is_(True),
                ProductAssessment.status == expected_status,
                ProductAssessment.row_version == row_version,
            )
            .values(
                **values,
                row_version=ProductAssessment.row_version + 1,
                updated_at=updated_at,
            )
        )
        return result.rowcount == 1
