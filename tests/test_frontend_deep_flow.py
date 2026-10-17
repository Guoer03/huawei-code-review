"""Independent multi-file and control-flow contracts beyond the original fixtures."""
import json
from pathlib import Path
import sys
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from catalog_frontend import scan,runtime_status
IDS={
'duplicate':'da6b955c6db811eea68ffa163e0fa374','incoming':'da6bc7c46db811eea68ffa163e0fa374',
'mutation':'da73ef3d6db811eea68ffa163e0fa374','mutator':'da6bf13e6db811eea68ffa163e0fa374',
'void':'da6bbc486db811eea68ffa163e0fa374','same':'da6c32e46db811eea68ffa163e0fa374',
'var':'da6c1ff16db811eea68ffa163e0fa374',
}
class FrontendDeepFlowTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.catalog=json.loads((ROOT/'rulesets/catalog.json').read_text())['rules']
  if not runtime_status()['available']:raise unittest.SkipTest('frontend dependencies unavailable')
 def run_sources(self,rule,sources):
  files=[('/virtual_deep/'+p,t) for p,t in sources]
  result=scan(files,[r for r in self.catalog if r['id']==IDS[rule]])
  self.assertEqual(result['errors'],[],result['errors'][:3]);return result['findings']
 def test_cross_file_alpha_renamed_implementation(self):
  fs=self.run_sources('duplicate',[
   ('a.ts','export function first(value:number){ const result=value*2; return result+1; }'),
   ('b.ts','export function second(input:number){ const answer=input*2; return answer+1; }')])
  self.assertEqual([f['path'] for f in fs],['/virtual_deep/b.ts'])
  self.assertIn('a.ts',fs[0]['message'])
 def test_duplicate_preserves_literals_and_free_bindings(self):
  fs=self.run_sources('duplicate',[
   ('a.ts','const offset=1; export function first(x:number){ return x+offset+"a b"; }'),
   ('b.ts','const offset=2; export function second(x:number){ return x+offset+"a b"; }'),
   ('c.ts','export function third(x:number){ return x+"a b"; }'),
   ('d.ts','export function fourth(x:number){ return x+"ab"; }')])
  self.assertEqual(fs,[])
 def test_duplicate_resolves_import_aliases(self):
  fs=self.run_sources('duplicate',[
   ('base.ts','export function base(x:number){return x*x;}'),
   ('a.ts','import {base} from "./base";export function first(x:number){return base(x)+1;}'),
   ('b.ts','import {base as calculate} from "./base";export function second(value:number){return calculate(value)+1;}')])
  self.assertEqual([f['path'] for f in fs],['/virtual_deep/b.ts'])
 def test_incoming_value_write_after_unrelated_statement(self):
  fs=self.run_sources('incoming',[('a.ts','function f(value:number){ const other=1; value=other+1; return value; }')])
  self.assertEqual(len(fs),1)
 def test_incoming_value_branch_paths_and_reads(self):
  fs=self.run_sources('incoming',[('a.ts','function f(value:number, flag:boolean){ if(flag){ value=1; }else{value=2;} return value; }')])
  self.assertEqual(len(fs),2)
  safe=self.run_sources('incoming',[('b.ts','function f(value:number, flag:boolean){ if(flag){ console.log(value); } value=2; return value; }')])
  self.assertEqual(safe,[])
 def test_incoming_value_rhs_compound_and_termination(self):
  fs=self.run_sources('incoming',[('a.ts','function f(value:number,flag:boolean){ if(flag){return value;} value=1; return value; }')])
  self.assertEqual(len(fs),1)
  safe=self.run_sources('incoming',[('b.ts','function f(value:number){value+=1; value=value+2; return value;}')])
  self.assertEqual(safe,[])
 def test_catch_and_foreach_initial_value(self):
  fs=self.run_sources('incoming',[('a.ts','try{run();}catch(error){ const status=1; error=new Error(); } for(let value of [1,2]){const status=1;value=3;}')])
  self.assertEqual(len(fs),2)
 def test_array_alias_and_imported_mutation(self):
  fs=self.run_sources('mutation',[
   ('mutate.js','export function append(list,value){list.push(value);}'),
   ('use.js','import {append} from "./mutate";const values=[1,2];const alias=values;for(const value of values){append(alias,value);}')])
  self.assertEqual(len(fs),1)
  self.assertEqual(fs[0]['path'],'/virtual_deep/use.js')
 def test_index_loop_mutation_and_safe_copy(self):
  fs=self.run_sources('mutation',[('a.js','const values=[1,2];for(let i=0;i<values.length;i++){values.splice(i,1);}')])
  self.assertEqual(len(fs),1)
  safe=self.run_sources('mutation',[('b.js','const values=[1,2];const alias=[...values];for(const value of values){alias.push(value);}')])
  self.assertEqual(safe,[])
 def test_mutator_assignment_to_alias_is_not_copy(self):
  fs=self.run_sources('mutator',[('a.ts','const values=[2,1];const alias=values;let sorted:number[];sorted=alias.reverse();')])
  self.assertEqual(len(fs),1)
  safe=self.run_sources('mutator',[('b.ts','let values=[2,1];values=values.reverse();')])
  self.assertEqual(safe,[])
 def test_void_outputs_in_aggregate_values(self):
  fs=self.run_sources('void',[('a.ts','function run():void{} const object={value:run()}; const list=[run()]; const text=`result ${run()}`;')])
  self.assertEqual(len(fs),3)
  safe=self.run_sources('void',[('b.ts','function run():void{} const callback=()=>run(); const list=[1].forEach(()=>run());')])
  # Assigning the result of forEach is itself a violation; callback bodies are not.
  self.assertEqual(len(safe),1)
 def test_identical_operand_scope_and_effect_boundaries(self):
  fs=self.run_sources('same',[('a.ts','declare const value:number; const a=(value) & value; const b=value ^ value; const c=value-value;')])
  self.assertEqual(len(fs),3)
  safe=self.run_sources('same',[('b.ts','declare const obj:{get value():number}; const a=obj.value-obj.value; function run(){return Math.random();}const b=run()-run();')])
  self.assertEqual(safe,[])
 def test_var_policy_does_not_report_let_const(self):
  fs=self.run_sources('var',[('a.ts','consume(value); var value=1; consume(other);let other=2; consume(last);const last=3;')])
  self.assertEqual(len(fs),1)
  self.assertIn('value',fs[0]['evidence'])
 def test_duplicate_retains_unary_template_and_execution_kind(self):
  source='''
export function negative(x:number){ return -x; }
export function positive(x:number){ return +x; }
export function templateA(x:string){ return `A${x}Z`; }
export function templateB(x:string){ return `B${x}Z`; }
export async function asyncValue(){ return 1; }
export function syncValue(){ return 1; }
export function* generatorValue(){ return 2; }
export function ordinaryValue(){ return 2; }
export function namedKey({a}:{a:number}){return a;}
export function otherKey({b}:{b:number}){return b;}
'''
  self.assertEqual(self.run_sources('duplicate',[('a.ts',source)]),[])
 def test_incoming_reads_property_keys_and_closure_capture(self):
  source='''
function key(value:number) { const object={value:2}; value=3; return value; }
function capture(value:number) { const read=()=>value; value=3; return read; }
function compound(value:number) { value ||= 2; value=3; return value; }
'''
  fs=self.run_sources('incoming',[('a.ts',source)])
  self.assertEqual(len(fs),1)
 def test_array_reassigned_parameter_is_not_original_array(self):
  source='''
function detached(list,value){list=[];list.push(value);}
const items=[1,2];for(const value of items){detached(items,value);}
'''
  self.assertEqual(self.run_sources('mutation',[('a.js',source)]),[])
 def test_array_computed_mutator_and_helper_alias(self):
  source='''
function append(list,value){const alias=list;alias["push"](value);}
const items=[1,2];for(const value of items){append(items,value);}
'''
  self.assertEqual(len(self.run_sources('mutation',[('a.js',source)])),1)
 def test_array_alias_rebound_before_mutation_is_not_original(self):
  source='''
let items=[1,2];const old=items;items=[3,4];for(const value of items){old.push(value);}
'''
  self.assertEqual(self.run_sources('mutation',[('a.js',source)]),[])
 def test_void_cast_await_and_ternary_propagate_actual_value_use(self):
  source='''
function run():void{}
const value=(run() as unknown);
async function wrapped(){const result=await run();}
const result=true ? run() : run();
true ? run() : run();
void run();
'''
  self.assertEqual(len(self.run_sources('void',[('a.ts',source)])),4)
 def test_incoming_conditional_expression_and_short_circuit_paths(self):
  source='''
function branching(value:number, flag:boolean){ const result=flag ? value : 0; value=1; return result; }
function shortCircuit(value:number, flag:boolean){ flag && consume(value); value=1; return value; }
'''
  self.assertEqual(self.run_sources('incoming',[('a.ts',source)]),[])
 def test_mutation_in_uninvoked_callback_is_not_during_traversal(self):
  source='''
const items=[1,2];for(const value of items){const later=()=>items.push(value);}
'''
  self.assertEqual(self.run_sources('mutation',[('a.js',source)]),[])
 def test_var_destructured_binding_use_before_define(self):
  fs=self.run_sources('var',[('a.ts','consume(value); var {value}={value:1}; consume(other);let {other}={other:2};')])
  self.assertEqual(len(fs),1)
 def test_void_conditional_statement_preserves_side_effects(self):
  source='''
function run():void{}
true ? run() : run();
const value = true ? run() : run();
'''
  fs=self.run_sources('void',[('a.ts',source)])
  self.assertEqual(len(fs),2)
  self.assertTrue(all(f['line']==4 for f in fs))
 def test_helper_rest_parameter_and_unreachable_mutation_do_not_change_source(self):
  source='''
function rest(...lists){ lists.push([]); }
function unreachable(list){ return; list.push(1); }
const items=[1,2];for(const value of items){rest(items);unreachable(items);}
'''
  self.assertEqual(self.run_sources('mutation',[('a.js',source)]),[])
 def test_initial_value_conditional_expression_writes_both_paths(self):
  source='function f(value:number,flag:boolean){flag ? value=1 : value=2;return value;}'
  self.assertEqual(len(self.run_sources('incoming',[('a.ts',source)])),2)
 def test_identical_getter_comparison_is_not_pure(self):
  source='declare const obj:{get value():number};const result=obj.value === obj.value;'
  self.assertEqual(self.run_sources('same',[('a.ts',source)]),[])
 def test_vue_arguments_slice_reads_parameter_initial_value(self):
  source='''
function h(type:unknown, props?:unknown, children?:unknown) {
  const length=arguments.length;
  if(length>3) children=Array.prototype.slice.call(arguments,2);
  return children;
}
'''
  self.assertEqual(self.run_sources('incoming',[('a.ts',source)]),[])
 def test_arguments_value_reads_and_length_only_boundary(self):
  source='''
function values(value:number){ consume(arguments); value=2; return value; }
function indexed(value:number){ consume(arguments[0]);value=2;return value;}
function lengthOnly(value:number){const size=arguments.length;value=size;return value;}
function nested(value:number){function inner(){consume(arguments);} value=2;return value;}
'''
  fs=self.run_sources('incoming',[('a.ts',source)])
  self.assertEqual([f['line'] for f in fs],[4,5])
 def test_vue_void_comma_left_is_discarded_but_right_value_is_used(self):
  source='''
function openBlock():void{}
function createBlock(){return {};}
function valid(){return (openBlock(), createBlock());}
const validValue=(openBlock(),createBlock());
const invalidValue=(createBlock(),openBlock());
'''
  fs=self.run_sources('void',[('a.ts',source)])
  self.assertEqual([f['line'] for f in fs],[6])
