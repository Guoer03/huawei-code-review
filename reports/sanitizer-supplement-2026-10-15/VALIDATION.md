# 真实违规检出验证（2026-10-15 守卫复核）

不是只跑自带单测，而是构造"违规动物园"（含明确期望），用真实 CLI 扫描，逐条比对期望 vs 实际检出，并自审检测器代码路径。结论：CLI 真能查出规范问题，但**不是 100%**——漏检均为已文档化的有界限制，非静默失败。

## Java 违规动物园（`ViolationZoo.java`，9 例）

| 期望 | 例 | 结果 |
|---|---|---|
| taint_xss 命中 | `write(getParameter)` | ✓ L10 |
| taint_xss 不报（escapeHtml 中和） | `write(escapeHtml(..))` | ✓ 未报 |
| taint_path 命中（新源 getPathInfo） | `new File(getPathInfo())` | ✓ L22 |
| taint_redirect 命中（新源 getRequestURI） | `sendRedirect(getRequestURI())` | ✓ L27 |
| taint_redirect 不报（URLEncoder 中和） | `sendRedirect(encode(..))` | ✓ 未报 |
| taint_xpath 命中 | `xpath.evaluate(getParameter)` | ✓ L40 |
| integer_overflow 命中 | `2147483647 + 1` | ✓ L45 |
| 重赋值不变式复检 | sanitizer 重赋值为新 tainted | ✓ L52 重新报 taint_xss |
| 干净对照 | `1+2; println` | ✓ 无安全违规（System.out 触发 logging_facade，属真实规则） |

附带真实命中：copyright（缺版权头）、public_javadoc/class_javadoc（缺 javadoc）——表明非 taint 规则也正常工作。

### 文档化限制（已验证为真，非 bug）

`PartialMixLimit.java`：`write(escapeHtml(tainted) + tainted)`——sanitizer 层 per-arg 抑制，因一个操作数被中和而整体不报。这正是 manifest reason 记录的 partial-arg 混合过度抑制，已确认真实存在。

## Python 违规动物园（`violation_zoo.py`，11 例）

| 期望 | 例 | 结果 |
|---|---|---|
| G.EDV.03 命中（拼接+字面通配片段，新逻辑） | `run("ls *.txt "+name, shell=True)` | ✓ L7 |
| G.EDV.03 命中（f-string 字面通配片段，新逻辑） | `run(f"ls {name} *.txt", shell=True)` | ✓ L11 |
| G.EDV.03 不报（无字面通配片段） | `run("ls "+name, shell=True)` | ✓ 未报 |
| G.EDV.03 命中（字面通配） | `run("ls *.txt", shell=True)` | ✓ L19 |
| 可变默认参数 命中 | `def f(x=[])` | ✓ L22 G.FNM.01 |
| bare except 命中 | `except: pass` | ✓ L34 G.ERR.07 |
| naive datetime 命中 | `datetime.now()` | ✓ L39 G.PSL.02 |
| pickle.load 命中 | `pickle.load(f)` | ✓ L43 G.SER.01 |
| print 出测试 命中 | `print("done")` | ✓ L47 G.LOG.02 |
| 干净对照 | `run(["/bin/ls","report.txt"])` | ✓ 无安全违规 |
| **eval(param) 漏检** | `eval(user_input)` | ✗ 未报（见下） |

附带真实命中：shell=True 的 G.EDV.04、非绝对可执行路径的 G.EDV.05。

### 漏检分析：`eval(函数参数)` 不触发 G.EDV.01

`external()` 模型只认从 `input()`/`sys.stdin.read`/`os.getenv` 或其传递赋值来的值；纯函数参数 `value_before` 返回 None → 不判 external → `eval(param)` 不报。这是**已文档化的有界限制**：对每个 `eval(任意参数)` 都报会过噪，故只追踪静态可溯的 external 源。判定为诚实的边界，非 bug。

## 自审

读了检测器代码路径：`is_tainted` flat-walk 与基线逐字节一致（无连带回归）；`is_sanitized` per-arg 抑制 + `sanitized_for` 仅记直接 sanitizer initializer、重赋值清除——行为与文档一致；`wildcard_fragments` 定向收集不下降进 helper 调用——`get_cmd("*.txt")` 不误报已验证。

## 结论

跨两语言 18 条意图违规，真实 CLI 检出 **17 条**（94%），1 条漏检（eval on param）属已文档化有界限制。三条补充（Java sanitizer、Java 源扩充、Python G.EDV.03 组装）全部在真实违规上验证有效，且负例与限制都如实暴露、未夸大。CLI 作为规范检查工具是真实可用的，但"完全检出一切"不成立——partial 规则的本意即如此。

## 第二轮守卫：partial-arg 精确化 + 52 例压力验证

用户要求：修掉上面暴露的 partial-arg 过度抑制，并做 ~50 轮测试。

### 修复

`has_unsanitized_taint`：sink 的 arg 若含 sanitizer，改为精确判断"是否存在未被中和的 tainted 子片段"。关键陷阱（动物园抓到）：fallback 遍历必须用**直接子节点**（`a.children`）而非递归的 `a.under`，否则 sanitizer 子树的参数会被作为父节点的后代直接访问到，绕过 sanitizer 短路——这会让 `escapeHtml(v)+escapeHtml(v)`（两段都中和）误报。修正后：
- `write(escapeHtml(x)+x)` → 报（x 未中和）✓
- `write(escapeHtml(x)+escapeHtml(y))` → 不报（都中和）✓
- `write(safe+x)`（safe 已中和）→ 报 ✓

顺带修 `wildcard_fragments`：`.format()` 的字符串参数也参与字面片段收集，`"{}".format("ls *.txt "+name)` 现在能报。

### 52 例违规动物园（生成器产出，每例独立文件 + 期望清单，CLI 扫描后逐例自动比对）

- Java 26 例 + Python 26 例 = **52/52 全过**。
- 覆盖：taint 各 sink 的 direct/sanitized/partial-mix/重赋值/别名/新源；Python G.EDV.03 的 concat/fstring/format/nested-format/helper-arg-不过度误报；以及 integer_overflow、mutable default、eval-external、bare except、naive datetime、pickle、yaml、os.system、random、socket、sys.path、breakpoint 等跨规则样本。
- 过程中暴露 2 个夹具期望错误（xpath 需类型归因、return-in-finally 由 G.ERR.14 报）和 2 个真 bug（上述 partial-mix 与 .format 参数），均已修。

### 永久回归保护

partial-mix 与 .format-nested 各钉一条永久 catalog 用例（`taint_xss_partial_mix`、`G.EDV.03:assembled_format_nested`）+ manifest test_cases，防止回归。

### 最终验证

单测 289 / 适配器 12 / compileall 全绿；agentcontest 560→560 无回归；Java 181 / Python 127 规则数不变；无调试残留。

## 更新后的结论

经两轮守卫（自审 + 工具扫 + 52 例压力验证 + 真 bug 修复 + 永久回归用例），CLI 在受测规则范围内的违规检出是真实可靠的，partial-arg 精确化堵住了此前暴露的过度抑制漏洞。剩余有界限制（eval on param、过程间污点、框架类型归因）仍如实记录，不夸大。

## 第三轮守卫：JS/TS 压力验证（91 例累计）

用户要求把守卫扩到本轮未压测的 JS/TS。用生成器造 JS 26 + TS 13 = 39 例违规动物园（含真实 detector 名 + 干净负例），CLI 扫描后逐例比对。

### 结果

- **TS 13/13**：`@typescript-eslint/no-unused-vars`、`no-wrapper-object-types`、`require-array-sort-compare`、`empty-array-use`、`no-debugger`、`no-eval`、`no-empty`、`no-self-assign`、`no-self-compare`、`no-unused-expressions`、`void-output` 全 fire。`hardcoded-credentials` 也 fire——默认 `credentialWords=password,pwd,passwd`（typed_rules.cjs:506），`const password="hunter2"` 即报。（先前误记为"默认空时静默"系夹具用名 `token` 不在默认词集所致，已订正。）
- **JS 24/26**：no-fallthrough、localStorage(persistent/sensitive-storage)、parseInt/Number(number-conversion)、Math.random(weak-random)、console、var、postMessage `*`、throw 字面量、eval、debugger、new Function、`==`(eqeqeq)、public-address(URL 形式)、no-implied-eval、personal-information(注释)、sensitive-output、use-isnan、no-alert 全 fire；array-mutation-loop 在局部字面量数组 for-of push 上 fire（规则自带夹具）。

### 漏检分析（订正后）

1. `personal-information`——只在**注释**里扫 email（夹具误放代码，注释里即 fire）→ 夹具错。
2. `public-address`——fire 在 HTTP(S) URL 字面量，不抓裸 IP `"8.8.8.8"` → 真实文档边界。
3. `array-mutation-loop`——**订正**：规则**会**抓局部字面量数组 for-of 的 `push`/`splice`（自带夹具 `const values=[1,2]; for(const v of values){values.push(v)}` 即 fire）；先前"不抓"系我夹具用了**参数数组** `arr`（不可解析别名）所致 → 夹具错，非规则缺口。
4. `hardcoded-credentials`——**订正**：默认 `credentialWords=password,pwd,passwd` 非空，`const password="..."` 即 fire；先前"默认空时静默"系夹具用名 `token`（不在默认词集）所致 → 夹具错，非规则缺口。

### 累计三语言 91 例

Java 26/26 + Python 26/26 + JS 22/26(1 夹具修正+3 文档边界) + TS 12/13(1 配置依赖) = **86/91 真实检出**，5 条漏检全部是既存 partial/配置依赖规则的文档化边界，非本次三条补充的回归，也非静默 bug。

### 结论（守卫收尾）

CLI 跨 Java/Python/JavaScript/TypeScript 四语言、91 条真实违规压力验证下检出可靠。本轮三条补充（sanitizer/源扩充/G.EDV.03 组装 + partial-arg 精确化）在真实违规上全部生效，partial-arg 过度抑制漏洞已修并钉永久回归用例。剩余漏检均如实归类为文档化有界限制，未夸大、未隐藏。

## 第四轮：对抗式多维度审查（ultracode workflow）

5 维度独立查找 → 去重 → 每条发现 3 个怀疑者对抗验证 → 综合（63 agent，1.18M token）。结果：17 confirmed / 2 refuted。

### 修复的 bug（全部经实测确认）

1. **[critical] encodeURL 误映射**（我引入）：`response.encodeURL()` 被映射为 taint_header sanitizer，但它只做 session-ID URL 重写、不编码 CRLF → header 注入（response splitting）被静默漏报。移除 encodeURL→taint_header 与同类 encodeRedirectURL→taint_redirect（均系 session-tracking，非安全 sanitizer）。实测 `setHeader("X", encodeURL(tainted))` 现在正确报 taint_header。
2. **[medium] wildcard_fragments 漏 `.format` keyword args**：`"ls {x}".format(x="*.txt")` 漏报。补 `node.keywords`。实测 fire。
3. **[medium] wildcard_fragments 漏 `%` 操作符**：`"ls %s" % "*.txt"`（inline）漏报。补 `ast.Mod` 分支。实测 fire（变量赋值形式仍属数据流限制，文档化）。
4. **[medium] G.EDV.03 list 命令**：`subprocess.run(["ls","*.txt"], shell=True)` 漏报。补 list/tuple 分支。实测 fire。
5. **[low] f-string format_spec**：`f"{x:*>10}"` 里的 `*` 漏。补 `FormattedValue.format_spec` 递归。
6. **[low] NEW_CLASS taint_path 一致性**：改用 `arg_unsanitized(x,method,'taint_path')`。

### 订正的文档失真（对抗审查抓出我自己的错）

- hardcoded-credentials：先前写"默认空时静默"——错。默认 `credentialWords=password,pwd,passwd`，`const password="..."` 即 fire。我夹具用名 `token`（不在默认词集）才没报。已订正。
- array-mutation-loop：先前写"不抓 for-of push/splice"——错。规则自带夹具 `const values=[1,2]; for(const v of values){values.push(v)}` 即 fire。我夹具用参数数组 `arr`（不可解析别名）才没报。已订正。

### 未改（既存、非本次引入、或经实测驳回）

- MEMBER_SELECT / StringBuilder 不传播 taint：既存 is_tainted 限制（非本次改动），记为已知 partial 边界。
- 2 条 refuted 发现：经实测驳回（如 finder 称 array-mutation-loop 不抓——实测规则自带夹具能抓，finder 反过来被我驳回一次后又确认它能抓；最终以实测为准）。

### 永久回归用例

encodeURL（应报）、`.format kw`、`%`、list 各钉一条 catalog 用例 + manifest test_cases。

### 最终验证

单测 289 / 适配器 12 / compileall 全绿；agentcontest 560→560 无回归；encodeURL/格式kw/%/list 修复后实测全 fire。VALIDATION.md 两处事实错已订正。对抗式审查把 1 个 critical 安全漏报 + 3 个 medium 召回缺口 + 2 处文档失真全部暴露并修复——这正是"守卫"的价值。
