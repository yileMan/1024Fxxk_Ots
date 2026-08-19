from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.user import Base, identifier_type


class Product(Base):
    __tablename__ = "product"

    id: Mapped[int] = mapped_column(identifier_type, primary_key=True, autoincrement=True)
    product_code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    product_name: Mapped[str] = mapped_column(String(200), index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="active", index=True)
    row_version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)


class ProductVersion(Base):
    __tablename__ = "product_version"
    __table_args__ = (UniqueConstraint("product_id", "version_no", name="uk_product_version"),)

    id: Mapped[int] = mapped_column(identifier_type, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("product.id"), index=True)
    version_no: Mapped[str] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    primary_cvss_version: Mapped[str] = mapped_column(String(8), default="3.1")
    owner_id: Mapped[int] = mapped_column(ForeignKey("app_user.id"), index=True)
    reviewer_id: Mapped[int] = mapped_column(ForeignKey("app_user.id"), index=True)
    status: Mapped[str] = mapped_column(String(32), default="active", index=True)
    row_version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)
