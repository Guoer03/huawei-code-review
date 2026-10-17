"""Multi-file Python semantics without importing or executing project modules."""
import json
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.catalog_python import scan,rule_key
ENTRIES=json.loads((ROOT/'rulesets/catalog.json').read_text())['rules']

class PythonProjectTests(unittest.TestCase):
    def run_rule(self,key,files):
        entries=[e for e in ENTRIES if e['rule']['language']=='PYTHON' and rule_key(e['rule'])==key]
        self.assertEqual(len(entries),1)
        return scan([('/project/'+name,source) for name,source in files.items()],entries)

    def test_imported_parent_init_and_alias(self):
        files={'pkg/__init__.py':'','pkg/base.py':'class Base:\n    def __init__(self):\n        self.ready = True\n','pkg/child.py':'from .base import Base as Parent\nclass Child(Parent):\n    def __init__(self):\n        self.value = 1\n'}
        result=self.run_rule('G.CLS.01',files)
        self.assertEqual(result['errors'],[])
        self.assertEqual([f['path'] for f in result['findings']],['/project/pkg/child.py'])
        files['pkg/child.py']='from .base import Base as Parent\nclass Child(Parent):\n    def __init__(self):\n        super().__init__()\n        self.value = 1\n'
        self.assertEqual(self.run_rule('G.CLS.01',files)['findings'],[])

    def test_parent_init_inherited_through_intermediate_class(self):
        files={'base.py':'class Base:\n    def __init__(self):\n        self.x = 1\nclass Middle(Base):\n    pass\n','child.py':'import base\nclass Child(base.Middle):\n    def __init__(self):\n        self.y = 2\n'}
        result=self.run_rule('G.CLS.01',files)
        self.assertEqual(len(result['findings']),1)

    def test_explicit_parent_alias_initializer_and_conditional_gap(self):
        files={'base.py':'class Base:\n    def __init__(self):\n        self.x = 1\n','child.py':'from base import Base as Parent\nclass Child(Parent):\n    def __init__(self):\n        Parent.__init__(self)\n'}
        self.assertEqual(self.run_rule('G.CLS.01',files)['findings'],[])
        files['child.py']='from base import Base\nclass Child(Base):\n    def __init__(self, enabled):\n        if enabled:\n            super().__init__()\n'
        self.assertEqual(len(self.run_rule('G.CLS.01',files)['findings']),1)

    def test_cross_module_override_signature_and_same_named_other_class(self):
        files={'one.py':'class Base:\n    def load(self, name, *, strict=True):\n        pass\n','two.py':'class Base:\n    def load(self):\n        pass\n','use.py':'from one import Base as Parent\nfrom two import Base\nclass Child(Parent):\n    def load(self):\n        pass\n'}
        r=self.run_rule('G.CLS.02',files)
        self.assertEqual(r['errors'],[])
        self.assertEqual([f['path'] for f in r['findings']],['/project/use.py'])
        files['use.py']='from one import Base\nclass Child(Base):\n    def load(self, name, *, strict=True):\n        pass\n'
        self.assertEqual(self.run_rule('G.CLS.02',files)['findings'],[])

    def test_kwonly_requiredness_is_part_of_override_signature(self):
        files={'base.py':'class Base:\n    def read(self, *, strict=True):\n        pass\n','child.py':'from base import Base\nclass Child(Base):\n    def read(self, *, strict):\n        pass\n'}
        self.assertEqual(len(self.run_rule('G.CLS.02',files)['findings']),1)

    def test_custom_exception_handler_order_across_modules(self):
        files={'errors.py':'class ApiError(Exception):\n    pass\nclass Retryable(ApiError):\n    pass\n','client.py':'from errors import ApiError, Retryable\ntry:\n    work()\nexcept ApiError:\n    handle()\nexcept Retryable:\n    retry()\n'}
        r=self.run_rule('G.ERR.10',files)
        self.assertEqual(r['errors'],[])
        self.assertEqual(len(r['findings']),1)
        files['client.py']='from errors import ApiError, Retryable\ntry:\n    work()\nexcept Retryable:\n    retry()\nexcept ApiError:\n    handle()\n'
        self.assertEqual(self.run_rule('G.ERR.10',files)['findings'],[])

    def test_exception_definition_must_eventually_inherit_exception(self):
        files={'roots.py':'class BadRoot(BaseException):\n    pass\nclass GoodRoot(Exception):\n    pass\n','errors.py':'from roots import BadRoot, GoodRoot\nclass BadError(BadRoot):\n    pass\nclass GoodError(GoodRoot):\n    pass\n'}
        r=self.run_rule('G.ERR.03',files)
        self.assertEqual(r['errors'],[])
        self.assertEqual([(f['path'],f['line']) for f in r['findings']],[('/project/errors.py',2)])

    def test_raised_non_exception_class_detected_without_error_suffix(self):
        files={'values.py':'class Response:\n    pass\n','api.py':'from values import Response\nraise Response()\n'}
        r=self.run_rule('G.ERR.03',files)
        self.assertEqual(len(r['findings']),1)

    def test_magic_return_infers_imported_helper_and_constants(self):
        files={'helpers.py':'COUNT = 3\ndef label():\n    return 42\ndef length():\n    return COUNT\n','value.py':'from helpers import label, length\nclass Value:\n    def __str__(self):\n        return label()\n    def __len__(self):\n        return length()\n'}
        r=self.run_rule('G.CLS.09:str',files)
        self.assertEqual(r['errors'],[])
        self.assertEqual([(f['path'],f['line']) for f in r['findings']],[('/project/value.py',4)])
        self.assertEqual(self.run_rule('G.CLS.09:len',files)['findings'],[])
        files['helpers.py']='COUNT = 3\ndef label():\n    return "value"\ndef length():\n    return COUNT\n'
        self.assertEqual(self.run_rule('G.CLS.09:str',files)['findings'],[])

    def test_magic_return_infers_annotated_external_return(self):
        files={'helper.py':'def count() -> int:\n    return external()\n','value.py':'from helper import count\nclass Value:\n    def __str__(self):\n        return count()\n'}
        self.assertEqual(len(self.run_rule('G.CLS.09:str',files)['findings']),1)

    def test_circular_module_imports_are_bounded_and_resolve_known_classes(self):
        files={'a.py':'import b\nclass Base:\n    def read(self, value):\n        pass\n','b.py':'from a import Base\nclass Child(Base):\n    def read(self):\n        pass\n'}
        r=self.run_rule('G.CLS.02',files)
        self.assertEqual(r['errors'],[])
        self.assertEqual(len(r['findings']),1)

    def test_reexported_parent_is_resolved_without_executing_module(self):
        files={'pkg/__init__.py':'from .base import Base\nraise RuntimeError("must not execute")\n','pkg/base.py':'class Base:\n    def read(self, name):\n        pass\n','consumer.py':'from pkg import Base\nclass Consumer(Base):\n    def read(self):\n        pass\n'}
        self.assertEqual(len(self.run_rule('G.CLS.02',files)['findings']),1)

    def test_unknown_external_base_reports_missing_context(self):
        files={'value.py':'from missing_external import Base\nclass Value(Base):\n    def read(self):\n        pass\n'}
        r=self.run_rule('G.CLS.02',files)
        self.assertEqual(r['findings'],[])
        self.assertTrue(r['errors'])
        self.assertIn('missing_external',str(r['errors']))

    def init_result(self, body, parameters='self, enabled=False', prefix=''):
        files={'base.py':'class Base:\n    def __init__(self):\n        self.ready = True\n',
               'child.py':'from base import Base\n'+prefix+'class Child(Base):\n    def __init__('+parameters+'):\n'+''.join('        '+line+'\n' for line in body.splitlines())}
        result=self.run_rule('G.CLS.01',files)
        self.assertEqual(result['errors'],[])
        return result['findings']

    def test_early_return_path_is_not_repaired_by_later_init(self):
        self.assertEqual(len(self.init_result('if enabled:\n    return\nsuper().__init__()')),1)
        self.assertEqual(self.init_result('if enabled:\n    super().__init__()\n    return\nsuper().__init__()'),[])

    def test_finally_init_applies_to_return_paths(self):
        self.assertEqual(self.init_result('try:\n    if enabled:\n        return\nfinally:\n    super().__init__()'),[])
        self.assertEqual(len(self.init_result('try:\n    if enabled:\n        return\nfinally:\n    pass\nsuper().__init__()')),1)

    def test_shadowed_super_is_not_builtin_super(self):
        self.assertEqual(len(self.init_result('super().__init__()',parameters='self, super')),1)
        self.assertEqual(len(self.init_result('super().__init__()',prefix='def super():\n    return object()\n')),1)
        self.assertEqual(self.init_result('super(Child, self).__init__()'),[])

    def test_conditional_and_deferred_calls_do_not_initialize_every_path(self):
        for body in ['enabled and super().__init__()',
                     'super().__init__() if enabled else None',
                     'callback = lambda: super().__init__()',
                     'values = [super().__init__() for item in []]']:
            with self.subTest(body=body):self.assertEqual(len(self.init_result(body)),1)
        self.assertEqual(self.init_result('enabled and super().__init__()\nsuper().__init__()'),[])

    def test_loop_early_return_is_preserved(self):
        self.assertEqual(len(self.init_result('for item in [1]:\n    if enabled:\n        return\nsuper().__init__()')),1)
        self.assertEqual(self.init_result('for item in [1]:\n    if enabled:\n        break\nsuper().__init__()'),[])

    def test_magic_method_implicit_none_is_a_real_return_path(self):
        files={'value.py':'class Value:\n    def __str__(self):\n        if ready():\n            return "value"\n'}
        result=self.run_rule('G.CLS.09:str',files)
        self.assertEqual(len(result['findings']),1)
        files['value.py']='class Value:\n    def __str__(self):\n        if ready():\n            return "value"\n        raise ValueError("not ready")\n'
        self.assertEqual(self.run_rule('G.CLS.09:str',files)['findings'],[])

    def test_imported_helper_optional_return_is_not_treated_as_always_str(self):
        files={'helper.py':'def label():\n    if ready():\n        return "value"\n',
               'value.py':'from helper import label\nclass Value:\n    def __str__(self):\n        return label()\n'}
        result=self.run_rule('G.CLS.09:str',files)
        self.assertEqual(len(result['findings']),1)
        files['helper.py']='def label():\n    if ready():\n        return "value"\n    return "other"\n'
        self.assertEqual(self.run_rule('G.CLS.09:str',files)['findings'],[])

    def test_magic_method_finally_return_and_infinite_loop_boundaries(self):
        files={'value.py':'class Value:\n    def __str__(self):\n        try:\n            return "value"\n        finally:\n            return\n'}
        self.assertTrue(self.run_rule('G.CLS.09:str',files)['findings'])
        files['value.py']='class Value:\n    def __str__(self):\n        while True:\n            if ready():\n                return "value"\n'
        self.assertEqual(self.run_rule('G.CLS.09:str',files)['findings'],[])

    def test_parent_initialization_must_use_current_receiver(self):
        self.assertEqual(len(self.init_result('Base.__init__(enabled)')),1)
        self.assertEqual(self.init_result('Base.__init__(self)'),[])
        self.assertEqual(self.init_result('import builtins\nbuiltins.super().__init__()'),[])

    def test_literal_short_circuit_execution_is_understood(self):
        self.assertEqual(self.init_result('True and super().__init__()'),[])
        self.assertEqual(self.init_result('False or super().__init__()'),[])
        self.assertEqual(len(self.init_result('False and super().__init__()')),1)

    def test_generator_iterator_does_not_return_none_as_iterator(self):
        files={'value.py':'class Value:\n    def __iter__(self):\n        yield 1\n'}
        self.assertEqual(self.run_rule('G.CLS.09:iter',files)['findings'],[])
        files['value.py']='class Value:\n    def __str__(self):\n        yield "value"\n'
        self.assertTrue(self.run_rule('G.CLS.09:str',files)['findings'])

    def test_declared_return_does_not_hide_known_incompatible_value(self):
        files={'helper.py':'def label() -> str:\n    return 42\n',
               'value.py':'from helper import label\nclass Value:\n    def __str__(self):\n        return label()\n'}
        self.assertTrue(self.run_rule('G.CLS.09:str',files)['findings'])

    def test_assigning_imported_and_reexported_void_results(self):
        files={'pkg/__init__.py':'from .helpers import flush\n',
               'pkg/helpers.py':'def flush():\n    print("saved")\n',
               'client.py':'from pkg import flush as persist\nimport pkg.helpers as helpers\na = persist()\nb: object = helpers.flush()\n'}
        result=self.run_rule('G.FNM.04',files)
        self.assertEqual(result['errors'],[])
        self.assertEqual([(f['path'],f['line']) for f in result['findings']],[('/project/client.py',3),('/project/client.py',4)])

    def test_local_alias_of_imported_void_function(self):
        files={'helpers.py':'def flush():\n    return None\n',
               'client.py':'from helpers import flush\ndef save():\n    persist = flush\n    result = persist()\n    return result\n'}
        self.assertEqual(len(self.run_rule('G.FNM.04',files)['findings']),1)

    def test_void_calls_exclude_async_generator_and_mixed_returns(self):
        files={'helpers.py':'async def asynchronous():\n    pass\ndef generator():\n    yield 1\ndef maybe(flag):\n    if flag:\n        return 1\ndef unknown():\n    return external()\n',
               'client.py':'import helpers\na = helpers.asynchronous()\nb = helpers.generator()\nc = helpers.maybe(flag)\nd = helpers.unknown()\n'}
        self.assertEqual(self.run_rule('G.FNM.04',files)['findings'],[])
        files={'value.py':'async def work():\n    pass\ntask = work()\n'}
        self.assertEqual(self.run_rule('G.FNM.04',files)['findings'],[])

    def test_import_and_function_parameter_shadowing_do_not_create_void_findings(self):
        files={'helpers.py':'def flush():\n    pass\n',
               'client.py':'from helpers import flush\ndef use(flush):\n    return_value = flush()\nflush = lambda: 1\nvalue = flush()\n'}
        self.assertEqual(self.run_rule('G.FNM.04',files)['findings'],[])
        files={'value.py':'def helper():\n    pass\ndef caller(helper):\n    result = helper()\n'}
        self.assertEqual(self.run_rule('G.FNM.04',files)['findings'],[])

    def test_rebound_module_attribute_is_not_original_void_function(self):
        files={'helpers.py':'def flush():\n    pass\n',
               'client.py':'import helpers\nhelpers.flush = lambda: 1\nvalue = helpers.flush()\n'}
        self.assertEqual(self.run_rule('G.FNM.04',files)['findings'],[])

    def test_decorator_can_change_void_function_result(self):
        files={'helpers.py':'def replaces(fn):\n    return lambda: 1\n@replaces\ndef flush():\n    pass\n',
               'client.py':'from helpers import flush\nvalue = flush()\n'}
        self.assertEqual(self.run_rule('G.FNM.04',files)['findings'],[])

    def test_raising_function_has_no_normal_none_result(self):
        files={'helpers.py':'def fail():\n    raise ValueError("failed")\n',
               'client.py':'from helpers import fail\nvalue = fail()\n'}
        self.assertEqual(self.run_rule('G.FNM.04',files)['findings'],[])

    def test_module_rebinding_uses_binding_visible_at_call_site(self):
        files={'helpers.py':'def flush():\n    pass\n',
               'client.py':'from helpers import flush\nfirst = flush()\nflush = lambda: 1\nsecond = flush()\n'}
        result=self.run_rule('G.FNM.04',files)
        self.assertEqual([(f['path'],f['line']) for f in result['findings']],[('/project/client.py',2)])

    def test_function_name_bound_after_call_is_not_visible_early(self):
        files={'value.py':'result = flush()\ndef flush():\n    pass\n'}
        self.assertEqual(self.run_rule('G.FNM.04',files)['findings'],[])

    def test_void_function_with_local_import_alias(self):
        files={'helpers.py':'def flush():\n    pass\n',
               'client.py':'def caller():\n    from helpers import flush as persist\n    result = persist()\n'}
        self.assertEqual(len(self.run_rule('G.FNM.04',files)['findings']),1)

if __name__=='__main__':unittest.main()
