from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.user import AppUser


class UserRepository:
    def get_by_login_name(self, session: Session, login_name: str) -> AppUser | None:
        return session.scalar(select(AppUser).where(AppUser.login_name == login_name))

    def get_by_id(self, session: Session, user_id: int) -> AppUser | None:
        return session.get(AppUser, user_id)
