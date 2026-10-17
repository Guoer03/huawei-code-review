"""Regression cases reduced from actual project scans, plus positive controls."""
from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from engine import check
from config import Config


class PythonRealProjectRegressionTests(unittest.TestCase):
    def scan(self, text):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'app.py'
            path.write_text(text)
            return check([str(path)], config=Config(ruleset="legacy"))

    def test_embedded_scripts_are_not_host_import_statements(self):
        report = self.scan("READ_SCRIPT = r'''\nimport json, os, sys, time\n'''\n")
        self.assertFalse(report['findings'])
        self.assertFalse(report['uncovered'])

    def test_actual_multi_module_import_remains_detected(self):
        report = self.scan('import json, os, sys, time\n')
        self.assertIn('HUAWEI-PY-IMPORT-001', {f['id'] for f in report['findings']})

    def test_bad_function_name_in_docstring_is_not_code(self):
        report = self.scan("'''\ndef BadExample():\n    pass\n'''\n")
        self.assertFalse(report['findings'])

    def test_actual_bad_function_name_keeps_original_location(self):
        report = self.scan("# example\ndef BadExample():\n    pass\n")
        finding = next(f for f in report['findings'] if f['id'] == 'HUAWEI-PY-STYLE-001')
        self.assertEqual(finding['line'], 2)

    def test_incomplete_string_cannot_produce_clean_result(self):
        report = self.scan("value = '''unfinished\n")
        self.assertTrue(report['uncovered'])
        self.assertFalse(report['summary']['pass'])


if __name__ == '__main__':
    unittest.main()
