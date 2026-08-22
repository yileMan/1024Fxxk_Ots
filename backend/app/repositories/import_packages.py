from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.imports import ImportBatch, Vulnerability


class ImportPackageRepository:
    def get_by_id(self, session: Session, batch_id: int) -> ImportBatch | None:
        return session.get(ImportBatch, batch_id)

    def get_by_package_sha256(self, session: Session, package_sha256: str) -> ImportBatch | None:
        return session.scalar(
            select(ImportBatch).where(ImportBatch.package_sha256 == package_sha256)
        )

    def get_by_batch_no(self, session: Session, batch_no: str) -> ImportBatch | None:
        return session.scalar(select(ImportBatch).where(ImportBatch.batch_no == batch_no))

    def list_vulnerabilities(
        self, session: Session, cve_ids: set[str]
    ) -> dict[str, Vulnerability]:
        if not cve_ids:
            return {}
        return {
            item.cve_id: item
            for item in session.scalars(
                select(Vulnerability).where(Vulnerability.cve_id.in_(cve_ids))
            )
        }
