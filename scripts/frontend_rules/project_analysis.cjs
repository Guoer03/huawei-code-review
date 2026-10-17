"use strict";
// Bounded source semantics. Never evaluate a project's expressions or imports.
const fingerprints = new WeakMap();
exports.duplicateFunctions = function (ts, program, checker) {
  if (fingerprints.has(program)) return fingerprints.get(program);
  const seen = new Map(),
    duplicates = new Map();
  const roots = new Set(program.getRootFileNames());
  const symbol = (node) => {
    let s = checker.getSymbolAtLocation(node);
    if (s && s.flags & ts.SymbolFlags.Alias) s = checker.getAliasedSymbol(s);
    return s;
  };
  const visit = (node, fn) => {
    fn(node);
    ts.forEachChild(node, (n) => visit(n, fn));
  };
  function key(fn) {
    const locals = new Map();
    function bind(n) {
      if (ts.isIdentifier(n)) {
        const s = symbol(n);
        if (s && !locals.has(s)) locals.set(s, locals.size);
      } else if (ts.isObjectBindingPattern(n) || ts.isArrayBindingPattern(n)) {
        for (const element of n.elements)
          if (ts.isBindingElement(element)) bind(element.name);
      }
    }
    for (const p of fn.parameters) bind(p.name);
    visit(fn.body, (n) => {
      if (
        ts.isVariableDeclaration(n) ||
        ts.isParameter(n) ||
        (ts.isFunctionDeclaration(n) && n.name)
      )
        bind(n.name);
    });
    function encode(n) {
      if (ts.isBindingElement(n) && ts.isObjectBindingPattern(n.parent))
        return [
          "binding-property",
          n.propertyName
            ? n.propertyName.getText(n.getSourceFile())
            : ts.isIdentifier(n.name)
              ? n.name.text
              : null,
          !!n.dotDotDotToken,
          encode(n.name),
          n.initializer ? encode(n.initializer) : null,
        ];
      if (ts.isIdentifier(n)) {
        // Property names are observable keys, not alpha-renamable local names.
        const p = n.parent;
        if (
          (ts.isPropertyAccessExpression(p) && p.name === n) ||
          (ts.isPropertyAssignment(p) && p.name === n)
        )
          return ["property", n.text];
        if (ts.isShorthandPropertyAssignment(p)) return ["shorthand", n.text];
        const s = symbol(n);
        if (locals.has(s)) return ["local", locals.get(s)];
        const d = s?.declarations?.[0];
        return [
          "free",
          s?.name || n.text,
          d?.getSourceFile().fileName || n.getSourceFile().fileName,
          d?.pos,
        ];
      }
      if (
        ts.isLiteralExpression(n) ||
        [
          ts.SyntaxKind.TemplateHead,
          ts.SyntaxKind.TemplateMiddle,
          ts.SyntaxKind.TemplateTail,
        ].includes(n.kind)
      )
        return [n.kind, n.text];
      if (ts.isPrefixUnaryExpression(n) || ts.isPostfixUnaryExpression(n))
        return [n.kind, n.operator, encode(n.operand)];
      const children = [];
      ts.forEachChild(n, (c) => {
        children.push(encode(c));
      });
      return [n.kind, ...children];
    }
    if (ts.isBlock(fn.body) && fn.body.statements.length === 0) return null;
    return JSON.stringify([
      !!fn.asteriskToken,
      !!fn.modifiers?.some((m) => m.kind === ts.SyntaxKind.AsyncKeyword),
      fn.parameters.map((p) => [
        encode(p.name),
        !!p.dotDotDotToken,
        !!p.questionToken,
        p.initializer ? encode(p.initializer) : null,
      ]),
      encode(fn.body),
    ]);
  }
  for (const sf of program
    .getSourceFiles()
    .filter((s) => roots.has(s.fileName) && !s.isDeclarationFile)
    .sort((a, b) => a.fileName.localeCompare(b.fileName))) {
    visit(sf, (node) => {
      if (!ts.isFunctionLike(node) || !node.body) return;
      const value = key(node);
      if (!value) return;
      if (seen.has(value)) duplicates.set(node, seen.get(value));
      else seen.set(value, node);
    });
  }
  fingerprints.set(program, duplicates);
  return duplicates;
};

exports.incomingWrites = function (ts, checker, binding, body) {
  if (!binding || !ts.isIdentifier(binding) || !body) return [];
  const target = checker.getSymbolAtLocation(binding),
    hits = [];
  if (!target) return hits;
  const same = (n) =>
    ts.isIdentifier(n) && checker.getSymbolAtLocation(n) === target;
  function argumentsReadsBinding(node) {
    if (
      !ts.isIdentifier(node) ||
      node.text !== "arguments" ||
      !ts.isParameter(binding.parent)
    )
      return false;
    const declaration = checker.getSymbolAtLocation(node)?.valueDeclaration;
    if (
      declaration &&
      (ts.isVariableDeclaration(declaration) || ts.isParameter(declaration))
    )
      return false;
    let owner = node.parent;
    while (owner && (!ts.isFunctionLike(owner) || ts.isArrowFunction(owner)))
      owner = owner.parent;
    if (!owner || owner !== binding.parent.parent) return false;
    const parent = node.parent;
    if (
      ts.isPropertyAccessExpression(parent) &&
      parent.expression === node &&
      parent.name.text === "length"
    )
      return false;
    if (ts.isElementAccessExpression(parent) && parent.expression === node) {
      if (
        ts.isStringLiteralLike(parent.argumentExpression) &&
        parent.argumentExpression.text === "length"
      )
        return false;
      if (ts.isNumericLiteral(parent.argumentExpression))
        return (
          Number(parent.argumentExpression.text) ===
          owner.parameters.indexOf(binding.parent)
        );
    }
    return true;
  }
  function expression(node, state) {
    if (!node || !state.size) return state;
    if (argumentsReadsBinding(node)) return new Set(["read"]);
    if (
      ts.isBinaryExpression(node) &&
      node.operatorToken.kind === ts.SyntaxKind.EqualsToken &&
      same(node.left)
    ) {
      state = expression(node.right, state);
      if (state.size === 1 && state.has("unread")) hits.push(node);
      return new Set(["written"]);
    }
    if (ts.isConditionalExpression(node)) {
      state = expression(node.condition, state);
      return new Set([
        ...expression(node.whenTrue, new Set(state)),
        ...expression(node.whenFalse, new Set(state)),
      ]);
    }
    if (
      ts.isBinaryExpression(node) &&
      [
        ts.SyntaxKind.AmpersandAmpersandToken,
        ts.SyntaxKind.BarBarToken,
        ts.SyntaxKind.QuestionQuestionToken,
      ].includes(node.operatorToken.kind)
    ) {
      state = expression(node.left, state);
      return new Set([...state, ...expression(node.right, new Set(state))]);
    }
    if (same(node)) return new Set(["read"]);
    // Capturing a binding in a closure conservatively counts as using it.
    ts.forEachChild(node, (child) => {
      state = expression(child, state);
    });
    return state;
  }
  function flow(node, state) {
    if (!node || !state.size) return state;
    if (ts.isBlock(node)) {
      for (const s of node.statements) state = flow(s, state);
      return state;
    }
    if (ts.isIfStatement(node)) {
      state = expression(node.expression, state);
      return new Set([
        ...flow(node.thenStatement, new Set(state)),
        ...flow(node.elseStatement, new Set(state)),
      ]);
    }
    if (ts.isReturnStatement(node) || ts.isThrowStatement(node)) {
      expression(node.expression, state);
      return new Set();
    }
    if (
      ts.isForStatement(node) ||
      ts.isWhileStatement(node) ||
      ts.isForOfStatement(node) ||
      ts.isForInStatement(node) ||
      ts.isDoStatement(node) ||
      ts.isTryStatement(node) ||
      ts.isSwitchStatement(node)
    ) {
      // Loop/exception path feasibility is not proved. Reads suppress unsafe claims.
      expression(node, new Set(["read"]));
      return new Set(["read"]);
    }
    return expression(node, state);
  }
  flow(body, new Set(["unread"]));
  return hits;
};

exports.arrayRoot = function (ts, checker, node, seen = new Set()) {
  while (
    node &&
    (ts.isParenthesizedExpression(node) ||
      ts.isAsExpression(node) ||
      ts.isTypeAssertionExpression(node))
  )
    node = node.expression;
  if (!node || !ts.isIdentifier(node)) return null;
  const symbol = checker.getSymbolAtLocation(node);
  if (!symbol || seen.has(symbol)) return symbol || null;
  seen = new Set(seen);
  seen.add(symbol);
  const declaration = symbol.valueDeclaration;
  if (!declaration) return symbol;
  let scope = declaration.parent;
  while (scope.parent && !ts.isFunctionLike(scope) && !ts.isSourceFile(scope))
    scope = scope.parent;
  let lastWrite = null,
    uncertain = false;
  function visit(n, conditional = false) {
    if (n.pos >= node.pos || (ts.isFunctionLike(n) && n !== scope)) return;
    conditional ||=
      ts.isIfStatement(n) ||
      ts.isConditionalExpression(n) ||
      ts.isForStatement(n) ||
      ts.isForOfStatement(n) ||
      ts.isForInStatement(n) ||
      ts.isWhileStatement(n) ||
      ts.isDoStatement(n) ||
      ts.isSwitchStatement(n) ||
      ts.isTryStatement(n);
    if (
      ts.isBinaryExpression(n) &&
      n.operatorToken.kind === ts.SyntaxKind.EqualsToken &&
      ts.isIdentifier(n.left) &&
      checker.getSymbolAtLocation(n.left) === symbol &&
      n.end <= node.pos
    ) {
      if (conditional) uncertain = true;
      else {
        lastWrite = n;
        uncertain = false;
      }
    }
    ts.forEachChild(n, (child) => visit(child, conditional));
  }
  visit(scope);
  if (uncertain) return null;
  if (lastWrite)
    return ts.isIdentifier(lastWrite.right)
      ? exports.arrayRoot(ts, checker, lastWrite.right, seen)
      : lastWrite;
  if (
    ts.isVariableDeclaration(declaration) &&
    declaration.initializer &&
    ts.isIdentifier(declaration.initializer)
  )
    return exports.arrayRoot(ts, checker, declaration.initializer, seen);
  return symbol;
};

exports.mutatesArray = function (
  ts,
  checker,
  call,
  array,
  visited = new Set(),
) {
  const root = exports.arrayRoot(ts, checker, array);
  if (!root) return false;
  const prop =
    ts.isPropertyAccessExpression(call.expression) ||
    ts.isElementAccessExpression(call.expression)
      ? call.expression
      : null;
  const property =
    prop &&
    (ts.isPropertyAccessExpression(prop)
      ? prop.name.text
      : ts.isStringLiteralLike(prop.argumentExpression)
        ? prop.argumentExpression.text
        : null);
  if (
    prop &&
    ["push", "pop", "shift", "unshift", "splice"].includes(property) &&
    exports.arrayRoot(ts, checker, prop.expression) === root
  )
    return true;
  const fn = checker.getResolvedSignature(call)?.declaration;
  if (!fn?.body || fn.getSourceFile().isDeclarationFile || visited.has(fn))
    return false;
  visited = new Set(visited);
  visited.add(fn);
  const params = fn.parameters.filter(
    (p, i) =>
      !p.dotDotDotToken &&
      ts.isIdentifier(p.name) &&
      call.arguments[i] &&
      exports.arrayRoot(ts, checker, call.arguments[i]) === root,
  );
  let mutated = false;
  function visit(n) {
    if (ts.isFunctionLike(n) && n !== fn) return;
    if (
      ts.isCallExpression(n) &&
      params.some((p) => exports.mutatesArray(ts, checker, n, p.name, visited))
    )
      mutated = true;
    if (ts.isBlock(n)) {
      for (const statement of n.statements) {
        visit(statement);
        if (ts.isReturnStatement(statement) || ts.isThrowStatement(statement))
          break;
      }
      return;
    }
    ts.forEachChild(n, visit);
  }
  visit(fn.body);
  return mutated;
};
