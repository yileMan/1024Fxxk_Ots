from __future__ import annotations

import csv
import hashlib
import json
from io import StringIO
from pathlib import Path
from zipfile import ZipFile

from app.services.package_validation import select_cvss31, validate_package
from scripts.generate_ots07_samples import convert_row, package_files, write_package


SAMPLES = Path(__file__).parents[2] / "doc" / "samples"


def zip_rows(path: Path) -> tuple[dict[str, bytes], list[dict[str, str]]]:
    with ZipFile(path) as archive:
        files = {name: archive.read(name) for name in archive.namelist()}
    csv.field_size_limit(2 * 1024 * 1024)
    return files, list(csv.DictReader(StringIO(files["nvd_cves.csv"].decode(), newline="")))


def test_committed_samples_cover_minimal_full_invalid_and_large_field(tmp_path: Path) -> None:
    minimal = SAMPLES / "ots_intelligence_20260822_010203.zip"
    full = SAMPLES / "ots_intelligence_20260822_120000.zip"
    invalid = SAMPLES / "ots_intelligence_20260822_120001.zip"
    large = SAMPLES / "ots_intelligence_20260822_120002.zip"

    assert validate_package(minimal.read_bytes(), minimal.name).is_valid is True
    full_result = validate_package(full.read_bytes(), full.name)
    assert full_result.is_valid is True
    assert full_result.summary.total == 1_215
    assert any(record.affected_software for record in full_result.records)
    assert any(not record.affected_software for record in full_result.records)
    assert any(record.vuln_status == "Rejected" for record in full_result.records)
    assert any(select_cvss31(record.cvss)[0] is not None for record in full_result.records)

    invalid_result = validate_package(invalid.read_bytes(), invalid.name)
    assert invalid_result.is_valid is False
    assert any(error.field == "cvss_json" for error in invalid_result.errors)

    large_result = validate_package(large.read_bytes(), large.name)
    assert large_result.is_valid is True
    large_files, large_rows = zip_rows(large)
    assert len(large_rows[0]["configurations_json"].encode()) == 1024 * 1024
    assert set(large_files) == {"manifest.csv", "nvd_cves.csv"}


def test_full_sample_ids_digest_and_bytes_are_reproducible(tmp_path: Path) -> None:
    legacy = SAMPLES / "ots_intelligence_20260822_000009.zip"
    with ZipFile(legacy) as archive:
        old_text = archive.read("nvd_cves.csv").decode()
    source_rows = list(csv.DictReader(StringIO(old_text, newline="")))
    converted = [convert_row(row) for row in source_rows]
    expected_files = package_files(
        converted,
        "NVD-20260822-FULL",
        "fkie-cad/nvd-json-data-feeds@2026-08-22",
    )
    regenerated = tmp_path / "regenerated.zip"
    write_package(regenerated, expected_files)
    committed = SAMPLES / "ots_intelligence_20260822_120000.zip"
    assert regenerated.read_bytes() == committed.read_bytes()

    files, rows = zip_rows(committed)
    assert [row["cve_id"] for row in rows] == [row["cve_id"] for row in source_rows]
    manifest = list(csv.DictReader(StringIO(files["manifest.csv"].decode(), newline="")))
    file_row = next(row for row in manifest if row["record_type"] == "file")
    assert file_row["file_sha256"] == hashlib.sha256(files["nvd_cves.csv"]).hexdigest()
    assert any(
        any(item.get("version_start_including") or item.get("version_end_excluding") for item in json.loads(row["affected_software_json"]))
        for row in rows
    )
