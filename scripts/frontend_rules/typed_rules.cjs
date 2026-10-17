"use strict";
const projectAnalysis = require("./project_analysis.cjs");
const completionFlow = require("./completion_flow.cjs");
/** Explicit syntax and bounded local-flow rules. Partial mappings are documented in mappings.json. */
function throwEscapesFinally(ts, node) {
  for (let p = node.parent; p; p = p.parent) {
    if (ts.isFunctionLike(p)) return false;
    if (ts.isTryStatement(p)) {
      if (
        p.catchClause &&
        node.pos >= p.tryBlock.pos &&
        node.end <= p.tryBlock.end
      )
        return false;
      if (
        p.finallyBlock &&
        node.pos >= p.finallyBlock.pos &&
        node.end <= p.finallyBlock.end
      )
        return true;
    }
  }
  return false;
}
exports.ignoreEslintMessage = function (ts, sf, message, checker) {
  if (message.ruleId === "no-unsafe-finally") return true; // Replaced by completion-aware AST analysis.
  if (message.ruleId === "no-self-compare") {
    const pos = sf.getPositionOfLineAndCharacter(
      message.line - 1,
      message.column - 1,
    );
    let expression;
    const locate = (n) => {
      if (pos < n.pos || pos >= n.end) return;
      if (ts.isBinaryExpression(n) && n.getStart(sf) === pos) expression = n;
      ts.forEachChild(n, locate);
    };
    locate(sf);
    let effect = false;
    const visit = (n) => {
      if (
        ts.isPropertyAccessExpression(n) ||
        ts.isElementAccessExpression(n) ||
        ts.isCallExpression(n) ||
        ts.isNewExpression(n)
      )
        effect = true;
      ts.forEachChild(n, visit);
    };
    if (expression) visit(expression);
    if (effect) return true;
  }
  if (message.ruleId === "no-use-before-define") {
    const pos = sf.getPositionOfLineAndCharacter(
      message.line - 1,
      message.column - 1,
    );
    let identifier;
    const locate = (n) => {
      if (pos < n.pos || pos >= n.end) return;
      if (ts.isIdentifier(n) && n.getStart(sf) === pos) identifier = n;
      ts.forEachChild(n, locate);
    };
    locate(sf);
    let declaration =
      identifier && checker.getSymbolAtLocation(identifier)?.valueDeclaration;
    while (declaration && ts.isBindingElement(declaration))
      declaration = declaration.parent.parent;
    return (
      !declaration ||
      !ts.isVariableDeclaration(declaration) ||
      !ts.isVariableDeclarationList(declaration.parent) ||
      !!(declaration.parent.flags & (ts.NodeFlags.Let | ts.NodeFlags.Const))
    );
  }
  if (
    message.ruleId !== "no-unsafe-finally" ||
    !message.message.includes("ThrowStatement")
  )
    return false;
  const pos = sf.getPositionOfLineAndCharacter(
    message.line - 1,
    message.column - 1,
  );
  let target;
  function locate(n) {
    if (pos < n.pos || pos >= n.end) return;
    if (ts.isThrowStatement(n) && n.getStart(sf) === pos) target = n;
    ts.forEachChild(n, locate);
  }
  locate(sf);
  return !!target && !throwEscapesFinally(ts, target);
};
exports.scan = function (ctx) {
  const { ts, sf, checker, text, filePath, rules, mappings, emit } = ctx;
  const completions = completionFlow.create(ts,checker);
  const byDetector = new Map();
  for (const r of rules) {
    const d = mappings[r.id]?.detector;
    if (d?.startsWith("typescript-ast:")) {
      const key = d.slice(15);
      if (!byDetector.has(key)) byDetector.set(key, []);
      byDetector.get(key).push(r);
    }
  }
  const has = (d) => byDetector.has(d);
  function report(d, node, message) {
    for (const r of byDetector.get(d) || [])
      emit(
        r,
        typeof node === "number" ? node : node.getStart(sf),
        message,
        "typescript-ast:" + d,
      );
  }
  const start = (n) => n.getStart(sf);
  const bindings = (n) =>
    ts.isIdentifier(n)
      ? [n]
      : ts.isObjectBindingPattern(n) || ts.isArrayBindingPattern(n)
        ? n.elements
            .filter(ts.isBindingElement)
            .flatMap((e) => bindings(e.name))
        : [];
  const unwrap = (n) =>
    ts.isParenthesizedExpression(n) ? unwrap(n.expression) : n;
  const txt = (n) => n?.getText(sf) || "";
  const line = (n) => sf.getLineAndCharacterOfPosition(start(n)).line;
  const kind = (n) => n?.kind;
  const isFn = (n) => ts.isFunctionLike(n) && !!n.body;
  const isArray = (n) => {
    if (!n) return false;
    try {
      const t = checker.getTypeAtLocation(n);
      return (
        checker.isArrayType(t) ||
        checker.isTupleType(t) ||
        (t.isUnion?.() &&
          t.types.every(
            (x) => checker.isArrayType(x) || checker.isTupleType(x),
          ))
      );
    } catch {
      return false;
    }
  };
  const isSized = (n) => {
    if (!n) return false;
    const t = checker.getTypeAtLocation(n);
    return (
      isArray(n) ||
      !!(t.flags & ts.TypeFlags.StringLike) ||
      ["Map", "Set", "ReadonlyMap", "ReadonlySet"].includes(t.symbol?.name)
    );
  };
  const typeHas = (n, flag) => !!(checker.getTypeAtLocation(n).flags & flag);
  const property = (n) =>
    ts.isPropertyAccessExpression(n)
      ? n.name.text
      : ts.isElementAccessExpression(n) &&
          n.argumentExpression &&
          ts.isStringLiteralLike(n.argumentExpression)
        ? n.argumentExpression.text
        : undefined;
  const receiver = (n) =>
    ts.isPropertyAccessExpression(n) || ts.isElementAccessExpression(n)
      ? n.expression
      : undefined;
  const name = (n) =>
    ts.isIdentifier(n) || ts.isStringLiteralLike(n) ? n.text : undefined;
  const bool = (n) =>
    n &&
    (n.kind === ts.SyntaxKind.TrueKeyword ||
      n.kind === ts.SyntaxKind.FalseKeyword);
  const number = (n) =>
    ts.isNumericLiteral(n)
      ? Number(n.text)
      : ts.isPrefixUnaryExpression(n) &&
          n.operator === ts.SyntaxKind.MinusToken &&
          ts.isNumericLiteral(n.operand)
        ? -Number(n.operand.text)
        : undefined;
  const identifierSymbol = (n) =>
    ts.isIdentifier(n) ? checker.getSymbolAtLocation(n) : undefined;
  const same = (a, b) =>
    ts.isIdentifier(a) && ts.isIdentifier(b)
      ? identifierSymbol(a) === identifierSymbol(b) && !!identifierSymbol(a)
      : normalize(a) === normalize(b);
  function normalize(n) {
    if (!n) return "";
    const scanner = ts.createScanner(
      ts.ScriptTarget.Latest,
      true,
      ts.LanguageVariant.Standard,
      txt(n),
    );
    let values = [],
      token;
    while ((token = scanner.scan()) !== ts.SyntaxKind.EndOfFileToken)
      values.push(token + ":" + scanner.getTokenText());
    return values.join("|");
  }
  function each(n, visitor, skipFunctions = false) {
    ts.forEachChild(n, (c) => {
      visitor(c);
      if (!(skipFunctions && isFn(c))) each(c, visitor, skipFunctions);
    });
  }
  function descendants(n, predicate, skipFunctions = false) {
    let result = [];
    each(
      n,
      (c) => {
        if (predicate(c)) result.push(c);
      },
      skipFunctions,
    );
    return result;
  }
  function ancestor(n, predicate) {
    for (let p = n.parent; p; p = p.parent) {
      if (predicate(p)) return p;
    }
    return null;
  }
  const mutators = new Set([
    "push",
    "pop",
    "shift",
    "unshift",
    "splice",
    "sort",
    "reverse",
    "fill",
    "copyWithin",
  ]);
  const addRemove = new Set(["push", "pop", "shift", "unshift", "splice"]);
  const arrayMembers = new Set([
    "length",
    "at",
    "concat",
    "copyWithin",
    "entries",
    "every",
    "fill",
    "filter",
    "find",
    "findIndex",
    "findLast",
    "findLastIndex",
    "flat",
    "flatMap",
    "forEach",
    "includes",
    "indexOf",
    "join",
    "keys",
    "lastIndexOf",
    "map",
    "pop",
    "push",
    "reduce",
    "reduceRight",
    "reverse",
    "shift",
    "slice",
    "some",
    "sort",
    "splice",
    "toLocaleString",
    "toString",
    "unshift",
    "values",
    "toReversed",
    "toSorted",
    "toSpliced",
    "with",
    "constructor",
  ]);
  const credentialWords = [
    "password",
    "pwd",
    "passwd",
    "secret",
    "token",
    "credential",
    "apikey",
    "api_key",
  ];
  const sensitive = (value) =>
    credentialWords.some((w) => value.toLowerCase().includes(w));
  const functionBodies = new Map();
  const literalRanges = [];
  function sourceRefs(id) {
    const sym = identifierSymbol(id);
    if (!sym) return [];
    return descendants(
      sf,
      (n) => ts.isIdentifier(n) && identifierSymbol(n) === sym && n !== id,
    );
  }
  function numericInitializer(n) {
    if (ts.isNumericLiteral(n)) return number(n);
    const sym = identifierSymbol(n);
    const decl = sym?.valueDeclaration;
    return decl && ts.isVariableDeclaration(decl) && decl.initializer
      ? number(decl.initializer)
      : undefined;
  }
  function branches(node) {
    if (ts.isIfStatement(node)) {
      const out = [];
      let cur = node;
      while (ts.isIfStatement(cur)) {
        out.push(cur.thenStatement);
        if (!cur.elseStatement) return [];
        cur = cur.elseStatement;
      }
      out.push(cur);
      return out;
    }
    if (ts.isSwitchStatement(node))
      return node.caseBlock.clauses
        .filter((c) => c.statements.length)
        .map((c) => c.statements.filter((s) => !ts.isBreakStatement(s)));
    return [];
  }
  function bodyNorm(b) {
    return Array.isArray(b)
      ? b.map(normalize).join(";")
      : ts.isBlock(b)
        ? b.statements.map(normalize).join(";")
        : normalize(b);
  }
  function overwritesInitial(binding, body) {
    if (!binding || !body) return;
    for (const identifier of bindings(binding))
      for (const assignment of projectAnalysis.incomingWrites(
        ts,
        checker,
        identifier,
        body,
      ))
        report(
          "ignored-initial-value",
          assignment,
          "Incoming value is overwritten before being read on every path reaching this assignment.",
        );
  }
  const isLoop = (n) =>
    ts.isWhileStatement(n) ||
    ts.isDoStatement(n) ||
    ts.isForStatement(n) ||
    ts.isForInStatement(n) ||
    ts.isForOfStatement(n);
  function consumesValue(n) {
    const p = n.parent;
    if (!p) return false;
    if (
      ts.isParenthesizedExpression(p) ||
      ts.isAsExpression(p) ||
      ts.isTypeAssertionExpression(p) ||
      ts.isNonNullExpression(p) ||
      ts.isAwaitExpression(p) ||
      ts.isSatisfiesExpression(p)
    )
      return consumesValue(p);
    if (ts.isConditionalExpression(p) && p.condition !== n)
      return consumesValue(p);
    if (ts.isExpressionStatement(p)) return false;
    if (
      ts.isBinaryExpression(p) &&
      p.operatorToken.kind === ts.SyntaxKind.CommaToken &&
      p.left === n
    )
      return false;
    if (
      ts.isBinaryExpression(p) &&
      [
        ts.SyntaxKind.AmpersandAmpersandToken,
        ts.SyntaxKind.BarBarToken,
        ts.SyntaxKind.QuestionQuestionToken,
        ts.SyntaxKind.CommaToken,
      ].includes(p.operatorToken.kind) &&
      p.right === n
    )
      return consumesValue(p);
    if (ts.isReturnStatement(p)) {
      const fn = ancestor(p, isFn);
      const signature = fn && checker.getSignatureFromDeclaration(fn);
      return (
        !!signature &&
        !(
          checker.getReturnTypeOfSignature(signature).flags &
          (ts.TypeFlags.Void | ts.TypeFlags.Undefined)
        )
      );
    }
    if (ts.isArrowFunction(p) && p.body === n) return false;
    return (
      (ts.isVariableDeclaration(p) && p.initializer === n) ||
      ts.isBinaryExpression(p) ||
      (ts.isCallExpression(p) && p.arguments.includes(n)) ||
      ts.isPropertyAccessExpression(p) ||
      ts.isElementAccessExpression(p) ||
      ts.isIfStatement(p) ||
      (ts.isConditionalExpression(p) && p.condition === n) ||
      (ts.isPropertyAssignment(p) && p.initializer === n) ||
      ts.isArrayLiteralExpression(p) ||
      ts.isTemplateSpan(p) ||
      ts.isSpreadElement(p) ||
      ts.isSpreadAssignment(p) ||
      ts.isComputedPropertyName(p)
    );
  }
  function checkLoopArray(array, body) {
    if (!isArray(array)) return;
    for (const call of descendants(body, (n) => ts.isCallExpression(n), true)) {
      if (projectAnalysis.mutatesArray(ts, checker, call, array))
        report(
          "array-mutation-loop",
          call,
          "Element addition/removal through this call changes the traversed array (including resolved aliases and source functions).",
        );
    }
  }
  function noSideEffect(n) {
    let unsafe = false;
    if (
      ts.isCallExpression(n) ||
      ts.isNewExpression(n) ||
      ts.isPropertyAccessExpression(n) ||
      ts.isElementAccessExpression(n)
    )
      return false;
    each(n, (c) => {
      if (
        ts.isCallExpression(c) ||
        ts.isNewExpression(c) ||
        ts.isPropertyAccessExpression(c) ||
        ts.isElementAccessExpression(c) ||
        ts.isPostfixUnaryExpression(c) ||
        (ts.isPrefixUnaryExpression(c) &&
          [ts.SyntaxKind.PlusPlusToken, ts.SyntaxKind.MinusMinusToken].includes(
            c.operator,
          )) ||
        (ts.isBinaryExpression(c) &&
          c.operatorToken.kind >= ts.SyntaxKind.FirstAssignment &&
          c.operatorToken.kind <= ts.SyntaxKind.LastAssignment)
      )
        unsafe = true;
    });
    return !unsafe;
  }
  function walk(n) {
    if (
      ts.isStringLiteralLike(n) ||
      ts.isRegularExpressionLiteral(n) ||
      [
        ts.SyntaxKind.TemplateHead,
        ts.SyntaxKind.TemplateMiddle,
        ts.SyntaxKind.TemplateTail,
      ].includes(n.kind)
    )
      literalRanges.push([start(n), n.end]);
    if (ts.isVariableDeclaration(n) || ts.isParameter(n)) {
      for (const binding of bindings(n.name))
        if (!/^_?[a-z$][a-zA-Z0-9$]*$/.test(binding.text))
          report(
            "variable-camel",
            binding,
            "Variable/parameter name should use lowerCamelCase.",
          );
      if (ts.isIdentifier(n.name)) {
        if (
          typeHas(n.name, ts.TypeFlags.BooleanLike) &&
          /^(?:not|no|non|cannot|disabled|disable|isNot|hasNo|shouldNot)(?:[A-Z_]|$)/.test(
            n.name.text,
          )
        )
          report(
            "negative-boolean",
            n.name,
            "Boolean binding uses an explicit negative naming prefix.",
          );
      }
      if (n.initializer && ts.isIdentifier(n.name)) {
        const exported = ancestor(n, (p) => ts.isVariableStatement(p));
        if (
          exported?.modifiers?.some(
            (m) => m.kind === ts.SyntaxKind.ExportKeyword,
          ) &&
          (!(exported.declarationList.flags & ts.NodeFlags.Const) ||
            ts.isObjectLiteralExpression(n.initializer) ||
            ts.isArrayLiteralExpression(n.initializer))
        )
          report(
            "mutable-export",
            n,
            "Exported binding is reassignable or holds a mutable object/array literal.",
          );
        if (ts.isStringLiteralLike(n.initializer) && n.initializer.text)
          for (const r of byDetector.get("hardcoded-credentials") || []) {
            const words =
              (r.options || []).find((o) => o.optionKey === "credentialWords")
                ?.optionValue || "password,pwd,passwd";
            if (
              words
                .split(",")
                .some((w) =>
                  n.name.text.toLowerCase().includes(w.trim().toLowerCase()),
                )
            )
              emit(
                r,
                start(n.initializer),
                "Credential-named binding contains a literal secret candidate.",
                "typescript-ast:hardcoded-credentials",
                "medium",
              );
          }
        if (
          ts.isArrayLiteralExpression(n.initializer) &&
          n.initializer.elements.length === 0 &&
          (has("empty-array-use") || has("unused-collection"))
        ) {
          const refs = sourceRefs(n.name)
            .filter((r) => r.pos > n.end)
            .sort((a, b) => a.pos - b.pos);
          let escaped = false,
            read = false,
            wrote = false;
          for (const ref of refs) {
            const parent = ref.parent;
            const call =
              parent &&
              ts.isPropertyAccessExpression(parent) &&
              ts.isCallExpression(parent.parent)
                ? parent.parent
                : null;
            const write =
              (call && mutators.has(property(call.expression))) ||
              (ts.isElementAccessExpression(parent) &&
                ts.isBinaryExpression(parent.parent) &&
                parent.parent.left === parent &&
                parent.parent.operatorToken.kind === ts.SyntaxKind.EqualsToken);
            if (write) {
              wrote = true;
              escaped = true;
              if (
                call &&
                ["pop", "shift", "splice"].includes(
                  property(call.expression),
                ) &&
                consumesValue(call)
              )
                read = true;
              continue;
            }
            if (
              ts.isElementAccessExpression(parent) ||
              (ts.isForOfStatement(parent) && parent.expression === ref) ||
              (ts.isForInStatement(parent) && parent.expression === ref)
            ) {
              const loop = ancestor(ref, isLoop);
              const loopMayMutate =
                loop &&
                refs.some(
                  (other) =>
                    other.pos >= loop.pos &&
                    other.end <= loop.end &&
                    ((ts.isPropertyAccessExpression(other.parent) &&
                      ts.isCallExpression(other.parent.parent) &&
                      mutators.has(property(other.parent.parent.expression))) ||
                      (ts.isCallExpression(other.parent) &&
                        other.parent.arguments.includes(other))),
                );
              if (!escaped && !loopMayMutate)
                report(
                  "empty-array-use",
                  ref,
                  "Local array is still empty at this read/traversal.",
                );
              read = true;
            } else if (!(
              ts.isPropertyAccessExpression(parent) && parent.name === ref
            )) {
              read = true;
              escaped = true;
            }
          }
          if (wrote && !read)
            report(
              "unused-collection",
              n,
              "Array contents are written but never read or passed outside this local binding.",
            );
        }
      }
    }
    if (
      ts.isFunctionDeclaration(n) ||
      ts.isFunctionExpression(n) ||
      ts.isMethodDeclaration(n) ||
      ts.isMethodSignature(n)
    )
      if (
        n.name &&
        ts.isIdentifier(n.name) &&
        !/^[a-z$][a-zA-Z0-9$]*$/.test(n.name.text)
      )
        report(
          "function-camel",
          n.name,
          "Function name should use lowerCamelCase.",
        );
    if (ts.isClassDeclaration(n) || ts.isClassExpression(n))
      if (n.name && !/^[A-Z][a-zA-Z0-9]*$/.test(n.name.text))
        report("class-pascal", n.name, "Class name should use UpperCamelCase.");
    if (
      ts.isNewExpression(n) &&
      ts.isIdentifier(n.expression) &&
      /^[a-z]/.test(n.expression.text)
    )
      report(
        "class-pascal",
        n.expression,
        "Named constructor call target should use UpperCamelCase.",
      );
    if (isFn(n)) {
      if (has("identical-functions")) {
        const previous = projectAnalysis
          .duplicateFunctions(ts, ctx.program, checker)
          .get(n);
        if (previous) {
          const source = previous.getSourceFile();
          const location = source.getLineAndCharacterOfPosition(
            previous.getStart(source),
          );
          report(
            "identical-functions",
            n,
            `Function implementation duplicates ${source.fileName}:${location.line + 1}, preserving literal values and resolved free symbols.`,
          );
        }
      }
      if (has("invariant-return") && completions.invariant(n)) report("invariant-return",n,"Every reachable explicit return produces the same statically known value; abrupt/finally completions and implicit undefined were considered.");
      for (const p of n.parameters) {
        overwritesInitial(p.name, n.body);
        if (ts.isIdentifier(p.name)) {
          const used = descendants(
            n.body,
            (x) =>
              ts.isPropertyAccessExpression(x) && same(x.expression, p.name),
            true,
          );
          if (new Set(used.map((x) => x.name.text)).size >= 2)
            report(
              "parameter-destructure",
              p,
              "Parameter is read through multiple direct properties; consider a destructuring parameter.",
            );
        }
      }
    }
    if (
      ts.isIfStatement(n) ||
      ts.isWhileStatement(n) ||
      ts.isDoStatement(n) ||
      ts.isForStatement(n)
    ) {
      const exp = n.expression || n.condition;
      if (exp) {
        let count = 1;
        each(exp, (x) => {
          if (
            ts.isBinaryExpression(x) &&
            [
              ts.SyntaxKind.AmpersandAmpersandToken,
              ts.SyntaxKind.BarBarToken,
            ].includes(x.operatorToken.kind)
          )
            count++;
        });
        if (
          ts.isBinaryExpression(exp) &&
          [
            ts.SyntaxKind.AmpersandAmpersandToken,
            ts.SyntaxKind.BarBarToken,
          ].includes(exp.operatorToken.kind)
        )
          count++;
        if (count > 4)
          report(
            "many-conditions",
            exp,
            "Control expression contains more than four boolean operands.",
          );
      }
      const body = ts.isIfStatement(n) ? n.thenStatement : n.statement;
      if (
        body &&
        !ts.isBlock(body) &&
        (line(body) > line(n) ||
          sf.getLineAndCharacterOfPosition(body.end).line > line(body))
      )
        report(
          "multiline-curly",
          body,
          "Body extends onto another line and needs braces.",
        );
    }
    if (
      ts.isExpressionStatement(n) &&
      ts.isBinaryExpression(unwrap(n.expression)) &&
      [
        ts.SyntaxKind.AmpersandAmpersandToken,
        ts.SyntaxKind.BarBarToken,
      ].includes(unwrap(n.expression).operatorToken.kind)
    )
      report(
        "logical-control",
        n,
        "Standalone logical expression replaces an explicit control statement.",
      );
    if (ts.isObjectLiteralExpression(n) && n.properties.length > 4) {
      let previous = line(n);
      for (const p of n.properties) {
        if (line(p) <= previous)
          report(
            "object-properties-lines",
            p,
            "Object literals with more than four properties require one property per new line.",
          );
        previous = sf.getLineAndCharacterOfPosition(p.end).line;
      }
    }
    if (
      ts.isTryStatement(n) &&
      n.catchClause &&
      sf.getLineAndCharacterOfPosition(n.tryBlock.end - 1).line !==
        line(n.catchClause)
    )
      report(
        "else-catch-line",
        n.catchClause,
        "catch should share the line of the closing try brace.",
      );
    if (ts.isIfStatement(n)) {
      if (n.elseStatement && ts.isBlock(n.thenStatement)) {
        const gap = text.slice(n.thenStatement.end, start(n.elseStatement));
        const scan = ts.createScanner(
          ts.ScriptTarget.Latest,
          true,
          ts.LanguageVariant.Standard,
          gap,
        );
        for (
          let token = scan.scan();
          token !== ts.SyntaxKind.EndOfFileToken;
          token = scan.scan()
        )
          if (token === ts.SyntaxKind.ElseKeyword) {
            const pos = n.thenStatement.end + scan.getTokenPos();
            if (
              sf.getLineAndCharacterOfPosition(n.thenStatement.end - 1).line !==
              sf.getLineAndCharacterOfPosition(pos).line
            )
              report(
                "else-catch-line",
                pos,
                "else should share the line of the closing if brace.",
              );
            break;
          }
      }
      if (
        n.elseStatement &&
        ts.isIfStatement(n.elseStatement) &&
        !(ts.isIfStatement(n.parent) && n.parent.elseStatement === n)
      ) {
        let end = n.elseStatement;
        while (end.elseStatement && ts.isIfStatement(end.elseStatement))
          end = end.elseStatement;
        if (!end.elseStatement)
          report(
            "final-else",
            end,
            "if/else-if chain has no final else branch.",
          );
      }
      if (
        n.elseStatement &&
        ts.isPrefixUnaryExpression(n.expression) &&
        n.expression.operator === ts.SyntaxKind.ExclamationToken
      )
        report(
          "inverted-boolean",
          n.expression,
          "Prefer a positive condition when both branches exist.",
        );
      const prefix = text.slice(
        text.lastIndexOf("\n", start(n) - 1) + 1,
        start(n),
      );
      if (prefix.trim() && !/else\s*$/.test(prefix))
        report(
          "conditional-newline",
          n,
          "Conditional statement should begin on a new line.",
        );
    }
    if (ts.isIfStatement(n) || ts.isSwitchStatement(n)) {
      const bs = branches(n),
        norms = bs.map(bodyNorm);
      if (norms.length > 1 && norms[0] && norms.every((x) => x === norms[0]))
        report(
          "all-identical-branches",
          n,
          "Every direct branch has the same normalized body.",
        );
      if (norms.length > 1) {
        const seen = new Set();
        for (let i = 0; i < norms.length; i++) {
          if (norms[i] && seen.has(norms[i])) {
            const b = bs[i];
            report(
              "duplicate-branch",
              Array.isArray(b) ? b[0] || n : b,
              "Branch body duplicates another branch in this conditional.",
            );
          }
          seen.add(norms[i]);
        }
      }
    }
    if (ts.isSwitchStatement(n)) {
      const count = n.caseBlock.clauses.filter(ts.isCaseClause).length;
      for (const r of byDetector.get("many-cases") || []) {
        const max = Number(
          (r.options || []).find((o) => o.optionKey === "maximum")
            ?.optionValue || 30,
        );
        if (count > max)
          emit(
            r,
            start(n),
            "Switch contains " +
              count +
              " case clauses; maximum is " +
              max +
              ".",
            "typescript-ast:many-cases",
          );
      }
      if (count < 3)
        report(
          "few-cases",
          n,
          "Switch contains fewer than three case clauses.",
        );
    }
    if (
      ts.isCaseClause(n) &&
      ts.isBinaryExpression(unwrap(n.expression)) &&
      [ts.SyntaxKind.CommaToken, ts.SyntaxKind.BarBarToken].includes(
        unwrap(n.expression).operatorToken.kind,
      )
    )
      report(
        "case-operator",
        n.expression,
        "Comma/logical OR does not define multiple switch alternatives.",
      );
    if (ts.isForStatement(n) && !n.initializer && !n.incrementor)
      report(
        "prefer-while",
        n,
        "For-loop has no initializer or increment; use while.",
      );
    if (ts.isForInStatement(n) && isArray(n.expression))
      report(
        "array-in",
        n,
        "for-in iterates array property names rather than element values.",
      );
    if (
      ts.isBinaryExpression(n) &&
      n.operatorToken.kind === ts.SyntaxKind.InKeyword &&
      isArray(n.right)
    )
      report(
        "array-in",
        n,
        "The in operator tests array indexes/properties rather than values.",
      );
    if (ts.isForStatement(n) && n.condition) {
      const candidates = [];
      const collect = (x) => {
        if (
          ts.isPropertyAccessExpression(x) &&
          x.name.text === "length" &&
          isArray(x.expression)
        )
          candidates.push(x.expression);
      };
      collect(n.condition);
      each(n.condition, collect);
      for (const array of candidates) checkLoopArray(array, n.statement);
    }
    if (ts.isForOfStatement(n)) {
      if (isArray(n.expression)) {
        report(
          "array-traversal",
          n,
          "Consider Array traversal methods where loop control semantics allow.",
        );
        checkLoopArray(n.expression, n.statement);
        for (const assignment of descendants(
          n.statement,
          (x) =>
            ts.isBinaryExpression(x) &&
            x.operatorToken.kind === ts.SyntaxKind.EqualsToken,
          true,
        )) {
          if (
            ts.isElementAccessExpression(assignment.left) &&
            same(assignment.left.expression, n.expression) &&
            ts.isNumericLiteral(assignment.left.argumentExpression)
          )
            report(
              "collection-overwrite",
              assignment,
              "Loop repeatedly writes a constant index of the iterated array.",
            );
        }
      }
      const binding = ts.isVariableDeclarationList(n.initializer)
        ? n.initializer.declarations[0]?.name
        : n.initializer;
      overwritesInitial(binding, n.statement);
    }
    if (ts.isCatchClause(n))
      overwritesInitial(n.variableDeclaration?.name, n.block);
    if (ts.isPropertyAccessExpression(n) || ts.isElementAccessExpression(n)) {
      const prop = property(n);
      if (
        prop &&
        isArray(n.expression) &&
        !arrayMembers.has(prop) &&
        !/^\d+$/.test(prop)
      )
        report(
          "array-properties",
          n,
          "Array access uses a nonnumeric, nonstandard property.",
        );
    }
    if (ts.isCallExpression(n)) {
      if (
        ["sort", "reverse"].includes(property(n.expression)) &&
        isArray(receiver(n.expression))
      ) {
        let parent = n.parent;
        while (ts.isParenthesizedExpression(parent)) parent = parent.parent;
        const target =
          ts.isVariableDeclaration(parent) && parent.initializer
            ? parent.name
            : ts.isBinaryExpression(parent) &&
                parent.operatorToken.kind === ts.SyntaxKind.EqualsToken &&
                parent.right === n
              ? parent.left
              : null;
        const source = projectAnalysis.arrayRoot(
          ts,
          checker,
          receiver(n.expression),
        );
        if (
          target &&
          source &&
          projectAnalysis.arrayRoot(ts, checker, target) !== source
        )
          report(
            "assigned-mutator",
            n,
            "sort/reverse returns the same existing array; assigning it to a different binding does not make a copy.",
          );
      }
      const prop = property(n.expression),
        obj = receiver(n.expression);
      if (prop === "forEach" && obj && n.arguments[0] && isFn(n.arguments[0]))
        checkLoopArray(obj, n.arguments[0].body);
      if (prop === "slice" && n.arguments.length === 0 && isArray(obj))
        report(
          "array-copy",
          n,
          "Array copy uses slice(); prefer spread or concat per this rule.",
        );
      if (
        ts.isIdentifier(n.expression) &&
        ["parseInt", "parseFloat"].includes(n.expression.text)
      )
        report(
          "number-conversion",
          n,
          "Numeric conversion uses " +
            n.expression.text +
            " instead of Number().",
        );
      if (ts.isIdentifier(n.expression) && n.expression.text === "Number") {
        const variable = ts.isVariableDeclaration(n.parent) ? n.parent : null;
        if (variable && ts.isIdentifier(variable.name)) {
          const refs = sourceRefs(variable.name);
          const checked = refs.some(
            (r) =>
              ts.isCallExpression(r.parent) &&
              ["isNaN", "Number.isNaN"].includes(txt(r.parent.expression)),
          );
          if (!checked)
            report(
              "number-conversion",
              n,
              "Number() result has no local direct isNaN check.",
            );
        } else
          report(
            "number-conversion",
            n,
            "Number() result has no named local value with an explicit NaN check.",
          );
      }
      if (
        prop === "postMessage" &&
        (n.arguments.length < 2 ||
          (ts.isStringLiteralLike(n.arguments[1]) &&
            n.arguments[1].text === "*"))
      )
        report(
          "postmessage-origin",
          n,
          "postMessage destination is missing or uses wildcard origin.",
        );
      if (
        prop === "setItem" &&
        obj &&
        ["localStorage", "sessionStorage"].includes(txt(obj))
      ) {
        if (n.arguments.some((x) => sensitive(txt(x))))
          report(
            "sensitive-storage",
            n,
            "Credential-named data is written to browser storage; review data sensitivity.",
          );
        if (txt(obj) === "localStorage")
          report(
            "persistent-storage",
            n,
            "Persistent localStorage write requires retention review.",
          );
      }
      if (
        ["executeSql", "put", "add"].includes(prop) &&
        n.arguments.some((x) => sensitive(txt(x)))
      )
        report(
          "sensitive-database",
          n,
          "Database write contains credential-named data; review storage policy.",
        );
      if (prop === "random" && txt(obj) === "Math")
        report(
          "weak-random",
          n,
          "Math.random is unsuitable if this value is used in a security-sensitive context.",
        );
      if (
        (["log", "info", "warn", "error", "debug"].includes(prop) ||
          (ts.isIdentifier(n.expression) &&
            ["alert", "print"].includes(n.expression.text))) &&
        n.arguments.some((x) => sensitive(txt(x)))
      )
        report(
          "sensitive-output",
          n,
          "Output sink receives a credential-named value; review potential disclosure.",
        );
      if (
        ["extractAllTo", "extract", "unzip", "extractTo", "unzipSync"].includes(
          prop || name(n.expression),
        )
      )
        report(
          "archive-extract",
          n,
          "Archive extraction requires path, expanded-size and link validation; inspect the call context.",
        );
      if (has("void-output")) {
        const t = checker.getTypeAtLocation(n);
        const p = n.parent;
        if (t.flags & ts.TypeFlags.Void && consumesValue(n))
          report(
            "void-output",
            n,
            "The result of a void-returning function is used as a value.",
          );
      }
      if (has("argument-order")) {
        const signature = checker.getResolvedSignature(n),
          params = signature?.getParameters();
        if (
          params &&
          params.length === n.arguments.length &&
          params.length > 1 &&
          n.arguments.every(ts.isIdentifier)
        ) {
          const expected = params.map((x) => x.name),
            got = n.arguments.map((x) => x.text);
          if (
            got.join(",") !== expected.join(",") &&
            [...got].sort().join(",") === [...expected].sort().join(",")
          )
            report(
              "argument-order",
              n,
              "Arguments form a permutation of declared parameter names in a different order.",
            );
        }
      }
      if (has("undefined-optional")) {
        const signature = checker.getResolvedSignature(n);
        n.arguments.forEach((arg, i) => {
          const param = signature?.getParameters()[i]?.valueDeclaration;
          if (
            ts.isIdentifier(arg) &&
            arg.text === "undefined" &&
            typeHas(arg, ts.TypeFlags.Undefined) &&
            param &&
            (param.questionToken || param.initializer) &&
            n.arguments
              .slice(i + 1)
              .every(
                (a) =>
                  ts.isIdentifier(a) &&
                  a.text === "undefined" &&
                  typeHas(a, ts.TypeFlags.Undefined),
              )
          )
            report(
              "undefined-optional",
              arg,
              "Optional parameter is explicitly passed undefined.",
            );
        });
      }
      if (has("ignored-pure-return") && ts.isExpressionStatement(n.parent)) {
        const pureString = new Set([
          "trim",
          "trimStart",
          "trimEnd",
          "toUpperCase",
          "toLowerCase",
          "substring",
          "substr",
          "slice",
          "replace",
          "replaceAll",
          "concat",
          "split",
          "normalize",
          "padStart",
          "padEnd",
        ]);
        const pureArray = new Set([
          "concat",
          "filter",
          "map",
          "slice",
          "includes",
          "indexOf",
          "join",
        ]);
        if (
          obj &&
          ((typeHas(obj, ts.TypeFlags.StringLike) && pureString.has(prop)) ||
            (isArray(obj) && pureArray.has(prop)) ||
            (txt(obj) === "Math" && prop !== "random"))
        )
          report(
            "ignored-pure-return",
            n,
            "Return value of a known pure standard-library method is discarded.",
          );
      }
    }
    if (ts.isReturnStatement(n) && n.expression) {
      if (
        ts.isPostfixUnaryExpression(n.expression) &&
        ts.isIdentifier(n.expression.operand)
      ) {
        const declaration = identifierSymbol(
          n.expression.operand,
        )?.valueDeclaration;
        const fn = ancestor(n, isFn);
        if (
          declaration &&
          fn &&
          declaration.pos > fn.pos &&
          declaration.end < fn.end
        )
          report(
            "useless-increment",
            n.expression,
            "Postfix update of a local binding is lost after returning its old value.",
          );
      }

    }
    if (ts.isExpressionStatement(n) && ts.isNewExpression(n.expression)) {
      const t = checker.getTypeAtLocation(n.expression);
      const seen = new Set();
      function isErrorType(type) {
        if (seen.has(type)) return false;
        seen.add(type);
        if (
          type.symbol?.declarations?.some((d) =>
            ctx.program.isSourceFileDefaultLibrary(d.getSourceFile()),
          ) &&
          [
            "Error",
            "TypeError",
            "RangeError",
            "SyntaxError",
            "ReferenceError",
            "URIError",
            "EvalError",
            "AggregateError",
          ].includes(type.symbol.name)
        )
          return true;
        return !!type.getBaseTypes?.()?.some(isErrorType);
      }
      if (isErrorType(t))
        report(
          "unused-error",
          n,
          "Built-in Error or its subclass is created and immediately discarded instead of thrown.",
        );
    }
    if (ts.isBinaryExpression(n)) {
      const op = n.operatorToken.kind;
      if (
        [
          ts.SyntaxKind.EqualsEqualsToken,
          ts.SyntaxKind.EqualsEqualsEqualsToken,
          ts.SyntaxKind.ExclamationEqualsToken,
          ts.SyntaxKind.ExclamationEqualsEqualsToken,
        ].includes(op)
      ) {
        const a = numericInitializer(n.left),
          b = numericInitializer(n.right);
        if (
          (a !== undefined && !Number.isInteger(a)) ||
          (b !== undefined && !Number.isInteger(b))
        )
          report(
            "float-equality",
            n,
            "Equality directly compares a value known to be fractional.",
          );
        if (
          (bool(n.left) && typeHas(n.right, ts.TypeFlags.BooleanLike)) ||
          (bool(n.right) && typeHas(n.left, ts.TypeFlags.BooleanLike))
        )
          report(
            "boolean-compare",
            n,
            "Boolean comparison against true/false is redundant.",
          );
      }
      if (
        op === ts.SyntaxKind.EqualsToken &&
        ts.isPrefixUnaryExpression(n.right) &&
        [
          ts.SyntaxKind.PlusToken,
          ts.SyntaxKind.MinusToken,
          ts.SyntaxKind.ExclamationToken,
        ].includes(n.right.operator) &&
        n.operatorToken.end === n.right.getStart(sf)
      )
        report(
          "suspicious-assignment",
          n.operatorToken,
          "Adjacent = and unary operator can be mistaken for a compound assignment.",
        );
      if (
        [
          ts.SyntaxKind.LessThanToken,
          ts.SyntaxKind.LessThanEqualsToken,
          ts.SyntaxKind.GreaterThanToken,
          ts.SyntaxKind.GreaterThanEqualsToken,
          ts.SyntaxKind.EqualsEqualsToken,
          ts.SyntaxKind.EqualsEqualsEqualsToken,
          ts.SyntaxKind.ExclamationEqualsToken,
          ts.SyntaxKind.ExclamationEqualsEqualsToken,
        ].includes(op)
      ) {
        const leftProp = property(n.left),
          rightNum = number(n.right);
        const rightProp = property(n.right),
          leftNum = number(n.left);
        let value = rightNum,
          p = leftProp,
          operator = op,
          sizedReceiver = receiver(n.left);
        if (
          !["length", "size"].includes(p) &&
          ["length", "size"].includes(rightProp)
        ) {
          value = leftNum;
          p = rightProp;
          sizedReceiver = receiver(n.right);
          operator =
            {
              [ts.SyntaxKind.LessThanToken]: ts.SyntaxKind.GreaterThanToken,
              [ts.SyntaxKind.LessThanEqualsToken]:
                ts.SyntaxKind.GreaterThanEqualsToken,
              [ts.SyntaxKind.GreaterThanToken]: ts.SyntaxKind.LessThanToken,
              [ts.SyntaxKind.GreaterThanEqualsToken]:
                ts.SyntaxKind.LessThanEqualsToken,
            }[op] || op;
        }
        if (
          isSized(sizedReceiver) &&
          ["length", "size"].includes(p) &&
          value !== undefined &&
          (value < 0 ||
            (value === 0 &&
              [
                ts.SyntaxKind.LessThanToken,
                ts.SyntaxKind.GreaterThanEqualsToken,
              ].includes(operator)))
        )
          report(
            "collection-size",
            n,
            "Collection length/size is nonnegative; this comparison is constant or impossible.",
          );
      }
      const sameRule = rules.find(
        (r) => r.id === "da6c32e46db811eea68ffa163e0fa374",
      );
      if (
        sameRule &&
        [
          ts.SyntaxKind.MinusToken,
          ts.SyntaxKind.SlashToken,
          ts.SyntaxKind.PercentToken,
          ts.SyntaxKind.AmpersandToken,
          ts.SyntaxKind.BarToken,
          ts.SyntaxKind.CaretToken,
          ts.SyntaxKind.AmpersandAmpersandToken,
          ts.SyntaxKind.BarBarToken,
        ].includes(op) &&
        noSideEffect(n.left) &&
        noSideEffect(n.right) &&
        same(unwrap(n.left), unwrap(n.right))
      )
        emit(
          sameRule,
          start(n),
          "Both binary operands are identical expressions.",
          "typescript-ast:identical-operands",
          "medium",
        );
    }
    if (
      ts.isIntersectionTypeNode(n) &&
      n.types.some(
        (t) =>
          [ts.SyntaxKind.AnyKeyword, ts.SyntaxKind.NeverKeyword].includes(
            t.kind,
          ) ||
          (ts.isTypeLiteralNode(t) && t.members.length === 0),
      )
    )
      report(
        "empty-intersection",
        n,
        "Intersection contains any, never or an empty object type.",
      );
    if (ts.isInterfaceDeclaration(n) && /^I[A-Z]/.test(n.name.text))
      report(
        "interface-prefix",
        n.name,
        "Legacy default policy forbids an I prefix on interface names.",
      );
    if (ts.isInterfaceDeclaration(n) || ts.isTypeLiteralNode(n)) {
      for (const member of n.members) {
        if (line(member) !== line(n) && !/[;,]$/.test(txt(member).trim()))
          report(
            "member-delimiter",
            member,
            "Multiline type member requires a semicolon delimiter.",
          );
      }
    }
    if (ts.isGetAccessorDeclaration(n) || ts.isSetAccessorDeclaration(n)) {
      const access = name(n.name);
      if (access && n.body) {
        const fields = descendants(
          n.body,
          (x) =>
            ts.isPropertyAccessExpression(x) &&
            x.expression.kind === ts.SyntaxKind.ThisKeyword &&
            !(ts.isCallExpression(x.parent) && x.parent.expression === x),
          true,
        );
        if (
          fields.length === 1 &&
          !["" + access, "_" + access].includes(fields[0].name.text)
        )
          report(
            "accessor-field",
            fields[0],
            "Accessor " +
              access +
              " directly accesses a differently named backing field.",
          );
      }
    }
    if (ts.isTryStatement(n) && n.finallyBlock) {
      for (const completion of completions.finallyJumps(n.finallyBlock))
        for (const r of rules.filter(r=>["da73b7006db811eea68ffa163e0fa374","da6caa4f6db811eea68ffa163e0fa374"].includes(r.id)))
          emit(r,start(completion.node),`${completion.kind} abruptly completes this finally block.`,"typescript-ast:finally-completion","high");
    }
    if (ts.isStringLiteralLike(n) && has("public-address")) {
      const matches = n.text.match(/https?:\/\/[^\s/:'"<>]+/gi) || [];
      for (const match of matches) {
        const host = match.replace(/^https?:\/\//i, "").toLowerCase();
        if (
          ["localhost", "127.0.0.1", "0.0.0.0"].includes(host) ||
          host.endsWith(".test") ||
          host.endsWith(".example") ||
          ["example.com", "example.org", "example.net"].includes(host)
        )
          continue;
        const parts = host.split(".").map(Number);
        if (
          parts.length === 4 &&
          parts.every((x) => Number.isInteger(x) && x >= 0 && x <= 255)
        ) {
          if (
            parts[0] === 10 ||
            parts[0] === 127 ||
            (parts[0] === 192 && parts[1] === 168) ||
            (parts[0] === 172 && parts[1] >= 16 && parts[1] <= 31)
          )
            continue;
        }
        report(
          "public-address",
          n,
          "String contains a public network endpoint: " + host,
        );
        break;
      }
    }
    ts.forEachChild(n, walk);
  }
  walk(sf);
  if(has("promise-try"))for(const risk of completions.promiseRisks(sf))report("promise-try",risk.node,risk.message);
  if (has("space-indent")) {
    let offset = 0;
    for (const sourceLine of text.split("\n")) {
      const leading = /^[ \t]*\t/.exec(sourceLine);
      if (leading) {
        const pos = offset + leading[0].indexOf("\t");
        if (!literalRanges.some(([begin, end]) => pos >= begin && pos < end))
          report(
            "space-indent",
            pos,
            "Code indentation contains a tab; use spaces.",
          );
      }
      offset += sourceLine.length + 1;
    }
  }
  // Comments are inspected only for comment policies, never as executable source.
  const scanner = ts.createScanner(
      ts.ScriptTarget.Latest,
      false,
      ts.LanguageVariant.Standard,
      text,
    ),
    comments = [];
  literalRanges.sort((a, b) => a[0] - b[0]);
  let literalIndex = 0;
  for (
    let token = scanner.scan();
    token !== ts.SyntaxKind.EndOfFileToken;
    token = scanner.scan()
  ) {
    const pos = scanner.getTokenPos();
    while (
      literalIndex < literalRanges.length &&
      literalRanges[literalIndex][1] <= pos
    )
      literalIndex++;
    const range = literalRanges[literalIndex];
    if (range && pos >= range[0] && pos < range[1]) {
      scanner.setTextPos(range[1]);
      continue;
    }
    if (
      [
        ts.SyntaxKind.SingleLineCommentTrivia,
        ts.SyntaxKind.MultiLineCommentTrivia,
      ].includes(token)
    )
      comments.push({
        pos,
        end: scanner.getTextPos(),
        text: scanner.getTokenText(),
      });
  }
  if (has("copyright-header")) {
    const first = sf.statements[0]?.getStart(sf) ?? text.length;
    if (
      !comments.some(
        (c) => c.pos < first && /copyright|版权所有|©/i.test(c.text),
      )
    )
      report("copyright-header", 0, "File header has no copyright notice.");
  }
  if (has("utf8")) {
    const pos = text.indexOf("\uFFFD");
    if (pos >= 0)
      report(
        "utf8",
        pos,
        "Replacement character may indicate an earlier lossy decode. Inspect original file bytes.",
      );
  }
  if (has("filename")) {
    const ext = filePath.slice(filePath.lastIndexOf("."));
    if (ext !== ext.toLowerCase())
      report("filename", 0, "Source filename extension should be lowercase.");
  }
  for (const c of comments) {
    if (
      has("personal-information") &&
      /@author\b|\bauthor\s*:|[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/i.test(
        c.text,
      )
    )
      report(
        "personal-information",
        c.pos,
        "Comment contains an author tag or email-like personal contact.",
      );
    if (
      has("comment-placement") &&
      sf.statements.length &&
      c.pos > sf.statements.at(-1).end &&
      text.slice(sf.statements.at(-1).end, c.pos).includes("\n")
    )
      report(
        "comment-placement",
        c.pos,
        "Trailing standalone comment follows the last statement; verify the intended association.",
      );
    if (has("commented-code")) {
      const body = c.text
        .replace(/^\/\/?\*?/, "")
        .replace(/\*\/$/, "")
        .trim();
      if (body) {
        const parsed = ts.createSourceFile(
          "comment.js",
          body,
          ts.ScriptTarget.Latest,
          true,
          ts.ScriptKind.JS,
        );
        if (
          !parsed.parseDiagnostics.length &&
          parsed.statements.some(
            (s) =>
              ts.isVariableStatement(s) ||
              ts.isFunctionDeclaration(s) ||
              ts.isClassDeclaration(s) ||
              ts.isIfStatement(s) ||
              ts.isForStatement(s) ||
              ts.isReturnStatement(s) ||
              (ts.isExpressionStatement(s) &&
                (ts.isCallExpression(s.expression) ||
                  ts.isBinaryExpression(s.expression))),
          )
        )
          report(
            "commented-code",
            c.pos,
            "Comment parses as executable JavaScript; remove stale code or clarify documentation intent.",
          );
      }
    }
  }
};
