"""Static, identity-based stdlib class facts; no analysed module is imported.

Models describe Python 3.11 public inheritance and selected method signatures.
The table is pinned to Python 3.11; version-specific types added later (for
example ``collections.abc.Buffer`` in Python 3.12) are deliberately unknown.
They are not a replacement for complete stubs or a Python interpreter.  Facts
come from the corresponding Python library reference and CPython Lib classes:
https://docs.python.org/3/library/collections.abc.html
https://docs.python.org/3/library/typing.html
https://docs.python.org/3/library/http.cookiejar.html
https://docs.python.org/3/library/json.html#json.JSONDecodeError
https://docs.python.org/3/library/io.html#io.UnsupportedOperation
"""
from __future__ import annotations

import ast
from dataclasses import dataclass, replace

MODEL_VERSION = 'python-stdlib-public-types-2'
PYTHON_VERSION = '3.11'
PROVENANCE = {
    'implementation': 'CPython 3.11.15',
    'upstream': 'https://github.com/python/cpython/tree/v3.11.15',
    'source_sha256': {
        'Lib/_collections_abc.py': 'ec646ef7e27aae261adef3c57b9d18822c6526b3e9562dabb9f3cb4e6803066c',
        'Lib/abc.py': 'e558702a95cdce3febd289da021715d2b92bc43995b8a1bc58dfa1c3d8010287',
        'Lib/typing.py': 'eff3df4f1d65e13d690b8f427cada4dd3b88431dd1e7f319fda1bd0062113203',
        'Lib/http/cookiejar.py': '9587a95edc194a19513e8a8fa9a942cd9fe6217489697ee998a7ae544fb9d603',
        'Lib/json/decoder.py': '9f02654649816145bc76f8c210a5fe3ba1de142d4d97a1c93105732e747c285b',
        'Lib/io.py': '12636601d4f488b583cff41668c3a386c3b2d93499df09de0df9d9a2a4b95194',
        'Lib/socket.py': '64360e73e3db69396d45d5ee256e8306b3653212ab96ae4a130070488cddbb30',
        'Lib/netrc.py': '6394e8e650d04c26ed20b6058d5e93119f544ef1bd00aefb942297d2e2f6c7e1',
    },
    'validation': 'bases, aliases, own member inventory and signatures checked against CPython 3.11; analysed project modules are never imported',
}


@dataclass(frozen=True)
class ClassModel:
    bases: tuple[str, ...] = ('builtins.object',)
    generic: bool = False
    signatures: tuple[str, ...] = ()
    own_members: frozenset[str] = frozenset()


CLASSES = {
    'abc.ABC': ClassModel(),
    'typing.Generic': ClassModel(generic=True),
    'typing.Protocol': ClassModel(('typing.Generic',), generic=True),
    'json.decoder.JSONDecodeError': ClassModel(('builtins.ValueError',), signatures=('__init__(self, msg, doc, pos)',)),
    'io.UnsupportedOperation': ClassModel(('builtins.OSError', 'builtins.ValueError')),
    'socket.gaierror': ClassModel(('builtins.OSError',)),
    'socket.herror': ClassModel(('builtins.OSError',)),
    'netrc.NetrcParseError': ClassModel(('builtins.Exception',), signatures=('__init__(self, msg, filename=None, lineno=None)',)),
    'http.cookiejar.Cookie': ClassModel(),
    'http.cookiejar.CookiePolicy': ClassModel(),
    'http.cookiejar.DefaultCookiePolicy': ClassModel(('http.cookiejar.CookiePolicy',)),
    'http.cookiejar.CookieJar': ClassModel(signatures=(
        '__init__(self, policy=None)', 'set_policy(self, policy)',
        'make_cookies(self, response, request)', 'set_cookie(self, cookie)',
        'set_cookie_if_ok(self, cookie, request)', 'add_cookie_header(self, request)',
        'extract_cookies(self, response, request)', 'clear(self, domain=None, path=None, name=None)',
        'clear_session_cookies(self)', 'clear_expired_cookies(self)',
        '__iter__(self)', '__len__(self)', '__repr__(self)', '__str__(self)',
    )),
    'http.cookiejar.FileCookieJar': ClassModel(('http.cookiejar.CookieJar',), signatures=(
        '__init__(self, filename=None, delayload=False, policy=None)',
        'save(self, filename=None, ignore_discard=False, ignore_expires=False)',
        'load(self, filename=None, ignore_discard=False, ignore_expires=False)',
        'revert(self, filename=None, ignore_discard=False, ignore_expires=False)',
    )),
    'http.cookiejar.LWPCookieJar': ClassModel(('http.cookiejar.FileCookieJar',)),
    'http.cookiejar.MozillaCookieJar': ClassModel(('http.cookiejar.FileCookieJar',)),
    'http.cookiejar.LoadError': ClassModel(('builtins.OSError',)),
}

# Direct bases matter to C3; collapsing all ABCs to object loses real order facts.
_ABC_BASES = {
    'Hashable': (), 'Awaitable': (), 'Coroutine': ('Awaitable',),
    'AsyncIterable': (), 'AsyncIterator': ('AsyncIterable',), 'AsyncGenerator': ('AsyncIterator',),
    'Iterable': (), 'Iterator': ('Iterable',), 'Generator': ('Iterator',),
    'Reversible': ('Iterable',), 'Sized': (), 'Container': (), 'Callable': (),
    'Collection': ('Sized', 'Iterable', 'Container'), 'Set': ('Collection',),
    'MutableSet': ('Set',), 'Mapping': ('Collection',), 'MutableMapping': ('Mapping',),
    'MappingView': ('Sized',), 'KeysView': ('MappingView', 'Set'),
    'ItemsView': ('MappingView', 'Set'), 'ValuesView': ('MappingView', 'Collection'),
    'Sequence': ('Reversible', 'Collection'), 'MutableSequence': ('Sequence',),
    'ByteString': ('Sequence',),
}
_ABC_SIGNATURES = {
    'Hashable': ('__hash__(self)',), 'Awaitable': ('__await__(self)',),
    'AsyncIterable': ('__aiter__(self)',), 'AsyncIterator': ('__anext__(self)',),
    'Iterable': ('__iter__(self)',), 'Iterator': ('__next__(self)',),
    'Reversible': ('__reversed__(self)',), 'Sized': ('__len__(self)',),
    'Container': ('__contains__(self, x)',),
    'Mapping': ('__getitem__(self, key)', '__contains__(self, key)', 'get(self, key, default=None)',
                'keys(self)', 'items(self)', 'values(self)', '__eq__(self, other)'),
    'MutableMapping': ('__setitem__(self, key, value)', '__delitem__(self, key)',
                      'pop(self, key, default=None)', 'popitem(self)', 'clear(self)',
                      'update(self, other=(), /, **kwds)', 'setdefault(self, key, default=None)'),
    'Sequence': ('__getitem__(self, index)', 'index(self, value, start=0, stop=None)', 'count(self, value)'),
    'KeysView': ('__contains__(self, key)', '__iter__(self)'),
    'ItemsView': ('__contains__(self, item)', '__iter__(self)'),
    'ValuesView': ('__contains__(self, value)', '__iter__(self)'),
    'MutableSequence': ('__setitem__(self, index, value)', '__delitem__(self, index)',
                        'insert(self, index, value)', 'append(self, value)', 'clear(self)',
                        'reverse(self)', 'extend(self, values)', 'pop(self, index=-1)', 'remove(self, value)'),
}
for _name, _bases in _ABC_BASES.items():
    CLASSES['collections.abc.' + _name] = ClassModel(
        tuple('collections.abc.' + base for base in _bases) or ('builtins.object',),
        generic=_name not in {'Hashable', 'Sized'},
        signatures=_ABC_SIGNATURES.get(_name, ()),
    )

# Complete own-member inventories for the pinned model classes.  This is
# presence information, not executable code: an absent member lets C3 proceed
# to the next base; a present member without a checked signature stays unknown.
# CPython automatically generated metadata (__dict__, __doc__, __module__,
# __weakref__, __slots__, __abstractmethods__, _abc_impl) is excluded.
_OWN_MEMBERS = {
    'typing.Generic': '__class_getitem__ __init_subclass__ _is_protocol',
    'typing.Protocol': '__init_subclass__ __parameters__ _is_protocol _is_runtime_protocol',
    'json.decoder.JSONDecodeError': '__init__ __reduce__',
    'netrc.NetrcParseError': '__init__ __str__',
    'http.cookiejar.Cookie': '__init__ __repr__ __str__ get_nonstandard_attr has_nonstandard_attr is_expired set_nonstandard_attr',
    'http.cookiejar.CookiePolicy': 'domain_return_ok path_return_ok return_ok set_ok',
    'http.cookiejar.DefaultCookiePolicy': 'DomainLiberal DomainRFC2965Match DomainStrict DomainStrictNoDots DomainStrictNonDomain __init__ allowed_domains blocked_domains domain_return_ok is_blocked is_not_allowed path_return_ok return_ok return_ok_domain return_ok_expires return_ok_port return_ok_secure return_ok_verifiability return_ok_version set_allowed_domains set_blocked_domains set_ok set_ok_domain set_ok_name set_ok_path set_ok_port set_ok_verifiability set_ok_version',
    'http.cookiejar.CookieJar': '__init__ __iter__ __len__ __repr__ __str__ _cookie_attrs _cookie_from_cookie_tuple _cookies_for_domain _cookies_for_request _cookies_from_attrs_set _normalized_cookie_tuples _process_rfc2109_cookies add_cookie_header clear clear_expired_cookies clear_session_cookies domain_re dots_re extract_cookies magic_re make_cookies non_word_re quote_re set_cookie set_cookie_if_ok set_policy strict_domain_re',
    'http.cookiejar.FileCookieJar': '__init__ load revert save',
    'http.cookiejar.LWPCookieJar': '_really_load as_lwp_str save',
    'http.cookiejar.MozillaCookieJar': '_really_load save',
    'collections.abc.Hashable': '__hash__ __subclasshook__',
    'collections.abc.Awaitable': '__await__ __class_getitem__ __subclasshook__',
    'collections.abc.Coroutine': '__subclasshook__ close send throw',
    'collections.abc.AsyncIterable': '__aiter__ __class_getitem__ __subclasshook__',
    'collections.abc.AsyncIterator': '__aiter__ __anext__ __subclasshook__',
    'collections.abc.AsyncGenerator': '__anext__ __subclasshook__ aclose asend athrow',
    'collections.abc.Iterable': '__class_getitem__ __iter__ __subclasshook__',
    'collections.abc.Iterator': '__iter__ __next__ __subclasshook__',
    'collections.abc.Generator': '__next__ __subclasshook__ close send throw',
    'collections.abc.Reversible': '__reversed__ __subclasshook__',
    'collections.abc.Sized': '__len__ __subclasshook__',
    'collections.abc.Container': '__class_getitem__ __contains__ __subclasshook__',
    'collections.abc.Callable': '__call__ __class_getitem__ __subclasshook__',
    'collections.abc.Collection': '__subclasshook__',
    'collections.abc.Set': '__and__ __eq__ __ge__ __gt__ __hash__ __le__ __lt__ __or__ __rand__ __ror__ __rsub__ __rxor__ __sub__ __xor__ _from_iterable _hash isdisjoint',
    'collections.abc.MutableSet': '__iand__ __ior__ __isub__ __ixor__ add clear discard pop remove',
    'collections.abc.Mapping': '__contains__ __eq__ __getitem__ __hash__ __reversed__ get items keys values',
    'collections.abc.MutableMapping': '_MutableMapping__marker __delitem__ __setitem__ clear pop popitem setdefault update',
    'collections.abc.MappingView': '__class_getitem__ __init__ __len__ __repr__ _mapping',
    'collections.abc.KeysView': '__contains__ __iter__ _from_iterable',
    'collections.abc.ItemsView': '__contains__ __iter__ _from_iterable',
    'collections.abc.ValuesView': '__contains__ __iter__',
    'collections.abc.Sequence': '__contains__ __getitem__ __iter__ __reversed__ count index',
    'collections.abc.MutableSequence': '__delitem__ __iadd__ __setitem__ append clear extend insert pop remove reverse',
}
for _name, _model in list(CLASSES.items()):
    CLASSES[_name] = replace(_model, own_members=frozenset(_OWN_MEMBERS.get(_name, '').split()))

ALIASES = {
    'json.JSONDecodeError': 'json.decoder.JSONDecodeError',
    'socket.error': 'builtins.OSError', 'socket.timeout': 'builtins.TimeoutError',
    'io.BlockingIOError': 'builtins.BlockingIOError',
}
for _name in _ABC_BASES:
    ALIASES['typing.' + _name] = 'collections.abc.' + _name
ALIASES.update({'typing.List': 'builtins.list', 'typing.Dict': 'builtins.dict',
                'typing.Set': 'builtins.set', 'typing.FrozenSet': 'builtins.frozenset',
                'typing.Tuple': 'builtins.tuple', 'typing.Type': 'builtins.type'})

MODULES = frozenset('.'.join(name.split('.')[:length])
                    for name in (*CLASSES, *ALIASES) for length in range(1, len(name.split('.'))))
GENERIC_BUILTINS = frozenset({'list', 'dict', 'set', 'frozenset', 'tuple', 'type'})
METHODS = {name: {node.name: node for signature in model.signatures
                 for node in ast.parse('def ' + signature + ': ...').body}
           for name, model in CLASSES.items()}


def canonical_name(module, name):
    qualified = module + '.' + name
    return ALIASES.get(qualified, qualified) if qualified in CLASSES or qualified in ALIASES else None
