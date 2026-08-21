from sqlalchemy import and_, exists, func, or_, select, update
from sqlalchemy.orm import Session

from app.models.products import Product, ProductVersion
from app.models.scopes import UserProductScope


class ProductRepository:
    def get_product(self, session: Session, product_id: int) -> Product | None:
        return session.get(Product, product_id)

    def get_version(self, session: Session, version_id: int) -> ProductVersion | None:
        return session.get(ProductVersion, version_id)

    def list_products(
        self,
        session: Session,
        *,
        query: str | None,
        status: str | None,
        viewer_id: int | None,
        page: int,
        page_size: int,
    ) -> tuple[list[Product], int]:
        statement = select(Product).order_by(Product.id)
        if viewer_id is not None:
            active_version = exists(
                select(ProductVersion.id).where(
                    ProductVersion.id == UserProductScope.product_version_id,
                    ProductVersion.product_id == Product.id,
                    ProductVersion.status == "active",
                )
            )
            access = exists(
                select(UserProductScope.id).where(
                    UserProductScope.user_id == viewer_id,
                    UserProductScope.product_id == Product.id,
                    or_(
                        UserProductScope.scope_type == "product",
                        and_(UserProductScope.scope_type == "version", active_version),
                    ),
                )
            )
            statement = statement.where(Product.status == "active", access)
        if query:
            pattern = f"%{query}%"
            statement = statement.where(or_(Product.product_code.like(pattern), Product.product_name.like(pattern)))
        if status:
            statement = statement.where(Product.status == status)
        total = session.scalar(select(func.count()).select_from(statement.order_by(None).subquery())) or 0
        items = list(session.scalars(statement.offset((page - 1) * page_size).limit(page_size)).all())
        return items, total

    def list_versions(self, session: Session, product_id: int, viewer_id: int | None) -> list[ProductVersion]:
        statement = select(ProductVersion).where(ProductVersion.product_id == product_id)
        if viewer_id is not None:
            access = exists(
                select(UserProductScope.id).where(
                    UserProductScope.user_id == viewer_id,
                    UserProductScope.product_id == product_id,
                    or_(
                        UserProductScope.scope_type == "product",
                        and_(
                            UserProductScope.scope_type == "version",
                            UserProductScope.product_version_id == ProductVersion.id,
                        ),
                    ),
                )
            )
            statement = statement.where(ProductVersion.status == "active", access)
        return list(session.scalars(statement.order_by(ProductVersion.id)).all())

    def update_product_if_version(self, session: Session, product_id: int, row_version: int, **values: object) -> bool:
        result = session.execute(update(Product).where(Product.id == product_id, Product.row_version == row_version).values(**values, row_version=Product.row_version + 1))
        return result.rowcount == 1

    def update_version_if_version(self, session: Session, version_id: int, row_version: int, **values: object) -> bool:
        result = session.execute(update(ProductVersion).where(ProductVersion.id == version_id, ProductVersion.row_version == row_version).values(**values, row_version=ProductVersion.row_version + 1))
        return result.rowcount == 1
