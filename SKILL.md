---
name: huawei-code-review
description: Run the Huawei/CodeArts Java, Python, JavaScript and TypeScript standards CLI, export findings to Excel, review semantic coverage gaps, and repair code with a verified rescan when requested. Use for standards-based code review and repair, not general programming questions.
---

# Huawei code review and repair

Use the bundled CLI as the deterministic scanner. It executes the imported catalog by default; `--ruleset legacy` is only the old 17-rule compatibility mode. Never use legacy results to claim the imported standards passed.

## Inspect and scan

1. Identify project roots and languages. Read project instructions, test commands and runtime requirements. Preserve existing changes. The scanner parses source locally; it does not require executing a project's build/install hooks.
2. Check `python3 <skill-root>/scripts/check.py --list-rules --language LANGUAGE`. Inspect implementation status and reason, not just rule count. A rule being present does not establish complete semantics.
3. Select a durable run directory outside the scanned source tree. Save immutable `before.json` with:

   ```sh
   python3 <skill-root>/scripts/check.py SRC --format json --fail-on warning --output RUN/before.json
   ```

   Python uses the standard library; Java requires JDK21; JS/TS requires the pinned dependencies described in README.md. Respect existing authorization when setting up missing dependencies. Do not silently substitute legacy mode if dependencies fail.
4. Read the exit code plus `uncovered`, `coverage_summary`, `rule_coverage` and findings. Exit 2 means incomplete analysis, including partial/manual/unavailable selected rules. `--allow-uncovered` is an explicit threshold override, not a completeness claim. Record it if used.
5. Generate Excel from that exact JSON rather than scanning a second time:

   ```python
   import json
   from scripts.xlsx_export import write_xlsx
   write_xlsx(json.load(open("RUN/before.json")), "RUN/before.xlsx")
   ```

   Run this Python snippet with the installed package or `<skill-root>` on `PYTHONPATH`. Keep the four sheets: Summary, Findings, Uncovered and Rule Coverage.

## Review scope and semantics

Treat `implemented` as the documented local static-analysis implementation, not a claim of equivalence to proprietary Huawei engines. `partial` means the detector covers only the stated subset; read its reason before judging a result. Preserve original `raw_severity`; it is not automatically equivalent to local severity.

For `review_tasks`, read relevant source and project context, group related rules, and use the LLM semantic-review fallback described in `references/semantic-review.md`. This fallback is allowed, but it is supplemental judgment rather than a substitute for a deterministic detector. Record a separate `semantic-review.json` validated by `references/semantic-review.schema.json`, with rule key, evidence paths/lines, decision, confidence, rationale, and missing context. A pending task is not a violation. Do not manufacture findings for abstract naming, trust-boundary or sensitive-data rules when the needed project knowledge is missing. Keep these decisions separate from immutable CLI findings and automatic coverage, and do not change a rule's implementation status merely because an LLM reviewed it.

For a particular finding, trace the code and its callers. Classify it as a confirmed rule violation, a context-dependent candidate, an intentional exception or an analyzer false positive. Retain the raw finding and explain any disagreement in a derived review artifact. External adapters retain `external-tool` provenance; AI findings retain `manual-review` provenance.

## Repair when requested

Inspect uncovered[].affected_rule_ids before attributing a dependency gap to every rule. Valid scoped errors leave unrelated checks usable; missing or malformed scopes invalidate the language run. Findings with coverage_status=error remain incomplete evidence. A repair of an unaffected covered rule may verify under identical scope/options/fingerprints while the overall scan remains incomplete. Inspect the reported Python static model baseline before making library-dependent conclusions; a Python 3.11 model does not establish behavior for a different target library version.

If the user has requested fixing, perform authorized safe edits without asking again for each mechanical change. A review-only request produces a repair plan without changing source.

1. Write `repair-plan.json` with stable finding identity, original evidence, proposed edit, rationale, confidence, tests, and whether behavior changes. Re-read current source before applying each edit.
2. `fix.autofixable=false` means there is no trusted mechanical patch supplied by the detector. It does not forbid an AI-designed repair, but the AI must verify the diagnosis and safety from source. Do not use partial detections alone as proof that a behavior-changing repair is correct.
3. Apply bounded changes within the requested scope. Preserve source behavior for style repairs; for correctness repairs add a failing behavioral regression and then fix it. Use project tests to validate the change, not merely disappearance of a warning.
4. Rerun the same catalog rule selection, configuration, source paths and external tools into immutable `after.json`; derive `after.xlsx` from it. Never disable rules, lower severity or shrink scope to make a repair pass.
5. Run `huawei-code-review-compare RUN/before.json RUN/after.json --output RUN/delta.json`. Inspect `unverified_resolutions`: rules removed or unavailable, changed thresholds or analyzer fingerprints, and missing companion source files in the second scan cannot establish a fix. A resolved diagnostic is evidence of successful rescanning, not proof of overall behavioral correctness.
6. Save `changes.diff`, executed test commands and exit codes in `run.json`. Report confirmed fixes, remaining findings and incomplete rules. An exit 2 scan remains incomplete even when repaired findings disappeared.

## References

- Installation, runtime discovery and commands: README.md.
- Report semantics: references/report-schema.md.
- LLM fallback for partial/manual semantic review: references/semantic-review.md and references/semantic-review.schema.json.
- Imported rule provenance and limitations: references/codearts-rule-mapping.md.
- Industry baselines for uncertain rules: references/industry-baselines.md.
- CLI architecture and execution contract: references/cli-design.md.
- All rule implementation details: `--list-rules` and rulesets/implementations/*.json.

Project config is JSON or TOML, not YAML. Use repeated `--select RULE-ID` to restrict catalog rules, `--ignore RULE-ID` to disable a rule explicitly, and `--exclude PATH-PATTERN` for files. Report the narrowed scope. Per-line legacy suppression behavior is not a catalog-wide completion mechanism.

Use project `rules.<ID>.options` or repeated `--rule-option RULE-ID:OPTION=VALUE` only to apply an agreed project policy. Inspect effective `options` and immutable `exported_options` in Rule Coverage. Preserve those effective options throughout a repair run; policy changes require a separate baseline. Supply related source directories together so cross-file inheritance, imports and helper calls can be analyzed.
