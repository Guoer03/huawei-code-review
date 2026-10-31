# Huawei Code Review CLI

Local code checking for the four user-exported CodeArts standards catalogs: Java 181, Python 127, JavaScript 95, TypeScript 66. Version 0.4 defaults to catalog detectors rather than the original 17 pattern checks.

**469 imported rules do not mean 469 complete automated proofs.** Every rule has an implementation manifest, detector/test references and a reason explaining limitations. Consult `--list-rules` for current implemented/partial/manual/unavailable counts. Partial rules run their supported detectors and also create review tasks. Missing or incomplete selected checks produce exit 2 by default.

## Install and run

Python 3.10+ is required (3.11+ for TOML). Python rules use AST/tokenize. Java needs JDK21 (`JAVA_HOME` or Java on PATH); the analyzer parses source with javac and does not build or run the project. JavaScript/TypeScript needs Node 20.19+ and pinned dependencies:

```sh
python3 -m pip install .
npm ci --ignore-scripts
huawei-code-review src/ --format json --output before.json
huawei-code-review src/ --format xlsx --output before.xlsx
huawei-code-review --list-rules --language java --format xlsx --output java-rules.xlsx
```

For source checkout use `python3 scripts/check.py` or `bin/huawei-code-review`. The wheel includes imported catalogs, implementation manifests and parser runtime assets. Node dependencies and the JDK are external runtimes, not embedded in the wheel.

For an existing Node dependency installation set `HCR_NODE_MODULES` to its node_modules directory. `HCR_NODE` selects the Node executable. These are explicit local runtime choices; the scanner never installs dependencies automatically. To use JS/TS from an installed wheel, keep a dedicated Node dependency directory and set `HCR_NODE_MODULES` to it.

```sh
huawei-code-review src/ --select da6b2b5d6db811eea68ffa163e0fa374 --fail-on warning
huawei-code-review src/ --allow-uncovered --fail-on warning
huawei-code-review src/ --ruleset legacy
```

The first example selects the exported Python mutable-default rule. The second permits incomplete coverage for threshold evaluation but reports `coverage_summary.complete=false`. Legacy mode explicitly runs only the old checks and never establishes catalog coverage.

Directory discovery includes `.java`, `.py`, `.js`, `.jsx`, `.mjs`, `.cjs`, `.ts`, `.tsx`, `.mts`, `.cts` and `.ets`. TypeScript syntax in `.ets` is supported; ArkTS-only syntax requires a compatible parser and otherwise produces an analysis error.

## Project analysis

The scanner shares a supplied-source project context across files. Java resolves packages/imports, nested types, generic inheritance and erased override signatures; Python resolves imports/reexports, C3 inheritance, exception order and bounded return/control-flow facts. Neither imports nor executes scanned Python modules, and Java remains parse-only without build hooks or annotation processors.

TypeScript's program/checker supports cross-file symbol identity and return types. Additional checks cover alpha-renamed duplicate functions, branch-specific incoming-value overwrites and supplied-source array mutation helpers. These are bounded analyses: unresolved external types, dynamic dispatch and unsupported paths remain visible limitations. Provide all related source directories in the same scan for project analysis.

## Reports and process status

Version 0.4 adds structured completion analysis for Java and frontend code: nested finally, loop/label targets, switch completion and reachable return paths. Promise checks distinguish await, non-callable rejection handlers and handlers that rethrow or reject. Python includes selected standard-library inheritance and method signatures pinned to Python 3.11; model version, baseline, used classes and host version appear in type_context.stdlib_models. This baseline does not detect the target Python version or provide complete library stubs.

Scoped analyzer errors identify affected rules in uncovered[].affected_rule_ids. Independent checks retain their execution status; parse/runtime failures and invalid scopes invalidate the affected language run. Any gap still produces default exit 2. Findings inherit their rule's actual coverage status, including error; Excel Uncovered preserves affected rule IDs.

- 0: findings did not cross the configured threshold and no unpermitted coverage gap was reported. Inspect the chosen rules and any explicit `--allow-uncovered` override.
- 1: findings crossed `--fail-on info|warning|error`.
- 2: selected rules or files were not fully analyzed, required tools failed, or configuration/parse/runtime errors occurred. Findings can still be present and useful.

JSON is the canonical evidence. Excel has Summary, Findings, Uncovered and Rule Coverage, including each rule's implementation/execution status, reason, effective options and original exported options. `--list-rules` is an inventory operation, not a scan, and exits 0 when inventory rendering succeeds. It does not report a compliance pass.

Preserve the original numeric severity; normalization uses explicit local detector policy, not a guessed mapping of the exported numbers. Catalog results are `user-exported`; adapters are `external-tool`. No claim is made that local detectors reproduce private CodeArts engine internals.

To make Excel from the exact saved JSON:

```python
import json
from scripts.xlsx_export import write_xlsx
write_xlsx(json.load(open("before.json")), "before.xlsx")
```

## External tools and configuration

```sh
huawei-code-review src/ --require-tool eslint --tool-path eslint=/path/to/eslint \
  --tool-arg eslint=--config --tool-arg eslint=/path/to/eslint.config.mjs
huawei-code-review src/ --require-tool checkstyle --tool-arg checkstyle=-c \
  --tool-arg checkstyle=/path/to/checkstyle.xml
```

Each `--tool-arg` is one literal argument, never shell code. Config is `.huawei-code-review.toml` or JSON; explicit CLI values override it. Supported config fields include ruleset, language, fail_on, enabled_rules, disabled_rules, exclude, ignore, tools, required_tools, tool_paths, tool_args and tool_timeout. The default tool timeout is 60 seconds. Rule-specific thresholds use exported option names; unknown names and invalid values fail with exit 2. For example:

```toml
[rules.da6a6d696db811eea68ffa163e0fa374.options]
max-line-length = 100
```

```sh
huawei-code-review src/ --rule-option da6a6d696db811eea68ffa163e0fa374:max-line-length=100
```

Repeat `--rule-option RULE-ID:OPTION=VALUE` to override project settings. JSON and Excel preserve `exported_options` separately from effective `options`; changing a threshold never counts as a verified repair.

## AI semantic review and repair

The accompanying SKILL.md drives scan, source review, authorized repair, project tests and identical-scope rescan. `review_tasks` represent unresolved semantic work, not automatic findings. For those tasks the Skill can use an LLM as a bounded fallback, recording decisions in a separate `semantic-review.json`; see `references/semantic-review.md` and `references/semantic-review.schema.json`. Industry baselines for uncertain rules are recorded in [references/industry-baselines.md](references/industry-baselines.md); they are reference material, not an automatic rule upgrade. The CLI architecture and execution contract are documented in [references/cli-design.md](references/cli-design.md). This supplemental review never changes CLI implementation/coverage status by itself. Before/after comparison requires the same language source scope, rule options and analyzer fingerprint. Removed rules or companion source files, changed thresholds, and changed analyzer code cannot establish a verified repair:

```sh
huawei-code-review-compare before.json after.json --output delta.json
```

## Validation

```sh
python3 -m unittest discover -s tests -p 'test_*.py' -v
python3 -m unittest discover -s adapters -p 'test_*.py' -v
```

Language tests contain rule-specific positive and negative source examples. Real-project runs are recorded separately from fixture tests; neither establishes universal precision or recall. Exported rules lack some thresholds, project policies and semantic details, which remain visible in manifests rather than being invented as official settings.

Current validated implementation counts and real-project evidence: [validation/COVERAGE.md](validation/COVERAGE.md). This is a coverage snapshot, not a full-compliance claim.
