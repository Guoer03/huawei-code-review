# Java rule profile

Source: `huawei-java-mirror`, a community mirror of the downloaded Huawei Java document. Apply these rules when the project selects the Huawei Java profile; label the source as a mirror.

- `HUAWEI-JAVA-FORMAT-001`: use four spaces, never tabs, for indentation.
- `HUAWEI-JAVA-FORMAT-002`: keep one statement per line and brace control-flow bodies.
- `HUAWEI-JAVA-FORMAT-003`: split long statements; the historical document uses 80 characters as its trigger.
- `HUAWEI-JAVA-DOC-001`: public/protected classes, fields, and methods need useful Javadoc with parameters, return values, and declared exceptions where applicable.
- `HUAWEI-JAVA-SWITCH-001`: each switch case should terminate with `break`, unless intentional fall-through is explicitly documented.

Use compiler and project Checkstyle results when available. Do not infer a 30% comment ratio from a small snippet; report it only as an advisory project-level metric.
