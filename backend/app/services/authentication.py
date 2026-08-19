from __future__ import annotations

from dataclasses import dataclass

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from sqlalchemy.orm import sessionmaker

from app.models.user import AppUser
from app.repositories.users import UserRepository


class InvalidCredentialsError(ValueError):
    pass


class InvalidSessionError(ValueError):
    pass


@dataclass(frozen=True)
class PublicUser:
    id: int
    login_name: str
    display_name: str
    roles: list[str]


class AuthenticationService:
    def __init__(self, session_factory: sessionmaker) -> None:
        self._session_factory = session_factory
        self._repository = UserRepository()
        self._password_hasher = PasswordHasher()

    @staticmethod
    def _public_user(user: AppUser) -> PublicUser:
        return PublicUser(user.id, user.login_name, user.display_name, list(user.roles_json))

    def initialize_admin(self, login_name: str, display_name: str, password: str) -> PublicUser | None:
        with self._session_factory.begin() as session:
            if self._repository.get_by_login_name(session, login_name) is not None:
                return None
            user = AppUser(
                login_name=login_name,
                display_name=display_name,
                password_hash=self.hash_password(password),
                roles_json=["admin"],
                status="active",
            )
            session.add(user)
            session.flush()
            return self._public_user(user)

    def hash_password(self, password: str) -> str:
        return self._password_hasher.hash(password)

    def login(self, login_name: str, password: str) -> PublicUser:
        with self._session_factory.begin() as session:
            user = self._repository.get_by_login_name(session, login_name)
            if user is None:
                raise InvalidCredentialsError()
            try:
                password_matches = self._password_hasher.verify(user.password_hash, password)
            except (InvalidHashError, VerificationError):
                password_matches = False
            if not password_matches:
                raise InvalidCredentialsError()
            return self._public_user(user)

    def current_user(self, user_id: str) -> PublicUser:
        try:
            parsed_user_id = int(user_id)
        except ValueError as error:
            raise InvalidSessionError() from error
        with self._session_factory() as session:
            user = self._repository.get_by_id(session, parsed_user_id)
            if user is None:
                raise InvalidSessionError()
            return self._public_user(user)
