from __future__ import annotations

from pydantic import BaseModel


class PackageValidationIssueResponse(BaseModel):
    error_code: str
    file_name: str
    row_number: int | None
    field: str | None
    reason: str
    rejected_value: str | None


class PackageFileStatsResponse(BaseModel):
    total: int
    new: int
    update: int
    duplicate: int
    conflict: int
    error: int
    samples: list[dict[str, str]]


class PackageSummaryResponse(BaseModel):
    total: int
    new: int
    update: int
    duplicate: int
    conflict: int
    error: int


class ImportPackageResponse(BaseModel):
    id: int
    batch_no: str
    format_version: str
    package_file_name: str
    package_sha256: str
    status: str
    scope_export_id: str | None
    scope_count: int
    classification_basis: str
    final_import_diff: bool
    can_import: bool
    summary: PackageSummaryResponse
    file_stats: dict[str, PackageFileStatsResponse]
    errors: list[PackageValidationIssueResponse]
    total_error_count: int
    truncated_error_count: int
    duplicate: bool
