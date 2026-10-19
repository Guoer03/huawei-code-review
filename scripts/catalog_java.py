"""CodeArts Java catalog checks using the JDK compiler syntax-tree API.

Parsing is dependency-free and does not execute project code. Type-sensitive and
flow-sensitive checks intentionally expose partial coverage, not soundness claims.
"""
from __future__ import annotations

import json
import ipaddress
import os
import re
import shutil
import subprocess
import tempfile
from collections import Counter
from pathlib import Path
try:
    from .java_rules.project_symbols import ProjectSymbols
    from .java_rules.control_flow import ControlFlow
except ImportError:
    from java_rules.project_symbols import ProjectSymbols
    from java_rules.control_flow import ControlFlow

ROOT = Path(__file__).resolve().parents[1]
DATA = Path(__file__).with_name('java_rules')
_JAVA_VERSIONS = {}


def _java():
    candidates = [os.environ.get('HUAWEI_JAVA'), shutil.which('java'), '/opt/homebrew/opt/openjdk@21/libexec/openjdk.jdk/Contents/Home/bin/java']
    if os.environ.get('JAVA_HOME'):
        candidates.insert(1, str(Path(os.environ['JAVA_HOME']) / 'bin/java'))
    for executable in candidates:
        if executable and Path(executable).is_file():
            try:
                p = subprocess.run([executable, '-version'], capture_output=True, text=True, timeout=10)
                version = re.search(r'version "(\d+)', p.stderr + p.stdout)
                if p.returncode == 0 and version and int(version[1]) >= 21:
                    _JAVA_VERSIONS[executable]=(p.stderr+p.stdout).strip().splitlines()[0]
                    return executable
            except (OSError, subprocess.SubprocessError):
                pass
    return None


class Ast:
    def __init__(self, record, text):
        self.record, self.text = record, text
        self.nodes = record['nodes']
        # javac offsets count UTF-16 code units; Python indexes Unicode scalars.
        if any(ord(char)>0xffff for char in text):
            offsets=[]
            for index,char in enumerate(text):
                offsets.extend([index]*(2 if ord(char)>0xffff else 1))
            offsets.append(len(text))
            for node in self.nodes:
                for field in ('start','end'):
                    if 0<=node[field]<len(offsets):node[field]=offsets[node[field]]
                if node['start']>=0:node['column']=node['start']-text.rfind('\n',0,node['start'])
        self.byid = {n['id']: n for n in self.nodes}
        self.children = {}
        for node in self.nodes:
            self.children.setdefault(node['parent'], []).append(node)
        self.lines = text.splitlines()

    def get(self, node, key):
        return self.byid.get(node.get(key, -1), {})

    def many(self, node, key):
        return [self.byid[i] for i in node.get(key, []) if i in self.byid]

    def src(self, node):
        return self.text[max(0, node.get('start', 0)):max(0, node.get('end', 0))]

    def parent(self, node):
        return self.byid.get(node.get('parent', -1), {})

    def ancestors(self, node):
        while node.get('parent', -1) in self.byid:
            node = self.parent(node)
            yield node

    def under(self, node):
        for child in self.children.get(node.get('id', -1), []):
            yield child
            yield from self.under(child)

    def kind(self, *kinds):
        return [n for n in self.nodes if n['kind'] in kinds]

    def unwrap(self, node):
        while node.get('kind') == 'PARENTHESIZED':
            node = self.get(node, 'expr')
        return node

    def method(self, node):
        return next((n for n in self.ancestors(node) if n['kind'] == 'METHOD'), {})

    def clazz(self, node):
        return next((n for n in self.ancestors(node) if n['kind'] in {'CLASS', 'INTERFACE', 'ENUM', 'RECORD'}), {})

    def declaration(self, expr, at):
        name = self.src(self.unwrap(expr))
        if not re.fullmatch(r'(?:this\.)?[A-Za-z_$][\w$]*', name):
            return {}
        name = name.removeprefix('this.')
        method = self.method(at)
        local = [n for n in self.kind('VARIABLE') if n.get('name') == name and self.method(n).get('id') == method.get('id') and n['start'] <= at['start']]
        if local:
            return max(local, key=lambda n: n['start'])
        cls = self.clazz(at)
        return next((n for n in self.many(cls, 'members') if n['kind'] == 'VARIABLE' and n.get('name') == name), {})

    def type(self, expr, at=None):
        expr = self.unwrap(expr)
        if expr.get('kind') in {'STRING_LITERAL', 'CHAR_LITERAL', 'INT_LITERAL', 'LONG_LITERAL', 'FLOAT_LITERAL', 'DOUBLE_LITERAL', 'BOOLEAN_LITERAL', 'NULL_LITERAL'}:
            return {'STRING_LITERAL':'String', 'CHAR_LITERAL':'char', 'INT_LITERAL':'int', 'LONG_LITERAL':'long', 'FLOAT_LITERAL':'float', 'DOUBLE_LITERAL':'double', 'BOOLEAN_LITERAL':'boolean','NULL_LITERAL':'null'}[expr['kind']]
        if expr.get('kind') in {'NEW_CLASS', 'TYPE_CAST'}:
            return self.src(self.get(expr, 'type'))
        var = self.declaration(expr, at or expr)
        return self.src(self.get(var, 'type')) if var else ''

    def call(self, node):
        select = self.get(node, 'select')
        return select.get('name', self.src(select)), self.get(select, 'expr'), self.many(node, 'args')

    def platform_type(self, typ, qualified):
        """Resolve explicit/local names before falling back to java.lang/imports.

        This avoids conflating user-defined System/Thread/String classes with JDK
        APIs. Dependency-wide type attribution remains outside parse-only scope.
        """
        if typ==qualified:return True
        short=qualified.rsplit('.',1)[-1]
        if typ!=short:return False
        if any(n.get('name')==short for n in self.kind('CLASS','INTERFACE','ENUM','RECORD','ANNOTATION_TYPE','TYPE_PARAMETER')):return False
        explicit=[n['name'] for n in self.kind('IMPORT') if n['name'].rsplit('.',1)[-1]==short and not n.get('static')]
        if explicit:return explicit==[qualified]
        return qualified.startswith('java.lang.') or any(n['name']==qualified.rsplit('.',1)[0]+'.*' for n in self.kind('IMPORT'))

    def platform_owner(self, expr, qualified, at):
        source=self.src(expr)
        return source==qualified or self.platform_type(source,qualified) and not self.declaration(expr,at)



def _checks(ast, emit, limits=None):
    a = ast
    a.control_flow=ControlFlow(a)
    limits=limits or {'parameters':5,'method_length':50,'nesting':4}
    classes = {'CLASS', 'INTERFACE', 'ENUM', 'RECORD', 'ANNOTATION_TYPE'}
    containers = re.compile(r'(?:List|Set|Map|Collection|Queue|Deque|Iterable|ArrayList|HashMap|HashSet|\[\])')
    wrap = {'Boolean','Byte','Short','Integer','Long','Float','Double','Character','String'}
    names = a.kind('CLASS','INTERFACE','ENUM','RECORD','ANNOTATION_TYPE','METHOD','VARIABLE','TYPE_PARAMETER')
    for n in names:
        name, kind, mods = n.get('name', ''), n['kind'], n.get('mods', '')
        if name not in {'<init>', ''} and (len(name) > 64 or not re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*', name)):
            emit('identifier', n, '标识符必须由最多64个字母、数字或下划线组成。')
        if kind in classes and name and not re.fullmatch(r'[A-Z][A-Za-z0-9]*', name):
            emit('class_name', n, '类型名应采用大驼峰命名。')
        if kind == 'METHOD' and name != '<init>' and not re.fullmatch(r'[a-z][A-Za-z0-9]*', name):
            emit('method_name', n, '方法名应采用小驼峰命名。')
        if kind == 'VARIABLE':
            typ = a.src(a.get(n,'type'))
            is_field = a.parent(n).get('kind') in classes
            is_constant = is_field and 'static' in mods and 'final' in mods
            if is_constant and not re.fullmatch(r'[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)*',name):
                emit('constant_name', n, '静态常量应使用全大写字母和下划线命名。')
            if not is_constant and not re.fullmatch(r'[a-z][A-Za-z0-9]*', name):
                emit('variable_name', n, '变量应采用小驼峰命名。')
            if typ in {'boolean','Boolean','java.lang.Boolean'}:
                if re.match(r'(?:not|no|non|disable|invalid|unavailable|isNot|isNo|isDisabled)(?:[A-Z_]|$)',name):
                    emit('negative_boolean',n,'布尔变量名包含否定含义。')
                if not re.match(r'(?:is|has|can|should|will|must|need|allow|enable|contains|exists|supports)(?:[A-Z_]|$)',name):
                    emit('boolean_name',n,'建议布尔变量以表达是非意义的动词开头。')
            if is_field and 'public' in mods and 'final' not in mods:
                emit('public_field', n, '避免公开可变的类属性。')
            if is_field and all(m in mods for m in ('public','static','final')) and (containers.search(typ) or typ.endswith('[]')):
                init = a.src(a.get(n,'initializer'))
                if not re.match(r'(?:List|Set|Map)\.of\(|Collections\.(?:empty|singleton|unmodifiable)',init):
                    emit('mutable_constant', n,'public static final 只保护引用，数组或可变集合仍可被修改。')
            if is_field and typ.split('.')[-1] == 'Logger' and not ('private' in mods and 'final' in mods):
                emit('logger_modifiers',n,'Logger实例应声明为private final或private static final。')
            if re.match(r'(?:java\.util\.)?Optional(?:<|$)',typ) and a.get(n,'initializer').get('kind')=='NULL_LITERAL':
                emit('optional_null',n,'Optional变量不应初始化为null。')
            if re.search(r'\b'+re.escape(name)+r'\s*\[',a.src(n).split('=')[0]):
                emit('c_array',n,'数组维度应写在类型后，而不是变量名后。')
            if a.parent(n).get('kind')=='FOR_LOOP' and typ in {'float','double','Float','Double'}:
                emit('float_loop',n,'禁止使用浮点类型的循环计数器。')
        if kind=='TYPE_PARAMETER' and not n.get('bounds'):
            emit('generic_bound',n,'泛型类型参数未声明上界；需要按接口契约判断合理约束。')
        if kind in classes|{'METHOD','VARIABLE'} and any(x in mods for x in ('public','protected')):
            if kind!='VARIABLE' or a.parent(n).get('kind') in classes:
                if n.get('doc') is None:
                    emit('public_javadoc',n,'public/protected元素缺少Javadoc。')
        if kind in classes and a.parent(n).get('kind')=='COMPILATION_UNIT' and 'public' in mods:
            doc=n.get('doc') or ''
            if not doc.strip() or not re.search(r'@(?:since|version)\b|\d{4}[-/.年]\d',doc):
                emit('class_javadoc',n,'顶层public类型需要功能说明和创建日期/版本信息。')
        if kind=='METHOD':
            params=a.many(n,'params'); body=a.get(n,'body'); throws=a.many(n,'throws')
            if len(params)>limits['parameters']:emit('parameter_count',n,f"方法有{len(params)}个参数，超过{limits['parameters']}个。")
            if len(throws)>5:emit('throws_count',n,f'方法声明抛出{len(throws)}种异常，超过5种。')
            if body and a.src(body).count('\n')+1>limits['method_length']:emit('method_length',n,f"方法体超过{limits['method_length']}行。")
            if name=='finalize' and not params:emit('finalizer',n,'不要使用Finalizer机制。')
            if any('...' in a.src(p) for p in params):emit('varargs',n,'可变参数方法需要评估调用成本和API约束。')
            if body:
                statements=a.many(body,'statements')
                for first,second in zip(statements,statements[1:]):
                    if first['kind']=='VARIABLE' and second['kind']=='RETURN' and a.src(a.get(second,'expr'))==first.get('name'):
                        emit('temporary_return',first,'局部变量声明后立即返回，可直接返回初始化表达式。')
                nested=max([sum(1 for q in a.ancestors(x) if q['kind'] in {'IF','FOR_LOOP','ENHANCED_FOR_LOOP','WHILE_LOOP','DO_WHILE_LOOP','SWITCH','TRY','SYNCHRONIZED'} and q['start']>=body['start'])+1 for x in a.under(body) if x['kind'] in {'IF','FOR_LOOP','ENHANCED_FOR_LOOP','WHILE_LOOP','DO_WHILE_LOOP','SWITCH','TRY','SYNCHRONIZED'}] or [0])
                if nested>limits['nesting']:emit('nesting',n,f"控制结构嵌套深度为{nested}，超过{limits['nesting']}层。")
            doc=n.get('doc')
            if doc is not None:
                if not re.sub(r'@\w+[^\n]*','',doc).strip():emit('empty_javadoc',n,'Javadoc缺少功能说明。')
                tags=re.findall(r'@(param|return|throws|exception)\b',doc); order={'param':0,'return':1,'throws':2,'exception':2}
                if any(order[x]>order[y] for x,y in zip(tags,tags[1:])) or any(not re.search(r'@param\s+'+re.escape(p['name'])+r'\b',doc) for p in params) or (a.src(a.get(n,'returnType')) not in {'','void'} and '@return' not in doc) or any(not re.search(r'@(?:throws|exception)\s+'+re.escape(a.src(t).split('.')[-1])+r'\b',doc) for t in throws):
                    emit('javadoc_tags',n,'Javadoc参数、返回值、异常标签缺失或顺序错误。')
                first_tag = re.search(r'^[ \t]*@(?:param|return|throws)\b',doc,re.M)
                if first_tag and doc[:first_tag.start()].strip() and not re.search(r'\n[ \t]*\n[ \t]*$',doc[:first_tag.start()]):emit('javadoc_blank',n,'功能描述与Javadoc标签之间缺少空行。')
            for annotation in a.many(n,'annotations'):
                pass
        if kind in classes:
            members=a.many(n,'members'); methods=[x for x in members if x['kind']=='METHOD']
            symbol=a.project.symbol(a,n)
            serial=bool(symbol and a.project.is_serializable(symbol) and kind not in {'INTERFACE','ANNOTATION_TYPE','ENUM','RECORD'})
            if serial:
                emit('serializable',n,'实现Serializable增加反序列化攻击面，请确认必要性。')
                if not any(x.get('name')=='serialVersionUID' for x in members):emit('serial_uid',n,'可序列化类未显式声明serialVersionUID。')
                if a.parent(n).get('kind') in classes and 'static' not in mods:emit('serial_inner',n,'不要序列化非静态内部类。')
                for field in members:
                    typ=a.src(a.get(field,'type')).split('.')[-1]
                    if field['kind']=='VARIABLE' and 'transient' not in field.get('mods','') and 'static' not in field.get('mods','') and typ in {'FileInputStream','FileOutputStream','InputStream','OutputStream','Socket','ServerSocket','Connection','Thread','Process'}:
                        emit('serial_resource',field,'系统资源字段不应直接参与序列化。')
            if symbol and any(m.get('name')=='equals' and a.project.object_override(symbol,m) for m in methods) and not a.project.has_hashcode(symbol):
                emit('equals_hashcode',n,'覆写equals(Object)时必须同时覆写hashCode()。')
            for annotation in a.many(n,'annotations'):
                if annotation.get('name','').split('.')[-1]=='SuppressWarnings':emit('class_suppress',annotation,'避免在整个类上使用SuppressWarnings。')
            for m in methods:
                if m.get('name')=='<init>':
                    for call in a.under(a.get(m,'body')):
                        if call['kind']=='METHOD_INVOCATION':
                            cname,recv,args=a.call(call)
                            target=next((q for q in methods if q.get('name')==cname and len(q.get('params',[]))==len(args)),{})
                            if a.src(recv) in {'','this'} and target and not any(x in target.get('mods','') for x in ('final','private','static')) and 'final' not in mods:
                                emit('constructor_override',call,'构造方法调用了本类可被覆写的方法。')
                for other in methods:
                    if m['id']>=other['id'] or m.get('name')!=other.get('name') or len(m.get('params',[]))!=len(other.get('params',[])):continue
                    types=[a.src(a.get(p,'type')) for p in a.many(m,'params')]; other_types=[a.src(a.get(p,'type')) for p in a.many(other,'params')]
                    pairs=dict(zip(['boolean','byte','short','int','long','float','double','char'],['Boolean','Byte','Short','Integer','Long','Float','Double','Character']))
                    if types!=other_types and all(x==y or pairs.get(x)==y or pairs.get(y)==x for x,y in zip(types,other_types)):emit('boxing_overload',other,'避免仅以基本类型和对应包装类型区别重载方法。')
            if kind=='INTERFACE':
                for member in members:
                    if member['kind']=='METHOD' and any(x in member.get('mods','') for x in ('public','abstract')):emit('interface_modifiers',member,'接口方法不需要显式public/abstract修饰符。')
                    if member['kind']=='VARIABLE' and any(x in member.get('mods','') for x in ('public','static','final')):emit('interface_modifiers',member,'接口常量不需要显式public static final修饰符。')

    if a.record.get('package') and any(c.isupper() for c in a.record['package']):
        emit('package_name',next(iter(a.nodes)), '包名中的字母应为小写。')

    for n in a.nodes:
        kind=n['kind']
        if kind=='ASSERT':emit('assert',n,'代码中不应使用assert。')
        if kind in {'IF','FOR_LOOP','WHILE_LOOP','DO_WHILE_LOOP'}:
            cond=a.get(n,'condition')
            if any(x['kind']=='ASSIGNMENT' for x in [cond,*a.under(cond)]):emit('condition_assignment',n,'控制条件中存在赋值操作。')
        if kind in {'IF','FOR_LOOP','ENHANCED_FOR_LOOP','WHILE_LOOP','DO_WHILE_LOOP'}:
            for key in (('then','else') if kind=='IF' else ('body',)):
                block=a.get(n,key)
                if block and block['kind']!='BLOCK' and not (key=='else' and block['kind']=='IF'):
                    emit('braces',block,'控制结构的语句体必须使用大括号。')
            if kind=='IF' and a.get(n,'else').get('kind')=='IF':
                tail=a.get(n,'else')
                while a.get(tail,'else').get('kind')=='IF':tail=a.get(tail,'else')
                if not a.get(tail,'else'):emit('final_else',n,'else if链缺少最后的else分支。')
        if kind in {'SWITCH','SWITCH_EXPRESSION'} and not any(c.get('hasDefault') for c in a.many(n,'cases')):
            emit('switch_default',n,'switch缺少default分支。')
        if kind=='CATCH':
            param=a.get(n,'parameter'); typ=a.src(a.get(param,'type'));body=a.get(n,'body')
            if any(a.platform_type(t.strip(),'java.lang.'+base) for t in typ.split('|') for base in {'Exception','Throwable','RuntimeException'}):emit('broad_catch',n,'不要直接捕获Throwable、Exception或RuntimeException。')
            if any(a.platform_type(t.strip(),'java.lang.'+base) for t in typ.split('|') for base in {'NullPointerException','IndexOutOfBoundsException','ArrayIndexOutOfBoundsException','ClassCastException','ArithmeticException'}):emit('precheck_catch',n,'该运行时异常应优先通过前置条件检查避免。')
            if not body.get('statements'):emit('empty_catch',n,'空catch块忽略了异常。')
            for thrown in a.under(body):
                if thrown['kind']=='THROW':
                    expr=a.get(thrown,'expr')
                    if expr.get('kind')=='NEW_CLASS' and not any(a.src(arg)==param.get('name') for arg in a.many(expr,'args')):
                        emit('lost_exception',thrown,'新异常未携带捕获的异常作为cause；请确认是否通过initCause保留。')
        if kind=='TRY':
            final=a.get(n,'finally')
            for x in a.control_flow.escaping_finally(final):
                emit('finally_abrupt',x,'控制流分析发现finally块可能通过此语句非正常结束，覆盖原有返回值或异常。')
                if x['kind']=='RETURN':emit('finally_return',x,'此return可能使finally块非正常结束。')
                if x['kind']=='THROW':emit('finally_throw',x,'此throw的异常可能逃出finally块。')
        if kind=='RETURN':
            method=a.method(n);typ=a.src(a.get(method,'returnType'))
            if a.get(n,'expr').get('kind')=='NULL_LITERAL':
                if containers.search(typ):emit('null_collection',n,'返回空数组或空集合，不要返回null。')
                if re.match(r'(?:java\.util\.)?Optional(?:<|$)',typ):emit('optional_null',n,'Optional返回值不能为null。')
        if kind in {'ASSIGNMENT','PLUS_ASSIGNMENT','MINUS_ASSIGNMENT','MULTIPLY_ASSIGNMENT','DIVIDE_ASSIGNMENT','PREFIX_INCREMENT','POSTFIX_INCREMENT','PREFIX_DECREMENT','POSTFIX_DECREMENT'}:
            var=a.get(n,'variable') if 'variable' in n else a.get(n,'expr');method=a.method(n)
            if a.src(var) in {p.get('name') for p in a.many(method,'params')}:emit('parameter_mutation',n,'方法参数被重新赋值或增减，不应当作临时变量。')
            if a.type(var,n).startswith('Optional') and a.get(n,'expr').get('kind')=='NULL_LITERAL':emit('optional_null',n,'Optional不应赋值为null。')
        if kind in {'EQUAL_TO','NOT_EQUAL_TO','LESS_THAN','LESS_THAN_EQUAL','GREATER_THAN','GREATER_THAN_EQUAL'}:
            left,right=a.get(n,'left'),a.get(n,'right');lt,rt=a.type(left,n),a.type(right,n)
            if any(a.src(x) in {'Double.NaN','Float.NaN','java.lang.Double.NaN','java.lang.Float.NaN'} for x in (left,right)):emit('nan_compare',n,'NaN不能通过比较运算判断，使用isNaN()。')
            if kind in {'EQUAL_TO','NOT_EQUAL_TO'} and (lt in {'float','double','Float','Double'} or rt in {'float','double','Float','Double'}):emit('float_equality',n,'浮点数据不应直接判断相等。')
            if kind in {'EQUAL_TO','NOT_EQUAL_TO'} and lt=='String' and rt=='String':emit('string_equality',n,'字符串内容应使用equals比较。')
            if left.get('kind','').endswith('_LITERAL') and not right.get('kind','').endswith('_LITERAL'):emit('comparison_order',n,'比较表达式建议变量在左、常量在右。')
        if kind in {'DIVIDE','REMAINDER'} and a.get(n,'right').get('value')==0:emit('zero_divisor',n,'除数为字面量0。')
        if kind=='CONDITIONAL_EXPRESSION':
            lt,rt=a.type(a.get(n,'true'),n),a.type(a.get(n,'false'),n)
            if lt and rt and lt!=rt and 'null' not in {lt,rt}:emit('ternary_types',n,'条件表达式两个分支的静态可辨识类型不同。')
        if kind=='LONG_LITERAL' and a.src(n).endswith('l'):emit('long_suffix',n,'long字面量使用大写L后缀。')
        if kind=='BLOCK' and not n.get('statements') and a.parent(n).get('kind') not in {'METHOD','CATCH'}:
            emit('empty_block',n,'避免无语句的代码块。')
        if kind=='NEW_CLASS':
            typ=a.src(a.get(n,'type'));short=typ.split('.')[-1];args=a.many(n,'args')
            if any(a.platform_type(typ,'java.lang.'+boxed) for boxed in wrap):emit('unnecessary_object',n,'避免直接构造包装类型或String，优先valueOf或字面量。')
            if a.platform_type(typ,'java.lang.Thread'):
                emit('new_thread',n,'直接创建线程，请使用受控线程池。')
                if not any(a.platform_type(a.type(arg,n),'java.lang.String') or arg.get('kind')=='STRING_LITERAL' for arg in args):emit('thread_name',n,'新建线程未提供名称。')
            if short in {'FileReader','FileWriter'} and len(args)==1:emit('charset',n,'字符文件流未显式指定编码。')
            if short=='String' and len(args)==1 and a.type(args[0],n)=='byte[]':emit('charset',n,'字节转换字符串未指定编码。')
            if short=='ObjectInputStream':emit('deserialize',n,'反序列化入口需要验证来源、类型白名单和对象过滤器。')
            if short=='Socket':emit('plain_socket',n,'原始Socket未提供TLS；确认此连接是否传输敏感信息。')
            if short=='Random':emit('weak_random',n,'java.util.Random不适用于密码、令牌等安全场景。')
        if kind=='SYNCHRONIZED':
            expr=a.unwrap(a.get(n,'expr'));typ=a.type(expr,n);src=a.src(expr)
            if expr.get('kind')=='STRING_LITERAL' or typ in wrap-{'String'} or typ=='String':emit('reused_lock',n,'字符串或包装类型可能是共享缓存对象，不宜作为锁。')
            if src.endswith('.class'):emit('class_lock',n,'类字面量锁可能被外部代码共享，优先私有专用锁。')
            if typ.split('.')[-1].split('<')[0] in {'Lock','ReentrantLock','Semaphore','CountDownLatch','CyclicBarrier','AtomicInteger','AtomicLong'}:emit('concurrent_lock',n,'不要使用高级并发对象的监视器锁替代其并发API。')
            if src=='this':
                fields={x.get('name') for x in a.many(a.clazz(n),'members') if x['kind']=='VARIABLE' and 'static' in x.get('mods','')}
                if any(x['kind']=='IDENTIFIER' and x.get('name') in fields for x in a.under(a.get(n,'body'))):emit('instance_static_lock',n,'实例锁不能保护不同实例共享的static字段。')
        if kind=='ENHANCED_FOR_LOOP':
            collection=a.src(a.get(n,'expr'))
            for x in a.under(a.get(n,'body')):
                if x['kind']=='METHOD_INVOCATION':
                    name,recv,args=a.call(x)
                    if name in {'add','remove','clear','addAll','removeAll'} and a.src(recv)==collection:emit('foreach_mutation',x,'foreach遍历期间直接修改被遍历集合。')
        if kind!='METHOD_INVOCATION':continue
        name,recv,args=a.call(n);receiver=a.src(recv);typ=a.type(recv,n); short=typ.split('.')[-1]
        if a.platform_owner(recv,'java.lang.System',n):
            if name=='exit':emit('system_exit',n,'不要调用System.exit终止JVM。')
            if name in {'gc','runFinalization'}:emit('explicit_gc',n,'不要主动触发GC或Finalizer。')
        if name=='gc' and receiver in {'Runtime.getRuntime()','java.lang.Runtime.getRuntime()'}:emit('explicit_gc',n,'不要主动触发GC。')
        if name in {'toLowerCase','toUpperCase'} and not args and (a.platform_type(typ,'java.lang.String') or recv.get('kind')=='STRING_LITERAL'):emit('locale',n,'字符串大小写转换未显式指定Locale。')
        if name=='format' and a.platform_owner(recv,'java.lang.String',n) and args and (a.platform_type(a.type(args[0],n),'java.lang.String') or args[0].get('kind')=='STRING_LITERAL'):emit('locale',n,'格式化调用未显式指定Locale。')
        if name=='ordinal' and not args:emit('enum_ordinal',n,'避免依赖枚举ordinal作为持久化或业务标识。')
        if name in {'wait','notify','notifyAll'} and (receiver or name in {'wait','notify','notifyAll'}):emit('wait_notify',n,'优先使用java.util.concurrent并发工具替代wait/notify。')
        if name in {'stop','run','interrupt'} and a.platform_type(typ,'java.lang.Thread'):emit({'stop':'thread_stop','run':'thread_run','interrupt':'thread_interrupt'}[name],n,'直接调用Thread.'+name+'需要按线程协作规范处理。')
        if a.platform_owner(recv,'java.lang.Thread',n) and name=='yield':emit('thread_scheduling',n,'不要依赖Thread.yield的调度行为。')
        if a.platform_type(typ,'java.lang.Thread') and name=='setPriority':emit('thread_scheduling',n,'不要依赖线程优先级进行正确性控制。')
        if name=='getBytes' and not args and (a.platform_type(typ,'java.lang.String') or recv.get('kind')=='STRING_LITERAL'):emit('charset',n,'String.getBytes未指定字符编码。')
        if name=='toArray' and not args and containers.search(typ):emit('typed_toarray',n,'集合转数组应传入目标类型数组或数组构造器。')
        if name=='printStackTrace':emit('exception_leak',n,'直接输出异常堆栈可能暴露内部信息，应按日志策略处理。')
        if receiver in {'System.out','System.err'} and name in {'print','println','printf'}:emit('logging_facade',n,'使用日志Facade替代标准输出。')
        if name=='getInstance' and args and args[0].get('kind')=='STRING_LITERAL':
            algo=str(args[0].get('value','')).upper();owner=receiver.split('.')[-1]
            if owner=='Cipher':
                if algo=='AES' or 'AES/ECB/' in algo:emit('aes_ecb',n,'AES默认/ECB模式不提供安全的消息加密。')
                if algo=='RSA' or algo.endswith('/NOPADDING') and algo.startswith('RSA'):emit('rsa_padding',n,'RSA需要安全的显式填充方案。')
                if algo.split('/')[0] in {'DES','DESEDE','RC2','RC4','ARCFOUR','BLOWFISH'}:emit('weak_cipher',n,'使用了已过时或弱加密算法。')
            if owner=='MessageDigest' and algo in {'MD2','MD4','MD5','SHA','SHA-1','SHA1'}:emit('weak_hash',n,'使用了不安全的哈希算法。')
            if owner=='SSLContext' and algo in {'SSL','SSLV2','SSLV3','TLS','TLSV1','TLSV1.0','TLSV1.1'}:emit('old_tls',n,'明确使用TLS1.2及以上并核对实际启用协议。')
        if name in {'setEnabledProtocols','setProtocols'}:
            if any(x['kind']=='STRING_LITERAL' and str(x.get('value','')).upper() in {'SSLV2','SSLV3','TLSV1','TLSV1.0','TLSV1.1'} for arg in args for x in [arg,*a.under(arg)]):emit('old_tls',n,'协议列表包含不安全的SSL/TLS版本。')
        if name=='compile' and receiver.split('.')[-1]=='Pattern' and any(x['kind'] in {'FOR_LOOP','ENHANCED_FOR_LOOP','WHILE_LOOP','DO_WHILE_LOOP'} for x in a.ancestors(n)) and args and args[0].get('kind')=='STRING_LITERAL':emit('regex_loop',n,'循环体中重复预编译常量正则表达式。')
        if name=='read' and not args and any(x['kind']=='TYPE_CAST' and a.src(a.get(x,'type')) in {'byte','char'} for x in a.ancestors(n)):emit('read_int',n,'读取单字符/字节的结果应保留int以区分-1。')
        if name in {'execute','executeQuery','executeUpdate','prepareStatement'} and args and args[0].get('kind')=='PLUS':emit('sql_concat',n,'SQL调用接收了拼接字符串，需要参数化并确认数据来源。')
        if name in {'exec','start'} and (short in {'Runtime','ProcessBuilder'} or receiver=='Runtime.getRuntime()') and any(x.get('kind')!='STRING_LITERAL' for x in args):emit('command_input',n,'进程调用参数不是常量，需要验证外部输入及参数边界。')
        if name in {'forName','loadClass','getMethod','getDeclaredMethod'} and args and args[0].get('kind')!='STRING_LITERAL':emit('reflection_input',n,'动态反射名称需要来源验证和允许列表。')
        if name=='setSecure' and args and args[0].get('value') is False and short=='Cookie':emit('cookie_secure',n,'Cookie显式关闭了secure标志。')

    # Source-format rules are evaluated only after successful javac parsing.
    for i,line in enumerate(a.lines,1):
        loc={'line':i,'column':1,'start':0,'end':0}
        if len(line)>120:emit('line_length',loc,f'本行{len(line)}个字符，超过120。')
        if '\t' in line[:len(line)-len(line.lstrip())]:emit('indentation',loc,'缩进中含有Tab，应使用4个空格。')
        if i>2 and not line.strip() and not a.lines[i-2].strip() and not a.lines[i-3].strip():emit('blank_lines',loc,'连续空行过多。')
    comments = _comments(a.text)
    for start,text in comments:
        loc={'line':a.text.count('\n',0,start)+1,'column':start-a.text.rfind('\n',0,start),'start':start,'end':start+len(text)}
        if re.search(r'\b(?:TODO|FIXME)\b',text):emit('todo',loc,'交付代码中包含TODO/FIXME注释。')
        marker_len=3 if text.startswith('/**') else 2
        body=text[marker_len:] if text.startswith('//') else text[marker_len:-2]
        if body and not body[0].isspace():emit('comment_spacing',loc,'注释符与注释内容之间缺少空格。')
        if start and not a.text[start-1].isspace():emit('comment_spacing',loc,'代码与注释之间缺少空格。')
        end=start+len(text)
        if text.startswith('/*') and end<len(a.text) and not a.text[end].isspace():emit('comment_spacing',loc,'注释与后续代码之间缺少空格。')
        if text.startswith('//') and re.match(r'//\s*import\s+[\w.]+\s*;',text):emit('commented_import',loc,'删除不用的import，不要注释保留。')
        elif text.startswith('//') and re.search(r'\b(?:return|throw|if|for|while|new)\b.+[;{}]',text):emit('commented_code',loc,'注释中疑似保留了停用代码，需要人工核对后删除。')
    leading=a.text[:min((n['start'] for n in a.nodes if n['kind'] in classes|{'IMPORT','PACKAGE'} and n['start']>=0),default=0)]
    if not re.search(r'copyright|版权所有|SPDX-License-Identifier',leading,re.I):emit('copyright',{'line':1,'column':1},'文件头未找到版权或许可证声明。')
    _more_checks(a, emit)


def _more_checks(a, emit):
    """Additional structural checks; context-dependent results stay partial."""
    classes={'CLASS','INTERFACE','ENUM','RECORD','ANNOTATION_TYPE'}
    primitives={'boolean','byte','short','int','long','float','double','char','void'}
    resources={'FileInputStream','FileOutputStream','FileReader','FileWriter','BufferedReader','BufferedWriter','InputStreamReader','OutputStreamWriter','RandomAccessFile','ZipInputStream','ZipOutputStream','Scanner','ObjectInputStream','ObjectOutputStream'}
    statements={}
    for n in a.nodes:
        kind=n['kind']
        if kind in {'VARIABLE','EXPRESSION_STATEMENT','RETURN','THROW','BREAK','CONTINUE'} and a.parent(n).get('kind') in {'BLOCK','CASE','CLASS','INTERFACE'}:
            statements.setdefault(n['line'],[]).append(n)
        if kind in {'CLASS','INTERFACE','METHOD','VARIABLE'}:
            annotations=a.many(n,'annotations')
            if kind!='VARIABLE' or a.parent(n).get('kind') in classes:
                for ann in annotations:
                    tail=a.text[ann['end']:n['end']].split('\n',1)[0]
                    if tail.strip():emit('annotation_lines',ann,'应用于类型、方法或字段的注解应独占一行。')
            order=['public','protected','private','abstract','default','static','sealed','non-sealed','final','transient','volatile','synchronized','native','strictfp']
            modifiers=a.get(n,'modifiers')
            header=a.src(modifiers)
            for ann in reversed(a.many(n,'annotations')):
                rel_start=ann['start']-modifiers.get('start',0);rel_end=ann['end']-modifiers.get('start',0)
                if 0<=rel_start<=rel_end<=len(header):header=header[:rel_start]+' '*(rel_end-rel_start)+header[rel_end:]
            header=_mask_literals_comments(header)
            words=re.findall(r'\b(?:'+'|'.join(order)+r')\b',header)
            if words!=sorted(words,key=order.index):emit('modifier_order',n,'修饰符顺序不符合Java语言规范建议。')
        if kind in classes:
            ranked=[]
            for x in a.many(n,'members'):
                if x['kind']=='VARIABLE':rank=0 if 'static' in x.get('mods','') else 2
                elif x['kind']=='BLOCK':rank=1 if x.get('static') else 3
                elif x['kind']=='METHOD':rank=4 if x.get('name')=='<init>' else 5
                else:continue
                ranked.append((rank,x))
            for (before,_),(after,node) in zip(ranked,ranked[1:]):
                if before>after:emit('member_order',node,'成员顺序应为静态字段、静态初始化、实例字段、实例初始化、构造器、方法。')
            symbol=a.project.symbol(a,n)
            for method in a.many(n,'members'):
                if symbol and method['kind']=='METHOD' and (a.project.overrides(symbol,method) or a.project.object_override(symbol,method)) and not any(t.get('name','').split('.')[-1]=='Override' for t in a.many(method,'annotations')):
                    emit('override_annotation',method,'项目内可辨识的覆写/接口实现缺少@Override。')
        if kind=='VARIABLE':
            if a.parent(n).get('kind') not in classes:
                fields=[x for x in a.many(a.clazz(n),'members') if x['kind']=='VARIABLE' and x.get('name')==n.get('name')]
                if fields:emit('shadowing',n,'局部变量或参数遮蔽了同名字段。')
            parent=a.parent(n)
            if parent.get('kind')=='BLOCK' and a.get(n,'initializer').get('kind') in {'INT_LITERAL','STRING_LITERAL','BOOLEAN_LITERAL','NULL_LITERAL'}:
                refs=[q for q in a.under(parent) if q['kind']=='IDENTIFIER' and q.get('name')==n.get('name') and q['start']>n['end']]
                if refs and min(q['line'] for q in refs)-n['line']>3:emit('declaration_proximity',n,'局部变量声明与首次使用相隔超过3行。')
        if kind in {'PLUS','MINUS','MULTIPLY','DIVIDE','REMAINDER','EQUAL_TO','NOT_EQUAL_TO','LESS_THAN','LESS_THAN_EQUAL','GREATER_THAN','GREATER_THAN_EQUAL','CONDITIONAL_AND','CONDITIONAL_OR','AND','OR','XOR','LEFT_SHIFT','RIGHT_SHIFT','UNSIGNED_RIGHT_SHIFT'}:
            left,right=a.get(n,'left'),a.get(n,'right')
            gap=a.text[left.get('end',0):right.get('start',0)]
            if gap and (not gap[0].isspace() or not gap[-1].isspace()):emit('operator_spaces',n,'二元运算符两侧应有空格。')
            related={'PLUS':{'MULTIPLY','DIVIDE','REMAINDER'},'MINUS':{'MULTIPLY','DIVIDE','REMAINDER'},'CONDITIONAL_OR':{'CONDITIONAL_AND'},'OR':{'AND','XOR'},'XOR':{'AND'}}
            if left.get('kind') in related.get(kind,set()) or right.get('kind') in related.get(kind,set()):emit('explicit_precedence',n,'混合不同优先级的运算符应使用括号明确顺序。')
        if kind=='EXPRESSION_STATEMENT':
            vars=[a.src(a.get(q,'variable')) for q in a.under(n) if q['kind']=='ASSIGNMENT']
            if any(count>1 for count in Counter(vars).values()):emit('multiple_assignment',n,'单个表达式对同一个变量赋值超过一次。')
        if kind=='STRING_LITERAL':
            value=str(n.get('value',''))
            if value in {'\n','\r','\r\n'}:emit('hardcoded_newline',n,'避免硬编码换行符，使用System.lineSeparator()。')
            if value in {'/','\\'}:emit('hardcoded_separator',n,'避免硬编码文件路径分隔符，使用Path或File.separator。')
            candidates=re.findall(r'(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?![\w.])',value)
            for ip in candidates:
                try:
                    if ipaddress.ip_address(ip).is_global:emit('public_ip',n,'字符串字面量包含公网IP地址。')
                except ValueError:pass
        if kind=='TYPE_CAST':
            typ=a.src(a.get(n,'type'));expr=a.get(n,'expr')
            if typ not in primitives and a.type(expr,n) in {'Object','java.lang.Object'}:
                source=a.src(expr)
                guarded=any(q['kind']=='IF' and source+' instanceof '+typ in a.src(a.get(q,'condition')) for q in a.ancestors(n))
                if not guarded:emit('downcast_check',n,'Object向下转换前未找到包围条件中的instanceof检查。')
        if kind=='NEW_CLASS' and a.src(a.get(n,'type')).split('.')[-1] in resources:
            ancestors=list(a.ancestors(n));var=next((q for q in ancestors if q['kind']=='VARIABLE'),{})
            in_resources=any(q['kind']=='TRY' and var.get('id') in q.get('resources',[]) for q in ancestors)
            method=a.method(n);name=var.get('name','')
            final_close=any(q['kind']=='TRY' and re.search(r'\b'+re.escape(name)+r'\s*\.\s*close\s*\(',a.src(a.get(q,'finally'))) for q in a.under(method)) if name else False
            if not in_resources and not final_close:emit('resource_close',n,'IO资源未在try-with-resources声明或本方法finally中关闭。')
        if kind=='METHOD_INVOCATION':
            name,recv,args=a.call(n);receiver=a.src(recv);method=a.method(n)
            if name in {'debug','info','warn','error','trace','fatal','log'} and ('log' in receiver.lower() or a.type(recv,n).endswith('Logger')) and any(q.get('kind')=='STRING_LITERAL' and re.search(r'[\u4e00-\u9fff]',str(q.get('value',''))) for q in args):emit('chinese_log',n,'日志消息包含中文；需要核对产品销售区域。')
            if name=='set' and a.type(recv,n).startswith('ThreadLocal'):
                if not any(q['kind']=='TRY' and receiver+'.remove(' in a.src(a.get(q,'finally')).replace(' ','') for q in a.under(method)):emit('threadlocal_cleanup',n,'ThreadLocal.set后未找到本方法finally中的remove清理。')
            if name=='createTempFile' and receiver.split('.')[-1] in {'Files','File'}:
                if not any(q['kind']=='TRY' and re.search(r'\b(?:delete|deleteIfExists)\s*\(',a.src(a.get(q,'finally'))) for q in a.under(method)):emit('temp_cleanup',n,'临时文件创建后未找到finally删除路径。')
            if name=='compile' and receiver.split('.')[-1]=='Pattern' and args and args[0].get('kind')=='STRING_LITERAL':
                pattern=str(args[0].get('value',''))
                if re.search(r'\([^)]*[+*][^)]*\)[+*{]',pattern):emit('regex_redos',n,'正则包含嵌套重复量词，需评估灾难性回溯。')
            if name in {'getPermissions','getPermission'} and receiver=='super':pass
            typ=a.type(recv,n)
            if typ:
                cls=next((q for q in a.kind(*classes) if q.get('name')==typ),{})
                if any(m['kind']=='METHOD' and m.get('name')==name and 'static' in m.get('mods','') for m in a.many(cls,'members')):emit('static_receiver',n,'静态方法应使用类名调用。')
    for line,nodes in statements.items():
        if len(nodes)>1:emit('one_statement',nodes[1],'同一行有多个声明或语句。')
    by_start={}
    for node in a.kind('VARIABLE'):
        by_start.setdefault((node['start'],node['parent']),[]).append(node)
    for group in by_start.values():
        if len(group)>1:emit('one_variable',group[0],'一个声明中包含多个变量，应每行声明一个变量。')
    for node in a.kind('BLOCK'):
        if not node.get('statements'):continue
        source=a.src(node);start=node['start'];end=node['end']
        previous=a.text[a.text.rfind('\n',0,start)+1:start]
        closing=a.text[a.text.rfind('\n',0,end-1)+1:end-1]
        if not previous.strip() or closing.strip():emit('brace_layout',node,'非空块的左大括号应在行尾，右大括号应另起一行。')
    _flow_checks(a, emit)


def _flow_checks(a, emit):
    """Bounded intraprocedural source propagation with sink-scoped sanitizer
    recognition, and explicit partial status.

    This is deliberately not an interprocedural or path-sensitive taint engine.
    The taint set is computed exactly as the legacy flat-walk propagation; a
    separate sink-scoped sanitizer layer only suppresses a finding when the
    tainted argument has passed through a conservative encoding/escaping
    sanitizer that legitimately covers that sink category. Only a binding's
    direct sanitizer-call initializer is recognized (a later non-sanitizer
    assignment clears it), so aliases and reassignments never over-silence.
    Findings identify concrete source/sink review candidates, not proven exploits.
    """
    sources={'getParameter','getParameterValues','getParameterMap','getHeader','getQueryString','getCookies','getInputStream','getReader','getPathInfo','getRequestURI','getRequestURL','getRequestedSessionId'}
    def sanitizer_detectors(name, recv_src):
        recv_short=recv_src.rsplit('.',1)[-1] if recv_src else ''
        if name in {'escapeHtml','escapeHtml4','escapeHtml3','escapeXml','escapeXml10','escapeXml11'} and recv_short=='StringEscapeUtils':
            return {'taint_xss','taint_xml_concat'}
        if name in {'encodeForHTML','encodeForHTMLAttribute'}:return {'taint_xss'}
        if name in {'encodeForXML','encodeForXMLAttribute'}:return {'taint_xss','taint_xml_concat'}
        if name=='encode' and recv_short=='URLEncoder':return {'taint_redirect','taint_header'}
        # NOTE: response.encodeURL / encodeRedirectURL are session-tracking URL
        # rewriters (add ;jsessionid); they do NOT encode CRLF or validate
        # redirect targets, so they are NOT security sanitizers and must not
        # suppress taint_header / taint_redirect (would cause false negatives).
        return set()
    def expr_sanitizers(expr):
        expr=a.unwrap(expr)
        if not expr or expr.get('kind')!='METHOD_INVOCATION':return set()
        name,recv,args=a.call(expr)
        return sanitizer_detectors(name,a.src(recv))
    tainted=set()
    def is_tainted(expr, method):
        for node in [expr,*a.under(expr)]:
            if node.get('kind')=='METHOD_INVOCATION':
                name,recv,args=a.call(node)
                if name in sources or name in {'getenv','getProperty'} and a.src(recv) in {'System','java.lang.System'}:return True
            if node.get('kind')=='IDENTIFIER' and (method.get('id'),node.get('name')) in tainted:return True
        return False
    sanitized_for=set()
    def is_sanitized(expr, method, sink_detector):
        for node in [a.unwrap(expr),*a.under(a.unwrap(expr))]:
            if node.get('kind')=='METHOD_INVOCATION':
                name,recv,args=a.call(node)
                if sink_detector in sanitizer_detectors(name,a.src(recv)):return True
            if node.get('kind')=='IDENTIFIER' and (method.get('id'),node.get('name'),sink_detector) in sanitized_for:return True
        return False
    def has_unsanitized_taint(expr, method, sink_detector):
        """Precise: a tainted leaf counts as unsanitized for this sink unless an
        enclosing sanitizer (call covering the sink, or a sanitized_for binding)
        neutralizes it. Used only when the arg actually contains sanitization,
        so partial-arg mixes like escapeHtml(x)+x are no longer over-suppressed.
        The fallback iterates DIRECT children only (not a.under, which is
        recursive) so a sanitizer call's subtree stays protected by its branch."""
        node=a.unwrap(expr)
        if not node or 'kind' not in node:return False
        k=node['kind']
        if k=='METHOD_INVOCATION':
            name,recv,args=a.call(node)
            if name in sources or name in {'getenv','getProperty'} and a.src(recv) in {'System','java.lang.System'}:return True
            if sink_detector in sanitizer_detectors(name,a.src(recv)):return False
            if has_unsanitized_taint(recv,method,sink_detector):return True
            return any(has_unsanitized_taint(x,method,sink_detector) for x in args)
        if k=='IDENTIFIER':
            nm=node.get('name')
            if (method.get('id'),nm) in tainted:
                return (method.get('id'),nm,sink_detector) not in sanitized_for
            return False
        for child in a.children.get(node.get('id',-1),[]):
            if has_unsanitized_taint(child,method,sink_detector):return True
        return False
    def arg_unsanitized(expr, method, sink_detector):
        if not is_tainted(expr,method):return False
        if not is_sanitized(expr,method,sink_detector):return True
        return has_unsanitized_taint(expr,method,sink_detector)
    for n in a.kind('VARIABLE'):
        if any(x.get('name','').split('.')[-1] in {'RequestParam','RequestHeader','PathVariable','RequestBody','CookieValue'} for x in a.many(n,'annotations')):
            tainted.add((a.method(n).get('id'),n.get('name')))
    for _ in range(5):
        old=len(tainted)
        for n in a.nodes:
            method=a.method(n)
            if n['kind']=='VARIABLE' and is_tainted(a.get(n,'initializer'),method):tainted.add((method.get('id'),n.get('name')))
            if n['kind']=='ASSIGNMENT' and is_tainted(a.get(n,'expr'),method):tainted.add((method.get('id'),a.src(a.get(n,'variable'))))
        if old==len(tainted):break
    # Record direct sanitizer neutralization per binding; a later assignment to
    # the same name overrides, so reassigning to a non-sanitizer clears it.
    sanitized_map={}
    for n in a.nodes:
        if n['kind']=='VARIABLE':
            dets=expr_sanitizers(a.get(n,'initializer'))
            if dets:sanitized_map[(a.method(n).get('id'),n.get('name'))]=dets
        if n['kind']=='ASSIGNMENT':
            dets=expr_sanitizers(a.get(n,'expr'))
            sanitized_map[(a.method(n).get('id'),a.src(a.get(n,'variable')))]=dets
    for (mid,nm),dets in sanitized_map.items():
        for d in dets:sanitized_for.add((mid,nm,d))
    for n in a.nodes:
        kind=n['kind'];method=a.method(n)
        if kind=='METHOD_INVOCATION':
            name,recv,args=a.call(n);receiver=a.src(recv);typ=a.type(recv,n).split('.')[-1]
            mappings=[]
            if name in {'evaluate','compile'} and ('xpath' in receiver.lower() or typ=='XPath'):mappings.append('taint_xpath')
            if name in {'validate','setSchema'}:mappings.append('taint_xml_validation')
            if name=='getInstance' and receiver.split('.')[-1] in {'MessageDigest','Mac','SecretKeyFactory'}:mappings.append('taint_hash')
            if name in {'setHeader','addHeader'}:mappings.append('taint_header')
            if name in {'sendRedirect','getRequestDispatcher','forward'}:mappings.append('taint_redirect')
            if name in {'getValue','setValue','parseExpression'} and 'ognl' in receiver.lower():mappings.append('taint_ognl')
            if name in {'eval','evaluate'} and (typ in {'ScriptEngine','Interpreter','GroovyShell'} or 'engine' in receiver.lower()):mappings.append('taint_code')
            if name in {'search','lookup'} and (typ in {'DirContext','InitialDirContext','LdapContext'} or 'context' in receiver.lower()):mappings.append('taint_ldap')
            if name in {'print','println','write','append'} and (typ in {'PrintWriter','Writer','ServletOutputStream'} or receiver.endswith('.getWriter()')):mappings.append('taint_xss')
            if name in {'debug','info','warn','error','trace','fatal','log'} and ('log' in receiver.lower() or typ=='Logger'):mappings.append('taint_log')
            if name in {'format','printf'}:mappings.append('taint_format')
            if name in {'parse','loadXML'} and any(q.get('kind')=='PLUS' for q in args):mappings.append('taint_xml_concat')
            if name in {'getResource','getResourceAsStream','openConnection'}:mappings.append('taint_resource')
            if name in {'setAttribute','putValue'}:mappings.append('taint_trust')
            if name in {'get','of'} and receiver.split('.')[-1] in {'Paths','Path'}:mappings.append('taint_path')
            for detector in mappings:
                if any(arg_unsanitized(x,method,detector) for x in args):
                    emit(detector,n,'本方法内可追踪的外部输入到达敏感调用；需要验证允许列表、编码或其他防护。')
            if name=='setFeature' and len(args)>=2 and args[0].get('kind')=='STRING_LITERAL':
                feature=args[0].get('value','');enabled=args[1].get('value')
                if feature in {'http://xml.org/sax/features/external-general-entities','http://xml.org/sax/features/external-parameter-entities','http://apache.org/xml/features/nonvalidating/load-external-dtd'} and enabled is True:emit('xml_external',n,'XML解析器显式启用了外部实体或DTD。')
                if feature=='http://apache.org/xml/features/disallow-doctype-decl' and enabled is False:emit('xml_expansion',n,'XML解析器显式允许DOCTYPE，需限制实体扩展。')
                if feature=='http://javax.xml.XMLConstants/feature/secure-processing' and enabled is False:emit('xslt_secure',n,'禁用XML安全处理可能允许不安全XSLT操作。')
            if name=='setAttribute' and len(args)>=2 and a.src(args[0]).endswith(('ACCESS_EXTERNAL_DTD','ACCESS_EXTERNAL_STYLESHEET')) and args[1].get('value')=='all':emit('xslt_secure',n,'XSLT处理器允许访问全部外部协议。')
            if name=='initialize' and args and isinstance(args[0].get('value'),int):
                decl=a.declaration(recv,n);init=a.get(decl,'initializer');algo=''
                if init.get('kind')=='METHOD_INVOCATION':
                    iname,irecv,iargs=a.call(init)
                    if iname=='getInstance' and iargs:algo=str(iargs[0].get('value','')).upper()
                if algo in {'RSA','DSA','DH'} and args[0]['value']<2048 or algo=='AES' and args[0]['value']<128:emit('key_length',n,'显式密钥长度低于本地最低策略（RSA/DSA/DH 2048，AES 128）。')
            if name=='start' and a.platform_type(a.type(recv,n),'java.lang.Thread'):
                if not any(x['kind']=='METHOD_INVOCATION' and a.call(x)[0]=='setUncaughtExceptionHandler' and a.src(a.call(x)[1])==receiver and x['start']<n['start'] for x in a.under(method)):
                    emit('thread_handler',n,'线程启动前未找到本方法显式注册未捕获异常处理器。')
            if name=='waitFor' and a.type(recv,n).split('.')[-1]=='Process':
                methodtext=a.src(method)
                if not any(word in methodtext for word in ('getInputStream','getErrorStream','inheritIO','redirectOutput','redirectError')):emit('process_streams',n,'等待子进程结束前未找到本方法读取或重定向输出流的路径。')
        if kind=='NEW_CLASS':
            typ=a.src(a.get(n,'type')).split('.')[-1];args=a.many(n,'args')
            if typ in {'File','FileInputStream','FileOutputStream','RandomAccessFile'} and any(arg_unsanitized(x,method,'taint_path') for x in args):emit('taint_path',n,'外部输入用于构造文件路径，需要规范化并验证允许范围。')
            if typ=='PBEKeySpec' and len(args)>=3:
                salt=args[1];decl=a.declaration(salt,n);init=a.get(decl,'initializer')
                if salt.get('kind') in {'STRING_LITERAL','NEW_ARRAY'} or init.get('kind')=='NEW_ARRAY' or salt.get('kind')=='METHOD_INVOCATION' and a.call(salt)[1].get('kind')=='STRING_LITERAL':emit('fixed_salt',n,'密码派生使用了固定字节数组或字符串盐值。')
                if isinstance(args[2].get('value'),int) and args[2]['value']<10000:emit('hash_iterations',n,'密码派生迭代数低于本地最低策略10000；实际应按算法和当前安全基线配置。')
        if kind=='METHOD':
            if n.get('name') in {'getPermission','getPermissions'} and a.src(a.get(a.clazz(n),'extends')).split('.')[-1].endswith('ClassLoader'):
                if not any(q['kind']=='METHOD_INVOCATION' and a.call(q)[0]==n['name'] and a.src(a.call(q)[1])=='super' for q in a.under(a.get(n,'body'))):emit('classloader_permissions',n,'ClassLoader权限方法未调用父类实现。')
            if n.get('name','').startswith(('checkPermission','checkAccess','verifyPermission','validatePermission')) and not any(x in n.get('mods','') for x in ('private','final')):emit('security_method',n,'安全检查方法可以被覆写，需要private或final保护。')
            typ=a.src(a.get(n,'returnType'))
            if typ in {'int','long'} and any(q['kind']=='NEW_CLASS' and a.src(a.get(q,'type')).split('.')[-1] in {'Integer','Long'} for q in a.under(n)):emit('boxed_primitive',n,'基本类型返回值中不必要地创建包装对象。')
        if kind in {'PLUS','MINUS','MULTIPLY'}:
            left,right=a.get(n,'left'),a.get(n,'right')
            if left.get('kind') in {'INT_LITERAL','LONG_LITERAL'} and right.get('kind') in {'INT_LITERAL','LONG_LITERAL'}:
                x,y=left.get('value'),right.get('value');value={'PLUS':lambda:x+y,'MINUS':lambda:x-y,'MULTIPLY':lambda:x*y}[kind]()
                bits=64 if 'LONG_LITERAL' in {left['kind'],right['kind']} else 32
                if not -(2**(bits-1))<=value<2**(bits-1):emit('integer_overflow',n,f'常量运算超过有符号{bits}位整数范围。')
        if kind=='VARIABLE' and a.src(a.get(n,'type')) in {'float','double'} and re.search(r'(?i)price|amount|money|balance|currency|payment',n.get('name','')):emit('decimal_precision',n,'疑似金额变量使用二进制浮点数，需确认是否应使用BigDecimal。')
        if kind=='MEMBER_SELECT':
            recv=a.get(n,'expr');decl=a.declaration(recv,n)
            if a.get(decl,'initializer').get('kind')=='NULL_LITERAL' and a.method(decl).get('id')==method.get('id'):
                between=[q for q in a.nodes if decl['end']<=q['start']<n['start'] and q['kind']=='ASSIGNMENT' and a.src(a.get(q,'variable'))==a.src(recv)]
                guard=any(q['kind']=='IF' and re.search(r'\b'+re.escape(a.src(recv))+r'\s*!=\s*null',a.src(a.get(q,'condition'))) for q in a.ancestors(n))
                if not between and not guard:emit('null_dereference',n,'本方法显式初始化为null的变量在未重新赋值的情况下被解引用。')
    for sw in a.kind('SWITCH'):
        cases=a.many(sw,'cases')
        for case,next_case in zip(cases,cases[1:]):
            statements=a.many(case,'statements')
            if case.get('caseKind')=='RULE' or not statements:continue
            comments=[text for start,text in _comments(a.text) if case['start']<=start<next_case['start']]
            if a.control_flow.can_complete(statements) and not any(re.search(r'fall[ -]?through|falls? through',text,re.I) for text in comments):emit('fallthrough',case,'控制流分析发现case可正常结束并进入下一分支，且未找到fall-through注释。')
    for loop in a.kind('FOR_LOOP'):
        for assign in a.under(a.get(loop,'body')):
            if assign['kind']=='ASSIGNMENT' and a.get(assign,'variable').get('kind')=='ARRAY_ACCESS' and a.get(assign,'expr').get('kind')=='ARRAY_ACCESS':emit('array_copy',assign,'逐元素数组复制循环可使用System.arraycopy或Arrays.copyOf。')
    constructors=[n for n in a.kind('METHOD') if n.get('name')=='<init>']
    for first in constructors:
        for second in constructors:
            if first['id']>=second['id'] or a.clazz(first).get('id')!=a.clazz(second).get('id'):continue
            fbody,sbody=a.get(first,'body'),a.get(second,'body')
            fsrc,ssrc=re.sub(r'\s+','',a.src(fbody)),re.sub(r'\s+','',a.src(sbody))
            if fsrc not in {'','{}'} and fsrc==ssrc:emit('constructor_reuse',second,'多个构造方法重复相同实现，可通过构造器委托复用。')
    _remaining_checks(a, emit)


def _remaining_checks(a, emit):
    classes={'CLASS','INTERFACE','ENUM','RECORD','ANNOTATION_TYPE'}
    imports=a.kind('IMPORT')
    def group(name):
        if name.startswith('android.'):return 0
        if name.startswith(('com.huawei.','com.hihonor.')):return 1
        if name.startswith('com.'):return 2
        if name.startswith(('net.','org.')):return 4
        if name.startswith(('java.','javax.')):return 5
        return 3
    for previous,current in zip(imports,imports[1:]):
        pg,cg=group(previous['name']),group(current['name'])
        if pg>cg or pg!=cg and current['line']-previous['line']<2:emit('import_order',current,'import分组顺序或分组间空行不符合指定规范。')
    package=a.kind('PACKAGE')
    top=[n for n in a.nodes if n['kind'] in classes and a.parent(n).get('kind')=='COMPILATION_UNIT']
    sections=[]
    if package:sections.append(package[-1])
    if imports:
        if sections and imports[0]['line']-a.text.count('\n',0,sections[-1]['end'])<3:emit('source_sections',imports[0],'package和import区之间应有空行。')
        sections.append(imports[-1])
    if top and sections and top[0]['line']-a.text.count('\n',0,sections[-1]['end'])<3:emit('source_sections',top[0],'import/package与顶层类型之间应有空行。')
    for n in a.nodes:
        kind=n['kind'];method=a.method(n)
        if kind in {'ASSIGNMENT','VARIABLE'}:
            expr=a.get(n,'expr') if kind=='ASSIGNMENT' else a.get(n,'initializer')
            if expr:
                prefix=a.text[n['start']:expr['start']]
                if re.search(r'\S[ \t]{2,}=',prefix):emit('vertical_alignment',n,'赋值前包含用于垂直对齐的多余空格。')
        if kind in {'PLUS','MINUS','MULTIPLY','DIVIDE','CONDITIONAL_AND','CONDITIONAL_OR','EQUAL_TO','NOT_EQUAL_TO'}:
            left,right=a.get(n,'left'),a.get(n,'right');gap=a.text[left.get('end',0):right.get('start',0)]
            if '\n' in gap and gap.split('\n',1)[0].strip():emit('operator_wrap',n,'换行应从操作符之前开始。')
        if kind=='VARIABLE':
            typ=a.src(a.get(n,'type'))
            if typ.endswith('[]') and typ[:-2].split('.')[-1] not in {'byte','short','int','long','float','double','char','boolean'} and 'String[] args' not in a.src(n):emit('prefer_collections',n,'引用类型数组可考虑使用泛型集合，需要结合性能和API约束判断。')
            init=a.get(n,'initializer')
            if typ=='long' and init.get('kind')=='DIVIDE' and a.type(a.get(init,'left'),n)=='int' and a.type(a.get(init,'right'),n)=='int':emit('explicit_cast',n,'int除法后赋值给long，类型提升发生在运算之后；请显式选择运算类型。')
            if typ in {'float','double'} and init.get('kind')=='DIVIDE' and a.type(a.get(init,'left'),n)=='int' and a.type(a.get(init,'right'),n)=='int':emit('explicit_cast',n,'整数除法之后隐式转换为浮点，可能丢失小数部分。')
        if kind in classes:
            name=n.get('name');members=a.many(n,'members');methods=[q for q in members if q['kind']=='METHOD']
            singleton=any(q['kind']=='VARIABLE' and a.src(a.get(q,'type'))==name and 'static' in q.get('mods','') and q.get('name','').lower() in {'instance','singleton'} for q in members)
            if singleton:
                for m in methods:
                    if m.get('name')=='<init>' and 'private' not in m.get('mods',''):emit('singleton_constructor',m,'单例实例字段所在类暴露了非private构造方法。')
            for m in methods:
                if m.get('name')=='readObject' and any(x['kind']=='METHOD_INVOCATION' and a.call(x)[0]=='defaultReadObject' for x in a.under(m)):
                    constructors=[q for q in methods if q.get('name')=='<init>']
                    checks={a.call(x)[0] for constructor in constructors for x in a.under(constructor) if x['kind']=='METHOD_INVOCATION' and a.call(x)[0].startswith(('check','validate','verify'))}
                    readcalls={a.call(x)[0] for x in a.under(m) if x['kind']=='METHOD_INVOCATION'}
                    if checks-readcalls:emit('deserialize_validation',m,'反序列化方法未重复构造方法中可辨识的安全校验。')
            symbol=a.project.symbol(a,n)
            for m in methods:
                if symbol and any('synchronized' in parent.get('mods','') for _,parent in a.project.overrides(symbol,m)) and 'synchronized' not in m.get('mods','') and not any(x['kind']=='SYNCHRONIZED' for x in a.under(m)):emit('unsafe_override',m,'项目内父类同步方法被不含同步结构的方法覆写。')
        if kind=='SYNCHRONIZED':
            conditions=[q for q in a.ancestors(n) if q['kind']=='IF']
            outerchecks=[a.src(a.get(q,'condition')) for q in conditions]
            body=a.get(n,'body')
            for inner in a.under(body):
                if inner['kind']=='IF' and a.src(a.get(inner,'condition')) in outerchecks:
                    expr=a.unwrap(a.get(inner,'condition'))
                    if expr.get('kind')=='EQUAL_TO':
                        left,right=a.get(expr,'left'),a.get(expr,'right');ref=left if right.get('kind')=='NULL_LITERAL' else right if left.get('kind')=='NULL_LITERAL' else {}
                        var=a.declaration(ref,n)
                        if var and 'volatile' not in var.get('mods',''):emit('double_checked_lock',n,'双重检查锁发布的字段未声明volatile。')
        if kind=='METHOD_INVOCATION':
            name,recv,args=a.call(n);receiver=a.src(recv)
            if receiver in {'System','java.lang.System'} and name=='setSecurityManager' and args and args[0].get('kind')=='NULL_LITERAL':emit('security_manager',n,'代码显式禁用了SecurityManager；此旧版规范在现代JDK中应按平台安全模型迁移。')
            if name=='log' and ('log' in receiver.lower() or a.type(recv,n).endswith('Logger')) and len(args)==1 and a.type(args[0],n)=='String':emit('log_level',n,'日志调用未提供明确级别。')
            if name=='setConfig' and len(args)>=2 and args[0].get('value') in {'kex','server_host_key','mac.c2s','mac.s2c'} and args[1].get('kind')=='STRING_LITERAL':
                value=str(args[1].get('value','')).lower()
                if any(x in value for x in ('diffie-hellman-group1','ssh-dss','hmac-md5','hmac-sha1')):emit('ssh_algorithms',n,'SSH显式配置中含有弱密钥交换、身份认证或消息认证算法。')
            if name in {'getActivity','getService','getBroadcast','getForegroundService'} and receiver.split('.')[-1]=='PendingIntent' and len(args)>2:
                intent=args[2];var=a.declaration(intent,n);init=a.get(var,'initializer') if var else intent
                if init.get('kind')=='NEW_CLASS' and a.src(a.get(init,'type')).split('.')[-1]=='Intent':
                    iargs=a.many(init,'args');explicit=any(a.src(x).endswith('.class') for x in iargs)
                    explicit |= any(x['kind']=='METHOD_INVOCATION' and a.src(a.call(x)[1])==a.src(intent) and a.call(x)[0] in {'setClass','setClassName','setComponent'} and x['start']<n['start'] for x in a.under(method))
                    if not explicit:emit('pending_intent',n,'PendingIntent使用了本地可辨识的隐式Intent。')
            if name=='computeIfAbsent':
                variable=a.parent(n)
                is_lock=variable.get('kind')=='VARIABLE' and a.src(a.get(variable,'type')).split('.')[-1] in {'Lock','ReentrantLock','ReadWriteLock','ReentrantReadWriteLock'}
                if is_lock:
                    for t in a.under(method):
                        if t['kind']=='TRY':
                            for call in a.under(a.get(t,'finally')):
                                if call['kind']=='METHOD_INVOCATION' and a.call(call)[0]=='remove' and a.src(a.call(call)[1])==receiver:emit('lock_eviction',call,'并发锁映射在finally中直接移除；等待线程可能继续持有旧锁，后续调用却获得新锁。')
        if kind=='IF' and '.isDirectory()' in a.src(a.get(n,'condition')):
            branch=a.get(n,'then')
            if not any(q['kind'] in {'THROW','RETURN'} for q in [branch,*a.under(branch)]) and any(q['kind']=='METHOD_INVOCATION' and a.call(q)[0]=='getNextEntry' for q in a.under(method)):
                has_read=any(q['kind']=='METHOD_INVOCATION' and a.call(q)[0] in {'read','transferTo'} for q in a.under(branch))
                if not has_read:emit('zip_directory_bytes',n,'ZIP目录分支未显式读取负载；closeEntry/getNextEntry可能隐式排空数据，绕过只统计文件负载的限额。')
    orders=[]
    for method in a.kind('METHOD'):
        locks=[]
        for n in a.under(method):
            if n['kind']=='METHOD_INVOCATION':
                name,recv,args=a.call(n)
                if name=='lock' and not args:
                    receiver=a.src(recv);decl=a.declaration(recv,n)
                    if a.parent(decl).get('kind') in classes:locks.append((receiver,n))
        orders.append((method,locks))
    for i,(method,locks) in enumerate(orders):
        for other,others in orders[i+1:]:
            if a.clazz(method).get('id')!=a.clazz(other).get('id'):continue
            positions={name:index for index,(name,_) in enumerate(others)}
            for (left,_),(right,node) in zip(locks,locks[1:]):
                if left in positions and right in positions and positions[left]>positions[right]:emit('lock_order',node,'同一类的另一个方法以相反顺序请求这些字段锁，存在锁顺序不一致风险。')
    for start,text in _comments(a.text):
        if not text.startswith('/*') or '\n' not in text:continue
        line=a.text.count('\n',0,start);prefix=a.lines[line][:start-a.text.rfind('\n',0,start)-1]
        if prefix.strip():continue
        after=next((s for s in a.lines[line+text.count('\n')+1:] if s.strip()),'')
        if after and not after.lstrip().startswith('}') and len(prefix)!=len(after)-len(after.lstrip()):emit('comment_indent',{'line':line+1,'column':len(prefix)+1},'块注释与后续代码的缩进级别不同。')



def _comments(text):
    # Lexer preserves comment offsets and skips Java strings/text blocks/chars.
    pattern = re.compile(r'"""[\s\S]*?"""|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|//[^\n]*|/\*[\s\S]*?\*/')
    return [(m.start(),m.group()) for m in pattern.finditer(text) if m.group().startswith(('//','/*'))]


def _mask_literals_comments(text):
    pattern=re.compile(r'"""[\s\S]*?"""|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|//[^\n]*|/\*[\s\S]*?\*/')
    return pattern.sub(lambda match:re.sub(r'[^\n]',' ',match.group()),text)


def scan(files, entries):
    selected={e['id']:e for e in entries if e.get('rule',{}).get('language')=='JAVA'}
    result={'findings':[],'errors':[]}
    if not files or not selected:return result
    executable=_java()
    if not executable:
        result['errors']=[{'path':p,'reason':'Java catalog analysis requires a JDK 21+ (set HUAWEI_JAVA or JAVA_HOME).'} for p,_ in files]
        return result
    result['engines']={'java_version':_JAVA_VERSIONS.get(executable,'unknown'),'parser':'javac-parse-only','java_source_release':'21','annotation_processing':'disabled'}
    manifest=json.loads((ROOT/'rulesets/implementations/java.json').read_text())
    detectors={}
    limits={'parameters':5,'method_length':50,'nesting':4}
    option_names={'maxParameterNum':'parameters','maxMethodLength':'method_length','maxMethodNestedDepth':'nesting'}
    for entry in selected.values():
        for option in entry['rule'].get('options',[]):
            key=option_names.get(option.get('optionKey'))
            if key:
                try:
                    value=int(option.get('optionValue'))
                    if value<0:raise ValueError('negative threshold')
                    limits[key]=value
                except (TypeError,ValueError):
                    result['errors'].append({'path':'','reason':f"Invalid Java rule option {option.get('optionKey')}: {option.get('optionValue')}"})
    if result['errors']:return result
    for entry in manifest:
        if entry['rule_id'] in selected and entry['status'] in {'implemented','partial'}:
            detectors.setdefault(entry['detector'].removeprefix('javac-ast:'),[]).append(entry)
    with tempfile.TemporaryDirectory(prefix='huawei-java-ast-') as temp:
        mappings={};paths=[]
        for index,(path,text) in enumerate(files):
            target=Path(temp)/str(index)/'Source.java';target.parent.mkdir()
            try:
                target.write_text(text,encoding='utf-8')
            except UnicodeEncodeError as error:
                result['errors'].append({'path':path,'reason':'Source cannot be encoded as UTF-8: '+str(error)})
                continue
            mappings[str(target.resolve())]=(path,text);paths.append(str(target.resolve()))
        if not paths:return result
        listing=Path(temp)/'sources.txt';listing.write_text('\n'.join(paths),encoding='utf-8')
        try:
            process=subprocess.run([executable,str(DATA/'AstDump.java'),str(listing)],capture_output=True,text=True,timeout=max(60,len(files)*2))
            if process.returncode:raise RuntimeError(process.stderr.strip() or f'javac bridge exit {process.returncode}')
            payload=json.loads(process.stdout)
        except (OSError,ValueError,RuntimeError,subprocess.SubprocessError) as error:
            result['errors']=[{'path':p,'reason':str(error)} for p,_ in files]
            return result
        failed=set()
        for error in payload['errors']:
            failed.add(error['path']);path=mappings.get(error['path'],(error['path'],''))[0]
            result['errors'].append(dict(error,path=path))
        seen=set();asts=[]
        for record in payload['files']:
            if record['path'] in failed:continue
            path,text=mappings[record['path']]
            record['source_path']=path
            asts.append(Ast(record,text))
        project=ProjectSymbols(asts)
        result['type_context']=project.context()
        for ast in asts:
            path=ast.record['source_path']
            def emit(detector,node,message):
                for implementation in detectors.get(detector,[]):
                    rule=selected[implementation['rule_id']]['rule'];line=max(1,node.get('line',1));column=max(1,node.get('column',1));key=(path,rule['id'],line,column)
                    if key in seen:continue
                    seen.add(key)
                    partial=implementation['status']=='partial'
                    result['findings'].append({'id':rule['id'],'path':path,'line':line,'column':column,'language':'java','severity':'warning','severity_policy':'local-catalog-review-warning','raw_severity':rule.get('severity'),'confidence':'medium' if partial else 'high','title':rule.get('nameCn',rule.get('name','')),'message':message,'evidence':ast.lines[line-1].strip() if line<=len(ast.lines) else '', 'source':{'id':'codearts-user-export','status':'user-exported'},'coverage_status':implementation['status'],'detector':'javac-ast:'+detector,'fix':{'autofixable':False}})
            try:
                _checks(ast,emit,limits)
            except Exception as error:
                result['errors'].append({'path':path,'reason':f'Java rule evaluation failed: {type(error).__name__}: {error}'})
    return result
