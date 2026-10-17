"""Regression tests for the deterministic Huawei/OpenHarmony checker.

The suite deliberately invokes the same script used by the skill.  This keeps
the contract testable without installing the checker as a Python package and
also exercises its JSON, Markdown, and SARIF boundaries.
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check.py"
FIXTURES = ROOT / "tests" / "fixtures"
sys.path.insert(0, str(ROOT / "scripts"))


def load_checker():
    spec = importlib.util.spec_from_file_location("huawei_check", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CHECKER = load_checker()
from config import Config
_original_check = CHECKER.check
def _legacy_check(*args, **kwargs):
    kwargs.setdefault("config", Config(ruleset="legacy"))
    return _original_check(*args, **kwargs)
CHECKER.check = _legacy_check


class CheckerEngineTests(unittest.TestCase):
    def test_all_four_languages_are_auto_detected(self):
        report = CHECKER.check(
            [str(FIXTURES / name) for name in (
                "violations.java", "violations.js", "violations.ts", "violations.py"
            )],
            "auto",
            "balanced",
        )
        self.assertEqual(report["summary"]["files"], 4)
        self.assertFalse(report["uncovered"])
        self.assertEqual(
            {finding["language"] for finding in report["findings"]},
            {"java", "javascript", "typescript", "python"},
        )

    def test_each_language_reports_expected_rule_ids(self):
        expected = {
            "violations.java": {"HUAWEI-JAVA-FORMAT-001", "HUAWEI-JAVA-FORMAT-002", "HUAWEI-JAVA-SWITCH-001"},
            "violations.js": {"OH-JS-DECL-001", "OH-JS-SECURITY-001", "OH-JS-FORMAT-001", "OH-JS-EQUALITY-001"},
            "violations.ts": {"OH-TS-DECL-001", "OH-TS-TYPE-001", "OH-TS-SECURITY-001", "OH-TS-ARRAY-001"},
            "violations.py": {"HUAWEI-PY-FORMAT-001", "HUAWEI-PY-IMPORT-001", "HUAWEI-PY-STYLE-001", "HUAWEI-PY-QUALITY-001"},
        }
        for filename, rule_ids in expected.items():
            with self.subTest(filename=filename):
                report = CHECKER.check([str(FIXTURES / filename)], "auto", "balanced")
                actual = {finding["id"] for finding in report["findings"]}
                self.assertTrue(rule_ids <= actual, (filename, rule_ids - actual))

    def test_clean_fixtures_have_no_findings_or_uncovered_files(self):
        for filename in ("clean.java", "clean.js", "clean.ts", "clean.py"):
            with self.subTest(filename=filename):
                report = CHECKER.check([str(FIXTURES / filename)], "auto", "balanced")
                self.assertEqual(report["findings"], [])
                self.assertEqual(report["uncovered"], [])
                self.assertTrue(report["summary"]["pass"])

    def test_inline_suppression_removes_findings(self):
        report = CHECKER.check([str(FIXTURES / "suppressed.js")], "auto", "balanced")
        self.assertEqual(report["findings"], [])

    def test_source_provenance_is_present_and_language_specific(self):
        report = CHECKER.check([str(FIXTURES / "violations.js"), str(FIXTURES / "violations.py")], "auto", "balanced")
        sources = {f["language"]: f["source"] for f in report["findings"]}
        self.assertEqual(sources["javascript"]["status"], "official-public")
        self.assertEqual(sources["python"]["status"], "community")
        for finding in report["findings"]:
            self.assertIn(finding["confidence"], {"high", "medium", "low"})
            self.assertTrue(finding["evidence"])


class CheckerFailureAndCliTests(unittest.TestCase):
    def run_cli(self, *args, env=None):
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--ruleset", "legacy", *map(str, args)],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_unsupported_extension_is_uncovered_and_exit_two(self):
        result = self.run_cli(FIXTURES / "unsupported.txt")
        self.assertEqual(result.returncode, 2)
        report = json.loads(result.stdout)
        self.assertFalse(report["summary"]["pass"])
        self.assertEqual(report["summary"]["findings"], 0)
        self.assertEqual(report["uncovered"][0]["reason"], "language could not be inferred")

    def test_binary_file_is_uncovered_and_exit_two(self):
        with tempfile.TemporaryDirectory() as directory:
            binary = Path(directory) / "payload.py"
            binary.write_bytes(b"\xff\xfe\x00\x01")
            result = self.run_cli(binary)
            self.assertEqual(result.returncode, 2)
            report = json.loads(result.stdout)
            self.assertIn("utf-8", report["uncovered"][0]["reason"].lower())

    def test_explicit_language_checks_extensionless_stdin(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--ruleset", "legacy", "-", "--language", "python"],
            input="def good_name():\n    return 1\n",
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0)
        report = json.loads(result.stdout)
        self.assertEqual(report["summary"]["files"], 1)
        self.assertEqual(report["findings"], [])

    def test_profile_option_is_recorded_as_configuration(self):
        result = self.run_cli(FIXTURES / "clean.js", "--profile", "strict")
        self.assertEqual(result.returncode, 0)
        report = json.loads(result.stdout)
        self.assertEqual(report["toolchain"]["profile"], "strict")

    def test_json_project_config_controls_format_and_profile(self):
        result = self.run_cli(
            FIXTURES / "clean.js",
            "--config",
            FIXTURES / "review-config.json",
        )
        self.assertEqual(result.returncode, 0)
        sarif = json.loads(result.stdout)
        self.assertEqual(sarif["version"], "2.1.0")

        # Explicit CLI values take precedence over project configuration.
        result = self.run_cli(
            FIXTURES / "clean.js",
            "--config",
            FIXTURES / "review-config.json",
            "--format",
            "json",
            "--profile",
            "balanced",
        )
        self.assertEqual(result.returncode, 0)
        report = json.loads(result.stdout)
        self.assertEqual(report["toolchain"]["profile"], "balanced")

    def test_config_can_disable_rule_and_fail_on_none(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "check.json"
            config.write_text(
                json.dumps({"format": "json", "fail_on": "none", "rules": {"OH-JS-DECL-001": "off"}}),
                encoding="utf-8",
            )
            result = self.run_cli(FIXTURES / "violations.js", "--config", config)
            self.assertEqual(result.returncode, 0)
            report = json.loads(result.stdout)
            self.assertNotIn("OH-JS-DECL-001", {f["id"] for f in report["findings"]})
            self.assertIn("OH-JS-SECURITY-001", {f["id"] for f in report["findings"]})

    def test_cli_ignore_rule_and_exclude_path(self):
        ignored = self.run_cli(FIXTURES / "violations.js", "--ignore", "OH-JS-DECL-001")
        self.assertEqual(ignored.returncode, 1)
        self.assertNotIn("OH-JS-DECL-001", {f["id"] for f in json.loads(ignored.stdout)["findings"]})

        excluded = self.run_cli(FIXTURES, "--exclude", "violations.js")
        report = json.loads(excluded.stdout)
        self.assertNotIn(str(FIXTURES / "violations.js"), {f["path"] for f in report["findings"]})

    def test_json_output_has_stable_top_level_schema(self):
        result = self.run_cli(FIXTURES / "violations.ts", "--format", "json")
        report = json.loads(result.stdout)
        self.assertTrue({"schema_version", "summary", "findings", "uncovered", "toolchain"} <= set(report))
        self.assertEqual(report["schema_version"], "1.0")

    def test_markdown_output_contains_evidence_and_provenance(self):
        result = self.run_cli(FIXTURES / "violations.js", "--format", "markdown")
        self.assertEqual(result.returncode, 1)
        self.assertIn("# Huawei/OpenHarmony code review", result.stdout)
        self.assertIn("Evidence:", result.stdout)
        self.assertIn("Source: `openharmony-javascript` (official-public)", result.stdout)

    def test_sarif_output_has_locations_and_rule_ids(self):
        result = self.run_cli(FIXTURES / "violations.py", "--format", "sarif")
        self.assertEqual(result.returncode, 1)
        sarif = json.loads(result.stdout)
        self.assertEqual(sarif["version"], "2.1.0")
        findings = sarif["runs"][0]["results"]
        self.assertTrue(findings)
        self.assertTrue(all(item["ruleId"].startswith("HUAWEI-PY-") for item in findings))
        self.assertTrue(all("locations" in item for item in findings))

    def test_checker_does_not_require_optional_external_tools(self):
        env = os.environ.copy()
        env["PATH"] = "/nonexistent"
        result = self.run_cli(FIXTURES / "clean.py", env=env)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_optional_adapter_is_reported_without_breaking_cli(self):
        result = self.run_cli(FIXTURES / "clean.js", "--tool", "eslint")
        self.assertIn(result.returncode, (0, 2))
        report = json.loads(result.stdout)
        self.assertIn("adapters", report["toolchain"])
        self.assertEqual(report["toolchain"]["adapters"][0]["name"], "eslint")

    def test_required_missing_adapter_is_uncovered(self):
        result = self.run_cli(FIXTURES / "clean.js", "--require-tool", "missing-huawei-checker")
        self.assertEqual(result.returncode, 2)
        report = json.loads(result.stdout)
        self.assertTrue(any("required adapter" in item["reason"] for item in report["uncovered"]))


if __name__ == "__main__":
    unittest.main()
