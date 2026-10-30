# 0.4.0 覆盖率与真实项目验收

## 2026-10-30 当前覆盖快照

本节记录当前工作树的规则状态；下文保留 0.4.0 发布时的历史验收证据。

| 语言 | 规则总数 | implemented | partial | manual |
|---|---:|---:|---:|---:|
| Java | 181 | 89 | 91 | 1 |
| Python | 127 | 92 | 33 | 2 |
| JavaScript | 95 | 79 | 16 | 0 |
| TypeScript | 66 | 51 | 15 | 0 |
| **合计** | **469** | **311** | **155** | **3** |

当前源码树验证：`python3 -m unittest discover -s tests -q` 通过 **299** 个测试，**1** 个跳过。逐条未完全实现说明见 [IMPLEMENTATION_GAPS.md](IMPLEMENTATION_GAPS.md) 和 [PARTIAL_RULES.md](PARTIAL_RULES.md)。这些状态仍表示本地静态分析实现，不等同于 CodeArts 私有引擎语义。

验证日期：2026-10-14。CLI 已构建为 0.4.0、安装到干净 Python 3.11 虚拟环境，并从源码树外完成真实项目扫描。469 条导入规则已经有明确的本地实现状态，但这不表示与私有 CodeArts 引擎语义等价，也不表示没有漏报。

## 规则状态

| 语言 | 原规则 | implemented | partial | manual |
|---|---:|---:|---:|---:|
| Java | 181 | 63 | 117 | 1 |
| Python | 127 | 40 | 85 | 2 |
| JavaScript | 95 | 62 | 33 | 0 |
| TypeScript | 66 | 43 | 23 | 0 |
| **合计** | **469** | **208** | **258** | **3** |

`implemented` 表示已实现并有规则级测试证据的本地静态检测子集；`partial` 表示只覆盖规则明确列出的可判定子集，无法证明完整语义；`manual` 需要业务或人工判断。当前没有 `unavailable` 规则。逐条状态、检测器、测试引用、原始严重性和限制见[规则清单 JSON](../reports/control-flow-2026-10-14-final/rule-inventory.json)与[规则清单 Excel](../reports/control-flow-2026-10-14-final/rule-inventory.xlsx)。

本轮重点包括：Java 结构化 completion、常量/异常/资源边界；Python 3.11 固定标准库继承、成员和签名模型，以及跨文件项目上下文；JavaScript/TypeScript 的 `finally`、循环/标签、`switch`、返回路径、Promise/await 和拒绝处理；作用域分析错误及受影响规则 ID；规则生成器状态和测试引用的完整性。Python 标准库模型不会导入或执行被扫描项目，目标运行时版本也不会自动探测。

## 测试、语法和安装证据

- [主测试日志](../reports/control-flow-2026-10-14-final/unit-tests.log)：287 个 `unittest` 方法通过，68.889 秒，无 skip。
- [适配器测试日志](../reports/control-flow-2026-10-14-final/adapter-tests.log)：12 个方法通过，无 skip。两套测试合计 **299 个测试方法**。
- [实际测试命令和退出码](../reports/control-flow-2026-10-14-final/test-commands.json)记录了命令、工作目录和运行时。
- Python `compileall`、4 个前端 Node `--check`、JDK 21 `javac` 资产编译和 Skill `quick_validate.py` 均通过；详见[语法与 Skill 校验](../reports/control-flow-2026-10-14-final/syntax-and-skill-checks.json)及[Skill 日志](../reports/control-flow-2026-10-14-final/skill-validation.log)。
- 0.4.0 wheel 在干净虚拟环境中离线构建、安装和运行 `--version`，安装后的 35 个运行时资产与当前源码逐一比对；详见[打包校验](../reports/control-flow-2026-10-14-final/packaging-verification.json)、[安装日志](../reports/control-flow-2026-10-14-final/install.log)和[资产日志](../reports/control-flow-2026-10-14-final/installed-assets.log)。

## 真实项目扫描

所有目标文件扫描前后 SHA-256 一致，扫描器没有改动或执行目标项目代码。最终范围合计 **238 个源码文件**。所有扫描退出码均为 2，因为仍存在 partial/manual 覆盖或外部上下文缺失；退出 2 表示证据不完整，不等于“没有告警”。

| 项目 | 语言 | 文件 | 告警/候选 | 分析错误 | 选中规则 | implemented / partial / manual | 退出码 |
|---|---|---:|---:|---:|---:|---:|---:|
| agentcontest-java | Java | 78 | 560 | 0 | 181 | 63 / 117 / 1 | 2 |
| requests-python 2.34.2 | Python | 19 | 331 | 17 | 127 | 40 / 85 / 2 | 2 |
| eslint 10.8.0（lib/linter） | JavaScript | 20 | 7,224 | 26 | 95 | 62 / 33 / 0 | 2 |
| Vue 3.5.13（runtime-core/reactivity/shared） | TypeScript | 93 | 1,312 | 2 | 66 | 43 / 23 / 0 | 2 |
| corecompetition | Python | 27 | 1,812 | 0 | 127 | 40 / 85 / 2 | 2 |
| ms 2.1.3 | JavaScript | 1 | 50 | 0 | 95 | 62 / 33 / 0 | 2 |

每个项目均有[JSON 和 Excel 报告](../reports/control-flow-2026-10-14-final/)。命令、源码范围、版本/路径来源、SHA-256、退出码和分析错误见[运行记录](../reports/control-flow-2026-10-14-final/run.json)、[项目范围](../reports/control-flow-2026-10-14-final/projects.json)和[扫描日志](../reports/control-flow-2026-10-14-final/project-scans.log)。

分析错误是缺少可解析的外部类型或异常上下文，不应被当作项目缺陷；例如 Requests 仍有 17 个依赖上下文错误，Vue 缺少部分 Node、Puppeteer 和 Vitest 全局类型，ESLint 的范围也只包含 `lib/linter`。Requests 新增的 7 个 `G.CLS.02` 候选已做静态签名审阅，确认 0 个应用 bug；详情见[审阅记录](../reports/control-flow-2026-10-14-final/requests-findings-review.json)。

## Excel 与修复闭环

[独立 openpyxl 校验](../reports/control-flow-2026-10-14-final/excel-independent-validation.json)打开并验证了 9 个工作簿：6 个项目报告、1 个规则清单和修复演练的 before/after。每个工作簿均有 `Summary`、`Findings`、`Uncovered`、`Rule Coverage` 四个工作表，发现数、规则覆盖行、状态、受影响规则 ID 与对应 JSON 一致，无公式依赖。

[修复演练](../reports/control-flow-2026-10-14-final/repair-smoke/run.json)使用安装后的实际 CLI 检查一个可变默认参数示例：行为测试在修复前失败，修复后通过并保留调用方列表身份；同范围复扫得到 1 条 `resolved`、0 条 `unverified_resolutions`。[差异与汇总](../reports/control-flow-2026-10-14-final/repair-smoke/delta.json)只证明该演练的扫描闭环，不是任意项目的 AI 自主修复成功率。

## 限制与后续工作

258 条 partial 仍涉及外部类路径/框架模型、完整控制流、跨过程污点分析、动态绑定、项目策略和阈值语义；3 条 manual 需要业务判断。真实项目候选尚未逐条人工标注，因此当前没有系统化查准率/查全率结论。改变规则选择、阈值、源码范围、伴随文件或分析器指纹，不能作为已验证修复；比较前后报告必须保持这些条件一致。

JSON 是规范证据，Excel 是从同一份 JSON 导出的审阅视图。报告目录中若存在 2026-10-13 的旧快照，以本目录的 0.4.0 结果为准；旧快照仅作为历史记录保留。
