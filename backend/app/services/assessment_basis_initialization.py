from __future__ import annotations

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session, sessionmaker

from app.models.assessments import ProductAssessment
from app.models.imports import Vulnerability, VulnerabilityOtsMatch
from app.models.ots import ProductOts
from app.services.automatic_reassessment import build_assessment_basis


class AssessmentBasisInitializer:
    def __init__(self, session_factory: sessionmaker) -> None:
        self._session_factory = session_factory

    def run(self, *, dry_run: bool, batch_size: int = 500) -> dict[str, object]:
        if batch_size < 1:
            raise ValueError("batch_size must be positive")
        with self._session_factory() as session:
            eligible = self._remaining(session)
        if dry_run:
            return self._summary(True, eligible, 0, eligible)

        initialized = 0
        last_id = 0
        while True:
            with self._session_factory.begin() as session:
                rows = self._page(session, last_id=last_id, limit=batch_size)
                if not rows:
                    break
                for assessment, vulnerability, relation, candidate in rows:
                    basis = build_assessment_basis(
                        source=vulnerability,
                        candidate=candidate,
                        product_ots_id=relation.id,
                        product_ots_status=relation.status,
                        kev_available=False,
                    )
                    assessment.assessment_basis_sha256 = basis.sha256
                    assessment.assessment_basis_json = basis.data
                    last_id = assessment.id
                    initialized += 1
        with self._session_factory() as session:
            remaining = self._remaining(session)
        return self._summary(False, eligible, initialized, remaining)

    @staticmethod
    def _page(
        session: Session, *, last_id: int, limit: int
    ) -> list[tuple[ProductAssessment, Vulnerability, ProductOts, VulnerabilityOtsMatch | None]]:
        statement = (
            select(ProductAssessment, Vulnerability, ProductOts, VulnerabilityOtsMatch)
            .join(ProductOts, ProductOts.id == ProductAssessment.product_ots_id)
            .join(Vulnerability, Vulnerability.id == ProductAssessment.vulnerability_id)
            .outerjoin(
                VulnerabilityOtsMatch,
                and_(
                    VulnerabilityOtsMatch.vulnerability_id == Vulnerability.id,
                    VulnerabilityOtsMatch.ots_component_id == ProductOts.ots_component_id,
                ),
            )
            .where(
                ProductAssessment.id > last_id,
                ProductAssessment.is_current.is_(True),
                or_(
                    ProductAssessment.assessment_basis_sha256.is_(None),
                    ProductAssessment.assessment_basis_json.is_(None),
                ),
            )
            .order_by(ProductAssessment.id)
            .limit(limit)
        )
        return list(session.execute(statement).tuples().all())

    @staticmethod
    def _remaining(session: Session) -> int:
        return int(session.scalar(
            select(func.count(ProductAssessment.id)).where(
                ProductAssessment.is_current.is_(True),
                or_(
                    ProductAssessment.assessment_basis_sha256.is_(None),
                    ProductAssessment.assessment_basis_json.is_(None),
                ),
            )
        ) or 0)

    @staticmethod
    def _summary(
        dry_run: bool, eligible: int, initialized: int, remaining: int
    ) -> dict[str, object]:
        return {
            "dry_run": dry_run,
            "scanned_count": eligible,
            "eligible_count": eligible,
            "initialized_count": initialized,
            "remaining_count": remaining,
        }
