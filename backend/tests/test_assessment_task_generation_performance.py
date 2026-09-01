from __future__ import annotations

from datetime import datetime, timezone
from time import perf_counter
import tracemalloc

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.imports import Vulnerability
from app.models.ots import OtsComponent, ProductOts
from app.models.products import Product, ProductVersion
from app.models.user import AppUser, Base
from app.services.assessment_tasks import AssessmentTaskService
from app.services.vulnerability_matching import CalculatedCandidate


def test_ten_thousand_candidate_product_tasks_stay_within_acceptance_budget(
    tmp_path,
) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'ots10-performance.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    now = datetime.now(timezone.utc)
    with factory.begin() as session:
        owner = AppUser(
            login_name="owner", display_name="负责人", password_hash="x",
            roles_json=["product_owner"], status="active", row_version=1,
        )
        reviewer = AppUser(
            login_name="reviewer", display_name="审核人", password_hash="x",
            roles_json=["reviewer"], status="active", row_version=1,
        )
        product = Product(
            product_code="PERF", product_name="性能产品", status="active", row_version=1,
        )
        ots = OtsComponent(
            ots_name="OpenSSL", ots_version="3.0.0",
            official_website="https://openssl.org", is_eol=False, row_version=1,
        )
        session.add_all([owner, reviewer, product, ots])
        session.flush()
        version = ProductVersion(
            product_id=product.id, version_no="1.0", primary_cvss_version="3.1",
            owner_id=owner.id, reviewer_id=reviewer.id, status="active", row_version=1,
        )
        session.add(version)
        session.flush()
        relation = ProductOts(
            product_version_id=version.id, ots_component_id=ots.id, created_by=owner.id,
        )
        session.add(relation)
        session.flush()

        vulnerabilities = [
            Vulnerability(
                id=index + 1,
                cve_id=f"CVE-2026-{index + 1:05d}",
                affected_ranges_json=[],
                content_sha256=f"{index:064x}",
                source_modified_at=now,
            )
            for index in range(10_000)
        ]
        targets = [
            CalculatedCandidate(
                vulnerability_id=item.id,
                cve_id=item.cve_id,
                ots_component_id=ots.id,
                ots_name=ots.ots_name,
                ots_version=ots.ots_version,
                match_method="cpe",
                match_basis="性能验收候选",
                evidence={"schema_version": "1.0", "matched_ranges": []},
                content_sha256=item.content_sha256,
                source_modified_at=now,
            )
            for item in vulnerabilities
        ]

        tracemalloc.start()
        started_at = perf_counter()
        plan = AssessmentTaskService().plan(
            session,
            vulnerabilities=vulnerabilities,
            targets=targets,
            existing_candidates=[],
            status="pending",
        )
        elapsed = perf_counter() - started_at
        _, peak_bytes = tracemalloc.get_traced_memory()
        tracemalloc.stop()

    engine.dispose()
    print(
        "ots10_task_benchmark count=10000 products=1 "
        f"elapsed_seconds={elapsed:.3f} peak_mib={peak_bytes / 1024 / 1024:.2f}"
    )
    assert plan.result["task_inserted_count"] == 10_000
    assert plan.result["truncated_task_count"] == 9_900
    assert elapsed < 300
    assert peak_bytes < 256 * 1024 * 1024
