"""Static stdlib identities, using regressions reduced from real project sources.

Requests 2.34.2: cookies.py, structures.py, _types.py, compat.py.
corecompetition: submission/src/agent/protocol.py and server.py.
The source strings are parsed only; test modules never import those projects.
"""
import json
import ast
import inspect
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.catalog_python import scan, rule_key
from scripts import python_stdlib_models as stdlib

ENTRIES = json.loads((ROOT / 'rulesets/catalog.json').read_text())['rules']


class PythonStdlibModelsTests(unittest.TestCase):
    def run_rules(self, files, *keys):
        entries = [e for e in ENTRIES if e['rule']['language'].lower() == 'python'
                   and rule_key(e['rule']) in keys]
        return scan([('/project/' + path, source) for path, source in files.items()], entries)

    def test_corecompetition_abc_and_json_handler_sources(self):
        result = self.run_rules({'protocol.py': 'from abc import ABC, abstractmethod\n'
            'class Strategy(ABC):\n    @abstractmethod\n    def decide(self, state): ...\n',
            'server.py': 'import json\ntry:\n    json.loads(payload)\n'
            'except json.JSONDecodeError:\n    handle_error()\n'}, 'G.CLS.02', 'G.ERR.10')
        self.assertEqual(result['errors'], [])
        self.assertEqual(result['findings'], [])

    def test_requests_cookiejar_and_generic_mapping_sources(self):
        result = self.run_rules({'cookies.py': 'from collections.abc import MutableMapping\n'
            'from http.cookiejar import CookieJar\n'
            'class RequestsCookieJar(CookieJar, MutableMapping[str, str | None]):\n    pass\n',
            'structures.py': 'from collections.abc import MutableMapping\n'
            'from typing import Generic, TypeVar\n_VT = TypeVar("_VT")\n'
            'class CaseInsensitiveDict(MutableMapping[str, _VT], Generic[_VT]):\n    pass\n'
            'class LookupDict(dict[str, _VT]):\n    pass\n'}, 'G.CLS.02')
        self.assertEqual(result['errors'], [])

    def test_requests_protocol_sources(self):
        result = self.run_rules({'_types.py': 'from typing import Protocol, TypeVar, runtime_checkable\n'
            '_T_co = TypeVar("_T_co", covariant=True)\n'
            '@runtime_checkable\nclass SupportsRead(Protocol[_T_co]):\n'
            '    def read(self, length: int = ..., /) -> _T_co: ...\n'}, 'G.CLS.02')
        self.assertEqual(result['errors'], [])

    def test_exception_model_identity_and_handler_order(self):
        source = ('from json import JSONDecodeError as DecodeError\n'
                  'from io import UnsupportedOperation\nfrom socket import gaierror\n'
                  'from netrc import NetrcParseError\n'
                  'try:\n    work()\nexcept ValueError:\n    pass\n'
                  'except DecodeError:\n    pass\nexcept UnsupportedOperation:\n    pass\n'
                  'try:\n    work()\nexcept OSError:\n    pass\nexcept gaierror:\n    pass\n'
                  'try:\n    work()\nexcept Exception:\n    pass\nexcept NetrcParseError:\n    pass\n')
        result = self.run_rules({'client.py': source}, 'G.ERR.10')
        self.assertEqual(result['errors'], [])
        self.assertEqual(len(result['findings']), 4)

    def test_import_styles_reexports_and_builtin_alias_identity(self):
        files = {'pkg/__init__.py': 'from json.decoder import JSONDecodeError as Error\n',
                 'client.py': 'import http.cookiejar\nfrom http import cookiejar as jars\n'
                 'from pkg import Error\n'
                 'class First(http.cookiejar.CookieJar):\n    pass\n'
                 'class Second(jars.CookieJar):\n    pass\n'
                 'class DecodeError(Error):\n    pass\n'
                 'try:\n    work()\nexcept IOError:\n    pass\n'
                 'except OSError:\n    pass\n'}
        result = self.run_rules(files, 'G.CLS.02', 'G.ERR.03', 'G.ERR.10')
        self.assertEqual(result['errors'], [])
        self.assertEqual(len(result['findings']), 1)

    def test_known_stdlib_initializer_is_checked(self):
        files = {'cookies.py': 'from http.cookiejar import CookieJar\n'
                 'class Broken(CookieJar):\n    def __init__(self):\n        self.value = 1\n'}
        result = self.run_rules(files, 'G.CLS.01')
        self.assertEqual(result['errors'], [])
        self.assertEqual(len(result['findings']), 1)
        files['cookies.py'] = files['cookies.py'].replace('self.value = 1', 'super().__init__()')
        self.assertEqual(self.run_rules(files, 'G.CLS.01')['findings'], [])

    def test_supplied_generic_base_keeps_identity_and_methods(self):
        files = {'base.py': 'from typing import Generic, TypeVar\nT = TypeVar("T")\n'
                 'class Base(Generic[T]):\n    def __init__(self):\n        self.ready = True\n'
                 '    def load(self, value):\n        pass\n',
                 'child.py': 'from base import Base as Parent\n'
                 'class Child(Parent[int]):\n    def __init__(self):\n        pass\n'
                 '    def load(self):\n        pass\n'}
        for rule in ('G.CLS.01', 'G.CLS.02'):
            result = self.run_rules(files, rule)
            self.assertEqual(result['errors'], [])
            self.assertEqual(len(result['findings']), 1)

    def test_supplied_generic_exception_handler_order(self):
        files = {'errors.py': 'from typing import Generic, TypeVar\nT = TypeVar("T")\n'
                 'class Error(Exception, Generic[T]):\n    pass\n'
                 'class Specific(Error[int]):\n    pass\n',
                 'client.py': 'from errors import Error, Specific\ntry:\n    work()\n'
                 'except Error:\n    pass\nexcept Specific:\n    pass\n'}
        result = self.run_rules(files, 'G.ERR.03', 'G.ERR.10')
        self.assertEqual(result['errors'], [])
        self.assertEqual(len(result['findings']), 1)

    def test_vendor_and_shadowed_names_are_not_stdlib(self):
        for imports, base in [('from vendor import ABC', 'ABC'),
                              ('from vendor import MutableMapping', 'MutableMapping[str, int]'),
                              ('import json\njson = external()', 'json.JSONDecodeError'),
                              ('from abc import ABC\nABC = external()', 'ABC'),
                              ('import json\njson.JSONDecodeError = external()', 'json.JSONDecodeError')]:
            with self.subTest(imports=imports):
                result = self.run_rules({'client.py': imports + '\nclass Value(' + base + '):\n    pass\n'}, 'G.CLS.02')
                self.assertTrue(result['errors'])
                self.assertEqual(result['findings'], [])

    def test_supplied_module_shadows_stdlib_even_if_member_missing(self):
        result = self.run_rules({'json.py': 'raise RuntimeError("never execute")\n',
            'client.py': 'from json import JSONDecodeError\nclass Value(JSONDecodeError):\n    pass\n'}, 'G.CLS.02')
        self.assertTrue(result['errors'])

    def test_supplied_root_package_shadows_stdlib_submodules(self):
        result = self.run_rules({'http/__init__.py': 'raise RuntimeError("never execute")\n',
            'client.py': 'from http.cookiejar import CookieJar\nclass Value(CookieJar):\n    pass\n'}, 'G.CLS.02')
        self.assertTrue(result['errors'])

    def test_a_later_stdlib_import_does_not_rewrite_an_earlier_vendor_binding(self):
        source = ('from vendor import ABC\nclass First(ABC):\n    pass\n'
                  'from abc import ABC\nclass Second(ABC):\n    pass\n')
        result = self.run_rules({'client.py': source}, 'G.CLS.02')
        self.assertEqual(len(result['errors']), 1)
        self.assertIn('vendor.ABC', result['errors'][0]['reason'])

    def test_a_later_vendor_import_does_not_rewrite_an_earlier_stdlib_binding(self):
        source = ('from abc import ABC\nclass First(ABC):\n    pass\n'
                  'from vendor import ABC\nclass Second(ABC):\n    pass\n')
        result = self.run_rules({'client.py': source}, 'G.CLS.02')
        self.assertEqual(len(result['errors']), 1)
        self.assertEqual(result['errors'][0]['line'], 5)

    def test_local_stdlib_import_has_provenance_and_local_shadow_is_unknown(self):
        source = ('def clean():\n    import json\n    try:\n        work()\n'
                  '    except ValueError:\n        pass\n    except json.JSONDecodeError:\n        pass\n'
                  'def unknown(json):\n    try:\n        work()\n'
                  '    except json.JSONDecodeError:\n        pass\n')
        result = self.run_rules({'client.py': source}, 'G.ERR.10')
        self.assertEqual(len(result['findings']), 1)
        self.assertEqual(len(result['errors']), 1)

    def test_static_model_methods_are_not_executable_none_returning_functions(self):
        source = ('from http.cookiejar import CookieJar\n'
                  'result = CookieJar.make_cookies(jar, response, request)\n')
        self.assertEqual(self.run_rules({'client.py': source}, 'G.FNM.04')['findings'], [])

    def test_conditional_vendor_fallback_remains_unknown(self):
        # Requests compat.py can use simplejson, so the json branch alone cannot prove identity.
        files = {'compat.py': 'try:\n    from simplejson import JSONDecodeError\n'
                 'except ImportError:\n    from json import JSONDecodeError\n',
                 'errors.py': 'from compat import JSONDecodeError\nclass DecodeError(JSONDecodeError):\n    pass\n'}
        self.assertTrue(self.run_rules(files, 'G.ERR.03')['errors'])

    def test_arbitrary_class_subscription_cannot_change_base_identity_silently(self):
        files = {'base.py': 'class Other:\n    pass\nclass Base:\n'
                 '    def __class_getitem__(cls, item):\n        return Other\n',
                 'child.py': 'from base import Base\nclass Child(Base[int]):\n    pass\n'}
        self.assertTrue(self.run_rules(files, 'G.CLS.02')['errors'])

    def test_context_errors_have_only_selected_semantic_rule_ids(self):
        result = self.run_rules({'client.py': 'from vendor import Base\nclass Value(Base):\n    pass\n'},
                                'G.CLS.02', 'G.FMT.02')
        expected = [e['rule']['id'] for e in ENTRIES if e['rule']['language'].lower() == 'python'
                    and rule_key(e['rule']) == 'G.CLS.02']
        self.assertTrue(result['errors'])
        for error in result['errors']:
            self.assertEqual(error.get('affected_rule_ids'), expected)

    def test_parse_errors_are_not_rule_scoped(self):
        result = self.run_rules({'broken.py': 'class :'}, 'G.CLS.02', 'G.FMT.02')
        self.assertTrue(result['errors'])
        self.assertNotIn('affected_rule_ids', result['errors'][0])

    def test_python311_model_does_not_invent_python312_buffer(self):
        result = self.run_rules({'client.py': 'from collections.abc import Buffer\n'
            'class Value(Buffer):\n    pass\n'}, 'G.CLS.02')
        self.assertTrue(result['errors'])
        self.assertIn('collections.abc.Buffer', result['errors'][0]['reason'])

    def test_keysview_override_uses_its_concrete_signature(self):
        # KeysView.__contains__(self, key) is explicitly modeled.  A matching
        # override is clean; a mismatched one is a real signature finding.
        result = self.run_rules({'client.py': 'from collections.abc import KeysView\n'
            'class View(KeysView):\n    def __contains__(self, key):\n        return False\n'}, 'G.CLS.02')
        self.assertEqual(result['errors'], [])
        self.assertEqual(result['findings'], [])
        result = self.run_rules({'client.py': 'from collections.abc import KeysView\n'
            'class View(KeysView):\n    def __contains__(self):\n        return False\n'}, 'G.CLS.02')
        self.assertEqual(result['errors'], [])
        self.assertTrue(result['findings'])

    def test_mapping_override_uses_mapping_signature(self):
        source = ('from collections.abc import Mapping\nclass Value(Mapping):\n'
                  '    def __contains__(self, key):\n        return False\n')
        result = self.run_rules({'client.py': source}, 'G.CLS.02')
        self.assertEqual(result['errors'], [])
        self.assertEqual(result['findings'], [])
        self.assertTrue(self.run_rules({'client.py': source.replace('self, key', 'self')}, 'G.CLS.02')['findings'])

    def test_mutable_mapping_update_positional_only_is_preserved(self):
        source = ('from collections.abc import MutableMapping\nclass Value(MutableMapping):\n'
                  '    def update(self, other=(), /, **kwds):\n        pass\n')
        result = self.run_rules({'client.py': source}, 'G.CLS.02')
        self.assertEqual(result['errors'], [])
        self.assertEqual(result['findings'], [])
        self.assertTrue(self.run_rules({'client.py': source.replace(', /,', ',')}, 'G.CLS.02')['findings'])

    def test_new_methods_on_stdlib_subclasses_do_not_create_model_gaps(self):
        source = ('from http.cookiejar import CookieJar\nfrom collections.abc import MutableMapping\n'
                  'class Jar(CookieJar):\n    def iterkeys(self):\n        return []\n'
                  '    def get_policy(self):\n        return self._policy\n'
                  'class Dictionary(MutableMapping):\n    def lower_items(self):\n        return []\n'
                  '    def copy(self):\n        return Dictionary()\n')
        result = self.run_rules({'client.py': source}, 'G.CLS.02')
        self.assertEqual(result['errors'], [])
        self.assertEqual(result['findings'], [])

    def test_multiple_inheritance_continues_past_stdlib_without_that_member(self):
        source = ('from http.cookiejar import CookieJar\nfrom collections.abc import MutableMapping\n'
                  'class Jar(CookieJar, MutableMapping):\n    def get(self, key):\n        return None\n')
        result = self.run_rules({'client.py': source}, 'G.CLS.02')
        self.assertEqual(result['errors'], [])
        self.assertEqual(len(result['findings']), 1)
        self.assertIn('Mapping.get', result['findings'][0]['message'])
        self.assertEqual(self.run_rules({'client.py': source.replace('get(self, key)', 'get(self, key, default=None)')}, 'G.CLS.02')['findings'], [])

    def test_inherited_stdlib_method_is_reached_through_own_member_inventory(self):
        source = ('from collections.abc import MutableMapping\nclass Dictionary(MutableMapping):\n'
                  '    def __getitem__(self, key):\n        return key\n'
                  '    def __iter__(self):\n        return iter(())\n'
                  '    def __len__(self):\n        return 0\n')
        result = self.run_rules({'client.py': source}, 'G.CLS.02')
        self.assertEqual(result['errors'], [])
        self.assertEqual(result['findings'], [])
        self.assertTrue(self.run_rules({'client.py': source.replace('__getitem__(self, key)', '__getitem__(self)')}, 'G.CLS.02')['findings'])

    def test_existing_unmodelled_override_blocks_inherited_signature(self):
        # DefaultCookiePolicy overrides CookiePolicy.set_ok; its signature is
        # deliberately not in the checked table, so this remains an unknown.
        source = ('from http.cookiejar import DefaultCookiePolicy\nclass Policy(DefaultCookiePolicy):\n'
                  '    def set_ok(self, cookie, request):\n        return True\n')
        result = self.run_rules({'client.py': source}, 'G.CLS.02', 'G.ERR.10')
        self.assertEqual(result['findings'], [])
        self.assertEqual(len(result['errors']), 1)
        self.assertIn('DefaultCookiePolicy.set_ok', result['errors'][0]['reason'])
        self.assertEqual(result['errors'][0]['affected_rule_ids'], ['da6bbffc6db811eea68ffa163e0fa374'])

    def test_missing_stdlib_init_signature_affects_initializer_rule(self):
        result = self.run_rules({'client.py': 'from http.cookiejar import DefaultCookiePolicy\n'
            'class Policy(DefaultCookiePolicy):\n    def __init__(self):\n        pass\n'}, 'G.CLS.01')
        self.assertEqual(result['findings'], [])
        self.assertEqual(len(result['errors']), 1)
        self.assertEqual(result['errors'][0]['affected_rule_ids'], ['da6bb6296db811eea68ffa163e0fa374'])

    def test_context_distinguishes_stdlib_model_version_from_runtime(self):
        result = self.run_rules({'client.py': 'from abc import ABC\nclass Value(ABC):\n    pass\n'}, 'G.CLS.02')
        context = result['type_context']['stdlib_models']
        self.assertEqual(context.get('python_version'), '3.11')
        self.assertFalse(context.get('target_version_detected', True))
        self.assertTrue(context.get('provenance', {}).get('source_sha256'))

    @unittest.skipUnless(sys.version_info[:2] == (3, 11), 'model facts are pinned to Python 3.11')
    def test_model_facts_match_independent_python311_stdlib(self):
        # Explicit safe imports only: the target sources under scan are never imported.
        import abc
        import builtins
        import collections.abc
        import http.cookiejar
        import io
        import json
        import json.decoder
        import netrc
        import socket
        import typing
        modules = {m.__name__: m for m in (abc, builtins, collections.abc, http.cookiejar,
                   io, json, json.decoder, netrc, socket, typing)}
        def actual_class(qualified):
            module, _, name = qualified.rpartition('.')
            return getattr(modules[module], name)
        for qualified, model in stdlib.CLASSES.items():
            with self.subTest(model=qualified):
                actual = actual_class(qualified)
                self.assertEqual(model.bases, tuple(base.__module__ + '.' + base.__name__ for base in actual.__bases__))
                self.assertEqual(model.own_members, frozenset(vars(actual)) - {'__module__', '__doc__', '__dict__',
                    '__weakref__', '__slots__', '__abstractmethods__', '_abc_impl'})
                for name, function in stdlib.METHODS[qualified].items():
                    arguments = function.args
                    positional = arguments.posonlyargs + arguments.args
                    required = len(positional) - len(arguments.defaults)
                    expected = [(arg.arg, inspect.Parameter.POSITIONAL_ONLY if i < len(arguments.posonlyargs)
                                 else inspect.Parameter.POSITIONAL_OR_KEYWORD, i >= required)
                                for i, arg in enumerate(positional)]
                    if arguments.vararg:expected.append((arguments.vararg.arg, inspect.Parameter.VAR_POSITIONAL, False))
                    expected.extend((arg.arg, inspect.Parameter.KEYWORD_ONLY, default is not None)
                                    for arg, default in zip(arguments.kwonlyargs, arguments.kw_defaults))
                    if arguments.kwarg:expected.append((arguments.kwarg.arg, inspect.Parameter.VAR_KEYWORD, False))
                    signature = inspect.signature(getattr(actual, name))
                    observed = [(param.name, param.kind, param.default is not inspect.Parameter.empty)
                                for param in signature.parameters.values()]
                    self.assertEqual(expected, observed, qualified + '.' + name)
        for alias, target in stdlib.ALIASES.items():
            with self.subTest(alias=alias):
                module, _, name = alias.rpartition('.')
                actual = getattr(modules[module], name, None)
                target_module, _, target_name = target.rpartition('.')
                expected = getattr(modules[target_module], target_name, None)
                if actual is None:
                    # ``json.JSONDecodeError`` is a re-export through json.decoder.
                    self.assertEqual((module, name), ('json', 'JSONDecodeError'))
                    actual = getattr(json, name)
                self.assertIs(typing.get_origin(actual) or actual, expected)


if __name__ == '__main__':
    unittest.main()
