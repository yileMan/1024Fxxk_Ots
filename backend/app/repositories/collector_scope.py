from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.imports import ImportBatch
from app.models.ots import OtsComponent, ProductOts
from app.models.products import Product, ProductVersion


class CollectorScopeRepository:
    def list_active_ots(self, session: Session) -> list[OtsComponent]:
        statement = (
            select(OtsComponent)
            .join(ProductOts, ProductOts.ots_component_id == OtsComponent.id)
            .join(ProductVersion, ProductVersion.id == ProductOts.product_version_id)
            .join(Product, Product.id == ProductVersion.product_id)
            .where(Product.status == "active", ProductVersion.status == "active")
            .distinct()
            .order_by(OtsComponent.id)
        )
        return list(session.scalars(statement).all())

    def list_succeeded_batches(
        self,
        session: Session,
        *,
        offset: int,
        limit: int,
    ) -> list[ImportBatch]:
        statement = (
            select(ImportBatch)
            .where(ImportBatch.status == "succeeded")
            .order_by(
                ImportBatch.finished_at.desc(),
                ImportBatch.created_at.desc(),
                ImportBatch.id.desc(),
            )
            .offset(offset)
            .limit(limit)
        )
        return list(session.scalars(statement).all())
