"""Static Python project symbols, import resolution, inheritance and return facts.

Only caller-supplied source is parsed. Project imports and decorators never execute.
Missing required dependencies remain explicit errors; dynamic dispatch is unknown.
"""
from __future__ import annotations

import ast
import builtins
from dataclasses import dataclass
from pathlib import Path
import os

try:
    from . import python_stdlib_models as stdlib
except ImportError:
    import python_stdlib_models as stdlib

FUNCTIONS=(ast.FunctionDef,ast.AsyncFunctionDef)


@dataclass(frozen=True)
class Symbol:
    kind: str
    name: str
    module: str = ''
    node: object = None
    analyzer: object = None

    @property
    def identity(self):
        return self.kind,self.module,self.name


class Project:
    def __init__(self,analyzers,selected):
        self.analyzers=analyzers
        self.selected=set(selected)
        self.modules={}
        self.module_names={}
        self.definitions={}
        self.imports={}
        self.class_symbols={}
        self.errors=[]
        self._errors=set()
        self._mros={}
        self.stdlib_models_used=set()
        paths=[Path(a.path).resolve() for a in analyzers]
        common=Path(os.path.commonpath([str(p.parent) for p in paths])) if paths else Path.cwd()
        # __init__.py files provide package roots, including scans of a package alone.
        package_dirs={p.parent for p in paths if p.name=='__init__.py'}
        while common in package_dirs:common=common.parent
        for a,p in zip(analyzers,paths):
            relative=p.relative_to(common)
            parts=list(relative.with_suffix('').parts)
            if parts[-1]=='__init__':parts.pop()
            name='.'.join(parts) or p.parent.name
            self.modules[name]=a;self.module_names[a]=name
        for module,a in self.modules.items():
            definitions={};imports={}
            for n in a.tree.body:
                if isinstance(n,(ast.ClassDef,*FUNCTIONS)):
                    symbol=Symbol('class' if isinstance(n,ast.ClassDef) else 'function',n.name,module,n,a)
                    definitions[n.name]=symbol
                    if isinstance(n,ast.ClassDef):self.class_symbols[n]=symbol
                elif isinstance(n,(ast.Assign,ast.AnnAssign)):
                    targets=n.targets if isinstance(n,ast.Assign) else [n.target]
                    for target in targets:
                        if isinstance(target,ast.Name):definitions[target.id]=Symbol('value',target.id,module,n.value,a)
                elif isinstance(n,ast.Import):
                    for alias in n.names:imports[alias.asname or alias.name.split('.')[0]]=(alias.name if alias.asname else alias.name.split('.')[0],None)
                elif isinstance(n,ast.ImportFrom):
                    package=module if Path(a.path).name=='__init__.py' else module.rpartition('.')[0]
                    parts=package.split('.') if package else []
                    if n.level:
                        parts=parts[:len(parts)-n.level+1] if n.level<=len(parts)+1 else []
                        target='.'.join(parts+([n.module] if n.module else []))
                    else:target=n.module or ''
                    for alias in n.names:imports[alias.asname or alias.name]=(target,alias.name)
            self.definitions[module]=definitions;self.imports[module]=imports
        for a in analyzers:a.project=self

    def context(self):
        return {'source_files':len(self.analyzers),'modules':[{'name':n,'path':a.path} for n,a in sorted(self.modules.items())],
                'analysis':'supplied-source imports, lexical symbols, C3 inheritance, static stdlib identities and bounded return inference; project modules are never executed',
                'stdlib_models':{'version':stdlib.MODEL_VERSION,'python_version':stdlib.PYTHON_VERSION,
                                 'target_version_detected':False,'provenance':stdlib.PROVENANCE,
                                 'classes':sorted(self.stdlib_models_used),
                                 'scope':'fixed CPython 3.11 inheritance, member inventories and selected signatures, independent of CLI host version; target-version differences, dynamic imports, vendor types and runtime mutation are not inferred'},
                'unresolved_dependencies':[dict(e) for e in self.errors]}

    def error(self,a,node,reason,affected_rules=None):
        key=(a.path,getattr(node,'lineno',1),reason)
        if key not in self._errors:
            self._errors.add(key)
            error={'path':a.path,'line':key[1],'reason':'Incomplete Python project analysis: '+reason}
            if affected_rules is not None:error['affected_rule_keys']=sorted(set(affected_rules)&self.selected)
            self.errors.append(error)

    def unknown(self,name):return Symbol('unknown',name)

    @staticmethod
    def builtin(name):
        value=getattr(builtins,name,None)
        # IOError/EnvironmentError are aliases of OSError, not separate classes.
        return Symbol('builtin',value.__name__) if isinstance(value,type) else Symbol('unknown','builtins.'+name)

    def model_allowed(self,module):
        root=module.split('.')[0]
        return not any(m==root or m.startswith(root+'.') for m in self.modules)

    def module_symbol(self,module):
        available=module=='builtins' or module in self.modules or any(m.startswith(module+'.') for m in self.modules)
        if available or self.model_allowed(module) and module in stdlib.MODULES:return Symbol('module',module)
        return self.unknown(module)

    def model_symbol(self,module,name):
        if not self.model_allowed(module):return self.unknown(module+'.'+name)
        canonical=stdlib.canonical_name(module,name)
        if canonical is None:return self.unknown(module+'.'+name)
        target,_,member=canonical.rpartition('.')
        if target=='builtins':return self.builtin(member)
        self.stdlib_models_used.add(canonical)
        return Symbol('stdlib',member,target,stdlib.CLASSES[canonical])

    def import_binding(self,a,name,line):
        """Resolve the actual import at a binding site, not a later same-name import."""
        module=self.module_names[a]
        for statement in a.nodes:
            if getattr(statement,'lineno',0)!=line or not isinstance(statement,(ast.Import,ast.ImportFrom)):continue
            for alias in statement.names:
                bound=alias.asname or (alias.name.split('.')[0] if isinstance(statement,ast.Import) else alias.name)
                if bound!=name:continue
                if isinstance(statement,ast.Import):return self.module_symbol(alias.name if alias.asname else alias.name.split('.')[0])
                target=statement.module or ''
                if statement.level:
                    package=module if Path(a.path).name=='__init__.py' else module.rpartition('.')[0]
                    parts=package.split('.') if package else []
                    parts=parts[:len(parts)-statement.level+1] if statement.level<=len(parts)+1 else []
                    target='.'.join(parts+([target] if target else []))
                child=self.module_symbol(target+'.'+alias.name)
                return child if child.kind=='module' else self.symbol(target,alias.name)
        return self.unknown('unresolved import '+name)

    def symbol(self,module,name,seen=None):
        seen=set() if seen is None else set(seen)
        identity=(module,name)
        if identity in seen:return self.unknown('cyclic alias '+module+'.'+name)
        seen.add(identity)
        if module=='builtins' and isinstance(getattr(builtins,name,None),type):return self.builtin(name)
        if name in self.definitions.get(module,{}):return self.definitions[module][name]
        if name in self.imports.get(module,{}):
            target,member=self.imports[module][name]
            if member is None:
                return self.module_symbol(target)
            child=self.module_symbol(target+'.'+member)
            if child.kind=='module':return child
            return self.symbol(target,member,seen)
        child=self.module_symbol(module+'.'+name)
        if child.kind=='module':return child
        return self.model_symbol(module,name)

    def resolve(self,a,node,seen=None):
        if node is None:return self.unknown('<empty>')
        seen=set() if seen is None else set(seen)
        if id(node) in seen:return self.unknown('cyclic expression')
        seen.add(id(node))
        if isinstance(node,ast.Name):
            module=self.module_names[a]
            for scope in a.lexical_scopes(node):
                if isinstance(scope,ast.Module):break
                bindings=a.scope_bindings(scope)
                if node.id in bindings:
                    for arg in list(getattr(scope,'args',ast.arguments(posonlyargs=[],args=[],kwonlyargs=[],kw_defaults=[],defaults=[])).posonlyargs)+list(getattr(scope,'args',ast.arguments(posonlyargs=[],args=[],kwonlyargs=[],kw_defaults=[],defaults=[])).args)+list(getattr(scope,'args',ast.arguments(posonlyargs=[],args=[],kwonlyargs=[],kw_defaults=[],defaults=[])).kwonlyargs) if isinstance(scope,(*FUNCTIONS,ast.Lambda)) else []:
                        if arg.arg==node.id:return Symbol('parameter',node.id,module,arg,a)
                    value=a.value_before(node.id,node.lineno,node)
                    if value is not None:return Symbol('value',node.id,module,value,a)
                    local=next((n for n in getattr(scope,'body',[]) if isinstance(n,(ast.ClassDef,*FUNCTIONS)) and n.name==node.id),None)
                    if local:return Symbol('class' if isinstance(local,ast.ClassDef) else 'function',node.id,module,local,a)
                    imported=[(line,value) for line,value in bindings[node.id] if line<=getattr(node,'lineno',0) and value is not None]
                    if imported:
                        return self.import_binding(a,node.id,imported[-1][0])
                    return self.unknown('local '+node.id)
            # A module-level expression sees only bindings established before it.
            # Deferred function bodies instead use the final supplied module symbol map.
            if not any(isinstance(scope,(*FUNCTIONS,ast.Lambda)) for scope in a.lexical_scopes(node)):
                bindings=a.scope_bindings(a.tree).get(node.id,[])
                earlier=[binding for binding in bindings if binding[0]<node.lineno]
                if bindings:
                    if not earlier:return self.unknown('not-yet-bound '+module+'.'+node.id)
                    line,imported=earlier[-1]
                    if imported is not None:
                        return self.import_binding(a,node.id,line)
                    value=a.value_before(node.id,node.lineno,node)
                    definitions=[statement for statement in a.tree.body if isinstance(statement,(ast.ClassDef,*FUNCTIONS)) and statement.name==node.id and statement.lineno==line]
                    if definitions:
                        definition=definitions[-1]
                        return Symbol('class' if isinstance(definition,ast.ClassDef) else 'function',node.id,module,definition,a)
                    if value is not None:return Symbol('value',node.id,module,value,a)
                    return self.unknown('module binding '+module+'.'+node.id)
            resolved=self.symbol(module,node.id)
            if resolved.kind!='unknown':return resolved
            if node.id not in self.imports.get(module,{}) and node.id not in self.definitions.get(module,{}) and isinstance(getattr(builtins,node.id,None),type):return self.builtin(node.id)
            return resolved
        if isinstance(node,ast.Attribute):
            base=self.resolve(a,node.value,seen)
            if base.kind=='module':
                identity=a.name(node)
                if any(isinstance(other,ast.Attribute) and isinstance(other.ctx,(ast.Store,ast.Del))
                       and getattr(other,'lineno',0)<=getattr(node,'lineno',0) and a.name(other)==identity
                       for other in a.nodes):return self.unknown('rebound '+base.name+'.'+node.attr)
                return self.symbol(base.name,node.attr)
            if base.kind in {'class','stdlib'}:
                cls,method=self.find_method(base,node.attr)
                if method:return Symbol('stdlib_function' if cls.kind=='stdlib' else 'function',node.attr,cls.module,method,cls.analyzer)
            return self.unknown(base.name+'.'+node.attr)
        return self.unknown(ast.unparse(node))

    def base_symbol(self,a,node,seen=None):
        """Erase only proven generic type arguments, never arbitrary subscription."""
        seen=set() if seen is None else set(seen)
        marker=(id(a),id(node))
        if marker in seen:return self.unknown('cyclic base alias')
        seen.add(marker)
        expression=node.value if isinstance(node,ast.Subscript) else node
        resolved=self.resolve(a,expression)
        if resolved.kind=='value':resolved=self.base_symbol(resolved.analyzer,resolved.node,seen)
        if isinstance(node,ast.Subscript) and not self.is_generic(resolved):return self.unknown('unresolved generic base '+ast.unparse(node))
        return resolved

    def is_generic(self,symbol):
        if symbol.kind=='builtin':return symbol.name in stdlib.GENERIC_BUILTINS
        if symbol.kind=='stdlib':return symbol.node.generic
        if symbol.kind!='class':return False
        # A metaclass or user subscription hook can replace the subscribed class.
        if any(keyword.arg=='metaclass' for keyword in symbol.node.keywords):return False
        for base in self.mro(symbol):
            if base.kind=='unknown':return False
            if base.kind=='class' and (self.method(base,'__class_getitem__') or base.node.decorator_list):return False
            if base.kind=='stdlib' and base.node.generic:return True
            if base.kind=='builtin' and base.name in stdlib.GENERIC_BUILTINS:return True
        return False

    def bases(self,symbol,report=True):
        if symbol.kind=='stdlib':
            return [self.builtin(name) if module=='builtins' else self.model_symbol(module,name)
                    for module,name in (base.rsplit('.',1) for base in symbol.node.bases)]
        if symbol.kind!='class':return []
        result=[]
        for base in symbol.node.bases:
            resolved=self.base_symbol(symbol.analyzer,base)
            if resolved.kind not in {'class','builtin','stdlib'}:
                if report:self.error(symbol.analyzer,base,'unresolved base '+resolved.name)
            result.append(resolved)
        return result or [Symbol('builtin','object')]

    def mro(self,symbol,visiting=None):
        if symbol.kind=='builtin':
            cls=getattr(builtins,symbol.name,None)
            return [Symbol('builtin',x.__name__) for x in cls.__mro__] if isinstance(cls,type) else [symbol]
        if symbol.kind not in {'class','stdlib'}:return [symbol]
        if symbol.identity in self._mros:return self._mros[symbol.identity]
        visiting=set() if visiting is None else set(visiting)
        if symbol.identity in visiting:
            if symbol.analyzer:self.error(symbol.analyzer,symbol.node,'cyclic class inheritance for '+symbol.name)
            return [symbol]
        visiting.add(symbol.identity)
        bases=self.bases(symbol)
        sequences=[list(self.mro(base,visiting)) for base in bases]+[list(bases)]
        merged=[]
        while any(sequences):
            sequences=[s for s in sequences if s]
            head=next((s[0] for s in sequences if not any(s[0].identity in [x.identity for x in other[1:]] for other in sequences)),None)
            if head is None:
                if symbol.analyzer:self.error(symbol.analyzer,symbol.node,'inconsistent method resolution order for '+symbol.name)
                break
            merged.append(head)
            for sequence in sequences:
                if sequence and sequence[0].identity==head.identity:sequence.pop(0)
        result=[symbol]+merged
        self._mros[symbol.identity]=result
        return result

    def method(self,cls,name):
        if cls.kind=='stdlib':return stdlib.METHODS.get(cls.module+'.'+cls.name,{}).get(name)
        if cls.kind!='class':return None
        return next((n for n in cls.node.body if isinstance(n,FUNCTIONS) and n.name==name),None)

    def subclass(self,child,parent):
        if child.kind not in {'class','builtin','stdlib'} or parent.kind not in {'class','builtin','stdlib'}:return None
        mro=self.mro(child)
        if any(x.identity==parent.identity for x in mro):return True
        return None if any(x.kind=='unknown' for x in mro) else False

    def find_method(self,cls,name,skip_self=False):
        for base in self.mro(cls)[1 if skip_self else 0:]:
            method=self.method(base,name)
            if method:return base,method
            # A verified absent own member allows C3 traversal to continue.
            # A present but unmodelled member shadows any ancestor signature.
            if base.kind=='stdlib' and name in base.node.own_members:return base,None
        return None,None

    @staticmethod
    def signature(fn):
        args=fn.args
        normal=list(args.posonlyargs)+list(args.args)
        required=len(normal)-len(args.defaults)
        positional=[(a.arg if i>=len(args.posonlyargs) else '<positional>',i>=required) for i,a in enumerate(normal)]
        # Receiver spelling is governed separately by NAM.03.
        if positional:positional[0]=('<receiver>',positional[0][1])
        keywords=[(a.arg,d is not None) for a,d in zip(args.kwonlyargs,args.kw_defaults)]
        decorators=tuple(ast.unparse(d) for d in fn.decorator_list if isinstance(d,ast.Name) and d.id in {'staticmethod','classmethod'})
        return positional,len(args.posonlyargs),keywords,bool(args.vararg),bool(args.kwarg),decorators

    def class_checks(self,a,node):
        cls=self.class_symbols.get(node)
        if not cls:return
        needs_inheritance=bool(self.selected&{'G.CLS.01','G.CLS.02'})
        exception_candidate=node.name.endswith(('Error','Exception')) and 'G.ERR.03' in self.selected
        for method in [n for n in node.body if isinstance(n,FUNCTIONS)]:
            key='G.CLS.09:'+method.name[2:-2]
            if method.name.startswith('__') and method.name.endswith('__') and key in self.selected:
                generator=any(isinstance(n,(ast.Yield,ast.YieldFrom)) for n in self.local_nodes(method))
                if generator:
                    if method.name!='__iter__':a.hit(key,method,'This magic method returns a generator object rather than the required protocol type.')
                elif self.flow(a,method.body,None,{False})['normal']:
                    a.hit(key,method,'Magic method has a normal path reaching the end and returning None implicitly.')
        if not needs_inheritance and not exception_candidate:return
        ancestors=self.mro(cls)
        if exception_candidate and self.subclass(cls,Symbol('builtin','Exception')) is False:
            a.hit('G.ERR.03',node,'Exception class does not derive from Exception through the supplied project hierarchy.')
        for method in [n for n in node.body if isinstance(n,FUNCTIONS)]:
            owner,parent=self.find_method(cls,method.name,skip_self=True)
            if owner and parent is None:
                affected={'G.CLS.01'} if method.name=='__init__' else ({'G.CLS.02'} if method.name!='__new__' else set())
                if affected&self.selected:
                    self.error(a,method,'incomplete stdlib override model for '+owner.module+'.'+owner.name+'.'+method.name,affected)
                continue
            if parent and method.name not in {'__init__','__new__'} and 'G.CLS.02' in self.selected:
                if self.signature(method)!=self.signature(parent):a.hit('G.CLS.02',method,'Override signature differs from '+owner.module+'.'+owner.name+'.'+method.name+'.')
            if method.name=='__init__' and parent and 'G.CLS.01' in self.selected:
                states=self.init_states(a,method.body,cls,{False})
                if False in states:a.hit('G.CLS.01',method,'A normal initializer path does not call the inherited initializer '+owner.module+'.'+owner.name+'.__init__.')

    def is_init_call(self,a,node,cls):
        if cls is None or not isinstance(node,ast.Call) or not isinstance(node.func,ast.Attribute) or node.func.attr!='__init__':return False
        owner=node.func.value
        if isinstance(owner,ast.Call):
            target=self.resolve(a,owner.func)
            if target.kind!='builtin' or target.name!='super':return False
            if not owner.args:return True
            if len(owner.args)!=2 or self.resolve(a,owner.args[0]).identity!=cls.identity:return False
            method=a.ancestor(node,FUNCTIONS)
            positional=list(method.args.posonlyargs)+list(method.args.args) if method else []
            return bool(positional) and isinstance(owner.args[1],ast.Name) and owner.args[1].id==positional[0].arg
        symbol=self.resolve(a,owner)
        method=a.ancestor(node,FUNCTIONS)
        positional=list(method.args.posonlyargs)+list(method.args.args) if method else []
        return bool(node.args) and bool(positional) and isinstance(node.args[0],ast.Name) and node.args[0].id==positional[0].arg and any(symbol.identity==base.identity for base in self.mro(cls)[1:])

    def expression_states(self,a,node,cls,states):
        """Track calls evaluated on normal paths without entering deferred code."""
        states=set(states)
        if node is None or not states:return states
        if isinstance(node,(ast.Lambda,ast.GeneratorExp)):return states
        if isinstance(node,(ast.ListComp,ast.DictComp,ast.SetComp)):
            # Iterables can be empty; only evaluation of the first iterable is guaranteed.
            return self.expression_states(a,node.generators[0].iter,cls,states)
        if isinstance(node,ast.BoolOp):
            current=states;completed=set()
            for index,value in enumerate(node.values):
                current=self.expression_states(a,value,cls,current)
                if index==len(node.values)-1:break
                known=bool(value.value) if isinstance(value,ast.Constant) else None
                stops=known is False if isinstance(node.op,ast.And) else known is True
                continues=known is True if isinstance(node.op,ast.And) else known is False
                if stops:completed|=current;current=set();break
                if not continues:completed|=current
            return completed|current
        if isinstance(node,ast.IfExp):
            current=self.expression_states(a,node.test,cls,states)
            if isinstance(node.test,ast.Constant):return self.expression_states(a,node.body if node.test.value else node.orelse,cls,current)
            return self.expression_states(a,node.body,cls,current)|self.expression_states(a,node.orelse,cls,current)
        if isinstance(node,ast.Compare):
            current=self.expression_states(a,node.left,cls,states)
            possible=set()
            for operand in node.comparators:
                current=self.expression_states(a,operand,cls,current)
                possible|=current
            return possible or current
        for child in ast.iter_child_nodes(node):
            states=self.expression_states(a,child,cls,states)
        return {True} if self.is_init_call(a,node,cls) else states

    @staticmethod
    def empty_flow():return {kind:set() for kind in ('normal','return','raise','break','continue')}

    def flow(self,a,statements,cls,states):
        """A bounded statement CFG preserving each completion kind separately.

        Loops include zero iterations unless literally while True. Exception handler
        entry conservatively uses pre-try state, without pretending a prior call succeeded.
        """
        result=self.empty_flow();result['normal']=set(states)
        for statement in statements:
            incoming=result['normal']
            if not incoming:break
            step=self.empty_flow()
            if isinstance(statement,ast.If):
                incoming=self.expression_states(a,statement.test,cls,incoming)
                branches=(statement.body,statement.orelse)
                if isinstance(statement.test,ast.Constant):branches=(statement.body if statement.test.value else statement.orelse,)
                for branch in branches:
                    flow=self.flow(a,branch,cls,incoming)
                    for kind in step:step[kind]|=flow[kind]
            elif isinstance(statement,(ast.For,ast.AsyncFor,ast.While)):
                expression=statement.test if isinstance(statement,ast.While) else statement.iter
                incoming=self.expression_states(a,expression,cls,incoming)
                forever=isinstance(statement,ast.While) and isinstance(statement.test,ast.Constant) and bool(statement.test.value)
                never=isinstance(statement,ast.While) and isinstance(statement.test,ast.Constant) and not statement.test.value
                body=self.empty_flow() if never else self.flow(a,statement.body,cls,incoming)
                step['return']=body['return'];step['raise']=body['raise']
                exhausted=set() if forever else incoming|body['normal']|body['continue']
                tail=self.flow(a,statement.orelse,cls,exhausted)
                for kind in step:step[kind]|=tail[kind]
                step['normal']|=body['break']
            elif isinstance(statement,(ast.With,ast.AsyncWith)):
                for item in statement.items:incoming=self.expression_states(a,item.context_expr,cls,incoming)
                step=self.flow(a,statement.body,cls,incoming)
            elif isinstance(statement,ast.Try):
                step=self.flow(a,statement.body,cls,incoming)
                normal=self.flow(a,statement.orelse,cls,step['normal']);step['normal']=set()
                for kind in step:step[kind]|=normal[kind]
                for handler in statement.handlers:
                    caught=self.flow(a,handler.body,cls,incoming)
                    for kind in step:step[kind]|=caught[kind]
                if statement.finalbody:
                    finalized=self.empty_flow()
                    for pending,values in step.items():
                        cleanup=self.flow(a,statement.finalbody,cls,values)
                        finalized[pending]|=cleanup['normal']
                        for kind in cleanup:
                            if kind!='normal':finalized[kind]|=cleanup[kind]
                    step=finalized
            elif isinstance(statement,ast.Match):
                incoming=self.expression_states(a,statement.subject,cls,incoming)
                exhaustive=False
                for case in statement.cases:
                    branch=self.flow(a,case.body,cls,incoming)
                    for kind in step:step[kind]|=branch[kind]
                    if isinstance(case.pattern,ast.MatchAs) and case.pattern.pattern is None and case.guard is None:exhaustive=True
                if not exhaustive:step['normal']|=incoming
            elif isinstance(statement,(ast.Return,ast.Raise,ast.Break,ast.Continue)):
                kind={ast.Return:'return',ast.Raise:'raise',ast.Break:'break',ast.Continue:'continue'}[type(statement)]
                expression=getattr(statement,'value',None) if isinstance(statement,ast.Return) else getattr(statement,'exc',None)
                step[kind]=self.expression_states(a,expression,cls,incoming)
            elif isinstance(statement,(ast.ClassDef,*FUNCTIONS)):
                step['normal']=incoming
            else:step['normal']=self.expression_states(a,statement,cls,incoming)
            result['normal']=step['normal']
            for kind in result:
                if kind!='normal':result[kind]|=step[kind]
        return result

    def init_states(self,a,statements,cls,states):
        result=self.flow(a,statements,cls,states)
        return result['normal']|result['return']

    def handler_order(self,a,node):
        if 'G.ERR.10' not in self.selected:return
        caught=[]
        for handler in node.handlers:
            types=handler.type.elts if isinstance(handler.type,ast.Tuple) else [handler.type]
            current=[Symbol('builtin','BaseException') if x is None else self.resolve(a,x) for x in types]
            if any(self.subclass(c,prior) is True for c in current for prior in caught):
                a.hit('G.ERR.10',handler,'An earlier handler catches this exception according to the supplied project hierarchy.')
            for symbol in current:
                if symbol.kind=='unknown':self.error(a,handler,'unresolved exception type '+symbol.name)
            caught.extend(current)

    def raised_exception(self,a,node):
        if 'G.ERR.03' not in self.selected or node.exc is None:return
        expression=node.exc.func if isinstance(node.exc,ast.Call) else node.exc
        symbol=self.resolve(a,expression)
        if symbol.kind=='class' and self.subclass(symbol,Symbol('builtin','Exception')) is False:
            # Point to the construction/use to avoid labeling unrelated classes by name.
            if not symbol.name.endswith(('Error','Exception')):a.hit('G.ERR.03',node,'Raised class '+symbol.module+'.'+symbol.name+' does not inherit Exception.')
        elif symbol.kind=='unknown' and isinstance(expression,(ast.Name,ast.Attribute)):
            self.error(a,node,'unresolved raised exception '+symbol.name)

    def value_type(self,a,node,seen=None):
        """Return known built-in name or class symbol; unknown values stay None."""
        seen=set() if seen is None else set(seen)
        if node is None:return 'NoneType'
        if id(node) in seen or len(seen)>64:return None
        seen.add(id(node))
        try:return type(ast.literal_eval(node)).__name__
        except (ValueError,TypeError,RecursionError):pass
        if isinstance(node,ast.JoinedStr):return 'str'
        if isinstance(node,ast.IfExp):
            left=self.value_type(a,node.body,seen);right=self.value_type(a,node.orelse,seen)
            return left if left==right else None
        if isinstance(node,ast.BinOp):
            left=self.value_type(a,node.left,seen);right=self.value_type(a,node.right,seen)
            if left==right and left in {'str','bytes','list','tuple','int','float'}:return left
            if {left,right}<={'int','float'}:return 'float' if isinstance(node.op,ast.Div) or 'float' in {left,right} else 'int'
            return None
        if isinstance(node,ast.Call):
            if isinstance(node.func,ast.Name) and node.func.id=='iter':return 'iterator'
            symbol=self.resolve(a,node.func)
            if symbol.kind=='builtin':return symbol.name
            if symbol.kind in {'class','stdlib'}:return symbol
            if symbol.kind=='function':return self.function_return_type(symbol,seen)
            return None
        symbol=self.resolve(a,node)
        if symbol.kind=='value':return self.value_type(symbol.analyzer,symbol.node,seen)
        if symbol.kind=='parameter' and symbol.node.annotation:return self.annotation_type(symbol.analyzer,symbol.node.annotation)
        return None

    def callable_symbol(self,a,expression,seen=None):
        """Resolve direct imports and assignment aliases without invoking factories."""
        seen=set() if seen is None else set(seen)
        symbol=self.resolve(a,expression)
        while symbol.kind=='value':
            marker=(symbol.module,id(symbol.node))
            if marker in seen:return self.unknown('cyclic callable alias')
            seen.add(marker)
            symbol=self.resolve(symbol.analyzer,symbol.node)
        return symbol

    def assigned_void_result(self,a,assignment):
        if 'G.FNM.04' not in self.selected or not isinstance(assignment.value,ast.Call):return
        call=assignment.value
        symbol=self.callable_symbol(a,call.func)
        if symbol.kind!='function' or isinstance(symbol.node,ast.AsyncFunctionDef) or symbol.node.decorator_list:return
        # Explicit module-attribute rebinding can replace the imported function.
        # Do not claim a function identity once this source writes that binding.
        if isinstance(call.func,ast.Attribute):
            spelling=ast.unparse(call.func)
            for node in a.nodes:
                if isinstance(node,ast.Attribute) and isinstance(node.ctx,ast.Store) and ast.unparse(node)==spelling and node.lineno<=call.lineno:return
        body=self.local_nodes(symbol.node)
        if any(isinstance(n,(ast.Yield,ast.YieldFrom)) for n in body):return
        if self.function_return_type(symbol,set())=='NoneType':
            a.hit('G.FNM.04',assignment,'Assigned result of '+symbol.module+'.'+symbol.name+'; every statically resolved normal return is None.')

    def annotation_type(self,a,node):
        if isinstance(node,ast.Constant) and isinstance(node.value,str):
            try:node=ast.parse(node.value,mode='eval').body
            except SyntaxError:return None
        if isinstance(node,ast.Constant) and node.value is None:return 'NoneType'
        if isinstance(node,ast.Subscript):node=node.value
        resolved=self.resolve(a,node)
        if resolved.kind=='builtin':return resolved.name
        if resolved.kind in {'class','stdlib'}:return resolved
        if isinstance(node,ast.Name) and node.id in {'Iterator','Generator','AsyncIterator','Iterable'}:return 'iterator' if node.id in {'Iterator','Generator'} else None
        return None

    @staticmethod
    def local_nodes(fn):
        try:
            from .catalog_python import local_walk
        except ImportError:
            from catalog_python import local_walk
        return list(local_walk(fn))

    def function_return_type(self,symbol,seen):
        a=symbol.analyzer;fn=symbol.node
        if isinstance(fn,ast.AsyncFunctionDef):return 'coroutine'
        if fn.decorator_list:return None
        if id(fn) in seen:return None
        seen=set(seen)|{id(fn)}
        annotation=self.annotation_type(a,fn.returns) if fn.returns is not None else None
        body=self.local_nodes(fn)
        if any(isinstance(n,(ast.Yield,ast.YieldFrom)) for n in body):return 'iterator'
        returns=[n for n in body if isinstance(n,ast.Return)]
        if not returns:return 'NoneType' if self.flow(a,fn.body,None,{False})['normal'] else None
        types=[self.value_type(a,n.value,seen) for n in returns]
        if self.flow(a,fn.body,None,{False})['normal']:types.append('NoneType')
        known=set()
        for typ in types:
            if typ is None:continue
            known.update(typ if isinstance(typ,frozenset) else [typ])
        if len(known)>1:return frozenset(known)
        if known and all(typ is not None for typ in types):return next(iter(known))
        # Type hints fill otherwise unknown flows; concrete contradictory values win.
        if annotation is not None:
            if known and annotation not in known:return frozenset(known|{annotation})
            return annotation
        return None

    def valid_magic_type(self,typ,expected):
        if typ is None:return None
        if isinstance(typ,frozenset):
            results=[self.valid_magic_type(t,expected) for t in typ]
            if False in results:return False
            return True if results and all(r is True for r in results) else None
        if isinstance(typ,str):return typ==expected or expected=='int' and typ=='bool'
        if isinstance(typ,Symbol):
            if expected=='iterator':return all(self.find_method(typ,name)[1] is not None for name in ('__iter__','__next__'))
            return self.subclass(typ,Symbol('builtin',expected))
        return None
