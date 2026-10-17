"""Control-flow regressions using the real javac parser, not synthetic ASTs."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.catalog_java import scan, _java

ABRUPT='da7086536db811eea68ffa163e0fa374'
THROW='da66d7b66db811eea68ffa163e0fa374'
RETURN='da66cd7c6db811eea68ffa163e0fa374'
FALL='da727db76db811eea68ffa163e0fa374'
DEFAULT='da650cfd6db811eea68ffa163e0fa374'


def method(body):return 'class C { void f(boolean flag,int value) { '+body+' } }'
def sw(body):return method('switch(value) { '+body+' }')


class JavaControlFlowTests(unittest.TestCase):
    CASES={
        'branch_returns':(sw('case 0: if(flag) { return; } else { return; } case 1: break; default: break;'),FALL,0),
        'branch_may_complete':(sw('case 0: if(flag) { return; } case 1: break; default: break;'),FALL,1),
        'nested_block_break':(sw('case 0: { if(flag) { break; } else { break; } } case 1: break; default: break;'),FALL,0),
        'endless_loop':(sw('case 0: while(true) { if(flag) { return; } } case 1: break; default: break;'),FALL,0),
        'endless_loop_with_break':(sw('case 0: while(true) { if(flag) { break; } } case 1: break; default: break;'),FALL,1),
        'conditional_constant_loop':(sw('case 0: while(1 < 2) { } case 1: break; default: break;'),FALL,0),
        'nested_switch_exhaustive':(sw('case 0: switch(value) { case 7: return; default: return; } case 1: break; default: break;'),FALL,0),
        'nested_switch_incomplete':(sw('case 0: switch(value) { case 7: return; } case 1: break; default: break;'),FALL,1),
        'nested_switch_constant_exhaustive':(method('switch(value) { case 0: switch(0) { case 0: return; } case 1: break; default: break; }'),FALL,0),
        'try_catch_returns':(sw('case 0: try { throw new IllegalArgumentException(); } catch(IllegalArgumentException e) { return; } case 1: break; default: break;'),FALL,0),
        'try_catch_swallows':(sw('case 0: try { throw new IllegalArgumentException(); } catch(IllegalArgumentException e) {} case 1: break; default: break;'),FALL,1),
        'finally_return_blocks_fallthrough':(sw('case 0: try { use(); } finally { return; } case 1: break; default: break;'),FALL,0),
        'finally_loop_cancels_return':(sw('case 0: label: { try { return; } finally { break label; } } case 1: break; default: break;'),FALL,1),
        'lambda_return_is_not_outer':(sw('case 0: Runnable task=() -> { return; }; case 1: break; default: break;'),FALL,1),
        'nested_finally_return_overridden':(method('try {} finally { label: { try { return; } finally { break label; } } }'),RETURN,0),
        'nested_finally_throw_overridden':(method('try {} finally { label: { try { throw new IllegalStateException(); } finally { break label; } } }'),THROW,0),
        'nested_finally_rethrows':(method('try {} finally { try { throw new IllegalArgumentException(); } finally { throw new IllegalStateException(); } }'),THROW,1),
        'unreachable_return':(method('try {} finally { if(false) { return; } }'),ABRUPT,0),
        'out_of_scope_constant_does_not_hide_field_return':('class C { boolean active; void f() { try {} finally { { final boolean active=false; } if(active) { return; } } } }',RETURN,1),
        'char_numeric_comparison_preserves_return':(method("try {} finally { if('a' == 97) { return; } }"),RETURN,1),
        'numeric_promotion_preserves_return':(method('try {} finally { if(9007199254740993L == 9007199254740992d) { return; } }'),RETURN,1),
        'integer_unary_overflow_preserves_return':(method('try {} finally { if(-(-2147483648) < 0) { return; } }'),RETURN,1),
        'boxed_final_identity_not_folded_by_value':(method('try {} finally { final Integer left=128; final Integer right=128; if(left != right) { return; } }'),RETURN,1),
        'unknown_exception_hierarchy_keeps_explicit_throw':('import external.CustomProblem; class C { void f() { try {} finally { try { throw new CustomProblem(); } catch(IllegalArgumentException caught) {} } } }',THROW,1),
        'out_of_scope_exception_does_not_hide_field_throw':('class C { Error problem; void f() { try {} finally { { final RuntimeException problem=new RuntimeException(); } try { throw problem; } catch(RuntimeException caught) {} } } }',THROW,1),
        'resource_initializer_exception_reaches_catch_return':('class C { AutoCloseable acquire() throws Exception { return null; } void f() { try {} finally { try(AutoCloseable resource=acquire()) {} catch(Exception failure) { return; } } } }',RETURN,1),
        'field_dereference_exception_reaches_catch_return':('class C { int value; void f(C other) { try {} finally { try { int result=other.value; } catch(NullPointerException failure) { return; } } } }',RETURN,1),
        'unboxing_exception_reaches_catch_return':('class C { void f(Boolean value) { try {} finally { try { if(value) {} } catch(NullPointerException failure) { return; } } } }',RETURN,1),
        'resource_close_exception_reaches_catch_return':('class C { void f(AutoCloseable resource) { try {} finally { try(resource) {} catch(Exception failure) { return; } } } }',RETURN,1),
        'local_labeled_continue':(method('try {} finally { inner: for(int i=0;i<3;i++) { continue inner; } }'),ABRUPT,0),
        'outer_labeled_continue':(method('outer: for(int i=0;i<3;i++) { try {} finally { continue outer; } }'),ABRUPT,1),
        'local_labeled_break':(method('try {} finally { inner: { if(flag) { break inner; } } }'),ABRUPT,0),
        'outer_labeled_break':(method('outer: { try {} finally { break outer; } }'),ABRUPT,1),
        'catch_superclass':('class Problem extends RuntimeException {} '+method('try {} finally { try { throw new Problem(); } catch(RuntimeException e) {} }'),THROW,0),
        'catch_rethrows':(method('try {} finally { try { throw new IllegalArgumentException(); } catch(IllegalArgumentException e) { throw e; } }'),THROW,1),
        'throw_in_catch_not_caught_by_sibling':(method('try {} finally { try { throw new IllegalArgumentException(); } catch(IllegalArgumentException e) { throw new IllegalStateException(); } catch(RuntimeException e) {} }'),THROW,1),
        'throw_expression_lambda_ignored':(method('try {} finally { Runnable task=() -> { throw new IllegalArgumentException(); }; }'),THROW,0),
        'fallthrough_comment_in_block':(sw('case 0: { use(); /* fall-through */ } case 1: break; default: break;'),FALL,0),
        'fallthrough_string_not_comment':(sw('case 0: use("fall-through"); case 1: break; default: break;'),FALL,1),
        'arrow_case_no_fallthrough':(sw('case 0 -> { use(); } case 1 -> { use(); } default -> {}'),FALL,0),
        'pattern_case_is_not_default':('class C { void f(Object value) { switch(value) { case String text -> use(text); } } }',DEFAULT,1),
        'null_and_default':('class C { void f(Object value) { switch(value) { case String text -> use(text); case null, default -> {} } } }',DEFAULT,0),
        'default_keyword_string':('class C { void f(String value) { switch(value) { case "default": break; } } }',DEFAULT,1),
        'switch_expression_throw_from_return':('class C { int f(int value) { try { return 0; } finally { return switch(0) { case 1 -> 1; default -> throw new IllegalStateException(); }; } } }',RETURN,0),
        'switch_expression_yield_in_loop':(method('try {} finally { int result=switch(value) { default -> { while(true) { yield 1; } } }; if(flag) { return; } }'),RETURN,1),
        'expression_throw_prevents_following_return':(method('try {} finally { int result=switch(0) { case 1 -> 1; default -> throw new IllegalStateException(); }; return; }'),RETURN,0),
        'catch_custom_exception_name':('class Problem extends RuntimeException {} '+method('try {} finally { try { throw new Problem(); } catch(Exception e) {} }'),THROW,0),
        'catch_custom_non_exception_name':('class Disaster extends Error {} '+method('try {} finally { try { throw new Disaster(); } catch(Exception e) {} }'),THROW,1),
        'throwing_switch_expression_fallthrough':(sw('case 0: int result=switch(0) { case 1 -> 1; default -> throw new IllegalStateException(); }; case 1: break; default: break;'),FALL,0),
        'multi_catch_covers_subtype':(method('try {} finally { try { throw new NumberFormatException(); } catch(IllegalArgumentException | IllegalStateException e) {} }'),THROW,0),
        'do_while_returns':(sw('case 0: do { return; } while(flag); case 1: break; default: break;'),FALL,0),
        'do_while_break_completes':(sw('case 0: do { break; } while(true); case 1: break; default: break;'),FALL,1),
        'labeled_infinite_continue':(sw('case 0: outer: while(true) { continue outer; } case 1: break; default: break;'),FALL,0),
        'nested_finally_conditionally_preserves_return':('class C { int f(boolean flag) { try { return 0; } finally { label: { try { return 1; } finally { if(flag) { break label; } } } } } }',RETURN,1),
        'throwing_condition_prevents_return':(method('try {} finally { if(switch(0) { case 1 -> true; default -> throw new IllegalStateException(); }) { return; } }'),RETURN,0),
        'throwing_loop_init_prevents_return':(method('try {} finally { for(int i=switch(0) { case 1 -> 1; default -> throw new IllegalStateException(); };flag;) { return; } }'),RETURN,0),
        'throwing_switch_selector_prevents_return':(method('try {} finally { switch(switch(0) { case 1 -> 1; default -> throw new IllegalStateException(); }) { default: return; } }'),RETURN,0),
        'throwing_monitor_prevents_return':(method('try {} finally { synchronized(switch(0) { case 1 -> new Object(); default -> throw new IllegalStateException(); }) { return; } }'),RETURN,0),
    }

    @classmethod
    def setUpClass(cls):
        entries=[e for e in json.loads((ROOT/'rulesets/catalog.json').read_text())['rules'] if e['id'] in {ABRUPT,THROW,RETURN,FALL,DEFAULT}]
        cls.result=scan([(name+'.java',value[0]) for name,value in cls.CASES.items()],entries)

    def test_all_fixtures_parse(self):self.assertEqual([],self.result['errors'])

    def test_structured_completion_and_target_resolution(self):
        for name,(_,rule,count) in self.CASES.items():
            with self.subTest(case=name):
                found=[f for f in self.result['findings'] if f['path']==name+'.java' and f['id']==rule]
                self.assertEqual(count,len(found),found)

    def test_overridden_throw_reports_only_surviving_source_location(self):
        source=self.CASES['nested_finally_rethrows'][0]
        found=[f for f in self.result['findings'] if f['path']=='nested_finally_rethrows.java' and f['id']==THROW]
        self.assertEqual([source.index('throw new IllegalStateException')+1],[f['column'] for f in found])

    def test_control_flow_fixtures_are_semantically_valid_java(self):
        # Compile only isolated synthetic test fixtures, never scanned project
        # source. This catches impossible control-flow examples that parse-only
        # checks would otherwise accept. No annotation processors or code run.
        executable=_java()
        self.assertIsNotNone(executable)
        javac=Path(executable).with_name('javac')
        if not javac.is_file():self.skipTest('JDK javac executable not adjacent to selected java')
        with tempfile.TemporaryDirectory(prefix='huawei-control-flow-test-') as directory:
            root=Path(directory);files=[]
            for name,(source,_,_) in self.CASES.items():
                if name in {'pattern_case_is_not_default','unknown_exception_hierarchy_keeps_explicit_throw'}:continue
                source='package fixture_'+name+'; '+source.replace('class C {','class C { void use(Object... args) {}',1)
                path=root/name/'C.java';path.parent.mkdir();path.write_text(source,encoding='utf-8');files.append(str(path))
            process=subprocess.run([str(javac),'-proc:none','--release','21','-d',str(root/'classes'),*files],capture_output=True,text=True,timeout=30)
            self.assertEqual(0,process.returncode,process.stderr)


if __name__=='__main__':unittest.main()
