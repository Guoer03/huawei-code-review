# TypeScript and ArkTS rule profile

Source: `openharmony-ts-js` (OpenHarmony public TS&JS guide). ArkTS-specific checks require an ArkTS profile and should not be silently applied to ordinary TypeScript.

- `OH-TS-DECL-001`: avoid `var`; use `const` for immutable bindings and `let` for reassigned bindings.
- `OH-TS-TYPE-001`: avoid `any`; prefer a precise type or `unknown` where the source permits it.
- `OH-TS-IMPORT-001`: keep type imports and exports consistent with the project configuration.
- `OH-TS-SECURITY-001`: do not use `eval`, `with`, or dynamic function construction.
- `OH-TS-ARRAY-001`: use array iteration methods or `for...of` instead of `for...in` for arrays.

When a rule depends on `tsconfig`, ESLint, or ArkTS compiler settings, report the missing configuration under `uncovered` rather than guessing.
