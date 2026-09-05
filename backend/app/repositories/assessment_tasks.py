from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.orm import Session

from app.models.assessments import ProductAssessment
from app.models.imports import Vulnerability, VulnerabilityOtsMatch
from app.models.ots import ProductOts
from app.models.products import Product, ProductVersion
from app.models.user import AppUser


@dataclass(frozen=True)
class ProductOtsContext:
    product_ots_id: int
    ots_component_id: int
    product_id: int
    product_name: str
    product_status: str
    product_version_id: int
    version_no: str
    product_version_status: str
    owner_id: int
    owner_available: bool


class AssessmentTaskRepository:
    @staticmethod
    def current_bases_ready(session: Session) -> bool:
        missing = session.scalar(
            select(func.count(ProductAssessment.id)).where(
                ProductAssessment.is_current.is_(True),
                or_(
                    ProductAssessment.assessment_basis_sha256.is_(None),
                    ProductAssessment.assessment_basis_json.is_(None),
                ),
            )
        )
        return int(missing or 0) == 0

    def list_candidates(
        self, session: Session, vulnerability_ids: set[int]
    ) -> list[VulnerabilityOtsMatch]:
        if not vulnerability_ids:
            return []
        return list(session.scalars(
            select(VulnerabilityOtsMatch)
            .where(VulnerabilityOtsMatch.vulnerability_id.in_(vulnerability_ids))
            .order_by(
                VulnerabilityOtsMatch.vulnerability_id,
                VulnerabilityOtsMatch.ots_component_id,
            )
        ))

    @staticmethod
    def update_current_if_version(
        session: Session,
        *,
        assessment_id: int,
        expected_status: str,
        row_version: int,
        values: dict[str, object],
    ) -> bool:
        result = session.execute(
            update(ProductAssessment)
            .where(
                ProductAssessment.id == assessment_id,
                ProductAssessment.is_current.is_(True),
                ProductAssessment.status == expected_status,
                ProductAssessment.row_version == row_version,
            )
            .values(**values, row_version=ProductAssessment.row_version + 1)
        )
        return result.rowcount == 1

    def get_product_context(
        self, session: Session, product_ots_id: int
    ) -> ProductOtsContext | None:
        row = session.execute(
            select(ProductOts, ProductVersion, Product, AppUser)
            .join(ProductVersion, ProductVersion.id == ProductOts.product_version_id)
            .join(Product, Product.id == ProductVersion.product_id)
            .join(AppUser, AppUser.id == ProductVersion.owner_id)
            .where(ProductOts.id == product_ots_id)
        ).first()
        if row is None:
            return None
        relation, version, product, owner = row
        return ProductOtsContext(
            product_ots_id=relation.id,
            ots_component_id=relation.ots_component_id,
            product_id=product.id,
            product_name=product.product_name,
            product_status=product.status,
            product_version_id=version.id,
            version_no=version.version_no,
            product_version_status=version.status,
            owner_id=version.owner_id,
            owner_available=owner.status == "active" and "product_owner" in owner.roles_json,
        )

    def list_relation_current_facts(
        self, session: Session, product_ots_id: int, *, lock: bool = False
    ) -> list[tuple[ProductAssessment, Vulnerability, VulnerabilityOtsMatch | None]]:
        statement = (
            select(ProductAssessment, Vulnerability, VulnerabilityOtsMatch)
            .join(Vulnerability, Vulnerability.id == ProductAssessment.vulnerability_id)
            .outerjoin(
                VulnerabilityOtsMatch,
                and_(
                    VulnerabilityOtsMatch.vulnerability_id == Vulnerability.id,
                    VulnerabilityOtsMatch.ots_component_id
                    == select(ProductOts.ots_component_id)
                    .where(ProductOts.id == product_ots_id)
                    .scalar_subquery(),
                ),
            )
            .where(
                ProductAssessment.product_ots_id == product_ots_id,
                ProductAssessment.is_current.is_(True),
            )
            .order_by(Vulnerability.cve_id)
        )
        if lock:
            statement = statement.with_for_update()
        return list(session.execute(statement).tuples().all())

    def list_product_contexts(
        self, session: Session, ots_component_ids: set[int]
    ) -> list[ProductOtsContext]:
        if not ots_component_ids:
            return []
        rows = session.execute(
            select(ProductOts, ProductVersion, Product, AppUser)
            .join(ProductVersion, ProductVersion.id == ProductOts.product_version_id)
            .join(Product, Product.id == ProductVersion.product_id)
            .join(AppUser, AppUser.id == ProductVersion.owner_id)
            .where(
                ProductOts.ots_component_id.in_(ots_component_ids),
                ProductOts.status == "active",
            )
            .order_by(Product.id, ProductVersion.id, ProductOts.id)
        ).all()
        return [
            ProductOtsContext(
                product_ots_id=relation.id,
                ots_component_id=relation.ots_component_id,
                product_id=product.id,
                product_name=product.product_name,
                product_status=product.status,
                product_version_id=version.id,
                version_no=version.version_no,
                product_version_status=version.status,
                owner_id=version.owner_id,
                owner_available=owner.status == "active" and "product_owner" in owner.roles_json,
            )
            for relation, version, product, owner in rows
        ]

    def list_current_assessments(
        self, session: Session, vulnerability_ids: set[int], *, lock: bool = False
    ) -> list[ProductAssessment]:
        if not vulnerability_ids:
            return []
        statement = (
            select(ProductAssessment)
            .where(
                ProductAssessment.vulnerability_id.in_(vulnerability_ids),
                ProductAssessment.is_current.is_(True),
            )
            .order_by(ProductAssessment.product_ots_id, ProductAssessment.vulnerability_id)
        )
        if lock:
            statement = statement.with_for_update()
        return list(session.scalars(statement))
