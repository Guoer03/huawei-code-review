"""Tests for the stable source-checkout and package CLI entry points."""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10; other entry tests still run.
    try:
        import tomli as tomllib
    except ModuleNotFoundError:
        tomllib = None


ROOT = Path(__file__).resolve().parents[1]
WRAPPER = ROOT / "bin" / "huawei-code-review"
COMPARE_WRAPPER = ROOT / "bin" / "huawei-code-review-compare"
FIXTURES = ROOT / "tests" / "fixtures"


class CliEntryTests(unittest.TestCase):
    def run_command(self, *command: str, cwd: Path | None = None):
        return subprocess.run(
            list(command),
            cwd=cwd or ROOT,
            env={**os.environ, "PYTHON": sys.executable},
            capture_output=True,
            text=True,
            check=False,
        )

    @unittest.skipIf(tomllib is None, "Metadata validation needs Python 3.11+ or tomli")
    def test_pyproject_exposes_stable_console_script(self):
        with (ROOT / "pyproject.toml").open("rb") as stream:
            project = tomllib.load(stream)["project"]
        self.assertEqual(project["name"], "huawei-code-review")
        self.assertEqual(project["scripts"]["huawei-code-review"], "scripts.check:main")
        self.assertRegex(project["version"], r"^\d+\.\d+\.\d+$")

    def test_source_checkout_wrapper_works_outside_repository(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self.run_command(str(WRAPPER), "--help", cwd=Path(directory))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("usage:", result.stdout.lower())
        self.assertIn("huawei-code-review", result.stdout)

    def test_wrapper_forwards_checker_arguments(self):
        result = self.run_command(str(WRAPPER), str(FIXTURES / "clean.py"), "--ruleset", "legacy", "--format", "json")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('"schema_version": "1.0"', result.stdout)

    def test_compare_wrapper_works_from_any_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            before = Path(directory) / "before.json"
            after = Path(directory) / "after.json"
            before.write_text('{"findings": []}', encoding="utf-8")
            after.write_text('{"findings": []}', encoding="utf-8")
            result = self.run_command(
                str(COMPARE_WRAPPER), str(before), str(after), cwd=Path(directory)
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('"before_findings": 0', result.stdout)

    def test_module_entry_point_supports_help_and_version(self):
        help_result = self.run_command(sys.executable, "-m", "scripts", "--help")
        self.assertEqual(help_result.returncode, 0, help_result.stderr)
        self.assertIn("usage:", help_result.stdout.lower())

        version_result = self.run_command(sys.executable, "-m", "scripts", "--version")
        self.assertEqual(version_result.returncode, 0, version_result.stderr)
        self.assertRegex(version_result.stdout.strip(), r"^huawei-code-review \d+\.\d+\.\d+$")


if __name__ == "__main__":
    unittest.main()
