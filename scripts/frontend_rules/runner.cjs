"use strict";
const fs = require("node:fs");
const { createHash } = require("node:crypto");
const digest = (data) => createHash("sha256").update(data).digest("hex");
const path = require("node:path");
const { createRequire } = require("node:module");
function findRuntime() {
  const roots = [];
  if (process.env.HCR_NODE_MODULES)
    roots.push(path.resolve(process.env.HCR_NODE_MODULES, ".."));
  let base = __dirname;
  for (let i = 0; i < 7; i++) {
    roots.push(base);
    const parent = path.dirname(base);
    if (parent === base) break;
    base = parent;
  }
  roots.push(process.cwd());
  const failures = [];
  for (const root of roots) {
    try {
      const req = createRequire(path.join(root, "package.json"));
      const eslint = req("eslint");
      const parser = req("@typescript-eslint/parser");
      const plugin = req("@typescript-eslint/eslint-plugin");
      const ts = req("typescript");
      return {
        eslint,
        parser,
        plugin,
        ts,
        versions: {
          node: process.versions.node,
          eslint: req("eslint/package.json").version,
          typescript: req("typescript/package.json").version,
          typescript_eslint_parser: req(
            "@typescript-eslint/parser/package.json",
          ).version,
          typescript_eslint_plugin: req(
            "@typescript-eslint/eslint-plugin/package.json",
          ).version,
          frontend_rules_sha256: digest(
            [
              "runner.cjs",
              "typed_rules.cjs",
              "project_analysis.cjs",
              "completion_flow.cjs",
              "mappings.json",
            ]
              .map(
                (name) =>
                  name +
                  ":" +
                  digest(fs.readFileSync(path.join(__dirname, name))),
              )
              .join("\n"),
          ),
        },
      };
    } catch (e) {
      failures.push(root + ": " + e.message.split("\n")[0]);
    }
  }
  throw new Error(
    "Frontend dependencies missing. Install pinned dependencies in scripts/frontend_rules or set HCR_NODE_MODULES to a node_modules directory. " +
      failures.slice(0, 2).join("; "),
  );
}
let runtime;
try {
  runtime = findRuntime();
} catch (e) {
  if (process.argv.includes("--doctor")) {
    process.stdout.write(
      JSON.stringify({ available: false, reason: e.message }),
    );
    process.exit(0);
  }
  process.stderr.write(e.message);
  process.exit(2);
}
if (process.argv.includes("--doctor")) {
  process.stdout.write(
    JSON.stringify({ available: true, versions: runtime.versions }),
  );
  process.exit(0);
}
const mappings = JSON.parse(
  fs.readFileSync(path.join(__dirname, "mappings.json"), "utf8"),
);
const { ts, eslint, parser, plugin } = runtime;
const custom = require("./typed_rules.cjs");
const input = JSON.parse(fs.readFileSync(0, "utf8"));
const findings = [],
  errors = [];
const sources = new Map(input.files.map((f) => [path.resolve(f.path), f.text]));
let opts = {
  target: ts.ScriptTarget.Latest,
  module: ts.ModuleKind.ESNext,
  moduleResolution: ts.ModuleResolutionKind.Bundler,
  strict: true,
  allowJs: true,
  allowNonTsExtensions: true,
  checkJs: true,
  noEmit: true,
  skipLibCheck: true,
  jsx: ts.JsxEmit.Preserve,
  moduleDetection: ts.ModuleDetectionKind.Force,
};
const configs = new Set(),
  projectTypeFiles = [];
for (const file of input.files) {
  const cfg =
    process.env.HCR_TS_CONFIG ||
    ts.findConfigFile(
      path.dirname(path.resolve(file.path)),
      ts.sys.fileExists,
      "tsconfig.json",
    );
  if (cfg) configs.add(path.resolve(cfg));
}
if (configs.size > 1)
  errors.push({
    path: "<frontend-project>",
    reason:
      "Multiple tsconfig projects in one scan; use separate scans or HCR_TS_CONFIG per project. Type analysis uses the first configuration.",
  });
if (configs.size) {
  const cfg = [...configs][0];
  const raw = ts.readConfigFile(cfg, ts.sys.readFile);
  if (raw.error)
    errors.push({
      path: cfg,
      reason:
        "Cannot read tsconfig: " +
        ts.flattenDiagnosticMessageText(raw.error.messageText, " "),
    });
  else {
    const parsed = ts.parseJsonConfigFileContent(
      raw.config,
      ts.sys,
      path.dirname(cfg),
    );
    projectTypeFiles.push(
      ...parsed.fileNames.filter((p) => /\.d\.[cm]?ts$/.test(p)),
    );
    for (const d of parsed.errors.filter((d) => d.code !== 18003))
      errors.push({
        path: cfg,
        reason:
          "Invalid tsconfig: " +
          ts.flattenDiagnosticMessageText(d.messageText, " "),
      });
    opts = {
      ...opts,
      ...parsed.options,
      noEmit: true,
      allowJs: input.files.some((file) => /\.[cm]?jsx?$/i.test(file.path)),
      checkJs: input.files.some((file) => /\.[cm]?jsx?$/i.test(file.path)),
      allowNonTsExtensions: true,
    };
  }
}
const host = ts.createCompilerHost(opts, true);
const originalRead = host.readFile.bind(host),
  originalExists = host.fileExists.bind(host),
  originalDirectoryExists = host.directoryExists.bind(host),
  originalSource = host.getSourceFile.bind(host);
host.directoryExists = (p) =>
  [...sources.keys()].some((name) =>
    name.startsWith(path.resolve(p) + path.sep),
  ) || originalDirectoryExists(p);
host.readFile = (p) =>
  sources.has(path.resolve(p)) ? sources.get(path.resolve(p)) : originalRead(p);
host.fileExists = (p) => sources.has(path.resolve(p)) || originalExists(p);
host.getSourceFile = (p, ver, onError, newFile) =>
  sources.has(path.resolve(p))
    ? ts.createSourceFile(p, sources.get(path.resolve(p)), ver, true)
    : originalSource(p, ver, onError, newFile);
const program = ts.createProgram(
  [...new Set([...sources.keys(), ...projectTypeFiles])],
  opts,
  host,
);
const checker = program.getTypeChecker();
for (const diagnostic of [
  ...program.getOptionsDiagnostics(),
  ...program.getGlobalDiagnostics(),
]) {
  errors.push({
    path:
      diagnostic.file?.fileName || [...configs][0] || "<typescript-project>",
    reason:
      "Incomplete TypeScript project: " +
      ts.flattenDiagnosticMessageText(diagnostic.messageText, " "),
    diagnostic_code: diagnostic.code,
  });
}
const linter = new eslint.Linter({ cwd: path.parse(process.cwd()).root });
const dedup = new Set();
for (const file of input.files) {
  const actualPath = path.resolve(file.path);
  const language =
    file.language ||
    (/\.(?:ts|tsx|mts|cts|ets)$/i.test(file.path)
      ? "typescript"
      : "javascript");
  const rules = input.rules.filter(
    (r) => r.language.toLowerCase() === language,
  );
  const sf = program.getSourceFile(actualPath);
  if (!sf) {
    errors.push({
      path: file.path,
      reason: "TypeScript parser did not create source file",
    });
    continue;
  }
  const syntax = program.getSyntacticDiagnostics(sf);
  if (syntax.length) {
    for (const d of syntax.slice(0, 10))
      errors.push({
        path: file.path,
        reason:
          "Syntax error: " +
          ts.flattenDiagnosticMessageText(d.messageText, " "),
        line: sf.getLineAndCharacterOfPosition(d.start || 0).line + 1,
      });
    continue;
  }
  const incompleteTypes = program
    .getSemanticDiagnostics(sf)
    .filter((d) => [2307, 2792, 7016, 6053, 2688].includes(d.code));
  for (const d of incompleteTypes)
    errors.push({
      path: file.path,
      reason:
        "Incomplete type analysis: " +
        ts.flattenDiagnosticMessageText(d.messageText, " "),
      line: sf.getLineAndCharacterOfPosition(d.start || 0).line + 1,
    });
  const lines = file.text.split(/\r?\n/);
  function emit(rule, pos, message, detector, confidence = "high") {
    const m = mappings[rule.id];
    const lc = sf.getLineAndCharacterOfPosition(
      Math.max(0, Math.min(pos, file.text.length)),
    );
    const key = [rule.id, file.path, lc.line, lc.character].join(":");
    if (dedup.has(key)) return;
    dedup.add(key);
    findings.push({
      id: rule.id,
      path: file.path,
      line: lc.line + 1,
      column: lc.character + 1,
      language,
      severity: detector.startsWith("eslint:") ? "error" : "warning",
      severity_policy: detector.startsWith("eslint:")
        ? "local-eslint-config-error"
        : "local-ast-warning",
      raw_severity: rule.severity,
      confidence: m.status === "partial" ? "low" : confidence,
      title: rule.nameCn || rule.name,
      message,
      evidence: (lines[lc.line] || "").trim(),
      source: { id: "codearts-user-export", status: "user-exported" },
      coverage_status: m.status,
      detector,
      fix: { autofixable: false },
    });
  }
  const eslintRules = {};
  const backmap = new Map();
  for (const rule of rules) {
    const mapping = mappings[rule.id];
    if (!mapping) {
      errors.push({
        path: file.path,
        reason: "No executable mapping for exported rule " + rule.id,
      });
      continue;
    }
    for (const [name, options] of Object.entries(mapping.rules)) {
      eslintRules[name] = options;
      if (!backmap.has(name)) backmap.set(name, []);
      backmap.get(name).push(rule);
    }
  }
  try {
    const config = {
      files: ["**/*.{js,jsx,mjs,cjs,ts,tsx,mts,cts,ets,JS,JSX,TS,TSX}"],
      languageOptions: {
        parser,
        ecmaVersion: "latest",
        sourceType: ts.isExternalModule(
          ts.createSourceFile(
            actualPath,
            file.text,
            ts.ScriptTarget.Latest,
            true,
          ),
        )
          ? "module"
          : "script",
        globals: {
          setTimeout: "readonly",
          setInterval: "readonly",
          window: "readonly",
          global: "readonly",
          self: "readonly",
          console: "readonly",
          localStorage: "readonly",
          sessionStorage: "readonly",
          alert: "readonly",
        },
        parserOptions: {
          programs: [program],
          projectService: false,
          extraFileExtensions: [".JS", ".JSX", ".TS", ".TSX", ".ets"],
          tsconfigRootDir: path.parse(actualPath).root,
          ecmaFeatures: { jsx: true },
        },
      },
      plugins: { "@typescript-eslint": plugin },
      rules: eslintRules,
      linterOptions: { noInlineConfig: true },
    };
    // File selection belongs to the CLI. Explicitly selected dependency source
    // must not be silently discarded by ESLint's default node_modules ignore.
    const messages = linter.verify(
      file.text,
      [{ ignores: ["!**/node_modules/", "!**/node_modules/**"] }, config],
      {
        filename: actualPath,
        allowInlineConfig: false,
      },
    );
    for (const message of messages) {
      if (message.fatal || !message.ruleId) {
        errors.push({
          path: file.path,
          reason: message.message,
          line: message.line || 1,
        });
        continue;
      }
      if (custom.ignoreEslintMessage(ts, sf, message, checker)) continue;
      for (const rule of backmap.get(message.ruleId) || []) {
        const allowedMessages = mappings[rule.id].message_ids?.[message.ruleId];
        if (allowedMessages && !allowedMessages.includes(message.messageId))
          continue;
        const lineStart = sf.getPositionOfLineAndCharacter(
          Math.max(0, message.line - 1),
          Math.max(0, (message.column || 1) - 1),
        );
        emit(rule, lineStart, message.message, "eslint:" + message.ruleId);
      }
    }
  } catch (e) {
    errors.push({
      path: file.path,
      reason: "ESLint failed: " + e.message.slice(0, 1800),
    });
  }
  try {
    custom.scan({
      ts,
      sf,
      checker,
      program,
      text: file.text,
      filePath: file.path,
      rules,
      mappings,
      emit,
    });
  } catch (e) {
    errors.push({
      path: file.path,
      reason: "Typed AST detector failed: " + e.stack,
    });
  }
}
findings.sort(
  (a, b) =>
    a.path.localeCompare(b.path) ||
    a.line - b.line ||
    a.column - b.column ||
    a.id.localeCompare(b.id),
);
process.stdout.write(
  JSON.stringify({
    findings,
    errors,
    engines: runtime.versions,
    type_context: {
      configurations: [...configs],
      configuration_sha256: [...configs].map((p) => ({
        path: p,
        sha256: ts.sys.fileExists(p) ? digest(fs.readFileSync(p)) : null,
      })),
      compiler_options_sha256: digest(
        JSON.stringify(
          Object.fromEntries(
            Object.entries(opts).sort(([a], [b]) => a.localeCompare(b)),
          ),
        ),
      ),
      project_declaration_files: projectTypeFiles.length,
      declaration_files: program
        .getSourceFiles()
        .filter((f) => f.isDeclarationFile).length,
      declaration_files_sha256: digest(
        program
          .getSourceFiles()
          .filter((f) => f.isDeclarationFile)
          .map((f) => f.fileName + ":" + digest(f.text))
          .sort()
          .join("\n"),
      ),
      source_files: input.files.length,
    },
  }),
);
