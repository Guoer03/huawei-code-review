"""Independent Java type-name, control-flow, offset and option regressions."""
import copy
import json
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.catalog_java import scan

SYSTEM='da66e8186db811eea68ffa163e0fa374'
THREAD_NEW='da7538686db811eea68ffa163e0fa374'
THREAD_RUN='da66a3866db811eea68ffa163e0fa374'
FINALLY='da7086536db811eea68ffa163e0fa374'
FINALLY_THROW='da66d7b66db811eea68ffa163e0fa374'
LOCALE='da746c2d6db811eea68ffa163e0fa374'
PARAMETERS='da7497676db811eea68ffa163e0fa374'
NESTING='da651d776db811eea68ffa163e0fa374'


class CatalogJavaReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entries=[e for e in json.loads((ROOT/'rulesets/catalog.json').read_text())['rules'] if e['rule']['language']=='JAVA']
        cls.cases={
            'LocalSystem.java':('class System { static void exit(int code) {} } class C { void run() { System.exit(0); java.lang.System.exit(0); } }',SYSTEM,1),
            'LocalThread.java':('class Thread { void run() {} } class C { void run(Thread local, java.lang.Thread actual) { local.run(); actual.run(); new Thread(); new java.lang.Thread(); } }',THREAD_RUN,1),
            'LocalString.java':('class String { String toLowerCase() { return this; } } class C { void run(String local, java.lang.String actual) { local.toLowerCase(); actual.toLowerCase(); } }',LOCALE,1),
            'FinallyLoop.java':('class C { void run() { try {} finally { for (int i = 0; i < 3; i++) { if (i == 1) break; if (i == 2) continue; } } } }',FINALLY,0),
            'FinallyCaught.java':('class C { void run() { try {} finally { try { throw new IllegalStateException(); } catch (IllegalStateException caught) { } } } }',FINALLY_THROW,0),
            'FinallyEscapes.java':('class C { void run() { try {} finally { throw new IllegalStateException(); } } }',FINALLY_THROW,1),
            'UnicodeOffset.java':('class C { void run() { java.lang.String text = "😀🦄中文"; java.lang.System.exit(0); } }',SYSTEM,1),
        }
        ids={c[1] for c in cls.cases.values()}|{THREAD_NEW}
        cls.result=scan([(name,source) for name,(source,_,_) in cls.cases.items()],[e for e in cls.entries if e['id'] in ids])

    def test_independent_semantic_counterexamples(self):
        self.assertEqual(self.result['errors'],[])
        for name,(_,rid,count) in self.cases.items():
            with self.subTest(source=name,rule=rid):
                self.assertEqual(len([f for f in self.result['findings'] if f['path']==name and f['id']==rid]),count)

    def test_local_thread_constructor_is_not_jdk_thread(self):
        self.assertEqual(len([f for f in self.result['findings'] if f['path']=='LocalThread.java' and f['id']==THREAD_NEW]),1)

    def test_string_api_targets_real_jdk_receiver_not_local_class(self):
        source=self.cases['LocalString.java'][0]
        found=[f for f in self.result['findings'] if f['path']=='LocalString.java' and f['id']==LOCALE]
        self.assertEqual([f['column'] for f in found],[source.index('actual.toLowerCase')+1])

    def test_emoji_offsets_are_original_character_columns(self):
        source=self.cases['UnicodeOffset.java'][0]
        found=next(f for f in self.result['findings'] if f['path']=='UnicodeOffset.java' and f['id']==SYSTEM)
        self.assertEqual(found['column'],source.index('java.lang.System.exit')+1)

    def test_exported_parameter_threshold_exact_boundary(self):
        entries=copy.deepcopy([e for e in self.entries if e['id']==PARAMETERS])
        entries[0]['rule']['options'][0]['optionValue']='2'
        result=scan([('At.java','class At { void run(int a, int b) {} }'),('Over.java','class Over { void run(int a, int b, int c) {} }')],entries)
        self.assertEqual(result['errors'],[])
        self.assertEqual([f['path'] for f in result['findings']],['Over.java'])

    def test_zero_nesting_threshold_is_not_replaced_by_default(self):
        entries=copy.deepcopy([e for e in self.entries if e['id']==NESTING])
        entries[0]['rule']['options'][0]['optionValue']='0'
        result=scan([('At.java','class At { void run() {} }'),('Over.java','class Over { void run(boolean condition) { if (condition) {} } }')],entries)
        self.assertEqual(result['errors'],[])
        self.assertEqual([f['path'] for f in result['findings']],['Over.java'])

if __name__=='__main__':unittest.main()
