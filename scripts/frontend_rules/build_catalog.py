"""Generate auditable catalog mappings and independent source examples.

No rule descriptions are executed. Every mapping below is an explicit decision.
"""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
CAT=json.loads((ROOT/'rulesets/catalog.json').read_text())['rules']
rows=[]; cases=[]; definitions={}

def add(lang, key, detector, bad, good, status='implemented', reason=None, config=None):
    candidates=[r['rule'] for r in CAT if r['rule']['language']==lang.upper() and (r['rule']['name'].startswith(key+' ') if key.startswith('G.') else r['rule']['name']==key)]
    if len(candidates)!=1: raise ValueError((key,len(candidates)))
    r=candidates[0]; rid=r['id']
    reason=reason or 'Executable syntax/type rule with positive and negative fixtures. Mapping is to the exported requirement, not proprietary CodeArts engine equivalence.'
    defs={'detector':detector,'rules':config or {},'status':status,'reason':reason}
    definitions[rid]=defs
    test_names=[]
    if bad is not None:
        test_names=[key+' positive',key+' negative']
        cases.append({'rule_id':rid,'language':lang,'name':key,'bad':bad,'good':good})
    rows.append({'rule_id':rid,'language':lang,'title':r.get('nameCn',r['name']),'status':status,'detector':detector,'reason':reason,'test_cases':test_names})

def e(key,rules,bad,good,lang='javascript',**kw):
    if isinstance(rules,str): rules={rules:'error'}
    add(lang,key,'eslint:'+','.join(rules),bad,good,config=rules,**kw)
def a(key,det,bad,good,lang='javascript',**kw): add(lang,key,'typescript-ast:'+det,bad,good,**kw)

# JavaScript: exact AST rules from ESLint, with explicit options from the export.
e('G.EXP.02','eqeqeq','if (a == b) run();','if (a === b) run();')
e('G.EXP.01','yoda','if (5 === value) run();','if (value === 5) run();')
a('G.ERR.03','finally-completion','function f() { try { return 1; } finally { return 2; } }','function f() { try { return 1; } finally { cleanup(); } }',reason='Structural completion analysis reports reachable return/throw/break/continue paths that escape finally, while excluding nested functions and locally consumed loop/switch jumps. It does not execute code or infer dynamic control flow.')
e('G.ERR.02','prefer-promise-reject-errors','Promise.reject("failed");','Promise.reject(new Error("failed"));')
e('G.ERR.01','no-throw-literal','throw "failed";','throw new Error("failed");',status='implemented',reason='Executes ESLint no-throw-literal. Local interpretation rejects thrown literals and requires exception objects; recoverability strategy is project policy outside this syntax check.')
e('G.MET.12','prefer-arrow-callback','const task = [1].map(function (x) { return x + 1; });','const task = [1].map(x => x + 1);',status='implemented',reason='Executes ESLint prefer-arrow-callback. Local interpretation prefers arrow callbacks for anonymous function expressions; explicit saved-this style is outside the syntax policy.')
a('G.CTL.05','logical-control','enabled && run();','if (enabled) run();')
e('G.CTL.06',{'no-cond-assign':['error','always']},'if (x = value) run();','if (x === value) run();')
e('G.MET.10','prefer-rest-params','function f() { return arguments[0]; }','function f(...args) { return args[0]; }')
e('G.MET.09','no-param-reassign','function f(x) { x = 1; return x; }','function f(x) { return x + 1; }')
e('G.TYP.06','no-multi-str',"const value = 'first\\\nsecond';","const value = `first\nsecond`;")
e('G.MET.08','no-new-func','const f = new Function("return 1");','const f = () => 1;')
e('G.TYP.05','prefer-template','const message = "Hello " + name;','const message = `Hello ${name}`;')
e('G.CTL.03','no-case-declarations','switch (x) { case 1: let y=2; break; }','switch (x) { case 1: { let y=2; break; } }')
e('G.MET.07','consistent-return','function f(x) { if (x) return 1; return; }','function f(x) { if (x) return 1; return 2; }')
e('G.TYP.04',{'quotes':['error','single',{'avoidEscape':True,'allowTemplateLiterals':True}]},'const word = "hello";',"const word = 'hello';")
e('G.CTL.02','no-fallthrough','switch (x) { case 1: run(); case 2: stop(); break; }','switch (x) { case 1: run(); break; case 2: stop(); break; }',status='implemented',reason='Executes ESLint no-fallthrough. Local interpretation requires every nonempty case to end with break or another completion statement; return/throw/continue are accepted as valid terminators.')
e('G.CTL.01','default-case','switch (x) { case 1: run(); break; }','switch (x) { case 1: run(); break; default: stop(); }')
e('G.MET.06','default-param-last','function f(x = 1, y) { return x+y; }','function f(y, x = 1) { return x+y; }')
e('G.DCL.07','no-shadow','let value=1; function f() { let value=2; return value; }','let value=1; function f() { let other=2; return other; }')
e('G.MET.05',{'max-params':['error',5]},'function f(a,b,c,d,e,f) {}','function f(a,b,c,d,e) {}')
e('G.TYP.02','use-isnan','if (value === NaN) run();','if (Number.isNaN(value)) run();')
e('G.DCL.06',{'no-array-constructor':'error','no-object-constructor':'error'},'const list = new Array(1,2);','const list = [1,2];')
e('G.MET.03',{'max-depth':['error',4]},'function f() { if(a) { if(b) { if(c) { if(d) { if(e) { run(); } } } } } }','function f() { if(a) { if(b) { if(c) { if(d) { run(); } } } } }')
e('G.MET.04',{'max-nested-callbacks':['error',4]},'f(() => { f(() => { f(() => { f(() => { f(() => { run(); }); }); }); }); });','f(() => { f(() => { f(() => { f(() => { run(); }); }); }); });')
e('G.TYP.01','no-floating-decimal','const value = .5;','const value = 0.5;')
e('G.CMT.03',{'no-warning-comments':['error',{'terms':['todo','fixme'],'location':'anywhere'}]},'// TODO: remove workaround\nrun();','// Completed workaround removal\nrun();')
e('G.DCL.05','no-undef-init','let value = undefined;','let value;')
e('G.MET.02',{'complexity':['error',20]},'function f(x) { '+''.join('if(x==='+str(i)+') return '+str(i)+';' for i in range(21))+' return -1; }','function f(x) { if (x) return 1; return 2; }')
e('G.SCO.01','no-implicit-globals','var shared = 1; function run() {}','export const shared = 1;',status='implemented',reason='Executes ESLint no-implicit-globals. Local interpretation reports declarations in script global scope; ES modules and bundler wrappers are not treated as globals without project context.')
e('G.CMT.02',{'spaced-comment':['error','always']},'//comment\nrun();','// comment\nrun();')
e('G.DCL.04','no-multi-assign','a = b = 1;','a = 1; b = 1;')
e('G.MET.01',{'max-lines-per-function':['error',{'max':50,'skipBlankLines':True,'skipComments':True}]},'function f() {\n'+'run();\n'*51+'}', 'function f() { run(); }',status='implemented',reason='Executes ESLint max-lines-per-function with 50 effective lines including the signature and closing line, excluding blank and comment-only lines. This is the user-confirmed local policy.')
e('G.PRJ.03',{'max-lines':['error',2000]},'// line\n'*2001,'// line\n'*2000)
e('G.DCL.03',{'one-var':['error','never']},'let a=1, b=2;','let a=1; let b=2;')
e('G.FMT.12',{'semi':['error','always']},'const value = 1\n','const value = 1;\n')
e('G.AOD.05','no-debugger','debugger;','run();')
e('G.DCL.01','no-var','var value = 1;','let value = 1;')
e('G.FMT.11',{'comma-dangle':['error','always-multiline']},'const list = [\n  1\n];','const list = [\n  1,\n];')
e('G.FMT.10',{'brace-style':['error','1tbs',{'allowSingleLine':True}]},'if (ready)\n{\nrun();\n}','if (ready) {\nrun();\n}')
e('G.AOD.04','no-alert','alert("hi");','showMessage("hi");')
e('G.AOD.03','no-console','console.log("hi");','logger.info("hi");')
e('G.TYP.14','no-implicit-coercion','const value = +input;','const value = Number(input);')
e('G.FMT.09',{'curly':['error','all']},'if (ready) run();','if (ready) { run(); }')
e('G.AOD.02','no-implied-eval','setTimeout("run()", 10);','setTimeout(() => run(), 10);')
e('G.FMT.08',{'keyword-spacing':'error','space-infix-ops':'error'},'if(ready) { let value=1; }','if (ready) { let value = 1; }',status='implemented',reason='Executes ESLint keyword-spacing and space-infix-ops. Local interpretation enforces spaces around keywords and infix operators.')
e('G.OBJ.07','no-extend-native','Array.prototype.extra = function () {};','const extra = function () {};')
e('G.AOD.01','no-eval','eval(code);','parse(code);')
e('G.TYP.10',{'prefer-destructuring':['error',{'array':True,'object':False}]},'const first = values[0];','const [first] = values;')
e('G.FMT.07',{'no-multiple-empty-lines':['error',{'max':2,'maxEOF':1}]},'run();\n\n\n\nstop();','run();\n\nstop();',status='implemented',reason='Executes ESLint no-multiple-empty-lines with at most two consecutive blank lines and one at EOF. This is an explicit local policy.')
a('G.FMT.06','else-catch-line','if (ready) {\nrun();\n}\nelse {\nstop();\n}','if (ready) {\nrun();\n} else {\nstop();\n}')
e('G.OBJ.06','guard-for-in','for (const key in value) { run(value[key]); }','for (const key in value) { if (Object.hasOwn(value,key)) { run(value[key]); } }')
e('G.FMT.05',{'newline-per-chained-call':['error',{'ignoreChainWithDepth':4}]},'foo().a().b().c().d().e();','foo().a().b().c();')
e('G.OBJ.05','no-prototype-builtins','value.hasOwnProperty("x");','Object.prototype.hasOwnProperty.call(value,"x");')
a('G.FMT.04','object-properties-lines','const obj = {a:1,b:2,c:3,d:4,e:5};','const obj = {\na:1,\nb:2,\nc:3,\nd:4,\ne:5\n};')
e('G.OBJ.04','dot-notation','const value = obj["name"];','const value = obj.name;')
e('G.FMT.03',{'operator-linebreak':['error','after']},'const value = left\n + right;','const value = left +\n right;')
e('G.OBJ.03',{'object-shorthand':['error','always']},'const obj = {name: name};','const obj = {name};')
e('G.FMT.02',{'max-len':['error',{'code':120,'ignoreComments':False}]},'const value = "'+'a'*125+'";','const value = "short";',status='implemented',reason='Executes ESLint max-len with a 120-character limit; source characters are counted and comments are not ignored. This is the user-confirmed local policy.')
e('G.OBJ.02',{'quote-props':['error','as-needed']},'const obj = {"name":1};','const obj = {name:1};')
a('G.FMT.01','space-indent','function f() {\n\treturn 1;\n}','function f() {\n  return 1;\n}')
e('G.OBJ.01','new-parens','const value = new Thing;','const value = new Thing();')
e('G.EXP.06','prefer-named-capture-group','const value = /(ab)/;','const value = /(?<word>ab)/;')
e('G.EXP.05','no-regex-spaces','const value = /a   b/;','const value = /a {3}b/;')
e('G.EXP.04','no-mixed-operators','const value = a + b * c;','const value = a + (b * c);')
e('G.NAM.05','no-shadow-restricted-names','function f(undefined) { return undefined; }','function f(value) { return value; }',status='implemented',reason='Executes ESLint no-shadow-restricted-names. Local interpretation reports shadowing of restricted identifiers such as undefined, NaN, and arguments.')
e('G.EXP.03','no-nested-ternary','const value = a ? b ? c : d : e;','const value = a ? c : d;')
# Specific syntax checks implemented with a typed TypeScript AST.
a('G.NAM.03','variable-camel','let Bad_name = 1;','let goodName = 1;')
a('G.NAM.02','function-camel','function Bad_name() {}','function goodName() {}')
a('G.NAM.01','class-pascal','class lower {}','class Upper {}',status='implemented',reason='Executes a local AST check requiring class declarations and named constructor call targets to use UpperCamelCase. This is the complete local naming policy for the mapped surface.')
a('G.NAM.04','negative-boolean','const isNotReady = true;','const isReady = true;',status='implemented',reason='Executes a local AST check reporting boolean-typed bindings with an explicit negative-prefix list. The prefix list is the local naming policy; broader natural-language inference is out of scope.')
a('G.MOD.01','mutable-export','export let value = 1;','export const value = 1;',status='partial',reason='Detects reassignable exports and exported object/array literals. Deep immutability of arbitrary imported/user-defined types requires a project-specific immutability policy.')
a('G.CTL.07','many-conditions','if(a&&b&&c&&d&&e) run();','if(a&&b&&c&&d) run();',status='partial',reason='Export does not define too many. Checks more than four boolean operands in a control condition.')
a('G.CTL.04','final-else','if (a) { run(); } else if (b) { stop(); }','if (a) { run(); } else if (b) { stop(); } else { wait(); }')
a('G.CMT.04','copyright-header','// Utilities\nconst x=1;','// Copyright 2026 Example\nconst x=1;')
a('G.CMT.01','comment-placement','run();\n// explains the call above','// explains the call below\nrun();',status='partial',reason='Detects orphan trailing comments after the last statement. Association of arbitrary comments to intended code cannot be fully inferred.')
a('G.PRJ.01','utf8','const text = "\ufffd";','const text = "hello";',status='implemented',reason='Executes strict UTF-8 decoding during file discovery and flags replacement characters in the AST. This is the complete local encoding check for supplied source text.')
a('G.NAM.07','filename',None,None,status='partial',reason='Checks uppercase source extensions. Consistency of base filename styles is project-dependent; the export provides no selected naming convention.')
a('G.TYP.03','float-equality','const value = 0.1; if(value === 0.2) run();','const value = 0.1; if(Math.abs(value - 0.2) < 1e-8) run();',status='partial',reason='Detects equality against noninteger number literals and locally inferred fractional initializers. JavaScript numbers do not distinguish integers from floats statically; external values need context.')
a('G.MET.11','parameter-destructure','function f(options) { return options.name + options.age; }','function f({name, age}) { return name + age; }',status='partial',reason='Advisory for parameters used through at least two direct property reads. Applicability and API compatibility require review.')
a('G.TYP.08','array-traversal','const values=[1,2]; for(const value of values) { run(value); }','const values=[1,2]; values.forEach(value => run(value));',status='partial',reason='Detects typed array for-of traversal. Break/continue/async semantics may justify a loop; other equivalent traversal styles need review.')
a('G.TYP.07','array-properties','const values=[1,2]; values.name="bad";','const values=[1,2]; values[0]=2;',status='implemented',reason='Executes a local AST check reporting statically named nonnumeric properties on inferred arrays, excluding standard Array members. Computed keys and aliases are outside the local policy.')
a('G.TYP.09','array-mutation-loop','const values=[1,2]; for(const value of values) { values.push(value); }','const values=[1,2]; for(const value of values) { run(value); }',status='partial',reason='Detects direct and resolvable array alias mutations in for-of, forEach and index loops, including mutating supplied-source function calls. Conditional reassignments, closures, external callees and complete path-sensitive effects remain unsupported.')
a('G.TYP.11','array-copy','const values=[1,2]; const copy=values.slice();','const values=[1,2]; const copy=[...values];',status='implemented',reason='Executes a local AST check reporting typed array slice() with no arguments as the copying idiom; spread and concat are accepted alternatives. Hand-written loops are outside this local mapping.')
a('G.TYP.15','number-conversion','const value=parseInt(input,10);','const value=Number(input); if(Number.isNaN(value)) throw new Error();',status='implemented',reason='Executes a local AST check reporting parseInt/parseFloat and Number() results without a local NaN check. Cross-function validation is outside the local policy.')
a('G.CORS.01','postmessage-origin','window.postMessage(data,"*");','window.postMessage(data,"https://example.test");',status='partial',reason='Checks missing or wildcard postMessage target origins. Incoming message origin verification and dynamically computed destinations need whole-program analysis.')
a('G.WST.01','sensitive-storage','localStorage.setItem("password", secret);','sessionStorage.setItem("theme", preference);',status='partial',reason='Checks storage keys/values with credential names. This is a security review candidate, not taint-flow proof.')
a('G.WST.02','persistent-storage','localStorage.setItem("theme", value);','sessionStorage.setItem("theme", value);',status='partial',reason='Reports localStorage writes for retention review. Whether data is temporary is an application requirement not present in source syntax.')
a('G.WSQ.01','sensitive-database','db.executeSql("INSERT INTO users(password) VALUES (?)", [password]);','db.executeSql("SELECT theme FROM settings", []);',status='partial',reason='Detects sensitive-name literals in direct SQL or IndexedDB put/add calls. No complete database taint tracking is claimed.')
a('G.OTH.05','public-address','const endpoint="https://8.8.8.8/api";','const endpoint="http://127.0.0.1/api";',status='implemented',reason='Executes a local AST check detecting public IPv4 and literal HTTP(S) hostnames in string literals, excluding loopback/private ranges and example/test domains. Dynamic assembly and IPv6 are outside the local policy.')
a('G.OTH.04','personal-information','// author: Jane <jane@company.com>\nrun();','// Copyright Example Corp\nrun();',status='partial',reason='Detects author tags and email-like personal contact strings in comments. Determining personal identity in arbitrary prose is not decidable from syntax alone.')
a('G.OTH.03','commented-code','// const unused = 1;\nrun();','// Explain why this path is used\nrun();',status='implemented',reason='Executes a local AST check that parses comment text as JavaScript and flags executable declarations or statements. Documentation examples are outside this syntax-only interpretation.')
a('G.OTH.01','weak-random','const token=Math.random();','const token=crypto.randomUUID();',status='partial',reason='Reports Math.random as a security review candidate; source syntax alone cannot prove use in a security-sensitive scenario.')
a('G.OTH.06','sensitive-output','console.log(password);','console.log(status);',status='partial',reason='Detects credential-named values sent to logging/UI sinks. Full sensitive-data taint tracking and necessity assessment are not implemented.')
a('G.NOD.04','archive-extract','zip.extractAllTo(destination);','validateArchive(zip);',status='partial',reason='Reports archive extraction API calls for path/size/link review. It cannot prove prior validation or protect every extraction library.')

# TypeScript mapped core/typed ESLint rules.
def te(title,rules,bad,good,**kw): e(title,rules,bad,good,lang='typescript',**kw)
def ta(title,det,bad,good,**kw): a(title,det,bad,good,lang='typescript',**kw)
te('Dynamically executing code is security-sensitive',{'no-eval':'error','no-new-func':'error','no-implied-eval':'error'},'eval(code);','parse(code);')
te("Redundant casts and non-null assertions should be avoided",{'@typescript-eslint/no-unnecessary-type-assertion':'error','@typescript-eslint/no-extra-non-null-assertion':'error'},'const value = 1; const same = value!;','declare const value: number | undefined; const same = value!;')
te('Unused assignments should be removed','no-useless-assignment','function f(){ let value=1; value=2; return value; }','function f(){ let value=1; return value; }')
te('Related "if/else if" statements should not have the same condition',{'no-dupe-else-if':'error','no-duplicate-case':'error'},'if (a) run(); else if(a) stop();','if (a) run(); else if(b) stop();')
te('eslint_repo:@typescript-eslint/array-type',{'@typescript-eslint/array-type':['error',{'default':'array'}]},'let value: Array<string>;','let value: string[];')
te('eslint_repo:@typescript-eslint/no-unused-vars',{'@typescript-eslint/no-unused-vars':['error',{'vars':'all','args':'after-used','ignoreRestSiblings':True}]},'const unused=1;','export const used=1;')
te('"super()" should be invoked appropriately','constructor-super','class Child extends Parent { constructor() {} }','class Child extends Parent { constructor() { super(); } }')
te('"catch" clauses should do more than rethrow','no-useless-catch','try { run(); } catch (error) { throw error; }','try { run(); } catch (error) { log(error); throw error; }')
te('Sparse arrays should not be declared','no-sparse-arrays','const values=[1,,3];','const values=[1,2,3];')
ta('Jump statements should not occur in "finally" blocks','finally-completion','function f(){ try { return 1; } finally { return 2; } }','function f(){ try { return 1; } finally { cleanup(); } }',reason='Structural completion analysis reports reachable return/throw/break/continue paths that escape finally, while excluding nested functions and locally consumed loop/switch jumps. It does not execute code or infer dynamic control flow.')
te('Comma operator should not be used',{'no-sequences':['error',{'allowInParentheses':False}]},'const value=(a(),b());','a(); const value=b();')
te('"NaN" should not be used in comparisons','use-isnan','if (value===NaN) run();','if (Number.isNaN(value)) run();')
te('Variables and functions should not be redeclared',{'@typescript-eslint/no-redeclare':'error'},'var value=1; var value=2;','let value=1; value=2;')
te('Wrapper objects should not be used for primitive types',{'no-new-wrappers':'error','@typescript-eslint/no-wrapper-object-types':'error'},'const value = new Boolean(false);','const value = false;')
te('Union and intersection types should not be defined with duplicated elements',{'@typescript-eslint/no-duplicate-type-constituents':'error'},'type Value = string | string;','type Value = string | number;')
te("Boolean expressions should not be gratuitous",{'no-constant-condition':['error',{'checkLoops':False}],'@typescript-eslint/no-unnecessary-condition':'error'},'if (true) run();','declare const value:boolean; if(value) run();',status='partial',reason='Checks type-proven constants and literal conditions. Arbitrary runtime/path-sensitive conditions beyond TypeScript narrowing are not proven.')
te('Destructuring patterns should not be empty','no-empty-pattern','const {}=value;','const {name}=value;')
te('"default" clauses should be last','default-case-last','switch(x){ default: run(); break; case 1: stop(); }','switch(x){ case 1: run(); break; default: stop(); }')
te('"await" should only be used with promises',{'@typescript-eslint/await-thenable':'error'},'async function f(){ await 1; }','async function f(){ await Promise.resolve(1); }')
te('Redundant pairs of parentheses should be removed',{'no-extra-parens':['error','all',{'nestedBinaryExpressions':False}]},'const value=(1);','const value=1;')
te('Constructors should not be declared inside interfaces',{'@typescript-eslint/no-misused-new':'error'},'interface Example { new(): Example; }','interface Example { create(): Example; }')
te('Variables should not be self-assigned','no-self-assign','value=value;','value=other;')
te('Multiline string literals should not be used','no-multi-str',"const value='a\\\nb';","const value=`a\nb`;")
te('Non-empty statements should change control flow or have at least one side-effect',{'@typescript-eslint/no-unused-expressions':['error',{'allowShortCircuit':True,'allowTernary':True,'allowTaggedTemplates':True}]},'a + b;','run(a+b);')
te('Extra semicolons should be removed','no-extra-semi','const value=1;;','const value=1;')
te('Nested blocks of code should not be left empty',{'no-empty':['error',{'allowEmptyCatch':False}]},'if(value) {}','if(value) { run(); }')
te('Identical expressions should not be used on both sides of a binary operator','no-self-compare','if(value===value) run();','if(value===other) run();',status='partial',reason='ESLint comparisons plus pure identifier/literal arithmetic, logical and bitwise duplicate operands with parentheses unwrapped. Getter/property/call expressions and complete side-effect analysis remain excluded.')
te('Variables declared with "var" should be declared before they are used',{'no-use-before-define':['error',{'functions':False,'classes':False,'variables':True}]},'run(value); var value=1;','var value=1; run(value);',status='implemented',reason='ESLint resolves use-before-definition bindings; exported var-only policy filters let/const, functions and classes by their actual declaration symbols.')
te('Debugger statements should not be used','no-debugger','debugger;','run();')
te('"delete" should not be used on arrays',{'@typescript-eslint/no-array-delete':'error'},'const values=[1,2]; delete values[0];','const values=[1,2]; values.splice(0,1);')
te('A compare function should be provided when using "Array.prototype.sort()"',{'@typescript-eslint/require-array-sort-compare':['error',{'ignoreStringArrays':False}]},'const values=[10,2]; values.sort();','const values=[10,2]; values.sort((a,b)=>a-b);')
te('Loops with at most one iteration should be refactored','no-unreachable-loop','for(const value of values) { run(value); break; }','for(const value of values) { run(value); }')
# Explicit compatibility mappings for removed legacy TypeScript-ESLint rules.
te('eslint_repo:@typescript-eslint/ban-types',{'@typescript-eslint/no-wrapper-object-types':'error','@typescript-eslint/no-unsafe-function-type':'error','@typescript-eslint/no-empty-object-type':'error'},'let value: Function;','let value: () => void;',status='implemented',reason='Executes the supported successor rules for the removed ban-types rule. Local interpretation enforces the successor defaults: no wrapper object types, unsafe function types, or empty object types.')
ta('eslint_repo:@typescript-eslint/interface-name-prefix','interface-prefix','interface IFoo { value: number; }','interface Foo { value: number; }',status='implemented',reason='Executes a local AST replacement for the removed interface-name-prefix rule. Local interpretation uses the historical default: interface names must not start with I followed by an uppercase letter.')
ta('eslint_repo:@typescript-eslint/member-delimiter-style','member-delimiter','interface Foo {\n value: number\n}','interface Foo {\n value: number;\n}',status='implemented',reason='Executes a local AST replacement for the removed member-delimiter-style rule. Local interpretation requires semicolon delimiters on multiline members and a final delimiter.')
ta('eslint_repo:@typescript-eslint/camelcase','variable-camel','let bad_name=1;','let goodName=1;',status='implemented',reason='Executes a local AST replacement for the removed camelcase rule. Local interpretation checks variable and parameter bindings; property interoperability exceptions are outside this local policy.')
# Typed AST/local-flow checks; partial whenever aliases, cross-function flows or semantics exceed the implementation.
ta('Array-mutating methods should not be used misleadingly','assigned-mutator','const values=[1,2]; const sorted=values.sort();','const values=[1,2]; const sorted=[...values].sort();',status='partial',reason='Detects sort/reverse results assigned to different bindings, including const aliases and assignment expressions; excludes assignment back to the same source array. Escaping state, reassigned aliases and nested expressions remain unsupported.')
ta("Types without members, 'any' and 'never' should not be used in type intersections",'empty-intersection','type Value=string & any;','type Value={a:string} & {b:number};')
ta('"in" should not be used on arrays','array-in','const values=[1,2]; for(const key in values) { run(key); }','const values={a:1}; for(const key in values) { run(key); }')
ta('All branches in a conditional structure should not have exactly the same implementation','all-identical-branches','if(value) { run(); } else { run(); }','if(value) { run(); } else { stop(); }',status='implemented',reason='Executes a local AST check comparing normalized direct if/else and switch branch implementations. Semantically equivalent branches expressed with different syntax are outside this local policy.')
ta("Function parameters, caught exceptions and foreach variables' initial values should not be ignored",'ignored-initial-value','function f(value: number){ value=1; return value; }','function f(value:number){ return value+1; }',status='partial',reason='Tracks unread incoming parameter, catch and for-of binding values through bounded branch/return paths and reports their first overwrite. Accounts for arguments object/index reads while excluding arguments.length and nested function arguments. Complex loops, exceptions, closures and full path feasibility remain unsupported.')
ta("The output of functions that don't return anything should not be used",'void-output','function log():void {} const value=log();','function get():number { return 1; } const value=get();',status='partial',reason='Checks TypeScript-inferred void results in assignments, returns, arguments, object/array literals, templates, casts, awaits and conditional values. Discarded comma-left and callback expression results are excluded. Unknown external signatures and full expression paths remain unsupported.')
ta('Conditionals should start on new lines','conditional-newline','if(a) run(); if(b) stop();','if(a) run();\nif(b) stop();')
ta('Boolean checks should not be inverted','inverted-boolean','if(!ready) stop(); else run();','if(ready) run(); else stop();',status='partial',reason='Detects negated if conditions with an else branch. Other forms of inversion and domain readability need review.')
ta('Values should not be uselessly incremented','useless-increment','function f(){ let value=0; return value++; }','function f(){ let value=0; return ++value; }',status='partial',reason='Detects returning a postfix update of a local variable. Other dead increments need liveness and escape analysis.')
ta('Parameters should be passed in the correct order','argument-order','function move(source:string,target:string){}; const source="a",target="b"; move(target,source);','function move(source:string,target:string){}; const source="a",target="b"; move(source,target);',status='partial',reason='Detects obvious permutations where call identifiers match a local resolved function signature parameter set. Positional semantics with different names require review.')
ta('Functions should not have identical implementations','identical-functions','function first(){ return 1; } function second(){ return 1; }','function first(){ return 1; } function second(){ return 2; }',status='implemented',reason='Executes a local structural-equivalence check across nonempty supplied-source functions with alpha-renamed local symbols and resolved import aliases, preserving literals, operators and free bindings. Semantic equivalence through refactoring, dynamic dispatch and missing dependencies is outside this local policy.')
ta('"switch" statements should not have too many "case" clauses','many-cases','switch(value){'+''.join('case '+str(i)+': break;' for i in range(31))+'}','switch(value){'+''.join('case '+str(i)+': break;' for i in range(30))+'}',reason='Counts CaseClause nodes; uses the exported maximum option (30 by default).')
ta('Comma and logical OR operators should not be used in switch cases','case-operator','switch(value){case 1 || 2: run();}','switch(value){case 1: case 2: run();}')
ta('A "while" loop should be used instead of a "for" loop','prefer-while','for(; ready;) { run(); }','while(ready) { run(); }')
ta('Function returns should not be invariant','invariant-return','function f(x:boolean){ if(x) return 1; return 1; }','function f(x:boolean){ if(x) return 1; return 2; }',status='partial',reason='Uses structural completion analysis for reachable returns, const aliases, literal conditions, switch fallthrough, loops, throws and finally overrides. Dynamic predicates, implicit effects and values produced by calls remain unknown.')
ta('Collection elements should not be replaced unconditionally','collection-overwrite','const values=[1,2]; for(const value of values) { values[0]=value; }','const values=[1,2]; for(let i=0;i<values.length;i++){ values[i]=i; }',status='partial',reason='Detects constant-index writes to the iterated array from a for-of loop. Other collection types, indices and aliases need dataflow analysis.')
ta("Non-existent operators '=+', '=-' and '=!' should not be used",'suspicious-assignment','value =+ 1;','value += 1;')
ta("Promise rejections should not be caught by 'try' block",'promise-try','function f(){ try { return Promise.reject(new Error()); } catch(e) { log(e); } }','async function f(){ try { return await Promise.reject(new Error()); } catch(e) { log(e); } }',status='partial',reason='Checks returned and discarded thenables inside lexical try bodies, follows const aliases and conditional/comma returns, and recognizes safe await/valid rejection handlers. Unknown thenables, handler side effects, interprocedural effects and arbitrary promise variables remain partial.')
ta('Errors should not be created without being thrown','unused-error','new Error("failed");','throw new Error("failed");')
ta('Empty collections should not be accessed or iterated','empty-array-use','const values: number[]=[]; const first=values[0];','const values: number[]=[1]; const first=values[0];',status='partial',reason='Detects reading or iterating an empty local array before a visible mutation/escape. Interprocedural mutations and arbitrary collection classes are outside this analysis.')
ta('Collection sizes and array length comparisons should make sense','collection-size','const values=[1,2]; if(values.length < 0) run();','const values=[1,2]; if(values.length > 0) run();')
ta('Collection and array contents should be used','unused-collection','const values:number[]=[]; values.push(1);','const values:number[]=[]; values.push(1); consume(values);',status='partial',reason='Detects local array bindings whose only references write through mutators/indexes. Escapes, indirect references and custom collections are outside this analysis.')
ta('Getters and setters should access the expected fields','accessor-field','class Example { _name=""; _age=0; get name(){ return this._age; } }','class Example { _name=""; get name(){ return this._name; } }',status='partial',reason='Checks simple backing fields named name or _name for matching accessors. Delegated/computed accessors and unconventional field policies need review.')
ta('Return values from functions without side effects should not be ignored','ignored-pure-return','const text="hello"; text.trim();','const text="hello"; const trimmed=text.trim();',status='implemented',reason='Executes a local allowlist policy that reports ignored returns from pure standard string/array/Math methods with known receiver types. Arbitrary function-effect inference is outside this local policy.')
ta('"undefined" should not be passed as the value of optional parameters','undefined-optional','function f(value?:number){} f(undefined);','function f(value?:number){} f();')
ta('Two branches in a conditional structure should not have exactly the same implementation','duplicate-branch','if(a) { run(); } else if(b) { stop(); } else { run(); }','if(a) { run(); } else if(b) { stop(); } else { wait(); }',status='implemented',reason='Executes a local AST check comparing normalized direct if/else and switch branch bodies within one construct. Semantically equivalent bodies expressed with different syntax are outside this local policy.')
ta('Hard-coded credentials are security-sensitive','hardcoded-credentials','const password="super-secret";','const password=readSecret();',status='partial',reason='Detects nonempty string literals bound to credential-word names using the exported credentialWords option. This is a security review candidate, not proof of a live credential.')
ta('Multiline blocks should be enclosed in curly braces','multiline-curly','if(ready)\n  run();','if(ready) {\n  run();\n}')
ta('"switch" statements should have at least 3 "case" clauses','few-cases','switch(value){case 1: run(); break; case 2: stop(); break;}','switch(value){case 1: run(); break; case 2: stop(); break; case 3: wait(); break;}')
ta('Boolean literals should not be used in comparisons','boolean-compare','declare const ready:boolean; if(ready === true) run();','declare const ready:boolean; if(ready) run();')

# Adversarial and boundary examples are additional tests, not additional rules.
extra_cases = [
 ('javascript','G.FMT.10','opening braces independent of else placement','if (ready)\n{ run(); }','if (ready) {\nrun();\n}\nelse {\nstop();\n}'),

 ('javascript','G.FMT.01','tabs inside strings are data','\tconst value=1;','const value="a\tb";'),

 ('typescript','Non-empty statements should change control flow or have at least one side-effect','short circuit side effect','enabled && value;','enabled && run();'),
 ('typescript','Non-empty statements should change control flow or have at least one side-effect','conditional side effects','enabled ? a : b;','enabled ? run() : stop();'),

 ('typescript', 'Comma and logical OR operators should not be used in switch cases', 'parenthesized switch alternatives', 'switch(value){case (1 || 2): run();}', 'switch(value){case (1 + 2): run();}'),
 ('typescript', 'Collection sizes and array length comparisons should make sense', 'typed receiver boundary', 'const values=new Set<number>(); if(values.size < 0) run();', 'const custom={length:-1}; if(custom.length < 0) run();'),
 ('typescript', '\"in\" should not be used on arrays', 'array membership versus object membership', 'const values=[1,2]; const found=1 in values;', 'const values={one:1}; const found=\"one\" in values;'),
 ('typescript', 'Boolean literals should not be used in comparisons', 'boolean versus coercion-sensitive union', 'declare const ready:boolean; if(false === ready) run();', 'declare const ready:boolean | undefined; if(ready === false) run();'),
 ('typescript', 'Functions should not have identical implementations', 'string contents remain significant', 'function a(){return \"a b\";} function b(){return \"a b\";}', 'function a(){return \"a b\";} function b(){return \"ab\";}'),
 ('typescript', 'Empty collections should not be accessed or iterated', 'visible mutation removes empty-array warning', 'const items:number[]=[]; for(const item of items) run(item);', 'const items:number[]=[]; fill(items); for(const item of items) run(item);'),
 ('typescript', 'Hard-coded credentials are security-sensitive', 'export credentialWords options default', 'const pwd=\"live-value\";', 'const password=\"\";'),
 ('javascript','G.CMT.03','TODO inside string is not comment','// FIXME: replace workaround\nrun();','const value=\"TODO FIXME\";'),
 ('javascript','G.CMT.04','copyright text must be header comment','const value=\"Copyright 2026\";','/* Copyright 2026 */\nrun();'),
 ('javascript','G.TYP.09','same-spelling shadow does not mutate outer array','const values=[1,2]; values.forEach(x=>{values.pop();});','const values=[1,2]; for(const x of values){const values=[]; values.push(x);}'),
 ('javascript','G.CORS.01','computed literal wildcard target','target[\"postMessage\"](value,\"*\");','target[\"postMessage\"](value,\"https://example.test\");'),
]
for lang,key,label,bad,good in extra_cases:
    rule=next(r for r in CAT if r['rule']['language']==lang.upper() and (r['rule']['name'].startswith(key+' ') if key.startswith('G.') else r['rule']['name']==key))
    cases.append({'rule_id':rule['id'],'language':lang,'name':label,'bad':bad,'good':good})

# Keep opening-brace placement separate from the independent else/catch rule.
fmt10=next(r['id'] for r in CAT if r['rule']['language']=='JAVASCRIPT' and r['rule']['name'].startswith('G.FMT.10 '))
definitions[fmt10]['message_ids']={'brace-style':['nextLineOpen']}

# Keep independently validated test evidence in the generator, not only in
# generated manifests, so regeneration cannot erase coverage provenance.
supplementary_by_detector={
    'typescript-ast:array-mutation-loop':'tests/test_frontend_deep_flow.py',
    'eslint:no-self-compare':'tests/test_frontend_deep_flow.py',
    'eslint:no-use-before-define':'tests/test_frontend_deep_flow.py',
    'typescript-ast:assigned-mutator':'tests/test_frontend_deep_flow.py',
    'typescript-ast:ignored-initial-value':'tests/test_frontend_deep_flow.py',
    'typescript-ast:void-output':'tests/test_frontend_deep_flow.py',
    'typescript-ast:identical-functions':'tests/test_frontend_deep_flow.py',
    'typescript-ast:finally-completion':'tests/test_frontend_completion_flow.py',
    'typescript-ast:invariant-return':'tests/test_frontend_completion_flow.py',
    'typescript-ast:promise-try':'tests/test_frontend_completion_flow.py',
}
for row in rows:
    if row['detector'] in supplementary_by_detector:
        row['supplementary_test_files']=[supplementary_by_detector[row['detector']]]

for language in ('javascript','typescript'):
    expected={r['id'] for r in CAT if r['rule']['language']==language.upper()}
    actual={r['rule_id'] for r in rows if r['language']==language}
    if expected!=actual: raise RuntimeError((language,expected-actual,actual-expected))
    (ROOT/f'rulesets/implementations/{language}.json').write_text(json.dumps([r for r in rows if r['language']==language],ensure_ascii=False,indent=2)+'\n')
(ROOT/'scripts/frontend_rules/mappings.json').write_text(json.dumps(definitions,ensure_ascii=False,indent=2)+'\n')
(ROOT/'tests/catalog_cases/frontend.json').write_text(json.dumps(cases,ensure_ascii=False,indent=2)+'\n')
print('Generated',len(rows),'rule mappings and',len(cases),'paired source cases')
