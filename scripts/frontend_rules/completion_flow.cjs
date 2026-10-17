"use strict";
// Structural ECMAScript completions. No scanned expression is executed.
exports.create = function (ts, checker) {
  const normal = () => ({kind:"normal"});
  const unwrap = n => n && (ts.isParenthesizedExpression(n)||ts.isAsExpression(n)||ts.isTypeAssertionExpression(n)||ts.isNonNullExpression(n)||ts.isSatisfiesExpression(n)) ? unwrap(n.expression) : n;
  function constant(node,seen=new Set()) {
    node=unwrap(node);
    if(!node)return {known:true,value:undefined};
    if(ts.isStringLiteralLike(node))return {known:true,value:node.text};
    if(ts.isNumericLiteral(node))return {known:true,value:Number(node.text)};
    if(node.kind===ts.SyntaxKind.TrueKeyword)return {known:true,value:true};
    if(node.kind===ts.SyntaxKind.FalseKeyword)return {known:true,value:false};
    if(node.kind===ts.SyntaxKind.NullKeyword)return {known:true,value:null};
    if(ts.isPrefixUnaryExpression(node)){
      const value=constant(node.operand,seen);
      if(value.known){if(node.operator===ts.SyntaxKind.ExclamationToken)return {known:true,value:!value.value};if(node.operator===ts.SyntaxKind.PlusToken&&typeof value.value==='number')return value;if(node.operator===ts.SyntaxKind.MinusToken&&typeof value.value==='number')return {known:true,value:-value.value};}
    }
    if(ts.isIdentifier(node)){
      const symbol=checker.getSymbolAtLocation(node),decl=symbol?.valueDeclaration;
      if(node.text==='undefined'&&!decl)return {known:true,value:undefined};
      if(!seen.has(symbol)&&decl&&ts.isVariableDeclaration(decl)&&(decl.parent.flags&ts.NodeFlags.Const)&&decl.initializer){const next=new Set(seen);next.add(symbol);return constant(decl.initializer,next);}
    }
    return {known:false};
  }
  function sequence(statements) {
    let results=[normal()];
    for(const statement of statements){if(!results.some(r=>r.kind==='normal'))break;results=[...results.filter(r=>r.kind!=='normal'),...analyze(statement)];}
    return unique(results);
  }
  function unique(results){const seen=new Set();return results.filter(r=>{const key=r.kind+':'+(r.node?.pos??'')+':'+(r.label||'');if(seen.has(key))return false;seen.add(key);return true;});}
  function analyze(node, loopLabels=[]) {
    if(!node)return [normal()];
    if(ts.isBlock(node)||ts.isSourceFile(node))return sequence(node.statements);
    if(ts.isReturnStatement(node))return [{kind:'return',node,value:node.expression}];
    if(ts.isThrowStatement(node))return [{kind:'throw',node,value:node.expression}];
    if(ts.isBreakStatement(node)||ts.isContinueStatement(node))return [{kind:ts.isBreakStatement(node)?'break':'continue',node,label:node.label?.text}];
    if(ts.isIfStatement(node)){
      const condition=constant(node.expression);
      if(condition.known)return analyze(condition.value?node.thenStatement:node.elseStatement);
      return unique([...analyze(node.thenStatement),...analyze(node.elseStatement)]);
    }
    if(ts.isTryStatement(node)){
      let results=analyze(node.tryBlock);
      if(node.catchClause){const hasThrow=results.some(r=>r.kind==='throw');results=results.filter(r=>r.kind!=='throw');if(hasThrow||mayThrow(node.tryBlock))results.push(...analyze(node.catchClause.block));}
      if(node.finallyBlock){const final=analyze(node.finallyBlock);results=results.flatMap(prior=>final.map(after=>after.kind==='normal'?prior:after));}
      return unique(results);
    }
    if(ts.isLabeledStatement(node)){
      const labels=[...loopLabels,node.label.text];
      const results=analyze(node.statement,labels);
      return unique(results.map(r=>r.kind==='break'&&r.label===node.label.text?normal():r));
    }
    if(ts.isWhileStatement(node)||ts.isDoStatement(node)||ts.isForStatement(node)||ts.isForOfStatement(node)||ts.isForInStatement(node)){
      const cond=ts.isForStatement(node)?node.condition:ts.isWhileStatement(node)||ts.isDoStatement(node)?node.expression:null;
      const state=cond?constant(cond):{known:ts.isForStatement(node),value:true};
      if(state.known&&!state.value&&!ts.isDoStatement(node))return [normal()];
      let results=analyze(node.statement);const breaks=results.some(r=>r.kind==='break'&&(!r.label||loopLabels.includes(r.label)));
      const canTestCondition=results.some(r=>r.kind==='normal'||(r.kind==='continue'&&(!r.label||loopLabels.includes(r.label))));
      results=results.filter(r=>r.kind!=='normal'&&!(r.kind==='continue'&&(!r.label||loopLabels.includes(r.label)))&&!(r.kind==='break'&&(!r.label||loopLabels.includes(r.label))));
      if(breaks||((!state.known||!state.value)&&(!ts.isDoStatement(node)||canTestCondition)))results.push(normal());
      return unique(results);
    }
    if(ts.isSwitchStatement(node)){
      const clauses=node.caseBlock.clauses,results=[];
      for(let i=0;i<clauses.length;i++){const items=sequence(clauses.slice(i).flatMap(c=>[...c.statements]));results.push(...items.map(r=>r.kind==='break'&&!r.label?normal():r));}
      if(!clauses.some(ts.isDefaultClause))results.push(normal());
      return unique(results);
    }
    return [normal()];
  }
  function mayThrow(node){let result=false;function visit(n){if(ts.isFunctionLike(n))return;if(ts.isCallExpression(n)||ts.isNewExpression(n)||ts.isAwaitExpression(n)||ts.isPropertyAccessExpression(n)||ts.isElementAccessExpression(n)||ts.isThrowStatement(n))result=true;ts.forEachChild(n,visit);}visit(node);return result;}
  function reachable(node){
    let child=node;
    for(let parent=node.parent;parent;child=parent,parent=parent.parent){
      if(ts.isFunctionLike(parent))break;
      if(ts.isBlock(parent)||ts.isSourceFile(parent)){
        const index=parent.statements.indexOf(child);
        if(index>0&&!sequence(parent.statements.slice(0,index)).some(r=>r.kind==='normal'))return false;
      }
      if(ts.isIfStatement(parent)){
        const state=constant(parent.expression);
        if(state.known&&((child===parent.thenStatement&&!state.value)||(child===parent.elseStatement&&state.value)))return false;
      }
      if((ts.isWhileStatement(parent)||ts.isForStatement(parent))&&child===parent.statement){
        const state=constant(ts.isWhileStatement(parent)?parent.expression:parent.condition);
        if((ts.isWhileStatement(parent)||parent.condition)&&state.known&&!state.value)return false;
      }
      if(ts.isTryStatement(parent)&&child===parent.finallyBlock&&!analyze(parent.tryBlock).length&&!mayThrow(parent.tryBlock))return false;
    }
    return true;
  }
  function finallyJumps(node){return reachable(node)?analyze(node).filter(r=>['return','throw','break','continue'].includes(r.kind)):[];}
  function invariant(fn){
    const results=analyze(fn.body),returns=results.filter(r=>r.kind==='return');
    if(returns.length<2||results.some(r=>r.kind==='normal'||r.kind==='break'||r.kind==='continue'))return false;
    const values=returns.map(r=>constant(r.value));
    return values.every(v=>v.known)&&values.every(v=>Object.is(v.value,values[0].value));
  }
  function enclosingCatch(node){for(let p=node.parent;p;p=p.parent){if(ts.isFunctionLike(p))return null;if(ts.isTryStatement(p)&&p.catchClause&&node.pos>=p.tryBlock.pos&&node.end<=p.tryBlock.end)return p;}return null;}
  function isPromise(node){node=unwrap(node);if(!node)return false;try {const type=checker.getTypeAtLocation(node);return !(type.flags&(ts.TypeFlags.Any|ts.TypeFlags.Unknown))&&!!checker.getPropertyOfType(type,'then');}catch{return false;}}
  function property(node){return ts.isPropertyAccessExpression(node)?node.name.text:ts.isElementAccessExpression(node)&&ts.isStringLiteralLike(node.argumentExpression)?node.argumentExpression.text:null;}
  const activeHandlers=new Set();
  function handlerFunction(node,seen=new Set()){
    node=unwrap(node);if(!node)return null;
    if(ts.isArrowFunction(node)||ts.isFunctionExpression(node)||ts.isFunctionDeclaration(node))return node;
    if(ts.isIdentifier(node)){
      let symbol=checker.getSymbolAtLocation(node);
      if(symbol?.flags&ts.SymbolFlags.Alias)symbol=checker.getAliasedSymbol(symbol);
      if(!symbol||seen.has(symbol))return null;
      const next=new Set(seen);next.add(symbol);const decl=symbol.valueDeclaration;
      if(decl&&ts.isFunctionDeclaration(decl))return decl;
      if(decl&&ts.isVariableDeclaration(decl)&&(decl.parent.flags&ts.NodeFlags.Const))return handlerFunction(decl.initializer,next);
    }
    return null;
  }
  function safeHandler(node){
    const fn=handlerFunction(node);if(!fn?.body)return false;
    if(activeHandlers.has(fn))return false;
    activeHandlers.add(fn);
    try {
    if(!ts.isBlock(fn.body))return !returnedPromise(fn.body)&&!mayThrow(fn.body);
    const results=analyze(fn.body);
    if(results.some(r=>r.kind==='throw'||r.kind==='break'||r.kind==='continue'||(r.kind==='return'&&r.value&&returnedPromise(r.value))))return false;
    // A local catch may contain known throws. Other call/property effects remain unknown.
    let unknownEffect=false;
    function visit(n){
      if(n!==fn.body&&ts.isFunctionLike(n))return;
      if(!reachable(n))return;
      if(ts.isCallExpression(n)||ts.isNewExpression(n)||ts.isAwaitExpression(n)||ts.isPropertyAccessExpression(n)||ts.isElementAccessExpression(n)){
        const owner=enclosingCatch(n);
        if(!owner)unknownEffect=true;
      }
      ts.forEachChild(n,visit);
    }
    visit(fn.body);return !unknownEffect;
    } finally { activeHandlers.delete(fn); }
  }
  function explicitlyHandled(node){
    node=unwrap(node);if(!ts.isCallExpression(node))return false;
    const name=property(node.expression);
    if(name==='catch')return safeHandler(node.arguments[0]);
    if(name==='then')return safeHandler(node.arguments[1])&&(!node.arguments[0]||constant(node.arguments[0]).value==null&&constant(node.arguments[0]).known||safeHandler(node.arguments[0]));
    return false;
  }
  function returnedPromise(node,seen=new Set()){
    node=unwrap(node);if(!node||ts.isAwaitExpression(node)||explicitlyHandled(node))return false;
    if(ts.isConditionalExpression(node))return returnedPromise(node.whenTrue,seen)||returnedPromise(node.whenFalse,seen);
    if(ts.isBinaryExpression(node)&&node.operatorToken.kind===ts.SyntaxKind.CommaToken)return returnedPromise(node.right,seen);
    if(ts.isIdentifier(node)){const symbol=checker.getSymbolAtLocation(node),decl=symbol?.valueDeclaration;if(decl&&ts.isVariableDeclaration(decl)&&(decl.parent.flags&ts.NodeFlags.Const)&&decl.initializer&&!seen.has(symbol)){const next=new Set(seen);next.add(symbol);return returnedPromise(decl.initializer,next);}}
    return isPromise(node);
  }
  function promiseRisks(sf){const risks=[];function visit(node){if(!reachable(node))return;if(ts.isReturnStatement(node)&&node.expression&&enclosingCatch(node)&&returnedPromise(node.expression))risks.push({node:node.expression,message:'Promise is returned without await from a try body; its later rejection bypasses this catch.'});if(ts.isExpressionStatement(node)&&enclosingCatch(node)&&returnedPromise(node.expression))risks.push({node:node.expression,message:'Promise result is discarded in a try body; later rejection is not caught by this synchronous catch.'});ts.forEachChild(node,visit);}visit(sf);return risks;}
  return {analyze,finallyJumps,invariant,promiseRisks,constant};
};
