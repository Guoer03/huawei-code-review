# 未完整实现规则与补齐信息清单

生成日期：2026-10-19。数据来自当前源码执行 `python3 scripts/check.py --list-rules --format json`，CLI 版本为 `0.4.0`。本报告把“未完整实现”定义为 `partial` 或 `manual`。

## 口径

- `implemented`：本地静态分析器可执行、manifest 有检测器与正反例、边界已写明。它不是 proprietary CodeArts 引擎等价证明。
- `partial`：本地检测器只覆盖 reason 中明确声明的子集，结果可作为审阅线索，不能当作完整语义证明。
- `manual`：缺少业务、架构或安全上下文，当前只生成人工审阅任务。

## 结论

- 导入规则总数：**469**
- 本地已实现：**311**
- 未完整实现：**158**
  - `partial`：**155**，已有可执行局部检测，但没有完整语义证明
  - `manual`：**3**，当前只能生成人工/业务审阅任务
- `unavailable`：**0**；没有规则被标记为完全无法构建局部解释
- 逐条 158 条清单见 `validation/PARTIAL_RULES.md`；该文件包含原始规则 ID、检测器、覆盖说明和限制原文。

## 已确认的样式策略

2026-10-19 用户确认：

- 最大行宽：**120 字符**
- 最大函数/方法长度：**50 行**
- 函数/方法长度统计口径：**算上函数签名，除去注释行和空行，只统计有效行**

Java 实现已按该口径修正：Javac AST 的方法声明范围包含签名、方法体和结束行；空行与整行注释不计入；字符串、字符和文本块里的 `//`、`/* */` 不是注释。JavaScript 的 `G.MET.01` 使用 ESLint `max-lines-per-function`，其函数节点范围包含签名和结束行，并开启 `skipBlankLines` 与 `skipComments`。Python 和 TypeScript 导出规则集中没有单独的函数长度条目，因此不额外发明规则。

## 语言分布

| 语言 | 规则总数 | implemented | partial | manual | 未完整实现合计 |
|---|---:|---:|---:|---:|---:|
| Java | 181 | 89 | 91 | 1 | 92 |
| Python | 127 | 92 | 33 | 2 | 35 |
| JavaScript | 95 | 79 | 16 | 0 | 16 |
| TypeScript | 66 | 51 | 15 | 0 | 15 |
| **合计** | 469 | 311 | 155 | 3 | 158 |

## 规则族分布

下表只统计 `partial/manual` 规则。`非G族` 表示导出项没有 `G.xxx` 前缀，主要是 TypeScript/ESLint 兼容规则和代码质量规则。

| 语言 | 未完整实现规则族 |
|---|---|
| Java | `G.CON`(10), `G.PRM`(3), `G.OBJ`(8), `G.EDV`(9), `G.EXP`(3), `G.TYP`(7), `G.CTL`(1), `G.SEC`(2), `G.DCL`(1), `非G族`(19), `G.FMT`(6), `G.FIO`(6), `G.ERR`(3), `G.OTH`(3), `G.SER`(4), `G.LOG`(4), `G.MET`(2), `G.COL`(1) |
| Python | `G.LOG`(2), `G.EDV`(5), `G.PSL`(2), `G.DSP`(4), `G.TYP`(2), `G.NAM`(2), `G.VAR`(2), `G.CTL`(2), `G.FNM`(2), `G.ERR`(3), `G.SER`(1), `G.CLS`(3), `G.EXP`(1), `G.OPR`(1), `G.FIO`(2), `G.PRM`(1) |
| JavaScript | `G.MOD`(1), `G.CTL`(1), `G.TYP`(3), `G.MET`(1), `G.WST`(2), `G.WSQ`(1), `G.CORS`(1), `G.CMT`(1), `G.OTH`(3), `G.NOD`(1), `G.NAM`(1) |
| TypeScript | `非G族`(15) |

## 三条 manual 规则

| 语言 | 规则 | 需要的信息 |
|---|---|---|
| Python | `da6c6a446db811eea68ffa163e0fa374` G.NAM.02 命名要有明确含义，以提升代码的可读性 | 业务词汇表、领域命名约定、允许缩写表、人工/AI 审阅标准 |
| Python | `da6919d06db811eea68ffa163e0fa374` G.DSP.01 将敏感对象发送出信任区域前进行签名并加密 | 敏感对象定义、信任边界图、目的地清单、必须使用的签名和加密算法、密钥管理策略 |
| Java | `da707c426db811eea68ffa163e0fa374` G.ERR.05 方法抛出的异常，应该与本身的抽象层次相对应 | 方法的架构/领域契约、预期抽象层、允许跨层暴露的异常白名单或分层边界 |

## 主要实现缺口

这些分类来自对 158 条 `reason` 的关键词归纳，类别之间有重叠；计数是“涉及该能力的规则数”，不能相加。

| 缺口类型 | 涉及规则数 | 典型表现 |
|---|---:|---|
| 类型/语义/继承推断 | 74 | 外部类型、泛型、动态调用、方法返回类型、继承/协议关系无法完整解析 |
| 跨过程数据流/别名/生命周期 | 56 | 缺 call graph、别名、逃逸、可变性、sanitizer、资源或线程池生命周期模型 |
| 路径敏感控制流 | 60 | 分支可达性、常量表达式、异常路径、finally 覆盖、循环终止仍未完全证明 |
| 外部依赖/运行时/项目上下文 | 42 | 缺 classpath、依赖类型声明、目标运行时版本、框架 source/sink、bundler/module 语义 |
| 业务/领域/安全上下文 | 47 | 无法从语法判断业务敏感性、信任边界、精度要求、架构层次或命名含义 |
| 并发/线程/锁 | 11 | 锁别名、ThreadLocal 清理、双重检查锁、线程取消协议、内存模型语义 |
| 样式/阈值/项目选项 | 26 | 导出缺少阈值、命名例外、空行、安全阈值等明确配置 |

## 本轮补齐原则

- 不把“已有局部检测器”直接冒充官方完整语义。
- 只有当本地解释、可执行检测器、正反例和明确边界都存在时，才把 manifest 从 `partial` 升为 `implemented`。
- 安全、数据流、业务语义、项目阈值和信任边界类规则仍保持 `partial` 或 `manual`，除非用户提供明确策略。
- 外部依赖、运行时和框架上下文缺失时必须显式记录，不允许静默假设。

## 补齐实现需要的信息

### 1. 官方语义与验收样例

要实现“完整”而不是本地解释，至少需要：

- CodeArts 每条规则的精确定义、适用范围、边界行为和告警抑制语义
- 每条规则的官方正反例、误报/漏报验收样例和版本变更记录
- 官方 severity `0/1/2/3` 的含义、阻断策略和报告语义
- 明确要求“与 CodeArts 完全等价”还是接受“本地可执行且边界清楚”的替代解释

### 2. 项目与运行时上下文

- Java classpath/依赖版本、编译目标、注解处理器和生成代码位置
- Python 目标版本、虚拟环境、依赖清单和模块根路径
- JavaScript/TypeScript tsconfig/path alias/bundler/runtime 版本与依赖源
- 测试/生产/CLI/入口文件边界，以及允许的框架特例

### 3. 安全策略

- RSA/DSA/DH 最小密钥长度、AES 最小长度和 cipher 白名单
- PBKDF2/argon/bcrypt 等迭代次数与算法策略
- TLS 最低版本、 cipher/hash 白名单和 SSH 算法偏好
- 敏感字段/对象词汇表、信任边界图、source/sink/sanitizer 清单
- 反序列化、文件解压、反射、日志输出等场景的必须校验动作

### 4. 业务与架构语义

- 业务词汇表、允许缩写和命名例外
- 方法/异常的领域抽象层次和分层边界
- 精确计算、时区敏感、临时数据、日志语言等产品策略
- 集合/数组/Optional/varargs 等 API 设计例外

### 5. 风格阈值与例外

- 条件复杂度、参数个数、返回元组长度、注释位置等未导出阈值
- 空块、空行、缩进、垂直对齐、换行、文件命名等 formatter 例外
- 项目级 ignore/suppress 权限和审批流程

## 建议补齐顺序

1. 先由用户确认安全阈值、业务词汇和项目边界；这些决定会解锁最多 `partial/manual` 规则。
2. 建立项目索引：依赖版本、classpath、模块图、入口/测试边界，用于消除外部类型和运行时不确定性。
3. 增加有界跨过程模型：call graph、参数/返回摘要、别名与逃逸摘要，先覆盖安全 source/sink 高频规则。
4. 增强路径敏感控制流：分支可达、异常路径、常量折叠和 finally/Promise 完成语义。
5. 用官方或项目验收样例建立 precision/recall 基准，避免只靠新增示例自我验证。
6. 将无法自动化的业务/架构规则保留为 review task，并要求人工记录证据、决策和上下文。

## 验证

- `python3 -m unittest discover -s tests -p "test_catalog_*.py" -q`：39 tests passed（本轮已执行）。
- `python3 -m unittest discover -s tests -q`：299 tests passed, 1 skipped（本轮最终变更后已执行）。
- `python3 -m py_compile scripts/catalog_java.py scripts/catalog_python.py`：通过。
- `python3 -m json.tool references/semantic-review.schema.json`：通过。
- `git diff --check`：通过。
