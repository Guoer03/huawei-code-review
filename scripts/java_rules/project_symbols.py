"""Bounded project-source Java symbols, without class loading or compilation.

Resolves packages, explicit/wildcard imports, nested classes, generic base
substitution, erased method signatures, and inherited method visibility. Unknown
external classes and ambiguous symbols remain explicit unresolved context.
"""
from __future__ import annotations

from collections import defaultdict
import re

CLASS_KINDS={'CLASS','INTERFACE','ENUM','RECORD','ANNOTATION_TYPE'}
PRIMITIVES={'boolean','byte','short','int','long','float','double','char','void'}
JAVA_LANG={'Object','String','Thread','System','Runtime','Boolean','Byte','Short','Integer','Long','Float','Double','Character','Number','Throwable','Exception','RuntimeException','Error','Class','Enum','Record','Runnable','Comparable','CharSequence','Iterable','Cloneable','AutoCloseable','Override','Deprecated','SuppressWarnings','Void','Math','StringBuilder','StringBuffer','AssertionError','IllegalArgumentException','IllegalStateException','NullPointerException','IndexOutOfBoundsException','ArrayIndexOutOfBoundsException','ClassCastException','ArithmeticException','SecurityException','UnsupportedOperationException','InterruptedException','ArrayStoreException','ConcurrentModificationException','NegativeArraySizeException','NumberFormatException'}
KNOWN_BASES={'java.lang.Object','java.lang.Enum','java.lang.Record','java.io.Serializable','java.io.Externalizable','java.lang.Runnable','java.lang.Comparable','java.lang.AutoCloseable','java.lang.Cloneable'}


def split_type(text):
    text=re.sub(r'\s+','',text)
    start=text.find('<')
    if start<0:return text,[]
    raw=text[:start];inner=text[start+1:text.rfind('>')];args=[];depth=0;cursor=0
    for index,char in enumerate(inner):
        if char=='<':depth+=1
        elif char=='>':depth-=1
        elif char==',' and depth==0:args.append(inner[cursor:index]);cursor=index+1
    if inner:args.append(inner[cursor:])
    return raw,args


class ProjectSymbols:
    def __init__(self,asts):
        self.symbols=[];self.by_name=defaultdict(list);self.by_node={};self.unresolved=[];self.ambiguous=[];self._ambiguous_keys=set()
        for ast in asts:
            for node in ast.kind(*CLASS_KINDS):
                if not node.get('name'):continue
                owners=[p['name'] for p in ast.ancestors(node) if p['kind'] in CLASS_KINDS and p.get('name')]
                nested='.'.join([*reversed(owners),node['name']]);package=ast.record.get('package','')
                qualified=(package+'.' if package else '')+nested
                scope=next((p for p in ast.ancestors(node) if p['kind'] in {'BLOCK','METHOD','LAMBDA_EXPRESSION'}),None)
                # A local class is not the member type Outer.Name. Its lexical
                # scope and source position are part of its internal identity.
                if scope is not None:qualified+='@local:'+str(node['start'])
                symbol={'name':qualified,'package':package,'ast':ast,'node':node,'scope':scope,'top_level':ast.parent(node).get('kind')=='COMPILATION_UNIT','parameters':ast.many(node,'typeParameters')}
                self.symbols.append(symbol);self.by_name[qualified].append(symbol);self.by_node[(id(ast),node['id'])]=symbol
        for ast in asts:ast.project=self
        for symbol in self.symbols:
            for raw in self.base_types(symbol):
                resolved=self.resolve_type(split_type(raw)[0],symbol['ast'],symbol)
                if resolved not in KNOWN_BASES and not self.lookup(resolved,symbol['ast']):
                    self.unresolved.append({'path':symbol['ast'].record.get('source_path',''),'class':symbol['name'],'type':resolved,'reason':'External or ambiguous base is not available in selected project source.'})

    def symbol(self,ast,node):
        return self.by_node.get((id(ast),node.get('id')))

    def lookup(self,name,ast=None):
        candidates=self.by_name.get(name,[])
        local=[s for s in candidates if s['ast'] is ast]
        if len(local)==1:return local[0]
        return candidates[0] if len(candidates)==1 else None

    def base_types(self,symbol):
        ast,node=symbol['ast'],symbol['node'];base=ast.get(node,'extends')
        types=([ast.src(base)] if base else [])+[ast.src(n) for n in ast.many(node,'implements')]
        return types

    def resolve_type(self,text,ast,context=None,bindings=None):
        text=text.strip().replace('...','[]');text=re.sub(r'@[\w.]+(?:\([^)]*\))?\s*','',text)
        text=re.sub(r'\s+','',text)
        if text.endswith('[]'):return self.resolve_type(text[:-2],ast,context,bindings)+'[]'
        raw,_=split_type(text)
        if bindings and raw in bindings:return bindings[raw]
        if raw in PRIMITIVES or raw.startswith('?'):return raw
        if not raw:return ''
        if raw in self.by_name:return raw
        if context:
            local=[s for s in self.symbols if s['ast'] is ast and s['node'].get('name')==raw and s['scope'] is not None and s['scope']['start']<=context['node']['start']<s['scope']['end'] and s['node']['start']<=context['node']['start']]
            if local:return max(local,key=lambda s:s['node']['start'])['name']
        if context:
            owner=context['name']
            # Search only lexical type owners. The package is not a lexical
            # owner: an explicit single-type import wins over same-package types.
            while owner and (not context['package'] or owner!=context['package']):
                candidate=owner+'.'+raw
                if self.lookup(candidate,ast):return candidate
                owner=owner.rpartition('.')[0]
        # A declaration in this compilation unit is nearer than external imports.
        local=[s for s in self.symbols if s['ast'] is ast and s['top_level'] and s['node'].get('name')==raw]
        if len(local)==1:return local[0]['name']
        package=ast.record.get('package','')
        imports=[n['name'] for n in ast.kind('IMPORT') if not n.get('static') or n['name'].endswith('.*') or self.lookup(n['name'],ast)]
        explicit=[name for name in imports if name.rsplit('.',1)[-1]==raw.split('.',1)[0] and not name.endswith('.*')]
        if len(explicit)==1:
            return explicit[0]+('.'+raw.split('.',1)[1] if '.' in raw else '')
        same_package=(package+'.' if package else '')+raw
        if self.lookup(same_package,ast):return same_package
        if '.' in raw:return raw
        wildcard=[name[:-1]+raw for name in imports if name.endswith('.*')]
        known=[candidate for candidate in wildcard if self.lookup(candidate,ast) or candidate in KNOWN_BASES]
        if raw in JAVA_LANG:known.append('java.lang.'+raw)
        known=list(dict.fromkeys(known))
        if len(known)==1:return known[0]
        if len(known)>1:
            identity=(ast.record.get('source_path',''),raw)
            if identity not in self._ambiguous_keys:
                self._ambiguous_keys.add(identity)
                self.ambiguous.append({'path':identity[0],'type':raw,'candidates':sorted(known),'reason':'More than one on-demand imported type matches; no symbol was selected.'})
            return '<ambiguous:'+raw+'>'
        if len(wildcard)==1:return wildcard[0]
        # Keep unqualified unknowns qualified to the referring package, never
        # guess an unrelated class with the same name in another source file.
        return same_package

    def bindings(self,symbol,existing=None):
        result=dict(existing or {})
        for param in symbol['parameters']:
            if param['name'] in result:continue
            bounds=symbol['ast'].many(param,'bounds')
            result[param['name']]=self.resolve_type(symbol['ast'].src(bounds[0]),symbol['ast'],symbol,result) if bounds else 'java.lang.Object'
        return result

    def ancestors(self,symbol):
        queue=[(symbol,self.bindings(symbol))];seen={symbol['name']}
        while queue:
            current,bindings=queue.pop(0);ast=current['ast']
            for base in self.base_types(current):
                raw,arguments=split_type(base);qualified=self.resolve_type(raw,ast,current,bindings)
                target=self.lookup(qualified,ast)
                if not target or qualified in seen:continue
                seen.add(qualified)
                bound={p['name']:self.resolve_type(argument,ast,current,bindings) for p,argument in zip(target['parameters'],arguments)}
                bound=self.bindings(target,bound)
                yield target,bound
                queue.append((target,bound))

    def signature(self,symbol,method,bindings=None):
        ast=symbol['ast'];bound=self.bindings(symbol,bindings)
        for param in ast.many(method,'typeParameters'):
            bounds=ast.many(param,'bounds')
            bound[param['name']]=self.resolve_type(ast.src(bounds[0]),ast,symbol,bound) if bounds else 'java.lang.Object'
        return method.get('name'),tuple(self.resolve_type(ast.src(ast.get(param,'type')),ast,symbol,bound) for param in ast.many(method,'params'))

    def inherited_methods(self,symbol):
        for base,bindings in self.ancestors(symbol):
            for method in base['ast'].many(base['node'],'members'):
                mods=method.get('mods','')
                if method['kind']!='METHOD' or method.get('name')=='<init>' or any(m in mods for m in ('private','static')):continue
                public=base['node']['kind'] in {'INTERFACE','ANNOTATION_TYPE'} or any(m in mods for m in ('public','protected'))
                if not public and base['package']!=symbol['package']:continue
                yield base,method,self.signature(base,method,bindings)

    def overrides(self,symbol,method):
        if method.get('name')=='<init>' or any(m in method.get('mods','') for m in ('private','static')):return []
        signature=self.signature(symbol,method)
        return [(base,m) for base,m,sig in self.inherited_methods(symbol) if sig==signature]

    def object_override(self,symbol,method):
        if any(m in method.get('mods','') for m in ('private','static')):return False
        name,params=self.signature(symbol,method)
        return (name,params) in {('toString',()),('hashCode',()),('equals',('java.lang.Object',)),('clone',()),('finalize',())}

    def is_serializable(self,symbol):
        if symbol['node']['kind']=='ENUM':return True
        nodes=[symbol,*[base for base,_ in self.ancestors(symbol)]]
        return any(self.resolve_type(split_type(raw)[0],s['ast'],s) in {'java.io.Serializable','java.io.Externalizable'} for s in nodes for raw in self.base_types(s))

    def has_hashcode(self,symbol):
        for method in symbol['ast'].many(symbol['node'],'members'):
            if method['kind']=='METHOD' and not any(x in method.get('mods','') for x in ('static','private')) and self.signature(symbol,method)==('hashCode',()) and symbol['ast'].src(symbol['ast'].get(method,'returnType'))=='int':return True
        return any(sig==('hashCode',()) and base['ast'].src(base['ast'].get(method,'returnType'))=='int' for base,method,sig in self.inherited_methods(symbol))

    def context(self):
        return {'mode':'project-source-symbol-index','indexed_classes':len(self.symbols),'indexed_source_files':len({id(s['ast']) for s in self.symbols}),'unresolved_bases':self.unresolved,'ambiguous_types':self.ambiguous,'external_classpath_loaded':False,'generic_model':'project base substitutions and erased method parameter signatures; no javac type attribution'}
