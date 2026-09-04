from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json

from app.services.automatic_reassessment import (
    build_assessment_basis,
    diff_assessment_basis,
    merge_reassessment_changes,
)


NOW = datetime(2026, 9, 4, 8, 0, tzinfo=timezone.utc)


def source(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "source_status": "Analyzed",
        "cvss31_score": Decimal("7.50"),
        "cvss31_vector": "CVSS:3.1/A:H/I:H/C:H/S:U/UI:N/PR:N/AC:L/AV:N",
        "affected_ranges_json": [
            {
                "product": "OpenSSL",
                "vendor": "OpenSSL",
                "version": "3.0.0",
                "versionStartIncluding": "3.0.0",
                "versionEndExcluding": "3.0.2",
            }
        ],
        "is_kev": False,
        "kev_date_added": None,
        "kev_due_date": None,
        "kev_required_action": None,
        "description": "旧描述",
        "references_json": ["https://example.test/a"],
        "source_modified_at": "2026-09-01T00:00:00Z",
    }
    value.update(overrides)
    return value


def candidate(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "match_method": "name_version",
        "match_evidence_json": {
            "matched_ranges": [{"end": "3.0.2", "start": "3.0.0"}],
            "identity": {"name": "openssl", "version": "3.0.0"},
        },
        "match_basis": "OpenSSL 3.0.0 命中",
        "last_seen_batch_id": 9,
    }
    value.update(overrides)
    return value


def test_basis_is_canonical_and_has_stable_sha256() -> None:
    basis = build_assessment_basis(
        source=source(),
        candidate=candidate(),
        product_ots_id=12,
        product_ots_status="active",
        kev_available=False,
    )

    expected = {
        "candidate": {
            "exists": True,
            "match_evidence": {
                "identity": {"name": "openssl", "version": "3.0.0"},
                "matched_ranges": [{"end": "3.0.2", "start": "3.0.0"}],
            },
            "match_method": "name_version",
        },
        "product_context": {"product_ots_id": 12, "status": "active"},
        "schema_version": "1.0",
        "source": {
            "affected_ranges": [
                {
                    "product": "OpenSSL",
                    "vendor": "OpenSSL",
                    "version": "3.0.0",
                    "versionEndExcluding": "3.0.2",
                    "versionStartIncluding": "3.0.0",
                }
            ],
            "cvss31_score": "7.5",
            "cvss31_vector": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H",
            "kev": {"available": False},
            "status": "analyzed",
        },
    }
    canonical = json.dumps(expected, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    assert basis.data == expected
    assert basis.sha256 == hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def test_equivalent_order_whitespace_and_decimal_do_not_change_basis() -> None:
    first = build_assessment_basis(
        source=source(), candidate=candidate(), product_ots_id=12,
        product_ots_status="active", kev_available=False,
    )
    reordered = build_assessment_basis(
        source=source(
            source_status=" analyzed ",
            cvss31_score=7.5,
            affected_ranges_json=[{
                "versionEndExcluding": "3.0.2",
                "versionStartIncluding": "3.0.0",
                "version": "3.0.0",
                "vendor": "OpenSSL",
                "product": "OpenSSL",
            }],
            description="完全不同的描述",
            references_json=["https://example.test/other"],
            source_modified_at="2026-09-04T00:00:00Z",
        ),
        candidate=candidate(
            match_evidence_json={
                "identity": {"version": "3.0.0", "name": "openssl"},
                "matched_ranges": [{"start": "3.0.0", "end": "3.0.2"}],
            },
            match_basis="不同显示文案",
            last_seen_batch_id=88,
        ),
        product_ots_id=12,
        product_ots_status="active",
        kev_available=False,
    )

    assert reordered == first
    assert diff_assessment_basis(first.data, reordered.data, now=NOW) is None


def test_material_fields_produce_bounded_sorted_changes() -> None:
    before = build_assessment_basis(
        source=source(), candidate=candidate(), product_ots_id=12,
        product_ots_status="active", kev_available=True,
    )
    after = build_assessment_basis(
        source=source(
            source_status="Rejected",
            cvss31_score=Decimal("9.8"),
            cvss31_vector="CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:L",
            affected_ranges_json=[],
            is_kev=True,
            kev_date_added="2026-09-04",
            kev_due_date="2026-09-10",
            kev_required_action="立即升级",
        ),
        candidate=None,
        product_ots_id=12,
        product_ots_status="disabled",
        kev_available=True,
    )

    summary = diff_assessment_basis(before.data, after.data, now=NOW)

    assert summary is not None
    assert summary["trigger_type"] == "automatic_reassessment"
    assert summary["triggered_at"] == "2026-09-04T08:00:00Z"
    assert summary["change_types"] == ["candidate", "product_context", "source"]
    assert [item["field"] for item in summary["changes"]] == sorted(
        item["field"] for item in summary["changes"]
    )
    assert {item["field"] for item in summary["changes"]} >= {
        "candidate.exists",
        "product_context.status",
        "source.affected_ranges",
        "source.cvss31_score",
        "source.cvss31_vector",
        "source.kev.is_kev",
        "source.status",
    }
    assert summary["truncated_count"] == 0


def test_kev_is_compared_only_when_contract_marks_it_available() -> None:
    unavailable_before = build_assessment_basis(
        source=source(is_kev=False), candidate=candidate(), product_ots_id=12,
        product_ots_status="active", kev_available=False,
    )
    unavailable_after = build_assessment_basis(
        source=source(is_kev=True, kev_required_action="升级"), candidate=candidate(),
        product_ots_id=12, product_ots_status="active", kev_available=False,
    )
    available_after = build_assessment_basis(
        source=source(is_kev=True, kev_required_action="升级"), candidate=candidate(),
        product_ots_id=12, product_ots_status="active", kev_available=True,
    )

    assert unavailable_before == unavailable_after
    assert diff_assessment_basis(
        unavailable_before.data, available_after.data, now=NOW
    ) is not None


def test_change_merge_keeps_original_before_latest_after_and_removes_reverted_field() -> None:
    baseline = build_assessment_basis(
        source=source(), candidate=candidate(), product_ots_id=12,
        product_ots_status="active", kev_available=False,
    )
    first_target = build_assessment_basis(
        source=source(cvss31_score=8.0), candidate=candidate(), product_ots_id=12,
        product_ots_status="active", kev_available=False,
    )
    second_target = build_assessment_basis(
        source=source(cvss31_score=9.0, source_status="Rejected"),
        candidate=candidate(), product_ots_id=12,
        product_ots_status="active", kev_available=False,
    )
    reverted_target = build_assessment_basis(
        source=source(cvss31_score=Decimal("7.5"), source_status="Rejected"),
        candidate=candidate(), product_ots_id=12,
        product_ots_status="active", kev_available=False,
    )
    first = diff_assessment_basis(baseline.data, first_target.data, now=NOW)
    second = diff_assessment_basis(first_target.data, second_target.data, now=NOW)
    reverted = diff_assessment_basis(second_target.data, reverted_target.data, now=NOW)

    merged = merge_reassessment_changes(None, first)
    merged = merge_reassessment_changes(merged, second)
    merged = merge_reassessment_changes(merged, reverted)

    assert merged is not None
    by_field = {item["field"]: item for item in merged["changes"]}
    assert "source.cvss31_score" not in by_field
    assert by_field["source.status"] == {
        "field": "source.status", "before": "analyzed", "after": "rejected"
    }


def test_change_values_are_truncated_and_hashed() -> None:
    before = {"schema_version": "1.0", "source": {"affected_ranges": []}}
    after = {
        "schema_version": "1.0",
        "source": {"affected_ranges": [{"value": "x" * 2_000}]},
    }

    summary = diff_assessment_basis(before, after, now=NOW, max_value_chars=80)

    assert summary is not None
    change = summary["changes"][0]
    assert change["field"] == "source.affected_ranges"
    assert isinstance(change["after"], dict)
    assert change["after"]["truncated"] is True
    assert change["after"]["length"] > 80
    assert len(change["after"]["sha256"]) == 64
    assert len(change["after"]["preview"]) <= 80
