"""Dependency gaps invalidate affected checks without hiding successful syntax scans."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.engine import check, exit_code
from scripts.config import Config
from scripts.compare_reports import compare_reports
from scripts import catalog_python

MUTABLE = 'da6b2b5d6db811eea68ffa163e0fa374'
OVERRIDE = 'da6bbffc6db811eea68ffa163e0fa374'


class AnalysisErrorScopeTests(unittest.TestCase):
    def setup_source(self, directory, bad=True):
        root = Path(directory)
        source = root / 'code.py'
        source.write_text('def collect(items=' + ('[]' if bad else 'None') + '):\n    return items\n')
        (root / 'context.py').write_text('from vendor import Base\nclass Child(Base):\n    def method(self):\n        pass\n')
        return root

    def scan(self, root):
        return check([str(root)], config=Config(enabled_rules=[MUTABLE, OVERRIDE], fail_on='warning'))

    def test_missing_external_base_does_not_invalidate_mutable_default_check(self):
        with tempfile.TemporaryDirectory() as directory:
            report = self.scan(self.setup_source(directory))
        rows = {r['rule_id']: r for r in report['rule_coverage']}
        self.assertEqual(rows[MUTABLE]['execution_status'], 'completed')
        self.assertEqual(rows[MUTABLE]['coverage_status'], 'covered')
        self.assertEqual(rows[OVERRIDE]['execution_status'], 'error')
        self.assertTrue(any(OVERRIDE in e.get('affected_rule_ids', []) for e in report['uncovered']))
        self.assertFalse(report['coverage_summary']['complete'])
        self.assertEqual(exit_code(report, 'warning'), 2)

    def test_same_scope_repair_of_unaffected_rule_is_verifiable_with_dependency_gap(self):
        with tempfile.TemporaryDirectory() as directory:
            before = self.scan(self.setup_source(directory))
            after = self.scan(self.setup_source(directory, bad=False))
        delta = compare_reports(before, after)
        self.assertEqual([f['id'] for f in delta['resolved']], [MUTABLE])
        self.assertEqual(delta['unverified_resolutions'], [])
        self.assertEqual(exit_code(after, 'warning'), 2)

    def test_excel_discloses_which_rules_need_missing_context(self):
        import io
        import zipfile
        from scripts.xlsx_export import workbook_bytes
        try:
            from test_xlsx_export import sheet_values
        except ModuleNotFoundError:
            from tests.test_xlsx_export import sheet_values
        with tempfile.TemporaryDirectory() as directory:
            report = self.scan(self.setup_source(directory))
        with zipfile.ZipFile(io.BytesIO(workbook_bytes(report))) as archive:
            rows = sheet_values(archive, 3)
        entries = [dict(zip(rows[0], row)) for row in rows[1:]]
        context = next(row for row in entries if 'vendor' in row['reason'])
        self.assertEqual(json.loads(context['affected_rule_ids']), [OVERRIDE])

    def test_parse_failure_still_invalidates_all_selected_rules(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.setup_source(directory)
            (root / 'syntax_error.py').write_text('def broken(:\n')
            report = self.scan(root)
        self.assertTrue(all(r['execution_status'] == 'error' for r in report['rule_coverage']))
        self.assertEqual(report['findings'][0]['coverage_status'], 'error')
        self.assertEqual(exit_code(report, 'warning'), 2)

    def test_invalid_scope_from_analyzer_fails_closed(self):
        # Analyzer protocol robustness: bad metadata must never turn errors into passes.
        with tempfile.TemporaryDirectory() as directory:
            root = self.setup_source(directory)
            for invalid in ([], ['invented-rule'], [MUTABLE, 'invented-rule'], 'all', [None]):
                result = {'findings': [], 'errors': [{'path': str(root / 'context.py'),
                          'reason': 'missing context', 'affected_rule_ids': invalid}]}
                with self.subTest(scope=invalid), patch.object(catalog_python, 'scan', return_value=result):
                    report = self.scan(root)
                self.assertTrue(all(r['execution_status'] == 'error' for r in report['rule_coverage']))
                self.assertEqual(exit_code(report, 'warning'), 2)


if __name__ == '__main__':
    unittest.main()
