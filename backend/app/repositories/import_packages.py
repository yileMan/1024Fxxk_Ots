from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.imports import ImportBatch
from app.models.ots import OtsComponent


class ImportPackageRepository:
    def get_by_id(self, session: Session, batch_id: int) -> ImportBatch | None:
        return session.get(ImportBatch, batch_id)

    def get_by_package_sha256(self, session: Session, package_sha256: str) -> ImportBatch | None:
        return session.scalar(
            select(ImportBatch).where(ImportBatch.package_sha256 == package_sha256)
        )

    def get_by_batch_no(self, session: Session, batch_no: str) -> ImportBatch | None:
        return session.scalar(select(ImportBatch).where(ImportBatch.batch_no == batch_no))

    def list_ots_ids(self, session: Session) -> set[int]:
        return set(session.scalars(select(OtsComponent.id)).all())
