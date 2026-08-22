from __future__ import annotations

import csv
import hashlib
import json
from collections.abc import Callable
from io import BytesIO, StringIO
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo


CSV_FIELDS = {
    "collector_scope.csv": (
        "scope_export_id",
        "ots_id",
        "ots_name",
        "ots_version",
        "official_website",
        "last_covered_time",
    ),
    "manifest.csv": (
        "record_type",
        "format_version",
        "batch_no",
        "generated_at",
        "producer_version",
        "scope_export_id",
        "scope_sha256",
        "file_name",
        "file_sha256",
        "ots_id",
        "collection_status",
        "covered_from",
        "covered_to",
        "error_message",
    ),
    "nvd_cves.csv": (
        "cve_id",
        "status",
        "published_at",
        "last_modified_at",
        "description",
        "cvss_json",
        "cwes_json",
        "references_json",
        "configurations_json",
        "matched_ots_json",
    ),
}

SCOPE_EXPORT_ID = "2ef57421-4978-47b2-897c-3b8dfe7e1ea0"


def json_value(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def csv_bytes(file_name: str, rows: list[dict[str, object]]) -> bytes:
    output = StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=CSV_FIELDS[file_name], lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode("utf-8")


def nvd_row(cve_id: str = "CVE-2026-0001", *, ots_id: int = 1) -> dict[str, object]:
    return {
        "cve_id": cve_id,
        "status": "published",
        "published_at": "2026-08-01T00:00:00Z",
        "last_modified_at": "2026-08-02T00:00:00Z",
        "description": "测试漏洞",
        "cvss_json": json_value(
            [
                {
                    "source": "nvd",
                    "version": "3.1",
                    "base_score": 7.5,
                    "base_severity": "HIGH",
                    "vector": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:N/A:N",
                }
            ]
        ),
        "cwes_json": json_value(["CWE-79"]),
        "references_json": json_value(
            [{"url": f"https://example.test/{cve_id}", "tags": ["advisory"]}]
        ),
        "configurations_json": json_value(
            [
                {
                    "nodes": [
                        {
                            "operator": "OR",
                            "cpe_match": [
                                {
                                    "criteria": "cpe:2.3:a:openssl:openssl:*:*:*:*:*:*:*:*",
                                    "vulnerable": True,
                                }
                            ],
                        }
                    ]
                }
            ]
        ),
        "matched_ots_json": json_value(
            [
                {
                    "ots_id": ots_id,
                    "match_method": "cpe",
                    "match_evidence": "vendor/product/version",
                    "confidence": 0.95,
                }
            ]
        ),
    }


def base_rows() -> dict[str, list[dict[str, object]]]:
    return {
        "collector_scope.csv": [
            {
                "scope_export_id": SCOPE_EXPORT_ID,
                "ots_id": 1,
                "ots_name": "OpenSSL",
                "ots_version": "3.0.0",
                "official_website": "https://openssl.org",
                "last_covered_time": "2026-08-01T00:00:00.000Z",
            }
        ],
        "nvd_cves.csv": [nvd_row()],
    }


def build_package(
    *,
    rows: dict[str, list[dict[str, object]]] | None = None,
    batch_no: str = "BATCH-20260822-001",
    format_version: str = "1.0",
    override_files: dict[str, bytes] | None = None,
    mutate_files: dict[str, bytes] | None = None,
    omit_files: set[str] | None = None,
    extra_files: dict[str, bytes] | None = None,
    manifest_mutator: Callable[[list[dict[str, object]]], None] | None = None,
) -> bytes:
    package_rows = rows or base_rows()
    files = {
        name: csv_bytes(name, package_rows.get(name, []))
        for name in CSV_FIELDS
        if name != "manifest.csv"
    }
    files.update(override_files or {})
    scope_sha256 = hashlib.sha256(files["collector_scope.csv"]).hexdigest()
    common = {
        "format_version": format_version,
        "batch_no": batch_no,
        "generated_at": "2026-08-22T01:02:03Z",
        "producer_version": "collector-test/1.0",
        "scope_export_id": SCOPE_EXPORT_ID,
        "scope_sha256": scope_sha256,
    }
    manifest_rows: list[dict[str, object]] = [
        {"record_type": "package", **common},
        *[
            {
                "record_type": "file",
                **common,
                "file_name": name,
                "file_sha256": hashlib.sha256(content).hexdigest(),
            }
            for name, content in sorted(files.items())
        ],
        {
            "record_type": "scope_result",
            **common,
            "ots_id": 1,
            "collection_status": "succeeded",
            "covered_from": "2026-08-01T00:00:00Z",
            "covered_to": "2026-08-22T00:00:00Z",
        },
    ]
    if manifest_mutator is not None:
        manifest_mutator(manifest_rows)
    files["manifest.csv"] = csv_bytes("manifest.csv", manifest_rows)
    files.update(mutate_files or {})
    for name in omit_files or set():
        files.pop(name, None)
    files.update(extra_files or {})

    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        for name, content in sorted(files.items()):
            info = ZipInfo(name, date_time=(2026, 8, 22, 1, 2, 2))
            info.compress_type = ZIP_DEFLATED
            info.external_attr = 0o100600 << 16
            archive.writestr(info, content)
    return output.getvalue()


def build_zip_with_member(name: str, content: bytes = b"unsafe") -> bytes:
    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        info = ZipInfo(name, date_time=(2026, 8, 22, 1, 2, 2))
        info.compress_type = ZIP_DEFLATED
        info.external_attr = 0o100600 << 16
        archive.writestr(info, content)
    return output.getvalue()


def build_zip_with_duplicate_member() -> bytes:
    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        for content in (b"one", b"two"):
            info = ZipInfo("manifest.csv", date_time=(2026, 8, 22, 1, 2, 2))
            info.compress_type = ZIP_DEFLATED
            info.external_attr = 0o100600 << 16
            archive.writestr(info, content)
    return output.getvalue()


def build_zip_with_symlink() -> bytes:
    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        info = ZipInfo("manifest.csv", date_time=(2026, 8, 22, 1, 2, 2))
        info.create_system = 3
        info.compress_type = ZIP_DEFLATED
        info.external_attr = 0o120777 << 16
        archive.writestr(info, b"../outside")
    return output.getvalue()
