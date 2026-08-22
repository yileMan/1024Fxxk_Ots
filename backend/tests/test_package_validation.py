from __future__ import annotations

import csv
import json
import time
import tracemalloc
from dataclasses import replace
from datetime import datetime, timezone
from io import BytesIO, StringIO
from zipfile import ZipFile

import pytest

from app.services.package_validation import (
    DEFAULT_LIMITS,
    ExistingVulnerability,
    PackageValidationError,
    content_hash,
    errors_csv,
    select_cvss31,
    validate_package,
)
from tests.package_fixtures import (
    CSV_FIELDS,
    affected_software,
    base_rows,
    build_legacy_three_file_package,
    build_package,
    build_zip_with_duplicate_member,
    build_zip_with_member,
    build_zip_with_symlink,
    csv_bytes,
    json_value,
    nvd_row,
)


PACKAGE_NAME = "ots_intelligence_20260822_010203.zip"


def error_codes(result) -> set[str]:
    return {error.error_code for error in result.errors}


def test_fixture_is_deterministic_and_contains_exact_two_file_contract() -> None:
    first = build_package()
    assert first == build_package()
    with ZipFile(BytesIO(first)) as archive:
        assert set(archive.namelist()) == {"manifest.csv", "nvd_cves.csv"}
        manifest = list(csv.DictReader(StringIO(archive.read("manifest.csv").decode())))
    assert [row["record_type"] for row in manifest] == ["package", "file"]
    assert manifest[1]["file_name"] == "nvd_cves.csv"


def test_two_file_package_validates_and_legacy_three_file_package_is_red() -> None:
    result = validate_package(build_package(), PACKAGE_NAME)
    assert result.is_valid is True
    assert result.batch_no == "BATCH-20260822-001"
    assert result.source_name == "nvd"
    assert result.summary.new == 1
    assert result.can_import is True
    assert result.classification_basis == "vulnerability_current_facts_v1"

    with pytest.raises(PackageValidationError) as caught:
        validate_package(build_legacy_three_file_package(), PACKAGE_NAME)
    assert caught.value.code == "PACKAGE_STRUCTURE_INVALID"


@pytest.mark.parametrize(
    ("file_name", "package", "expected_code"),
    [
        ("wrong.zip", build_package(), "PACKAGE_TYPE_INVALID"),
        (PACKAGE_NAME, b"not-a-zip", "PACKAGE_STRUCTURE_INVALID"),
        (PACKAGE_NAME, build_package(omit_files={"nvd_cves.csv"}), "PACKAGE_STRUCTURE_INVALID"),
        (PACKAGE_NAME, build_package(extra_files={"kev.csv": b"cve_id\r\n"}), "PACKAGE_STRUCTURE_INVALID"),
    ],
)
def test_rejects_invalid_name_archive_and_file_set(file_name: str, package: bytes, expected_code: str) -> None:
    with pytest.raises(PackageValidationError) as caught:
        validate_package(package, file_name)
    assert caught.value.code == expected_code


@pytest.mark.parametrize("unsafe_name", ["../manifest.csv", "/manifest.csv", "C:/manifest.csv", r"C:\manifest.csv", "nested/manifest.csv"])
def test_rejects_unsafe_member_paths(unsafe_name: str) -> None:
    with pytest.raises(PackageValidationError) as caught:
        validate_package(build_zip_with_member(unsafe_name), PACKAGE_NAME)
    assert caught.value.code == "PACKAGE_ZIP_UNSAFE"


@pytest.mark.parametrize("package", [build_zip_with_duplicate_member(), build_zip_with_symlink()])
def test_rejects_duplicate_members_and_links(package: bytes) -> None:
    with pytest.raises(PackageValidationError) as caught:
        validate_package(package, PACKAGE_NAME)
    assert caught.value.code == "PACKAGE_ZIP_UNSAFE"


def test_csv_allows_quoted_lf_and_crlf_but_rejects_bare_lf() -> None:
    for description in ("第一段\n第二段", "第一段\r\n第二段"):
        rows = base_rows()
        rows["nvd_cves.csv"][0]["description"] = description
        result = validate_package(build_package(rows=rows), PACKAGE_NAME)
        assert result.is_valid is True
        assert result.records[0].description == "第一段\n第二段"

    bare_lf = csv_bytes("nvd_cves.csv", [nvd_row()], lineterminator="\n")
    result = validate_package(build_package(override_files={"nvd_cves.csv": bare_lf}), PACKAGE_NAME)
    assert result.is_valid is False
    assert any(error.reason == "CSV 记录必须使用 CRLF 换行" for error in result.errors)


@pytest.mark.parametrize("content", [b"\xef\xbb\xbfcve_id\r\n", b"cve_id\r\nCVE-2026-\x000001\r\n", b"\xff\xfe\r\n"])
def test_rejects_bom_nul_and_non_utf8(content: bytes) -> None:
    result = validate_package(build_package(override_files={"nvd_cves.csv": content}), PACKAGE_NAME)
    assert result.is_valid is False
    assert "PACKAGE_CSV_INVALID" in error_codes(result)


def test_field_limit_accepts_exactly_one_mib_and_rejects_one_byte_more() -> None:
    rows = base_rows()
    rows["nvd_cves.csv"][0]["description"] = "x" * (1024 * 1024)
    accepted = validate_package(
        build_package(rows=rows),
        PACKAGE_NAME,
        limits=replace(DEFAULT_LIMITS, max_compression_ratio=10_000),
    )
    assert accepted.is_valid is True
    rows["nvd_cves.csv"][0]["description"] += "x"
    rejected = validate_package(
        build_package(rows=rows),
        PACKAGE_NAME,
        limits=replace(DEFAULT_LIMITS, max_compression_ratio=10_000),
    )
    assert rejected.is_valid is False
    assert any(error.field == "description" for error in rejected.errors)


def test_invalid_json_after_multiline_record_has_exact_physical_start_line() -> None:
    rows = base_rows()
    rows["nvd_cves.csv"][0]["description"] = "第一段\n第二段"
    second = nvd_row("CVE-2026-0002")
    second["cvss_json"] = "{"
    rows["nvd_cves.csv"].append(second)
    result = validate_package(build_package(rows=rows), PACKAGE_NAME)
    error = next(error for error in result.errors if error.field == "cvss_json")
    assert error.row_number == 4


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("cvss_json", "[NaN]"),
        ("cwes_json", json_value({"cwe": "CWE-79"})),
        ("references_json", "null"),
        ("configurations_json", json_value({"nodes": []})),
        ("affected_software_json", json_value({"product": "openssl"})),
    ],
)
def test_five_json_fields_require_standard_json_arrays(field: str, value: str) -> None:
    rows = base_rows()
    rows["nvd_cves.csv"][0][field] = value
    result = validate_package(build_package(rows=rows), PACKAGE_NAME)
    error = next(error for error in result.errors if error.field == field)
    assert error.row_number == 2
    assert error.error_code == "PACKAGE_CSV_INVALID"


def test_affected_software_supports_exact_range_wildcard_and_multiple_products() -> None:
    rows = base_rows()
    rows["nvd_cves.csv"][0]["affected_software_json"] = json_value(
        [
            affected_software(version="3.1.1", product="linux_kernel", vendor="linux", part="o"),
            affected_software(version="*", version_start_including="1.0.0", version_end_excluding="1.0.2"),
            affected_software(version=None, product="libssl"),
        ]
    )
    result = validate_package(build_package(rows=rows), PACKAGE_NAME)
    assert result.is_valid is True
    assert len(result.records[0].affected_software) == 3
    assert result.records[0].configurations


def test_affected_software_rejects_missing_extra_wrong_type_and_conflicting_bounds() -> None:
    valid = affected_software()
    cases = [
        {key: value for key, value in valid.items() if key != "vendor"},
        {**valid, "extra": "x"},
        {**valid, "vulnerable": "true"},
        {**valid, "version_start_including": "1", "version_start_excluding": "2"},
    ]
    for value in cases:
        rows = base_rows()
        rows["nvd_cves.csv"][0]["affected_software_json"] = json_value([value])
        result = validate_package(build_package(rows=rows), PACKAGE_NAME)
        assert result.is_valid is False
        assert any(error.field == "affected_software_json" for error in result.errors)


@pytest.mark.parametrize("status", ["Rejected", "Awaiting Analysis", "Undergoing Analysis"])
def test_rejected_unanalyzed_and_empty_applicability_are_valid(status: str) -> None:
    rows = base_rows()
    row = rows["nvd_cves.csv"][0]
    row["vuln_status"] = status
    row["affected_software_json"] = "[]"
    row["configurations_json"] = "[]"
    result = validate_package(build_package(rows=rows), PACKAGE_NAME)
    assert result.is_valid is True
    assert result.summary.new == 1


def test_manifest_validates_release_window_digest_and_exact_records() -> None:
    digest_mismatch = validate_package(
        build_package(mutate_files={"nvd_cves.csv": b"changed\r\n"}), PACKAGE_NAME
    )
    assert "PACKAGE_DIGEST_MISMATCH" in error_codes(digest_mismatch)

    invalid_window = validate_package(
        build_package(window_start="2026-08-23T00:00:00Z", window_end="2026-08-22T00:00:00Z"),
        PACKAGE_NAME,
    )
    assert "PACKAGE_MANIFEST_INVALID" in error_codes(invalid_window)

    missing_release = validate_package(build_package(source_release=""), PACKAGE_NAME)
    assert "PACKAGE_MANIFEST_INVALID" in error_codes(missing_release)

    def duplicate_file(rows: list[dict[str, object]]) -> None:
        rows.append(dict(rows[1]))

    duplicate = validate_package(build_package(manifest_mutator=duplicate_file), PACKAGE_NAME)
    assert "PACKAGE_MANIFEST_INVALID" in error_codes(duplicate)


def test_package_duplicate_and_conflict_are_classified() -> None:
    rows = base_rows()
    rows["nvd_cves.csv"].append(dict(rows["nvd_cves.csv"][0]))
    duplicate = validate_package(build_package(rows=rows), PACKAGE_NAME)
    assert duplicate.is_valid is True
    assert duplicate.summary.duplicate == 1

    rows["nvd_cves.csv"][1]["description"] = "冲突"
    conflict = validate_package(build_package(rows=rows), PACKAGE_NAME)
    assert conflict.is_valid is False
    assert conflict.summary.conflict == 1


def test_database_classification_uses_modified_time_and_content_hash() -> None:
    initial = validate_package(build_package(), PACKAGE_NAME)
    record = initial.records[0]
    existing = {
        record.cve_id: ExistingVulnerability(
            content_sha256=record.content_sha256,
            source_modified_at=record.last_modified_at,
        )
    }
    duplicate = validate_package(build_package(), PACKAGE_NAME, existing=existing)
    assert duplicate.summary.duplicate == 1

    rows = base_rows()
    rows["nvd_cves.csv"][0]["description"] = "更新描述"
    rows["nvd_cves.csv"][0]["last_modified_at"] = "2026-08-03T00:00:00Z"
    update = validate_package(build_package(rows=rows), PACKAGE_NAME, existing=existing)
    assert update.summary.update == 1
    assert update.can_import is True

    rows["nvd_cves.csv"][0]["last_modified_at"] = "2026-08-02T00:00:00Z"
    conflict = validate_package(build_package(rows=rows), PACKAGE_NAME, existing=existing)
    assert conflict.summary.conflict == 1
    assert conflict.can_import is False


def test_content_hash_is_deterministic_and_ignores_unordered_json_array_order() -> None:
    row = nvd_row()
    first = content_hash(row)
    cvss = json.loads(row["cvss_json"])
    cvss.append({"source": "vendor", "type": "Secondary", "cvssData": {"version": "3.1", "vectorString": "v", "baseScore": 4.0}})
    row["cvss_json"] = json_value(cvss)
    second = content_hash(row)
    row["cvss_json"] = json_value(list(reversed(cvss)))
    assert content_hash(row) == second
    assert first != second


def test_cvss31_selection_prefers_nvd_primary_and_preserves_all_scores() -> None:
    scores = [
        {"source": "vendor", "type": "Primary", "cvssData": {"version": "3.1", "baseScore": 9.8, "baseSeverity": "CRITICAL", "vectorString": "vendor"}},
        {"source": "nvd@nist.gov", "type": "Primary", "cvssData": {"version": "3.1", "baseScore": 7.5, "baseSeverity": "HIGH", "vectorString": "nvd"}},
        {"source": "nvd@nist.gov", "type": "Primary", "cvssData": {"version": "2.0", "baseScore": 5.0, "vectorString": "v2"}},
    ]
    selected = select_cvss31(scores)
    assert selected == (7.5, "HIGH", "nvd", "nvd@nist.gov")
    assert len(scores) == 3
    assert select_cvss31([]) == (None, None, None, None)


def test_error_output_is_bounded_and_crlf() -> None:
    rows = base_rows()
    rows["nvd_cves.csv"] = [{**nvd_row(f"CVE-2026-{index + 1:04d}"), "published_at": "bad"} for index in range(20)]
    result = validate_package(
        build_package(rows=rows),
        PACKAGE_NAME,
        limits=replace(DEFAULT_LIMITS, max_errors=5, max_error_value_chars=16),
    )
    assert len(result.errors) == 5
    assert result.truncated_error_count == result.total_error_count - 5
    content = errors_csv(result.errors)
    assert content.startswith(b"error_code,file_name,row_number,field,reason,rejected_value\r\n")


def test_ten_thousand_cves_validate_under_five_minutes_with_bounded_memory() -> None:
    rows = base_rows()
    rows["nvd_cves.csv"] = [nvd_row(f"CVE-2026-{index + 1:04d}") for index in range(10_000)]
    package = build_package(rows=rows)
    tracemalloc.start()
    started = time.perf_counter()
    try:
        result = validate_package(
            package,
            PACKAGE_NAME,
            limits=replace(DEFAULT_LIMITS, max_compression_ratio=10_000),
        )
        duration = time.perf_counter() - started
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert result.is_valid is True
    assert result.summary.new == 10_000
    assert duration < 300
    assert peak < 256 * 1024 * 1024
