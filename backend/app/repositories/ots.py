from __future__ import annotations

from sqlalchemy import inspect, or_, select, text, tuple_, update
from sqlalchemy.orm import Session

from app.models.ots import OtsComponent, ProductOts
from app.models.products import Product, ProductVersion


class OtsRepository:
    def get_ots(self, session: Session, ots_id: int) -> OtsComponent | None:
        return session.get(OtsComponent, ots_id)

    def get_relation(self, session: Session, relation_id: int) -> ProductOts | None:
        return session.get(ProductOts, relation_id)

    def find_relation(self, session: Session, version_id: int, ots_id: int) -> ProductOts | None:
        return session.scalar(select(ProductOts).where(ProductOts.product_version_id == version_id, ProductOts.ots_component_id == ots_id))

    def find_ots_by_keys(self, session: Session, keys: list[tuple[str, str]]) -> list[OtsComponent]:
        if not keys:
            return []
        return list(session.scalars(select(OtsComponent).where(tuple_(OtsComponent.ots_name, OtsComponent.ots_version).in_(keys))).all())

    def list_ots(self, session: Session, *, query: str | None, is_eol: bool | None) -> list[OtsComponent]:
        statement = select(OtsComponent).order_by(OtsComponent.ots_name, OtsComponent.ots_version, OtsComponent.id)
        if query:
            pattern = f"%{query}%"
            statement = statement.where(or_(OtsComponent.ots_name.like(pattern), OtsComponent.ots_version.like(pattern)))
        if is_eol is not None:
            statement = statement.where(OtsComponent.is_eol == is_eol)
        return list(session.scalars(statement).all())

    def list_product_ots(self, session: Session, version_id: int) -> list[tuple[ProductOts, OtsComponent]]:
        statement = (select(ProductOts, OtsComponent).join(OtsComponent, OtsComponent.id == ProductOts.ots_component_id).where(ProductOts.product_version_id == version_id).order_by(OtsComponent.ots_name, OtsComponent.ots_version, ProductOts.id))
        return list(session.execute(statement).tuples().all())

    def list_associated_versions(self, session: Session, ots_id: int) -> list[tuple[ProductOts, ProductVersion, Product]]:
        statement = (select(ProductOts, ProductVersion, Product).join(ProductVersion, ProductVersion.id == ProductOts.product_version_id).join(Product, Product.id == ProductVersion.product_id).where(ProductOts.ots_component_id == ots_id).order_by(Product.product_name, ProductVersion.version_no))
        return list(session.execute(statement).tuples().all())

    def update_ots_if_version(self, session: Session, ots_id: int, row_version: int, **values: object) -> bool:
        result = session.execute(update(OtsComponent).where(OtsComponent.id == ots_id, OtsComponent.row_version == row_version).values(**values, row_version=OtsComponent.row_version + 1))
        return result.rowcount == 1

    def has_downstream_history(self, session: Session, relation_id: int) -> bool:
        if session.bind is None or not inspect(session.bind).has_table("product_assessment"):
            return False
        return session.execute(text("SELECT 1 FROM product_assessment WHERE product_ots_id = :relation_id LIMIT 1"), {"relation_id": relation_id}).first() is not None
