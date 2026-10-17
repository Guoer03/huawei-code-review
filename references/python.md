# Python rule profile

The downloaded Python document is `huawei-python-community`, a Huawei Cloud community article. CodeArts also exposes an official gated Python/Huawei rule set, but it was not exported locally. Community findings are advisory unless the user supplies an authenticated CodeArts export.

- `HUAWEI-PY-FORMAT-001`: use four spaces for indentation; do not mix tabs and spaces.
- `HUAWEI-PY-FORMAT-002`: avoid semicolons and keep line length within the selected project limit (the community article uses 80 characters).
- `HUAWEI-PY-IMPORT-001`: keep imports at module scope, one module per import, and avoid wildcard imports.
- `HUAWEI-PY-STYLE-001`: use meaningful snake_case names for functions and variables; use CapWords for classes.
- `HUAWEI-PY-QUALITY-001`: prefer iterable-oriented loops over index-only `range(len(items))` when the index is not needed.

Use Ruff/Flake8/Black or a supplied project configuration for executable Python linting. Do not claim that these community rules are the CodeArts official set.
