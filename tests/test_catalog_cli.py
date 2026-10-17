"""End-to-end acceptance gates for imported rule execution, not catalog presence."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / 'scripts/check.py'


class CatalogCliTests(unittest.TestCase):
    def invoke(self, *args):
        return subprocess.run([sys.executable, str(CLI), *map(str, args)],
                              cwd=ROOT, text=True, capture_output=True, timeout=30)

    def test_list_rules_accounts_for_every_exported_identity(self):
        result = self.invoke('--list-rules')
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(len(data['rule_coverage']), 469)
        self.assertEqual(len({r['key'] for r in data['rule_coverage']}), 469)
        self.assertTrue(all(r['reason'] for r in data['rule_coverage']))

    def test_default_scan_executes_exported_mutable_default_rule(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'example.py'
            path.write_text('def append_item(item, values=[]):\n    values.append(item)\n    return values\n')
            result = self.invoke(path)
        self.assertIn(result.returncode, (1, 2), result.stderr)
        report = json.loads(result.stdout)
        self.assertIn('da6b2b5d6db811eea68ffa163e0fa374', {f['id'] for f in report['findings']})
        self.assertEqual(report['toolchain']['ruleset'], 'catalog')

    def test_catalog_gaps_fail_even_when_findings_threshold_is_none(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'empty.py'
            path.write_text('')
            result = self.invoke(path, '--fail-on', 'none')
        self.assertEqual(result.returncode, 2, result.stderr)
        report = json.loads(result.stdout)
        self.assertFalse(report['summary']['pass'])
        self.assertFalse(report['coverage_summary']['complete'])
        self.assertTrue(report['uncovered'])

    def test_selected_complete_rule_can_pass_and_reject_mutable_default(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'selected.py'
            path.write_text('def add(value, values=None):\n    return value\n')
            result = self.invoke(path, '--select', 'da6b2b5d6db811eea68ffa163e0fa374')
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report['coverage_summary']['selected_rules'], 1)
        self.assertTrue(report['coverage_summary']['complete'])

    def test_unknown_selected_rule_is_configuration_failure(self):
        result = self.invoke('--list-rules', '--select', 'not-a-real-rule')
        self.assertEqual(result.returncode, 2)
        self.assertIn('unknown', result.stderr.lower())

    def test_legacy_requires_explicit_opt_in(self):
        result = self.invoke(ROOT / 'tests/fixtures/clean.py', '--ruleset', 'legacy')
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report['toolchain']['ruleset'], 'legacy')
        self.assertFalse(report['coverage_summary']['catalog_checked'])

    def test_raw_mixed_line_endings_reach_the_python_detector(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'endings.py'
            path.write_bytes(b'first = 1\r\nsecond = 2\n')
            result = self.invoke(path, '--select', 'da6a775d6db811eea68ffa163e0fa374', '--fail-on', 'warning')
        report = json.loads(result.stdout)
        self.assertTrue(report['findings'])
        self.assertEqual(report['findings'][0]['id'], 'da6a775d6db811eea68ffa163e0fa374')

    def test_directory_discovery_includes_modern_module_extensions(self):
        from scripts.engine import files_for, language_for
        with tempfile.TemporaryDirectory() as temp:
            for suffix in ('.mjs', '.cjs', '.mts', '.cts'):
                (Path(temp) / ('module' + suffix)).write_text('export {};')
            files, errors = files_for([temp])
        self.assertEqual(errors, [])
        self.assertEqual({Path(path).suffix: language_for(path) for path, _ in files},
                         {'.mjs': 'javascript', '.cjs': 'javascript',
                          '.mts': 'typescript', '.cts': 'typescript'})

    def test_invalid_utf8_java_is_analysis_failure_not_clean(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'BadEncoding.java'
            path.write_bytes(b'class BadEncoding { /*\xff*/ }')
            result = self.invoke(path, '--select', 'da7457aa6db811eea68ffa163e0fa374')
        self.assertEqual(result.returncode, 2, result.stderr)
        report = json.loads(result.stdout)
        self.assertFalse(report['summary']['pass'])
        self.assertFalse(report['coverage_summary']['complete'])
        self.assertTrue(any('cannot read file' in row['reason'] for row in report['uncovered']))

    def test_catalog_report_records_analysis_fingerprint(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'example.py'
            path.write_text('def collect(items=None):\n    return items\n')
            result = self.invoke(path, '--select', 'da6b2b5d6db811eea68ffa163e0fa374')
        report = json.loads(result.stdout)
        self.assertRegex(report['rule_coverage'][0]['detector_fingerprint'], r'^[0-9a-f]{64}$')
        self.assertIn('python', report['toolchain']['analyzers'])

    def test_explicit_javascript_stdin_runs_selected_rule(self):
        from scripts.catalog_frontend import runtime_status
        if not runtime_status()['available']:
            self.skipTest('frontend runtime unavailable')
        result = subprocess.run([sys.executable, str(CLI), '-', '--language', 'javascript',
                                 '--select', 'da73a29a6db811eea68ffa163e0fa374'],
                                cwd=ROOT, text=True, input='debugger;', capture_output=True)
        report = json.loads(result.stdout)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual([f['id'] for f in report['findings']], ['da73a29a6db811eea68ffa163e0fa374'])

    def test_language_override_cannot_silently_skip_frontend_rules(self):
        from scripts.catalog_frontend import runtime_status
        if not runtime_status()['available']:
            self.skipTest('frontend runtime unavailable')
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'input.ts'
            path.write_text('debugger;')
            result=self.invoke(path,'--language','javascript','--select','da73a29a6db811eea68ffa163e0fa374')
        report=json.loads(result.stdout)
        self.assertEqual(result.returncode,1,result.stderr)
        self.assertEqual(len(report['findings']),1)


if __name__ == '__main__':
    unittest.main()
