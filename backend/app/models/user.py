from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, BigInteger, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


identifier_type = BigInteger().with_variant(Integer, "sqlite")


class AppUser(Base):
    __tablename__ = "app_user"

    id: Mapped[int] = mapped_column(identifier_type, primary_key=True, autoincrement=True)
    login_name: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(100))
    password_hash: Mapped[str] = mapped_column(String(255))
    roles_json: Mapped[list[str]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(32), default="active", index=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    row_version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)

    @property
    def roles(self) -> list[str]:
        return self.roles_json


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(identifier_type, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("app_user.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(16))
    object_type: Mapped[str] = mapped_column(String(64))
    object_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    detail_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.now)
