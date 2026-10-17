"""Completion and asynchronous rejection regression contracts for exported rules."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from catalog_frontend import scan,runtime_status
IDS={'finally_js':'da73b7006db811eea68ffa163e0fa374','finally_ts':'da6caa4f6db811eea68ffa163e0fa374','invariant':'da6d3d336db811eea68ffa163e0fa374','promise':'da6d33f06db811eea68ffa163e0fa374'}
class FrontendCompletionTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.catalog=json.loads((ROOT/'rulesets/catalog.json').read_text())['rules']
  if not runtime_status()['available']:raise unittest.SkipTest('frontend dependencies unavailable')
 def findings(self,rule,source):
  suffix='js' if rule=='finally_js' else 'ts'
  report=scan([('/virtual_completion/input.'+suffix,source)],[r for r in self.catalog if r['id']==IDS[rule]])
  self.assertEqual(report['errors'],[]);return report['findings']
 def test_catalog_regeneration_preserves_status_and_test_evidence(self):
  # A stale generator previously downgraded var-only coverage and erased
  # independently validated semantic descriptions and regression references.
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory)
   for relative in ('scripts/frontend_rules','rulesets/implementations','tests/catalog_cases'):
    (root/relative).mkdir(parents=True,exist_ok=True)
   shutil.copyfile(ROOT/'scripts/frontend_rules/build_catalog.py',root/'scripts/frontend_rules/build_catalog.py')
   shutil.copyfile(ROOT/'rulesets/catalog.json',root/'rulesets/catalog.json')
   result=subprocess.run([sys.executable,str(root/'scripts/frontend_rules/build_catalog.py')],capture_output=True,text=True)
   self.assertEqual(result.returncode,0,result.stderr)
   for language in ('javascript','typescript'):
    relative='rulesets/implementations/'+language+'.json'
    generated=json.loads((root/relative).read_text())
    self.assertEqual(generated,json.loads((ROOT/relative).read_text()))
   for relative in ('scripts/frontend_rules/mappings.json','tests/catalog_cases/frontend.json'):
    self.assertEqual(json.loads((root/relative).read_text()),json.loads((ROOT/relative).read_text()))
 def test_finally_ignores_unreachable_jumps(self):
  self.assertEqual(self.findings('finally_js','function f(){try { return 1; } finally { if(false){return 2;} }}'),[])
 def test_finally_overridden_completion_reports_only_escape(self):
  fs=self.findings('finally_ts','function f(){try {run();}finally{try{return 1;}finally{throw new Error();}}}')
  self.assertEqual(len(fs),1)
  self.assertIn('throw',fs[0]['evidence'])
 def test_finally_local_labels_switches_and_nested_functions(self):
  source='''function f(){try { run(); } finally {
while(ready){if(stop)break;continue;}
local:{if(ready)break local;}
switch(value){case 1: break;default:break;}
function nested(){return 1;}
const task=()=>{throw new Error();};
try{throw new Error();}catch(e){recover(e);}
}}'''
  self.assertEqual(self.findings('finally_js',source),[])
 def test_finally_cross_boundary_labels_report(self):
  source='outer:while(ready){try{run();}finally{if(stop)break outer;else continue outer;}}'
  self.assertEqual(len(self.findings('finally_js',source)),2)
 def test_finally_catch_rethrow_and_nested_return(self):
  source='function f(){try{run();}finally{try{throw new Error();}catch(e){throw e;}}}'
  self.assertEqual(len(self.findings('finally_ts',source)),1)
 def test_invariant_const_alias_and_terminal_throw(self):
  source='function f(flag:boolean){const result=2;if(flag)return result; if(other)throw new Error();return 2;}'
  self.assertEqual(len(self.findings('invariant',source)),1)
 def test_invariant_implicit_undefined_and_finally_override(self):
  self.assertEqual(self.findings('invariant','function f(flag:boolean){if(flag){return 1;}if(other){return 1;}}'),[])
  self.assertEqual(self.findings('invariant','function f(flag:boolean){try{if(flag)return 1;return 1;}finally{if(other)return 2;}}'),[])
 def test_invariant_switch_fallthrough_and_default(self):
  source='function f(value:number){const result=3;switch(value){case 1:case 2:return result;default:return 3;}}'
  self.assertEqual(len(self.findings('invariant',source)),1)
 def test_invariant_unreachable_distinct_return(self):
  source='function f(value:boolean){if(value)return 3;return 3;return 9;}'
  self.assertEqual(len(self.findings('invariant',source)),1)
 def test_promise_discarded_call_and_aliased_return(self):
  source='''async function source(){return 1;}
function discarded(){try{source();}catch(e){recover(e);}}
function returned(){try{const task=source();return task;}catch(e){recover(e);}}
'''
  self.assertEqual(len(self.findings('promise',source)),2)
 def test_promise_await_and_rejection_handler(self):
  source='''async function source(){return 1;}
async function awaited(){try{const task=source();return await task;}catch(e){recover(e);}}
function handled(){try{return source().catch(error=>0);}catch(e){recover(e);}}
function thenHandled(){try{return source().then(value=>value,error=>0);}catch(e){recover(e);}}
'''
  self.assertEqual(self.findings('promise',source),[])
 def test_promise_nested_function_catch_scope(self):
  source='''async function source(){return 1;}
function outer(){try{return function nested(){return source();};}catch(e){recover(e);}}
function catchBody(){try{run();}catch(e){return source();}}
function finalizer(){try{run();}catch(e){recover(e);}finally{return source();}}
'''
  self.assertEqual(self.findings('promise',source),[])
 def test_promise_conditional_return_and_nested_try_handler(self):
  source='''async function source(){return 1;}
function f(flag:boolean){try{return flag ? source() : Promise.resolve(2);}catch(e){recover(e);}}
async function g(){try{try{return await source();}finally{cleanup();}}catch(e){recover(e);}}
'''
  self.assertEqual(len(self.findings('promise',source)),1)
 def test_promise_non_callable_handlers_do_not_handle_rejection(self):
  source='''async function source(){return 1;}
function absent(){try{return source().catch(undefined);}catch(e){recover(e);}}
function thenAbsent(){try{return source().then(value=>value,undefined);}catch(e){recover(e);}}
function invalid(){try{return source().catch(123 as any);}catch(e){recover(e);}}
'''
  self.assertEqual(len(self.findings('promise',source)),3)
 def test_promise_unreachable_paths_are_ignored(self):
  source='''async function source(){return 1;}
function f(){try{if(false){source();}return 1;source();}catch(e){recover(e);}}
function g(){try{while(false){source();}}catch(e){recover(e);}}
'''
  self.assertEqual(self.findings('promise',source),[])
 def test_invariant_do_loop_has_no_implicit_undefined_after_return(self):
  source='function f(flag:boolean){do{if(flag)return 1;return 1;}while(flag);}'
  self.assertEqual(len(self.findings('invariant',source)),1)
 def test_invariant_undefined_and_void_returns(self):
  source='function f(flag:boolean){if(flag)return undefined;return;} '
  self.assertEqual(len(self.findings('invariant',source)),1)
 def test_vue_recursive_key_lookup_has_implicit_undefined_return(self):
  # Reduced from Vue runtime-core/customFormatter.ts:176-190.
  source='''type ComponentOptions={ [name:string]:unknown; extends?:ComponentOptions; mixins?:ComponentOptions[] };
const isArray=Array.isArray;
const isObject=(value:unknown):value is object=>typeof value==='object'&&value!==null;
function isKeyOfType(Comp:ComponentOptions,key:string,type:string){
 const opts=Comp[type];
 if((isArray(opts)&&opts.includes(key))||(isObject(opts)&&key in opts)){return true;}
 if(Comp.extends&&isKeyOfType(Comp.extends,key,type)){return true;}
 if(Comp.mixins&&Comp.mixins.some(m=>isKeyOfType(m,key,type))){return true;}
}
'''
  self.assertEqual(self.findings('invariant',source),[])
  # Adding a true fallback makes all completing paths invariant.
  always_true=source.rstrip()[:-1]+'return true;}'
  self.assertEqual(len(self.findings('invariant',always_true)),1)
 def test_promise_handler_rethrow_and_rejection_are_not_safe(self):
  source='''async function source(){return 1;}
function rethrow(){try{return source().catch(error=>{throw error;});}catch(e){recover(e);}}
function reject(){try{return source().catch(error=>Promise.reject(error));}catch(e){recover(e);}}
'''
  self.assertEqual(len(self.findings('promise',source)),2)
 def test_promise_handler_local_catch_and_alias_return_are_safe(self):
  source='''async function source(){return 1;}
const fallback=(error:unknown)=>0;
function f(){try{return source().catch(fallback);}catch(e){recover(e);}}
function g(){try{return source().catch(error=>{try{throw error;}catch(e){return 0;}});}catch(e){recover(e);}}
'''
  self.assertEqual(self.findings('promise',source),[])
 def test_finally_unreachable_infinite_loop_and_preceding_return(self):
  source='''function f(){try{while(true){}}finally{return 1;}}
function g(){return;try{run();}finally{return 2;}}
'''
  self.assertEqual(self.findings('finally_js',source),[])
 def test_finally_nested_loop_continue_outer_local_label(self):
  source='function f(){try{run();}finally{outer:while(ready){while(more){continue outer;}break;}}}'
  self.assertEqual(self.findings('finally_js',source),[])
 def test_promise_recursive_handler_does_not_crash_or_claim_safe(self):
  source='''async function source(){return 1;}
const fallback=()=>source().catch(fallback);
function f(){try{return source().catch(fallback);}catch(e){recover(e);}}
'''
  self.assertEqual(len(self.findings('promise',source)),1)
 def test_promise_then_fulfillment_rejection_is_not_handled_by_second_argument(self):
  source='''async function source(){return 1;}
function f(){try{return source().then(value=>{throw new Error();},error=>0);}catch(e){recover(e);}}
'''
  self.assertEqual(len(self.findings('promise',source)),1)
