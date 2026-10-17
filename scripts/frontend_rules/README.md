# Exported JavaScript and TypeScript rule backend

This backend maps all 95 JavaScript and 66 TypeScript catalog entries to executable ESLint rules or typed TypeScript AST checks. A mapping is not a claim that Huawei's proprietary analyzer has been reproduced. The manifests in `rulesets/implementations` distinguish implemented requirements from partial checks, document each boundary, and point to paired source examples.

Install the pinned runtime using the top-level dependency setup, or install these packages in this directory:

```sh
npm install --save-exact eslint@10.8.0 @typescript-eslint/parser@8.65.0 @typescript-eslint/eslint-plugin@8.65.0 typescript@5.9.3
```

Use Node.js 20.19+ (or a newer supported Node release). `HCR_NODE_MODULES` may point to an existing directory containing these dependencies; `HCR_NODE` may specify a Node executable. The runtime also searches its own and parent directories. It never loads a scanned project's ESLint config or executes scanned source. Existing ESLint disable comments cannot bypass catalog policy.

`HCR_TS_CONFIG` selects a TypeScript JSON configuration. Otherwise the nearest `tsconfig.json` for input files is read to resolve project compiler options, aliases and declaration files. Multiple different configs require separate scans (or an explicit config) and produce an incomplete-analysis error. Missing imported modules/types, parser errors, invalid configuration and missing tools are structured errors, never a clean result. This is not a substitute for a full project build; diagnostic codes unrelated to missing type inputs are left to the project's compiler.

Exported numeric `severity` is retained as `raw_severity`; its meaning is not guessed. The explicit local policy is ESLint `error` and AST `warning`, recorded as `severity_policy`. Partial checks have low confidence. Security checks based on suspicious APIs or credential names are candidates for review, not proofs of exploitable defects.

The export omits numeric/style options for several prose requirements. The implementation states its chosen interpretation (for example, 120-column lines and 50 nonblank function lines) and marks that mapping partial. Removed legacy TypeScript-ESLint rules are mapped to supported replacements or explicit compatibility AST checks, with differences documented. TypeScript checks use static types; unknown values, aliasing and interprocedural dataflow remain documented limits.

Regenerate mappings and fixture data:

```sh
python3 scripts/frontend_rules/build_catalog.py
python3 -m unittest discover -s tests -p test_catalog_frontend.py
```

Tests exercise each code rule's positive/negative source, threshold boundaries, typed array/object differences, local shadowing, comment/string/template/regex isolation, module resolution, malformed syntax, absent runtime, and representative patterns from Vue. Tests skip runtime-dependent cases when dependencies are absent; the CLI still reports missing dependencies as incomplete analysis.
