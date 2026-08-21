from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.models.products import Product, ProductVersion
from app.models.scopes import UserProductScope
from app.models.user import AppUser, AuditLog
from app.repositories.scopes import ScopeRepository
from app.services.authentication import PublicUser


class ScopeAuthorizationError(ValueError):
    code = "PRODUCT_SCOPE_ERROR"


class ScopeTargetNotFoundError(ScopeAuthorizationError):
    code = "PRODUCT_SCOPE_TARGET_NOT_FOUND"


class ScopeInvalidError(ScopeAuthorizationError):
    code = "PRODUCT_SCOPE_INVALID"


class ProductScopeForbiddenError(ScopeAuthorizationError):
    code = "PRODUCT_SCOPE_FORBIDDEN"


@dataclass(frozen=True)
class ScopeView:
    id: int
    user_id: int
    scope_type: str
    product_id: int
    product_version_id: int | None
    scope_key: str
    created_by: int
    created_at: datetime
    updated_at: datetime
    is_effective: bool


@dataclass(frozen=True)
class ScopeSummary:
    is_global: bool
    scopes: list[ScopeView]
    effective_product_ids: list[int]
    effective_version_ids: list[int]


class ScopeAuthorizationService:
    def __init__(self, session_factory: sessionmaker) -> None:
        self._session_factory = session_factory
        self._repository = ScopeRepository()

    def summary_for_current_user(self, user: PublicUser) -> ScopeSummary:
        if "admin" in user.roles:
            return ScopeSummary(True, [], [], [])
        return self.summary_for_user(user.id)

    def summary_for_user(self, user_id: int) -> ScopeSummary:
        with self._session_factory() as session:
            user = self._user(session, user_id)
            scopes = self._repository.list_scopes(session, user_id)
            is_global = "admin" in user.roles_json
            effective_products = [] if is_global else self._repository.effective_product_ids(session, user_id)
            effective_versions = [] if is_global else self._repository.effective_version_ids(session, user_id)
            return ScopeSummary(
                is_global,
                [self._view(session, scope) for scope in scopes],
                effective_products,
                effective_versions,
            )

    def grant(
        self,
        *,
        actor_id: int,
        user_id: int,
        scope_type: str,
        product_id: int,
        product_version_id: int | None,
    ) -> ScopeView:
        scope_key = self._scope_key(scope_type, product_id, product_version_id)
        try:
            with self._session_factory.begin() as session:
                self._user(session, user_id)
                self._validate_target(session, scope_type, product_id, product_version_id)
                existing = self._repository.find_scope(session, user_id, scope_key)
                if existing is not None:
                    return self._view(session, existing)
                scope = UserProductScope(
                    user_id=user_id,
                    scope_type=scope_type,
                    product_id=product_id,
                    product_version_id=product_version_id,
                    scope_key=scope_key,
                    created_by=actor_id,
                )
                session.add(scope)
                session.flush()
                self._audit(session, actor_id, "insert", scope, user_id)
                return self._view(session, scope)
        except IntegrityError as error:
            with self._session_factory() as session:
                existing = self._repository.find_scope(session, user_id, scope_key)
                if existing is not None:
                    return self._view(session, existing)
            raise ScopeInvalidError() from error

    def revoke(self, *, actor_id: int, user_id: int, scope_id: int) -> None:
        with self._session_factory.begin() as session:
            self._user(session, user_id)
            scope = self._repository.get_scope(session, user_id, scope_id)
            if scope is None:
                return
            self._audit(session, actor_id, "delete", scope, user_id)
            session.delete(scope)

    def require_product_access(self, user: PublicUser, product_id: int) -> None:
        with self._session_factory() as session:
            if session.get(Product, product_id) is None:
                raise ScopeTargetNotFoundError()
            if "admin" not in user.roles and not self._repository.has_product_access(session, user.id, product_id):
                raise ProductScopeForbiddenError()

    def require_version_access(self, user: PublicUser, version_id: int) -> None:
        with self._session_factory() as session:
            if session.get(ProductVersion, version_id) is None:
                raise ScopeTargetNotFoundError()
            if "admin" not in user.roles and not self._repository.has_version_access(session, user.id, version_id):
                raise ProductScopeForbiddenError()

    @staticmethod
    def require_assigned_role(
        user: PublicUser,
        *,
        required_role: str,
        assigned_user_id: int,
        submitted_by: int | None = None,
        forbid_self_review: bool = False,
    ) -> None:
        if required_role not in user.roles or user.id != assigned_user_id:
            raise ProductScopeForbiddenError()
        if forbid_self_review and submitted_by == user.id:
            raise ProductScopeForbiddenError()

    @staticmethod
    def _scope_key(scope_type: str, product_id: int, product_version_id: int | None) -> str:
        if scope_type == "product" and product_version_id is None:
            return f"product:{product_id}"
        if scope_type == "version" and product_version_id is not None:
            return f"version:{product_version_id}"
        raise ScopeInvalidError()

    @staticmethod
    def _user(session: Session, user_id: int) -> AppUser:
        user = session.get(AppUser, user_id)
        if user is None:
            raise ScopeTargetNotFoundError()
        return user

    @staticmethod
    def _validate_target(
        session: Session,
        scope_type: str,
        product_id: int,
        product_version_id: int | None,
    ) -> None:
        product = session.get(Product, product_id)
        if product is None:
            raise ScopeTargetNotFoundError()
        if scope_type == "product":
            if product_version_id is not None:
                raise ScopeInvalidError()
            return
        if scope_type != "version" or product_version_id is None:
            raise ScopeInvalidError()
        version = session.get(ProductVersion, product_version_id)
        if version is None:
            raise ScopeTargetNotFoundError()
        if version.product_id != product_id:
            raise ScopeInvalidError()

    @staticmethod
    def _is_effective(session: Session, scope: UserProductScope) -> bool:
        product = session.get(Product, scope.product_id)
        if product is None or product.status != "active":
            return False
        if scope.scope_type == "product":
            return True
        version = session.get(ProductVersion, scope.product_version_id)
        return version is not None and version.product_id == product.id and version.status == "active"

    @classmethod
    def _view(cls, session: Session, scope: UserProductScope) -> ScopeView:
        return ScopeView(
            scope.id,
            scope.user_id,
            scope.scope_type,
            scope.product_id,
            scope.product_version_id,
            scope.scope_key,
            scope.created_by,
            scope.created_at,
            scope.updated_at,
            cls._is_effective(session, scope),
        )

    @staticmethod
    def _audit(session: Session, actor_id: int, action: str, scope: UserProductScope, user_id: int) -> None:
        session.add(
            AuditLog(
                user_id=actor_id,
                action=action,
                object_type="user_product_scope",
                object_id=str(scope.id),
                detail_json={
                    "target_user_id": user_id,
                    "scope_type": scope.scope_type,
                    "product_id": scope.product_id,
                    "product_version_id": scope.product_version_id,
                },
            )
        )
