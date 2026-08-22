from __future__ import annotations

import csv
import json
import time
import tracemalloc
from dataclasses import replace
from io import BytesIO, StringIO
from zipfile import ZipFile

import pytest

from app.services.package_validation import (
    DEFAULT_LIMITS,
    PackageValidationError,
    errors_csv,
    validate_package,
)
from tests.package_fixtures import (
    CSV_FIELDS,
    base_rows,
    build_package,
    build_zip_with_duplicate_member,
    build_zip_with_member,
    build_zip_with_symlink,
    csv_bytes,
    json_value,
    nvd_row,
)


def error_codes(result) -> set[str]:
    return {error.error_code for error in result.errors}


def test_fixture_is_deterministic_and_contains_exact_three_file_contract() -> None:
    first = build_package()
    second = build_package()

    assert first == second
    with ZipFile(BytesIO(first)) as archive:
        assert set(archive.namelist()) == {"manifest.csv", "collector_scope.csv", "nvd_cves.csv"}
        manifest = list(csv.DictReader(StringIO(archive.read("manifest.csv").decode("utf-8"))))
    assert [row["file_name"] for row in manifest if row["record_type"] == "file"] == [
        "collector_scope.csv",
        "nvd_cves.csv",
    ]


def test_three_file_fixture_validates_complete_contract() -> None:
    result = validate_package(
        build_package(),
        "ots_intelligence_20260822_010203.zip",
        {1},
    )

    assert result.is_valid is True
    assert result.batch_no == "BATCH-20260822-001"
    assert result.format_version == "1.0"
    assert result.scope_count == 1
    assert result.classification_basis == "package_structure_v1"
    assert result.final_import_diff is False
    assert result.can_import is False
    assert set(result.file_stats) == {"nvd_cves.csv"}
    assert result.file_stats["nvd_cves.csv"].new == 1
    assert result.summary.update == 0
    assert result.summary.error == 0


@pytest.mark.parametrize(
    ("file_name", "package", "expected_code"),
    [
        ("wrong.zip", build_package(), "PACKAGE_TYPE_INVALID"),
        ("ots_intelligence_20260822_010203.csv", build_package(), "PACKAGE_TYPE_INVALID"),
        ("ots_intelligence_20260822_010203.zip", b"not-a-zip", "PACKAGE_STRUCTURE_INVALID"),
        (
            "ots_intelligence_20260822_010203.zip",
            build_package(omit_files={"nvd_cves.csv"}),
            "PACKAGE_STRUCTURE_INVALID",
        ),
        (
            "ots_intelligence_20260822_010203.zip",
            build_package(extra_files={"kev.csv": b"cve_id\r\n"}),
            "PACKAGE_STRUCTURE_INVALID",
        ),
        (
            "ots_intelligence_20260822_010203.zip",
            build_package(extra_files={"vulnerabilities.csv": b"cve_id\r\n"}),
            "PACKAGE_STRUCTURE_INVALID",
        ),
    ],
)
def test_rejects_invalid_name_archive_and_exact_file_set(
    file_name: str,
    package: bytes,
    expected_code: str,
) -> None:
    with pytest.raises(PackageValidationError) as caught:
        validate_package(package, file_name, {1})
    assert caught.value.code == expected_code


@pytest.mark.parametrize("mode", ["missing", "duplicate"])
def test_rejects_manifest_without_exactly_two_file_digest_records(mode: str) -> None:
    def mutate(rows: list[dict[str, object]]) -> None:
        nvd_file = next(
            row for row in rows if row.get("record_type") == "file" and row.get("file_name") == "nvd_cves.csv"
        )
        if mode == "missing":
            rows.remove(nvd_file)
        else:
            rows.append(dict(nvd_file))

    result = validate_package(
        build_package(manifest_mutator=mutate),
        "ots_intelligence_20260822_010203.zip",
        {1},
    )
    assert result.is_valid is False
    assert "PACKAGE_MANIFEST_INVALID" in error_codes(result)


@pytest.mark.parametrize(
    "unsafe_name",
    ["../manifest.csv", "/manifest.csv", "C:/manifest.csv", r"C:\manifest.csv", "nested/manifest.csv"],
)
def test_rejects_unsafe_member_paths(unsafe_name: str) -> None:
    with pytest.raises(PackageValidationError) as caught:
        validate_package(
            build_zip_with_member(unsafe_name),
            "ots_intelligence_20260822_010203.zip",
            {1},
        )
    assert caught.value.code == "PACKAGE_ZIP_UNSAFE"


@pytest.mark.parametrize("package", [build_zip_with_duplicate_member(), build_zip_with_symlink()])
def test_rejects_duplicate_members_and_symbolic_links(package: bytes) -> None:
    with pytest.raises(PackageValidationError) as caught:
        validate_package(package, "ots_intelligence_20260822_010203.zip", {1})
    assert caught.value.code == "PACKAGE_ZIP_UNSAFE"


def test_rejects_upload_member_and_row_resource_limits() -> None:
    package = build_package()
    with pytest.raises(PackageValidationError) as caught:
        validate_package(
            package,
            "ots_intelligence_20260822_010203.zip",
            {1},
            limits=replace(DEFAULT_LIMITS, max_upload_bytes=len(package) - 1),
        )
    assert caught.value.code == "PACKAGE_TOO_LARGE"

    rows = base_rows()
    rows["nvd_cves.csv"] = [nvd_row(f"CVE-2026-{index + 1:04d}") for index in range(3)]
    result = validate_package(
        build_package(rows=rows),
        "ots_intelligence_20260822_010203.zip",
        {1},
        limits=replace(DEFAULT_LIMITS, max_csv_rows=2),
    )
    assert result.is_valid is False
    assert "PACKAGE_TOO_LARGE" in error_codes(result)

    with pytest.raises(PackageValidationError) as caught:
        validate_package(
            package,
            "ots_intelligence_20260822_010203.zip",
            {1},
            limits=replace(DEFAULT_LIMITS, max_member_bytes=20),
        )
    assert caught.value.code == "PACKAGE_TOO_LARGE"


def test_detects_changed_nvd_bytes_before_parsing() -> None:
    result = validate_package(
        build_package(mutate_files={"nvd_cves.csv": b"changed\r\n"}),
        "ots_intelligence_20260822_010203.zip",
        {1},
    )
    assert result.is_valid is False
    assert "PACKAGE_DIGEST_MISMATCH" in error_codes(result)


@pytest.mark.parametrize(
    "content",
    [
        b"\xef\xbb\xbfcve_id\r\n",
        b"status,cve_id\r\npublished,CVE-2026-0001\r\n",
        b"cve_id\nCVE-2026-0001\n",
        b"cve_id\r\nCVE-2026-\x000001\r\n",
    ],
)
def test_rejects_invalid_csv_encoding_header_newline_and_nul(content: bytes) -> None:
    result = validate_package(
        build_package(override_files={"nvd_cves.csv": content}),
        "ots_intelligence_20260822_010203.zip",
        {1},
    )
    assert result.is_valid is False
    assert "PACKAGE_CSV_INVALID" in error_codes(result)


def test_rejects_field_byte_limit() -> None:
    rows = base_rows()
    rows["nvd_cves.csv"][0]["description"] = "长" * 20
    result = validate_package(
        build_package(rows=rows),
        "ots_intelligence_20260822_010203.zip",
        {1},
        limits=replace(DEFAULT_LIMITS, max_field_bytes=16),
    )
    assert result.is_valid is False
    assert any(error.field == "description" for error in result.errors)


def test_rejects_unsupported_version() -> None:
    result = validate_package(
        build_package(format_version="2.0"),
        "ots_intelligence_20260822_010203.zip",
        {1},
    )
    assert result.is_valid is False
    assert "PACKAGE_VERSION_UNSUPPORTED" in error_codes(result)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("cvss_json", "{"),
        ("cwes_json", json_value({"cwe": "CWE-79"})),
        ("references_json", "null"),
        ("configurations_json", json_value({"nodes": []})),
        ("matched_ots_json", json_value({"ots_id": 1})),
    ],
)
def test_rejects_invalid_json_columns_with_physical_field_location(field: str, value: str) -> None:
    rows = base_rows()
    rows["nvd_cves.csv"][0][field] = value
    result = validate_package(
        build_package(rows=rows),
        "ots_intelligence_20260822_010203.zip",
        {1},
    )

    assert result.is_valid is False
    error = next(error for error in result.errors if error.field == field)
    assert error.error_code == "PACKAGE_CSV_INVALID"
    assert error.file_name == "nvd_cves.csv"
    assert error.row_number == 2


@pytest.mark.parametrize(
    ("matches", "expected_code"),
    [
        ([], "PACKAGE_REFERENCE_INVALID"),
        ([{"ots_id": 999, "match_method": "cpe", "match_evidence": "x", "confidence": 0.8}], "PACKAGE_SCOPE_INVALID"),
        ([{"ots_id": 1, "match_method": "", "match_evidence": "x", "confidence": 0.8}], "PACKAGE_CSV_INVALID"),
        ([{"ots_id": 1, "match_method": "cpe", "match_evidence": "x", "confidence": 1.2}], "PACKAGE_CSV_INVALID"),
    ],
)
def test_rejects_invalid_or_out_of_scope_candidate_matches(matches: list[dict], expected_code: str) -> None:
    rows = base_rows()
    rows["nvd_cves.csv"][0]["matched_ots_json"] = json_value(matches)
    result = validate_package(
        build_package(rows=rows),
        "ots_intelligence_20260822_010203.zip",
        {1},
    )

    assert result.is_valid is False
    assert expected_code in error_codes(result)
    assert any(
        error.file_name == "nvd_cves.csv"
        and error.row_number == 2
        and error.field == "matched_ots_json"
        for error in result.errors
    )
    assert result.file_stats["nvd_cves.csv"].new == 0
    assert result.file_stats["nvd_cves.csv"].error == 1


def test_rejects_scope_snapshot_ots_unknown_to_platform() -> None:
    result = validate_package(
        build_package(),
        "ots_intelligence_20260822_010203.zip",
        set(),
    )
    assert result.is_valid is False
    assert "PACKAGE_SCOPE_INVALID" in error_codes(result)
    assert any(error.file_name == "collector_scope.csv" and error.row_number == 2 for error in result.errors)


def test_classifies_duplicate_and_conflicting_cve_rows() -> None:
    duplicate_rows = base_rows()
    duplicate_rows["nvd_cves.csv"].append(dict(duplicate_rows["nvd_cves.csv"][0]))
    duplicate = validate_package(
        build_package(rows=duplicate_rows),
        "ots_intelligence_20260822_010203.zip",
        {1},
    )
    assert duplicate.is_valid is True
    assert duplicate.file_stats["nvd_cves.csv"].duplicate == 1

    conflict_rows = base_rows()
    conflict_rows["nvd_cves.csv"].append(
        {**conflict_rows["nvd_cves.csv"][0], "description": "冲突描述"}
    )
    conflict = validate_package(
        build_package(rows=conflict_rows),
        "ots_intelligence_20260822_010203.zip",
        {1},
    )
    assert conflict.is_valid is False
    assert conflict.file_stats["nvd_cves.csv"].conflict == 1
    assert "PACKAGE_CSV_INVALID" in error_codes(conflict)


def test_csv_schema_errors_include_physical_row_field_and_truncated_value() -> None:
    rows = base_rows()
    rows["nvd_cves.csv"][0]["published_at"] = "not-a-time"
    result = validate_package(
        build_package(rows=rows),
        "ots_intelligence_20260822_010203.zip",
        {1},
    )
    error = next(error for error in result.errors if error.field == "published_at")
    assert error.file_name == "nvd_cves.csv"
    assert error.row_number == 2
    assert error.error_code == "PACKAGE_CSV_INVALID"
    assert error.rejected_value == "not-a-time"


def test_error_output_is_bounded_and_download_contract_is_stable() -> None:
    rows = base_rows()
    rows["nvd_cves.csv"] = [
        {**nvd_row(f"CVE-2026-{index + 1:04d}"), "status": "X" * 400}
        for index in range(20)
    ]
    result = validate_package(
        build_package(rows=rows),
        "ots_intelligence_20260822_010203.zip",
        {1},
        limits=replace(DEFAULT_LIMITS, max_errors=5, max_error_value_chars=16),
    )
    assert len(result.errors) == 5
    assert result.total_error_count >= 20
    assert result.truncated_error_count == result.total_error_count - 5
    assert all(len(error.rejected_value or "") <= 16 for error in result.errors)

    content = errors_csv(result.errors)
    assert content.startswith(b"error_code,file_name,row_number,field,reason,rejected_value\r\n")
    parsed = list(csv.DictReader(StringIO(content.decode("utf-8"))))
    assert len(parsed) == 5


def test_ten_thousand_cves_validate_under_five_minutes_with_bounded_memory() -> None:
    rows = base_rows()
    rows["nvd_cves.csv"] = [nvd_row(f"CVE-2026-{index + 1:04d}") for index in range(10_000)]
    package = build_package(rows=rows)

    tracemalloc.start()
    started = time.perf_counter()
    try:
        result = validate_package(
            package,
            "ots_intelligence_20260822_010203.zip",
            {1},
        )
        duration = time.perf_counter() - started
        _, peak_memory = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()

    assert result.is_valid is True
    assert result.file_stats["nvd_cves.csv"].new == 10_000
    assert duration < 300
    assert peak_memory < 256 * 1024 * 1024
