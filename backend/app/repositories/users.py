from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from app.models.user import AppUser


class UserRepository:
    def get_by_login_name(self, session: Session, login_name: str) -> AppUser | None:
        return session.scalar(select(AppUser).where(AppUser.login_name == login_name))

    def get_by_id(self, session: Session, user_id: int) -> AppUser | None:
        return session.get(AppUser, user_id)

    def list_users(
        self,
        session: Session,
        *,
        query: str | None = None,
        status: str | None = None,
    ) -> list[AppUser]:
        statement = select(AppUser).order_by(AppUser.id)
        if query:
            pattern = f"%{query}%"
            statement = statement.where(
                or_(AppUser.login_name.like(pattern), AppUser.display_name.like(pattern))
            )
        if status:
            statement = statement.where(AppUser.status == status)
        return list(session.scalars(statement).all())

    def update_if_version(
        self,
        session: Session,
        user_id: int,
        row_version: int,
        **values: object,
    ) -> bool:
        result = session.execute(
            update(AppUser)
            .where(AppUser.id == user_id, AppUser.row_version == row_version)
            .values(**values, row_version=AppUser.row_version + 1)
        )
        return result.rowcount == 1
