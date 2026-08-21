from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.user import Base, identifier_type


class UserProductScope(Base):
    __tablename__ = "user_product_scope"
    __table_args__ = (
        CheckConstraint("scope_type IN ('product', 'version')", name="ck_user_product_scope_type"),
        CheckConstraint(
            "(scope_type = 'product' AND product_version_id IS NULL) OR "
            "(scope_type = 'version' AND product_version_id IS NOT NULL)",
            name="ck_user_product_scope_target",
        ),
        UniqueConstraint("user_id", "scope_key", name="uk_user_product_scope"),
        Index("idx_scope_product", "product_id", "user_id"),
        Index("idx_scope_version", "product_version_id", "user_id"),
    )

    id: Mapped[int] = mapped_column(identifier_type, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("app_user.id"))
    scope_type: Mapped[str] = mapped_column(String(16))
    product_id: Mapped[int] = mapped_column(ForeignKey("product.id"))
    product_version_id: Mapped[int | None] = mapped_column(ForeignKey("product_version.id"), nullable=True)
    scope_key: Mapped[str] = mapped_column(String(64))
    created_by: Mapped[int] = mapped_column(ForeignKey("app_user.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)
