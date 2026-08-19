from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.models.user import AppUser, AuditLog
from app.repositories.users import UserRepository
from app.services.authentication import AuthenticationService


class UserManagementError(ValueError):
    code = "USER_MANAGEMENT_ERROR"


class UserNotFoundError(UserManagementError):
    code = "USER_NOT_FOUND"


class UserLoginNameConflictError(UserManagementError):
    code = "USER_LOGIN_NAME_CONFLICT"


class UserVersionConflictError(UserManagementError):
    code = "USER_VERSION_CONFLICT"


@dataclass(frozen=True)
class ManagedUser:
    id: int
    login_name: str
    display_name: str
    roles: list[str]
    status: str
    last_login_at: datetime | None
    row_version: int
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class UserPage:
    items: list[ManagedUser]
    total: int
    page: int
    page_size: int


class UserManagementService:
    def __init__(
        self,
        session_factory: sessionmaker,
        authentication_service: AuthenticationService,
    ) -> None:
        self._session_factory = session_factory
        self._authentication_service = authentication_service
        self._repository = UserRepository()

    @staticmethod
    def _managed_user(user: AppUser) -> ManagedUser:
        return ManagedUser(
            id=user.id,
            login_name=user.login_name,
            display_name=user.display_name,
            roles=list(user.roles_json),
            status=user.status,
            last_login_at=user.last_login_at,
            row_version=user.row_version,
            created_at=user.created_at,
            updated_at=user.updated_at,
        )

    @staticmethod
    def _audit(
        session: Session,
        *,
        actor_id: int,
        action: str,
        object_id: int,
        detail: dict[str, object],
    ) -> None:
        session.add(
            AuditLog(
                user_id=actor_id,
                action=action,
                object_type="app_user",
                object_id=str(object_id),
                detail_json=detail,
            )
        )

    def list_users(
        self,
        *,
        query: str | None,
        status: str | None,
        role: str | None,
        page: int,
        page_size: int,
    ) -> UserPage:
        with self._session_factory() as session:
            users = self._repository.list_users(session, query=query, status=status)
            if role:
                users = [user for user in users if role in user.roles_json]
            total = len(users)
            start = (page - 1) * page_size
            return UserPage(
                items=[self._managed_user(user) for user in users[start : start + page_size]],
                total=total,
                page=page,
                page_size=page_size,
            )

    def get_user(self, user_id: int) -> ManagedUser:
        with self._session_factory() as session:
            user = self._repository.get_by_id(session, user_id)
            if user is None:
                raise UserNotFoundError()
            return self._managed_user(user)

    def create_user(
        self,
        *,
        actor_id: int,
        login_name: str,
        display_name: str,
        password: str,
        roles: list[str],
    ) -> ManagedUser:
        try:
            with self._session_factory.begin() as session:
                if self._repository.get_by_login_name(session, login_name) is not None:
                    raise UserLoginNameConflictError()
                user = AppUser(
                    login_name=login_name,
                    display_name=display_name,
                    password_hash=self._authentication_service.hash_password(password),
                    roles_json=roles,
                    status="active",
                    row_version=1,
                )
                session.add(user)
                session.flush()
                self._audit(
                    session,
                    actor_id=actor_id,
                    action="insert",
                    object_id=user.id,
                    detail={
                        "login_name": login_name,
                        "display_name": display_name,
                        "roles": roles,
                        "status": "active",
                        "row_version": 1,
                    },
                )
                result = self._managed_user(user)
            return result
        except IntegrityError as error:
            raise UserLoginNameConflictError() from error

    def update_user(
        self,
        *,
        actor_id: int,
        user_id: int,
        display_name: str,
        roles: list[str],
        row_version: int,
    ) -> ManagedUser:
        with self._session_factory.begin() as session:
            before = self._get_for_update(session, user_id)
            previous_display_name = before.display_name
            previous_roles = list(before.roles_json)
            if not self._repository.update_if_version(
                session,
                user_id,
                row_version,
                display_name=display_name,
                roles_json=roles,
                updated_at=datetime.now(),
            ):
                raise UserVersionConflictError()
            session.expire(before)
            user = self._repository.get_by_id(session, user_id)
            self._audit(
                session,
                actor_id=actor_id,
                action="update",
                object_id=user_id,
                detail={
                    "display_name": {"from": previous_display_name, "to": display_name},
                    "roles": {"from": previous_roles, "to": roles},
                    "row_version": {"from": row_version, "to": row_version + 1},
                },
            )
            return self._managed_user(user)

    def reset_password(
        self,
        *,
        actor_id: int,
        user_id: int,
        password: str,
        row_version: int,
    ) -> ManagedUser:
        with self._session_factory.begin() as session:
            user = self._get_for_update(session, user_id)
            if not self._repository.update_if_version(
                session,
                user_id,
                row_version,
                password_hash=self._authentication_service.hash_password(password),
                updated_at=datetime.now(),
            ):
                raise UserVersionConflictError()
            session.expire(user)
            updated = self._repository.get_by_id(session, user_id)
            self._audit(
                session,
                actor_id=actor_id,
                action="update",
                object_id=user_id,
                detail={
                    "password_reset": True,
                    "row_version": {"from": row_version, "to": row_version + 1},
                },
            )
            return self._managed_user(updated)

    def disable_user(self, *, actor_id: int, user_id: int, row_version: int) -> ManagedUser:
        with self._session_factory.begin() as session:
            user = self._get_for_update(session, user_id)
            if user.status == "disabled":
                return self._managed_user(user)
            if not self._repository.update_if_version(
                session,
                user_id,
                row_version,
                status="disabled",
                updated_at=datetime.now(),
            ):
                raise UserVersionConflictError()
            session.expire(user)
            updated = self._repository.get_by_id(session, user_id)
            self._audit(
                session,
                actor_id=actor_id,
                action="update",
                object_id=user_id,
                detail={
                    "status": {"from": "active", "to": "disabled"},
                    "row_version": {"from": row_version, "to": row_version + 1},
                },
            )
            return self._managed_user(updated)

    def _get_for_update(self, session: Session, user_id: int) -> AppUser:
        user = self._repository.get_by_id(session, user_id)
        if user is None:
            raise UserNotFoundError()
        return user
