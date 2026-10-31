# Java catalog implementation

`catalog_java.py` reads the original CodeArts rule IDs and runs a trusted JDK
compiler bridge over source files. `AstDump.java` uses `JavacTask.parse()` and
the public `com.sun.source.tree` API, with `-proc:none --release 21`.
It never invokes a project build, annotation processors, or analyzed source.
The bridge is launched in source-file mode; generated compiler artifacts stay
inside the JVM. Batch input and output files live in a temporary directory.

Runtime discovery accepts `HUAWEI_JAVA`, `JAVA_HOME`, and `PATH`; JDK 21 or newer
is required. Missing JDK, malformed source, subprocess timeout, invalid UTF-8,
invalid exported options, and detector failures are structured errors. Valid
files still produce findings when another input file is invalid. Java UTF-16
source offsets are translated to Python Unicode offsets before source slicing.

## Coverage and interpretation

The 181 original Java rules have an explicit entry in
`rulesets/implementations/java.json`: 85 implemented, 95 partial, and one manual
rule. `implemented` means the stated detector has direct syntax/structure
semantics and positive/negative cases; it is not a formal guarantee about all
possible Java programs. The UTF-8 and enum-separator rules are input/grammar
checks, whose negative cases produce structured errors rather than findings.

Partial rules disclose their implemented patterns and limitations individually.
No dependency classpaths are loaded, so external inheritance, overloads,
aliases, generic types, method results, and custom frameworks are not fully
resolved. Bounded intraprocedural taint tracks common servlet/environment
sources and a documented sink set. It has no interprocedural call graph,
path-sensitive sanitizer proof, or framework model. These findings are review
candidates, not proven exploits. Naming-based domain checks (such as monetary
floating-point variables) are also explicitly partial.

`G.ERR.05` asks whether exceptions match a method's domain abstraction level.
That requires an architecture/domain contract and is explicitly manual; there
is no substitute detector pretending to establish that fact from syntax.

Normalized severity is the explicit local policy `warning`. The unverified
CodeArts numeric severity is retained only in `raw_severity`; no guessed mapping
is made. Findings retain the original exported rule ID and user-exported source.
No automatic code rewriting is provided by these Java detectors.

Exported `maxParameterNum`, `maxMethodLength`, and `maxMethodNestedDepth` options
are honored. `maxMethodLength` counts effective declaration lines: the signature,
body, and closing line are included; blank and comment-only lines are excluded.
Comment-like text inside strings, characters, and text blocks is still treated as
code. Security thresholds absent from the export are identified as local policies
in the corresponding partial manifest entries (for example RSA 2048 and PBKDF
iteration floor 10000). They must not be described as Huawei's exact runtime
security policy.

## Verification

Run `python3.11 -m unittest discover -s tests -p test_catalog_java.py`.
The test batches 183 positive/negative case pairs through the real JDK parser,
then checks exact original rule IDs. Additional tests cover missing runtime,
mixed valid/invalid files, Unicode offsets, strings/comments, shadowed System,
and exported threshold options. The catalog fixture is evidence for implemented
patterns, not an exhaustive Java grammar corpus or a precision/recall benchmark.

`control_flow.py` composes normal and abrupt completions across branches,
loops, switches, labels, catches, and nested finally blocks. A transfer discarded
by an inner finally is not reported as escaping the outer finally. Break and
continue resolve their actual loop/label targets; exceptions use known JDK and
indexed project hierarchies. Switch expressions and yield participate in
expression evaluation. Fall-through checks ask whether the case can complete
normally and read real comment tokens. Default detection uses the JDK's
DEFAULT_CASE_LABEL identity, including Java 21 pattern and null/default labels.

The general finally and throw-specific finally rules, plus fall-through, are
implemented as structured local control-flow policies. Their boundaries remain
documented: arbitrary constant arithmetic, external method completion, unknown
external exception summaries, and implicit resource-close exceptions are not
modeled. No silent upgrade to proprietary-engine equivalence is made by adding
more examples.

Run `python3.11 -m unittest discover -s tests -p '*java*.py'` for all Java tests.
`test_java_control_flow.py` adds 58 source examples; 56 also pass isolated javac
compilation with annotation processing disabled. The remaining examples purposely
omit default from a pattern switch or reference an unavailable external exception
type. They check diagnostics without claiming those programs compile standalone.
These fixture compilations never run code or compile a user's scanned project.

The final 0.4 audit adds conservative constant folding: character literals are
normalized to their Java numeric value; expired locals, boxed identities,
floating-point conversions and ambiguous minimum-integer negation are never used
to eliminate a branch. Catch feasibility includes resource initialization/closing,
member access and possible unboxing. Exception types obtained from expired locals
are discarded rather than used to consume a possible throw. These conservative
paths can retain review candidates; they are not exact exception summaries.

Real-project validation on AgentContestBackend's 78 Java files found both the
lock-map eviction candidate in `UserOperationLockManager.java:23` and ZIP
directory-payload bypass candidate in `ZipPackageExtractor.java:57`. Original
project source was not modified. The many additional documentation, style,
and context-sensitive findings are not a count of confirmed defects.
