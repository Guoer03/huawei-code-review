# Sanitizer 识别与源扩充补充（2026-10-15）

本次给 Java taint 检测器与 Python shell 通配符检测器做三项覆盖补充，闭合 `validation/COVERAGE.md` 与 manifest `reason` 中点名的缺口。这是 0.4.0 之后的覆盖补充，不升版本号、不改 `status`（规则仍为 partial）。

## 改动一：sink 作用域 sanitizer 识别（精度↑）

- 在保持原 flat-walk 过程内污点传播**逐字节不变**的前提下，新增独立的 `is_sanitized` 抑制层：tainted 参数若经过对应该 sink 类别的公认编码/转义函数，则不再报告该 sink。
- sanitizer 集保守且 sink 作用域化（避免 "URLEncoder 保护 XPath" 类假阴性）：
  - `StringEscapeUtils.escapeHtml*/escapeXml*`、ESAPI `encodeForHTML/HTMLAttribute/encodeForXML/...` → `taint_xss`、`taint_xml_concat`
  - `URLEncoder.encode`、`response.encodeRedirectURL` → `taint_redirect`；`URLEncoder.encode`、`response.encodeURL` → `taint_header`
- 仅识别 binding 的**直接 sanitizer 调用 initializer**；别名不传播，重赋值为非 sanitizer 会清除中和（避免陈旧中和的假阴性）。`taint_path` 等其余 12 条 taint 规则本轮不引入 sanitizer（无公认编码中和函数）。

## 受影响规则（4 条，status 仍 partial，仅 reason 与 test_cases 更新）

| 规则 | detector | 新增 sanitizer |
|---|---|---|
| da76fab3 | taint_xss | escapeHtml/escapeXml, ESAPI encodeForHTML |
| da5dc9f7 | taint_redirect | URLEncoder.encode, response.encodeRedirectURL |
| da7726f8 | taint_header | URLEncoder.encode, response.encodeURL |
| da5ff9c5 | taint_xml_concat | escapeXml, ESAPI encodeForXML |

## 测试

- `tests/catalog_cases/java.json`：新增 4 条 `*_sanitized` 用例（bad 直接污染→报；good 经 sanitizer→不报）。
- `tests/test_catalog_java.py`：新增两个不变式测试——`test_sanitizer_is_sink_scoped_not_global`（escapeHtml 不中和 taint_path）、`test_reassignment_to_non_sanitizer_clears_neutralization`（重赋值清除）。
- 单测 289（+2）/ 适配器 12 全绿；repair-smoke 仍 1 resolved / 0 unverified；`compileall` 通过。

## 真实项目无回归证据

以 `reports/control-flow-2026-10-14-final/agentcontest-java.json`（0.4.0 基线）为 before，同范围同选项用新代码复扫为 after：

- finding 总数：560 → 560（[agentcontest-java-after.json](agentcontest-java-after.json)）。
- `huawei-code-review-compare` 结果（[agentcontest-delta.json](agentcontest-delta.json)）：`resolved=0, new=0, unchanged=560, unverified_resolutions=0`。

agentcontest-java 在这 4 条 sink 上基线即为 0 命中，故本次补充对其无可观察的 finding 变化；精度提升由上述单测的 sanitized 用例证明，无回归由本复扫证明。`taint_path` 的 8 条与 `taint_log` 的 3 条 finding 在前后保持完全一致（消息文案未改）。

## 改动二：外部输入源扩充（召回↑）

同一检测器的 `sources` 集从 7 个扩到 11 个，补回明显用户可控却被遗漏的请求输入入口：

- 新增 `getParameterMap`、`getPathInfo`、`getRequestURI`、`getRequestURL`、`getRequestedSessionId`。
- 保守**不加** `getRemoteAddr`/`getRemoteUser`/`getRemoteHost` 等网络元数据：正常访问日志会记录这些，作为源会大面积误报。

纯加法，无假阴性风险；与 sanitizer 识别互补（一个提精度、一个提召回）。reason 文本"common servlet/environment sources"已涵盖扩充后的集合，故 manifest 无需改动。

### 测试

- `tests/catalog_cases/java.json` 新增 3 条源用例：`taint_path_pathinfo_source`、`taint_redirect_requesturi_source`、`taint_xss_requesturl_source`（bad 报、good 字面量不报）。
- 单测 289 / 适配器 12 全绿；`compileall` 通过。

### 真实项目证据

agentcontest-java 复扫（[agentcontest-java-after-sources.json](agentcontest-java-after-sources.json)）：finding 总数 560 → 560，delta=0。该项目不以上述新源到达敏感 sink，故无可观察变化；召回提升由单测证明，无回归由复扫证明。

## 改动三：Python shell 通配符组装命令识别（召回↑）

`G.EDV.03`（`scripts/catalog_python.py`）原先只在命令是**完整字面字符串**且含通配符时命中；半字面组装命令（如 `subprocess.run("ls *.txt " + name, shell=True)`、f-string、`.format()`）因 `ast.literal_eval` 对含 Name 的 BinOp 失败而漏报。

新增模块级 `wildcard_fragments(node)`：在 BinOp(+) / JoinedStr / `str.format` 的**组装结构**里定向收集字面字符串片段（不下降进任意 helper 调用，避免把 `get_cmd("*.txt")` 这类参数里的字面量误算）。任一片段含通配符，则组装后的 shell 命令必含该通配符 → 命中。完整字面命令分支逐字节不变，故既有 finding 不受影响（纯加法）。

### 测试

- `tests/catalog_cases/python.json` 新增 5 条用例：`assembled_concat`（positive/negative）、`assembled_fstring:positive`、`assembled_format:positive`、`helper_arg_not_overreached:negative`（证明不误把 helper 调用参数算入）。
- manifest `reason` 更新为记录组装命令的字面片段识别；`status` 仍 partial；test_cases 补 5 条。
- 单测 289 / 适配器 12 / compileall 通过；`test_rule_examples` 逐条断言 5 条新用例行为正确。

### 真实项目证据与环境噪声说明

requests-python 复扫（[requests-python-after.json](requests-python-after.json)）：`G.EDV.03` finding 0 → 0（该项目无此模式，无可观察召回变化）。复扫相对基线多出 3 条 `G.FMT.04:分隔符` finding，经**临时回退本改动后复扫**验证仍为 +3，故判定为扫描环境噪声（本地 `python3` 与基线安装版 0.4.0 wheel 所在 venv 的 Python 版本/tokenizer 差异），**非本次改动所致**；本改动对 `G.FMT.04` 代码路径零触及。召回提升由上述 5 条单测用例证明。

## 限制（保留）

Java taint：过程间传播、path-sensitive、框架类型归因仍超出范围；partial-arg 混合会被整体抑制；别名链不传播 sanitizer 中和。Python G.EDV.03：非字面变量内容与 helper 调用结果仍需数据流分析。逐条状态与限制见 `validation/COVERAGE.md` 与 `--list-rules`。
