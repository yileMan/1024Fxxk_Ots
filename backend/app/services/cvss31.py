from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_CEILING
from typing import Mapping


CALCULATOR_VERSION = "ots-cvss31-1"
BASE_ORDER = ("AV", "AC", "PR", "UI", "S", "C", "I", "A")
ENVIRONMENTAL_ORDER = (
    "CR", "IR", "AR", "MAV", "MAC", "MPR", "MUI", "MS", "MC", "MI", "MA"
)
ALLOWED_VALUES = {
    "AV": frozenset({"N", "A", "L", "P"}),
    "AC": frozenset({"L", "H"}),
    "PR": frozenset({"N", "L", "H"}),
    "UI": frozenset({"N", "R"}),
    "S": frozenset({"U", "C"}),
    "C": frozenset({"N", "L", "H"}),
    "I": frozenset({"N", "L", "H"}),
    "A": frozenset({"N", "L", "H"}),
    "CR": frozenset({"X", "L", "M", "H"}),
    "IR": frozenset({"X", "L", "M", "H"}),
    "AR": frozenset({"X", "L", "M", "H"}),
    "MAV": frozenset({"X", "N", "A", "L", "P"}),
    "MAC": frozenset({"X", "L", "H"}),
    "MPR": frozenset({"X", "N", "L", "H"}),
    "MUI": frozenset({"X", "N", "R"}),
    "MS": frozenset({"X", "U", "C"}),
    "MC": frozenset({"X", "N", "L", "H"}),
    "MI": frozenset({"X", "N", "L", "H"}),
    "MA": frozenset({"X", "N", "L", "H"}),
}

D = Decimal
AV = {"N": D("0.85"), "A": D("0.62"), "L": D("0.55"), "P": D("0.2")}
AC = {"L": D("0.77"), "H": D("0.44")}
UI = {"N": D("0.85"), "R": D("0.62")}
IMPACT = {"N": D("0"), "L": D("0.22"), "H": D("0.56")}
REQUIREMENT = {"X": D("1"), "L": D("0.5"), "M": D("1"), "H": D("1.5")}
PR = {
    "U": {"N": D("0.85"), "L": D("0.62"), "H": D("0.27")},
    "C": {"N": D("0.85"), "L": D("0.68"), "H": D("0.5")},
}


class Cvss31Error(ValueError):
    def __init__(self, message: str, *, field: str = "cvss31_vector") -> None:
        super().__init__(message)
        self.field = field


@dataclass(frozen=True)
class EnvironmentalResult:
    score: float
    vector: str
    metrics: dict[str, str]
    calculator_version: str = CALCULATOR_VERSION


def parse_base_vector(vector: str) -> dict[str, str]:
    if not isinstance(vector, str) or not vector.startswith("CVSS:3.1/"):
        raise Cvss31Error("仅支持 CVSS v3.1 基础向量")
    parsed: dict[str, str] = {}
    for component in vector.split("/")[1:]:
        if component.count(":") != 1:
            raise Cvss31Error("CVSS v3.1 向量格式无效")
        name, value = component.split(":")
        if name not in BASE_ORDER or name in parsed:
            raise Cvss31Error("CVSS v3.1 向量包含未知或重复指标", field=name)
        if value not in ALLOWED_VALUES[name]:
            raise Cvss31Error("CVSS v3.1 基础指标值无效", field=name)
        parsed[name] = value
    missing = next((name for name in BASE_ORDER if name not in parsed), None)
    if missing is not None:
        raise Cvss31Error("CVSS v3.1 基础向量不完整", field=missing)
    return {name: parsed[name] for name in BASE_ORDER}


def normalize_environmental_metrics(metrics: Mapping[str, str]) -> dict[str, str]:
    values = {name: "X" for name in ENVIRONMENTAL_ORDER}
    for name, value in metrics.items():
        if name not in ENVIRONMENTAL_ORDER:
            raise Cvss31Error("不支持的环境指标", field=name)
        if not isinstance(value, str) or value not in ALLOWED_VALUES[name]:
            raise Cvss31Error("环境指标值无效", field=name)
        values[name] = value
    return values


def _modified(metrics: Mapping[str, str], base: Mapping[str, str], name: str) -> str:
    value = metrics[f"M{name}"]
    return base[name] if value == "X" else value


def _roundup(value: Decimal) -> Decimal:
    return value.quantize(D("0.1"), rounding=ROUND_CEILING)


def calculate_environmental(
    base_vector: str, metrics: Mapping[str, str]
) -> EnvironmentalResult:
    base = parse_base_vector(base_vector)
    normalized = normalize_environmental_metrics(metrics)
    scope = base["S"] if normalized["MS"] == "X" else normalized["MS"]
    confidentiality = IMPACT[_modified(normalized, base, "C")]
    integrity = IMPACT[_modified(normalized, base, "I")]
    availability = IMPACT[_modified(normalized, base, "A")]
    miss = min(
        D("1")
        - (D("1") - REQUIREMENT[normalized["CR"]] * confidentiality)
        * (D("1") - REQUIREMENT[normalized["IR"]] * integrity)
        * (D("1") - REQUIREMENT[normalized["AR"]] * availability),
        D("0.915"),
    )
    if scope == "U":
        modified_impact = D("6.42") * miss
    else:
        modified_impact = (
            D("7.52") * (miss - D("0.029"))
            - D("3.25") * (miss * D("0.9731") - D("0.02")) ** 13
        )
    if modified_impact <= 0:
        score = D("0.0")
    else:
        exploitability = (
            D("8.22")
            * AV[_modified(normalized, base, "AV")]
            * AC[_modified(normalized, base, "AC")]
            * PR[scope][_modified(normalized, base, "PR")]
            * UI[_modified(normalized, base, "UI")]
        )
        subtotal = modified_impact + exploitability
        if scope == "C":
            subtotal *= D("1.08")
        score = _roundup(_roundup(min(subtotal, D("10"))))
    canonical_base = "/".join(f"{name}:{base[name]}" for name in BASE_ORDER)
    canonical_environment = "/".join(
        f"{name}:{normalized[name]}" for name in ENVIRONMENTAL_ORDER
    )
    return EnvironmentalResult(
        score=float(score),
        vector=f"CVSS:3.1/{canonical_base}/{canonical_environment}",
        metrics=normalized,
    )
