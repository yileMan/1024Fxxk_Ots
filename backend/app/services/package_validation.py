from __future__ import annotations

import csv
import hashlib
import math
import re
import stat
from dataclasses import dataclass, field
from datetime import datetime
from io import BytesIO, StringIO
from pathlib import PurePosixPath
from zipfile import BadZipFile, ZipFile, ZipInfo


PACKAGE_NAME = re.compile(r"^ots_intelligence_\d{8}_\d{6}\.zip$")
CVE_ID = re.compile(r"^CVE-\d{4}-\d{4,}$")
CWE_ID = re.compile(r"^CWE-\d+$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
SUPPORTED_FORMAT_VERSIONS = {"1.0"}

CSV_FIELDS: dict[str, tuple[str, ...]] = {
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
    "vulnerabilities.csv": (
        "cve_id",
        "status",
        "published_at",
        "last_modified_at",
        "description",
        "source",
    ),
    "affected_ranges.csv": (
        "cve_id",
        "cpe",
        "version_start_including",
        "version_start_excluding",
        "version_end_including",
        "version_end_excluding",
    ),
    "cvss_scores.csv": (
        "cve_id",
        "source",
        "cvss_version",
        "base_score",
        "base_severity",
        "vector",
    ),
    "cwes.csv": ("cve_id", "cwe_id"),
    "references.csv": ("cve_id", "url", "tags"),
    "kev.csv": (
        "cve_id",
        "date_added",
        "due_date",
        "known_ransomware_campaign_use",
        "required_action",
    ),
    "lifecycle.csv": (
        "ots_id",
        "cycle",
        "release_date",
        "eol_date",
        "status",
        "source_url",
    ),
    "matches.csv": (
        "cve_id",
        "ots_id",
        "match_method",
        "match_evidence",
        "confidence",
    ),
}

DATA_FILES = tuple(name for name in CSV_FIELDS if name not in {"manifest.csv", "collector_scope.csv"})
FILE_KEYS: dict[str, tuple[str, ...]] = {
    "vulnerabilities.csv": ("cve_id",),
    "affected_ranges.csv": (
        "cve_id",
        "cpe",
        "version_start_including",
        "version_start_excluding",
        "version_end_including",
        "version_end_excluding",
    ),
    "cvss_scores.csv": ("cve_id", "source", "cvss_version"),
    "cwes.csv": ("cve_id", "cwe_id"),
    "references.csv": ("cve_id", "url"),
    "kev.csv": ("cve_id",),
    "lifecycle.csv": ("ots_id", "cycle"),
    "matches.csv": ("cve_id", "ots_id", "match_method"),
}


@dataclass(frozen=True)
class PackageLimits:
    max_upload_bytes: int = 50 * 1024 * 1024
    max_members: int = 10
    max_member_bytes: int = 50 * 1024 * 1024
    max_total_uncompressed_bytes: int = 200 * 1024 * 1024
    max_compression_ratio: float = 100.0
    max_csv_rows: int = 10_000
    max_field_bytes: int = 64 * 1024
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
    samples: list[dict[str, str]] = field(default_factory=list)


@dataclass(frozen=True)
class PackageSummary:
    total: int
    new: int
    update: int
    duplicate: int
    conflict: int
    error: int


@dataclass(frozen=True)
class PackageValidationResult:
    is_valid: bool
    batch_no: str | None
    format_version: str | None
    scope_export_id: str | None
    scope_count: int
    manifest: dict[str, object] | None
    scope_snapshot: list[dict[str, object]]
    scope_coverage: list[dict[str, object]]
    file_stats: dict[str, FileStats]
    summary: PackageSummary
    errors: list[ValidationIssue]
    total_error_count: int
    truncated_error_count: int
    classification_basis: str = "package_structure_v1"
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
            value = "".join(character for character in str(rejected_value) if character >= " " or character == "\t")
            value = value[: self._limits.max_error_value_chars]
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
            total_size = 0
            for info in infos:
                if _unsafe_member(info) or info.filename in names:
                    raise PackageValidationError("PACKAGE_ZIP_UNSAFE", "ZIP 包含不安全成员")
                names.add(info.filename)
                if info.file_size > limits.max_member_bytes:
                    raise PackageValidationError("PACKAGE_TOO_LARGE", "ZIP 成员超过大小限制")
                total_size += info.file_size
                if total_size > limits.max_total_uncompressed_bytes:
                    raise PackageValidationError("PACKAGE_TOO_LARGE", "ZIP 解压总大小超过限制")
                if info.file_size and (not info.compress_size or info.file_size / info.compress_size > limits.max_compression_ratio):
                    raise PackageValidationError("PACKAGE_TOO_LARGE", "ZIP 压缩比超过限制")
            expected = set(CSV_FIELDS)
            if names != expected:
                raise PackageValidationError("PACKAGE_STRUCTURE_INVALID", "ZIP 文件集合不符合契约")
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


def _decode_csv(
    file_name: str,
    content: bytes,
    limits: PackageLimits,
    issues: _IssueCollector,
) -> list[dict[str, str]]:
    if content.startswith(b"\xef\xbb\xbf") or b"\x00" in content:
        issues.add("PACKAGE_CSV_INVALID", file_name, "CSV 编码或内容不符合契约", field_name="header")
        return []
    if b"\n" in content.replace(b"\r\n", b"") or b"\r" in content.replace(b"\r\n", b""):
        issues.add("PACKAGE_CSV_INVALID", file_name, "CSV 必须使用 CRLF 换行", field_name="header")
        return []
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        issues.add("PACKAGE_CSV_INVALID", file_name, "CSV 必须使用 UTF-8", field_name="header")
        return []
    try:
        reader = csv.DictReader(StringIO(text, newline=""), strict=True)
        if tuple(reader.fieldnames or ()) != CSV_FIELDS[file_name]:
            issues.add("PACKAGE_CSV_INVALID", file_name, "CSV 表头不符合契约", field_name="header")
            return []
        rows: list[dict[str, str]] = []
        for row_number, row in enumerate(reader, start=2):
            if len(rows) >= limits.max_csv_rows:
                issues.add("PACKAGE_TOO_LARGE", file_name, "CSV 数据行数超过限制", row_number=row_number)
                break
            normalized = {key: value if value is not None else "" for key, value in row.items() if key is not None}
            extra = row.get(None)
            if extra:
                issues.add("PACKAGE_CSV_INVALID", file_name, "CSV 数据列数超过表头", row_number=row_number)
                continue
            row_invalid = False
            for field_name, value in normalized.items():
                if len(value.encode("utf-8")) > limits.max_field_bytes:
                    row_invalid = True
                    issues.add(
                        "PACKAGE_CSV_INVALID",
                        file_name,
                        "字段超过长度限制",
                        row_number=row_number,
                        field_name=field_name,
                        rejected_value=value,
                    )
            normalized["__row_number__"] = str(row_number)
            if row_invalid:
                normalized["__invalid__"] = "1"
            rows.append(normalized)
        return rows
    except csv.Error:
        issues.add("PACKAGE_CSV_INVALID", file_name, "CSV 转义或行结构无法解析")
        return []


def _parse_time(value: str, *, allow_empty: bool = False) -> bool:
    if not value:
        return allow_empty
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None


def _positive_identifier(value: str) -> int | None:
    if not value.isdigit() or int(value) <= 0:
        return None
    return int(value)


def _row_number(row: dict[str, str]) -> int:
    return int(row["__row_number__"])


def _validate_manifest(
    rows: list[dict[str, str]],
    contents: dict[str, bytes],
    issues: _IssueCollector,
) -> tuple[dict[str, str] | None, list[dict[str, str]], dict[str, dict[str, str]]]:
    package_rows = [row for row in rows if row["record_type"] == "package"]
    file_rows = [row for row in rows if row["record_type"] == "file"]
    scope_rows = [row for row in rows if row["record_type"] == "scope_result"]
    invalid_types = [row for row in rows if row["record_type"] not in {"package", "file", "scope_result"}]
    for row in invalid_types:
        issues.add(
            "PACKAGE_MANIFEST_INVALID",
            "manifest.csv",
            "未知 manifest 记录类型",
            row_number=_row_number(row),
            field_name="record_type",
            rejected_value=row["record_type"],
        )
    if len(package_rows) != 1:
        issues.add("PACKAGE_MANIFEST_INVALID", "manifest.csv", "package 记录必须且只能有一条", field_name="record_type")
        return None, scope_rows, {}
    package_row = package_rows[0]
    common_fields = (
        "format_version",
        "batch_no",
        "generated_at",
        "producer_version",
        "scope_export_id",
        "scope_sha256",
    )
    for row in rows:
        for field_name in common_fields:
            if row[field_name] != package_row[field_name]:
                issues.add(
                    "PACKAGE_MANIFEST_INVALID",
                    "manifest.csv",
                    "manifest 公共元数据不一致",
                    row_number=_row_number(row),
                    field_name=field_name,
                    rejected_value=row[field_name],
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
    if not package_row["batch_no"] or len(package_row["batch_no"].encode("utf-8")) > 100:
        issues.add("PACKAGE_MANIFEST_INVALID", "manifest.csv", "批次号无效", row_number=_row_number(package_row), field_name="batch_no")
    if not _parse_time(package_row["generated_at"]):
        issues.add("PACKAGE_MANIFEST_INVALID", "manifest.csv", "生成时间无效", row_number=_row_number(package_row), field_name="generated_at", rejected_value=package_row["generated_at"])
    if not SHA256.fullmatch(package_row["scope_sha256"]):
        issues.add("PACKAGE_MANIFEST_INVALID", "manifest.csv", "范围摘要格式无效", row_number=_row_number(package_row), field_name="scope_sha256")

    file_by_name: dict[str, dict[str, str]] = {}
    expected_files = set(CSV_FIELDS) - {"manifest.csv"}
    for row in file_rows:
        name = row["file_name"]
        if name in file_by_name:
            issues.add("PACKAGE_MANIFEST_INVALID", "manifest.csv", "文件摘要记录重复", row_number=_row_number(row), field_name="file_name", rejected_value=name)
        file_by_name[name] = row
    if set(file_by_name) != expected_files:
        issues.add("PACKAGE_MANIFEST_INVALID", "manifest.csv", "manifest 文件清单不完整", field_name="file_name")
    for name, row in file_by_name.items():
        if name not in contents:
            continue
        actual = hashlib.sha256(contents[name]).hexdigest()
        if row["file_sha256"] != actual:
            issues.add(
                "PACKAGE_DIGEST_MISMATCH",
                name,
                "文件 SHA-256 与 manifest 不一致",
                row_number=_row_number(row),
                field_name="file_sha256",
                rejected_value=row["file_sha256"],
            )
    return package_row, scope_rows, file_by_name


def _validate_scope(
    rows: list[dict[str, str]],
    manifest: dict[str, str],
    scope_rows: list[dict[str, str]],
    known_ots_ids: set[int],
    issues: _IssueCollector,
) -> tuple[set[int], list[dict[str, object]], list[dict[str, object]]]:
    scope_ids: set[int] = set()
    snapshot: list[dict[str, object]] = []
    for row in rows:
        row_number = _row_number(row)
        if row["scope_export_id"] != manifest["scope_export_id"]:
            issues.add("PACKAGE_SCOPE_INVALID", "collector_scope.csv", "范围导出 ID 与 manifest 不一致", row_number=row_number, field_name="scope_export_id", rejected_value=row["scope_export_id"])
        ots_id = _positive_identifier(row["ots_id"])
        if ots_id is None:
            issues.add("PACKAGE_SCOPE_INVALID", "collector_scope.csv", "OTS ID 无效", row_number=row_number, field_name="ots_id", rejected_value=row["ots_id"])
            continue
        if ots_id in scope_ids:
            issues.add("PACKAGE_SCOPE_INVALID", "collector_scope.csv", "OTS ID 在范围快照中重复", row_number=row_number, field_name="ots_id", rejected_value=ots_id)
            continue
        scope_ids.add(ots_id)
        if ots_id not in known_ots_ids:
            issues.add("PACKAGE_SCOPE_INVALID", "collector_scope.csv", "OTS 无法由管理平台识别", row_number=row_number, field_name="ots_id", rejected_value=ots_id)
        if not row["ots_name"] or not row["ots_version"] or not row["official_website"]:
            issues.add("PACKAGE_CSV_INVALID", "collector_scope.csv", "范围必填字段为空", row_number=row_number)
        if row["last_covered_time"] and not _parse_time(row["last_covered_time"]):
            issues.add("PACKAGE_CSV_INVALID", "collector_scope.csv", "覆盖时间无效", row_number=row_number, field_name="last_covered_time", rejected_value=row["last_covered_time"])
        snapshot.append(
            {
                "ots_id": ots_id,
                "ots_name": row["ots_name"],
                "ots_version": row["ots_version"],
                "official_website": row["official_website"],
                "last_covered_time": row["last_covered_time"] or None,
            }
        )

    coverage: list[dict[str, object]] = []
    seen_results: set[int] = set()
    for row in scope_rows:
        row_number = _row_number(row)
        ots_id = _positive_identifier(row["ots_id"])
        if ots_id is None or ots_id not in scope_ids:
            issues.add("PACKAGE_SCOPE_INVALID", "manifest.csv", "采集结果引用范围外 OTS", row_number=row_number, field_name="ots_id", rejected_value=row["ots_id"])
            continue
        if ots_id in seen_results:
            issues.add("PACKAGE_MANIFEST_INVALID", "manifest.csv", "逐 OTS 采集结果重复", row_number=row_number, field_name="ots_id", rejected_value=ots_id)
            continue
        seen_results.add(ots_id)
        status_value = row["collection_status"]
        if status_value not in {"succeeded", "failed", "not_run"}:
            issues.add("PACKAGE_MANIFEST_INVALID", "manifest.csv", "采集状态无效", row_number=row_number, field_name="collection_status", rejected_value=status_value)
        if status_value == "succeeded":
            if not _parse_time(row["covered_to"]):
                issues.add("PACKAGE_MANIFEST_INVALID", "manifest.csv", "成功采集必须提供覆盖截止时间", row_number=row_number, field_name="covered_to", rejected_value=row["covered_to"])
        elif row["covered_to"]:
            issues.add("PACKAGE_MANIFEST_INVALID", "manifest.csv", "失败或未执行不得推进覆盖时间", row_number=row_number, field_name="covered_to", rejected_value=row["covered_to"])
        if status_value in {"failed", "not_run"} and not row["error_message"]:
            issues.add("PACKAGE_MANIFEST_INVALID", "manifest.csv", "失败或未执行必须提供原因", row_number=row_number, field_name="error_message")
        coverage.append(
            {
                "ots_id": ots_id,
                "status": status_value,
                "covered_from": row["covered_from"] or None,
                "covered_to": row["covered_to"] or None,
                "error_message": row["error_message"] or None,
            }
        )
    if seen_results != scope_ids:
        issues.add("PACKAGE_MANIFEST_INVALID", "manifest.csv", "逐 OTS 采集结果与范围快照不完整对应", field_name="ots_id")
    return scope_ids, snapshot, coverage


def _validate_common_fields(
    file_name: str,
    row: dict[str, str],
    issues: _IssueCollector,
) -> bool:
    row_number = _row_number(row)
    valid = True

    def invalid(field_name: str, reason: str) -> None:
        nonlocal valid
        valid = False
        issues.add("PACKAGE_CSV_INVALID", file_name, reason, row_number=row_number, field_name=field_name, rejected_value=row[field_name])

    if "cve_id" in row and not CVE_ID.fullmatch(row["cve_id"]):
        invalid("cve_id", "CVE ID 格式无效")
    if "ots_id" in row and _positive_identifier(row["ots_id"]) is None:
        invalid("ots_id", "OTS ID 格式无效")
    if file_name == "vulnerabilities.csv":
        if row["status"] not in {"published", "modified", "rejected"}:
            invalid("status", "漏洞状态无效")
        for field_name in ("published_at", "last_modified_at"):
            if not _parse_time(row[field_name]):
                invalid(field_name, "时间字段无效")
        if not row["description"] or not row["source"]:
            invalid("description" if not row["description"] else "source", "必填字段为空")
    elif file_name == "affected_ranges.csv" and not row["cpe"]:
        invalid("cpe", "CPE 不能为空")
    elif file_name == "cvss_scores.csv":
        if row["cvss_version"] != "3.1":
            invalid("cvss_version", "仅接受 CVSS 3.1")
        try:
            score = float(row["base_score"])
        except ValueError:
            score = math.nan
        if not 0 <= score <= 10:
            invalid("base_score", "CVSS 分数无效")
        if row["base_severity"] not in {"NONE", "LOW", "MEDIUM", "HIGH", "CRITICAL"}:
            invalid("base_severity", "严重度无效")
        if not row["vector"].startswith("CVSS:3.1/"):
            invalid("vector", "CVSS 向量无效")
    elif file_name == "cwes.csv" and not CWE_ID.fullmatch(row["cwe_id"]):
        invalid("cwe_id", "CWE ID 格式无效")
    elif file_name == "references.csv" and not row["url"].startswith(("https://", "http://")):
        invalid("url", "参考链接无效")
    elif file_name == "kev.csv":
        for field_name in ("date_added", "due_date"):
            try:
                datetime.fromisoformat(row[field_name])
            except ValueError:
                invalid(field_name, "日期字段无效")
        if row["known_ransomware_campaign_use"] not in {"known", "unknown"}:
            invalid("known_ransomware_campaign_use", "勒索活动标记无效")
    elif file_name == "lifecycle.csv":
        if row["status"] not in {"active", "eol", "unknown"}:
            invalid("status", "生命周期状态无效")
    elif file_name == "matches.csv":
        if not row["match_method"] or not row["match_evidence"]:
            invalid("match_method" if not row["match_method"] else "match_evidence", "候选匹配依据不能为空")
        if row["confidence"]:
            try:
                confidence = float(row["confidence"])
            except ValueError:
                confidence = math.nan
            if not 0 <= confidence <= 1:
                invalid("confidence", "置信度无效")
    return valid


def _classify_rows(
    parsed: dict[str, list[dict[str, str]]],
    limits: PackageLimits,
    issues: _IssueCollector,
) -> tuple[dict[str, FileStats], dict[str, list[dict[str, str]]]]:
    stats = {name: FileStats() for name in DATA_FILES}
    accepted: dict[str, list[dict[str, str]]] = {name: [] for name in DATA_FILES}
    for file_name in DATA_FILES:
        seen: dict[tuple[str, ...], tuple[tuple[str, str], ...]] = {}
        for row in parsed[file_name]:
            file_stats = stats[file_name]
            file_stats.total += 1
            before = issues.total
            row_valid = row.get("__invalid__") != "1" and _validate_common_fields(file_name, row, issues)
            key = tuple(row[field_name] for field_name in FILE_KEYS[file_name])
            canonical = tuple(sorted((field_name, value) for field_name, value in row.items() if not field_name.startswith("__")))
            if key in seen:
                if seen[key] == canonical:
                    file_stats.duplicate += 1
                    continue
                file_stats.conflict += 1
                issues.add(
                    "PACKAGE_CSV_INVALID",
                    file_name,
                    "相同业务键对应不同内容",
                    row_number=_row_number(row),
                    field_name=FILE_KEYS[file_name][0],
                    rejected_value="|".join(key),
                )
                continue
            seen[key] = canonical
            if not row_valid or issues.total > before:
                file_stats.error += 1
                continue
            file_stats.new += 1
            accepted[file_name].append(row)
            if len(file_stats.samples) < limits.max_samples_per_file:
                file_stats.samples.append({key: value for key, value in row.items() if not key.startswith("__")})
    return stats, accepted


def _validate_references(
    accepted: dict[str, list[dict[str, str]]],
    scope_ids: set[int],
    stats: dict[str, FileStats],
    issues: _IssueCollector,
) -> None:
    def mark_error(file_name: str, row: dict[str, str]) -> None:
        file_stats = stats[file_name]
        file_stats.new = max(0, file_stats.new - 1)
        file_stats.error += 1
        sample = {key: value for key, value in row.items() if not key.startswith("__")}
        if sample in file_stats.samples:
            file_stats.samples.remove(sample)

    vulnerability_ids = {row["cve_id"] for row in accepted["vulnerabilities.csv"]}
    matched_cves: set[str] = set()
    for row in accepted["matches.csv"]:
        ots_id = int(row["ots_id"])
        if ots_id not in scope_ids:
            mark_error("matches.csv", row)
            issues.add("PACKAGE_SCOPE_INVALID", "matches.csv", "候选匹配引用范围外 OTS", row_number=_row_number(row), field_name="ots_id", rejected_value=ots_id)
        elif row["cve_id"] not in vulnerability_ids:
            mark_error("matches.csv", row)
            issues.add("PACKAGE_REFERENCE_INVALID", "matches.csv", "候选匹配引用不存在的 CVE", row_number=_row_number(row), field_name="cve_id", rejected_value=row["cve_id"])
        else:
            matched_cves.add(row["cve_id"])
    for row in accepted["vulnerabilities.csv"]:
        if row["cve_id"] not in matched_cves:
            mark_error("vulnerabilities.csv", row)
            issues.add("PACKAGE_REFERENCE_INVALID", "vulnerabilities.csv", "CVE 没有任何范围内 OTS 候选匹配", row_number=_row_number(row), field_name="cve_id", rejected_value=row["cve_id"])
    for file_name in ("affected_ranges.csv", "cvss_scores.csv", "cwes.csv", "references.csv", "kev.csv"):
        for row in accepted[file_name]:
            if row["cve_id"] not in matched_cves:
                mark_error(file_name, row)
                issues.add("PACKAGE_REFERENCE_INVALID", file_name, "记录引用不存在或无范围内匹配的 CVE", row_number=_row_number(row), field_name="cve_id", rejected_value=row["cve_id"])
    for row in accepted["lifecycle.csv"]:
        ots_id = int(row["ots_id"])
        if ots_id not in scope_ids:
            mark_error("lifecycle.csv", row)
            issues.add("PACKAGE_SCOPE_INVALID", "lifecycle.csv", "生命周期记录引用范围外 OTS", row_number=_row_number(row), field_name="ots_id", rejected_value=ots_id)


def _summary(stats: dict[str, FileStats]) -> PackageSummary:
    return PackageSummary(
        total=sum(item.total for item in stats.values()),
        new=sum(item.new for item in stats.values()),
        update=0,
        duplicate=sum(item.duplicate for item in stats.values()),
        conflict=sum(item.conflict for item in stats.values()),
        error=sum(item.error for item in stats.values()),
    )


def validate_package(
    package: bytes,
    file_name: str,
    known_ots_ids: set[int],
    *,
    limits: PackageLimits = DEFAULT_LIMITS,
) -> PackageValidationResult:
    if not PACKAGE_NAME.fullmatch(file_name):
        raise PackageValidationError("PACKAGE_TYPE_INVALID", "数据包文件名不符合契约")
    contents = _read_archive(package, limits)
    issues = _IssueCollector(limits)
    parsed = {
        name: _decode_csv(name, contents[name], limits, issues)
        for name in CSV_FIELDS
    }
    manifest, scope_rows, file_rows = _validate_manifest(parsed["manifest.csv"], contents, issues)
    empty_stats = {name: FileStats() for name in DATA_FILES}
    if manifest is None:
        summary = _summary(empty_stats)
        return PackageValidationResult(False, None, None, None, 0, None, [], [], empty_stats, summary, issues.items, issues.total, issues.total - len(issues.items))
    if any(error.error_code == "PACKAGE_DIGEST_MISMATCH" for error in issues.items):
        summary = _summary(empty_stats)
        return PackageValidationResult(False, manifest["batch_no"], manifest["format_version"], manifest["scope_export_id"], 0, None, [], [], empty_stats, summary, issues.items, issues.total, issues.total - len(issues.items))
    scope_ids, snapshot, coverage = _validate_scope(
        parsed["collector_scope.csv"], manifest, scope_rows, known_ots_ids, issues
    )
    actual_scope_sha = hashlib.sha256(contents["collector_scope.csv"]).hexdigest()
    if manifest["scope_sha256"] != actual_scope_sha:
        issues.add("PACKAGE_DIGEST_MISMATCH", "collector_scope.csv", "范围 SHA-256 与 manifest 不一致", field_name="scope_sha256", rejected_value=manifest["scope_sha256"])
    stats, accepted = _classify_rows(parsed, limits, issues)
    _validate_references(accepted, scope_ids, stats, issues)
    summary = _summary(stats)
    normalized_manifest: dict[str, object] = {
        "format_version": manifest["format_version"],
        "batch_no": manifest["batch_no"],
        "generated_at": manifest["generated_at"],
        "producer_version": manifest["producer_version"],
        "scope_export_id": manifest["scope_export_id"],
        "scope_sha256": manifest["scope_sha256"],
        "files": {name: row["file_sha256"] for name, row in file_rows.items()},
        "scope_snapshot": snapshot,
    }
    return PackageValidationResult(
        issues.total == 0,
        manifest["batch_no"],
        manifest["format_version"],
        manifest["scope_export_id"],
        len(scope_ids),
        normalized_manifest,
        snapshot,
        coverage,
        stats,
        summary,
        issues.items,
        issues.total,
        issues.total - len(issues.items),
    )


def errors_csv(errors: list[ValidationIssue]) -> bytes:
    output = StringIO(newline="")
    writer = csv.writer(output, lineterminator="\r\n")
    writer.writerow(("error_code", "file_name", "row_number", "field", "reason", "rejected_value"))
    for error in errors:
        writer.writerow(
            (
                error.error_code,
                error.file_name,
                error.row_number or "",
                error.field or "",
                error.reason,
                error.rejected_value or "",
            )
        )
    return output.getvalue().encode("utf-8")
