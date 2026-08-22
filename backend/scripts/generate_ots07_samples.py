from __future__ import annotations

import argparse
import csv
import hashlib
import json
from copy import deepcopy
from io import BytesIO, StringIO
from pathlib import Path
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo


MANIFEST_FIELDS = (
    "record_type", "format_version", "batch_no", "generated_at", "producer_version",
    "source_name", "source_release", "window_start", "window_end", "file_name", "file_sha256",
)
NVD_FIELDS = (
    "cve_id", "source_identifier", "vuln_status", "published_at", "last_modified_at", "description",
    "affected_software_json", "cvss_json", "cwes_json", "references_json", "configurations_json",
)
JSON_FIELDS = {
    "affected_software_json", "cvss_json", "cwes_json", "references_json", "configurations_json"
}


def compact(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def csv_content(fields: tuple[str, ...], rows: list[dict[str, object]]) -> bytes:
    output = StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=fields, lineterminator="\r\n")
    writer.writeheader()
    for row in rows:
        encoded = {
            name: compact(value) if name in JSON_FIELDS and not isinstance(value, str) else value
            for name, value in row.items()
        }
        writer.writerow(encoded)
    return output.getvalue().encode("utf-8")


def cpe_parts(criteria: str) -> list[str]:
    parts: list[str] = []
    current: list[str] = []
    escaped = False
    for character in criteria:
        if character == ":" and not escaped:
            parts.append("".join(current))
            current = []
        else:
            current.append(character)
        escaped = character == "\\" and not escaped
        if character != "\\":
            escaped = False
    parts.append("".join(current))
    return parts


def get_value(item: dict[str, Any], camel: str, snake: str) -> Any:
    return item.get(camel, item.get(snake))


def iter_cpe_matches(value: object):
    if isinstance(value, list):
        for item in value:
            yield from iter_cpe_matches(item)
    elif isinstance(value, dict):
        for key, item in value.items():
            if key in {"cpeMatch", "cpe_match"} and isinstance(item, list):
                for match in item:
                    if isinstance(match, dict):
                        yield match
            else:
                yield from iter_cpe_matches(item)


def affected_from_configurations(configurations: list[object]) -> list[dict[str, object]]:
    affected: list[dict[str, object]] = []
    seen: set[str] = set()
    for match in iter_cpe_matches(configurations):
        criteria = str(match.get("criteria", match.get("cpe23Uri", "")))
        parts = cpe_parts(criteria)
        if len(parts) < 6 or parts[:2] != ["cpe", "2.3"]:
            continue
        version = parts[5]
        item = {
            "part": parts[2],
            "vendor": parts[3],
            "product": parts[4],
            "version": version if version not in {"", "-"} else None,
            "version_start_including": get_value(match, "versionStartIncluding", "version_start_including"),
            "version_start_excluding": get_value(match, "versionStartExcluding", "version_start_excluding"),
            "version_end_including": get_value(match, "versionEndIncluding", "version_end_including"),
            "version_end_excluding": get_value(match, "versionEndExcluding", "version_end_excluding"),
            "cpe": criteria,
            "match_criteria_id": str(match.get("matchCriteriaId", match.get("match_criteria_id", ""))),
            "vulnerable": bool(match.get("vulnerable", False)),
        }
        key = compact(item)
        if key not in seen:
            seen.add(key)
            affected.append(item)
    return affected


def parse_json_array(value: str) -> list[object]:
    if not value:
        return []
    parsed = json.loads(value)
    if isinstance(parsed, list):
        return parsed
    if isinstance(parsed, dict):
        return [parsed]
    return []


def convert_row(row: dict[str, str]) -> dict[str, object]:
    configurations = parse_json_array(row.get("configurations_json", "[]"))
    status = row.get("status", "")
    normalized_status = {
        "rejected": "Rejected", "modified": "Modified", "published": "Analyzed"
    }.get(status.lower(), status or "Awaiting Analysis")
    return {
        "cve_id": row["cve_id"].upper(),
        "source_identifier": "nvd@nist.gov",
        "vuln_status": normalized_status,
        "published_at": row["published_at"],
        "last_modified_at": row["last_modified_at"],
        "description": row.get("description", "") or "NVD 未提供描述",
        "affected_software_json": affected_from_configurations(configurations),
        "cvss_json": parse_json_array(row.get("cvss_json", "[]")),
        "cwes_json": parse_json_array(row.get("cwes_json", "[]")),
        "references_json": parse_json_array(row.get("references_json", "[]")),
        "configurations_json": configurations,
    }


def package_files(
    rows: list[dict[str, object]], batch_no: str, source_release: str
) -> dict[str, bytes]:
    nvd = csv_content(NVD_FIELDS, rows)
    common = {
        "format_version": "1.0",
        "batch_no": batch_no,
        "generated_at": "2026-08-22T12:00:00Z",
        "producer_version": "ots-sample-generator/1.0",
        "source_name": "nvd",
        "source_release": source_release,
        "window_start": "2026-08-21T00:00:00Z",
        "window_end": "2026-08-22T00:00:00Z",
    }
    manifest = csv_content(MANIFEST_FIELDS, [
        {"record_type": "package", **common},
        {"record_type": "file", **common, "file_name": "nvd_cves.csv", "file_sha256": hashlib.sha256(nvd).hexdigest()},
    ])
    return {"manifest.csv": manifest, "nvd_cves.csv": nvd}


def write_package(target: Path, files: dict[str, bytes], *, extract: bool = False) -> None:
    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        for name in sorted(files):
            info = ZipInfo(name, date_time=(2026, 8, 22, 12, 0, 0))
            info.compress_type = ZIP_DEFLATED
            info.external_attr = 0o100600 << 16
            archive.writestr(info, files[name])
    target.write_bytes(output.getvalue())
    if extract:
        directory = target.with_suffix("")
        directory.mkdir(exist_ok=True)
        for name, content in files.items():
            (directory / name).write_bytes(content)


def deterministic_filler(length: int) -> str:
    chunks: list[str] = []
    index = 0
    total = 0
    while total < length:
        chunks.append(hashlib.sha256(f"ots07-{index}".encode()).hexdigest())
        total += len(chunks[-1])
        index += 1
    return "".join(chunks)[:length]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.source.suffix.lower() == ".zip":
        with ZipFile(args.source) as archive:
            source_text = archive.read("nvd_cves.csv").decode("utf-8")
        rows = [convert_row(row) for row in csv.DictReader(StringIO(source_text, newline=""))]
    else:
        with args.source.open("r", encoding="utf-8", newline="") as source:
            rows = [convert_row(row) for row in csv.DictReader(source)]
    if not rows:
        raise SystemExit("source CSV contains no CVE rows")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    release = "fkie-cad/nvd-json-data-feeds@2026-08-22"

    minimal = next((row for row in rows if row["affected_software_json"]), rows[0])
    write_package(
        args.output_dir / "ots_intelligence_20260822_010203.zip",
        package_files([minimal], "NVD-20260822-MINIMAL", release),
        extract=True,
    )
    write_package(
        args.output_dir / "ots_intelligence_20260822_120000.zip",
        package_files(rows, "NVD-20260822-FULL", release),
        extract=True,
    )

    invalid = deepcopy(minimal)
    invalid["cvss_json"] = "{"
    write_package(
        args.output_dir / "ots_intelligence_20260822_120001.zip",
        package_files([invalid], "NVD-20260822-INVALID-JSON", release),
    )

    large = deepcopy(minimal)
    empty_encoded = compact([{"blob": ""}])
    large["configurations_json"] = [{"blob": deterministic_filler(1024 * 1024 - len(empty_encoded))}]
    assert len(compact(large["configurations_json"]).encode()) == 1024 * 1024
    write_package(
        args.output_dir / "ots_intelligence_20260822_120002.zip",
        package_files([large], "NVD-20260822-LARGE-FIELD", release),
    )


if __name__ == "__main__":
    main()
