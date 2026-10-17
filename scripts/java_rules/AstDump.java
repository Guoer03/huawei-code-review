import java.io.*;
import java.nio.file.*;
import java.util.*;
import javax.tools.*;
import com.sun.source.tree.*;
import com.sun.source.util.*;

/** Syntax-only javac bridge: never executes analyzed code or annotation processors. */
class AstDump {
    static class Dump extends TreeScanner<Void, Integer> {
        final CompilationUnitTree unit;
        final SourcePositions positions;
        final DocTrees docs;
        final List<Map<String,Object>> nodes = new ArrayList<>();
        final IdentityHashMap<Tree,Integer> ids = new IdentityHashMap<>();
        Dump(CompilationUnitTree u, JavacTask task) {unit=u; positions=Trees.instance(task).getSourcePositions(); docs=DocTrees.instance(task);}
        int id(Tree t) {if(t==null)return -1; return ids.computeIfAbsent(t, k->ids.size());}
        List<Integer> refs(List<? extends Tree> ts) {List<Integer> r=new ArrayList<>(); for(Tree t:ts)r.add(id(t));return r;}
        @Override public Void scan(Tree t, Integer parent) {
            if(t==null)return null;
            Map<String,Object> n=new LinkedHashMap<>(); nodes.add(n);
            n.put("id",id(t));n.put("parent",parent==null?-1:parent);n.put("kind",t.getKind().toString());
            long start=positions.getStartPosition(unit,t),end=positions.getEndPosition(unit,t);
            n.put("start",start);n.put("end",end);
            n.put("line",start<0?1:unit.getLineMap().getLineNumber(start));
            n.put("column",start<0?1:unit.getLineMap().getColumnNumber(start));
            if(t instanceof ClassTree x){n.put("name",x.getSimpleName().toString()); n.put("mods",x.getModifiers().getFlags().toString());n.put("modifiers",id(x.getModifiers()));n.put("annotations",refs(x.getModifiers().getAnnotations()));n.put("typeParameters",refs(x.getTypeParameters()));n.put("members",refs(x.getMembers()));n.put("implements",refs(x.getImplementsClause()));n.put("extends",id(x.getExtendsClause()));}
            if(t instanceof MethodTree x){n.put("name",x.getName().toString());n.put("mods",x.getModifiers().getFlags().toString());n.put("modifiers",id(x.getModifiers()));n.put("annotations",refs(x.getModifiers().getAnnotations()));n.put("typeParameters",refs(x.getTypeParameters()));n.put("params",refs(x.getParameters()));n.put("throws",refs(x.getThrows()));n.put("returnType",id(x.getReturnType()));n.put("body",id(x.getBody()));}
            if(t instanceof VariableTree x){n.put("name",x.getName().toString());n.put("mods",x.getModifiers().getFlags().toString());n.put("modifiers",id(x.getModifiers()));n.put("annotations",refs(x.getModifiers().getAnnotations()));n.put("type",id(x.getType()));n.put("initializer",id(x.getInitializer()));}
            if(t instanceof IdentifierTree x)n.put("name",x.getName().toString());
            if(t instanceof MemberSelectTree x){n.put("name",x.getIdentifier().toString());n.put("expr",id(x.getExpression()));}
            if(t instanceof MethodInvocationTree x){n.put("select",id(x.getMethodSelect()));n.put("args",refs(x.getArguments()));}
            if(t instanceof NewClassTree x){n.put("type",id(x.getIdentifier()));n.put("args",refs(x.getArguments()));n.put("body",id(x.getClassBody()));}
            if(t instanceof NewArrayTree x){n.put("type",id(x.getType()));n.put("dimensions",refs(x.getDimensions()));if(x.getInitializers()!=null)n.put("initializers",refs(x.getInitializers()));}
            if(t instanceof LiteralTree x)n.put("value",x.getValue());
            if(t instanceof BinaryTree x){n.put("left",id(x.getLeftOperand()));n.put("right",id(x.getRightOperand()));}
            if(t instanceof AssignmentTree x){n.put("variable",id(x.getVariable()));n.put("expr",id(x.getExpression()));}
            if(t instanceof CompoundAssignmentTree x){n.put("variable",id(x.getVariable()));n.put("expr",id(x.getExpression()));}
            if(t instanceof UnaryTree x)n.put("expr",id(x.getExpression()));
            if(t instanceof ParenthesizedTree x)n.put("expr",id(x.getExpression()));
            if(t instanceof ReturnTree x)n.put("expr",id(x.getExpression()));
            if(t instanceof YieldTree x)n.put("expr",id(x.getValue()));
            if(t instanceof ThrowTree x)n.put("expr",id(x.getExpression()));
            if(t instanceof BreakTree x)n.put("label",x.getLabel()==null?null:x.getLabel().toString());
            if(t instanceof ContinueTree x)n.put("label",x.getLabel()==null?null:x.getLabel().toString());
            if(t instanceof LabeledStatementTree x){n.put("label",x.getLabel().toString());n.put("body",id(x.getStatement()));}
            if(t instanceof TypeCastTree x){n.put("type",id(x.getType()));n.put("expr",id(x.getExpression()));}
            if(t instanceof ConditionalExpressionTree x){n.put("condition",id(x.getCondition()));n.put("true",id(x.getTrueExpression()));n.put("false",id(x.getFalseExpression()));}
            if(t instanceof IfTree x){n.put("condition",id(x.getCondition()));n.put("then",id(x.getThenStatement()));n.put("else",id(x.getElseStatement()));}
            if(t instanceof ForLoopTree x){n.put("condition",id(x.getCondition()));n.put("initializers",refs(x.getInitializer()));n.put("updates",refs(x.getUpdate()));n.put("body",id(x.getStatement()));}
            if(t instanceof EnhancedForLoopTree x){n.put("variable",id(x.getVariable()));n.put("expr",id(x.getExpression()));n.put("body",id(x.getStatement()));}
            if(t instanceof WhileLoopTree x){n.put("condition",id(x.getCondition()));n.put("body",id(x.getStatement()));}
            if(t instanceof DoWhileLoopTree x){n.put("condition",id(x.getCondition()));n.put("body",id(x.getStatement()));}
            if(t instanceof SwitchTree x){n.put("expr",id(x.getExpression()));n.put("cases",refs(x.getCases()));}
            if(t instanceof SwitchExpressionTree x){n.put("expr",id(x.getExpression()));n.put("cases",refs(x.getCases()));}
            if(t instanceof CaseTree x){n.put("labels",refs(x.getExpressions()));n.put("hasDefault",x.getLabels().stream().anyMatch(label->label.getKind()==Tree.Kind.DEFAULT_CASE_LABEL));n.put("caseKind",x.getCaseKind().toString());if(x.getStatements()!=null)n.put("statements",refs(x.getStatements()));n.put("body",id(x.getBody()));}
            if(t instanceof BlockTree x){n.put("statements",refs(x.getStatements()));n.put("static",x.isStatic());}
            if(t instanceof TryTree x){n.put("body",id(x.getBlock()));n.put("catches",refs(x.getCatches()));n.put("finally",id(x.getFinallyBlock()));n.put("resources",refs(x.getResources()));}
            if(t instanceof CatchTree x){n.put("parameter",id(x.getParameter()));n.put("body",id(x.getBlock()));}
            if(t instanceof SynchronizedTree x){n.put("expr",id(x.getExpression()));n.put("body",id(x.getBlock()));}
            if(t instanceof ImportTree x){n.put("name",x.getQualifiedIdentifier().toString());n.put("static",x.isStatic());}
            if(t instanceof AnnotationTree x)n.put("name",x.getAnnotationType().toString());
            if(t instanceof TypeParameterTree x){n.put("name",x.getName().toString());n.put("bounds",refs(x.getBounds()));}
            if(t instanceof ExpressionStatementTree x)n.put("expr",id(x.getExpression()));
            if(t instanceof ArrayAccessTree x){n.put("expr",id(x.getExpression()));n.put("index",id(x.getIndex()));}
            if(t instanceof InstanceOfTree x){n.put("expr",id(x.getExpression()));n.put("type",id(x.getType()));}
            if(t instanceof ClassTree || t instanceof MethodTree || t instanceof VariableTree){
                TreePath path=TreePath.getPath(unit,t);String doc=path==null?null:docs.getDocComment(path);n.put("doc",doc);
            }
            return super.scan(t,id(t));
        }
    }
    static String json(Object x) {
        if(x==null)return "null";
        if(x instanceof Map<?,?> m){StringJoiner j=new StringJoiner(",","{","}");for(var e:m.entrySet())j.add(json(e.getKey().toString())+":"+json(e.getValue()));return j.toString();}
        if(x instanceof Collection<?> a){StringJoiner j=new StringJoiner(",","[","]");for(Object e:a)j.add(json(e));return j.toString();}
        if(x instanceof Number || x instanceof Boolean)return x.toString();
        StringBuilder b=new StringBuilder("\"");for(char c:x.toString().toCharArray()){switch(c){case '"':b.append("\\\"");break;case '\\':b.append("\\\\");break;case '\n':b.append("\\n");break;case '\r':b.append("\\r");break;case '\t':b.append("\\t");break;default:if(c<32)b.append(String.format("\\u%04x",(int)c));else b.append(c);}}return b.append('"').toString();
    }
    public static void main(String[] args) throws Exception {
        JavaCompiler compiler=ToolProvider.getSystemJavaCompiler();
        if(compiler==null)throw new IllegalStateException("A JDK with jdk.compiler is required");
        DiagnosticCollector<JavaFileObject> diagnostics=new DiagnosticCollector<>();
        try(StandardJavaFileManager manager=compiler.getStandardFileManager(diagnostics,Locale.ROOT,java.nio.charset.StandardCharsets.UTF_8)){
            List<Path> paths=Files.readAllLines(Path.of(args[0])).stream().map(Path::of).toList();
            JavacTask task=(JavacTask)compiler.getTask(null,manager,diagnostics,List.of("-proc:none","--release","21"),null,manager.getJavaFileObjectsFromPaths(paths));
            List<Object> files=new ArrayList<>();for(CompilationUnitTree u:task.parse()){Dump d=new Dump(u,task);d.scan(u,null);Map<String,Object> f=new LinkedHashMap<>();f.put("path",Path.of(u.getSourceFile().toUri()).toString());f.put("package",u.getPackageName()==null?"":u.getPackageName().toString());f.put("nodes",d.nodes);files.add(f);}
            List<Object> errors=new ArrayList<>();for(var d:diagnostics.getDiagnostics())if(d.getKind()==Diagnostic.Kind.ERROR){Map<String,Object> e=new LinkedHashMap<>();e.put("path",d.getSource()==null?"":Path.of(d.getSource().toUri()).toString());e.put("line",d.getLineNumber());e.put("reason",d.getMessage(Locale.ROOT));errors.add(e);}
            System.out.print(json(Map.of("files",files,"errors",errors)));
        }
    }
}
