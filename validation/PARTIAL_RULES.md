# Partial 与 Manual 规则逐条覆盖说明

共 **158** 条（155 partial + 3 manual），按语言与规则族分组。每条列出检测器与覆盖说明（reason，manifest 原文未截断）。`partial`=只实现规则明确列出的可判定子集；`manual`=需人工/业务判断。生成自 `scripts/check.py --list-rules --format json`。

## 汇总

| 语言 | partial | manual | 小计 |
|---|---:|---:|---:|
| Java | 91 | 1 | 92 |
| Python | 33 | 2 | 35 |
| JavaScript | 16 | 0 | 16 |
| TypeScript | 15 | 0 | 15 |
| **合计** | 155 | 3 | 158 |

## Java（92 条）

### 族 G.CON（10 条）

- **`da67a0aa6db811eea68ffa163e0fa374`** `partial` | detector: `javac-ast:lock_eviction`
  - 规则: G.CON.01 对共享变量做同步访问控制时需避开同步陷阱
  - 覆盖: Detects direct eviction of a computeIfAbsent-created lock mapping in finally, the observed lock-splitting hazard. Other shared-state synchronization traps require additional models.
- **`da6bbf0e6db811eea68ffa163e0fa374`** `partial` | detector: `javac-ast:instance_static_lock`
  - 规则: G.CON.01 对共享变量做同步访问控制时需避开同步陷阱--不要使用实例锁来保护静态共享数据
  - 覆盖: Detects local static field access inside synchronized(this); aliases and inherited state require interprocedural analysis.
- **`da752e1f6db811eea68ffa163e0fa374`** `partial` | detector: `javac-ast:thread_handler`
  - 规则: G.CON.08 使用Thread对象的setUncaughtExceptionHandler方法注册未捕获异常处理者
  - 覆盖: Looks for same-method handler registration before Thread.start; global/default/inherited handlers need lifecycle analysis.
- **`da7522ee6db811eea68ffa163e0fa374`** `partial` | detector: `javac-ast:wait_notify`
  - 规则: G.CON.06 使用新并发工具代替wait()和notify()
  - 覆盖: Detects wait/notify method call syntax; shadowing custom methods requires type resolution.
- **`da5fd4f06db811eea68ffa163e0fa374`** `partial` | detector: `javac-ast:threadlocal_cleanup`
  - 规则: G.CON.13 线程池中的任务结束后必须清理其自定义的ThreadLocal变量
  - 覆盖: Checks same-method finally removal for directly named ThreadLocal; interprocedural task lifecycle and aliases need flow analysis.
- **`da7517796db811eea68ffa163e0fa374`** `partial` | detector: `javac-ast:thread_name`
  - 规则: G.CON.07 创建新线程时必须指定线程名
  - 覆盖: Detects constructor naming; setName before start requires local lifecycle tracking.
- **`da77306c6db811eea68ffa163e0fa374`** `partial` | detector: `javac-ast:double_checked_lock`
  - 规则: G.CON.04 避免使用不正确形式的双重检查锁
  - 覆盖: Detects common same-condition double-check publishing without volatile; aliases and alternative safe-publication schemes need memory-model analysis.
- **`da5de2b26db811eea68ffa163e0fa374`** `partial` | detector: `javac-ast:unsafe_override`
  - 规则: G.CON.05 禁止使用非线程安全的方法来覆写线程安全的方法
  - 覆盖: Matches supplied-source inherited method signatures and synchronization modifiers, including generic parameter substitution. External classpath overrides, concurrency semantics beyond synchronized and complex generic bounds remain unsupported.
- **`da6699076db811eea68ffa163e0fa374`** `partial` | detector: `javac-ast:reused_lock`
  - 规则: G.CON.01 对共享变量做同步访问控制时需避开同步陷阱--不要使用可被重用的对象锁
  - 覆盖: Detects string/boxed primitive locks from local declarations and literals; aliases require type resolution.
- **`da6680f96db811eea68ffa163e0fa374`** `partial` | detector: `javac-ast:concurrent_lock`
  - 规则: G.CON.01 对共享变量做同步访问控制时需避开同步陷阱--不要使用基于高级并发对象的synchronized块
  - 覆盖: Checks known java.util.concurrent synchronizer types, not arbitrary subclasses.
### 族 G.PRM（3 条）

- **`da7574cb6db811eea68ffa163e0fa374`** `partial` | detector: `javac-ast:resource_close`
  - 规则: G.PRM.07 进行IO类操作时，必须在try-with-resource或finally里关闭资源
  - 覆盖: Checks common resource constructors, direct try resources and same-method finally close; ownership transfer/aliases and exceptional paths require dataflow.
- **`da7541666db811eea68ffa163e0fa374`** `partial` | detector: `javac-ast:typed_toarray`
  - 规则: G.PRM.01 将集合转为数组时使用Collection<T>.toArray(T[])方法；Java 11后使用Collection<T>.toArray(IntFunction<T[]>)
  - 覆盖: Checks locally declared common collection types; inherited/custom collections require type attribution.
- **`da5fb1426db811eea68ffa163e0fa374`** `partial` | detector: `javac-ast:resource_close`
  - 规则: G.PRM.07 进行IO类操作时，必须在try-with-resource或finally里关闭资源
  - 覆盖: Checks common resource constructors, direct try resources and same-method finally close; ownership transfer/aliases and exceptional paths require dataflow.
### 族 G.OBJ（8 条）

- **`da653cb46db811eea68ffa163e0fa374`** `partial` | detector: `javac-ast:override_annotation`
  - 规则: G.OBJ.07 子类覆写父类方法或实现接口时必须加上@Override注解
  - 覆盖: Resolves supplied-source packages, imports, nested classes, generic inheritance and erased method signatures, with visibility checks and common Object methods. External classpath attribution, generated members and complex bounds remain unsupported.
- **`da7001396db811eea68ffa163e0fa374`** `partial` | detector: `javac-ast:constructor_override`
  - 规则: G.OBJ.02 不要在父类的构造方法中调用可能被子类覆写的方法
  - 覆盖: Detects constructor calls to locally declared overridable methods; transitive and inherited calls require call graph.
- **`da7500456db811eea68ffa163e0fa374`** `partial` | detector: `javac-ast:singleton_constructor`
  - 规则: G.OBJ.08 正确实现单例模式
  - 覆盖: Detects exposed constructors in locally identifiable INSTANCE/singleton classes; all serialization, cloning and concurrent singleton hazards need additional models.
- **`da74f6266db811eea68ffa163e0fa374`** `partial` | detector: `javac-ast:static_receiver`
  - 规则: G.OBJ.09 使用类名调用静态方法，而不要使用实例或表达式来调用
  - 覆盖: Resolves static methods declared in the same source file and locally typed receivers; dependency classes require attribution.
- **`da74ea5f6db811eea68ffa163e0fa374`** `partial` | detector: `javac-ast:constructor_reuse`
  - 规则: G.OBJ.03 构造方法如果有多个，尽量重用
  - 覆盖: Detects identical constructor bodies; semantic common-prefix/suffix factoring requires deeper analysis.
- **`da74d41e6db811eea68ffa163e0fa374`** `partial` | detector: `javac-ast:shadowing`
  - 规则: G.OBJ.04 避免在无关的变量或无关的概念之间重用名字，避免隐藏（hide）、遮蔽（shadow）和遮掩（obscure）
  - 覆盖: Detects local/parameter shadowing of same-class fields; inherited names, imports and intentional setter patterns require context.
- **`da74c9566db811eea68ffa163e0fa374`** `partial` | detector: `javac-ast:equals_hashcode`
  - 规则: G.OBJ.06 覆写equals方法时，要同时覆写hashCode方法
  - 覆盖: Resolves equals(Object), inherited hashCode and custom Object names across supplied-source hierarchies. External classpath methods and behavioral contracts remain unproven.
- **`da5dd5a86db811eea68ffa163e0fa374`** `partial` | detector: `javac-ast:constructor_override`
  - 规则: G.OBJ.02 不要在父类的构造方法中调用可能被子类覆写的方法
  - 覆盖: Detects constructor calls to locally declared overridable methods; transitive and inherited calls require call graph.
### 族 G.EDV（9 条）

- **`da6c34736db811eea68ffa163e0fa374`** `partial` | detector: `javac-ast:xml_expansion`
  - 规则: G.EDV.06 防止解析来自外部的XML导致的内部实体扩展（XML Entity Expansion）攻击
  - 覆盖: Detects explicit DOCTYPE enablement; parser limits and complete entity expansion defenses need configuration flow.
- **`da6c2aac6db811eea68ffa163e0fa374`** `partial` | detector: `javac-ast:xml_external`
  - 规则: G.EDV.05 防止解析来自外部的XML导致的外部实体（XML External Entity）攻击
  - 覆盖: Detects explicit unsafe external-entity/DTD settings; defaults and effective factory configuration require object flow.
- **`da5ff9c56db811eea68ffa163e0fa374`** `partial` | detector: `javac-ast:taint_xml_concat`
  - 规则: G.EDV.04 禁止直接使用外部数据来拼接XML
  - 覆盖: Bounded intraprocedural propagation from common servlet/environment sources to this sink; recognizes direct-initializer XML-escaping sanitizers (StringEscapeUtils.escapeXml*, ESAPI encodeForXML) for this XML-concatenation sink, but no call graph, path-sensitive tracking or framework type attribution. Aliases and reassignments are not tracked, so only a binding's direct sanitizer-call initializer is neutralized. Partial-argument mixes are reported when any tainted fragment remains unsanitized. Review candidate, not a proven vulnerability.
- **`da5fe0a26db811eea68ffa163e0fa374`** `partial` | detector: `javac-ast:taint_format`
  - 规则: G.EDV.02 禁止直接使用外部数据构造格式化字符串
  - 覆盖: Bounded intraprocedural propagation from common servlet/environment sources to this sink; no call graph, path-sensitive sanitizers or framework type attribution. Review candidate, not a proven vulnerability.
- **`da5fbeac6db811eea68ffa163e0fa374`** `partial` | detector: `javac-ast:sql_concat`
  - 规则: G.EDV.01 禁止直接使用外部数据来拼接SQL语句
  - 覆盖: Detects SQL sink string concatenation; external-input provenance and prepared-statement bind flow need taint analysis.
- **`da66bac66db811eea68ffa163e0fa374`** `partial` | detector: `javac-ast:xslt_secure`
  - 规则: G.EDV.07 禁止使用不安全的XSLT转换XML文件
  - 覆盖: Detects explicit insecure processing and external-stylesheet access; effective defaults and source trust need type/configuration analysis.
- **`da5df7456db811eea68ffa163e0fa374`** `partial` | detector: `javac-ast:regex_redos`
  - 规则: G.EDV.08 正则表达式要尽量简单，防止ReDos攻击
  - 覆盖: Detects nested unbounded repetition in literal patterns; full regex automata ambiguity analysis is not implemented.
- **`da67c9c46db811eea68ffa163e0fa374`** `partial` | detector: `javac-ast:reflection_input`
  - 规则: G.EDV.09 禁止直接使用外部数据作为反射操作中的类名/方法名
  - 覆盖: Detects dynamic reflection names; external-input taint and allowlists need interprocedural analysis.
- **`da76eeb66db811eea68ffa163e0fa374`** `partial` | detector: `javac-ast:command_input`
  - 规则: G.EDV.03 禁止直接向Runtime.exec() 方法或java.lang.ProcessBuilder 类传递外部数据
  - 覆盖: Detects dynamic arguments to Runtime.exec; validates neither sanitizers nor complete ProcessBuilder flow.
### 族 G.EXP（3 条）

- **`da6515d96db811eea68ffa163e0fa374`** `partial` | detector: `javac-ast:ternary_types`
  - 规则: G.EXP.03 条件表达式?:的第2和第3个操作数应使用相同的类型
  - 覆盖: Compares types from literals, casts and local declarations; inferred generics/calls need type attribution.
- **`da62831f6db811eea68ffa163e0fa374`** `partial` | detector: `javac-ast:null_dereference`
  - 规则: G.EXP.05 禁止直接使用可能为null的对象，防止出现空指针引用
  - 覆盖: Detects explicit local null initialization followed by dereference without direct assignment/guard; full nullability dataflow is not implemented.
- **`da6fd3ed6db811eea68ffa163e0fa374`** `partial` | detector: `javac-ast:explicit_precedence`
  - 规则: G.EXP.02 用括号明确表达式的操作顺序，避免过分依赖默认优先级
  - 覆盖: Detects common mixed arithmetic/boolean/bitwise precedence; all operator combinations are not covered.
### 族 G.TYP（7 条）

- **`da7335a56db811eea68ffa163e0fa374`** `partial` | detector: `javac-ast:decimal_precision`
  - 规则: G.TYP.04 需要精确计算时使用BigDecimal，不要使用float和double
  - 覆盖: Flags amount-like float/double variable names for review; determining exact-decimal requirements requires domain knowledge.
- **`da773d126db811eea68ffa163e0fa374`** `partial` | detector: `javac-ast:integer_overflow`
  - 规则: G.TYP.01 进行数值运算时，避免整数溢出
  - 覆盖: Checks literal integer arithmetic overflow; symbolic ranges, narrowing and interprocedural values require abstract interpretation.
- **`da771bc36db811eea68ffa163e0fa374`** `partial` | detector: `javac-ast:zero_divisor`
  - 规则: G.TYP.02 确保除法运算和模运算中的除数不为0
  - 覆盖: Detects literal zero divisors; symbolic ranges and path constraints require dataflow analysis.
- **`da655c276db811eea68ffa163e0fa374`** `partial` | detector: `javac-ast:explicit_cast`
  - 规则: G.TYP.12 明确地进行类型转换，避免依赖隐式类型转换
  - 覆盖: Detects integer division implicitly converted to floating/long declarations; other numeric promotions and generic conversions need attribution.
- **`da7482f56db811eea68ffa163e0fa374`** `partial` | detector: `javac-ast:downcast_check`
  - 规则: G.TYP.13 在引用类型向下转换前用instanceof进行判断
  - 覆盖: Checks Object-to-reference casts guarded by an enclosing instanceof condition; flow patterns and assignability need attribution.
- **`da6551716db811eea68ffa163e0fa374`** `partial` | detector: `javac-ast:boxed_primitive`
  - 规则: G.TYP.11 基本类型优于包装类型，注意合理使用包装类型
  - 覆盖: Detects unnecessary boxed allocation in primitive-return methods; full primitive preference and legitimate nullability require types/context.
- **`da7478046db811eea68ffa163e0fa374`** `partial` | detector: `javac-ast:hardcoded_separator`
  - 规则: G.TYP.07 避免在代码中硬编码用于表示换行、文件路径分隔的字符--不要在代码中硬编码用于表示文件路径分隔的字符
  - 覆盖: Detects standalone slash/backslash strings; distinguishing path syntax from URLs/regex needs dataflow.
### 族 G.CTL（1 条）

- **`da6ffe8d6db811eea68ffa163e0fa374`** `partial` | detector: `javac-ast:condition_assignment`
  - 规则: G.CTL.01 不要在控制性条件表达式中执行赋值操作或执行复杂的条件判断
  - 覆盖: Detects assignment in control conditions; complex-condition readability is not fully implemented.
### 族 G.SEC（2 条）

- **`da66c40c6db811eea68ffa163e0fa374`** `partial` | detector: `javac-ast:security_method`
  - 规则: G.SEC.01 进行安全检查的方法必须声明为private或final
  - 覆盖: Recognizes common security-check method names; semantic classification of arbitrary authorization methods is not implemented.
- **`da6b99806db811eea68ffa163e0fa374`** `partial` | detector: `javac-ast:classloader_permissions`
  - 规则: G.SEC.02 自定义类加载器覆写getPermission() 时，必须先调用父类的getPermission() 方法
  - 覆盖: Checks direct local ClassLoader subclass methods and super call presence; override attribution and call ordering require complete control flow.
### 族 G.DCL（1 条）

- **`da6ff13f6db811eea68ffa163e0fa374`** `partial` | detector: `javac-ast:mutable_constant`
  - 规则: G.DCL.05 禁止将mutable对象声明为public static final
  - 覆盖: Detects arrays and common mutable collection declarations; custom mutability and aliases require type analysis.
### 族 非G族（19 条）

- **`da6c0e656db811eea68ffa163e0fa374`** `partial` | detector: `javac-ast:key_length`
  - 规则: 规则-9.2 禁止使用私有或者弱加密算法--密钥长度少于指定长度
  - 覆盖: Locally resolves literal algorithm/key size with an explicit policy (RSA/DSA/DH >=2048, AES >=128); export gives no authoritative thresholds.
- **`da6bfac16db811eea68ffa163e0fa374`** `partial` | detector: `javac-ast:fixed_salt`
  - 规则: 规则-9.3 基于哈希算法的口令安全存储必须加入盐值（salt）--盐值硬编码
  - 覆盖: Detects literal/new-array salts and directly initialized array variables; aliases and external secret configuration require dataflow.
- **`da6bf4786db811eea68ffa163e0fa374`** `partial` | detector: `javac-ast:hash_iterations`
  - 规则: 规则-9.3 基于哈希算法的口令安全存储必须加入盐值（salt）--Hash迭代不充分
  - 覆盖: Explicit local floor 10000 iterations for PBEKeySpec; actual algorithm-specific current policy must be configured separately.
- **`da60da8c6db811eea68ffa163e0fa374`** `partial` | detector: `javac-ast:old_tls`
  - 规则: 规则2.6.1 禁止使用SSL2.0、SSL3.0、TLS1.0、TLS1.1协议
  - 覆盖: Checks literal SSLContext and enabled protocol arrays; effective provider defaults require runtime configuration.
- **`da60a1026db811eea68ffa163e0fa374`** `partial` | detector: `javac-ast:pending_intent`
  - 规则: 规则6.3 使用PENDINGINTENT触发事件时须传入显式INTENT
  - 覆盖: Tracks direct Intent construction/setClass/setComponent before PendingIntent; aliases and framework factory methods need dataflow.
- **`da6069916db811eea68ffa163e0fa374`** `partial` | detector: `javac-ast:ssh_algorithms`
  - 规则: 建议2.6.5 SSH协议优先选择ECC密钥交换算法和身份认证公钥算法，优先选择HMAC-SHA2消息认证算法
  - 覆盖: Detects weak explicit JSch-style SSH algorithm lists; default/provider negotiation and relative algorithm preference require configuration context.
- **`da6010376db811eea68ffa163e0fa374`** `partial` | detector: `javac-ast:cookie_secure`
  - 规则: 建议5.5 为cookie设置secure标志
  - 覆盖: Detects explicit secure=false; missing secure=true and framework/global cookie policy need lifecycle analysis.
- **`da5fc95a6db811eea68ffa163e0fa374`** `partial` | detector: `javac-ast:taint_trust`
  - 规则: P.05 外部数据使用前必须进行合法性校验--信任边界场景
  - 覆盖: Bounded intraprocedural propagation from common servlet/environment sources to this sink; no call graph, path-sensitive sanitizers or framework type attribution. Review candidate, not a proven vulnerability.
- **`da67d1b56db811eea68ffa163e0fa374`** `partial` | detector: `javac-ast:taint_xpath`
  - 规则: P.05 外部数据使用前必须进行合法性校验--外部数据控制Xpath
  - 覆盖: Bounded intraprocedural propagation from common servlet/environment sources to this sink; no call graph, path-sensitive sanitizers or framework type attribution. Review candidate, not a proven vulnerability.
- **`da5fa3c66db811eea68ffa163e0fa374`** `partial` | detector: `javac-ast:taint_resource`
  - 规则: P.05 外部数据使用前必须进行合法性校验--资源注入场景
  - 覆盖: Bounded intraprocedural propagation from common servlet/environment sources to this sink; no call graph, path-sensitive sanitizers or framework type attribution. Review candidate, not a proven vulnerability.
- **`da67d09a6db811eea68ffa163e0fa374`** `partial` | detector: `javac-ast:taint_xml_validation`
  - 规则: P.05 外部数据使用前必须进行合法性校验--外部数据控制XML校验
  - 覆盖: Bounded intraprocedural propagation from common servlet/environment sources to this sink; no call graph, path-sensitive sanitizers or framework type attribution. Review candidate, not a proven vulnerability.
- **`da67cfc16db811eea68ffa163e0fa374`** `partial` | detector: `javac-ast:taint_hash`
  - 规则: P.05 外部数据使用前必须进行合法性校验--外部数据控制哈希算法
  - 覆盖: Bounded intraprocedural propagation from common servlet/environment sources to this sink; no call graph, path-sensitive sanitizers or framework type attribution. Review candidate, not a proven vulnerability.
- **`da7726f86db811eea68ffa163e0fa374`** `partial` | detector: `javac-ast:taint_header`
  - 规则: P.05 外部数据使用前必须进行合法性校验--Header Manipulation场景
  - 覆盖: Bounded intraprocedural propagation from common servlet/environment sources to this sink; recognizes direct-initializer URL-encoding sanitizers (URLEncoder.encode) for this header sink, but no call graph, path-sensitive tracking or framework type attribution. Aliases and reassignments are not tracked, so only a binding's direct sanitizer-call initializer is neutralized. Partial-argument mixes are reported when any tainted fragment remains unsanitized. Review candidate, not a proven vulnerability.
- **`da5dc9f76db811eea68ffa163e0fa374`** `partial` | detector: `javac-ast:taint_redirect`
  - 规则: P.05 外部数据使用前必须进行合法性校验--未经验证的重定向和转发场景
  - 覆盖: Bounded intraprocedural propagation from common servlet/environment sources to this sink; recognizes direct-initializer URL-encoding sanitizers (URLEncoder.encode) for this redirect sink, but no call graph, path-sensitive tracking or framework type attribution. Aliases and reassignments are not tracked, so only a binding's direct sanitizer-call initializer is neutralized. Partial-argument mixes are reported when any tainted fragment remains unsanitized. Review candidate, not a proven vulnerability.
- **`da77065e6db811eea68ffa163e0fa374`** `partial` | detector: `javac-ast:lock_order`
  - 规则: P.03 使用相同的顺序请求和释放锁来避免死锁
  - 覆盖: Detects opposite acquisition order of directly named field locks across local methods; aliasing, call graph, releases and conditional lock orders need analysis.
- **`da5dbde96db811eea68ffa163e0fa374`** `partial` | detector: `javac-ast:taint_ognl`
  - 规则: P.05 外部数据使用前必须进行合法性校验--OGNL注入场景
  - 覆盖: Bounded intraprocedural propagation from common servlet/environment sources to this sink; no call graph, path-sensitive sanitizers or framework type attribution. Review candidate, not a proven vulnerability.
- **`da76fab36db811eea68ffa163e0fa374`** `partial` | detector: `javac-ast:taint_xss`
  - 规则: P.05 外部数据使用前必须进行合法性校验--跨站脚本场景
  - 覆盖: Bounded intraprocedural propagation from common servlet/environment sources to this sink; recognizes direct-initializer encoding/escaping sanitizers (StringEscapeUtils.escapeHtml*, escapeXml*, ESAPI encodeForHTML/HTMLAttribute) for this XSS sink, but no call graph, path-sensitive tracking or framework type attribution. Aliases and reassignments are not tracked, so only a binding's direct sanitizer-call initializer is neutralized. Partial-argument mixes are reported when any tainted fragment remains unsanitized. Review candidate, not a proven vulnerability.
- **`da76d24b6db811eea68ffa163e0fa374`** `partial` | detector: `javac-ast:taint_code`
  - 规则: P.05 外部数据使用前必须进行合法性校验--代码注入场景
  - 覆盖: Bounded intraprocedural propagation from common servlet/environment sources to this sink; no call graph, path-sensitive sanitizers or framework type attribution. Review candidate, not a proven vulnerability.
- **`da5d85aa6db811eea68ffa163e0fa374`** `partial` | detector: `javac-ast:taint_ldap`
  - 规则: P.05 外部数据使用前必须进行合法性校验--LDAP注入场景
  - 覆盖: Bounded intraprocedural propagation from common servlet/environment sources to this sink; no call graph, path-sensitive sanitizers or framework type attribution. Review candidate, not a proven vulnerability.
### 族 G.FMT（6 条）

- **`da730a766db811eea68ffa163e0fa374`** `partial` | detector: `javac-ast:vertical_alignment`
  - 规则: G.FMT.14 不应插入多余空格使代码垂直对齐
  - 覆盖: Detects repeated spaces before declaration/assignment equals; visual alignment across all operators requires a full formatter.
- **`da72ff0c6db811eea68ffa163e0fa374`** `partial` | detector: `javac-ast:operator_spaces`
  - 规则: G.FMT.13 用空格突出关键字和重要信息
  - 覆盖: Checks AST binary operators; unary, keyword, delimiter and generics spacing need further formatting rules.
- **`da72e8dd6db811eea68ffa163e0fa374`** `partial` | detector: `javac-ast:operator_wrap`
  - 规则: G.FMT.11 建议换行起点在操作符之前
  - 覆盖: Checks common AST binary operators; chained calls and remaining operators need formatting extension.
- **`da72ca6d6db811eea68ffa163e0fa374`** `partial` | detector: `javac-ast:empty_block`
  - 规则: G.FMT.07 应该避免空块，必须使用空块时，应采用统一的大括号换行风格
  - 覆盖: Detects empty control/initializer blocks; mandatory empty blocks and brace-style exceptions need contextual policy.
- **`da72c16e6db811eea68ffa163e0fa374`** `partial` | detector: `javac-ast:indentation`
  - 规则: G.FMT.08 使用空格进行缩进，每次缩进4个空格
  - 覆盖: Detects tab indentation; continuation/alignment-aware full four-space indentation is not implemented.
- **`da728f456db811eea68ffa163e0fa374`** `partial` | detector: `javac-ast:comment_indent`
  - 规则: G.FMT.18 块注释的缩进级别应与上下文代码相同
  - 覆盖: Compares standalone multiline comment indentation to next code line; trailing/end-of-block comments and formatter exceptions need context.
### 族 G.FIO（6 条）

- **`da6fe6f46db811eea68ffa163e0fa374`** `partial` | detector: `javac-ast:zip_directory_bytes`
  - 规则: G.FIO.02 从ZipInputStream中解压文件必须进行安全检查
  - 覆盖: Detects directory paths that skip explicit payload reads before implicit closeEntry/getNextEntry draining. Partial pattern covering observed directory-entry quota bypass; full Zip Slip/size/ownership analysis requires complete flow models.
- **`da6bd1d96db811eea68ffa163e0fa374`** `partial` | detector: `javac-ast:read_int`
  - 规则: G.FIO.03 对于从流中读取一个字符或字节的方法，使用int类型的返回值
  - 覆盖: Detects explicit narrow casts of read(); other flow through wrapper conversions requires type/dataflow analysis.
- **`da6baaea6db811eea68ffa163e0fa374`** `partial` | detector: `javac-ast:taint_path`
  - 规则: G.FIO.01 使用外部数据构造的文件路径前必须进行校验，校验前必须对文件路径进行规范化处理
  - 覆盖: Bounded intraprocedural propagation from common servlet/environment sources to this sink; no call graph, path-sensitive sanitizers or framework type attribution. Review candidate, not a proven vulnerability.
- **`da6ba2666db811eea68ffa163e0fa374`** `partial` | detector: `javac-ast:process_streams`
  - 规则: G.FIO.04 防止外部进程阻塞在输入输出流上
  - 覆盖: Detects waitFor with no same-method stream handling; cannot prove deadlock freedom or independent stream draining.
- **`da5f954d6db811eea68ffa163e0fa374`** `partial` | detector: `javac-ast:temp_cleanup`
  - 规则: G.FIO.05 临时文件使用完毕必须及时删除
  - 覆盖: Checks presence of same-method finally deletion, not all alias/path or ownership cases.
- **`da67cc6b6db811eea68ffa163e0fa374`** `partial` | detector: `javac-ast:taint_path`
  - 规则: G.FIO.01 使用外部数据构造的文件路径前必须进行校验，校验前必须对文件路径进行规范化处理
  - 覆盖: Bounded intraprocedural propagation from common servlet/environment sources to this sink; no call graph, path-sensitive sanitizers or framework type attribution. Review candidate, not a proven vulnerability.
### 族 G.ERR（3 条）

- **`da622cf66db811eea68ffa163e0fa374`** `partial` | detector: `javac-ast:exception_leak`
  - 规则: G.ERR.04 防止通过异常泄露敏感信息
  - 覆盖: Reports direct printStackTrace; actual sensitive information and response sinks need taint/context.
- **`da707c426db811eea68ffa163e0fa374`** `manual` | detector: `None`
  - 规则: G.ERR.05 方法抛出的异常，应该与本身的抽象层次相对应
  - 覆盖: Determining the intended abstraction level of a method and whether its exceptions match that domain requires an explicit architecture/domain contract. Source syntax alone cannot establish that contract.
- **`da67a19d6db811eea68ffa163e0fa374`** `partial` | detector: `javac-ast:exception_leak`
  - 规则: G.ERR.04 防止通过异常泄露敏感信息
  - 覆盖: Reports direct printStackTrace; actual sensitive information and response sinks need taint/context.
### 族 G.OTH（3 条）

- **`da7248a86db811eea68ffa163e0fa374`** `partial` | detector: `javac-ast:commented_code`
  - 规则: G.OTH.03 不用的代码段包括import，直接删除，不要注释掉--不用的代码段，直接删除，不要注释掉
  - 覆盖: Heuristic detection within actual comment tokens; natural-language code examples need human review.
- **`da6bc9326db811eea68ffa163e0fa374`** `partial` | detector: `javac-ast:weak_random`
  - 规则: G.OTH.01 安全场景下必须使用密码学意义上的安全随机数
  - 覆盖: Reports java.util.Random construction; deciding whether randomness is security-sensitive requires dataflow/context.
- **`da6bb4986db811eea68ffa163e0fa374`** `partial` | detector: `javac-ast:public_ip`
  - 规则: G.OTH.04 禁止代码中包含公网地址
  - 覆盖: Detects public IPv4 literals; hostnames, IPv6, generated addresses and environment-specific exceptions need extension.
### 族 G.SER（4 条）

- **`da6fca696db811eea68ffa163e0fa374`** `partial` | detector: `javac-ast:serializable`
  - 规则: G.SER.01 尽量避免实现Serializable接口
  - 覆盖: Resolves adoption and inheritance of java.io.Serializable across supplied-source imports and hierarchies, excluding unrelated same-name types. Avoidability remains a design review; external bases need classpath context.
- **`da6fc0946db811eea68ffa163e0fa374`** `partial` | detector: `javac-ast:serial_resource`
  - 规则: G.SER.04 禁止直接序列化指向系统资源的信息
  - 覆盖: Resolves Serializable inheritance in supplied source and flags a known set of resource field types. Resource wrappers, inherited fields and external dependency types remain unsupported.
- **`da6b8d3e6db811eea68ffa163e0fa374`** `partial` | detector: `javac-ast:deserialize_validation`
  - 规则: G.SER.07 防止反序列化被利用来绕过构造方法中的安全操作
  - 覆盖: Compares recognizable validation calls in local constructors and readObject; arbitrary safety invariants and inherited serialization need semantic analysis.
- **`da67cd506db811eea68ffa163e0fa374`** `partial` | detector: `javac-ast:deserialize`
  - 规则: G.SER.08 禁止直接将外部数据进行反序列化
  - 覆盖: Reports ObjectInputStream construction for source/filter review; does not prove external taint.
### 族 G.LOG（4 条）

- **`da71857f6db811eea68ffa163e0fa374`** `partial` | detector: `javac-ast:chinese_log`
  - 规则: G.LOG.04 非仅限于中文区销售产品禁止用中文打印日志
  - 覆盖: Detects CJK literals in common logger calls; region/product-language policy must be supplied.
- **`da70b2976db811eea68ffa163e0fa374`** `partial` | detector: `javac-ast:logging_facade`
  - 规则: G.LOG.01 记录日志应该使用Facade模式的日志框架
  - 覆盖: Flags System.out/err printing; verifies neither all logging frameworks nor Facade conformance.
- **`da709a416db811eea68ffa163e0fa374`** `partial` | detector: `javac-ast:log_level`
  - 规则: G.LOG.03 日志必须分等级
  - 覆盖: Flags known logger.log(String) shape with no level; arbitrary custom logger API semantics need type attribution.
- **`da5d929f6db811eea68ffa163e0fa374`** `partial` | detector: `javac-ast:taint_log`
  - 规则: G.LOG.05 禁止直接使用外部数据记录日志
  - 覆盖: Bounded intraprocedural propagation from common servlet/environment sources to this sink; no call graph, path-sensitive sanitizers or framework type attribution. Review candidate, not a proven vulnerability.
### 族 G.MET（2 条）

- **`da74bee86db811eea68ffa163e0fa374`** `partial` | detector: `javac-ast:varargs`
  - 规则: G.MET.04 谨慎使用可变数量参数
  - 覆盖: Reports varargs for review; deciding whether the API use is justified needs context.
- **`da74b3986db811eea68ffa163e0fa374`** `partial` | detector: `javac-ast:optional_null`
  - 规则: G.MET.06 使用Optional代替null作为返回值或者可能的缺失值；禁止对Optional对象赋值为null
  - 覆盖: Checks explicit null assignment/return; does not infer all nullable expressions or Optional API design choices.
### 族 G.COL（1 条）

- **`da7090006db811eea68ffa163e0fa374`** `partial` | detector: `javac-ast:prefer_collections`
  - 规则: G.COL.02 优先使用泛型集合，而不是数组
  - 覆盖: Reports reference arrays for API/performance review; arrays may be justified and generic collection design needs context.

## Python（35 条）

### 族 G.LOG（2 条）

- **`da68aebe6db811eea68ffa163e0fa374`** `partial` | detector: `python-ast-tokenize:G.LOG.03`
  - 规则: G.LOG.03 禁止直接使用外部数据记录日志
  - 覆盖: Tracks direct input/request/environment data into logging format arguments within a file; custom sources and interprocedural sanitizers are not modeled.
- **`da6767f86db811eea68ffa163e0fa374`** `partial` | detector: `python-ast-tokenize:G.LOG.02`
  - 规则: G.LOG.02 使用日志记录工具实现日志功能
  - 覆盖: Flags print calls outside test-like paths; distinguishing CLI output from logging requires project intent.
### 族 G.EDV（5 条）

- **`da6890366db811eea68ffa163e0fa374`** `partial` | detector: `python-ast-tokenize:G.EDV.03`
  - 规则: G.EDV.03 避免在命令解析器中使用通配符
  - 覆盖: Checks literal wildcard shell command strings and commands assembled via +, %, f-string (including format specs) or str.format (positional and keyword args), plus list commands with shell=True; non-literal variable content and helper-call results still require data-flow analysis.
- **`da6963406db811eea68ffa163e0fa374`** `partial` | detector: `python-ast-tokenize:G.EDV.09`
  - 规则: G.EDV.09 禁止直接使用外部数据来拼接XML
  - 覆盖: Detects direct tainted string concatenation forming XML; template engines and custom sanitizers require interprocedural analysis.
- **`da6958bf6db811eea68ffa163e0fa374`** `partial` | detector: `python-ast-tokenize:G.EDV.10`
  - 规则: G.EDV.10 禁止在处理XML数据时解析不可信的实体
  - 覆盖: Detects explicit lxml entity enabling and common unsafe XML parsers; parser versions, external trust and custom resolvers require review.
- **`da6943f76db811eea68ffa163e0fa374`** `partial` | detector: `python-ast-tokenize:G.EDV.07`
  - 规则: G.EDV.07 不受信任的外部数据禁止使用.format()进行格式化
  - 覆盖: Tracks direct tainted format receivers; custom sources, sanitizers and interprocedural aliases require data-flow analysis.
- **`da68e7896db811eea68ffa163e0fa374`** `partial` | detector: `python-ast-tokenize:G.EDV.08`
  - 规则: G.EDV.08 防止正则表达式引起的ReDos攻击
  - 覆盖: Parses literal regex structures for nested quantifiers; this is a review signal, not an exhaustive ReDoS complexity proof.
### 族 G.PSL（2 条）

- **`da69c6b86db811eea68ffa163e0fa374`** `partial` | detector: `python-ast-tokenize:G.PSL.02`
  - 规则: G.PSL.02 在datetime的使用过程中注意时区的影响，时区敏感的场景建议显式指定时区
  - 覆盖: Detects timezone-omitting datetime now/utcnow calls; deciding which business operations are timezone-sensitive needs context.
- **`da6c60396db811eea68ffa163e0fa374`** `partial` | detector: `python-ast-tokenize:G.PSL.03`
  - 规则: G.PSL.03 修改sys.path时注意避免模块重名问题
  - 覆盖: Reports sys.path mutations for collision review; actual runtime environment and installed modules are unavailable.
### 族 G.DSP（4 条）

- **`da6873496db811eea68ffa163e0fa374`** `partial` | detector: `python-ast-tokenize:G.DSP.02`
  - 规则: G.DSP.02 安全场景下必须使用密码学意义上的安全随机数
  - 覆盖: Flags random module generation as a review candidate; security-sensitive use and wrapper APIs require context.
- **`da683a2f6db811eea68ffa163e0fa374`** `partial` | detector: `python-ast-tokenize:G.DSP.03`
  - 规则: G.DSP.03 必须使用ssl.SSLSocket代替socket.Socket来进行安全数据交互
  - 覆盖: Reports raw socket construction; whether traffic is security-sensitive or subsequently TLS-wrapped requires context.
- **`da6919d06db811eea68ffa163e0fa374`** `manual` | detector: `None`
  - 规则: G.DSP.01 将敏感对象发送出信任区域前进行签名并加密
  - 覆盖: The export does not identify sensitive objects, trust boundaries, destinations or required signature/encryption schemes; these inputs must be supplied before a sound enforceable policy can be built.
- **`da6910066db811eea68ffa163e0fa374`** `partial` | detector: `python-ast-tokenize:G.DSP.04`
  - 规则: G.DSP.04 禁止在用户界面、日志中暴露不必要信息
  - 覆盖: Flags common sensitive names in direct logging/print calls; actual disclosure necessity and data classification require context.
### 族 G.TYP（2 条）

- **`da6b79156db811eea68ffa163e0fa374`** `partial` | detector: `python-ast-tokenize:G.TYP.01`
  - 规则: G.TYP.01 需要精确数值计算的场景，应使用decimal模块，且不要用浮点数构造Decimal
  - 覆盖: Detects Decimal construction from floating-point literals; identifying every precision-sensitive business operation requires context.
- **`da6b6eb56db811eea68ffa163e0fa374`** `partial` | detector: `python-ast-tokenize:G.TYP.07`
  - 规则: G.TYP.07 使用dict[key]获取 value 时需要注意保证 key 在有效的范围内
  - 覆盖: Detects missing literal keys in a preceding literal dictionary assignment; alias mutation, branch state and dynamic keys are not proven.
### 族 G.NAM（2 条）

- **`da6c6a446db811eea68ffa163e0fa374`** `manual` | detector: `None`
  - 规则: G.NAM.02 命名要有明确含义，以提升代码的可读性
  - 覆盖: Identifier meaning depends on business vocabulary and cannot be inferred reliably from the exported title; human/AI review must consult domain documentation.
- **`da6b5d0b6db811eea68ffa163e0fa374`** `partial` | detector: `python-ast-tokenize:G.NAM.04`
  - 规则: G.NAM.04 避免在无关的标识符或无关的概念之间重用名字， 避免因重名而导致的意外赋值和错误引用
  - 覆盖: Detects overwriting imported identifiers; deciding whether other reuse represents unrelated concepts requires human review.
### 族 G.VAR（2 条）

- **`da6b66266db811eea68ffa163e0fa374`** `partial` | detector: `python-ast-tokenize:G.VAR.01`
  - 规则: G.VAR.01 禁止在变量的生命周期内修改其类型
  - 覆盖: Checks successive inferable literal type assignments in lexical scopes; union types, reassignment across branches and aliases require type analysis.
- **`da6b52e36db811eea68ffa163e0fa374`** `partial` | detector: `python-ast-tokenize:G.VAR.03`
  - 规则: G.VAR.03 禁止覆盖外部作用域中的标识符
  - 覆盖: Detects direct shadowing of module bindings inside functions; nested closures, class semantics and intentional overrides need review.
### 族 G.CTL（2 条）

- **`da6b652d6db811eea68ffa163e0fa374`** `partial` | detector: `python-ast-tokenize:G.CTL.01`
  - 规则: G.CTL.01 同一个函数所有分支的返回值类型和个数保持一致
  - 覆盖: Compares explicit inferable return types and tuple arities; implicit fallthrough and dynamically computed types require control-flow/type analysis.
- **`da6b51ca6db811eea68ffa163e0fa374`** `partial` | detector: `python-ast-tokenize:G.CTL.03`
  - 规则: G.CTL.03 避免在条件/循环控制语句中包含过多的条件
  - 覆盖: Flags control conditions with more than five boolean leaves; exported rule provides no numeric complexity threshold.
### 族 G.FNM（2 条）

- **`da6b5b136db811eea68ffa163e0fa374`** `partial` | detector: `python-ast-tokenize:G.FNM.05`
  - 规则: G.FNM.05 当函数返回值个数较多时，建议通过class/namedtuple/dataclass等具名形式进行封装
  - 覆盖: Flags tuple returns above three elements as candidates; exported rule provides no threshold or grouping semantics.
- **`da6b47626db811eea68ffa163e0fa374`** `partial` | detector: `python-ast-tokenize:G.FNM.03`
  - 规则: G.FNM.03 当函数参数个数较多且有相关性时，建议通过class/namedtuple/dataclass等具名形式进行封装
  - 覆盖: Flags more than five explicit parameters as candidates; parameter relatedness and required grouping are semantic judgments.
### 族 G.ERR（3 条）

- **`da679cf46db811eea68ffa163e0fa374`** `partial` | detector: `python-ast-tokenize:G.ERR.07`
  - 规则: G.ERR.07 避免抑制或忽略异常
  - 覆盖: Detects empty/pass-only exception handlers; indirect suppression and intended recovery require control-flow/context analysis.
- **`da6757416db811eea68ffa163e0fa374`** `partial` | detector: `python-ast-tokenize:G.ERR.08`
  - 规则: G.ERR.08 禁止通过异常泄露敏感数据
  - 覆盖: Flags common sensitive identifiers/keys in raised exceptions; complete sensitivity classification requires business context.
- **`da6bd2f46db811eea68ffa163e0fa374`** `partial` | detector: `python-ast-tokenize:G.ERR.11`
  - 规则: G.ERR.11 避免使用SystemExit和sys.exit()，主进程入口中例外
  - 覆盖: Detects SystemExit/sys.exit outside explicit __main__ guards; packaged entrypoints and CLI framework callbacks require project configuration.
### 族 G.SER（1 条）

- **`da677e636db811eea68ffa163e0fa374`** `partial` | detector: `python-ast-tokenize:G.SER.02`
  - 规则: G.SER.02 禁止序列化未加密的敏感数据
  - 覆盖: Flags serialization of common sensitive identifiers/keys; sensitivity classification and encryption state require business semantics.
### 族 G.CLS（3 条）

- **`da6b485c6db811eea68ffa163e0fa374`** `partial` | detector: `python-ast-tokenize:G.CLS.07`
  - 规则: G.CLS.07 类的方法不需要访问实例时，建议定义为staticmethod或classmethod
  - 覆盖: Detects instance methods with no self access (including closures) or super call; override and decorator contracts need cross-module type context.
- **`da6babe46db811eea68ffa163e0fa374`** `partial` | detector: `python-ast-tokenize:G.CLS.11`
  - 规则: G.CLS.11 避免在类外或者子类中访问父类受保护的成员
  - 覆盖: Flags underscore-member access on non-self/cls receivers; inheritance, module privacy and documented friend APIs require type context.
- **`da6ba15c6db811eea68ffa163e0fa374`** `partial` | detector: `python-ast-tokenize:G.CLS.08`
  - 规则: G.CLS.08 避免在__init__方法外定义类实例属性
  - 覆盖: Compares self stores against __init__ declarations within a class; inherited/dataclass/descriptor-generated attributes require type context.
### 族 G.EXP（1 条）

- **`da6c55ea6db811eea68ffa163e0fa374`** `partial` | detector: `python-ast-tokenize:G.EXP.04`
  - 规则: G.EXP.04 推导式和生成器表达式仅用于简单的逻辑表达
  - 覆盖: Flags multi-generator/multi-filter comprehensions; rule simplicity has no exported numeric definition.
### 族 G.OPR（1 条）

- **`da674bb76db811eea68ffa163e0fa374`** `partial` | detector: `python-ast-tokenize:G.OPR.01`
  - 规则: G.OPR.01 对除法运算和模运算中的除数为0的情况做相应保护
  - 覆盖: Detects a constant zero divisor; input range proofs and protections require control-flow and interprocedural analysis.
### 族 G.FIO（2 条）

- **`da6738c36db811eea68ffa163e0fa374`** `partial` | detector: `python-ast-tokenize:G.FIO.01`
  - 规则: G.FIO.01 在多用户系统中创建文件时应根据需要指定合适的权限
  - 覆盖: Detects explicitly group/world-writable modes on known OS file APIs; effective umask, ACLs, deployment and intended sharing require review.
- **`da68dca06db811eea68ffa163e0fa374`** `partial` | detector: `python-ast-tokenize:G.FIO.02`
  - 规则: G.FIO.02 校验文件路径之前应该先对其进行规范化处理
  - 覆盖: Tracks direct external paths into existence/type checks and basic normalization; canonicalization order, symlinks and custom wrappers require data-flow review.
### 族 G.PRM（1 条）

- **`da68fcd26db811eea68ffa163e0fa374`** `partial` | detector: `python-ast-tokenize:G.PRM.03`
  - 规则: G.PRM.03 资源的申请和释放需要成对使用，包括正常和异常场景
  - 覆盖: Flags file acquisition outside with context management; balanced explicit cleanup, exceptional paths and other resource types require control-flow analysis.

## JavaScript（16 条）

### 族 G.MOD（1 条）

- **`da73d2ff6db811eea68ffa163e0fa374`** `partial` | detector: `typescript-ast:mutable-export`
  - 规则: G.MOD.01 需要导出的变量必须是不可变的类型
  - 覆盖: Detects reassignable exports and exported object/array literals. Deep immutability of arbitrary imported/user-defined types requires a project-specific immutability policy.
### 族 G.CTL（1 条）

- **`da73b3ab6db811eea68ffa163e0fa374`** `partial` | detector: `typescript-ast:many-conditions`
  - 规则: G.CTL.07 避免在条件/循环控制语句中包含过多的条件
  - 覆盖: Export does not define too many. Checks more than four boolean operands in a control condition.
### 族 G.TYP（3 条）

- **`da73ef3d6db811eea68ffa163e0fa374`** `partial` | detector: `typescript-ast:array-mutation-loop`
  - 规则: G.TYP.09 不要在数组遍历中对其进行元素的 remove/add 操作
  - 覆盖: Detects direct and resolvable array alias mutations in for-of, forEach and index loops, including mutating supplied-source function calls. Conditional reassignments, closures, external callees and complete path-sensitive effects remain unsupported.
- **`da73ee666db811eea68ffa163e0fa374`** `partial` | detector: `typescript-ast:array-traversal`
  - 规则: G.TYP.08 数组遍历优先使用 Array 对象方法
  - 覆盖: Detects typed array for-of traversal. Break/continue/async semantics may justify a loop; other equivalent traversal styles need review.
- **`da73e9b06db811eea68ffa163e0fa374`** `partial` | detector: `typescript-ast:float-equality`
  - 规则: G.TYP.03 浮点型数据判断相等不要直接使用== 或===
  - 覆盖: Detects equality against noninteger number literals and locally inferred fractional initializers. JavaScript numbers do not distinguish integers from floats statically; external values need context.
### 族 G.MET（1 条）

- **`da73d1726db811eea68ffa163e0fa374`** `partial` | detector: `typescript-ast:parameter-destructure`
  - 规则: G.MET.11 建议使用参数的解构
  - 覆盖: Advisory for parameters used through at least two direct property reads. Applicability and API compatibility require review.
### 族 G.WST（2 条）

- **`da73fa626db811eea68ffa163e0fa374`** `partial` | detector: `typescript-ast:persistent-storage`
  - 规则: G.WST.02 如果数据仅需要临时存储在客户端，使用非持久性会话cookie或者sessionStorage而不是localStorage
  - 覆盖: Reports localStorage writes for retention review. Whether data is temporary is an application requirement not present in source syntax.
- **`da73f9706db811eea68ffa163e0fa374`** `partial` | detector: `typescript-ast:sensitive-storage`
  - 规则: G.WST.01 禁止在 localStorage和sessionStorage中存储敏感数据
  - 覆盖: Checks storage keys/values with credential names. This is a security review candidate, not taint-flow proof.
### 族 G.WSQ（1 条）

- **`da73f8cb6db811eea68ffa163e0fa374`** `partial` | detector: `typescript-ast:sensitive-database`
  - 规则: G.WSQ.01 禁止在 Web SQL database和Indexed database数据库中存储敏感数据
  - 覆盖: Detects sensitive-name literals in direct SQL or IndexedDB put/add calls. No complete database taint tracking is claimed.
### 族 G.CORS（1 条）

- **`da73aca26db811eea68ffa163e0fa374`** `partial` | detector: `typescript-ast:postmessage-origin`
  - 规则: G.CORS.01 使用postMessage方法实现跨域时，应严格校验Origin
  - 覆盖: Checks missing or wildcard postMessage target origins. Incoming message origin verification and dynamically computed destinations need whole-program analysis.
### 族 G.CMT（1 条）

- **`da73a70d6db811eea68ffa163e0fa374`** `partial` | detector: `typescript-ast:comment-placement`
  - 规则: G.CMT.01 代码注释置于对应代码的上方或右边
  - 覆盖: Detects orphan trailing comments after the last statement. Association of arbitrary comments to intended code cannot be fully inferred.
### 族 G.OTH（3 条）

- **`da73e2a76db811eea68ffa163e0fa374`** `partial` | detector: `typescript-ast:personal-information`
  - 规则: G.OTH.04 正式发布的代码及注释内容不应包含开发者个人信息
  - 覆盖: Detects author tags and email-like personal contact strings in comments. Determining personal identity in arbitrary prose is not decidable from syntax alone.
- **`da73e0fd6db811eea68ffa163e0fa374`** `partial` | detector: `typescript-ast:weak-random`
  - 规则: G.OTH.01 安全场景下必须使用密码学意义上的安全随机数
  - 覆盖: Reports Math.random as a security review candidate; source syntax alone cannot prove use in a security-sensitive scenario.
- **`da73da1d6db811eea68ffa163e0fa374`** `partial` | detector: `typescript-ast:sensitive-output`
  - 规则: G.OTH.06 禁止在用户界面、日志中暴露不必要信息
  - 覆盖: Detects credential-named values sent to logging/UI sinks. Full sensitive-data taint tracking and necessity assessment are not implemented.
### 族 G.NOD（1 条）

- **`da73d92c6db811eea68ffa163e0fa374`** `partial` | detector: `typescript-ast:archive-extract`
  - 规则: G.NOD.04 解压文件必须进行安全检查
  - 覆盖: Reports archive extraction API calls for path/size/link review. It cannot prove prior validation or protect every extraction library.
### 族 G.NAM（1 条）

- **`da73d87c6db811eea68ffa163e0fa374`** `partial` | detector: `typescript-ast:filename`
  - 规则: G.NAM.07 使用统一的文件命名风格，文件扩展名应小写
  - 覆盖: Checks uppercase source extensions. Consistency of base filename styles is project-dependent; the export provides no selected naming convention.

## TypeScript（15 条）

### 族 非G族（15 条）

- **`da6bf13e6db811eea68ffa163e0fa374`** `partial` | detector: `typescript-ast:assigned-mutator`
  - 规则: 数组变异方法需谨慎使用
  - 覆盖: Detects sort/reverse results assigned to different bindings, including const aliases and assignment expressions; excludes assignment back to the same source array. Escaping state, reassigned aliases and nested expressions remain unsupported.
- **`da6bc7c46db811eea68ffa163e0fa374`** `partial` | detector: `typescript-ast:ignored-initial-value`
  - 规则: 不应忽略函数参数、捕获的异常和foreach变量的初始值
  - 覆盖: Tracks unread incoming parameter, catch and for-of binding values through bounded branch/return paths and reports their first overwrite. Accounts for arguments object/index reads while excluding arguments.length and nested function arguments. Complex loops, exceptions, closures and full path feasibility remain unsupported.
- **`da6bbc486db811eea68ffa163e0fa374`** `partial` | detector: `typescript-ast:void-output`
  - 规则: 不应使用不返回内容的函数的输出结果
  - 覆盖: Checks TypeScript-inferred void results in assignments, returns, arguments, object/array literals, templates, casts, awaits and conditional values. Discarded comma-left and callback expression results are excluded. Unknown external signatures and full expression paths remain unsupported.
- **`da6d6e3c6db811eea68ffa163e0fa374`** `partial` | detector: `typescript-ast:inverted-boolean`
  - 规则: 布尔检查不应反转
  - 覆盖: Detects negated if conditions with an else branch. Other forms of inversion and domain readability need review.
- **`da6b9ed86db811eea68ffa163e0fa374`** `partial` | detector: `typescript-ast:useless-increment`
  - 规则: 值不能做无用的递增或递减
  - 覆盖: Detects returning a postfix update of a local variable. Other dead increments need liveness and escape analysis.
- **`da6d62106db811eea68ffa163e0fa374`** `partial` | detector: `typescript-ast:argument-order`
  - 规则: 应按正确的顺序传递参数
  - 覆盖: Detects obvious permutations where call identifiers match a local resolved function signature parameter set. Positional semantics with different names require review.
- **`da6d3d336db811eea68ffa163e0fa374`** `partial` | detector: `typescript-ast:invariant-return`
  - 规则: 函数返回的值不应该是不变的
  - 覆盖: Uses structural completion analysis for reachable returns, const aliases, literal conditions, switch fallthrough, loops, throws and finally overrides. Dynamic predicates, implicit effects and values produced by calls remain unknown.
- **`da6b7ba96db811eea68ffa163e0fa374`** `partial` | detector: `typescript-ast:collection-overwrite`
  - 规则: 不应无条件替换集合元素
  - 覆盖: Detects constant-index writes to the iterated array from a for-of loop. Other collection types, indices and aliases need dataflow analysis.
- **`da6d33f06db811eea68ffa163e0fa374`** `partial` | detector: `typescript-ast:promise-try`
  - 规则: Promise rejections不应被'try'块捕获
  - 覆盖: Checks returned and discarded thenables inside lexical try bodies, follows const aliases and conditional/comma returns, and recognizes safe await/valid rejection handlers. Unknown thenables, handler side effects, interprocedural effects and arbitrary promise variables remain partial.
- **`da6d2a466db811eea68ffa163e0fa374`** `partial` | detector: `typescript-ast:empty-array-use`
  - 规则: 不应访问或迭代空集合
  - 覆盖: Detects reading or iterating an empty local array before a visible mutation/escape. Interprocedural mutations and arbitrary collection classes are outside this analysis.
- **`da6d17b26db811eea68ffa163e0fa374`** `partial` | detector: `eslint:no-constant-condition,@typescript-eslint/no-unnecessary-condition`
  - 规则: 条件不应总是计算为'true'或'false'
  - 覆盖: Checks type-proven constants and literal conditions. Arbitrary runtime/path-sensitive conditions beyond TypeScript narrowing are not proven.
- **`da6b55d06db811eea68ffa163e0fa374`** `partial` | detector: `typescript-ast:unused-collection`
  - 规则: 应使用集合和数组内容
  - 覆盖: Detects local array bindings whose only references write through mutators/indexes. Escapes, indirect references and custom collections are outside this analysis.
- **`da6b49c76db811eea68ffa163e0fa374`** `partial` | detector: `typescript-ast:accessor-field`
  - 规则: getters和setters应该访问预期的字段
  - 覆盖: Checks simple backing fields named name or _name for matching accessors. Delegated/computed accessors and unconventional field policies need review.
- **`da6cf3296db811eea68ffa163e0fa374`** `partial` | detector: `typescript-ast:hardcoded-credentials`
  - 规则: 凭证不应硬编码
  - 覆盖: Detects nonempty string literals bound to credential-word names using the exported credentialWords option. This is a security review candidate, not proof of a live credential.
- **`da6c32e46db811eea68ffa163e0fa374`** `partial` | detector: `eslint:no-self-compare`
  - 规则: 二进制运算符两侧不应使用相同表达式
  - 覆盖: ESLint comparisons plus pure identifier/literal arithmetic, logical and bitwise duplicate operands with parentheses unwrapped. Getter/property/call expressions and complete side-effect analysis remain excluded.
