# Industry baselines for uncertain rules

This file collects public industry baselines that can help interpret rules that are
not fully specified by the imported Huawei/CodeArts export or that are currently
`partial` in the local CLI. It is **not** a Huawei/CodeArts rule source and does
not by itself upgrade any rule from `partial` to `implemented`.

## Scope

Use this document to:

- compare uncertain semantics with public industry standards;
- record explicit project policies when public standards disagree;
- explain why some rules remain context-sensitive or `partial`;
- choose future deterministic or LLM-assisted review heuristics.

Do not use this document to:

- claim official Huawei/CodeArts approval for a local interpretation;
- silently rewrite a rule's meaning;
- upgrade implementation status without a detector, tests, and a full rerun.

## Source inventory

All sources below were retrieved successfully on **2026-10-20**.

| Source | Status | URL | Main use |
|---|---|---|---|
| Google Java Style Guide | official-public | https://google.github.io/styleguide/javaguide.html | Java formatting, 100-column limit, 2-space indentation, brace style, Javadoc conventions |
| SEI CERT Oracle Coding Standard for Java | official-public | https://wiki.sei.cmu.edu/confluence/display/java/SEI+CERT+Oracle+Coding+Standard+for+Java | Java security, exceptions, serialization, platform security |
| PEP 8 | official-public | https://peps.python.org/pep-0008/ | Python formatting, 79-column limit, 4-space indentation, naming, imports, blank lines |
| PEP 257 | official-public | https://peps.python.org/pep-0257/ | Python docstring conventions |
| Google Python Style Guide | official-public | https://google.github.io/styleguide/pyguide.html | Python style, 80-column limit, function length around 40 lines, logging, resource closure |
| Google JavaScript Style Guide | official-public | https://google.github.io/styleguide/jsguide.html | JavaScript formatting, 80-column limit, 2-space indentation, `eval` restrictions |
| Google TypeScript Style Guide | official-public | https://google.github.io/styleguide/tsguide.html | TypeScript style, modules over namespaces, `var` avoidance, explicit typing guidance |
| ESLint rule documentation | official-public | https://eslint.org/docs/latest/rules/ | Configurable line length, function length, complexity, unused variables, exception and dynamic evaluation rules |
| typescript-eslint rule documentation | official-public | https://typescript-eslint.io/rules/ | TypeScript-specific promise, void, `any`, condition, and type-safety rules |
| OWASP Cheat Sheet Series | official-public | https://cheatsheetseries.owasp.org/ | SQL injection, XSS, OS command injection, XXE, deserialization, logging, crypto, and secrets guidance |
| Common Weakness Enumeration (CWE) | official-public | https://cwe.mitre.org/ | Standard weakness IDs for security rule mapping |

## Rule-family baselines

### 1. Formatting and readability

| Topic | Industry baseline | Local implication |
|---|---|---|
| Line width | Google Java: 100; PEP 8: 79; Google Python: 80; Google JavaScript: 80; Google TypeScript public guide does not state a numeric limit in the retrieved version | A **120-character project limit** is a deliberate relaxation, not an industry default. Keep it as an explicit project policy. |
| Indentation | PEP 8 and Google Python: 4 spaces; Google Java and Google JavaScript: 2 spaces | The current project uses 4 spaces. Record this as project policy, not universal industry practice. |
| Braces and blocks | Google Java and Google JavaScript use K&R-style braces and require braces for control structures | Good baseline for empty-block and brace-style checks. |
| Function length | Google Python recommends thinking about splitting functions around 40 lines but sets no hard limit; ESLint `max-lines-per-function` is configurable | A **50 effective-line limit** is stricter and more precise than most public guides. Keep it as project policy. |
| Complexity | ESLint `complexity` caps cyclomatic complexity; ESLint `max-lines-per-function` caps physical or logical lines depending on options | Use complexity as a complementary signal, not as a substitute for the user-defined effective-line metric. |

### 2. Exceptions, promises, and void expressions

| Topic | Industry baseline | Local implication |
|---|---|---|
| Throwing values | ESLint `no-throw-literal` disallows throwing literals and expressions that cannot be an `Error` | Useful for “do not throw non-exception values” checks. |
| Floating promises | typescript-eslint `no-floating-promises` reports unhandled promise-valued statements | Strong baseline for Promise rejection and sequencing rules. |
| Misused promises | typescript-eslint `no-misused-promises` reports promises where a non-promise is expected, often due to missing `await` | Useful for Promise-in-boolean or Promise-as-value rules. |
| Void expressions | typescript-eslint `no-confusing-void-expression` flags using `void` results where they are likely a bug | Useful for “do not use the output of a function that returns nothing.” |
| Docstrings | PEP 257 standardizes Python docstring semantics | Useful for docstring placement and content rules. |
| Error disclosure | OWASP Logging and CWE-209 recommend not exposing sensitive details in errors | Supports error-message and exception-disclosure rules. |

### 3. Security and injection

| Topic | Industry baseline | Local implication |
|---|---|---|
| SQL injection | OWASP SQL Injection Prevention and Query Parameterization; CWE-89 | Prefer parameterized queries; dynamic string concatenation with external input is a candidate violation, not automatically a proven exploit. |
| Cross-site scripting | OWASP XSS Prevention; CWE-79 | Prefer contextual escaping; raw external input in HTML/DOM sinks is a review candidate unless a safe framework path is proven. |
| OS command injection | OWASP OS Command Injection Defense; CWE-78 | Prefer fixed command paths and strict argument validation; do not pass external data to shell interpreters. |
| XXE | OWASP XML External Entity Prevention; CWE-611 | Disable DTDs and external entities when possible. |
| XML entity expansion | CWE-776 | Limit recursive entity references. |
| ReDoS | CWE-1333 | Avoid unbounded or high-complexity regular expressions on external input. |
| Path traversal | CWE-22 | Normalize and validate external paths against an allowlist. |
| Deserialization | OWASP Deserialization; CWE-502 | Avoid deserializing untrusted data; use safe formats or integrity checks. |
| Hard-coded secrets | CWE-798 | Prefer a secrets manager or environment-backed policy; a credential-like name is only a review candidate without secret verification. |
| Randomness | CWE-330 | Use cryptographically secure randomness in security contexts. |
| Cryptography | CWE-327; OWASP Cryptographic Storage | Avoid broken or risky algorithms; prefer standard, maintained libraries. |
| Log injection | CWE-117; OWASP Logging | Sanitize or structurally encode external input before logging. |

### 4. TypeScript-specific type safety

| Topic | Industry baseline | Local implication |
|---|---|---|
| `any` | typescript-eslint `no-explicit-any` | Prefer precise types or `unknown`; do not silently broaden to `any`. |
| Always-truthy or always-falsy conditions | typescript-eslint `no-unnecessary-condition` | Useful for constant-condition and useless-check rules. |
| Boolean strictness | typescript-eslint `strict-boolean-expressions` | Useful for non-boolean conditions that are likely bugs. |
| Promise misuse | typescript-eslint `no-floating-promises` and `no-misused-promises` | Strong baseline for Promise sequencing and rejection handling. |
| Void expressions | typescript-eslint `no-confusing-void-expression` | Useful for return-value and assignment checks. |

### 5. Resource lifecycle

| Topic | Industry baseline | Local implication |
|---|---|---|
| Files and sockets | Google Python requires explicit closure of files, sockets, and similar stateful resources | Pair acquisition with deterministic release. |
| Java resources | SEI CERT and common Java practice favor try-with-resources or guaranteed `finally` cleanup | Use try-with-resources when the resource type supports `AutoCloseable`. |
| External processes | OWASP OS Command Injection Defense | Validate fixed executable paths and arguments; do not expose external process control to arbitrary input. |

## Conflicting or project-specific decisions

The following choices are **not universal industry defaults** and must stay as explicit project policy:

1. **120-character line width.** Public baselines vary: 79, 80, or 100 characters. A local 120-character limit is a project relaxation.
2. **50 effective lines per function.** Google Python uses a soft “about 40 lines” heuristic, while ESLint leaves the limit configurable. The project's 50 effective-line rule is stricter and must remain explicit.
3. **Counting semantics.** Google Java counts Unicode code points; other guides count characters or display width. The local definition of “character” should be fixed in the rule manifest.
4. **4-space indentation.** PEP 8 and Google Python use 4 spaces, but Google Java and Google JavaScript use 2 spaces. The project's 4-space rule is a local style choice.
5. **Security thresholds.** Public standards recommend parameterization, validation, safe parsers, and secrets management, but do not remove the need for project-specific trust boundaries, framework models, and exploitability analysis.
6. **TypeScript presets.** Some typescript-eslint rules require type information and specific ESLint presets. Without those, findings must remain partial or unavailable rather than guessed.

## Still requires project context

Even with these baselines, the following remain context-sensitive:

- which inputs are actually external or untrusted;
- whether a sanitizer, ORM, framework, or template engine is safe in the local version;
- whether a credential-like name is a real secret;
- whether a warning is a violation or an intentional exception;
- whether generated code, tests, or migrations are exempt from the 120-character and 50-line limits;
- whether tabs count as one character, a fixed width, or are prohibited;
- which TypeScript strictness flags and ESLint presets are enabled;
- whether a long function is intentional and behaviorally safe;
- whether an exception message can be disclosed to this audience or log sink.

## How to use this file

1. Keep deterministic CLI findings unchanged.
2. Use these baselines to justify reasoning or to propose a project policy.
3. If a rule needs a project-specific threshold, record it in the effective options and manifest.
4. If a rule still cannot be fully decided, keep it `partial` and use the LLM semantic-review contract.
5. Do not treat a public standard as evidence that a local detector is already complete.

## Source notes

- **Google Java Style Guide** explicitly uses a 100-character column limit and 2-space block indentation.
- **PEP 8** explicitly limits lines to 79 characters and uses 4-space indentation.
- **Google Python Style Guide** sets an 80-character line limit and suggests reconsidering functions around 40 lines.
- **Google JavaScript Style Guide** sets an 80-character limit and 2-space indentation.
- **Google TypeScript Style Guide** does not state a numeric line limit in the retrieved public version.
- **ESLint** exposes configurable rules such as `max-len`, `max-lines-per-function`, `complexity`, `no-eval`, and `no-throw-literal`.
- **typescript-eslint** exposes type-aware rules such as `no-floating-promises`, `no-misused-promises`, `no-unnecessary-condition`, `no-confusing-void-expression`, `strict-boolean-expressions`, and `no-explicit-any`.
- **OWASP** and **CWE** provide security-specific baselines but do not replace local trust-boundary or exploitability analysis.
