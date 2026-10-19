"""CodeArts Python catalog checks using Python's parser and tokenizer.

The exported catalog contains titles/options, not executable upstream rules.
`implemented` is reserved for a local rule whose stated syntax is decidable;
partial checks explicitly record semantic limits in the companion manifest.
No finding from this module claims equivalence to Huawei's private engine.
"""
from __future__ import annotations

import ast
import builtins
from bisect import bisect_left, bisect_right
import io
import json
from pathlib import Path
import re
import sys
import tokenize

MANIFEST = Path(__file__).resolve().parents[1] / 'rulesets' / 'implementations' / 'python.json'
FUNCTIONS = (ast.FunctionDef, ast.AsyncFunctionDef)
NUMERIC_MAGIC = {'__add__', '__sub__', '__mul__', '__matmul__', '__truediv__', '__floordiv__',
                 '__mod__', '__divmod__', '__pow__', '__lshift__', '__rshift__', '__and__', '__xor__', '__or__',
                 '__radd__', '__rsub__', '__rmul__', '__rtruediv__', '__rfloordiv__', '__rmod__', '__rpow__',
                 '__iadd__', '__isub__', '__imul__', '__itruediv__', '__ifloordiv__', '__imod__', '__ipow__'}
KNOWN_MAGIC = set(dir(object)) | NUMERIC_MAGIC | {'__len__','__length_hint__','__iter__','__next__',
    '__getitem__','__setitem__','__delitem__','__contains__','__bool__','__bytes__','__index__','__int__',
    '__float__','__complex__','__enter__','__exit__','__aenter__','__aexit__','__await__','__aiter__','__anext__',
    '__getnewargs__','__getnewargs_ex__','__getstate__','__setstate__','__missing__','__slots__','__all__',
    '__name__','__file__','__package__','__spec__','__doc__','__annotations__','__version__','__path__',
    '__cached__','__loader__','__builtins__','__module__','__qualname__','__classcell__','__match_args__',
    '__set_name__','__get__','__set__','__delete__','__class_getitem__','__mro_entries__','__init_subclass__',
    '__prepare__','__instancecheck__','__subclasscheck__','__subclasshook__','__reversed__','__round__',
    '__trunc__','__floor__','__ceil__','__fspath__','__reduce__','__reduce_ex__','__buffer__','__release_buffer__'}
KNOWN_MAGIC.update({'__get__','__set__','__delete__','__set_name__','__mro_entries__',
                    '__class_getitem__','__init_subclass__','__buffer__','__release_buffer__'})
SENSITIVE = {'password','passwd','secret','token','api_key','apikey','private_key','credential'}


def rule_key(rule):
    title = rule.get('nameCn') or rule['name']
    return title.split()[0] + (':' + title.split('--', 1)[1] if '--' in title else '')


def literal(node):
    try:
        return ast.literal_eval(node)
    except (ValueError, TypeError, SyntaxError, MemoryError, RecursionError):
        return UNKNOWN


UNKNOWN = object()


def wildcard_fragments(node):
    """Literal string fragments of a command assembled via +, %, f-string, or
    str.format, without descending into arbitrary helper calls. A wildcard in
    any fragment will appear verbatim in the assembled shell command, so the
    glob will expand even when part of the command is non-literal."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        yield node.value
    elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        yield from wildcard_fragments(node.left)
        yield from wildcard_fragments(node.right)
    elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mod):
        # "fmt %s" % args — the format string and any string-literal args.
        yield from wildcard_fragments(node.left)
        rhs = node.right
        if isinstance(rhs, (ast.Tuple, ast.List)):
            for elt in rhs.elts:
                yield from wildcard_fragments(elt)
        else:
            yield from wildcard_fragments(rhs)
    elif isinstance(node, ast.JoinedStr):
        for value in node.values:
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                yield value.value
            elif isinstance(value, ast.FormattedValue):
                # format spec like f"{x:*>10}" holds literal chars in format_spec.
                yield from wildcard_fragments(value.format_spec)
    elif (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
          and node.func.attr == 'format'):
        yield from wildcard_fragments(node.func.value)
        for arg in node.args:
            yield from wildcard_fragments(arg)
        for kw in node.keywords:
            yield from wildcard_fragments(kw.value)


def dotted(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = dotted(node.value)
        return base + '.' + node.attr if base else node.attr
    return ''


def local_walk(node):
    """Visit one lexical scope, including expressions but excluding child scopes."""
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
            continue
        yield child
        yield from local_walk(child)


def assigned_names(node):
    return {x.id for x in ast.walk(node) if isinstance(x, ast.Name) and isinstance(x.ctx, ast.Store)}


def args_of(node):
    return list(node.args.posonlyargs) + list(node.args.args) + list(node.args.kwonlyargs)


def infer(node):
    value = literal(node)
    if value is not UNKNOWN:
        return type(value).__name__
    if isinstance(node, ast.Call):
        name = dotted(node.func)
        if name in {'str','int','float','bool','bytes','list','tuple','dict','set'}:
            return name
        if name in {'iter','next'}:
            return 'iterator' if name == 'iter' else None
    return None


class Analyzer:
    def __init__(self, path, text):
        self.original_text = text
        text = text[1:] if text.startswith('\ufeff') else text
        self.path, self.text = path, text
        self.lines = text.splitlines()
        self.tree = ast.parse(text, filename=path)
        self.tokens = list(tokenize.generate_tokens(io.StringIO(text).readline))
        self.nodes = list(ast.walk(self.tree))
        self.parents = {child: node for node in self.nodes for child in ast.iter_child_nodes(node)}
        self.hits = {}
        self._scope_cache = {}
        self.imports = {}
        for n in self.nodes:
            if isinstance(n, ast.Import):
                for alias in n.names:
                    self.imports[alias.asname or alias.name.split('.')[0]] = alias.name if alias.asname else alias.name.split('.')[0]
            elif isinstance(n, ast.ImportFrom):
                for alias in n.names:
                    self.imports[alias.asname or alias.name] = (n.module or '') + '.' + alias.name
        self.assignments = {}
        self.functions = {n.name:n for n in self.tree.body if isinstance(n, FUNCTIONS)}
        self.classes = {n.name:n for n in self.tree.body if isinstance(n, ast.ClassDef)}
        self.module_names = self.bindings(self.tree)
        # Assignment provenance is keyed by lexical scope; values are resolved at use sites.
        # Track direct assignment provenance in source order; not interprocedural.
        for n in sorted(self.nodes, key=lambda x:(getattr(x,'lineno',0),getattr(x,'col_offset',0))):
            if isinstance(n, (ast.Assign, ast.AnnAssign)) and n.value is not None:
                targets=n.targets if isinstance(n, ast.Assign) else [n.target]
                for target in targets:
                    for name in assigned_names(target):
                        self.assignments.setdefault((next(self.lexical_scopes(n),self.tree),name),[]).append((n.lineno,n.value))

    def bindings(self, scope):
        out={}
        for n in scope.body:
            if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)):
                out[n.name]=n
            elif isinstance(n,(ast.Import,ast.ImportFrom)):
                for a in n.names:out[a.asname or a.name.split('.')[0]]=n
            elif isinstance(n,(ast.Assign,ast.AnnAssign)):
                for name in assigned_names(n):out[name]=n
        return out

    def lexical_scopes(self,node):
        child=node
        parent=self.parents.get(child)
        crossed_function=False
        while parent is not None:
            if isinstance(parent,(*FUNCTIONS,ast.Lambda)):
                in_body=child is parent.body if isinstance(parent,ast.Lambda) else child in parent.body
                if in_body:
                    yield parent
                    crossed_function=True
            elif isinstance(parent,ast.ClassDef) and not crossed_function and child in parent.body:
                yield parent
            elif isinstance(parent,ast.Module):
                yield parent
            child,parent=parent,self.parents.get(parent)

    def scope_bindings(self,scope):
        if scope in self._scope_cache:return self._scope_cache[scope]
        bindings={}
        def add(name,node,value=None):
            bindings.setdefault(name,[]).append((getattr(node,'lineno',0),value))
        def walk(node):
            for child in ast.iter_child_nodes(node):
                if isinstance(child,(*FUNCTIONS,ast.ClassDef)):
                    add(child.name,child)
                    continue
                if isinstance(child,ast.Lambda):continue
                if isinstance(child,ast.Import):
                    for a in child.names:add(a.asname or a.name.split('.')[0],child,a.name if a.asname else a.name.split('.')[0])
                elif isinstance(child,ast.ImportFrom):
                    for a in child.names:add(a.asname or a.name,child,(child.module or '')+'.'+a.name)
                elif isinstance(child,ast.Name) and isinstance(child.ctx,ast.Store):add(child.id,child)
                elif isinstance(child,ast.ExceptHandler) and child.name:add(child.name,child)
                walk(child)
        if isinstance(scope,(*FUNCTIONS,ast.Lambda)):
            for a in args_of(scope):add(a.arg,scope)
            for a in (scope.args.vararg,scope.args.kwarg):
                if a:add(a.arg,scope)
        walk(scope)
        self._scope_cache[scope]=bindings
        return bindings

    def name(self, node):
        raw=dotted(node)
        root, _, rest=raw.partition('.')
        if not root:return raw
        position=getattr(node,'lineno',10**9)
        for scope in self.lexical_scopes(node):
            candidates=self.scope_bindings(scope).get(root,[])
            earlier=[b for b in candidates if b[0]<=position]
            if earlier:
                value=earlier[-1][1]
                base=value if value is not None else '@local:'+root
                return base+('.'+rest if rest else '')
            if candidates and isinstance(scope,(*FUNCTIONS,ast.Lambda)):
                return '@local:'+raw
        return raw

    def value_before(self, name, line, at=None):
        scopes=list(self.lexical_scopes(at)) if at is not None else [self.tree]
        for scope in scopes:
            values=[v for l,v in self.assignments.get((scope,name),[]) if l<line]
            if values:return values[-1]
            if name in self.scope_bindings(scope) and isinstance(scope,(*FUNCTIONS,ast.Lambda)):return None
        return None

    def external(self, node, visited=None):
        visited=set() if visited is None else set(visited)
        if node is None or id(node) in visited or len(visited)>64:return False
        visited.add(id(node))
        for n in ast.walk(node):
            if isinstance(n,ast.Name):
                value=self.value_before(n.id,n.lineno,n)
                if value is not None and self.external(value,visited):return True
            if isinstance(n,ast.Call) and self.name(n.func) in {'input','builtins.input','sys.stdin.read','sys.stdin.readline','os.getenv'}:return True
            if isinstance(n,ast.Attribute) and self.name(n).startswith(('request.','sys.argv','os.environ')):return True
            if isinstance(n,ast.Name) and self.name(n) in {'sys.argv','os.environ'}:return True
        return False

    def is_normalized(self,node,visited=None):
        visited=set() if visited is None else set(visited)
        if node is None or id(node) in visited:return False
        visited.add(id(node))
        if isinstance(node,ast.Call) and self.name(node.func) in {'os.path.realpath','os.path.abspath','os.path.normpath','pathlib.Path.resolve'}:return True
        if isinstance(node,ast.Name):return self.is_normalized(self.value_before(node.id,node.lineno,node),visited)
        return False

    def sensitive(self,node):
        for n in ast.walk(node):
            name=n.id if isinstance(n,ast.Name) else n.value if isinstance(n,ast.Constant) and isinstance(n.value,str) else ''
            if any(part in SENSITIVE for part in re.split(r'[^a-z0-9]+',name.lower())):return True
        return False

    def hit(self,key,node,message=None):
        if isinstance(node,tokenize.TokenInfo):line,col=node.start[0],node.start[1]+1
        elif isinstance(node,tuple):line,col=node
        else:
            line,col=self.ast_position(node)
            col+=1
        self.hits.setdefault(key,[]).append((line,col,message))

    def ast_position(self,node,end=False):
        line=getattr(node,'end_lineno' if end else 'lineno',1)
        byte=getattr(node,'end_col_offset' if end else 'col_offset',0)
        source=self.lines[line-1] if 0<line<=len(self.lines) else ''
        return line,len(source.encode('utf-8')[:byte].decode('utf-8',errors='ignore'))

    def ancestor(self,node,types):
        n=self.parents.get(node)
        while n:
            if isinstance(n,types):return n
            n=self.parents.get(n)
        return None

    def run(self):
        self.format_checks()
        self.scope_checks()
        for n in self.nodes:self.node_checks(n)
        return self.hits

    def format_checks(self):
        lines=self.lines
        newline_types={m.group(0) for m in re.finditer(r'\r\n|(?<!\r)\n',self.text)}
        if len(newline_types)>1:self.hit('G.FMT.10',(1,1))
        for line,s in enumerate(lines,1):
            if len(s)>120:self.hit('G.FMT.02',(line,121))
        for line,s in enumerate(lines[:2],1):
            coding=re.search(r'coding\s*[:=]\s*([-\w.]+)',s) if s.lstrip().startswith('#') else None
            if coding and coding.group(1).lower().replace('_','-') not in {'utf-8','utf8'}:self.hit('G.PRJ.04',(line,1))
        tokens=self.tokens
        code_tokens=[t for t in tokens if t.type not in {tokenize.ENCODING,tokenize.NL,tokenize.NEWLINE,tokenize.INDENT,tokenize.DEDENT,tokenize.COMMENT,tokenize.ENDMARKER}]
        positions=[t.start for t in code_tokens]
        binary_positions=set()
        default_equal_positions=set()
        for n in self.nodes:
            if isinstance(n,ast.BinOp):
                start,end=self.ast_position(n.left,True),self.ast_position(n.right)
                for t in code_tokens[bisect_left(positions,start):bisect_right(positions,end)]:
                    if t.end<=end:binary_positions.add(t.start)
            if isinstance(n,ast.AugAssign):
                start,end=self.ast_position(n.target,True),self.ast_position(n.value)
                for t in code_tokens[bisect_left(positions,start):bisect_right(positions,end)]:
                    if t.end<=end:binary_positions.add(t.start)
            if isinstance(n,(*FUNCTIONS,ast.Lambda)):
                positional=list(n.args.posonlyargs)+list(n.args.args)
                defaults=list(zip(positional[-len(n.args.defaults):],n.args.defaults)) if n.args.defaults else []
                defaults+=list(zip(n.args.kwonlyargs,n.args.kw_defaults))
                for arg,default in defaults:
                    if default is None or arg.annotation is not None:continue
                    start,end=self.ast_position(arg,True),self.ast_position(default)
                    for t in code_tokens[bisect_left(positions,start):bisect_right(positions,end)]:
                        if t.string=='=':default_equal_positions.add(t.start)
        indentation=[0]
        for i,t in enumerate(tokens):
            if t.type==tokenize.INDENT:
                width=len(t.string.expandtabs(8))
                if '\t' in t.string or width-indentation[-1]!=4:self.hit('G.FMT.01',t)
                indentation.append(width)
            elif t.type==tokenize.DEDENT and len(indentation)>1:indentation.pop()
            if t.type==tokenize.COMMENT:
                if re.search(r'\b(?:TODO|FIXME)\b',t.string):self.hit('G.CMT.05',t)
                before=t.line[:t.start[1]]
                if (not t.string.startswith(('#!','# -*-')) and len(t.string)>1 and t.string[1] not in ' #\t-' and not re.search(r'coding[:=]',t.string)) or (before.strip() and not before.endswith('  ')):
                    self.hit('G.CMT.04',t)
        for i,t in enumerate(code_tokens):
            before=code_tokens[i-1] if i else None
            after=code_tokens[i+1] if i+1<len(code_tokens) else None
            if t.type==tokenize.OP and t.string==';':self.hit('G.FMT.08:分号',t)
            if t.type==tokenize.OP and t.string in {',',';',':'} and after and after.start[0]==t.end[0] and after.start[1]==t.end[1] and after.string not in {')',']','}'}:
                # Slice separators have their own whitespace convention.
                if t.string!=':' or not any(isinstance(n,ast.Slice) and self._token_in_node(t,n) for n in self.nodes):self.hit('G.FMT.04:分隔符',t)
            if t.type==tokenize.NAME and t.string in {'if','elif','while','for','with','except','return','yield','assert','import','from','not','and','or','in','is','await','raise','del','lambda'} and after and after.start[0]==t.end[0] and after.start[1]==t.end[1] and after.string not in {':',',',';'} and not(t.string=='except' and after.string=='*'):
                self.hit('G.FMT.04:关键字后',t)
            if t.string=='*' and before and before.string=='except' and after and after.start==t.end:
                self.hit('G.FMT.04:关键字后',t)
            keys={'%':'G.FMT.04:取余操作符','&':'G.FMT.04:位运算操作符','|':'G.FMT.04:位运算操作符','^':'G.FMT.04:位运算操作符','<<':'G.FMT.04:位运算操作符','>>':'G.FMT.04:位运算操作符','+':'G.FMT.04:算术操作符','-':'G.FMT.04:算术操作符','*':'G.FMT.04:算术操作符','/':'G.FMT.04:算术操作符','//':'G.FMT.04:算术操作符','**':'G.FMT.04:算术操作符','@':'G.FMT.04:算术操作符'}
            operator=t.string.removesuffix('=')
            if t.start in binary_positions and operator in keys and before and after:
                if before.end==t.start or after.start==t.end:self.hit(keys[operator],t)
            if t.string in {'and','or','in','is'} and before and after and (before.end==t.start or after.start==t.end):
                self.hit('G.FMT.04',t)
            if t.type==tokenize.NAME and t.string in {'in','is','and','or'} and before and before.end==t.start:
                self.hit('G.FMT.04',t)
            if t.string in {'=','==','!=','<','>','<=','>=','+=','-=','*=','/=','//=','%=','&=','|=','^=','<<=','>>=','**=','@=',':='} and before and after:
                # Keyword/default argument '=' deliberately excluded.
                in_argument=t.string=='=' and (t.start in default_equal_positions or any(isinstance(n,ast.keyword) and self._token_in_node(t,n) for n in self.nodes))
                if not in_argument and (before.end==t.start or after.start==t.end):self.hit('G.FMT.04',t)
        for n in self.nodes:
            if isinstance(n,(ast.If,ast.For,ast.AsyncFor,ast.While,ast.With,ast.AsyncWith,ast.Try)) and n.body and n.body[0].lineno==n.lineno:self.hit('G.FMT.08',n)
            if isinstance(n,(*FUNCTIONS,ast.ClassDef)) and n.body and n.body[0].lineno==n.lineno:self.hit('G.FMT.08:定义',n)
            if hasattr(n,'body') and isinstance(n.body,list):
                prior=None
                for statement in n.body:
                    if prior and (isinstance(statement,(*FUNCTIONS,ast.ClassDef)) or isinstance(prior,(*FUNCTIONS,ast.ClassDef))):
                        start=min([statement.lineno]+[d.lineno for d in getattr(statement,'decorator_list',[])])
                        blank=sum(not lines[j-1].strip() for j in range(prior.end_lineno+1,start))
                        if isinstance(n,ast.Module) and blank<2:self.hit('G.FMT.03:类间空2行',statement)
                        elif isinstance(n,ast.ClassDef) and blank<1:self.hit('G.FMT.03:类内方法空1行',statement)
                        elif isinstance(n,FUNCTIONS) and blank<1:self.hit('G.FMT.03:嵌套定义空1行',statement)
                    prior=statement

    def _token_in_node(self,token,node):
        return hasattr(node,'lineno') and self.ast_position(node)<=token.start<=self.ast_position(node,True)

    def scope_checks(self):
        if self.tree.body and ast.get_docstring(self.tree) is None:self.hit('G.CMT.01',self.tree.body[0])
        previous_group=-1
        for n in self.tree.body:
            if isinstance(n,(ast.Import,ast.ImportFrom)):
                name=n.names[0].name.split('.')[0] if isinstance(n,ast.Import) else (n.module or '').split('.')[0]
                group=2 if isinstance(n,ast.ImportFrom) and n.level else 0 if name in sys.stdlib_module_names else 1
                if group<previous_group:self.hit('G.FMT.07',n)
                previous_group=group
        for scope in [self.tree]+[n for n in self.nodes if isinstance(n,(*FUNCTIONS,ast.ClassDef))]:
            seen={}
            for n in local_walk(scope):
                if isinstance(n,(ast.Assign,ast.AnnAssign)) and n.value:
                    typ=infer(n.value)
                    targets=n.targets if isinstance(n,ast.Assign) else [n.target]
                    for target in targets:
                        if isinstance(target,ast.Name) and typ:
                            if target.id in seen and seen[target.id]!=typ:self.hit('G.VAR.01',n)
                            seen[target.id]=typ
        for n in self.nodes:
            if not hasattr(n,'body') or not isinstance(n.body,list):continue
            stopped=False
            for statement in n.body:
                if stopped:self.hit('G.CTL.02',statement)
                if isinstance(statement,(ast.Return,ast.Raise,ast.Break,ast.Continue)):stopped=True
        for n in self.nodes:
            if isinstance(n,ast.ClassDef):self.class_checks(n)
            if isinstance(n,FUNCTIONS):self.function_checks(n)
            if isinstance(n,ast.Lambda):self.mutable_defaults(n)

    def docstring_checks(self,node,key):
        if ast.get_docstring(node) is None:
            self.hit(key,node)
            return
        doc=node.body[0]
        begin=self.ast_position(node);end=self.ast_position(doc)
        colons=[t for t in self.tokens if t.type==tokenize.OP and t.string==':' and begin<=t.start<end]
        colon=colons[-1] if colons else None
        if colon is None or doc.lineno!=colon.start[0]+1 or doc.col_offset!=node.col_offset+4:
            self.hit(key,doc)

    def class_checks(self,node):
        self.docstring_checks(node,'G.CMT.02')
        if not re.fullmatch(r'_?[A-Z][A-Za-z0-9]*',node.name):self.hit('G.NAM.01',node)
        methods={m.name:m for m in node.body if isinstance(m,FUNCTIONS)}
        init=methods.get('__init__')
        init_attrs={x.attr for x in ast.walk(init) if isinstance(x,ast.Attribute) and isinstance(x.ctx,ast.Store) and dotted(x.value)=='self'} if init else set()
        for method in methods.values():
            all_args=list(method.args.posonlyargs)+list(method.args.args)
            decs={self.name(d.func if isinstance(d,ast.Call) else d) for d in method.decorator_list}
            is_static='staticmethod' in decs or method.name=='__new__'
            is_class='classmethod' in decs
            if not is_static:
                if not all_args:self.hit('G.NAM.03:没有参数',method)
                elif is_class and all_args[0].arg!='cls':self.hit('G.NAM.03:cls',method)
                elif not is_class and all_args[0].arg!='self':self.hit('G.NAM.03:self',method)
            if not is_static and not is_class and all_args and not method.name.startswith('__'):
                uses={x.id for x in ast.walk(method) if isinstance(x,ast.Name) and isinstance(x.ctx,ast.Load)}
                if all_args[0].arg not in uses and not decs and not any(isinstance(x,ast.Call) and dotted(x.func)=='super' for x in local_walk(method)):
                    self.hit('G.CLS.07',method)
            if method.name!='__init__':
                for x in local_walk(method):
                    if isinstance(x,ast.Attribute) and isinstance(x.ctx,ast.Store) and dotted(x.value)=='self' and x.attr not in init_attrs:self.hit('G.CLS.08',x)
            for base in ([] if getattr(self,'project',None) else node.bases):
                parent=self.classes.get(dotted(base))
                if not parent:continue
                originals={m.name:m for m in parent.body if isinstance(m,FUNCTIONS)}
                if method.name in originals and method.name not in {'__init__','__new__'}:
                    first,second=originals[method.name],method
                    sig=lambda f:([a.arg for a in f.args.posonlyargs],[a.arg for a in f.args.args],[a.arg for a in f.args.kwonlyargs],bool(f.args.vararg),bool(f.args.kwarg),len(f.args.defaults))
                    if sig(first)!=sig(second):self.hit('G.CLS.02',method)
                if method.name=='__init__' and '__init__' in originals:
                    calls=[x for x in local_walk(method) if isinstance(x,ast.Call)]
                    if not any(isinstance(x.func,ast.Attribute) and x.func.attr=='__init__' and (dotted(x.func.value)==parent.name or isinstance(x.func.value,ast.Call) and dotted(x.func.value.func)=='super') for x in calls):self.hit('G.CLS.01',method)
        if getattr(self,'project',None):self.project.class_checks(self,node)
        elif node.name.endswith(('Error','Exception')) and any(dotted(b)=='BaseException' for b in node.bases):self.hit('G.ERR.03',node)

    def function_checks(self,n):
        body=list(local_walk(n))
        if not n.name.startswith('_'):self.docstring_checks(n,'G.CMT.03')
        if not re.fullmatch(r'_?[a-z][a-z0-9_]*|__[a-z][a-z0-9_]*__',n.name):self.hit('G.NAM.01',n)
        if len(args_of(n))-(bool(args_of(n)) and args_of(n)[0].arg in {'self','cls'})>5:self.hit('G.FNM.03',n)
        self.mutable_defaults(n)
        returns=[x for x in body if isinstance(x,ast.Return)]
        kinds={('tuple',len(x.value.elts)) if isinstance(x.value,ast.Tuple) else (infer(x.value),1) if x.value is not None else ('NoneType',0) for x in returns}
        known={k for k in kinds if k[0] is not None}
        if len(known)>1:self.hit('G.CTL.01',n)
        if any(isinstance(x,(ast.Yield,ast.YieldFrom)) for x in body):
            for x in body:
                if isinstance(x,ast.Raise) and self.name(x.exc.func if isinstance(x.exc,ast.Call) else x.exc)=='StopIteration':self.hit('G.FNM.06',x)
        expected={'format':'str','length_hint':'int','hash':'int','bytes':'bytes','str':'str','repr':'str','index':'int','bool':'bool','len':'int','iter':'iterator','getnewargs':'tuple','getnewargs_ex':'tuple'}
        magic=n.name[2:-2] if n.name.startswith('__') and n.name.endswith('__') else ''
        if magic in expected:
            for ret in returns:
                val=literal(ret.value);kind=infer(ret.value)
                invalid=kind is not None and kind!=expected[magic] and not(expected[magic]=='int' and kind=='bool')
                if getattr(self,'project',None):
                    known=self.project.valid_magic_type(self.project.value_type(self,ret.value),expected[magic])
                    if known is not None:invalid=not known
                if magic in {'len','length_hint'} and isinstance(val,int) and val<0:invalid=True
                if magic=='getnewargs_ex' and val is not UNKNOWN:invalid=not(isinstance(val,tuple) and len(val)==2 and isinstance(val[0],tuple) and isinstance(val[1],dict))
                if invalid:self.hit('G.CLS.09:'+magic,ret)
        if n.name in NUMERIC_MAGIC:
            for x in body:
                if isinstance(x,ast.Raise) and self.name(x.exc.func if isinstance(x.exc,ast.Call) else x.exc)=='NotImplementedError':self.hit('G.CLS.10',x)
        globals_here={name for x in body if isinstance(x,ast.Global) for name in x.names}
        for x in body:
            if isinstance(x,ast.Name) and isinstance(x.ctx,ast.Store) and x.id in self.module_names and x.id not in globals_here:self.hit('G.VAR.03',x)
        nested={x.name:x for x in n.body if isinstance(x,FUNCTIONS)}
        for ret in returns:
            if isinstance(ret.value,ast.Name) and ret.value.id in nested:
                wrap=nested[ret.value.id]
                calls=[x for x in local_walk(wrap) if isinstance(x,ast.Call)]
                params={a.arg for a in args_of(n)}
                if any(isinstance(x.func,ast.Name) and x.func.id in params for x in calls) and not any(self.name(d.func if isinstance(d,ast.Call) else d)=='functools.wraps' for d in wrap.decorator_list):self.hit('G.PSL.04',wrap)

    def mutable_defaults(self,n):
        for default in n.args.defaults+n.args.kw_defaults:
            if self.is_mutable_default(default):self.hit('G.FNM.01',default)

    def is_mutable_default(self,node,visited=None):
        visited=set() if visited is None else set(visited)
        if node is None or id(node) in visited:return False
        visited.add(id(node))
        if isinstance(node,(ast.List,ast.Dict,ast.Set,ast.ListComp,ast.DictComp,ast.SetComp)):return True
        if isinstance(node,ast.Call):
            return self.name(node.func) in {'list','dict','set','collections.defaultdict','collections.deque','collections.OrderedDict','builtins.list','builtins.dict','builtins.set'}
        if isinstance(node,ast.Name):return self.is_mutable_default(self.value_before(node.id,node.lineno,node),visited)
        if isinstance(node,ast.Tuple):return any(self.is_mutable_default(x,visited) for x in node.elts)
        return False

    def node_checks(self,n):
        if isinstance(n,ast.Dict):
            seen={}
            for k in n.keys:
                if k is None:continue
                v=literal(k)
                try:
                    if v is not UNKNOWN and v in seen:self.hit('G.TYP.06',k)
                    elif v is not UNKNOWN:seen[v]=k
                except TypeError:pass
        if isinstance(n,(ast.Assign,ast.AnnAssign)):
            if isinstance(n.value,ast.Lambda):self.hit('G.EXP.03',n)
            targets=n.targets if isinstance(n,ast.Assign) else [n.target]
            for t in targets:
                for name in assigned_names(t):
                    if name in self.imports:self.hit('G.NAM.04',n)
            if isinstance(n.value,ast.Call):
                if getattr(self,'project',None):self.project.assigned_void_result(self,n)
                else:
                    f=self.functions.get(dotted(n.value.func))
                    if f and not isinstance(f,ast.AsyncFunctionDef) and not f.decorator_list and not any(isinstance(x,(ast.Yield,ast.YieldFrom)) or isinstance(x,ast.Return) and x.value is not None for x in local_walk(f)):
                        self.hit('G.FNM.04',n)
        if isinstance(n,(ast.Name,ast.Attribute)) and isinstance(n.ctx,ast.Store) or isinstance(n,(*FUNCTIONS,ast.ClassDef,ast.arg)):
            name=n.id if isinstance(n,ast.Name) else n.attr if isinstance(n,ast.Attribute) else n.arg if isinstance(n,ast.arg) else n.name
            if name.startswith('__') and name.endswith('__') and name not in KNOWN_MAGIC:self.hit('G.NAM.05',n)
        if isinstance(n,ast.Global):
            for name in n.names:
                if name not in self.module_names:self.hit('G.VAR.02',n)
        if isinstance(n,ast.Return):
            if isinstance(n.value,ast.Tuple) and len(n.value.elts)>3:self.hit('G.FNM.05',n)
            if isinstance(n.value,ast.Call) and self.name(n.value.func).endswith(('Error','Exception')):self.hit('G.ERR.02',n)
        if isinstance(n,ast.Raise):
            if getattr(self,'project',None):self.project.raised_exception(self,n)
            if isinstance(n.exc,(ast.Constant,ast.Tuple,ast.List,ast.Dict,ast.Set)):self.hit('G.ERR.06',n)
            if n.exc is not None and self.sensitive(n.exc):self.hit('G.ERR.08',n)
            excname=self.name(n.exc.func if isinstance(n.exc,ast.Call) else n.exc)
            if excname in {'Exception','BaseException'}:self.hit('G.ERR.05',n)
            if excname=='SystemExit' and not self.in_main(n):self.hit('G.ERR.11',n)
        if isinstance(n,ast.Assert) and not self.is_test_file():self.hit('G.TES.01',n)
        if isinstance(n,ast.NamedExpr):self.hit('G.OPR.04',n)
        if isinstance(n,ast.BinOp):
            if isinstance(n.op,(ast.Div,ast.FloorDiv,ast.Mod)) and literal(n.right)==0:self.hit('G.OPR.01',n)
            if isinstance(n.op,ast.Add):
                constants=[x.value for x in ast.walk(n) if isinstance(x,ast.Constant) and isinstance(x.value,str)]
                if self.external(n) and any('<' in v and '>' in v for v in constants):self.hit('G.EDV.09',n)
                if any(v in {'/','\\'} for v in constants):self.hit('G.FIO.05',n)
        if isinstance(n,ast.Compare):
            operands=[n.left]+list(n.comparators)
            for left,op,right in zip(operands,n.ops,operands[1:]):
                vals=(literal(left),literal(right))
                if isinstance(op,(ast.Eq,ast.NotEq)) and None in vals:self.hit('G.OPR.02',n)
                if isinstance(op,(ast.Is,ast.IsNot)) and any(isinstance(v,(str,int,float,complex,bytes,tuple)) and not isinstance(v,bool) for v in vals if v is not UNKNOWN):self.hit('G.OPR.03',n)
                if isinstance(op,(ast.Eq,ast.NotEq)) and any(isinstance(v,float) for v in vals):self.hit('G.TYP.02',n)
                if any(isinstance(x,ast.Call) and self.name(x.func)=='type' for x in (left,right)):self.hit('G.TYP.08',n)
                if any(isinstance(x,ast.Call) and self.name(x.func)=='len' for x in (left,right)) and any(v==0 for v in vals if v is not UNKNOWN):self.hit('G.TYP.04',n)
        if isinstance(n,ast.UnaryOp) and isinstance(n.op,ast.Not) and isinstance(n.operand,ast.Compare):
            if any(isinstance(op,ast.Is) for op in n.operand.ops):self.hit('G.OPR.05',n)
            if any(isinstance(op,ast.In) for op in n.operand.ops):self.hit('G.OPR.06',n)
        if isinstance(n,ast.Subscript):
            if isinstance(n.slice,ast.Slice) and isinstance(literal(n.slice.step),(int,float)) and literal(n.slice.step)<0:self.hit('G.TYP.05',n)
            if isinstance(n.value,ast.Name) and isinstance(n.ctx,ast.Load):
                assignment=self.value_before(n.value.id,n.lineno,n);mapping=literal(assignment);key=literal(n.slice)
                if isinstance(mapping,dict) and key is not UNKNOWN:
                    try:
                        if key not in mapping:self.hit('G.TYP.07',n)
                    except TypeError:pass
        if isinstance(n,(ast.ListComp,ast.DictComp,ast.SetComp,ast.GeneratorExp)) and (len(n.generators)>1 or sum(len(g.ifs) for g in n.generators)>1):self.hit('G.EXP.04',n)
        if isinstance(n,(ast.If,ast.While)) and isinstance(n.test,ast.BoolOp):
            leaves=sum(not isinstance(x,ast.BoolOp) for x in self.boolean_leaves(n.test))
            if leaves>5:self.hit('G.CTL.03',n.test)
        if isinstance(n,(ast.For,ast.AsyncFor)):
            if isinstance(n.iter,ast.Call) and self.name(n.iter.func)=='range' and len(n.iter.args)==1 and isinstance(n.iter.args[0],ast.Call) and self.name(n.iter.args[0].func)=='len':self.hit('G.CTL.04',n)
            names=assigned_names(n.target)
            for x in ast.walk(n):
                if isinstance(x,(*FUNCTIONS,ast.Lambda)):
                    bound={a.arg for a in args_of(x)}
                    if isinstance(x,FUNCTIONS):bound|={a.id for a in local_walk(x) if isinstance(a,ast.Name) and isinstance(a.ctx,ast.Store)}
                    used={a.id for a in (local_walk(x) if isinstance(x,FUNCTIONS) else ast.walk(x.body)) if isinstance(a,ast.Name) and isinstance(a.ctx,ast.Load)}
                    if (used-bound)&names:self.hit('G.FNM.02',x)
        if isinstance(n,ast.Import) and len(n.names)>1:self.hit('G.FMT.06',n)
        if isinstance(n,ast.ImportFrom) and any(a.name=='*' for a in n.names):self.hit('G.IMP.02',n)
        if isinstance(n,ast.Attribute) and n.attr.startswith('_') and not n.attr.startswith('__') and dotted(n.value) not in {'self','cls'}:self.hit('G.CLS.11',n)
        if isinstance(n,(ast.Try,getattr(ast,'TryStar',ast.Try))):self.try_checks(n)
        if isinstance(n,ast.Call):self.call_checks(n)

    def is_test_file(self):
        p=Path(self.path)
        return p.name.startswith('test_') or p.name.endswith('_test.py') or 'tests' in p.parts

    @staticmethod
    def boolean_leaves(n):
        if isinstance(n,ast.BoolOp):
            for v in n.values:yield from Analyzer.boolean_leaves(v)
        else:yield n

    def in_main(self,n):
        while n in self.parents:
            n=self.parents[n]
            if isinstance(n,ast.If) and isinstance(n.test,ast.Compare) and isinstance(n.test.left,ast.Name) and n.test.left.id=='__name__' and any(literal(x)=='__main__' for x in n.test.comparators):return True
        return False

    def try_checks(self,n):
        if getattr(self,'project',None):self.project.handler_order(self,n)
        for statement in n.finalbody:
            if isinstance(statement,(*FUNCTIONS,ast.ClassDef)):continue
            for x in [statement]+list(local_walk(statement)):
                if isinstance(x,(ast.Return,ast.Raise,ast.Break,ast.Continue)):
                    if isinstance(x,(ast.Break,ast.Continue)):
                        target=self.ancestor(x,(ast.For,ast.AsyncFor,ast.While))
                        if target is not None and any(target is item or target in ast.walk(item) for item in n.finalbody):continue
                    self.hit('G.ERR.14',x)
                    if isinstance(x,ast.Continue):self.hit('G.ERR.14:不支持finally中的continue',x)
        caught=[]
        for handler in n.handlers:
            types=handler.type.elts if isinstance(handler.type,ast.Tuple) else [handler.type]
            names=[self.name(x) for x in types]
            if len(names)!=len(set(names)):self.hit('G.ERR.09',handler)
            for name in ([] if getattr(self,'project',None) else names):
                current=getattr(builtins,name,None)
                for previous in caught:
                    base=getattr(builtins,previous,None)
                    if previous=='' or name==previous or isinstance(current,type) and isinstance(base,type) and issubclass(current,BaseException) and issubclass(base,BaseException) and issubclass(current,base):self.hit('G.ERR.10',handler)
            caught.extend(names)
            if all(isinstance(s,ast.Pass) or isinstance(s,ast.Expr) and isinstance(s.value,ast.Constant) for s in handler.body):self.hit('G.ERR.07',handler)
            if len(handler.body)==1 and isinstance(handler.body[0],ast.Raise):
                raised=handler.body[0]
                if raised.exc is None or isinstance(raised.exc,ast.Name) and raised.exc.id==handler.name:self.hit('G.ERR.13',handler)
            for x in local_walk(handler):
                if isinstance(x,ast.Raise) and x.exc is not None and isinstance(x.exc,ast.Call) and x.cause is None:self.hit('G.ERR.04',x)

    def call_checks(self,n):
        name=self.name(n.func); args=n.args; kw={k.arg:k.value for k in n.keywords}
        if name=='__import__':self.hit('G.IMP.03',n)
        if name in {'breakpoint','pdb.set_trace','pdb.post_mortem','ipdb.set_trace','debugpy.listen','pydevd.settrace'}:self.hit('G.PRJ.03',n)
        if name=='decimal.Decimal' and args and isinstance(literal(args[0]),float):self.hit('G.TYP.01',n)
        if name=='yaml.load':self.hit('G.SER.03',n)
        if name=='tempfile.mktemp':self.hit('G.FIO.03',n)
        if name in {'jsonpickle.encode','jsonpickle.decode','jsonpickle.dumps','jsonpickle.loads'}:self.hit('G.SER.04',n)
        if name in {'eval','exec','builtins.eval','builtins.exec'} and args and self.external(args[0]):self.hit('G.EDV.01',n)
        if name in {'pickle.load','pickle.loads','_pickle.load','_pickle.loads','shelve.open'}:self.hit('G.SER.01',n)
        if name in {'os.system','os.popen','commands.getoutput','commands.getstatusoutput','subprocess.getoutput','subprocess.getstatusoutput'}:self.hit('G.EDV.02',n)
        if name.startswith('subprocess.') and literal(kw.get('shell')) is True:self.hit('G.EDV.04',n)
        command_calls={'subprocess.run','subprocess.call','subprocess.check_call','subprocess.check_output','subprocess.Popen','os.system','os.popen'}
        if name in command_calls and args:
            command=literal(args[0]); executable=command[0] if isinstance(command,(tuple,list)) and command else command
            if isinstance(executable,str) and executable and not(executable.startswith('/') or re.match(r'^[A-Za-z]:[\\/]',executable)):
                self.hit('G.EDV.05',n)
            if (name.startswith('os.') or literal(kw.get('shell')) is True):
                if isinstance(command,str):
                    if any(c in command for c in '*?['):self.hit('G.EDV.03',n)
                elif isinstance(command,(list,tuple)):
                    # List command with shell=True: the list is joined into one
                    # shell string, so a wildcard in any literal element expands.
                    if any(isinstance(e,str) and any(c in e for c in '*?[') for e in command):self.hit('G.EDV.03',n)
                elif command is UNKNOWN:
                    if any(any(c in frag for c in '*?[') for frag in wildcard_fragments(args[0])):self.hit('G.EDV.03',n)
        if name in {'datetime.datetime.now','datetime.datetime.utcnow','datetime.now','datetime.utcnow'} and not args and 'tz' not in kw:self.hit('G.PSL.02',n)
        if name.startswith('random.') and name.split('.')[-1] not in {'seed','Random','SystemRandom'}:self.hit('G.DSP.02',n)
        if name in {'socket.socket','socket.Socket'}:self.hit('G.DSP.03',n)
        if name in {'sys.path.insert','sys.path.append','sys.path.extend'}:self.hit('G.PSL.03',n)
        if name in {'lxml.etree.XMLParser','lxml.etree.ETCompatXMLParser'} and literal(kw.get('resolve_entities')) is True:self.hit('G.EDV.10',n)
        if name in {'xml.sax.parse','xml.sax.parseString','xml.dom.minidom.parse','xml.dom.minidom.parseString'}:self.hit('G.EDV.10',n)
        if name=='print' and not self.is_test_file():self.hit('G.LOG.02',n)
        if name=='sys.exit' and not self.in_main(n):self.hit('G.ERR.11',n)
        if name in {'imp.load_source','imp.load_module','imp.find_module','inspect.getargspec','time.clock','asyncio.coroutine','platform.dist','platform.linux_distribution','cgi.escape','base64.encodestring','base64.decodestring'}:self.hit('G.PSL.01',n)
        attr=n.func.attr if isinstance(n.func,ast.Attribute) else ''
        base=n.func.value if isinstance(n.func,ast.Attribute) else None
        if attr in {'debug','info','warning','error','critical','exception','log'} and (name.startswith('logging.') or isinstance(base,ast.Name) and base.id in {'logger','log'}):
            offset=1 if attr=='log' else 0
            if len(args)>offset:
                msg=args[offset]
                if isinstance(msg,(ast.JoinedStr,ast.BinOp)) or isinstance(msg,ast.Call) and isinstance(msg.func,ast.Attribute) and msg.func.attr=='format':self.hit('G.LOG.01',n)
                if any(self.external(a) for a in args[offset:]):self.hit('G.LOG.03',n)
                if any(self.sensitive(x) for x in args):self.hit('G.DSP.04',n)
        if name=='print' and any(self.sensitive(a) for a in args):self.hit('G.DSP.04',n)
        if name in {'json.dumps','json.dump','pickle.dumps','pickle.dump','yaml.dump','jsonpickle.encode'} and args and self.sensitive(args[0]):self.hit('G.SER.02',n)
        if attr in {'assertTrue','assertFalse'} and args and isinstance(args[0],ast.Compare):self.hit('G.TES.02',n)
        if attr=='format' and base is not None and self.external(base):self.hit('G.EDV.07',n)
        if attr in {'execute','executemany','executescript'} and args and isinstance(args[0],(ast.BinOp,ast.JoinedStr,ast.Call)) and self.external(args[0]):self.hit('G.EDV.06',n)
        if attr=='communicate' and 'timeout' not in kw:
            value=self.value_before(base.id,n.lineno,n) if isinstance(base,ast.Name) else base
            if isinstance(value,ast.Call) and self.name(value.func)=='subprocess.Popen':self.hit('G.CNP.01',n)
        if attr in {'extract','extractall'}:
            value=self.value_before(base.id,n.lineno,n) if isinstance(base,ast.Name) else base
            if isinstance(value,ast.Call) and self.name(value.func) in {'tarfile.open','tarfile.TarFile','zipfile.ZipFile'}:
                if not(self.name(value.func).startswith('tarfile.') and literal(kw.get('filter'))=='data'):self.hit('G.FIO.06',n)
        if name in {'os.open','os.chmod','Path.chmod'}:
            mode=kw.get('mode') or (args[2] if name=='os.open' and len(args)>2 else args[1] if name!='os.open' and len(args)>1 else None)
            permission=literal(mode)
            if isinstance(permission,int) and permission & 0o022:self.hit('G.FIO.01',n)
        if name in {'open','io.open'}:
            with_node=self.ancestor(n,(ast.With,ast.AsyncWith))
            in_context=with_node and any(n in ast.walk(i.context_expr) for i in with_node.items)
            if not in_context:self.hit('G.PRM.03',n)
        if name=='tempfile.NamedTemporaryFile' and literal(kw.get('delete')) is False:self.hit('G.FIO.04',n)
        if name in {'os.path.exists','os.path.isfile','os.path.isdir'} and args and self.external(args[0]):
            normalized=self.is_normalized(args[0])
            if not normalized:self.hit('G.FIO.02',n)
        if name in {'re.compile','re.match','re.search','re.fullmatch','re.findall'} and args:
            pattern=literal(args[0])
            if isinstance(pattern,str) and self.nested_repeat(pattern):self.hit('G.EDV.08',n)

    @staticmethod
    def nested_repeat(pattern):
        """Conservative structural ReDoS signal; not a complexity proof."""
        try:
            from re import _parser, _constants
            tree=_parser.parse(pattern,0)
            repeats={_constants.MAX_REPEAT,_constants.MIN_REPEAT}
            def walk(nodes,inside=False):
                for op,arg in nodes:
                    if op in repeats:
                        minimum,maximum,sub=arg
                        if inside and maximum>1:return True
                        if walk(sub,inside or maximum>1):return True
                    elif op is _constants.SUBPATTERN and walk(arg[-1],inside):return True
                    elif op is _constants.BRANCH and any(walk(branch,inside) for branch in arg[1]):return True
                return False
            return walk(tree)
        except (re.error,ImportError,AttributeError,ValueError):return False


def scan(files: list[tuple[str,str]], entries: list[dict]) -> dict:
    """Return original CodeArts IDs and explicit parser errors, without executing code."""
    manifests={r['rule_id']:r for r in json.loads(MANIFEST.read_text())}
    selected={rule_key(e['rule']):e['rule'] for e in entries if e['rule']['language'].lower()=='python'}
    findings=[];errors=[];analyzers=[]
    for path,text in files:
        try:
            analyzer=Analyzer(path,text)
            analyzers.append(analyzer)
        except (SyntaxError,tokenize.TokenError,IndentationError,RecursionError) as exc:
            errors.append({'path':path,'reason':f'Python parse failed: {exc}'})
    try:
        from .python_project import Project
    except ImportError:
        from python_project import Project
    project=Project(analyzers,selected)
    for analyzer in analyzers:
        path=analyzer.path
        hits=analyzer.run()
        if 'G.FMT.02' in selected:hits.setdefault('G.FMT.02',[])
        for key,locations in hits.items():
            if key not in selected:continue
            rule=selected[key];manifest=manifests[rule['id']]
            if key=='G.FMT.02':
                options={o.get('optionKey'):o.get('optionValue') for o in rule.get('options',[])}
                limit=int(options.get('max-line-length',120))
                locations=[(i,limit+1,f'Line has {len(s)} characters; configured maximum is {limit}.') for i,s in enumerate(analyzer.lines,1) if len(s)>limit]
            for line,col,message in sorted(set(locations),key=lambda x:(x[0],x[1])):
                partial=manifest['status']=='partial'
                findings.append({'id':rule['id'],'path':path,'line':line,'column':col,'language':'python',
                    'severity':'warning',
                    'severity_policy':'local-policy: catalog findings are warning; exported numeric severity is retained without interpretation',
                    'raw_severity':rule.get('severity'),'confidence':'medium' if partial else 'high',
                    'title':rule.get('nameCn') or rule['name'],
                    'message':message or (("Review candidate: " if partial else "Rule violation: ")+(rule.get('nameCn') or rule['name'])+(". Scope: "+manifest['reason'] if partial else '')),
                    'evidence':analyzer.lines[line-1] if 0<line<=len(analyzer.lines) else '',
                    'source':{'id':'codearts-user-export','status':'user-exported'},'coverage_status':manifest['status'],
                    'detector':manifest['detector'],'fix':{'autofixable':False}})
    semantic={'G.CLS.01','G.CLS.02','G.ERR.03','G.ERR.10','G.FNM.04'}
    affected=[rule['id'] for key,rule in selected.items() if key in semantic or key.startswith('G.CLS.09:')]
    for error in project.errors:
        keys=error.pop('affected_rule_keys',None)
        error['affected_rule_ids']=[selected[key]['id'] for key in keys if key in selected] if keys is not None else list(affected)
    return {'findings':findings,'errors':errors+project.errors,'type_context':project.context()}
