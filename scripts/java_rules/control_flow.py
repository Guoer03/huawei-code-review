"""Structured Java completion analysis over javac ASTs.

Composes normal/return/throw/break/continue/yield outcomes, resolves jump targets,
and applies catch dispatch and finally replacement. This is intraprocedural;
call completion and unknown external exception subtype relationships remain
conservative. It never executes expressions or loads analyzed classes.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Completion:
    kind: str
    origin: int = -1
    target: int = -1
    exception: str = ''


NORMAL=Completion('normal')
LOOPS={'FOR_LOOP','ENHANCED_FOR_LOOP','WHILE_LOOP','DO_WHILE_LOOP'}
BOUNDARIES={'METHOD','LAMBDA_EXPRESSION','CLASS','INTERFACE','ENUM','RECORD','ANNOTATION_TYPE'}
_UNKNOWN=object()
JAVA_EXCEPTIONS={
    'java.lang.RuntimeException':'java.lang.Exception',
    'java.lang.Exception':'java.lang.Throwable',
    'java.lang.Error':'java.lang.Throwable',
    'java.lang.AssertionError':'java.lang.Error',
    'java.lang.LinkageError':'java.lang.Error',
    'java.lang.VirtualMachineError':'java.lang.Error',
    'java.lang.OutOfMemoryError':'java.lang.VirtualMachineError',
    'java.lang.StackOverflowError':'java.lang.VirtualMachineError',
    'java.io.IOException':'java.lang.Exception',
    'java.io.FileNotFoundException':'java.io.IOException',
    'java.io.EOFException':'java.io.IOException',
    'java.sql.SQLException':'java.lang.Exception',
    'java.lang.InterruptedException':'java.lang.Exception',
    'java.lang.ReflectiveOperationException':'java.lang.Exception',
    'java.lang.ClassNotFoundException':'java.lang.ReflectiveOperationException',
    'java.lang.IllegalArgumentException':'java.lang.RuntimeException',
    'java.lang.NumberFormatException':'java.lang.IllegalArgumentException',
    'java.lang.IllegalStateException':'java.lang.RuntimeException',
    'java.lang.NullPointerException':'java.lang.RuntimeException',
    'java.lang.IndexOutOfBoundsException':'java.lang.RuntimeException',
    'java.lang.ArrayIndexOutOfBoundsException':'java.lang.IndexOutOfBoundsException',
    'java.lang.StringIndexOutOfBoundsException':'java.lang.IndexOutOfBoundsException',
    'java.lang.ClassCastException':'java.lang.RuntimeException',
    'java.lang.ArithmeticException':'java.lang.RuntimeException',
    'java.lang.SecurityException':'java.lang.RuntimeException',
    'java.lang.UnsupportedOperationException':'java.lang.RuntimeException',
    'java.lang.ArrayStoreException':'java.lang.RuntimeException',
    'java.lang.NegativeArraySizeException':'java.lang.RuntimeException',
    'java.util.ConcurrentModificationException':'java.lang.RuntimeException',
    'java.util.NoSuchElementException':'java.lang.RuntimeException',
}


class ControlFlow:
    def __init__(self,ast):
        self.a=ast
        self.cache={}

    def target(self,node):
        label=node.get('label');kind=node['kind'];a=self.a
        for parent in a.ancestors(node):
            if parent['kind'] in BOUNDARIES:break
            if label:
                if parent['kind']=='LABELED_STATEMENT' and parent.get('label')==label:
                    return a.get(parent,'body').get('id',-1) if kind=='CONTINUE' else parent['id']
            elif kind in {'BREAK','CONTINUE'} and parent['kind'] in LOOPS or kind=='BREAK' and parent['kind']=='SWITCH' or kind=='YIELD' and parent['kind']=='SWITCH_EXPRESSION':
                return parent['id']
        return -1

    def constant(self,node,seen=None):
        a=self.a;node=a.unwrap(node);kind=node.get('kind');seen=set() if seen is None else seen
        if kind=='CHAR_LITERAL':return ord(node['value'])
        # The bridge serializes Float.toString(), which does not preserve its
        # exact promoted double value. Do not prove branch reachability with it.
        if kind=='FLOAT_LITERAL':return _UNKNOWN
        if kind and kind.endswith('_LITERAL'):return node.get('value')
        if kind=='IDENTIFIER':
            declaration=a.declaration(node,node)
            if declaration and 'final' in declaration.get('mods','') and declaration['id'] not in seen:
                # Ast.declaration is a best-effort method-wide lookup. A local
                # from an already-exited block must not become a branch proof.
                scope=a.parent(declaration)
                if scope.get('id') not in {parent['id'] for parent in a.ancestors(node)}:return _UNKNOWN
                declared=a.src(a.get(declaration,'type'))
                if declared not in {'boolean','byte','short','char','int','long','String','java.lang.String'}:return _UNKNOWN
                value=self.constant(a.get(declaration,'initializer'),seen|{declaration['id']})
                # Boxed/reference identities and numeric conversions are not
                # source constants. Restrict propagation to exact value kinds.
                if declared=='boolean':return value if isinstance(value,bool) else _UNKNOWN
                if declared in {'String','java.lang.String'}:return value if isinstance(value,str) else _UNKNOWN
                return value if isinstance(value,int) and not isinstance(value,bool) else _UNKNOWN
        if kind in {'LOGICAL_COMPLEMENT','UNARY_MINUS','UNARY_PLUS','BITWISE_COMPLEMENT'}:
            value=self.constant(a.get(node,'expr'),seen)
            if value is _UNKNOWN:return _UNKNOWN
            if kind=='LOGICAL_COMPLEMENT':return not value if isinstance(value,bool) else _UNKNOWN
            if isinstance(value,(int,float)) and not isinstance(value,bool):
                if kind=='UNARY_MINUS':
                    # Java negation wraps MIN_VALUE, whereas Python integers
                    # are unbounded. Retain both paths if width is ambiguous.
                    if value in {-2147483648,-9223372036854775808}:return _UNKNOWN
                    return -value
                return +value if kind=='UNARY_PLUS' else ~value if isinstance(value,int) else _UNKNOWN
        left=self.constant(a.get(node,'left'),seen) if 'left' in node else _UNKNOWN
        right=self.constant(a.get(node,'right'),seen) if 'right' in node else _UNKNOWN
        if left is _UNKNOWN or right is _UNKNOWN:return _UNKNOWN
        # Java binary numeric promotion may round a long when converted to
        # floating point. Python's mixed equality/comparison behaves differently.
        if type(left) is not type(right):return _UNKNOWN
        try:
            if kind=='CONDITIONAL_AND':return left and right
            if kind=='CONDITIONAL_OR':return left or right
            if kind=='EQUAL_TO':return left==right
            if kind=='NOT_EQUAL_TO':return left!=right
            if kind=='LESS_THAN':return left<right
            if kind=='LESS_THAN_EQUAL':return left<=right
            if kind=='GREATER_THAN':return left>right
            if kind=='GREATER_THAN_EQUAL':return left>=right
            # Avoid unsound Java integer overflow by leaving arithmetic unknown.
        except (TypeError,ValueError):pass
        return _UNKNOWN

    def sequence(self,nodes):
        result={NORMAL}
        for node in nodes:
            if NORMAL not in result:break
            result=(result-{NORMAL})|self.flow(node)
        return result

    @staticmethod
    def then(first,second):
        return first-{NORMAL}|second if NORMAL in first else first

    def exception_type(self,statement):
        a=self.a;expr=a.get(statement,'expr')
        if expr.get('kind')=='NULL_LITERAL':return 'java.lang.NullPointerException'
        declaration=a.declaration(expr,statement)
        if declaration and a.parent(declaration).get('id') not in {parent['id'] for parent in a.ancestors(statement)}:
            # An expired local's type must not prove that an actual field throw
            # is consumed by a catch. Unknown keeps the explicit throw possible.
            return ''
        raw=a.type(expr,statement)
        context=a.project.symbol(a,a.clazz(statement))
        return a.project.resolve_type(raw,a,context) if raw else ''

    def subtype(self,child,parent):
        if child==parent or parent=='java.lang.Throwable':return True
        a=self.a;pending=[child];seen=set()
        while pending:
            name=pending.pop()
            if name in seen:continue
            seen.add(name)
            if name==parent:return True
            if name in JAVA_EXCEPTIONS:pending.append(JAVA_EXCEPTIONS[name])
            symbol=a.project.lookup(name,a)
            if symbol:
                for raw in a.project.base_types(symbol):
                    pending.append(a.project.resolve_type(raw,symbol['ast'],symbol))
        return False

    def catches(self,outcome,catch):
        a=self.a;parameter=a.get(catch,'parameter');context=a.project.symbol(a,a.clazz(catch))
        return any(self.subtype(outcome.exception,a.project.resolve_type(raw.strip(),a,context)) for raw in a.src(a.get(parameter,'type')).split('|'))

    def may_throw_implicitly(self,node):
        """Conservative feasibility for catch branches from evaluated code."""
        a=self.a
        def walk(current):
            if current.get('kind') in BOUNDARIES:return False
            if current.get('kind') in {'METHOD_INVOCATION','NEW_CLASS','NEW_ARRAY','ARRAY_ACCESS','MEMBER_SELECT','SYNCHRONIZED','DIVIDE','REMAINDER','TYPE_CAST','THROW'}:return True
            # Without type attribution, an identifier may be implicitly unboxed
            # by its expression context. Do not eliminate its catch path.
            if current.get('kind')=='IDENTIFIER' and a.type(current,current) not in {'boolean','byte','short','char','int','long','float','double'}:return True
            return any(walk(child) for child in a.children.get(current.get('id'),[]))
        return walk(node)

    def flow(self,node):
        if not node:return {NORMAL}
        identity=node['id']
        if identity in self.cache:return set(self.cache[identity])
        result=self._flow(node)
        self.cache[identity]=frozenset(result)
        return result

    def expression(self,node):
        """Evaluate explicit control-bearing expressions in Java order."""
        if not node:return {NORMAL}
        a=self.a;kind=node['kind']
        if kind in BOUNDARIES:return {NORMAL}
        if kind=='SWITCH_EXPRESSION':return self.flow(node)
        if kind=='CONDITIONAL_EXPRESSION':
            condition=a.get(node,'condition');first=self.expression(condition);value=self.constant(condition)
            branch=self.expression(a.get(node,'true')) if value is True else self.expression(a.get(node,'false')) if value is False else self.expression(a.get(node,'true'))|self.expression(a.get(node,'false'))
            return first-{NORMAL}|branch if NORMAL in first else first
        if kind in {'CONDITIONAL_AND','CONDITIONAL_OR'}:
            left=a.get(node,'left');first=self.expression(left);value=self.constant(left)
            if NORMAL not in first:return first
            if kind=='CONDITIONAL_AND' and value is False or kind=='CONDITIONAL_OR' and value is True:return first
            right=self.expression(a.get(node,'right'))
            return first-{NORMAL}|right|({NORMAL} if value is _UNKNOWN else set())
        result={NORMAL}
        for child in a.children.get(node.get('id'),[]):
            if child['kind'] in BOUNDARIES:continue
            if NORMAL not in result:break
            result=result-{NORMAL}|self.expression(child)
        return result

    def _flow(self,node):
        a=self.a;kind=node['kind']
        if kind=='BLOCK':return self.sequence(a.many(node,'statements'))
        if kind in BOUNDARIES:return {NORMAL}
        if kind in {'RETURN','THROW','BREAK','CONTINUE','YIELD'}:
            expression=self.expression(a.get(node,'expr'))
            transfer=Completion(kind.lower(),node['id'],self.target(node) if kind in {'BREAK','CONTINUE','YIELD'} else -1,self.exception_type(node) if kind=='THROW' else '')
            return expression-{NORMAL}|({transfer} if NORMAL in expression else set())
        if kind=='IF':
            expr=a.get(node,'condition');first=self.expression(expr);condition=self.constant(expr)
            if condition is True:return self.then(first,self.flow(a.get(node,'then')))
            if condition is False:return self.then(first,self.flow(a.get(node,'else')))
            return self.then(first,self.flow(a.get(node,'then'))|self.flow(a.get(node,'else')))
        if kind=='LABELED_STATEMENT':
            body=self.flow(a.get(node,'body'))
            return {NORMAL if item.kind=='break' and item.target==node['id'] else item for item in body}
        if kind=='SYNCHRONIZED':return self.then(self.expression(a.get(node,'expr')),self.flow(a.get(node,'body')))
        if kind in LOOPS:
            expression=a.get(node,'condition')
            condition=self.constant(expression) if expression else True if kind=='FOR_LOOP' else _UNKNOWN
            first=self.sequence(a.many(node,'initializers')) if kind=='FOR_LOOP' else self.expression(a.get(node,'expr')) if kind=='ENHANCED_FOR_LOOP' else {NORMAL}
            if kind!='DO_WHILE_LOOP':first=self.then(first,self.expression(expression))
            if NORMAL not in first:return first
            if kind!='DO_WHILE_LOOP' and condition is False:return first
            body=self.flow(a.get(node,'body'));out=set()
            for item in body:
                if item.kind=='break' and item.target==node['id']:out.add(NORMAL)
                elif item.kind=='continue' and item.target==node['id'] or item==NORMAL:
                    updates=self.sequence(a.many(node,'updates')) if kind=='FOR_LOOP' else {NORMAL}
                    iteration=self.then(updates,self.expression(expression))
                    out|=iteration-{NORMAL}
                    if condition is not True and NORMAL in iteration:out.add(NORMAL)
                else:out.add(item)
            if kind!='DO_WHILE_LOOP' and condition is not True:out.add(NORMAL)
            return self.then(first,out)
        if kind in {'SWITCH','SWITCH_EXPRESSION'}:
            cases=a.many(node,'cases');out=set()
            starts=list(enumerate(cases));selector=self.constant(a.get(node,'expr'))
            selector_resolved=False
            chosen=None
            if selector is not _UNKNOWN:
                values=[(index,[self.constant(label) for label in a.many(case,'labels')]) for index,case in starts]
                has_unknown=any(any(value is _UNKNOWN for value in labels) or not labels and not cases[index].get('hasDefault') for index,labels in values)
                if not has_unknown:
                    selector_resolved=True
                    chosen=next((index for index,labels in values if selector in labels),None)
                    if chosen is None:chosen=next((index for index,case in starts if case.get('hasDefault')),None)
                    starts=[] if chosen is None else [(chosen,cases[chosen])]
            for index,case in starts:
                if case.get('caseKind')=='RULE':branch=self.flow(a.get(case,'body'))
                else:
                    statements=[s for remaining in cases[index:] for s in a.many(remaining,'statements')]
                    branch=self.sequence(statements)
                for item in branch:
                    if item.target==node['id'] and item.kind in {'break','yield'}:out.add(NORMAL)
                    else:out.add(item)
            # A statement without default can complete normally when the
            # selector is unknown, or when a resolved constant selects no case.
            # Once a resolved constant selects a case, an abrupt case body must
            # remain abrupt; adding NORMAL unconditionally would invent an
            # impossible fall-through path for nested switches.
            if not any(c.get('hasDefault') for c in cases) and kind=='SWITCH' and (not selector_resolved or chosen is None):out.add(NORMAL)
            return self.then(self.expression(a.get(node,'expr')),out)
        if kind=='TRY':
            body=a.get(node,'body');pending=self.then(self.sequence(a.many(node,'resources')),self.flow(body));caught=set();catches=a.many(node,'catches')
            for outcome in pending:
                if outcome.kind!='throw':caught.add(outcome);continue
                handler=next((c for c in catches if self.catches(outcome,c)),None)
                if handler:caught|=self.flow(a.get(handler,'body'))
                else:caught.add(outcome)
            # A call may throw an unchecked/declared exception even without an
            # explicit throw node. Include handler branches conservatively.
            # Resource initialization and close may throw even with an empty
            # try body. This admits possible catch paths, without guessing the
            # resource's exact exception type or executing its implementation.
            if node.get('resources') or self.may_throw_implicitly(body):
                for handler in catches:caught|=self.flow(a.get(handler,'body'))
            final=a.get(node,'finally')
            if final and caught:
                final_out=self.flow(final)
                return (caught if NORMAL in final_out else set())|(final_out-{NORMAL})
            return caught
        # Evaluate embedded switch expressions, but do not enter lambdas or
        # nested/anonymous class bodies when evaluating a declaration/call.
        return self.expression(node)

    def escaping_finally(self,node):
        """Explicit transfers surviving the finally body's own control flow."""
        return [self.a.byid[outcome.origin] for outcome in self.flow(node)
                if outcome.kind in {'return','throw','break','continue'} and outcome.origin in self.a.byid]

    def can_complete(self,statements):
        return NORMAL in self.sequence(statements)
