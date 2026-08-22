from __future__ import annotations

import csv
import hashlib
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from io import StringIO

from sqlalchemy.orm import sessionmaker

from app.models.imports import ImportBatch
from app.models.ots import OtsComponent
from app.repositories.collector_scope import CollectorScopeRepository


CSV_FIELDS = (
    "scope_export_id",
    "ots_id",
    "ots_name",
    "ots_version",
    "official_website",
    "last_covered_time",
)
BATCH_PAGE_SIZE = 100


class CollectorScopeError(ValueError):
    code = "COLLECTOR_SCOPE_ERROR"


class CollectorScopeHistoryInvalidError(CollectorScopeError):
    code = "COLLECTOR_SCOPE_HISTORY_INVALID"


@dataclass(frozen=True)
class CollectorScopeItem:
    ots_id: int
    ots_name: str
    ots_version: str
    official_website: str
    last_covered_time: str | None
    is_initial_collection: bool


@dataclass(frozen=True)
class ComparisonBaseline:
    available: bool
    batch_no: str | None
    finished_at: str | None


@dataclass(frozen=True)
class ScopeChanges:
    added_ots_ids: list[int]
    removed_ots_ids: list[int]
    added_count: int
    removed_count: int


@dataclass(frozen=True)
class CollectorScopeSnapshot:
    scope_count: int
    items: list[CollectorScopeItem]
    comparison_baseline: ComparisonBaseline
    changes: ScopeChanges


@dataclass(frozen=True)
class CollectorScopeExport:
    content: bytes
    scope_export_id: str
    sha256: str


class CollectorScopeService:
    def __init__(self, session_factory: sessionmaker) -> None:
        self._session_factory = session_factory
        self._repository = CollectorScopeRepository()

    def preview(self) -> CollectorScopeSnapshot:
        with self._session_factory() as session:
            ots_items = self._repository.list_active_ots(session)
            return self._build_snapshot(session, ots_items)

    def export(self) -> CollectorScopeExport:
        snapshot = self.preview()
        export_id = str(uuid.uuid4())
        output = StringIO(newline="")
        writer = csv.writer(output, lineterminator="\r\n")
        writer.writerow(CSV_FIELDS)
        for item in snapshot.items:
            writer.writerow(
                (
                    export_id,
                    item.ots_id,
                    item.ots_name,
                    item.ots_version,
                    item.official_website,
                    item.last_covered_time or "",
                )
            )
        content = output.getvalue().encode("utf-8")
        return CollectorScopeExport(content, export_id, hashlib.sha256(content).hexdigest())

    def _build_snapshot(self, session, ots_items: list[OtsComponent]) -> CollectorScopeSnapshot:
        current_ids = {item.id for item in ots_items}
        coverage_by_ots: dict[int, str] = {}
        baseline: ComparisonBaseline | None = None
        baseline_ids: set[int] = set()
        offset = 0

        while True:
            batches = self._repository.list_succeeded_batches(
                session,
                offset=offset,
                limit=BATCH_PAGE_SIZE,
            )
            if not batches:
                break
            for batch in batches:
                snapshot_ids = self._parse_snapshot(batch)
                coverage = self._parse_coverage(batch)
                if baseline is None:
                    baseline_ids = snapshot_ids
                    baseline = ComparisonBaseline(
                        True,
                        batch.batch_no,
                        self._format_timestamp(batch.finished_at or batch.created_at, milliseconds=False),
                    )
                for ots_id, covered_to in coverage.items():
                    if ots_id in current_ids and ots_id not in coverage_by_ots:
                        coverage_by_ots[ots_id] = covered_to
                if baseline is not None and current_ids.issubset(coverage_by_ots):
                    break
            if baseline is not None and current_ids.issubset(coverage_by_ots):
                break
            if len(batches) < BATCH_PAGE_SIZE:
                break
            offset += len(batches)

        if baseline is None:
            baseline = ComparisonBaseline(False, None, None)
            added_ids: list[int] = []
            removed_ids: list[int] = []
        else:
            added_ids = sorted(current_ids - baseline_ids)
            removed_ids = sorted(baseline_ids - current_ids)

        items = [
            CollectorScopeItem(
                item.id,
                item.ots_name,
                item.ots_version,
                item.official_website,
                coverage_by_ots.get(item.id),
                item.id not in coverage_by_ots,
            )
            for item in ots_items
        ]
        return CollectorScopeSnapshot(
            len(items),
            items,
            baseline,
            ScopeChanges(added_ids, removed_ids, len(added_ids), len(removed_ids)),
        )

    def _parse_snapshot(self, batch: ImportBatch) -> set[int]:
        manifest = batch.manifest_json
        if not isinstance(manifest, dict):
            raise CollectorScopeHistoryInvalidError()
        raw_snapshot = manifest.get("scope_snapshot")
        if not isinstance(raw_snapshot, list):
            raise CollectorScopeHistoryInvalidError()
        result: set[int] = set()
        for raw in raw_snapshot:
            if not isinstance(raw, dict) or not self._is_identifier(raw.get("ots_id")):
                raise CollectorScopeHistoryInvalidError()
            ots_id = int(raw["ots_id"])
            if ots_id in result:
                raise CollectorScopeHistoryInvalidError()
            result.add(ots_id)
        return result

    def _parse_coverage(self, batch: ImportBatch) -> dict[int, str]:
        raw_coverage = batch.scope_coverage_json
        if not isinstance(raw_coverage, list):
            raise CollectorScopeHistoryInvalidError()
        result: dict[int, str] = {}
        seen: set[int] = set()
        for raw in raw_coverage:
            if not isinstance(raw, dict) or not self._is_identifier(raw.get("ots_id")):
                raise CollectorScopeHistoryInvalidError()
            ots_id = int(raw["ots_id"])
            if ots_id in seen:
                raise CollectorScopeHistoryInvalidError()
            seen.add(ots_id)
            status = raw.get("status")
            if status not in {"succeeded", "failed", "not_run"}:
                raise CollectorScopeHistoryInvalidError()
            if status == "succeeded":
                result[ots_id] = self._normalize_covered_to(raw.get("covered_to"))
        return result

    @staticmethod
    def _is_identifier(value: object) -> bool:
        return isinstance(value, int) and not isinstance(value, bool) and value > 0

    @classmethod
    def _normalize_covered_to(cls, value: object) -> str:
        if not isinstance(value, str):
            raise CollectorScopeHistoryInvalidError()
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as error:
            raise CollectorScopeHistoryInvalidError() from error
        if parsed.tzinfo is None:
            raise CollectorScopeHistoryInvalidError()
        return cls._format_timestamp(parsed, milliseconds=True)

    @staticmethod
    def _format_timestamp(value: datetime, *, milliseconds: bool) -> str:
        aware = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
        timespec = "milliseconds" if milliseconds else "seconds"
        return aware.isoformat(timespec=timespec).replace("+00:00", "Z")
