# CodeArts export mapping boundary

The four user-supplied ZIP files are structured CodeArts rule-set snapshots.
They are retained under `rulesets/` with their archive SHA-256 values and raw
JSON snapshots. Their status is `user-exported`: the files came from the user,
while their metadata identifies the CodeArts system rule sets.

## Snapshot inventory

| Language | Criterion set | Rules | Engine tags | Options |
|---|---|---:|---|---:|
| Python | Huawei Codestyle Specification Rule Set | 127 | pylint 72, flake8 20, codemars 35 | `max-line-length=120` |
| TypeScript | Comprehensive Rule Set | 66 | sonarqube 60, eslint 6 | `maximum=30`, `credentialWords=...` |
| JavaScript | Huawei Js Coding Standard Rule Set | 95 | codemars 95 | none |
| Java | Huawei Java Enhanced Coding Standard Rule Set | 181 | fixbotengine-java 110, secbrella 37, codemars 34 | method nesting 4, parameters 5, method length 50 |

## Mapping rules

- The identity key is `criterion_set_id + ruleInfos[].id`. Do not deduplicate
  by English or Chinese name; Java contains repeated names with different
  engines or scopes.
- Preserve the original numeric severity. The exports do not define whether
  `0`, `1`, `2`, and `3` correspond to the local `info`, `warning`, and `error`
  levels, so conversion must be configured and tested separately.
- A `systemTag` identifies the originating engine family. It is not proof that
  a Huawei rule ID equals a same-looking Ruff, Flake8, Pylint, ESLint, or
  Checkstyle code.
- TypeScript has six explicit `@typescript-eslint/*` names that can be exact
  mapping candidates. Python's `pylint` and `flake8` tags identify an engine
  family but do not provide a bottom-level message code in this export.
- Java and JavaScript entries tagged `codemars`, `fixbotengine-java`, or
  `secbrella` use tested local detectors where the exported meaning supports
  them. Their private original engines are not bundled or reproduced.
- `tsc` diagnostics are compiler findings and must retain their `tsc` source;
  they must not be relabeled as a CodeArts rule without an exact mapping.

## Coverage states

```text
covered   = implemented local semantics + successful execution
candidate = tested executable subset of a broader rule (partial)
opaque    = manual review or unavailable implementation
error     = selected analyzer failed or could not parse input
not-run   = inventory only
```

`covered` refers to the documented local interpretation of an exported rule,
not equivalence to an unpublished CodeArts implementation. The per-language
`rulesets/implementations/*.json` manifests are the authority for current
implementation status, supported patterns, limitations and test references.
Use `--list-rules` to inspect all 469 identities through the installed CLI.

Default scans dispatch Java through javac syntax trees, Python through AST and
tokenize, and JavaScript/TypeScript through ESLint and the TypeScript compiler
API. Partial rules run their supported checks and also generate semantic
review tasks. Manual rules generate review tasks only. Neither tasks nor
coverage gaps are fabricated findings. Partial/manual selections make full
coverage false and produce exit 2 unless explicitly permitted.

Original rule options are passed to each detector, including the exported
Python 120-column limit, Java method limits, and TypeScript case-count and
credential-word options. Local defaults used where the export lacks policy
are documented in each rule's reason; they are not official Huawei values.
