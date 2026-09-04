from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
from typing import Mapping

from app.services.cvss31 import Cvss31Error, parse_base_vector


BASIS_SCHEMA_VERSION = "1.0"
DEFAULT_MAX_CHANGES = 50
DEFAULT_MAX_VALUE_CHARS = 500


@dataclass(frozen=True)
class AssessmentBasis:
    data: dict[str, object]
    sha256: str


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _canonical_value(value: object) -> object:
    if isinstance(value, Mapping):
        return {
            str(key): _canonical_value(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, list):
        items = [_canonical_value(item) for item in value]
        return sorted(items, key=_canonical_json)
    if isinstance(value, tuple):
        return _canonical_value(list(value))
    if isinstance(value, Decimal):
        return _decimal_text(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def _decimal_text(value: object) -> str | None:
    if value is None or value == "":
        return None
    try:
        decimal = Decimal(str(value))
    except (InvalidOperation, ValueError) as error:
        raise ValueError("invalid CVSS v3.1 score") from error
    text = format(decimal.normalize(), "f")
    return "0" if text == "-0" else text


def _canonical_vector(value: object) -> str | None:
    if value is None or value == "":
        return None
    vector = str(value).strip()
    try:
        parsed = parse_base_vector(vector)
    except Cvss31Error:
        return vector
    body = "/".join(f"{name}:{metric}" for name, metric in parsed.items())
    return f"CVSS:3.1/{body}"


def _read(source: object, name: str, default: object = None) -> object:
    if isinstance(source, Mapping):
        return source.get(name, default)
    return getattr(source, name, default)


def build_assessment_basis(
    *,
    source: object,
    candidate: object | None,
    product_ots_id: int,
    product_ots_status: str,
    kev_available: bool,
) -> AssessmentBasis:
    affected_ranges = _canonical_value(
        _read(source, "affected_ranges_json", []) or []
    )
    source_data: dict[str, object] = {
        "affected_ranges": affected_ranges,
        "cvss31_score": _decimal_text(_read(source, "cvss31_score")),
        "cvss31_vector": _canonical_vector(_read(source, "cvss31_vector")),
        "kev": {"available": False},
        "status": str(_read(source, "source_status", "")).strip().casefold(),
    }
    if kev_available:
        source_data["kev"] = {
            "available": True,
            "is_kev": bool(_read(source, "is_kev", False)),
            "date_added": _canonical_value(_read(source, "kev_date_added")),
            "due_date": _canonical_value(_read(source, "kev_due_date")),
            "required_action": _read(source, "kev_required_action"),
        }

    candidate_data: dict[str, object]
    if candidate is None:
        candidate_data = {"exists": False}
    else:
        candidate_data = {
            "exists": True,
            "match_evidence": _canonical_value(
                _read(candidate, "match_evidence_json", {}) or {}
            ),
            "match_method": str(_read(candidate, "match_method", "")).strip(),
        }

    data: dict[str, object] = {
        "candidate": candidate_data,
        "product_context": {
            "product_ots_id": int(product_ots_id),
            "status": str(product_ots_status).strip().casefold(),
        },
        "schema_version": BASIS_SCHEMA_VERSION,
        "source": source_data,
    }
    canonical = _canonical_json(data)
    return AssessmentBasis(
        data=data,
        sha256=hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
    )


def _format_time(value: datetime) -> str:
    aware = value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
    return aware.isoformat(timespec="seconds").replace("+00:00", "Z")


def _diff_fields(before: Mapping[str, object], after: Mapping[str, object]) -> list[tuple[str, object, object]]:
    changes: list[tuple[str, object, object]] = []
    for section in ("candidate", "product_context", "source"):
        old_section = before.get(section, {})
        new_section = after.get(section, {})
        old_mapping = old_section if isinstance(old_section, Mapping) else {}
        new_mapping = new_section if isinstance(new_section, Mapping) else {}
        for field in sorted(set(old_mapping) | set(new_mapping)):
            old_value = old_mapping.get(field)
            new_value = new_mapping.get(field)
            if field == "kev" and isinstance(old_value, Mapping) and isinstance(new_value, Mapping):
                for kev_field in sorted(set(old_value) | set(new_value)):
                    kev_before = old_value.get(kev_field)
                    kev_after = new_value.get(kev_field)
                    if kev_before != kev_after:
                        changes.append((f"{section}.{field}.{kev_field}", kev_before, kev_after))
            elif old_value != new_value:
                changes.append((f"{section}.{field}", old_value, new_value))
    return changes


def _display_value(value: object, max_chars: int) -> object:
    if isinstance(value, (dict, list)):
        rendered = _canonical_json(value)
        if len(rendered) > max_chars:
            return {
                "length": len(rendered),
                "preview": rendered[:max_chars],
                "sha256": hashlib.sha256(rendered.encode("utf-8")).hexdigest(),
                "truncated": True,
            }
    return value


def diff_assessment_basis(
    before: Mapping[str, object],
    after: Mapping[str, object],
    *,
    now: datetime,
    max_changes: int = DEFAULT_MAX_CHANGES,
    max_value_chars: int = DEFAULT_MAX_VALUE_CHARS,
) -> dict[str, object] | None:
    raw_changes = _diff_fields(before, after)
    if not raw_changes:
        return None
    visible = raw_changes[:max_changes]
    changes = [
        {
            "field": field,
            "before": _display_value(old, max_value_chars),
            "after": _display_value(new, max_value_chars),
        }
        for field, old, new in visible
    ]
    return {
        "trigger_type": "automatic_reassessment",
        "triggered_at": _format_time(now),
        "change_types": sorted({field.split(".", 1)[0] for field, _, _ in raw_changes}),
        "changes": changes,
        "truncated_count": max(0, len(raw_changes) - len(visible)),
    }


def merge_reassessment_changes(
    existing: Mapping[str, object] | None,
    incoming: Mapping[str, object] | None,
    *,
    max_changes: int = DEFAULT_MAX_CHANGES,
) -> dict[str, object] | None:
    if incoming is None:
        return dict(existing) if existing is not None else None
    by_field: dict[str, dict[str, object]] = {}
    if existing is not None:
        for raw in existing.get("changes", []):
            if isinstance(raw, Mapping) and isinstance(raw.get("field"), str):
                by_field[str(raw["field"])] = dict(raw)
    for raw in incoming.get("changes", []):
        if not isinstance(raw, Mapping) or not isinstance(raw.get("field"), str):
            continue
        field = str(raw["field"])
        before = by_field[field]["before"] if field in by_field else raw.get("before")
        after = raw.get("after")
        if before == after:
            by_field.pop(field, None)
        else:
            by_field[field] = {"field": field, "before": before, "after": after}
    if not by_field:
        return None
    ordered = [by_field[field] for field in sorted(by_field)]
    visible = ordered[:max_changes]
    previous_truncated = int(existing.get("truncated_count", 0)) if existing else 0
    incoming_truncated = int(incoming.get("truncated_count", 0))
    return {
        "trigger_type": "automatic_reassessment",
        "triggered_at": incoming.get("triggered_at") or (existing or {}).get("triggered_at"),
        "change_types": sorted({item["field"].split(".", 1)[0] for item in ordered}),
        "changes": visible,
        "truncated_count": max(0, len(ordered) - len(visible))
        + previous_truncated
        + incoming_truncated,
    }
