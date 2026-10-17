# Industry architecture notes

This project uses established open-source analyzers as design references. These
links are reference implementations, not additional Huawei rule sources.

## Observed patterns

| Project | Repository | Pattern to reuse |
|---|---|---|
| ESLint | https://github.com/eslint/eslint | Every rule is a plugin with metadata, a stable name, configurable severity, and optional fixer. Rule tests are kept beside a valid/invalid fixture matrix. |
| Ruff | https://github.com/astral-sh/ruff | Stable rule codes, select/ignore configuration, fast native execution, and machine-readable JSON/SARIF output. |
| Semgrep | https://github.com/semgrep/semgrep | Declarative rules describe a pattern, message, severity, metadata, and optional fix; rule tests are data-driven. |
| Checkstyle | https://github.com/checkstyle/checkstyle | Java checks run over a parsed tree and are composed through a configuration file. Each check has focused input and expected-output tests. |
| SonarQube | https://github.com/SonarSource/sonarqube | Rule repositories are separated from quality profiles, project configuration, issue lifecycle, and quality gates. |
| OpenRewrite | https://github.com/openrewrite/rewrite | Analysis and source transformation are separate recipes; fixes can be previewed before application. |
| CodeQL | https://github.com/github/codeql | Query/data-flow analysis is a separate layer for security and cross-function findings. |
| SARIF | https://github.com/oasis-tcs/sarif-spec | Static-analysis tools exchange findings with stable rule IDs and physical locations. |

## Decisions for this tool

1. Keep the CodeArts export as an immutable, provenance-tracked rule catalog.
2. Separate `tool-backed`, `compiler-backed`, `custom`, and `opaque` rules.
3. Only an exact, tested mapping to ESLint, Ruff, Flake8, Pylint, Checkstyle,
   or `tsc` is marked `covered`.
4. A semantically similar rule without a verified mapping remains `candidate`
   and cannot be presented as CodeArts coverage.
5. Add one valid, one invalid, and one boundary fixture for every executable
   rule. Add a fix fixture only when the transformation is behavior-preserving.
6. Keep deterministic findings authoritative. AI may explain or add an
   evidence-backed semantic finding, but it cannot remove or lower a
   deterministic finding.
7. Emit the same normalized finding model as JSON, Markdown, and SARIF, with
   source provenance beside each finding.

## Planned pipeline

```text
CodeArts ZIP snapshot
  -> safe import + SHA-256 + raw archive
  -> normalized rule catalog
  -> exact mapping registry
  -> native/adapter/custom detector
  -> valid/invalid/boundary fixtures
  -> JSON/SARIF/Markdown report
  -> Skill orchestration and explanation
```

The current repository has completed the first two stages. The catalog is not
itself an executable implementation of all 469 rules.
