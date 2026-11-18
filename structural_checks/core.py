# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Limited Eurocode 3 checks for simply supported steel beams."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import json
import math
from pathlib import Path
from typing import Any

import yaml


class InputError(ValueError):
    """Raised when the beam input is invalid or outside the supported scope."""


def _positive_number(value: object, label: str, *, allow_zero: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InputError(f"{label} must be a number")
    try:
        number = float(value)
    except OverflowError as exc:
        raise InputError(f"{label} must be finite") from exc
    if not math.isfinite(number) or (number < 0 if allow_zero else number <= 0):
        condition = "non-negative" if allow_zero else "greater than zero"
        raise InputError(f"{label} must be finite and {condition}")
    return number


def _nonempty_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InputError(f"{label} must be a non-empty string")
    return value.strip()


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise InputError(f"{label} must be an integer")
    return value


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or not all(
        isinstance(key, str) for key in value
    ):
        raise InputError(f"{label} must be a mapping with string keys")
    return value


def _check_keys(
    value: Mapping[str, object],
    required: set[str],
    allowed: set[str],
    label: str,
) -> None:
    missing = required - value.keys()
    extra = value.keys() - allowed
    if missing:
        raise InputError(f"{label} is missing: {', '.join(sorted(missing))}")
    if extra:
        raise InputError(f"{label} has unknown fields: {', '.join(sorted(extra))}")


def _sequence(value: object, label: str) -> Sequence[object]:
    if (
        not isinstance(value, Sequence)
        or isinstance(value, (str, bytes, bytearray))
    ):
        raise InputError(f"{label} must be a list")
    return value


@dataclass(frozen=True)
class PointLoad:
    """A downward point load measured from the left support."""

    magnitude_kN: float
    position_m: float

    def __post_init__(self) -> None:
        _positive_number(self.magnitude_kN, "point load magnitude")
        _positive_number(self.position_m, "point load position")


@dataclass(frozen=True)
class LoadCase:
    """A load case with full-span UDL and point loads."""

    name: str
    udl_kN_per_m: float = 0.0
    point_loads: tuple[PointLoad, ...] = ()

    def __post_init__(self) -> None:
        _nonempty_text(self.name, "load case name")
        _positive_number(
            self.udl_kN_per_m, "UDL", allow_zero=True
        )
        if not isinstance(self.point_loads, tuple) or not all(
            isinstance(load, PointLoad) for load in self.point_loads
        ):
            raise InputError("point_loads must be a tuple of PointLoad values")
        if self.udl_kN_per_m == 0 and not self.point_loads:
            raise InputError(f"load case {self.name!r} has no loads")


@dataclass(frozen=True)
class Section:
    """Major-axis section properties supplied from a verified section source."""

    designation: str
    section_class: int
    i_y_mm4: float
    a_v_mm2: float
    w_pl_y_mm3: float | None = None
    w_el_y_mm3: float | None = None

    def __post_init__(self) -> None:
        _nonempty_text(self.designation, "section designation")
        if (
            isinstance(self.section_class, bool)
            or not isinstance(self.section_class, int)
            or self.section_class not in (1, 2, 3, 4)
        ):
            raise InputError("section_class must be an integer from 1 to 4")
        if self.section_class == 4:
            raise InputError(
                "Class 4 sections are not supported; effective properties "
                "require additional EN 1993-1-5 checks"
            )
        _positive_number(self.i_y_mm4, "i_y_mm4")
        _positive_number(self.a_v_mm2, "a_v_mm2")
        if self.section_class in (1, 2):
            if self.w_pl_y_mm3 is None:
                raise InputError("Class 1 and 2 sections require w_pl_y_mm3")
            _positive_number(self.w_pl_y_mm3, "w_pl_y_mm3")
        else:
            if self.w_el_y_mm3 is None:
                raise InputError("Class 3 sections require w_el_y_mm3")
            _positive_number(self.w_el_y_mm3, "w_el_y_mm3")


@dataclass(frozen=True)
class Combination:
    """An explicitly specified ULS or SLS load combination."""

    name: str
    limit_state: str
    factors: Mapping[str, float]
    deflection_limit_mm: float | None = None

    def __post_init__(self) -> None:
        _nonempty_text(self.name, "combination name")
        if self.limit_state not in ("ULS", "SLS"):
            raise InputError("combination limit_state must be ULS or SLS")
        if not isinstance(self.factors, Mapping) or not self.factors:
            raise InputError("combination factors must be a non-empty mapping")
        for case_name, factor in self.factors.items():
            _nonempty_text(case_name, "combination load-case name")
            _positive_number(factor, f"factor for {case_name}", allow_zero=True)
        if not any(self.factors.values()):
            raise InputError(f"combination {self.name!r} has all-zero factors")
        if self.limit_state == "SLS":
            if self.deflection_limit_mm is None:
                raise InputError(
                    f"SLS combination {self.name!r} requires "
                    "deflection_limit_mm from the project criteria"
                )
            _positive_number(
                self.deflection_limit_mm, "deflection_limit_mm"
            )
        elif self.deflection_limit_mm is not None:
            raise InputError(
                "deflection_limit_mm belongs only on an SLS combination"
            )


@dataclass(frozen=True)
class Beam:
    """Input data for a prismatic, simply supported beam."""

    member_id: str
    span_m: float
    fy_mpa: float
    gamma_m0: float
    e_mpa: float
    section: Section
    compression_flange_laterally_restrained: bool
    load_cases: tuple[LoadCase, ...]
    combinations: tuple[Combination, ...]

    def __post_init__(self) -> None:
        _nonempty_text(self.member_id, "member_id")
        _positive_number(self.span_m, "span_m")
        _positive_number(self.fy_mpa, "fy_mpa")
        _positive_number(self.gamma_m0, "gamma_m0")
        _positive_number(self.e_mpa, "e_mpa")
        if not isinstance(self.section, Section):
            raise InputError("section must be a Section")
        if not isinstance(self.compression_flange_laterally_restrained, bool):
            raise InputError(
                "compression_flange_laterally_restrained must be true or false"
            )
        if not isinstance(self.load_cases, tuple) or not self.load_cases or not all(
            isinstance(case, LoadCase) for case in self.load_cases
        ):
            raise InputError("load_cases must be a non-empty tuple of LoadCase values")
        if (
            not isinstance(self.combinations, tuple)
            or not self.combinations
            or not all(isinstance(item, Combination) for item in self.combinations)
        ):
            raise InputError(
                "combinations must be a non-empty tuple of Combination values"
            )
        case_names = [case.name for case in self.load_cases]
        if len(set(case_names)) != len(case_names):
            raise InputError("load case names must be unique")
        combo_names = [item.name for item in self.combinations]
        if len(set(combo_names)) != len(combo_names):
            raise InputError("combination names must be unique")
        if not any(item.limit_state == "ULS" for item in self.combinations):
            raise InputError("at least one ULS combination is required")
        if not any(item.limit_state == "SLS" for item in self.combinations):
            raise InputError("at least one SLS combination is required")
        known_cases = set(case_names)
        for combination in self.combinations:
            if set(combination.factors) != known_cases:
                raise InputError(
                    f"combination {combination.name!r} must specify a factor for "
                    "every load case (use 0 for excluded cases)"
                )
        for case in self.load_cases:
            for load in case.point_loads:
                if load.position_m >= self.span_m:
                    raise InputError(
                        f"point load in {case.name!r} must be strictly inside "
                        "the span"
                    )


def beam_from_mapping(data: object) -> Beam:
    """Validates and converts a YAML/JSON mapping into typed beam inputs."""
    root = _mapping(data, "input")
    _check_keys(
        root,
        {
            "member_id",
            "span_m",
            "fy_mpa",
            "gamma_m0",
            "e_mpa",
            "section",
            "compression_flange_laterally_restrained",
            "load_cases",
            "combinations",
        },
        {
            "member_id",
            "span_m",
            "fy_mpa",
            "gamma_m0",
            "e_mpa",
            "section",
            "compression_flange_laterally_restrained",
            "load_cases",
            "combinations",
        },
        "input",
    )

    section_data = _mapping(root["section"], "section")
    _check_keys(
        section_data,
        {"designation", "section_class", "i_y_mm4", "a_v_mm2"},
        {
            "designation",
            "section_class",
            "i_y_mm4",
            "a_v_mm2",
            "w_pl_y_mm3",
            "w_el_y_mm3",
        },
        "section",
    )
    section = Section(
        designation=_nonempty_text(section_data["designation"], "designation"),
        section_class=_integer(section_data["section_class"], "section_class"),
        i_y_mm4=_positive_number(section_data["i_y_mm4"], "i_y_mm4"),
        a_v_mm2=_positive_number(section_data["a_v_mm2"], "a_v_mm2"),
        w_pl_y_mm3=(
            None
            if "w_pl_y_mm3" not in section_data
            else _positive_number(section_data["w_pl_y_mm3"], "w_pl_y_mm3")
        ),
        w_el_y_mm3=(
            None
            if "w_el_y_mm3" not in section_data
            else _positive_number(section_data["w_el_y_mm3"], "w_el_y_mm3")
        ),
    )

    load_cases: list[LoadCase] = []
    for index, raw_case in enumerate(_sequence(root["load_cases"], "load_cases")):
        case_data = _mapping(raw_case, f"load_cases[{index}]")
        _check_keys(
            case_data,
            {"name"},
            {"name", "udl_kN_per_m", "point_loads"},
            f"load_cases[{index}]",
        )
        raw_points = _sequence(
            case_data.get("point_loads", []),
            f"load_cases[{index}].point_loads",
        )
        points: list[PointLoad] = []
        for point_index, raw_point in enumerate(raw_points):
            point_data = _mapping(
                raw_point, f"load_cases[{index}].point_loads[{point_index}]"
            )
            _check_keys(
                point_data,
                {"magnitude_kN", "position_m"},
                {"magnitude_kN", "position_m"},
                f"load_cases[{index}].point_loads[{point_index}]",
            )
            points.append(
                PointLoad(
                    magnitude_kN=_positive_number(
                        point_data["magnitude_kN"], "magnitude_kN"
                    ),
                    position_m=_positive_number(
                        point_data["position_m"], "position_m"
                    ),
                )
            )
        load_cases.append(
            LoadCase(
                name=_nonempty_text(case_data["name"], "load case name"),
                udl_kN_per_m=_positive_number(
                    case_data.get("udl_kN_per_m", 0.0),
                    "udl_kN_per_m",
                    allow_zero=True,
                ),
                point_loads=tuple(points),
            )
        )

    combinations: list[Combination] = []
    for index, raw_combination in enumerate(
        _sequence(root["combinations"], "combinations")
    ):
        combo_data = _mapping(raw_combination, f"combinations[{index}]")
        _check_keys(
            combo_data,
            {"name", "limit_state", "factors"},
            {"name", "limit_state", "factors", "deflection_limit_mm"},
            f"combinations[{index}]",
        )
        raw_factors = _mapping(combo_data["factors"], "combination factors")
        combinations.append(
            Combination(
                name=_nonempty_text(combo_data["name"], "combination name"),
                limit_state=_nonempty_text(
                    combo_data["limit_state"], "limit_state"
                ),
                factors={
                    key: _positive_number(value, f"factor for {key}", allow_zero=True)
                    for key, value in raw_factors.items()
                },
                deflection_limit_mm=(
                    None
                    if "deflection_limit_mm" not in combo_data
                    else _positive_number(
                        combo_data["deflection_limit_mm"],
                        "deflection_limit_mm",
                    )
                ),
            )
        )

    lateral_restraint = root["compression_flange_laterally_restrained"]
    if not isinstance(lateral_restraint, bool):
        raise InputError(
            "compression_flange_laterally_restrained must be true or false"
        )

    return Beam(
        member_id=_nonempty_text(root["member_id"], "member_id"),
        span_m=_positive_number(root["span_m"], "span_m"),
        fy_mpa=_positive_number(root["fy_mpa"], "fy_mpa"),
        gamma_m0=_positive_number(root["gamma_m0"], "gamma_m0"),
        e_mpa=_positive_number(root["e_mpa"], "e_mpa"),
        section=section,
        compression_flange_laterally_restrained=lateral_restraint,
        load_cases=tuple(load_cases),
        combinations=tuple(combinations),
    )


def read_beam(path: str | Path) -> Beam:
    """Loads a YAML or JSON beam definition from disk."""
    try:
        with Path(path).open("r", encoding="utf-8") as source:
            data = yaml.safe_load(source)
    except yaml.YAMLError as exc:
        raise InputError(f"cannot parse input file: {exc}") from exc
    return beam_from_mapping(data)


def _combined_loads(
    beam: Beam, combination: Combination
) -> tuple[float, list[tuple[float, float]]]:
    udl = sum(
        case.udl_kN_per_m * combination.factors[case.name]
        for case in beam.load_cases
    )
    points = [
        (
            load.magnitude_kN * combination.factors[case.name],
            load.position_m,
        )
        for case in beam.load_cases
        for load in case.point_loads
        if combination.factors[case.name] > 0
    ]
    return udl, points


def _action_effects(
    span_m: float, udl_kN_per_m: float, points: list[tuple[float, float]]
) -> tuple[float, float, float]:
    """Returns left reaction, maximum absolute shear, and maximum moment."""
    left_reaction = udl_kN_per_m * span_m / 2 + sum(
        load_kN * (span_m - position_m) / span_m
        for load_kN, position_m in points
    )
    events = sorted({0.0, span_m, *(position for _, position in points)})
    shear_candidates: list[float] = []
    for x in events:
        before = sum(load for load, position in points if position < x)
        through = sum(load for load, position in points if position <= x)
        shear_candidates.extend(
            (left_reaction - udl_kN_per_m * x - before,
             left_reaction - udl_kN_per_m * x - through)
        )
    max_shear = max((abs(value) for value in shear_candidates), default=0.0)

    moment_positions = list(events)
    if udl_kN_per_m > 0:
        for left, right in zip(events, events[1:]):
            loads_at_or_before_left = sum(
                load for load, position in points if position <= left
            )
            zero_shear = (
                left_reaction - loads_at_or_before_left
            ) / udl_kN_per_m
            if left < zero_shear < right:
                moment_positions.append(zero_shear)

    max_moment = max(
        (
            left_reaction * x
            - udl_kN_per_m * x**2 / 2
            - sum(load * max(0.0, x - position) for load, position in points)
            for x in moment_positions
        ),
        default=0.0,
    )
    return left_reaction, max_shear, max(0.0, max_moment)


def _max_deflection_mm(
    span_m: float,
    udl_kN_per_m: float,
    points: list[tuple[float, float]],
    e_mpa: float,
    i_y_mm4: float,
) -> float:
    """Calculates maximum elastic deflection for full-span UDL and point loads."""
    span_mm = span_m * 1000
    udl_n_per_mm = udl_kN_per_m
    point_loads_n_mm = [
        (load_kN * 1000, position_m * 1000)
        for load_kN, position_m in points
    ]
    if udl_n_per_mm == 0 and not point_loads_n_mm:
        return 0.0

    left_reaction_n = udl_n_per_mm * span_mm / 2 + sum(
        load_n * (span_mm - position_mm) / span_mm
        for load_n, position_mm in point_loads_n_mm
    )
    ei = e_mpa * i_y_mm4
    base_at_right = (
        left_reaction_n * span_mm**3 / 6
        - udl_n_per_mm * span_mm**4 / 24
        - sum(
            load_n * (span_mm - position_mm) ** 3 / 6
            for load_n, position_mm in point_loads_n_mm
        )
    )
    integration_constant = -base_at_right / (ei * span_mm)

    def slope(x_mm: float) -> float:
        value = (
            left_reaction_n * x_mm**2 / 2
            - udl_n_per_mm * x_mm**3 / 6
            - sum(
                load_n * max(0.0, x_mm - position_mm) ** 2 / 2
                for load_n, position_mm in point_loads_n_mm
            )
        ) / ei
        return value + integration_constant

    def deflection(x_mm: float) -> float:
        value = (
            left_reaction_n * x_mm**3 / 6
            - udl_n_per_mm * x_mm**4 / 24
            - sum(
                load_n * max(0.0, x_mm - position_mm) ** 3 / 6
                for load_n, position_mm in point_loads_n_mm
            )
        ) / ei
        return value + integration_constant * x_mm

    left, right = 0.0, span_mm
    if slope(left) >= 0 or slope(right) <= 0:
        raise ArithmeticError("could not locate the beam's maximum deflection")
    for _ in range(80):
        middle = (left + right) / 2
        if slope(middle) < 0:
            left = middle
        else:
            right = middle
    return abs(deflection((left + right) / 2))


def check_beam(beam: Beam) -> dict[str, Any]:
    """Checks configured load combinations and returns an auditable report."""
    section = beam.section
    if section.section_class in (1, 2):
        bending_modulus = section.w_pl_y_mm3
        bending_basis = "plastic section modulus (Class 1/2)"
    else:
        bending_modulus = section.w_el_y_mm3
        bending_basis = "elastic section modulus (Class 3)"
    if bending_modulus is None:
        raise InputError("the required bending section modulus is missing")

    moment_resistance_kNm = bending_modulus * beam.fy_mpa / beam.gamma_m0 / 1e6
    shear_resistance_kN = (
        section.a_v_mm2 * beam.fy_mpa / (math.sqrt(3) * beam.gamma_m0) / 1000
    )
    combinations: list[dict[str, Any]] = []
    any_failure = False

    for combination in beam.combinations:
        udl, points = _combined_loads(beam, combination)
        _, max_shear_kN, max_moment_kNm = _action_effects(
            beam.span_m, udl, points
        )
        item: dict[str, Any] = {
            "name": combination.name,
            "limit_state": combination.limit_state,
            "factors": dict(combination.factors),
            "max_shear_kN": max_shear_kN,
            "max_moment_kNm": max_moment_kNm,
            "checks": [],
        }
        checks: list[dict[str, Any]] = item["checks"]

        if combination.limit_state == "ULS":
            bending_ratio = max_moment_kNm / moment_resistance_kNm
            shear_ratio = max_shear_kN / shear_resistance_kN
            bending_status = "pass" if bending_ratio <= 1 else "fail"
            shear_status = "pass" if shear_ratio <= 1 else "fail"
            any_failure |= bending_status == "fail" or shear_status == "fail"
            checks.extend(
                [
                    {
                        "id": "cross_section_bending",
                        "status": bending_status,
                        "demand_kNm": max_moment_kNm,
                        "resistance_kNm": moment_resistance_kNm,
                        "utilization": bending_ratio,
                        "reference": "EN 1993-1-1:2005, 6.2.5",
                        "basis": bending_basis,
                    },
                    {
                        "id": "cross_section_shear",
                        "status": shear_status,
                        "demand_kN": max_shear_kN,
                        "resistance_kN": shear_resistance_kN,
                        "utilization": shear_ratio,
                        "reference": "EN 1993-1-1:2005, 6.2.6",
                        "basis": "user-supplied shear area Av",
                    },
                ]
            )
            checks.append(
                {
                    "id": "bending_shear_interaction",
                    "status": (
                        "pass"
                        if max_shear_kN <= 0.5 * shear_resistance_kN
                        else "not_assessed"
                    ),
                    "reference": "EN 1993-1-1:2005, 6.2.8",
                    "note": (
                        "The shear effect on bending resistance is below the "
                        "50% threshold."
                        if max_shear_kN <= 0.5 * shear_resistance_kN
                        else "Shear exceeds 50% of plastic shear resistance; "
                        "the bending-shear interaction reduction is not implemented."
                    ),
                }
            )
            checks.extend(
                [
                    {
                        "id": "lateral_torsional_buckling",
                        "status": (
                            "assumed"
                            if beam.compression_flange_laterally_restrained
                            else "not_assessed"
                        ),
                        "reference": "EN 1993-1-1:2005, 6.3.2",
                        "note": (
                            "Compression-flange restraint is asserted by the "
                            "input; restraint adequacy is not checked."
                            if beam.compression_flange_laterally_restrained
                            else "The beam is unrestrained and lateral-torsional "
                            "buckling resistance is not calculated."
                        ),
                    },
                    {
                        "id": "shear_buckling",
                        "status": "not_assessed",
                        "reference": "EN 1993-1-1:2005, 6.2.6; EN 1993-1-5",
                        "note": "Web slenderness and shear-buckling resistance are not checked.",
                    },
                ]
            )
        else:
            deflection_mm = _max_deflection_mm(
                beam.span_m,
                udl,
                points,
                beam.e_mpa,
                section.i_y_mm4,
            )
            limit_mm = combination.deflection_limit_mm
            if limit_mm is None:
                raise InputError("SLS combination has no deflection limit")
            ratio = deflection_mm / limit_mm
            status = "pass" if ratio <= 1 else "fail"
            any_failure |= status == "fail"
            item["max_deflection_mm"] = deflection_mm
            item["deflection_limit_mm"] = limit_mm
            checks.append(
                {
                    "id": "vertical_deflection",
                    "status": status,
                    "demand_mm": deflection_mm,
                    "limit_mm": limit_mm,
                    "utilization": ratio,
                    "reference": "EN 1993-1-1:2005, 7.2.1; project limit",
                }
            )
        combinations.append(item)

    limitations = [
        "This is a limited member check, not a complete structural design or integrity assessment.",
        "Section classification is supplied by the user and is not independently verified.",
        "Lateral-torsional buckling is not calculated (EN 1993-1-1, 6.3.2). "
        f"Compression-flange restraint is assumed to be "
        f"{'provided' if beam.compression_flange_laterally_restrained else 'not provided'}; "
        "the restraint itself is not checked.",
        "Shear buckling and web slenderness checks under EN 1993-1-5 are not implemented.",
        "Load-combination factors are user-supplied; this tool does not generate "
        "EN 1990 combinations or apply a National Annex.",
        "Actions are limited to downward full-span constant UDL and downward "
        "point loads on a prismatic, simply supported beam; analysis is first-order "
        "elastic and excludes self-weight unless entered as a load.",
        "Connections, local load introduction, fatigue, fire, vibration, "
        "durability, and global frame stability are outside the scope.",
    ]
    status = "fail" if any_failure else "partial"

    return {
        "standard_basis": "EN 1993-1-1:2005; user must confirm governing edition and National Annex.",
        "member_id": beam.member_id,
        "section": section.designation,
        "section_class": section.section_class,
        "status": status,
        "status_note": (
            "A partial result is not design approval; review all limitations."
        ),
        "resistances": {
            "bending_kNm": moment_resistance_kNm,
            "bending_basis": bending_basis,
            "shear_kN": shear_resistance_kN,
            "gamma_m0": beam.gamma_m0,
        },
        "combinations": combinations,
        "limitations": limitations,
    }


def report_json(report: Mapping[str, Any]) -> str:
    """Serializes a check report as stable, indented JSON."""
    return json.dumps(report, indent=2, sort_keys=True, allow_nan=False)
