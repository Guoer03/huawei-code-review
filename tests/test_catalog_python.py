"""Executable CodeArts rule conformance examples and parser regressions."""
import json
from pathlib import Path
import sys
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.catalog_python import scan, rule_key
ENTRIES=[e for e in json.loads((ROOT/'rulesets/catalog.json').read_text())['rules'] if e['rule']['language']=='PYTHON']
CASES=json.loads((ROOT/'tests/catalog_cases/python.json').read_text())
class CatalogPythonTests(unittest.TestCase):
    def test_rule_examples(self):
        for c in CASES:
            with self.subTest(case=c['case_id']):
                entry=next(e for e in ENTRIES if e['id']==c['rule_id'])
                result=scan([('example.py',c['source'])],[entry])
                self.assertEqual(result['errors'],[])
                self.assertEqual(any(f['id']==c['rule_id'] for f in result['findings']),c['expect'])
    def test_invalid_python_is_uncovered(self):
        self.assertTrue(scan([('broken.py','def broken(:\n')],ENTRIES)['errors'])
    def test_comments_and_strings_do_not_execute_security_rules(self):
        result=scan([('example.py','"""yaml.load(data); eval(input()); subprocess.run(shell=True)."""\n# pickle.loads(input())\n')],ENTRIES)
        self.assertFalse([f for f in result['findings'] if f['title'].startswith(('G.EDV.','G.SER.'))])
    def findings_for(self, key, source):
        entry=next(e for e in ENTRIES if rule_key(e['rule'])==key)
        return scan([('sample.py',source)],[entry])['findings']
    def test_import_aliases_and_shadowed_bindings(self):
        self.assertTrue(self.findings_for('G.SER.03','from yaml import load as parse\nparse(data)\n'))
        self.assertFalse(self.findings_for('G.SER.03','import yaml\ndef f(yaml):\n    return yaml.load(data)\n'))
        self.assertFalse(self.findings_for('G.SER.03','import yaml\nyaml = custom_parser\nyaml.load(data)\n'))
    def test_mutable_default_constructor_shadow(self):
        self.assertFalse(self.findings_for('G.FNM.01','def dict():\n    return ()\ndef f(x=dict()):\n    return x\n'))
    def test_configured_line_limit_below_default(self):
        import copy
        entry=copy.deepcopy(next(e for e in ENTRIES if e['rule']['nameCn'].startswith('G.FMT.02 ')))
        entry['rule']['options'][0]['optionValue']='80'
        self.assertEqual(len(scan([('sample.py','x = "'+'a'*90+'"\n')],[entry])['findings']),1)
    def test_finally_inner_loop_break_is_not_abrupt_exit(self):
        self.assertFalse(self.findings_for('G.ERR.14','try:\n    work()\nfinally:\n    for item in items:\n        if item:\n            break\n'))
    def test_scope_boundaries_do_not_confuse_return_and_loop_captures(self):
        source='def outer():\n    def inner():\n        return "value"\n    return 1\n'
        self.assertFalse(self.findings_for('G.CTL.01',source))
        source='for i in items:\n    def f():\n        i = 1\n        return i\n'
        self.assertFalse(self.findings_for('G.FNM.02',source))
    def test_duplicate_equal_numeric_dict_keys_and_unhashable_key(self):
        self.assertTrue(self.findings_for('G.TYP.06','d = {1: "a", True: "b"}\n'))
        self.assertFalse(self.findings_for('G.TYP.06','d = {[1]: "a"}\n'))
    def test_mutable_lambda_default_and_imported_builtin(self):
        self.assertTrue(self.findings_for('G.FNM.01','f = lambda items=[]: items\n'))
        self.assertTrue(self.findings_for('G.FNM.01','from builtins import dict as mapping\ndef f(items=mapping()):\n    return items\n'))
        self.assertFalse(self.findings_for('G.FNM.01','f = lambda items=None: items\n'))
    def test_taint_respects_parameter_shadowing_and_reassignment(self):
        self.assertFalse(self.findings_for('G.EDV.01','payload = input()\ndef run(payload):\n    return eval(payload)\n'))
        self.assertFalse(self.findings_for('G.EDV.01','payload = input()\npayload = "1 + 1"\nresult = eval(payload)\n'))
        self.assertTrue(self.findings_for('G.EDV.01','def run():\n    payload = input()\n    return eval(payload)\n'))
    def test_exported_numeric_severity_is_not_guessed(self):
        finding=self.findings_for('G.FNM.01','def f(items=[]):\n    return items\n')[0]
        self.assertEqual(finding['raw_severity'],'1')
        self.assertEqual(finding['severity'],'warning')
        self.assertIn('local-policy',finding['severity_policy'])
    def test_real_project_keyword_and_default_spacing(self):
        source='def f(role=None, *, allow=True):\n    trace("中文", gaps=role, ready=allow)\n'
        self.assertFalse(self.findings_for('G.FMT.04',source))
    def test_dictionary_assignment_is_not_invalid_key_read(self):
        self.assertFalse(self.findings_for('G.TYP.07','plan = {}\nplan["items"] = values\n'))
    def test_nested_route_handler_uses_instance(self):
        source='class Server:\n    def routes(self):\n        def handler():\n            return self.result\n        return handler\n'
        self.assertFalse(self.findings_for('G.CLS.07',source))
    def test_unicode_location_is_character_column(self):
        finding=self.findings_for('G.FIO.03','import tempfile\n中文 = tempfile.mktemp()\n')[0]
        self.assertEqual(finding['column'],6)
    def test_four_space_indent_means_each_block_increment(self):
        self.assertTrue(self.findings_for('G.FMT.01','if ready:\n        work()\n'))
        self.assertFalse(self.findings_for('G.FMT.01','if (ready\n        and available):\n    work()\n'))
    def test_mutable_default_comprehensions_and_bound_alias(self):
        self.assertTrue(self.findings_for('G.FNM.01','DEFAULT = []\ndef f(items=DEFAULT):\n    return items\n'))
        self.assertTrue(self.findings_for('G.FNM.01','def f(items=[x for x in range(3)]):\n    return items\n'))
        self.assertFalse(self.findings_for('G.FNM.01','DEFAULT = ()\ndef f(items=DEFAULT):\n    return items\n'))
    def test_utf8_bom_does_not_cause_parse_failure(self):
        source='\ufeffdef f(items=[]):\n    return items\n'
        result=scan([('bom.py',source)],ENTRIES)
        self.assertEqual(result['errors'],[])
        finding=next(f for f in result['findings'] if f['id']=='da6b2b5d6db811eea68ffa163e0fa374')
        self.assertEqual(finding['line'],1)
        self.assertEqual(finding['column'],13)
    def test_manifest_has_every_catalog_rule_and_test_evidence(self):
        rows=json.loads((ROOT/'rulesets/implementations/python.json').read_text())
        self.assertEqual({r['rule_id'] for r in rows},{e['id'] for e in ENTRIES})
        for row in rows:
            if row['status'] in ('implemented','partial'):
                self.assertGreaterEqual(len(row['test_cases']),2,row['rule_id'])
                self.assertTrue(all(any(c['case_id']==name for c in CASES) for name in row['test_cases']))
if __name__=='__main__':unittest.main()
