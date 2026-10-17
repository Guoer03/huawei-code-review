import json
import stat
import tempfile
import unittest
from pathlib import Path

try:  # Works both as a package and with unittest discover from this directory.
    from .runner import parse_output, run_adapter
except ImportError:  # pragma: no cover - discovery fallback
    from runner import parse_output, run_adapter


class ParseAdaptersTest(unittest.TestCase):
    def test_eslint_json_normalises_finding(self):
        findings, diagnostics = parse_output("eslint", json.dumps([{"filePath": "/repo/src/a.js", "messages": [{"ruleId": "no-eval", "severity": 2, "line": 3, "column": 4, "message": "Unexpected eval."}]}]), cwd="/repo")
        self.assertFalse(diagnostics)
        self.assertEqual(findings[0]["path"], "src/a.js")
        self.assertEqual(findings[0]["severity"], "error")
        self.assertEqual(findings[0]["id"], "no-eval")
        typescript, _ = parse_output("eslint", json.dumps([{"filePath": "src/a.tsx", "messages": [{"ruleId": "x", "severity": 1, "line": 1, "column": 1, "message": "warning"}]}]))
        self.assertEqual(typescript[0]["language"], "typescript")

    def test_ruff_json_and_sarif(self):
        findings, diagnostics = parse_output("ruff", json.dumps([{"filename": "a.py", "location": {"row": 2, "column": 1}, "code": "E501", "message": "line too long"}]))
        self.assertFalse(diagnostics)
        self.assertEqual(findings[0]["language"], "python")
        sarif = {"version": "2.1.0", "runs": [{"tool": {"driver": {"rules": []}}, "results": [{"ruleId": "X", "level": "error", "message": {"text": "bad"}, "locations": [{"physicalLocation": {"artifactLocation": {"uri": "a.ts"}, "region": {"startLine": 4, "startColumn": 2}}}]}]}]}
        findings, diagnostics = parse_output("tsc", json.dumps(sarif), format_hint="sarif")
        self.assertFalse(diagnostics)
        self.assertEqual(findings[0]["path"], "a.ts")

    def test_text_and_xml_parsers(self):
        findings, diagnostics = parse_output("flake8", "a.py:5:2: E501 line too long\nb.py:2:1: W291 trailing whitespace\n")
        self.assertFalse(diagnostics)
        self.assertEqual([x["severity"] for x in findings], ["error", "warning"])
        xml = '<checkstyle><file name="A.java"><error line="7" column="3" severity="warning" source="Javadoc" message="Missing docs"/></file></checkstyle>'
        findings, diagnostics = parse_output("checkstyle", xml)
        self.assertFalse(diagnostics)
        self.assertEqual(findings[0]["id"], "Javadoc")

    def test_bad_output_is_diagnostic(self):
        findings, diagnostics = parse_output("eslint", "not json")
        self.assertEqual(findings, [])
        self.assertEqual(diagnostics[0]["kind"], "parse_error")


class RunAdapterTest(unittest.TestCase):
    def test_fatal_exit_with_some_findings_is_incomplete(self):
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / 'eslint'
            executable.write_text("#!/bin/sh\nprintf '%s' '[{\"filePath\":\"a.js\",\"messages\":[{\"ruleId\":\"no-eval\",\"severity\":2,\"line\":1,\"message\":\"eval\"}]}]'\nexit 2\n")
            executable.chmod(0o755)
            result = run_adapter('eslint', ['a.js'], executable=str(executable))
        self.assertEqual(result['status'], 'error')
        self.assertEqual(len(result['findings']), 1)

    def test_parser_failure_is_not_a_successful_lint(self):
        output = '[{"filePath":"a.js","messages":[{"ruleId":null,"fatal":true,"severity":2,"message":"Parsing error"}]}]'
        _, diagnostics = parse_output('eslint', output)
        self.assertTrue(diagnostics)

    def test_empty_json_checker_output_is_error(self):
        _, diagnostics = parse_output('ruff', '')
        self.assertTrue(diagnostics)

    def test_malformed_ruff_shape_is_error(self):
        _, diagnostics = parse_output('ruff', '{"not_findings":true}')
        self.assertTrue(diagnostics)

    def test_missing_tool_is_structured(self):
        result = run_adapter("eslint", [], executable="definitely-not-installed-huawei-eslint")
        self.assertEqual(result["status"], "missing")
        self.assertEqual(result["diagnostics"][0]["kind"], "missing_tool")

    def test_fake_executable_preserves_nonzero_findings(self):
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / "fake-eslint"
            executable.write_text("#!/bin/sh\nprintf '%s' '[{\"filePath\":\"a.js\",\"messages\":[{\"ruleId\":\"x\",\"severity\":2,\"line\":1,\"column\":1,\"message\":\"bad\"}]}]'\nexit 1\n")
            executable.chmod(executable.stat().st_mode | stat.S_IXUSR)
            result = run_adapter("eslint", ["a.js"], executable=str(executable))
            self.assertEqual(result["status"], "completed")
            self.assertEqual(result["returncode"], 1)
            self.assertEqual(result["findings"][0]["id"], "x")

    def test_tool_failure_without_findings_is_error(self):
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / "bad-eslint"
            executable.write_text("#!/bin/sh\nprintf '%s' '[]'\necho 'configuration failed' >&2\nexit 2\n")
            executable.chmod(executable.stat().st_mode | stat.S_IXUSR)
            result = run_adapter("eslint", ["a.js"], executable=str(executable))
            self.assertEqual(result["status"], "error")
            self.assertEqual(result["diagnostics"][0]["kind"], "tool_error")

    def test_checkstyle_requires_config(self):
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / "checkstyle"
            executable.touch()
            result = run_adapter("checkstyle", ["A.java"], executable=str(executable))
            self.assertEqual(result["status"], "skipped")
            self.assertEqual(result["diagnostics"][0]["kind"], "missing_config")


if __name__ == "__main__":
    unittest.main()
