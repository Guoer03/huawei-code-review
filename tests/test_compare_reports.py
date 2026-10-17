from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "compare_reports.py"


def load_comparator():
    spec = importlib.util.spec_from_file_location("huawei_compare_reports", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


COMPARE = load_comparator()


def finding(path: str, line: int, column: int, rule_id: str, message: str, **extra):
    return {
        "path": path,
        "line": line,
        "column": column,
        "id": rule_id,
        "message": message,
        **extra,
    }


class CompareReportsTests(unittest.TestCase):
    def test_rule_removed_from_scan_does_not_count_as_verified_fix(self):
        before = {'findings': [finding('app.py', 1, 1, 'R1', 'bad')],
                  'rule_coverage': [{'rule_id': 'R1', 'coverage_status': 'covered'}]}
        after = {'findings': [], 'rule_coverage': [{'rule_id': 'R2', 'coverage_status': 'covered'}]}
        delta = COMPARE.compare_reports(before, after)
        self.assertEqual(delta['resolved'], [])
        self.assertEqual(len(delta['unverified_resolutions']), 1)

    def test_successful_same_rule_rescan_can_verify_disappearance(self):
        before = {'findings': [finding('app.py', 1, 1, 'R1', 'bad')],
                  'input_files': [{'path': 'app.py'}],
                  'rule_coverage': [{'rule_id': 'R1', 'coverage_status': 'covered'}]}
        after = {'findings': [], 'input_files': [{'path': 'app.py'}], 'rule_coverage': [{'rule_id': 'R1', 'coverage_status': 'covered', 'execution_status': 'completed'}]}
        delta = COMPARE.compare_reports(before, after)
        self.assertEqual(len(delta['resolved']), 1)

    def test_removing_file_from_scan_is_not_verified_repair(self):
        before = {'findings': [finding('app.py', 1, 1, 'R1', 'bad')], 'input_files': [{'path': 'app.py'}],
                  'rule_coverage': [{'rule_id': 'R1', 'coverage_status': 'covered'}]}
        after = {'findings': [], 'input_files': [{'path': 'other.py'}],
                 'rule_coverage': [{'rule_id': 'R1', 'coverage_status': 'covered', 'execution_status': 'completed'}]}
        delta = COMPARE.compare_reports(before, after)
        self.assertEqual(delta['resolved'], [])
        self.assertEqual(len(delta['unverified_resolutions']), 1)

    def test_classifies_resolved_new_unchanged_and_moved(self):
        before = {
            "findings": [
                finding("src/a.py", 1, 1, "R-UNCHANGED", "Use   const", severity="warning"),
                finding("src/a.py", 10, 3, "R-MOVED", "Avoid dynamic code"),
                finding("src/old.py", 4, 1, "R-RESOLVED", "Remove this issue"),
            ]
        }
        after = {
            "findings": [
                # Whitespace and case differences are normalized for matching.
                finding("src/a.py", 1, 1, "R-UNCHANGED", " use const ", severity="error"),
                finding("src/a.py", 12, 8, "R-MOVED", "Avoid   dynamic code"),
                finding("src/new.py", 2, 1, "R-NEW", "New issue"),
            ]
        }

        delta = COMPARE.compare_reports(before, after)

        self.assertEqual(delta["summary"], {
            "before_findings": 3,
            "after_findings": 3,
            "resolved": 1,
            "new": 1,
            "unchanged": 1,
            "moved": 1,
            "net_change": 0,
            "before_uncovered": 0,
            "after_uncovered": 0,
        })
        self.assertEqual(delta["unchanged"][0]["id"], "R-UNCHANGED")
        self.assertEqual(delta["resolved"][0]["id"], "R-RESOLVED")
        self.assertEqual(delta["new"][0]["id"], "R-NEW")
        self.assertEqual(delta["moved"][0]["before"]["line"], 10)
        self.assertEqual(delta["moved"][0]["after"]["line"], 12)

    def test_duplicate_findings_are_matched_one_to_one(self):
        issue = finding("src/a.js", 3, 1, "R-DUP", "Same")
        before = {"findings": [issue, dict(issue)]}
        after = {"findings": [dict(issue)]}

        delta = COMPARE.compare_reports(before, after)

        self.assertEqual(delta["summary"]["unchanged"], 1)
        self.assertEqual(delta["summary"]["resolved"], 1)

    def test_cli_writes_output_and_rejects_malformed_reports(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            before = directory / "before.json"
            after = directory / "after.json"
            output = directory / "nested" / "delta.json"
            before.write_text(json.dumps({"findings": []}), encoding="utf-8")
            after.write_text(json.dumps({"findings": [finding("a.py", 1, 1, "R", "x")]}), encoding="utf-8")

            result = subprocess.run(
                [sys.executable, str(SCRIPT), str(before), str(after), "--output", str(output)],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(output.read_text(encoding="utf-8"))["summary"]["new"], 1)
            self.assertEqual(result.stdout, "")

            malformed = directory / "bad.json"
            malformed.write_text("[]", encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(SCRIPT), str(malformed), str(after)],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("must contain a JSON object", result.stderr)


if __name__ == "__main__":
    unittest.main()
