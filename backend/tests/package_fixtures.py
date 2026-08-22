from __future__ import annotations

import csv
import hashlib
import json
from collections.abc import Callable
from io import BytesIO, StringIO
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo


CSV_FIELDS = {
    "manifest.csv": (
        "record_type",
        "format_version",
        "batch_no",
        "generated_at",
        "producer_version",
        "source_name",
        "source_release",
        "window_start",
        "window_end",
        "file_name",
        "file_sha256",
    ),
    "nvd_cves.csv": (
        "cve_id",
        "source_identifier",
        "vuln_status",
        "published_at",
        "last_modified_at",
        "description",
        "affected_software_json",
        "cvss_json",
        "cwes_json",
        "references_json",
        "configurations_json",
    ),
}


def json_value(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def csv_bytes(file_name: str, rows: list[dict[str, object]], *, lineterminator: str = "\r\n") -> bytes:
    output = StringIO(newline="")
    writer = csv.DictWriter(
        output,
        fieldnames=CSV_FIELDS[file_name],
        lineterminator=lineterminator,
    )
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode("utf-8")


def affected_software(
    *,
    part: str = "a",
    vendor: str = "openssl",
    product: str = "openssl",
    version: str | None = "3.0.0",
    version_start_including: str | None = None,
    version_start_excluding: str | None = None,
    version_end_including: str | None = None,
    version_end_excluding: str | None = None,
    vulnerable: bool = True,
) -> dict[str, object]:
    return {
        "part": part,
        "vendor": vendor,
        "product": product,
        "version": version,
        "version_start_including": version_start_including,
        "version_start_excluding": version_start_excluding,
        "version_end_including": version_end_including,
        "version_end_excluding": version_end_excluding,
        "cpe": f"cpe:2.3:{part}:{vendor}:{product}:{version or '*'}:*:*:*:*:*:*:*",
        "match_criteria_id": "11111111-1111-1111-1111-111111111111",
        "vulnerable": vulnerable,
    }


def nvd_row(cve_id: str = "CVE-2026-0001") -> dict[str, object]:
    return {
        "cve_id": cve_id,
        "source_identifier": "security@example.test",
        "vuln_status": "Analyzed",
        "published_at": "2026-08-01T00:00:00Z",
        "last_modified_at": "2026-08-02T00:00:00Z",
        "description": "测试漏洞",
        "affected_software_json": json_value([affected_software()]),
        "cvss_json": json_value(
            [
                {
                    "source": "nvd@nist.gov",
                    "type": "Primary",
                    "cvssData": {
                        "version": "3.1",
                        "baseScore": 7.5,
                        "baseSeverity": "HIGH",
                        "vectorString": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:N/A:N",
                    },
                }
            ]
        ),
        "cwes_json": json_value([{"source": "nvd@nist.gov", "values": ["CWE-79"]}]),
        "references_json": json_value(
            [{"url": f"https://example.test/{cve_id}", "tags": ["Vendor Advisory"]}]
        ),
        "configurations_json": json_value(
            [
                {
                    "nodes": [
                        {
                            "operator": "OR",
                            "cpeMatch": [
                                {
                                    "criteria": "cpe:2.3:a:openssl:openssl:3.0.0:*:*:*:*:*:*:*",
                                    "matchCriteriaId": "11111111-1111-1111-1111-111111111111",
                                    "vulnerable": True,
                                }
                            ],
                        }
                    ]
                }
            ]
        ),
    }


def base_rows() -> dict[str, list[dict[str, object]]]:
    return {"nvd_cves.csv": [nvd_row()]}


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
    source_release: str = "fkie-cad/nvd-json-data-feeds@2026-08-22",
    window_start: str = "2026-08-21T00:00:00Z",
    window_end: str = "2026-08-22T00:00:00Z",
) -> bytes:
    package_rows = rows or base_rows()
    files = {"nvd_cves.csv": csv_bytes("nvd_cves.csv", package_rows["nvd_cves.csv"])}
    files.update(override_files or {})
    common = {
        "format_version": format_version,
        "batch_no": batch_no,
        "generated_at": "2026-08-22T01:02:03Z",
        "producer_version": "collector-test/1.0",
        "source_name": "nvd",
        "source_release": source_release,
        "window_start": window_start,
        "window_end": window_end,
    }
    manifest_rows: list[dict[str, object]] = [
        {"record_type": "package", **common},
        {
            "record_type": "file",
            **common,
            "file_name": "nvd_cves.csv",
            "file_sha256": hashlib.sha256(files["nvd_cves.csv"]).hexdigest(),
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


def build_legacy_three_file_package() -> bytes:
    return build_package(extra_files={"collector_scope.csv": b"scope_export_id,ots_id\r\nlegacy,1\r\n"})


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
