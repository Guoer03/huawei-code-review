"""Independent language-semantic regressions for implemented frontend rules."""
import json
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.catalog_frontend import scan,runtime_status

CASES=[
    ('destructured-binding.js','da73d6156db811eea68ffa163e0fa374',True,
     'const { bad_name } = {bad_name: 1};\n'),
    ('named-method.js','da73d4666db811eea68ffa163e0fa374',True,
     'class Service { Bad_Name() { return 1; } }\n'),
    ('caught-finally-throw.js','da73b7006db811eea68ffa163e0fa374',False,
     'try { work(); } finally { try { throw new Error("inner"); } catch (error) { recover(error); } }\n'),
    ('shadow-error.ts','da6b717b6db811eea68ffa163e0fa374',False,
     'class Error { constructor() {} }\nnew Error();\n'),
    ('required-undefined-placeholder.ts','da6c6b3c6db811eea68ffa163e0fa374',False,
     'function send(first: number = 1, second: number): void {}\nsend(undefined, 2);\n'),
]

class FrontendIndependentReviewTests(unittest.TestCase):
    def test_implemented_rules_handle_language_semantics(self):
        if not runtime_status()['available']:
            self.skipTest('frontend runtime unavailable; set HCR_NODE_MODULES')
        catalog=json.loads((ROOT/'rulesets/catalog.json').read_text())['rules']
        ids={rid for _,rid,_,_ in CASES}
        inputs=[('/virtual_hcr_independent/'+name,source) for name,_,_,source in CASES]
        report=scan(inputs,[e for e in catalog if e['id'] in ids])
        self.assertEqual(report['errors'],[])
        actual={(f['path'],f['id']) for f in report['findings']}
        for name,rid,expected,_ in CASES:
            with self.subTest(case=name,rule=rid):
                self.assertEqual(('/virtual_hcr_independent/'+name,rid) in actual,expected)

if __name__=='__main__':unittest.main()
