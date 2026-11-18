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

import math
import unittest

from structural_checks.core import (
    InputError,
    _action_effects,
    _max_deflection_mm,
    beam_from_mapping,
    check_beam,
)


def sample_input() -> dict[str, object]:
    return {
        "member_id": "B-01",
        "span_m": 6.0,
        "fy_mpa": 355.0,
        "gamma_m0": 1.0,
        "e_mpa": 210000.0,
        "compression_flange_laterally_restrained": True,
        "section": {
            "designation": "test section",
            "section_class": 2,
            "i_y_mm4": 2.5e8,
            "a_v_mm2": 2500.0,
            "w_pl_y_mm3": 1.0e6,
        },
        "load_cases": [
            {"name": "G", "udl_kN_per_m": 10.0, "point_loads": []},
            {
                "name": "Q",
                "udl_kN_per_m": 0.0,
                "point_loads": [
                    {"magnitude_kN": 12.0, "position_m": 3.0}
                ],
            },
        ],
        "combinations": [
            {
                "name": "ULS-example",
                "limit_state": "ULS",
                "factors": {"G": 1.0, "Q": 1.0},
            },
            {
                "name": "SLS-example",
                "limit_state": "SLS",
                "factors": {"G": 1.0, "Q": 1.0},
                "deflection_limit_mm": 20.0,
            },
        ],
    }


class BeamCalculationTests(unittest.TestCase):
    def test_uniform_load_actions(self) -> None:
        reaction, shear, moment = _action_effects(6.0, 10.0, [])
        self.assertAlmostEqual(reaction, 30.0)
        self.assertAlmostEqual(shear, 30.0)
        self.assertAlmostEqual(moment, 45.0)

    def test_point_load_actions(self) -> None:
        reaction, shear, moment = _action_effects(6.0, 0.0, [(12.0, 3.0)])
        self.assertAlmostEqual(reaction, 6.0)
        self.assertAlmostEqual(shear, 6.0)
        self.assertAlmostEqual(moment, 18.0)

    def test_uniform_load_deflection_matches_closed_form(self) -> None:
        actual = _max_deflection_mm(
            span_m=6.0,
            udl_kN_per_m=10.0,
            points=[],
            e_mpa=210000.0,
            i_y_mm4=2.5e8,
        )
        expected = 5 * 10 * 6000**4 / (384 * 210000 * 2.5e8)
        self.assertTrue(math.isclose(actual, expected, rel_tol=1e-10))

    def test_midspan_point_load_deflection_matches_closed_form(self) -> None:
        actual = _max_deflection_mm(
            span_m=6.0,
            udl_kN_per_m=0.0,
            points=[(10.0, 3.0)],
            e_mpa=210000.0,
            i_y_mm4=2.5e8,
        )
        expected = 10000 * 6000**3 / (48 * 210000 * 2.5e8)
        self.assertTrue(math.isclose(actual, expected, rel_tol=1e-10))

    def test_combination_scales_actions_and_reports_partial_scope(self) -> None:
        report = check_beam(beam_from_mapping(sample_input()))
        uls = report["combinations"][0]
        self.assertAlmostEqual(uls["max_shear_kN"], 36.0)
        self.assertAlmostEqual(uls["max_moment_kNm"], 63.0)
        self.assertEqual(report["status"], "partial")

    def test_class_three_bending_uses_elastic_section_modulus(self) -> None:
        data = sample_input()
        section = data["section"]
        assert isinstance(section, dict)
        section["section_class"] = 3
        section.pop("w_pl_y_mm3")
        section["w_el_y_mm3"] = 500000.0
        report = check_beam(beam_from_mapping(data))
        self.assertAlmostEqual(report["resistances"]["bending_kNm"], 177.5)

    def test_shear_interaction_is_not_assumed_safe_above_threshold(self) -> None:
        data = sample_input()
        data["load_cases"] = [
            {"name": "G", "udl_kN_per_m": 500.0, "point_loads": []},
            {
                "name": "Q",
                "udl_kN_per_m": 0.0,
                "point_loads": [
                    {"magnitude_kN": 0.1, "position_m": 3.0}
                ],
            },
        ]
        report = check_beam(beam_from_mapping(data))
        interaction = report["combinations"][0]["checks"][2]
        self.assertEqual(interaction["status"], "not_assessed")

    def test_exceeding_a_project_deflection_limit_is_a_failure(self) -> None:
        data = sample_input()
        combinations = data["combinations"]
        assert isinstance(combinations, list)
        combinations[1]["deflection_limit_mm"] = 0.1
        report = check_beam(beam_from_mapping(data))
        sls = report["combinations"][1]
        self.assertEqual(sls["checks"][0]["status"], "fail")
        self.assertEqual(report["status"], "fail")

    def test_class_four_and_unconfigured_combinations_are_rejected(self) -> None:
        data = sample_input()
        section = data["section"]
        assert isinstance(section, dict)
        section["section_class"] = 4
        with self.assertRaisesRegex(InputError, "Class 4"):
            beam_from_mapping(data)

        data = sample_input()
        combinations = data["combinations"]
        assert isinstance(combinations, list)
        combinations[0]["factors"] = {"G": 1.0}
        with self.assertRaisesRegex(InputError, "every load case"):
            beam_from_mapping(data)


if __name__ == "__main__":
    unittest.main()
