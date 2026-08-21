from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.user import Base, identifier_type


class OtsComponent(Base):
    __tablename__ = "ots_component"
    __table_args__ = (UniqueConstraint("ots_name", "ots_version", name="uk_ots_name_version"),)

    id: Mapped[int] = mapped_column(identifier_type, primary_key=True, autoincrement=True)
    ots_name: Mapped[str] = mapped_column(String(200), index=True)
    ots_version: Mapped[str] = mapped_column(String(200))
    official_website: Mapped[str] = mapped_column(String(1000))
    is_eol: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    row_version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)


class ProductOts(Base):
    __tablename__ = "product_ots"
    __table_args__ = (UniqueConstraint("product_version_id", "ots_component_id", name="uk_product_version_ots"),)

    id: Mapped[int] = mapped_column(identifier_type, primary_key=True, autoincrement=True)
    product_version_id: Mapped[int] = mapped_column(ForeignKey("product_version.id"), index=True)
    ots_component_id: Mapped[int] = mapped_column(ForeignKey("ots_component.id"), index=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("app_user.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)
