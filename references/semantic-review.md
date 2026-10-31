# Semantic review fallback contract

The CLI is the deterministic scanner and remains the source of immutable findings and rule coverage. For `partial`, `manual`, or otherwise incomplete rules, the Skill may perform an LLM-assisted semantic review as a fallback, but that review is evidence-bearing human/AI review—not a detector upgrade.

Record the source CLI report path and its SHA-256 in `source_report` and `source_report_sha256`. Write the result to a separate `semantic-review.json`; never mutate the CLI's `before.json`, `after.json`, finding counts, `rule_coverage`, `implementation_status`, or `coverage_summary`. Validate it against `semantic-review.schema.json`.

Each decision must state:

- `decision`: `confirmed_violation`, `context_candidate`, `intentional_exception`, `analyzer_false_positive`, or `unresolved`;
- `confidence`: low, medium, or high;
- source `evidence` with path, line numbers, and a concrete observation;
- `missing_context` when project, dependency, security, architecture, or runtime information is needed;
- a bounded `recommended_action`.

Use `provenance: manual-review` and `method: skill-llm-semantic-review`. An AI conclusion does not change a rule from `partial` or `manual` to `implemented`. A deterministic upgrade requires detector code, positive/negative tests, an updated implementation manifest, and a full validation rerun. Security conclusions remain review candidates unless exploitability is separately proven.
