from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from app.models.products import Product, ProductVersion


class ProductRepository:
    def get_product(self, session: Session, product_id: int) -> Product | None:
        return session.get(Product, product_id)

    def get_version(self, session: Session, version_id: int) -> ProductVersion | None:
        return session.get(ProductVersion, version_id)

    def list_products(self, session: Session, *, query: str | None, status: str | None) -> list[Product]:
        statement = select(Product).order_by(Product.id)
        if query:
            pattern = f"%{query}%"
            statement = statement.where(or_(Product.product_code.like(pattern), Product.product_name.like(pattern)))
        if status:
            statement = statement.where(Product.status == status)
        return list(session.scalars(statement).all())

    def list_versions(self, session: Session, product_id: int) -> list[ProductVersion]:
        return list(session.scalars(select(ProductVersion).where(ProductVersion.product_id == product_id).order_by(ProductVersion.id)).all())

    def update_product_if_version(self, session: Session, product_id: int, row_version: int, **values: object) -> bool:
        result = session.execute(update(Product).where(Product.id == product_id, Product.row_version == row_version).values(**values, row_version=Product.row_version + 1))
        return result.rowcount == 1

    def update_version_if_version(self, session: Session, version_id: int, row_version: int, **values: object) -> bool:
        result = session.execute(update(ProductVersion).where(ProductVersion.id == version_id, ProductVersion.row_version == row_version).values(**values, row_version=ProductVersion.row_version + 1))
        return result.rowcount == 1
