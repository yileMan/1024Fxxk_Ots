from __future__ import annotations

import csv
import json
from io import StringIO
from pathlib import Path
from zipfile import ZipFile

from app.services.package_validation import validate_package


SAMPLE = (
    Path(__file__).parents[2]
    / "doc"
    / "samples"
    / "ots_intelligence_20260831_080000.zip"
)


def test_ots08_sample_is_valid_and_covers_matching_acceptance_cases() -> None:
    result = validate_package(SAMPLE.read_bytes(), SAMPLE.name)

    assert result.is_valid is True
    assert result.summary.total == 4

    with ZipFile(SAMPLE) as archive:
        rows = list(
            csv.DictReader(
                StringIO(archive.read("nvd_cves.csv").decode("utf-8"), newline="")
            )
        )
    affected = {
        row["cve_id"]: json.loads(row["affected_software_json"])
        for row in rows
    }

    assert affected["CVE-2026-0801"][0]["product"] == "OpenSSL"
    assert affected["CVE-2026-0801"][0]["version"] == "1.0"
    assert affected["CVE-2026-0802"][0]["product"] == "Linux"
    assert affected["CVE-2026-0802"][0]["version_start_including"] == "3.0"
    assert affected["CVE-2026-0802"][0]["version_end_excluding"] == "3.2"
    assert affected["CVE-2026-0803"][0]["product"] == "zlib"
    assert affected["CVE-2026-0804"] == []
