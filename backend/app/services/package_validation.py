from __future__ import annotations

import csv
import hashlib
import json
import re
import stat
from dataclasses import dataclass, field
from datetime import datetime, timezone
from io import BytesIO, StringIO
from pathlib import PurePosixPath
from typing import Any
from zipfile import BadZipFile, ZipFile, ZipInfo


PACKAGE_NAME = re.compile(r"^ots_intelligence_\d{8}_\d{6}\.zip$")
CVE_ID = re.compile(r"^CVE-\d{4}-\d{4,}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
SUPPORTED_FORMAT_VERSIONS = {"1.0"}

CSV_FIELDS: dict[str, tuple[str, ...]] = {
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
DATA_FILES = ("nvd_cves.csv",)
JSON_FIELDS = (
    "affected_software_json",
    "cvss_json",
    "cwes_json",
    "references_json",
    "configurations_json",
)
AFFECTED_FIELDS = {
    "part",
    "vendor",
    "product",
    "version",
    "version_start_including",
    "version_start_excluding",
    "version_end_including",
    "version_end_excluding",
    "cpe",
    "match_criteria_id",
    "vulnerable",
}
DEFAULT_MAX_FIELD_BYTES = 1024 * 1024
csv.field_size_limit(50 * 1024 * 1024)


def _reject_json_constant(value: str) -> object:
    raise ValueError(f"非标准 JSON 常量: {value}")


@dataclass(frozen=True)
class PackageLimits:
    max_upload_bytes: int = 50 * 1024 * 1024
    max_members: int = 2
    max_member_bytes: int = 50 * 1024 * 1024
    max_total_uncompressed_bytes: int = 200 * 1024 * 1024
    max_compression_ratio: float = 100.0
    max_csv_rows: int = 10_000
    max_field_bytes: int = DEFAULT_MAX_FIELD_BYTES
    max_errors: int = 1_000
    max_error_value_chars: int = 256
    max_samples_per_file: int = 5


DEFAULT_LIMITS = PackageLimits()


class PackageValidationError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ValidationIssue:
    error_code: str
    file_name: str
    row_number: int | None
    field: str | None
    reason: str
    rejected_value: str | None = None


@dataclass
class FileStats:
    total: int = 0
    new: int = 0
    update: int = 0
    duplicate: int = 0
    conflict: int = 0
    error: int = 0
    samples: list[dict[str, object]] = field(default_factory=list)


@dataclass(frozen=True)
class PackageSummary:
    total: int
    new: int
    update: int
    duplicate: int
    conflict: int
    error: int


@dataclass(frozen=True)
class ExistingVulnerability:
    content_sha256: str
    source_modified_at: datetime | None


@dataclass(frozen=True)
class VulnerabilityRecord:
    cve_id: str
    source_identifier: str
    vuln_status: str
    published_at: datetime
    last_modified_at: datetime
    description: str
    affected_software: list[dict[str, object]]
    cvss: list[object]
    cwes: list[object]
    references: list[object]
    configurations: list[object]
    content_sha256: str
    row_number: int


@dataclass(frozen=True)
class PackageValidationResult:
    is_valid: bool
    batch_no: str | None
    format_version: str | None
    source_name: str | None
    source_release: str | None
    window_start: datetime | None
    window_end: datetime | None
    manifest: dict[str, object] | None
    file_stats: dict[str, FileStats]
    summary: PackageSummary
    errors: list[ValidationIssue]
    total_error_count: int
    truncated_error_count: int
    records: list[VulnerabilityRecord] = field(default_factory=list)
    classification_basis: str = "vulnerability_current_facts_v1"
    final_import_diff: bool = False
    can_import: bool = False


class _IssueCollector:
    def __init__(self, limits: PackageLimits) -> None:
        self._limits = limits
        self.items: list[ValidationIssue] = []
        self.total = 0

    def add(
        self,
        code: str,
        file_name: str,
        reason: str,
        *,
        row_number: int | None = None,
        field_name: str | None = None,
        rejected_value: object | None = None,
    ) -> None:
        self.total += 1
        if len(self.items) >= self._limits.max_errors:
            return
        value = None
        if rejected_value is not None:
            value = "".join(
                character
                for character in str(rejected_value)
                if character >= " " or character == "\t"
            )[: self._limits.max_error_value_chars]
        self.items.append(
            ValidationIssue(code, file_name, row_number, field_name, reason, value)
        )


def _unsafe_member(info: ZipInfo) -> bool:
    name = info.filename
    if info.is_dir() or not name or "\\" in name or name.startswith("/"):
        return True
    if re.match(r"^[A-Za-z]:", name):
        return True
    path = PurePosixPath(name)
    if len(path.parts) != 1 or any(part in {".", "..", ""} for part in path.parts):
        return True
    mode = info.external_attr >> 16
    return bool(mode and not stat.S_ISREG(mode))


def _read_archive(package: bytes, limits: PackageLimits) -> dict[str, bytes]:
    if len(package) > limits.max_upload_bytes:
        raise PackageValidationError("PACKAGE_TOO_LARGE", "上传文件超过大小限制")
    try:
        with ZipFile(BytesIO(package)) as archive:
            infos = archive.infolist()
            names: set[str] = set()
            declared_total = 0
            for info in infos:
                if _unsafe_member(info) or info.filename in names:
                    raise PackageValidationError("PACKAGE_ZIP_UNSAFE", "ZIP 包含不安全成员")
                names.add(info.filename)
                if info.file_size > limits.max_member_bytes:
                    raise PackageValidationError("PACKAGE_TOO_LARGE", "ZIP 成员超过大小限制")
                declared_total += info.file_size
                if declared_total > limits.max_total_uncompressed_bytes:
                    raise PackageValidationError("PACKAGE_TOO_LARGE", "ZIP 解压总大小超过限制")
                if info.file_size and (
                    not info.compress_size
                    or info.file_size / info.compress_size > limits.max_compression_ratio
                ):
                    raise PackageValidationError("PACKAGE_TOO_LARGE", "ZIP 压缩比超过限制")
            if names != set(CSV_FIELDS):
                raise PackageValidationError(
                    "PACKAGE_STRUCTURE_INVALID", "ZIP 文件集合不符合两文件契约"
                )
            if len(infos) > limits.max_members:
                raise PackageValidationError("PACKAGE_TOO_LARGE", "ZIP 文件数量超过限制")
            contents: dict[str, bytes] = {}
            actual_total = 0
            for info in infos:
                with archive.open(info) as member:
                    content = member.read(limits.max_member_bytes + 1)
                if len(content) > limits.max_member_bytes:
                    raise PackageValidationError("PACKAGE_TOO_LARGE", "ZIP 成员实际大小超过限制")
                actual_total += len(content)
                if actual_total > limits.max_total_uncompressed_bytes:
                    raise PackageValidationError("PACKAGE_TOO_LARGE", "ZIP 实际解压总大小超过限制")
                contents[info.filename] = content
            return contents
    except BadZipFile as error:
        raise PackageValidationError("PACKAGE_STRUCTURE_INVALID", "文件不是有效 ZIP") from error


def _scan_csv_records(
    file_name: str, text: str, issues: _IssueCollector
) -> list[tuple[int, str]]:
    records: list[tuple[int, str]] = []
    start = 0
    start_line = 1
    physical_line = 1
    quoted = False
    index = 0
    while index < len(text):
        character = text[index]
        if character == '"':
            if quoted and index + 1 < len(text) and text[index + 1] == '"':
                index += 2
                continue
            quoted = not quoted
            index += 1
            continue
        if character == "\r":
            if index + 1 < len(text) and text[index + 1] == "\n":
                if quoted:
                    physical_line += 1
                    index += 2
                    continue
                records.append((start_line, text[start:index]))
                physical_line += 1
                start_line = physical_line
                index += 2
                start = index
                continue
            if quoted:
                physical_line += 1
                index += 1
                continue
            issues.add(
                "PACKAGE_CSV_INVALID",
                file_name,
                "CSV 记录必须使用 CRLF 换行",
                row_number=physical_line,
                field_name="header" if not records else None,
            )
            physical_line += 1
            index += 1
            continue
        if character == "\n":
            if quoted:
                physical_line += 1
                index += 1
                continue
            issues.add(
                "PACKAGE_CSV_INVALID",
                file_name,
                "CSV 记录必须使用 CRLF 换行",
                row_number=physical_line,
                field_name="header" if not records else None,
            )
            records.append((start_line, text[start:index]))
            physical_line += 1
            start_line = physical_line
            index += 1
            start = index
            continue
        index += 1
    if quoted:
        issues.add(
            "PACKAGE_CSV_INVALID",
            file_name,
            "CSV 引号未闭合",
            row_number=start_line,
        )
    if start < len(text):
        records.append((start_line, text[start:]))
    return records


def _parse_csv_record(record: str) -> list[str]:
    reader = csv.reader(StringIO(record, newline=""), strict=True)
    values = next(reader)
    if next(reader, None) is not None:
        raise csv.Error("record contains multiple rows")
    return [value.replace("\r\n", "\n").replace("\r", "\n") for value in values]


def _decode_csv(
    file_name: str,
    content: bytes,
    limits: PackageLimits,
    issues: _IssueCollector,
) -> list[dict[str, str]]:
    if content.startswith(b"\xef\xbb\xbf") or b"\x00" in content:
        issues.add(
            "PACKAGE_CSV_INVALID",
            file_name,
            "CSV 编码或内容不符合契约",
            field_name="header",
        )
        return []
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        issues.add("PACKAGE_CSV_INVALID", file_name, "CSV 必须使用 UTF-8", field_name="header")
        return []
    raw_records = _scan_csv_records(file_name, text, issues)
    if not raw_records:
        issues.add("PACKAGE_CSV_INVALID", file_name, "CSV 缺少表头", field_name="header")
        return []
    try:
        header = tuple(_parse_csv_record(raw_records[0][1]))
    except csv.Error:
        issues.add("PACKAGE_CSV_INVALID", file_name, "CSV 表头无法解析", field_name="header")
        return []
    if header != CSV_FIELDS[file_name]:
        issues.add("PACKAGE_CSV_INVALID", file_name, "CSV 表头不符合契约", field_name="header")
        return []
    rows: list[dict[str, str]] = []
    for start_line, raw_record in raw_records[1:]:
        if not raw_record:
            continue
        if len(rows) >= limits.max_csv_rows:
            issues.add(
                "PACKAGE_TOO_LARGE",
                file_name,
                "CSV 数据记录数超过限制",
                row_number=start_line,
            )
            break
        try:
            values = _parse_csv_record(raw_record)
        except csv.Error:
            issues.add(
                "PACKAGE_CSV_INVALID",
                file_name,
                "CSV 转义或记录结构无法解析",
                row_number=start_line,
            )
            continue
        if len(values) != len(header):
            issues.add(
                "PACKAGE_CSV_INVALID",
                file_name,
                "CSV 数据列数与表头不一致",
                row_number=start_line,
            )
            continue
        row = dict(zip(header, values, strict=True))
        invalid = False
        for field_name, value in row.items():
            if len(value.encode("utf-8")) > limits.max_field_bytes:
                invalid = True
                issues.add(
                    "PACKAGE_CSV_INVALID",
                    file_name,
                    "字段超过长度限制",
                    row_number=start_line,
                    field_name=field_name,
                    rejected_value=value,
                )
        row["__row_number__"] = str(start_line)
        if invalid:
            row["__invalid__"] = "1"
        rows.append(row)
    return rows


def _parse_time(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def _row_number(row: dict[str, str]) -> int:
    return int(row["__row_number__"])


def _validate_manifest(
    rows: list[dict[str, str]],
    contents: dict[str, bytes],
    issues: _IssueCollector,
) -> tuple[dict[str, object] | None, datetime | None, datetime | None]:
    package_rows = [row for row in rows if row.get("record_type") == "package"]
    file_rows = [row for row in rows if row.get("record_type") == "file"]
    if len(package_rows) != 1 or len(file_rows) != 1 or len(rows) != 2:
        issues.add(
            "PACKAGE_MANIFEST_INVALID",
            "manifest.csv",
            "manifest 必须恰好包含一条 package 和一条 file 记录",
            field_name="record_type",
        )
        return None, None, None
    package_row = package_rows[0]
    file_row = file_rows[0]
    common_fields = (
        "format_version",
        "batch_no",
        "generated_at",
        "producer_version",
        "source_name",
        "source_release",
        "window_start",
        "window_end",
    )
    for field_name in common_fields:
        if package_row[field_name] != file_row[field_name]:
            issues.add(
                "PACKAGE_MANIFEST_INVALID",
                "manifest.csv",
                "manifest 公共元数据不一致",
                row_number=_row_number(file_row),
                field_name=field_name,
                rejected_value=file_row[field_name],
            )
    if package_row["format_version"] not in SUPPORTED_FORMAT_VERSIONS:
        issues.add(
            "PACKAGE_VERSION_UNSUPPORTED",
            "manifest.csv",
            "数据包格式版本不受支持",
            row_number=_row_number(package_row),
            field_name="format_version",
            rejected_value=package_row["format_version"],
        )
    if not package_row["batch_no"] or len(package_row["batch_no"].encode()) > 100:
        issues.add("PACKAGE_MANIFEST_INVALID", "manifest.csv", "批次号无效", row_number=_row_number(package_row), field_name="batch_no")
    generated_at = _parse_time(package_row["generated_at"])
    window_start = _parse_time(package_row["window_start"])
    window_end = _parse_time(package_row["window_end"])
    if generated_at is None:
        issues.add("PACKAGE_MANIFEST_INVALID", "manifest.csv", "生成时间无效", row_number=_row_number(package_row), field_name="generated_at")
    if window_start is None or window_end is None or window_start > window_end:
        issues.add("PACKAGE_MANIFEST_INVALID", "manifest.csv", "来源时间窗口无效", row_number=_row_number(package_row), field_name="window_start")
    if not package_row["producer_version"]:
        issues.add("PACKAGE_MANIFEST_INVALID", "manifest.csv", "生产者版本不能为空", row_number=_row_number(package_row), field_name="producer_version")
    if package_row["source_name"].lower() != "nvd":
        issues.add("PACKAGE_MANIFEST_INVALID", "manifest.csv", "来源名称必须为 nvd", row_number=_row_number(package_row), field_name="source_name")
    if not package_row["source_release"]:
        issues.add("PACKAGE_MANIFEST_INVALID", "manifest.csv", "来源发布标识不能为空", row_number=_row_number(package_row), field_name="source_release")
    if package_row["file_name"] or package_row["file_sha256"]:
        issues.add("PACKAGE_MANIFEST_INVALID", "manifest.csv", "package 记录不得声明文件摘要", row_number=_row_number(package_row), field_name="file_name")
    if file_row["file_name"] != "nvd_cves.csv" or not SHA256.fullmatch(file_row["file_sha256"]):
        issues.add("PACKAGE_MANIFEST_INVALID", "manifest.csv", "file 记录必须声明 nvd_cves.csv 及 SHA-256", row_number=_row_number(file_row), field_name="file_name")
    elif hashlib.sha256(contents["nvd_cves.csv"]).hexdigest() != file_row["file_sha256"]:
        issues.add("PACKAGE_DIGEST_MISMATCH", "nvd_cves.csv", "文件 SHA-256 与 manifest 不一致", field_name="file_sha256", rejected_value=file_row["file_sha256"])
    normalized = {
        "format_version": package_row["format_version"],
        "batch_no": package_row["batch_no"],
        "generated_at": package_row["generated_at"],
        "producer_version": package_row["producer_version"],
        "source_name": package_row["source_name"].lower(),
        "source_release": package_row["source_release"],
        "window_start": package_row["window_start"],
        "window_end": package_row["window_end"],
        "files": {"nvd_cves.csv": file_row["file_sha256"]},
    }
    return normalized, window_start, window_end


def _json_array(
    row: dict[str, str], field_name: str, issues: _IssueCollector
) -> list[object] | None:
    try:
        value = json.loads(row[field_name], parse_constant=_reject_json_constant)
    except (TypeError, ValueError, json.JSONDecodeError):
        value = None
    if not isinstance(value, list):
        issues.add(
            "PACKAGE_CSV_INVALID",
            "nvd_cves.csv",
            "字段必须是标准 JSON 数组",
            row_number=_row_number(row),
            field_name=field_name,
            rejected_value=row[field_name],
        )
        return None
    return value


def _validate_affected(
    value: list[object], row: dict[str, str], issues: _IssueCollector
) -> list[dict[str, object]] | None:
    result: list[dict[str, object]] = []
    for item in value:
        valid = isinstance(item, dict) and set(item) == AFFECTED_FIELDS
        if valid:
            assert isinstance(item, dict)
            valid = (
                isinstance(item["part"], str)
                and bool(item["part"])
                and isinstance(item["vendor"], str)
                and bool(item["vendor"])
                and isinstance(item["product"], str)
                and bool(item["product"])
                and isinstance(item["vulnerable"], bool)
                and isinstance(item["cpe"], str)
                and item["cpe"].startswith("cpe:2.3:")
                and isinstance(item["match_criteria_id"], str)
            )
        if valid:
            string_or_null = (
                "version",
                "version_start_including",
                "version_start_excluding",
                "version_end_including",
                "version_end_excluding",
            )
            valid = all(item[name] is None or isinstance(item[name], str) for name in string_or_null)
            valid = valid and not (
                item["version_start_including"] is not None
                and item["version_start_excluding"] is not None
            )
            valid = valid and not (
                item["version_end_including"] is not None
                and item["version_end_excluding"] is not None
            )
        if not valid:
            issues.add(
                "PACKAGE_CSV_INVALID",
                "nvd_cves.csv",
                "受影响软件对象字段或版本边界无效",
                row_number=_row_number(row),
                field_name="affected_software_json",
                rejected_value=item,
            )
            return None
        result.append(item)
    return result


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _sorted_unordered(values: list[object]) -> list[object]:
    return sorted(values, key=_canonical_json)


def _normalized_hash_payload(row: dict[str, Any]) -> dict[str, object]:
    return {
        "cve_id": str(row["cve_id"]).upper(),
        "source_identifier": row["source_identifier"],
        "vuln_status": row["vuln_status"],
        "published_at": _parse_time(str(row["published_at"])).isoformat(),
        "last_modified_at": _parse_time(str(row["last_modified_at"])).isoformat(),
        "description": str(row["description"]).replace("\r\n", "\n").replace("\r", "\n"),
        "affected_software": _sorted_unordered(json.loads(row["affected_software_json"], parse_constant=_reject_json_constant)),
        "cvss": _sorted_unordered(json.loads(row["cvss_json"], parse_constant=_reject_json_constant)),
        "cwes": _sorted_unordered(json.loads(row["cwes_json"], parse_constant=_reject_json_constant)),
        "references": _sorted_unordered(json.loads(row["references_json"], parse_constant=_reject_json_constant)),
        "configurations": json.loads(row["configurations_json"], parse_constant=_reject_json_constant),
    }


def content_hash(row: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(_normalized_hash_payload(row)).encode("utf-8")).hexdigest()


def select_cvss31(scores: list[object]) -> tuple[float | None, str | None, str | None, str | None]:
    candidates: list[tuple[dict[str, object], dict[str, object]]] = []
    for item in scores:
        if not isinstance(item, dict):
            continue
        data = item.get("cvssData", item)
        if isinstance(data, dict) and str(data.get("version", "")) == "3.1":
            candidates.append((item, data))
    if not candidates:
        return None, None, None, None

    def rank(candidate: tuple[dict[str, object], dict[str, object]]) -> tuple[int, str, str]:
        item, data = candidate
        source = str(item.get("source", ""))
        primary = str(item.get("type", "")).lower() == "primary"
        if primary and source.lower() in {"nvd", "nvd@nist.gov"}:
            priority = 0
        elif primary:
            priority = 1
        else:
            priority = 2
        return priority, source, str(data.get("vectorString", data.get("vector", "")))

    selected, data = sorted(candidates, key=rank)[0]
    score = data.get("baseScore", data.get("base_score"))
    return (
        float(score) if isinstance(score, (int, float)) else None,
        str(data.get("baseSeverity", data.get("base_severity")))
        if data.get("baseSeverity", data.get("base_severity")) is not None
        else None,
        str(data.get("vectorString", data.get("vector")))
        if data.get("vectorString", data.get("vector")) is not None
        else None,
        str(selected["source"]) if selected.get("source") is not None else None,
    )


def _parse_vulnerability_row(
    row: dict[str, str], issues: _IssueCollector
) -> VulnerabilityRecord | None:
    before = issues.total
    cve_id = row["cve_id"].upper()
    if not CVE_ID.fullmatch(cve_id):
        issues.add("PACKAGE_CSV_INVALID", "nvd_cves.csv", "CVE ID 无效", row_number=_row_number(row), field_name="cve_id", rejected_value=row["cve_id"])
    for name in ("source_identifier", "vuln_status", "description"):
        if not row[name]:
            issues.add("PACKAGE_CSV_INVALID", "nvd_cves.csv", "必填字段不能为空", row_number=_row_number(row), field_name=name)
    published_at = _parse_time(row["published_at"])
    modified_at = _parse_time(row["last_modified_at"])
    if published_at is None:
        issues.add("PACKAGE_CSV_INVALID", "nvd_cves.csv", "发布时间无效", row_number=_row_number(row), field_name="published_at", rejected_value=row["published_at"])
    if modified_at is None:
        issues.add("PACKAGE_CSV_INVALID", "nvd_cves.csv", "最后修改时间无效", row_number=_row_number(row), field_name="last_modified_at", rejected_value=row["last_modified_at"])
    parsed = {name: _json_array(row, name, issues) for name in JSON_FIELDS}
    affected = None
    if parsed["affected_software_json"] is not None:
        affected = _validate_affected(parsed["affected_software_json"], row, issues)
    if row.get("__invalid__") == "1" or issues.total > before:
        return None
    assert published_at is not None and modified_at is not None and affected is not None
    return VulnerabilityRecord(
        cve_id=cve_id,
        source_identifier=row["source_identifier"],
        vuln_status=row["vuln_status"],
        published_at=published_at,
        last_modified_at=modified_at,
        description=row["description"],
        affected_software=affected,
        cvss=parsed["cvss_json"] or [],
        cwes=parsed["cwes_json"] or [],
        references=parsed["references_json"] or [],
        configurations=parsed["configurations_json"] or [],
        content_sha256=content_hash(row),
        row_number=_row_number(row),
    )


def _sample(record: VulnerabilityRecord) -> dict[str, object]:
    score, severity, _, _ = select_cvss31(record.cvss)
    return {
        "cve_id": record.cve_id,
        "vuln_status": record.vuln_status,
        "description": record.description[:200],
        "affected_software_json": record.affected_software[:3],
        "cvss31_score": score,
        "cvss31_severity": severity,
    }


def _classify(
    rows: list[dict[str, str]],
    existing: dict[str, ExistingVulnerability],
    limits: PackageLimits,
    issues: _IssueCollector,
) -> tuple[FileStats, list[VulnerabilityRecord]]:
    stats = FileStats()
    records: list[VulnerabilityRecord] = []
    seen: dict[str, VulnerabilityRecord] = {}
    for row in rows:
        stats.total += 1
        before = issues.total
        record = _parse_vulnerability_row(row, issues)
        if record is None or issues.total > before:
            stats.error += 1
            continue
        prior = seen.get(record.cve_id)
        if prior is not None:
            if prior.content_sha256 == record.content_sha256:
                stats.duplicate += 1
            else:
                stats.conflict += 1
                issues.add("PACKAGE_CVE_CONFLICT", "nvd_cves.csv", "包内相同 CVE 对应不同内容", row_number=record.row_number, field_name="cve_id", rejected_value=record.cve_id)
            continue
        seen[record.cve_id] = record
        records.append(record)
        current = existing.get(record.cve_id)
        if current is None:
            stats.new += 1
        elif current.content_sha256 == record.content_sha256:
            stats.duplicate += 1
        elif current.source_modified_at is not None and record.last_modified_at > _as_utc(current.source_modified_at):
            stats.update += 1
        else:
            stats.conflict += 1
            issues.add("PACKAGE_CVE_CONFLICT", "nvd_cves.csv", "来源修改时间未更新但内容不同", row_number=record.row_number, field_name="last_modified_at", rejected_value=record.last_modified_at.isoformat())
        if len(stats.samples) < limits.max_samples_per_file:
            stats.samples.append(_sample(record))
    return stats, records


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _summary(stats: dict[str, FileStats]) -> PackageSummary:
    return PackageSummary(
        total=sum(item.total for item in stats.values()),
        new=sum(item.new for item in stats.values()),
        update=sum(item.update for item in stats.values()),
        duplicate=sum(item.duplicate for item in stats.values()),
        conflict=sum(item.conflict for item in stats.values()),
        error=sum(item.error for item in stats.values()),
    )


def validate_package(
    package: bytes,
    file_name: str,
    *,
    existing: dict[str, ExistingVulnerability] | None = None,
    limits: PackageLimits = DEFAULT_LIMITS,
) -> PackageValidationResult:
    if not PACKAGE_NAME.fullmatch(file_name):
        raise PackageValidationError("PACKAGE_TYPE_INVALID", "数据包文件名不符合契约")
    contents = _read_archive(package, limits)
    issues = _IssueCollector(limits)
    parsed = {name: _decode_csv(name, contents[name], limits, issues) for name in CSV_FIELDS}
    manifest, window_start, window_end = _validate_manifest(parsed["manifest.csv"], contents, issues)
    stats, records = _classify(parsed["nvd_cves.csv"], existing or {}, limits, issues)
    file_stats = {"nvd_cves.csv": stats}
    summary = _summary(file_stats)
    is_valid = manifest is not None and issues.total == 0
    return PackageValidationResult(
        is_valid=is_valid,
        batch_no=str(manifest["batch_no"]) if manifest else None,
        format_version=str(manifest["format_version"]) if manifest else None,
        source_name=str(manifest["source_name"]) if manifest else None,
        source_release=str(manifest["source_release"]) if manifest else None,
        window_start=window_start,
        window_end=window_end,
        manifest=manifest,
        file_stats=file_stats,
        summary=summary,
        errors=issues.items,
        total_error_count=issues.total,
        truncated_error_count=issues.total - len(issues.items),
        records=records,
        can_import=is_valid,
    )


def errors_csv(errors: list[ValidationIssue]) -> bytes:
    output = StringIO(newline="")
    writer = csv.writer(output, lineterminator="\r\n")
    writer.writerow(("error_code", "file_name", "row_number", "field", "reason", "rejected_value"))
    for error in errors:
        writer.writerow((error.error_code, error.file_name, error.row_number or "", error.field or "", error.reason, error.rejected_value or ""))
    return output.getvalue().encode("utf-8")
