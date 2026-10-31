"""Catalog checks use genuine javac syntax trees and per-rule counterexamples."""
import json
import sys
import unittest
from unittest.mock import patch
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import catalog_java


class JavaCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entries = [e for e in json.loads((ROOT / 'rulesets/catalog.json').read_text())['rules'] if e['rule']['language'] == 'JAVA']
        cls.cases = json.loads((ROOT / 'tests/catalog_cases/java.json').read_text())
        files = []
        for i, case in enumerate(cls.cases):
            files += [(f'case_{i}_bad.java', case['bad']), (f'case_{i}_good.java', case['good'])]
        cls.result = catalog_java.scan(files, cls.entries)

    def test_all_cases_parse_without_errors(self):
        expected = {f'case_{i}_bad.java' for i, c in enumerate(self.cases) if c.get('expect_error')}
        self.assertEqual(expected, {e['path'] for e in self.result['errors']})

    def test_rule_positive_and_negative_cases(self):
        for i, case in enumerate(self.cases):
            with self.subTest(rule=case['rule_id'], name=case.get('name')):
                bad = [f for f in self.result['findings'] if f['path'] == f'case_{i}_bad.java' and f['id'] == case['rule_id']]
                good = [f for f in self.result['findings'] if f['path'] == f'case_{i}_good.java' and f['id'] == case['rule_id']]
                if case.get('expect_error'):
                    self.assertTrue([e for e in self.result['errors'] if e['path'] == f'case_{i}_bad.java'])
                else:
                    self.assertTrue(bad, 'missing violation')
                self.assertEqual([], good, 'false positive on compliant counterpart')

    def test_manifest_covers_every_original_rule(self):
        manifest = json.loads((ROOT / 'rulesets/implementations/java.json').read_text())
        self.assertEqual({e['id'] for e in self.entries}, {e['rule_id'] for e in manifest})
        tested = {case['rule_id'] for case in self.cases}
        for rule in manifest:
            if rule['status'] in {'implemented', 'partial'}:
                self.assertIn(rule['rule_id'], tested)
                self.assertTrue(rule['test_cases'])

    def test_syntax_failure_is_reported(self):
        result = catalog_java.scan([('Broken.java', 'class Broken { void f( {')], self.entries)
        self.assertTrue(result['errors'])

    def test_comments_strings_and_shadowed_system_are_not_calls(self):
        source = 'class Other { void exit(int x) {} } class C { void f(Other System) { String s = "😀 System.exit(0);"; System.exit(0); /* System.gc(); */ } }'
        result = catalog_java.scan([('C.java', source)], self.entries)
        forbidden = {'da66e8186db811eea68ffa163e0fa374', 'da756c086db811eea68ffa163e0fa374'}
        self.assertFalse([f for f in result['findings'] if f['id'] in forbidden])

    def test_missing_jdk_never_reports_clean(self):
        with patch.object(catalog_java, '_java', return_value=None):
            result = catalog_java.scan([('C.java', 'class C {}')], self.entries)
        self.assertTrue(result['errors'])
        self.assertEqual([], result['findings'])

    def test_unicode_offsets_match_original_source(self):
        source = 'class C { void f() { String emoji="😀"; System.exit(0); } }'
        result = catalog_java.scan([('C.java', source)], self.entries)
        findings = [f for f in result['findings'] if f['id']=='da66e8186db811eea68ffa163e0fa374']
        self.assertEqual(1, len(findings))
        self.assertEqual(source.index('System.exit') + 1, findings[0]['column'])

    def test_java_line_width_boundary_is_120_characters(self):
        rule_id = 'da72deaa6db811eea68ffa163e0fa374'
        at_limit = 'class C { // ' + 'x' * (120 - len('class C { // ')) + '\n}'
        over_limit = 'class C { // ' + 'x' * (121 - len('class C { // ')) + '\n}'
        self.assertEqual(120, len(at_limit.splitlines()[0]))
        self.assertEqual(121, len(over_limit.splitlines()[0]))
        at_result = catalog_java.scan([('AtLineLimit.java', at_limit)], self.entries)
        over_result = catalog_java.scan([('OverLineLimit.java', over_limit)], self.entries)
        self.assertEqual([], [f for f in at_result['findings'] if f['id'] == rule_id])
        self.assertEqual(1, len([f for f in over_result['findings'] if f['id'] == rule_id]))

    def test_method_length_counts_signature_and_skips_comments_blank_lines(self):
        rule_id = 'da748cd96db811eea68ffa163e0fa374'
        prefix = 'class C {\n    void f(\n        int a,\n        int b) {\n'
        suffix = '        String text = "// not a comment";\n    }\n}\n'
        # 3 signature/opening lines + 45 statements + text line + closing method line = 50.
        ignored = '\n        // comment-only line is not effective\n'
        at_limit = prefix + ignored + ''.join(f'        int value{i}=0;\n' for i in range(45)) + suffix
        # 3 signature/opening lines + 46 statements + text line + closing method line = 51.
        over_limit = prefix + ignored + ''.join(f'        int value{i}=0;\n' for i in range(46)) + suffix
        at_result = catalog_java.scan([('AtLimit.java', at_limit)], self.entries)
        over_result = catalog_java.scan([('OverLimit.java', over_limit)], self.entries)
        self.assertEqual([], [f for f in at_result['findings'] if f['id'] == rule_id])
        self.assertEqual(1, len([f for f in over_result['findings'] if f['id'] == rule_id]))

    def test_member_order_requires_blank_line_between_categories(self):
        rule_id = 'da7268e26db811eea68ffa163e0fa374'
        source = 'class C {\n    int value;\n    void f() {}\n}\n'
        result = catalog_java.scan([('C.java', source)], self.entries)
        self.assertEqual(1, len([f for f in result['findings'] if f['id'] == rule_id]))

        source = 'class C {\n    int value;\n\n    void f() {}\n}\n'
        result = catalog_java.scan([('C.java', source)], self.entries)
        self.assertEqual([], [f for f in result['findings'] if f['id'] == rule_id])

    def test_declaration_proximity_covers_nonliteral_initializers(self):
        rule_id = 'da6f97d26db811eea68ffa163e0fa374'
        source = 'class C { void f(int input) { int value=input;\nf();\nf();\nf();\nf();\nconsume(value); } }'
        result = catalog_java.scan([('C.java', source)], self.entries)
        self.assertEqual(1, len([f for f in result['findings'] if f['id'] == rule_id]))

    def test_throws_documentation_requires_condition_description(self):
        rule_id = 'da7051436db811eea68ffa163e0fa374'
        bad = 'class C { /** Runs.\n * @throws IllegalStateException\n */\nvoid f(int value) throws IllegalStateException {} }'
        good = 'class C { /** Runs.\n * @throws IllegalStateException when the input is negative\n */\nvoid f(int value) throws IllegalStateException {} }'
        bad_result = catalog_java.scan([('Bad.java', bad)], self.entries)
        good_result = catalog_java.scan([('Good.java', good)], self.entries)
        self.assertEqual(1, len([f for f in bad_result['findings'] if f['id'] == rule_id]))
        self.assertEqual([], [f for f in good_result['findings'] if f['id'] == rule_id])

    def test_float_wrapper_equals_and_compare_to_zero_are_rejected(self):
        rule_id = 'da7320a16db811eea68ffa163e0fa374'
        sources = [
            'class C { boolean f(Float a,Float b) { return a.equals(b); } }',
            'class C { boolean f(Double a,Double b) { return a.compareTo(b)==0; } }',
            'class C { boolean f(Double a,Double b) { return 0==a.compareTo(b); } }',
        ]
        for source in sources:
            result = catalog_java.scan([('C.java', source)], self.entries)
            self.assertEqual(1, len([f for f in result['findings'] if f['id'] == rule_id]), source)

    def test_exported_threshold_option_is_respected(self):
        entries = json.loads(json.dumps(self.entries))
        rule = next(e for e in entries if e['id']=='da7497676db811eea68ffa163e0fa374')
        rule['rule']['options'][0]['optionValue']='1'
        result = catalog_java.scan([('C.java','class C { void f(int a,int b) {} }')], entries)
        self.assertTrue([f for f in result['findings'] if f['id']==rule['id']])

    def test_bad_source_does_not_hide_other_file_findings(self):
        result=catalog_java.scan([('Bad.java','class Bad {'),('C.java','class C { void f() { System.exit(0); } }')], self.entries)
        self.assertTrue([e for e in result['errors'] if e['path']=='Bad.java'])
        self.assertTrue([f for f in result['findings'] if f['path']=='C.java' and f['id']=='da66e8186db811eea68ffa163e0fa374'])

    def test_sanitizer_is_sink_scoped_not_global(self):
        # escapeHtml neutralizes the XSS sink but must NOT neutralize a path sink.
        source='class C { void f() { String value=request.getParameter("q"); String s=StringEscapeUtils.escapeHtml(value); new File(s); } }'
        result=catalog_java.scan([('C.java',source)], self.entries)
        path='da6baaea6db811eea68ffa163e0fa374'
        self.assertTrue([f for f in result['findings'] if f['path']=='C.java' and f['id']==path],
                        'escapeHtml must not silence the unrelated file-path sink')

    def test_reassignment_to_non_sanitizer_clears_neutralization(self):
        # A sanitized binding that is later reassigned to fresh tainted input must report again.
        source=('class C { void f() { String value=request.getParameter("q"); '
                'String s=StringEscapeUtils.escapeHtml(value); '
                's=request.getParameter("r"); response.getWriter().write(s); } }')
        result=catalog_java.scan([('C.java',source)], self.entries)
        xss='da76fab36db811eea68ffa163e0fa374'
        self.assertTrue([f for f in result['findings'] if f['path']=='C.java' and f['id']==xss],
                        'reassigning a sanitized binding to fresh tainted input must restore the finding')


if __name__ == '__main__':
    unittest.main()
