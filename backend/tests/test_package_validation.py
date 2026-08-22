from __future__ import annotations

import csv
from dataclasses import replace
from io import StringIO

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
)


def error_codes(result) -> set[str]:
    return {error.error_code for error in result.errors}


def test_fixture_is_deterministic_and_validates_complete_contract() -> None:
    first = build_package()
    second = build_package()

    assert first == second
    result = validate_package(first, "ots_intelligence_20260822_010203.zip", {1})

    assert result.is_valid is True
    assert result.batch_no == "BATCH-20260822-001"
    assert result.format_version == "1.0"
    assert result.scope_count == 1
    assert result.classification_basis == "package_structure_v1"
    assert result.final_import_diff is False
    assert result.can_import is False
    assert set(result.file_stats) == set(CSV_FIELDS) - {"manifest.csv", "collector_scope.csv"}
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
            build_package(omit_files={"kev.csv"}),
            "PACKAGE_STRUCTURE_INVALID",
        ),
        (
            "ots_intelligence_20260822_010203.zip",
            build_package(extra_files={"unknown.csv": b"x\r\n"}),
            "PACKAGE_STRUCTURE_INVALID",
        ),
    ],
)
def test_rejects_invalid_name_archive_and_file_set(file_name: str, package: bytes, expected_code: str) -> None:
    with pytest.raises(PackageValidationError) as caught:
        validate_package(package, file_name, {1})
    assert caught.value.code == expected_code


@pytest.mark.parametrize("unsafe_name", ["../manifest.csv", "/manifest.csv", "C:/manifest.csv", r"C:\manifest.csv", "nested/manifest.csv"])
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


def test_rejects_upload_and_member_resource_limits() -> None:
    package = build_package()
    with pytest.raises(PackageValidationError) as caught:
        validate_package(
            package,
            "ots_intelligence_20260822_010203.zip",
            {1},
            limits=replace(DEFAULT_LIMITS, max_upload_bytes=len(package) - 1),
        )
    assert caught.value.code == "PACKAGE_TOO_LARGE"

    many_rows = base_rows()
    many_rows["cwes.csv"] = [
        {"cve_id": "CVE-2026-0001", "cwe_id": f"CWE-{index}"}
        for index in range(3)
    ]
    result = validate_package(
        build_package(rows=many_rows),
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


@pytest.mark.parametrize(
    ("mutated", "expected_code"),
    [
        ({"cwes.csv": b"\xef\xbb\xbfcve_id,cwe_id\r\nCVE-2026-0001,CWE-79\r\n"}, "PACKAGE_DIGEST_MISMATCH"),
        ({"cwes.csv": b"cwe_id,cve_id\r\nCWE-79,CVE-2026-0001\r\n"}, "PACKAGE_DIGEST_MISMATCH"),
        ({"cwes.csv": b"cve_id,cwe_id\nCVE-2026-0001,CWE-79\n"}, "PACKAGE_DIGEST_MISMATCH"),
    ],
)
def test_detects_changed_csv_bytes_before_parsing(mutated: dict[str, bytes], expected_code: str) -> None:
    result = validate_package(
        build_package(mutate_files=mutated),
        "ots_intelligence_20260822_010203.zip",
        {1},
    )
    assert result.is_valid is False
    assert expected_code in error_codes(result)


@pytest.mark.parametrize(
    "content",
    [
        b"\xef\xbb\xbfcve_id,cwe_id\r\nCVE-2026-0001,CWE-79\r\n",
        b"cwe_id,cve_id\r\nCWE-79,CVE-2026-0001\r\n",
        b"cve_id,cwe_id\nCVE-2026-0001,CWE-79\n",
        b"cve_id,cwe_id\r\nCVE-2026-0001,\x00CWE-79\r\n",
    ],
)
def test_rejects_invalid_csv_encoding_header_newline_and_nul(content: bytes) -> None:
    result = validate_package(
        build_package(override_files={"cwes.csv": content}),
        "ots_intelligence_20260822_010203.zip",
        {1},
    )
    assert result.is_valid is False
    assert "PACKAGE_CSV_INVALID" in error_codes(result)


def test_rejects_field_byte_limit() -> None:
    rows = base_rows()
    rows["vulnerabilities.csv"][0]["description"] = "长" * 20
    result = validate_package(
        build_package(rows=rows),
        "ots_intelligence_20260822_010203.zip",
        {1},
        limits=replace(DEFAULT_LIMITS, max_field_bytes=16),
    )
    assert result.is_valid is False
    assert any(error.field == "description" for error in result.errors)


def test_rejects_unsupported_version_and_manifest_inconsistency() -> None:
    result = validate_package(
        build_package(format_version="2.0"),
        "ots_intelligence_20260822_010203.zip",
        {1},
    )
    assert result.is_valid is False
    assert "PACKAGE_VERSION_UNSUPPORTED" in error_codes(result)


@pytest.mark.parametrize(
    ("mutator", "expected_code", "field"),
    [
        (lambda rows: rows["matches.csv"][0].update(ots_id=999), "PACKAGE_SCOPE_INVALID", "ots_id"),
        (lambda rows: rows["matches.csv"].clear(), "PACKAGE_REFERENCE_INVALID", "cve_id"),
        (lambda rows: rows["references.csv"][0].update(cve_id="CVE-2026-9999"), "PACKAGE_REFERENCE_INVALID", "cve_id"),
        (lambda rows: rows["lifecycle.csv"].append({"ots_id": 999, "cycle": "1", "release_date": "", "eol_date": "", "status": "unknown", "source_url": ""}), "PACKAGE_SCOPE_INVALID", "ots_id"),
    ],
)
def test_rejects_scope_and_reference_violations(mutator, expected_code: str, field: str) -> None:
    rows = base_rows()
    mutator(rows)
    result = validate_package(
        build_package(rows=rows),
        "ots_intelligence_20260822_010203.zip",
        {1},
    )
    assert result.is_valid is False
    assert expected_code in error_codes(result)
    assert any(error.field == field and error.row_number is not None for error in result.errors)


def test_rejects_scope_snapshot_ots_unknown_to_platform() -> None:
    result = validate_package(
        build_package(),
        "ots_intelligence_20260822_010203.zip",
        set(),
    )
    assert result.is_valid is False
    assert "PACKAGE_SCOPE_INVALID" in error_codes(result)
    assert any(error.file_name == "collector_scope.csv" and error.row_number == 2 for error in result.errors)


def test_classifies_duplicate_and_conflicting_keys() -> None:
    duplicate_rows = base_rows()
    duplicate_rows["cwes.csv"].append(dict(duplicate_rows["cwes.csv"][0]))
    duplicate = validate_package(
        build_package(rows=duplicate_rows),
        "ots_intelligence_20260822_010203.zip",
        {1},
    )
    assert duplicate.is_valid is True
    assert duplicate.file_stats["cwes.csv"].duplicate == 1

    conflict_rows = base_rows()
    conflict_rows["vulnerabilities.csv"].append(
        {**conflict_rows["vulnerabilities.csv"][0], "description": "冲突描述"}
    )
    conflict = validate_package(
        build_package(rows=conflict_rows),
        "ots_intelligence_20260822_010203.zip",
        {1},
    )
    assert conflict.is_valid is False
    assert conflict.file_stats["vulnerabilities.csv"].conflict == 1
    assert "PACKAGE_CSV_INVALID" in error_codes(conflict)


def test_csv_schema_errors_include_physical_row_field_and_truncated_value() -> None:
    rows = base_rows()
    rows["vulnerabilities.csv"][0]["published_at"] = "not-a-time"
    result = validate_package(
        build_package(rows=rows),
        "ots_intelligence_20260822_010203.zip",
        {1},
    )
    error = next(error for error in result.errors if error.field == "published_at")
    assert error.file_name == "vulnerabilities.csv"
    assert error.row_number == 2
    assert error.error_code == "PACKAGE_CSV_INVALID"
    assert error.rejected_value == "not-a-time"


def test_error_output_is_bounded_and_download_contract_is_stable() -> None:
    rows = base_rows()
    rows["cwes.csv"] = [
        {"cve_id": f"CVE-2026-{index:04d}", "cwe_id": "X" * 400}
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
