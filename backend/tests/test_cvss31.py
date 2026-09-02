from __future__ import annotations

import pytest

from app.services.cvss31 import (
    CALCULATOR_VERSION,
    Cvss31Error,
    calculate_environmental,
    normalize_environmental_metrics,
    parse_base_vector,
)


BASE_VECTOR = "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H"
ALL_UNDEFINED = {
    "CR": "X",
    "IR": "X",
    "AR": "X",
    "MAV": "X",
    "MAC": "X",
    "MPR": "X",
    "MUI": "X",
    "MS": "X",
    "MC": "X",
    "MI": "X",
    "MA": "X",
}


def test_first_v31_vector_and_all_undefined_environment_are_deterministic() -> None:
    first = calculate_environmental(BASE_VECTOR, ALL_UNDEFINED)
    second = calculate_environmental(BASE_VECTOR, dict(reversed(list(ALL_UNDEFINED.items()))))

    assert first.score == second.score == 9.8
    assert first.vector == second.vector == (
        BASE_VECTOR
        + "/CR:X/IR:X/AR:X/MAV:X/MAC:X/MPR:X/MUI:X/MS:X/MC:X/MI:X/MA:X"
    )
    assert first.metrics == ALL_UNDEFINED
    assert first.calculator_version == CALCULATOR_VERSION == "ots-cvss31-1"


def test_modified_scope_and_privileges_required_use_environmental_weights() -> None:
    result = calculate_environmental(
        "CVSS:3.1/AV:N/AC:L/PR:H/UI:N/S:U/C:L/I:L/A:N",
        {"MS": "C", "MPR": "H", "CR": "H", "MC": "H"},
    )

    assert result.score == 9.1
    assert result.vector.endswith(
        "/CR:H/IR:X/AR:X/MAV:X/MAC:X/MPR:H/MUI:X/MS:C/MC:H/MI:X/MA:X"
    )


def test_zero_modified_impact_scores_zero() -> None:
    result = calculate_environmental(BASE_VECTOR, {"MC": "N", "MI": "N", "MA": "N"})
    assert result.score == 0.0


@pytest.mark.parametrize(
    "vector",
    [
        "CVSS:3.0/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H",
        "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H",
        "CVSS:3.1/AV:N/AV:A/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H",
        "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H/XX:Y",
    ],
)
def test_parser_rejects_other_versions_missing_duplicate_and_unknown_metrics(vector: str) -> None:
    with pytest.raises(Cvss31Error):
        parse_base_vector(vector)


@pytest.mark.parametrize(
    ("metrics", "field"),
    [
        ({"CR": "INVALID"}, "CR"),
        ({"E": "H"}, "E"),
        ({"VC": "H"}, "VC"),
        ({"cr": "H"}, "cr"),
    ],
)
def test_environmental_metrics_reject_invalid_temporal_v40_and_unknown_values(
    metrics: dict[str, str], field: str
) -> None:
    with pytest.raises(Cvss31Error) as error:
        normalize_environmental_metrics(metrics)
    assert error.value.field == field


def test_partial_metrics_are_normalized_to_the_full_closed_set() -> None:
    normalized = normalize_environmental_metrics({"CR": "H", "MAV": "A"})
    assert normalized == {**ALL_UNDEFINED, "CR": "H", "MAV": "A"}
