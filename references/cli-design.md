# Huawei Code Review CLI 设计文档

## 1. 设计目标

本 CLI 面向四套用户导出的 CodeArts / 华为规范规则集，提供本地、确定性、目录驱动的代码审查：

- Java
- Python
- JavaScript
- TypeScript / 兼容 ArkTS 的前端源码

核心设计目标：

1. **规则保真，同时诚实呈现覆盖能力**
   - 只有存在明确检测器时才执行规则。
   - 区分 `implemented`、`partial`、`manual`、`unavailable`。
   - 不把“导入了规则”等同于“规则已完整自动化”。

2. **确定性证据**
   - JSON 是权威报告格式。
   - 每条 finding 包含路径、行号、列号、规则 ID、检测器、证据、覆盖状态和来源。
   - 支持导出 Markdown、SARIF 和 Excel。

3. **适配 CI 的退出码**
   - `0`：未达到失败阈值，且没有未经允许的覆盖缺口。
   - `1`：findings 达到配置的失败阈值。
   - `2`：分析不完整、必需工具失败、配置错误或运行时错误。

4. **允许项目策略，但不篡改导出规则**
   - 原始导出的数字 severity 保留为 `raw_severity`。
   - 本地 severity 是显式策略，可按规则覆盖。
   - 报告同时记录导出选项和有效选项。

5. **AI 只做补充，不替代确定性检测**
   - CLI 不会把 LLM 观点变成确定性覆盖。
   - partial / manual 规则会生成 review task，交给独立语义审查流程。

## 2. 非目标

本 CLI 不是：

- CodeArts 私有引擎的替代品；
- IDE；
- 构建系统；
- 完整的 taint / data-flow / 安全分析引擎；
- formatter 或 autofixer；
- 通用 AI 代码审查器。

具体边界：

- Java 不运行项目构建，也不运行注解处理器。
- Python 只解析源码，不 import、不执行模块。
- JS / TS 使用本地 parser / checker，但不安装依赖。
- 安全候选发现不等同于可利用漏洞证明。

## 3. 顶层架构

```text
CLI 入口
  -> 配置解析
  -> 规则目录 + 实现清单
  -> 语言分发
  -> 检测器 / 分析器
  -> 归一化 findings
  -> 覆盖状态和 review tasks
  -> 报告渲染
  -> 退出码
```

### 入口

| 命令 | 入口模块 |
|---|---|
| `huawei-code-review` | `scripts/check.py` |
| `python3 scripts/check.py` | 同一代码路径 |
| `huawei-code-review-compare` | `scripts/compare_reports.py` |

`pyproject.toml` 中导出这两个 CLI 命令。

## 4. 规则目录

导入的规则目录存放在：

```text
rulesets/catalog.json
```

每条规则身份包含：

- 稳定 rule ID；
- criterion-set ID；
- 组合 identity key；
- 语言；
- 规则标题，包含中文名；
- 导出的数字 severity；
- 导出选项；
- 来源 provenance。

规则目录被视为不可变输入。本地实现状态不写回原始规则目录。

## 5. 实现清单

每种语言都有实现清单：

```text
rulesets/implementations/java.json
rulesets/implementations/python.json
rulesets/implementations/javascript.json
rulesets/implementations/typescript.json
```

每条 manifest 记录：

- rule ID；
- implementation status；
- detector 名称；
- reason；
- test cases；
- 有效 options；
- 被覆盖时的导出 options。

允许的状态：

| 状态 | 含义 |
|---|---|
| `implemented` | 有文档、有测试的本地静态分析实现 |
| `partial` | 实现了明确子集，更广泛语义暂不支持 |
| `manual` | 需要人工或语义审查，不声称有确定性检测器 |
| `unavailable` | 没有可执行实现 |

没有 detector 证据和 test-case 引用的规则不能标记为 `implemented`。

## 6. 执行流程

### 6.1 输入发现

CLI 接受文件和目录。

前端支持扩展名：

- `.js`
- `.jsx`
- `.mjs`
- `.cjs`
- `.ts`
- `.tsx`
- `.mts`
- `.cts`
- `.ets`

后端支持扩展名：

- `.java`
- `.py`

扫描器可通过配置排除：

- `.git`
- `node_modules`
- `dist`
- build 输出
- 虚拟环境
- 其他指定路径

每个被扫描文件都会计算 SHA-256，并记录到 `input_files`。

### 6.2 规则选择

可以通过以下方式选择或禁用规则：

- rule ID；
- 组合 rule key；
- 语言；
- 项目配置；
- 重复 CLI 参数。

选择会做严格校验。未知 ID、未知 option、非法 value 都会返回退出码 `2`。

### 6.3 语言分发

`catalog_engine.py` 将每种语言映射到对应分析器模块：

| 语言 | 模块 |
|---|---|
| Java | `scripts/catalog_java.py` |
| Python | `scripts/catalog_python.py` |
| JavaScript | `scripts/catalog_frontend.py` |
| TypeScript | `scripts/catalog_frontend.py` |

前端模块通过显式 runtime 发现机制启动固定的 Node 分析器。

### 6.4 分析执行

每个分析器返回：

- findings；
- errors；
- engine / type-context 证据。

引擎会校验 findings：

- 必须引用被扫描源文件；
- 必须引用被选中的规则；
- 行号必须可用。

如果 finding 超出选择范围，会触发运行时错误，而不是静默进入报告。

### 6.5 Finding 归一化

所有语言都归一化为统一模型：

| 字段 | 含义 |
|---|---|
| `id` | 规则 ID |
| `rule_key` | 组合规则身份 |
| `path` | 源文件路径 |
| `line` | 1-based 行号 |
| `column` | 1-based 列号 |
| `language` | Java / Python / JavaScript / TypeScript |
| `severity` | 本地策略 severity |
| `raw_severity` | 原始导出数字 severity |
| `title` | 规则标题 |
| `message` | 检测器消息 |
| `evidence` | 截取的源码行 |
| `coverage_status` | `covered` / `candidate` / `error` / `opaque` |
| `implementation_status` | manifest 状态 |
| `detector` | 本地检测器标识 |
| `source` | 目录来源 |
| `fix` | autofix 元数据，目前默认不可自动修复 |

### 6.6 覆盖状态计算

对每条被选中的规则：

```text
implemented + 成功执行       -> covered
partial + 成功执行           -> candidate
分析器失败                   -> error
manual / unavailable         -> opaque
```

报告还会为所有 `partial` 或 `manual` 的被选规则生成 `review_tasks`。

如果某个语言没有可选规则，会记录 uncovered 条目。

### 6.7 报告渲染

支持格式：

- JSON：权威证据
- Markdown：人类可读报告
- SARIF：静态分析交换格式
- XLSX：工作簿报告

Excel sheet：

- Summary
- Findings
- Uncovered
- Rule Coverage

Excel 从同一个报告对象生成，不会重新扫描一次。

## 7. 语言分析器设计

### 7.1 Java

运行时：

- JDK 21
- `javac` parse-only 模式
- 本地 AST wrapper

输入：

- 提供的 Java 源码

能力：

- package / import 上下文；
- nested types；
- generic inheritance；
- erased override signatures；
- 注释和字面量遮蔽；
- 部分控制流和 completion 分析；
- 规则级 AST 检查。

限制：

- 不运行项目构建；
- 不运行 annotation processor；
- 不依赖项目 classpath；
- 不做完整 interprocedural data-flow；
- 不证明 Java memory-model 语义。

### 7.2 Python

运行时：

- Python 标准库
- `ast`
- `tokenize`

能力：

- 语法级规则；
- docstring 位置；
- 格式和空格；
- imports；
- 部分项目继承和方法签名分析；
- bounded control-flow facts；
- Python 3.11 标准库模型基线。

限制：

- 不 import 模块；
- 不执行模块；
- 不解析第三方依赖；
- 不做完整类型推导；
- 不检测目标运行时版本；
- 不做完整 call graph / alias / data-flow 证明。

### 7.3 JavaScript / TypeScript

运行时：

- Node.js
- 固定的本地 `node_modules`
- TypeScript compiler API
- typescript-eslint parser / plugin

能力：

- ESLint core 规则映射；
- TypeScript AST 检查；
- 跨文件 symbol identity；
- 部分返回类型检查；
- bounded Promise 和 completion 分析；
- JSX 支持。

限制：

- 外部类型可能无法解析；
- strictness 依赖提供的项目配置；
- 不做完整 path-sensitive data-flow；
- 不建模任意框架；
- 安全敏感规则在上下文未证明前保持候选状态。

环境变量：

- `HCR_NODE`
- `HCR_NODE_MODULES`

## 8. 外部 adapter

CLI 可以运行可选外部工具：

- ESLint
- Ruff
- Flake8
- Checkstyle
- `tsc`

adapter 状态显式记录：

- `ok`
- `missing`
- `timeout`
- `error`
- `skipped`

必需但缺失或失败的 adapter 会产生 uncovered coverage 和退出码 `2`。

外部工具 findings 保留 `external-tool` provenance。

## 9. 配置设计

配置格式：

- TOML
- JSON

常见字段：

- ruleset
- language
- fail-on 阈值
- enabled / disabled rules
- excludes
- tool 选择
- tool path
- tool args
- tool timeout
- rule options
- severity override

规则 option 必须使用导出的 option 名称。未知 option 或非法 value 会导致运行失败。

报告区分：

- `options`：实际生效值；
- `exported_options`：不可变的原始导出值。

## 10. 退出码契约

| 退出码 | 含义 |
|---:|---|
| `0` | 未达到阈值失败，且没有未经允许的覆盖缺口 |
| `1` | findings 达到选定的 fail-on 阈值 |
| `2` | 分析不完整、必需工具失败、配置错误、解析或运行失败 |

`--allow-uncovered` 可以改变阈值行为，但不会改变 `coverage_summary.complete`。

## 11. Provenance 和 severity 策略

CLI 分离以下概念：

1. 导出的规则来源；
2. 导出的数字 severity；
3. 本地 severity；
4. 本地实现状态；
5. 执行状态；
6. finding 判断状态。

默认策略是保留原始导出 severity，但不猜测其含义。本地 severity override 是显式项目策略，并记录在报告中。

## 12. Skill 编排设计

Skill 使用 CLI 作为确定性扫描器。

推荐流程：

1. 查看规则清单；
2. 保存不可变的 `before.json`；
3. 读取 findings、coverage 和 uncovered；
4. 从同一份 JSON 生成 Excel；
5. 进行源码审查；
6. 可选写入 `semantic-review.json`；
7. 如果用户要求修复，先写 repair plan；
8. 执行有边界的源码修改；
9. 运行项目测试；
10. 以相同 scope / options 重扫；
11. 比较 `before.json` 和 `after.json`。

LLM 语义审查单独存储，不能：

- 删除确定性 finding；
- 修改 implementation status；
- 升级 coverage；
- 改变 CLI 退出码语义。

## 13. 测试策略

每个可执行规则应有：

- 正例；
- 反例；
- 必要时的边界用例。

测试套件覆盖：

- 规则行为；
- CLI 行为；
- 配置；
- 报告 schema；
- adapter 行为;
- compare 行为；
- 真实项目回归。

当前验证记录：

- 299 个测试；
- 1 个跳过；
- JS / Java / Python 真实项目扫描。

Fixture 测试和真实项目运行是不同类型的证据。二者都不能单独证明普适 precision 或 recall。

## 14. 已知限制

1. 不等同于 CodeArts 私有引擎。
2. partial 规则只覆盖其声明范围内的子集。
3. 安全候选需要项目和信任边界上下文。
4. 跨文件和 interprocedural 分析是有边界的。
5. Java 是 parse-only。
6. Python 是 parse-only，不解析依赖。
7. 前端类型分析依赖提供的源码和配置。
8. 外部 adapter 行为依赖已安装的工具版本。
9. 规则 option 只支持导出且实现的 option 名称。
10. 当前 catalog 检测器不提供可信 autofixer。

## 15. 未来设计方向

可能的扩展：

- 更广泛的 interprocedural 项目上下文；
- taint / alias summary；
- framework-specific model；
- sanitizer / validator 库；
- 机器可读 rule-policy profile；
- 带有安全性测试的 repair suggestion；
- 更完整的 semantic-review 工作流；
- 增量扫描和缓存；
- 项目级 baseline suppression。

任何未来状态升级仍需要满足：

1. 确定性检测器；
2. 正例 / 反例测试；
3. manifest reason 更新；
4. 全量测试重跑；
5. 必要时进行真实项目验证。
