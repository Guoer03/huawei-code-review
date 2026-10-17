"""Java regressions discovered by scanning real production source."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.java_checks import java_rule_positions

BRACES = "HUAWEI-JAVA-FORMAT-002"
SWITCH = "HUAWEI-JAVA-SWITCH-001"


class JavaChecksTests(unittest.TestCase):
    def positions(self, source):
        return java_rule_positions(source)

    def test_nested_calls_with_existing_braces(self):
        source = "if (!requiresWriteKey(request) || hasValidWriteKey(request)) { return; }"
        self.assertEqual(self.positions(source)[BRACES], [])

    def test_multiline_condition_and_comment_before_brace(self):
        source = "if (\n    exists(user.id())\n) /* body starts next line */\n{ return; }"
        self.assertEqual(self.positions(source)[BRACES], [])

    def test_for_enhanced_for_and_while_calls_with_braces(self):
        source = '''for (int i = 0; i < sorted.size(); i++) { use(i); }
for (Cookie cookie : request.getCookies()) { use(cookie); }
while ((read = stream.read(buffer)) != -1) { count += read; }'''
        self.assertEqual(self.positions(source)[BRACES], [])

    def test_unbraced_if_still_reports_actual_keyword_position(self):
        source = "  if (isReady(call()))\n    run();"
        self.assertEqual(self.positions(source)[BRACES], [(1, 3)])

    def test_all_supported_unbraced_loops_remain_positive(self):
        source = "for (int i=0; i<size(); i++) run();\nfor (Item x : items()) run();\nwhile (ready()) run();"
        self.assertEqual(self.positions(source)[BRACES], [(1, 1), (2, 1), (3, 1)])

    def test_nested_unbraced_if_reports_each_body(self):
        self.assertEqual(self.positions("if (a) if (b) run();")[BRACES], [(1, 1), (1, 8)])

    def test_brace_inside_comment_does_not_hide_violation(self):
        self.assertEqual(self.positions("if (ready()) /* { */ run();")[BRACES], [(1, 1)])

    def test_comments_strings_chars_and_text_blocks_are_ignored(self):
        source = '''// if (a) run(); case 1:
/* while (a) run(); */
String a = "if (ready()) run(); case X:";
char quote = '\\'';
String block = """
if (a) run(); case X:
""";
if (a.equals("})") && quote != '(') { run(); }'''
        self.assertEqual(self.positions(source), {BRACES: [], SWITCH: []})

    def test_arrow_switch_method_references_are_not_colon_cases(self):
        source = '''return switch (sortField) {
    case TOKEN_USAGE -> longMetricComparator(RankRow::tokenUsage, sortOrder);
    case SUBMISSION_COUNT -> longMetricComparator(RankRow::submissionCount, sortOrder);
    case SCORE -> scoreComparator(sortOrder);
};'''
        self.assertEqual(self.positions(source), {BRACES: [], SWITCH: []})

    def test_arrow_case_throw_colon_text_is_ignored(self):
        source = 'switch (x) { case 1 -> throw new IllegalArgumentException("bad: input"); }'
        self.assertEqual(self.positions(source)[SWITCH], [])

    def test_classic_case_is_review_candidate_even_with_break(self):
        source = "switch (x) {\n  case 1: work(); break;\n  case 2: return;\n}"
        self.assertEqual(self.positions(source)[SWITCH], [(2, 3), (3, 3)])

    def test_char_colon_case_and_comment_colon(self):
        source = "switch (c) { case ':' /* -> */ : break; }"
        self.assertEqual(self.positions(source)[SWITCH], [(1, 14)])

    def test_case_ternary_and_nested_parentheses(self):
        source = "switch (n) { case (true ? 1 : 2): break; }"
        self.assertEqual(self.positions(source)[SWITCH], [(1, 14)])

    def test_do_while_tail_with_braced_body_is_not_new_loop_body(self):
        source = "do { if (ready()) { run(); } } while (keepGoing());"
        self.assertEqual(self.positions(source)[BRACES], [])

    def test_incomplete_header_does_not_invent_a_finding(self):
        self.assertEqual(self.positions("if (ready(\n"), {BRACES: [], SWITCH: []})


if __name__ == "__main__":
    unittest.main()
