from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from itsdangerous import BadSignature, URLSafeSerializer
from sqlalchemy.orm import sessionmaker

from app.models.user import AppUser
from app.repositories.users import UserRepository

SESSION_SECONDS = 2 * 60 * 60


class PasswordPolicyError(ValueError):
    pass


class InvalidCredentialsError(ValueError):
    pass


class InvalidSessionError(ValueError):
    pass


class DisabledUserError(ValueError):
    pass


@dataclass(frozen=True)
class PublicUser:
    id: int
    login_name: str
    display_name: str
    roles: list[str]


class AuthenticationService:
    def __init__(self, session_factory: sessionmaker, secret: str = "test-secret-that-is-long-enough-for-authentication") -> None:
        self._session_factory = session_factory
        self._repository = UserRepository()
        self._password_hasher = PasswordHasher()
        self._serializer = URLSafeSerializer(secret, salt="ots-session-v1")

    @staticmethod
    def _validate_password(password: str) -> None:
        if not 12 <= len(password) <= 256:
            raise PasswordPolicyError("密码长度必须为 12 至 256 个字符")

    @staticmethod
    def _public_user(user: AppUser) -> PublicUser:
        return PublicUser(user.id, user.login_name, user.display_name, list(user.roles_json))

    def initialize_admin(self, login_name: str, display_name: str, password: str) -> PublicUser | None:
        self._validate_password(password)
        with self._session_factory.begin() as session:
            if self._repository.get_by_login_name(session, login_name) is not None:
                return None
            user = AppUser(
                login_name=login_name,
                display_name=display_name,
                password_hash=self._password_hasher.hash(password),
                roles_json=["admin"],
                status="active",
            )
            session.add(user)
            session.flush()
            return self._public_user(user)

    def login(self, login_name: str, password: str) -> PublicUser:
        with self._session_factory.begin() as session:
            user = self._repository.get_by_login_name(session, login_name)
            if user is None or user.status != "active":
                raise InvalidCredentialsError()
            try:
                password_matches = self._password_hasher.verify(user.password_hash, password)
            except (InvalidHashError, VerificationError):
                password_matches = False
            if not password_matches:
                raise InvalidCredentialsError()
            user.last_login_at = datetime.now(timezone.utc)
            return self._public_user(user)

    def create_session_token(self, user_id: int, issued_at: datetime | None = None) -> str:
        issued_at = issued_at or datetime.now(timezone.utc)
        payload = {
            "v": 1,
            "uid": user_id,
            "iat": int(issued_at.timestamp()),
            "exp": int((issued_at + timedelta(seconds=SESSION_SECONDS)).timestamp()),
        }
        return self._serializer.dumps(payload)

    def current_user(self, token: str) -> PublicUser:
        try:
            payload = self._serializer.loads(token)
            expires_at = int(payload["exp"])
            user_id = int(payload["uid"])
        except (BadSignature, KeyError, TypeError, ValueError) as error:
            raise InvalidSessionError() from error
        if datetime.now(timezone.utc).timestamp() > expires_at:
            raise InvalidSessionError()
        with self._session_factory() as session:
            user = self._repository.get_by_id(session, user_id)
            if user is None:
                raise InvalidSessionError()
            if user.status != "active":
                raise DisabledUserError()
            return self._public_user(user)
