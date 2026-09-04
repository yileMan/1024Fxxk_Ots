from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.assessments import ProductAssessment
from app.models.imports import VulnerabilityOtsMatch
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
