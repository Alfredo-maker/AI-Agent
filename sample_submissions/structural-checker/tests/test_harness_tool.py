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

import asyncio
import json
import os
from pathlib import Path
import unittest

os.environ.setdefault("MODEL_NAME", "test-model")
os.environ.setdefault("OPENAI_API_KEY", "not-used-by-this-test")

import serve


class FakeSession:
    def __init__(self) -> None:
        example = (
            Path(__file__).parent.parent
            / "structural_checks"
            / "examples"
            / "simply_supported_beam.yaml"
        )
        self.files = {"beam.yaml": example.read_bytes()}
        self.writes: dict[str, bytes] = {}

    async def read_file(self, path: str) -> bytes:
        return self.files[path]

    async def write_file(self, path: str, data: str | bytes) -> int:
        contents = data.encode() if isinstance(data, str) else data
        self.writes[path] = contents
        return len(contents)


class CheckerToolTests(unittest.TestCase):
    def test_tool_reads_task_input_and_writes_json_report(self) -> None:
        session = FakeSession()
        result = asyncio.run(
            serve.run_tool(
                session,
                {
                    "name": "check_steel_beam",
                    "arguments": json.dumps(
                        {
                            "input_path": "beam.yaml",
                            "output_path": "beam-report.json",
                        }
                    ),
                },
            )
        )
        report = json.loads(session.writes["beam-report.json"])
        self.assertIn("Wrote", result)
        self.assertEqual(report["status"], "partial")
        self.assertIn("lateral_torsional_buckling", {
            check["id"]
            for item in report["combinations"]
            for check in item["checks"]
        })

    def test_tool_reports_invalid_input_without_writing_a_report(self) -> None:
        session = FakeSession()
        session.files["invalid.yaml"] = b"not: [valid"
        result = asyncio.run(
            serve.run_tool(
                session,
                {
                    "name": "check_steel_beam",
                    "arguments": json.dumps(
                        {
                            "input_path": "invalid.yaml",
                            "output_path": "beam-report.json",
                        }
                    ),
                },
            )
        )
        self.assertIn("error:", result)
        self.assertNotIn("beam-report.json", session.writes)


if __name__ == "__main__":
    unittest.main()
