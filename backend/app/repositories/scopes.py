from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.models.products import Product, ProductVersion
from app.models.scopes import UserProductScope


class ScopeRepository:
    def list_scopes(self, session: Session, user_id: int) -> list[UserProductScope]:
        return list(
            session.scalars(
                select(UserProductScope)
                .where(UserProductScope.user_id == user_id)
                .order_by(UserProductScope.id)
            ).all()
        )

    def get_scope(self, session: Session, user_id: int, scope_id: int) -> UserProductScope | None:
        return session.scalar(
            select(UserProductScope).where(
                UserProductScope.id == scope_id,
                UserProductScope.user_id == user_id,
            )
        )

    def find_scope(self, session: Session, user_id: int, scope_key: str) -> UserProductScope | None:
        return session.scalar(
            select(UserProductScope).where(
                UserProductScope.user_id == user_id,
                UserProductScope.scope_key == scope_key,
            )
        )

    def effective_product_ids(self, session: Session, user_id: int) -> list[int]:
        direct_ids = select(UserProductScope.product_id).join(
            Product, Product.id == UserProductScope.product_id
        ).where(
            UserProductScope.user_id == user_id,
            Product.status == "active",
            or_(
                UserProductScope.scope_type == "product",
                and_(
                    UserProductScope.scope_type == "version",
                    UserProductScope.product_version_id.in_(
                        select(ProductVersion.id).where(ProductVersion.status == "active")
                    ),
                ),
            ),
        )
        return sorted(set(session.scalars(direct_ids).all()))

    def effective_version_ids(self, session: Session, user_id: int) -> list[int]:
        statement = (
            select(ProductVersion.id)
            .join(Product, Product.id == ProductVersion.product_id)
            .join(UserProductScope, UserProductScope.product_id == Product.id)
            .where(
                UserProductScope.user_id == user_id,
                Product.status == "active",
                ProductVersion.status == "active",
                or_(
                    UserProductScope.scope_type == "product",
                    and_(
                        UserProductScope.scope_type == "version",
                        UserProductScope.product_version_id == ProductVersion.id,
                    ),
                ),
            )
        )
        return sorted(set(session.scalars(statement).all()))

    def has_product_access(self, session: Session, user_id: int, product_id: int) -> bool:
        active_version = select(ProductVersion.id).where(
            ProductVersion.id == UserProductScope.product_version_id,
            ProductVersion.product_id == Product.id,
            ProductVersion.status == "active",
        ).exists()
        statement = (
            select(UserProductScope.id)
            .join(Product, Product.id == UserProductScope.product_id)
            .where(
                UserProductScope.user_id == user_id,
                UserProductScope.product_id == product_id,
                Product.status == "active",
                or_(
                    UserProductScope.scope_type == "product",
                    and_(UserProductScope.scope_type == "version", active_version),
                ),
            )
            .limit(1)
        )
        return session.scalar(statement) is not None

    def has_version_access(self, session: Session, user_id: int, version_id: int) -> bool:
        statement = (
            select(UserProductScope.id)
            .join(ProductVersion, ProductVersion.product_id == UserProductScope.product_id)
            .join(Product, Product.id == ProductVersion.product_id)
            .where(
                UserProductScope.user_id == user_id,
                ProductVersion.id == version_id,
                Product.status == "active",
                ProductVersion.status == "active",
                or_(
                    UserProductScope.scope_type == "product",
                    and_(
                        UserProductScope.scope_type == "version",
                        UserProductScope.product_version_id == version_id,
                    ),
                ),
            )
            .limit(1)
        )
        return session.scalar(statement) is not None
