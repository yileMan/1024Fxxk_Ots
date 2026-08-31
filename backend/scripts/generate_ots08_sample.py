from __future__ import annotations

import hashlib
from pathlib import Path

from generate_ots07_samples import (
    MANIFEST_FIELDS,
    NVD_FIELDS,
    csv_content,
    write_package,
)


def affected(
    product: str,
    version: str | None,
    *,
    start_including: str | None = None,
    end_excluding: str | None = None,
) -> dict[str, object]:
    return {
        "part": "o" if product == "Linux" else "a",
        "vendor": product,
        "product": product,
        "version": version,
        "version_start_including": start_including,
        "version_start_excluding": None,
        "version_end_including": None,
        "version_end_excluding": end_excluding,
        "cpe": f"cpe:2.3:a:{product}:{product}:{version or '*'}:*:*:*:*:*:*:*",
        "match_criteria_id": f"00000000-0000-0000-0000-000000000{len(product):03d}",
        "vulnerable": True,
    }


def row(cve_id: str, description: str, affected_items: list[dict[str, object]], *, status: str = "Analyzed") -> dict[str, object]:
    return {
        "cve_id": cve_id,
        "source_identifier": "ots08-sample@example.test",
        "vuln_status": status,
        "published_at": "2026-08-30T00:00:00Z",
        "last_modified_at": "2026-08-31T00:00:00Z",
        "description": description,
        "affected_software_json": affected_items,
        "cvss_json": [],
        "cwes_json": [],
        "references_json": [{"url": f"https://example.test/{cve_id}"}],
        "configurations_json": [],
    }


def build_files() -> dict[str, bytes]:
    rows = [
        row("CVE-2026-0801", "OpenSSL 精确版本命中样例", [affected("OpenSSL", "1.0")]),
        row(
            "CVE-2026-0802",
            "Linux 左闭右开区间命中样例",
            [affected("Linux", "*", start_including="3.0", end_excluding="3.2")],
        ),
        row(
            "CVE-2026-0803",
            "zlib 范围外不命中样例",
            [affected("zlib", "*", start_including="1.0", end_excluding="1.2")],
        ),
        row("CVE-2026-0804", "Rejected 空受影响范围样例", [], status="Rejected"),
    ]
    nvd = csv_content(NVD_FIELDS, rows)
    common = {
        "format_version": "1.0",
        "batch_no": "NVD-20260831-OTS08",
        "generated_at": "2026-08-31T08:00:00Z",
        "producer_version": "ots08-sample-generator/1.0",
        "source_name": "nvd",
        "source_release": "ots08-deterministic-acceptance-sample",
        "window_start": "2026-08-30T00:00:00Z",
        "window_end": "2026-08-31T00:00:00Z",
    }
    manifest = csv_content(
        MANIFEST_FIELDS,
        [
            {"record_type": "package", **common},
            {
                "record_type": "file",
                **common,
                "file_name": "nvd_cves.csv",
                "file_sha256": hashlib.sha256(nvd).hexdigest(),
            },
        ],
    )
    return {"manifest.csv": manifest, "nvd_cves.csv": nvd}


def main() -> None:
    output_dir = Path(__file__).parents[2] / "doc" / "samples"
    target = output_dir / "ots_intelligence_20260831_080000.zip"
    write_package(target, build_files(), extract=True)
    print(f"{target.name} sha256={hashlib.sha256(target.read_bytes()).hexdigest()}")


if __name__ == "__main__":
    main()
