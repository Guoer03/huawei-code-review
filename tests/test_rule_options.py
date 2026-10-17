"""Project policy must affect real detectors without silently weakening evidence."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.compare_reports import compare_reports

LINE = 'da6a6d696db811eea68ffa163e0fa374'
JAVA_PARAMETERS = 'da7497676db811eea68ffa163e0fa374'
CASES = 'da6d4f676db811eea68ffa163e0fa374'


class RuleOptionTests(unittest.TestCase):
    def invoke(self, directory, source, rule, options=None, cli=()):
        config = Path(directory) / 'policy.json'
        config.write_text(json.dumps({'enabled_rules': [rule], 'fail_on': 'warning',
                                     'rules': {rule: {'options': options or {}}}}))
        run = subprocess.run([sys.executable, str(ROOT / 'scripts/check.py'), str(source),
                              '--config', str(config), *cli], text=True, capture_output=True)
        return run, json.loads(run.stdout) if run.stdout.startswith('{') else None

    def test_python_line_limit_is_applied_and_export_default_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'module.py'
            source.write_text('# ' + 'x' * 88 + '\n')
            default, _ = self.invoke(tmp, source, LINE)
            strict, report = self.invoke(tmp, source, LINE, {'max-line-length': 80})
        self.assertEqual(default.returncode, 0, default.stderr)
        self.assertEqual(strict.returncode, 1, strict.stderr)
        self.assertEqual(report['findings'][0]['column'], 81)
        coverage = report['rule_coverage'][0]
        self.assertEqual(coverage['options'][0]['optionValue'], '80')
        self.assertEqual(coverage['exported_options'][0]['optionValue'], '120')
        self.assertEqual(coverage['option_source'], 'project-config')

    def test_cli_option_overrides_project_without_mutating_catalog(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'module.py'
            source.write_text('# ' + 'x' * 88 + '\n')
            run, report = self.invoke(tmp, source, LINE, {'max-line-length': 80},
                                     ['--rule-option', LINE + ':max-line-length=100'])
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(report['rule_coverage'][0]['options'][0]['optionValue'], '100')
        original = next(e for e in json.loads((ROOT / 'rulesets/catalog.json').read_text())['rules'] if e['id'] == LINE)
        self.assertEqual(original['rule']['options'][0]['optionValue'], '120')

    def test_unknown_or_invalid_policy_cannot_silently_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'module.py'; source.write_text('value = 1\n')
            for options in ({'max-line-length': -1}, {'max-line-length': True},
                            {'max-line-length': 'abc'}, {'max-line-lenght': 80},
                            {'max-line-length': 1.5}):
                with self.subTest(options=options):
                    run, _ = self.invoke(tmp, source, LINE, options)
                    self.assertEqual(run.returncode, 2, run.stdout)
                    self.assertIn('option', run.stderr.lower())

    def test_java_exported_parameter_limit_works_through_cli(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'Example.java'
            source.write_text('class Example { void run(int first, int second, int third) {} }')
            run, report = self.invoke(tmp, source, JAVA_PARAMETERS, {'maxParameterNum': 2})
        self.assertEqual(run.returncode, 1, run.stderr)
        self.assertEqual([f['id'] for f in report['findings']], [JAVA_PARAMETERS])

    def test_typescript_exported_case_limit_works_through_cli(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'example.ts'
            source.write_text('declare const value: number; switch(value) { case 1: break; case 2: break; }')
            run, report = self.invoke(tmp, source, CASES, {'maximum': 1})
        self.assertIn(run.returncode, [1, 2], run.stderr)
        self.assertIsNotNone(report, run.stderr)
        self.assertEqual([f['id'] for f in report['findings']], [CASES])

    def test_malformed_rule_settings_return_config_error_without_traceback(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'module.py'; source.write_text('value = 1\n')
            for setting in ({'severity': []}, {'enabled': 'false'}, {'enabled': 0}):
                config = Path(tmp) / 'policy.json'
                config.write_text(json.dumps({'rules': {LINE: setting}}))
                run = subprocess.run([sys.executable, str(ROOT / 'scripts/check.py'),
                                      str(source), '--config', str(config)], capture_output=True, text=True)
                self.assertEqual(run.returncode, 2, run.stderr)
                self.assertNotIn('Traceback', run.stderr)
                self.assertIn('must be', run.stderr)

    def test_excel_preserves_effective_and_exported_policy(self):
        from scripts.xlsx_export import workbook_bytes
        try:
            from test_xlsx_export import sheet_values
        except ModuleNotFoundError:
            from tests.test_xlsx_export import sheet_values
        import io
        import zipfile
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'module.py'; source.write_text('# ' + 'x' * 88 + '\n')
            _, report = self.invoke(tmp, source, LINE, {'max-line-length': 80})
        with zipfile.ZipFile(io.BytesIO(workbook_bytes(report))) as archive:
            rows = sheet_values(archive, 4)
        coverage = dict(zip(rows[0], rows[1]))
        self.assertEqual(json.loads(coverage['options'])[0]['optionValue'], '80')
        self.assertEqual(json.loads(coverage['exported_options'])[0]['optionValue'], '120')
        self.assertEqual(coverage['option_source'], 'project-config')

    def test_loosened_limit_is_not_a_verified_repair(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'module.py'; source.write_text('# ' + 'x' * 88 + '\n')
            _, before = self.invoke(tmp, source, LINE, {'max-line-length': 80})
            _, after = self.invoke(tmp, source, LINE, {'max-line-length': 120})
        self.assertIsNotNone(before)
        delta = compare_reports(before, after)
        self.assertEqual(len(delta['unverified_resolutions']), 1)
        self.assertEqual(delta['resolved'], [])


if __name__ == '__main__':
    unittest.main()
