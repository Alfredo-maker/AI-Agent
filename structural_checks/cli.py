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

"""Command-line entry point for the structural beam checker."""

import argparse
from pathlib import Path
import sys
from typing import Any

import yaml

from structural_checks.core import InputError, beam_from_mapping, check_beam, report_json


def _summary(report: dict[str, Any]) -> str:
    lines = [
        f"Member {report['member_id']} ({report['section']}): {report['status']}",
        str(report["status_note"]),
    ]
    for combination in report["combinations"]:
        lines.append(
            f"\n{combination['name']} [{combination['limit_state']}]"
        )
        for check in combination["checks"]:
            utilization = check.get("utilization")
            suffix = (
                f", utilization {utilization:.3f}"
                if isinstance(utilization, (int, float))
                else ""
            )
            lines.append(
                f"  {check['id']}: {check['status']}{suffix}"
            )
    lines.append("\nLimitations:")
    lines.extend(f"  - {item}" for item in report["limitations"])
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run limited-scope checks for a simply supported steel beam."
    )
    parser.add_argument("input", type=Path, help="YAML or JSON beam definition")
    parser.add_argument(
        "--output",
        type=Path,
        help="write the detailed JSON report to this path",
    )
    args = parser.parse_args(argv)

    try:
        with args.input.open("r", encoding="utf-8") as source:
            data = yaml.safe_load(source)
        report = check_beam(beam_from_mapping(data))
        if args.output:
            args.output.write_text(report_json(report) + "\n", encoding="utf-8")
        print(_summary(report))
    except (OSError, yaml.YAMLError, InputError, ArithmeticError, ValueError) as exc:
        print(f"structural-checks: {exc}", file=sys.stderr)
        return 2
    return 1 if report["status"] == "fail" else 0
