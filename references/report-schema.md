# Report contract (schema 1.0, additive v0.4 fields)

`findings` remains a list of id, path, line, column, language, severity, confidence, title, message, evidence, source and fix. Catalog findings additionally include rule_key, criterion_set_id, raw_severity, implementation_status, coverage_status and detector.

`rule_coverage` has one row per selected exported rule identity, retaining criterion set, options, test_cases and reason. `implementation_status` is implemented, partial, manual or unavailable. `execution_status` is completed, error or not-run. `coverage_status` is covered only when an implemented rule actually ran without analyzer errors; partial detectors are candidate, non-executable rules opaque, and failed analysis error. Inventory rows use not-run.

`coverage_summary` separates selected rules, implementation counts, executed rules and complete. The complete flag refers only to selected local detector semantics, never private engine equivalence. `summary.pass` is a process threshold outcome and can be true with incomplete coverage only when the user explicitly allowed it. `summary.uncovered_allowed` records that override. Legacy mode has catalog_checked=false and complete=false.

`uncovered` contains path/reason entries. Coverage gaps use rule_ids; scoped analyzer errors use affected_rule_ids. Rule gaps, missing runtimes and parse errors never become silent zero findings.

Scoped errors contain a nonempty affected_rule_ids list containing only selected IDs. Absent, empty, malformed or unknown scopes invalidate all active rules in the language. Unaffected checks keep their execution status, while any gap preserves default exit 2 and complete=false. Findings inherit their rule's actual final coverage status. Excel Uncovered preserves affected_rule_ids (or catalog rule_ids).

Python type_context.stdlib_models records the pinned Python 3.11 baseline, model version, classes used, host version and target_version_detected=false. Unknown vendor types and conditional imports remain unresolved. Model and completion helper assets contribute to analyzer fingerprints. An unaffected covered rule can support same-scope repair comparison while unrelated checks remain incomplete.

`review_tasks` contains rule-specific pending semantic review instructions and source paths for partial/manual rules. A task is not an observed violation and does not increase finding counts. Save AI decisions separately with evidence.

SARIF retains coverage_summary, uncovered and rule_coverage in run.properties. executionSuccessful is false when gaps remain, regardless of an explicit CLI threshold override. Excel exports the same findings and coverage rows with implementation/execution reasons visible.

The comparator adds unverified_resolutions when a finding disappeared but its rule was removed or failed in the second scan. Resolved findings still require project tests to establish correct behavior.

`input_files` records the path, detected language and SHA-256 of every analyzed
source. `toolchain.analyzers` records implementation hashes and runtime/context
metadata returned by each language analyzer. Each executed rule includes a
`detector_fingerprint`; changed detector code, runtime or TypeScript context
cannot establish a verified repair by mere disappearance of diagnostics.

`rule_coverage.options` records effective project policy; `exported_options` retains the original imported values and `option_source` identifies a project override. Excel Rule Coverage includes all three fields. Comparisons require unchanged effective options and the same language source-file path set, including companion files used for cross-file analysis. Python/Java project helper modules contribute to analyzer fingerprints.
