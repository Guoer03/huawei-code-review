"""Reusable, deterministic Huawei/OpenHarmony code review engine."""
from __future__ import annotations

from dataclasses import dataclass
import json
import re
import sys
import tokenize
from pathlib import Path
from typing import Iterable, Pattern

try:
    from .config import Config, ConfigError, load_config, path_is_ignored
    from .python_tokens import code_only
    from .java_checks import java_rule_positions
except ImportError:  # direct ``python scripts/check.py`` execution
    from config import Config, ConfigError, load_config, path_is_ignored
    from python_tokens import code_only
    from java_checks import java_rule_positions

SOURCE = {
    "java": {"id": "huawei-java-mirror", "status": "community-mirror"},
    "javascript": {"id": "openharmony-javascript", "status": "official-public"},
    "typescript": {"id": "openharmony-ts-js", "status": "official-public"},
    "python": {"id": "huawei-python-community", "status": "community"},
}

@dataclass(frozen=True)
class Rule:
    id: str
    language: str
    severity: str
    pattern: Pattern[str]
    message: str
    title: str | None = None
    confidence: str = "high"
    autofixable: bool = False

    def to_dict(self) -> dict:
        return {"id": self.id, "language": self.language, "severity": self.severity,
                "message": self.message, "title": self.title or self.message.split(".")[0],
                "confidence": self.confidence, "autofixable": self.autofixable}


def _r(rule_id: str, language: str, severity: str, expression: str, message: str, **kwargs) -> Rule:
    return Rule(rule_id, language, severity, re.compile(expression), message, **kwargs)

RULES: dict[str, list[Rule]] = {
    "java": [_r("HUAWEI-JAVA-FORMAT-001", "java", "error", r"\t", "Use four spaces, not tabs, for Java indentation."),
             _r("HUAWEI-JAVA-FORMAT-002", "java", "warning", r"^\s*(if|for|while|switch)\s*\([^)]*\)\s*[^\s{].*", "Control-flow bodies should use braces."),
             _r("HUAWEI-JAVA-SWITCH-001", "java", "info", r"\bcase\s+[^:]+:", "Review classic switch case termination and intentional fall-through; this is not a confirmed missing break.", confidence="low")],
    "javascript": [_r("OH-JS-DECL-001", "javascript", "error", r"\bvar\s+[A-Za-z_$]", "Use const or let instead of var."),
                    _r("OH-JS-SECURITY-001", "javascript", "error", r"\beval\s*\(|\bwith\s*\(|new\s+Function\s*\(", "Avoid eval, with, and dynamic function construction."),
                    _r("OH-JS-FORMAT-001", "javascript", "warning", r"\t", "Use two spaces instead of tab indentation."),
                    _r("OH-JS-EQUALITY-001", "javascript", "warning", r"(?<![=!])==(?!=)|(?<![=!])!=(?!=)", "Prefer strict equality operators."),
                    _r("OH-JS-FORMAT-002", "javascript", "warning", r".{121}", "Keep source lines within 120 characters.")],
    "typescript": [_r("OH-TS-DECL-001", "typescript", "error", r"\bvar\s+[A-Za-z_$]", "Use const or let instead of var."),
                    _r("OH-TS-TYPE-001", "typescript", "warning", r"\bany\b", "Avoid any when a precise type is available."),
                    _r("OH-TS-SECURITY-001", "typescript", "error", r"\beval\s*\(|\bwith\s*\(|new\s+Function\s*\(", "Avoid dynamic code execution."),
                    _r("OH-TS-ARRAY-001", "typescript", "warning", r"\bfor\s*\([^;]+\s+in\s+[A-Za-z_$][\w$]*\s*\)", "Do not use for...in to iterate arrays.")],
    "python": [_r("HUAWEI-PY-FORMAT-001", "python", "error", r"\t", "Use four spaces and do not mix tabs with spaces."),
                _r("HUAWEI-PY-FORMAT-002", "python", "warning", r".{81}", "Keep source lines within 80 characters unless an exception is documented."),
                _r("HUAWEI-PY-IMPORT-001", "python", "warning", r"^\s*(from\s+\S+\s+import\s+\*|import\s+\S+\s*,)", "Avoid wildcard or multi-module imports."),
                _r("HUAWEI-PY-STYLE-001", "python", "warning", r"^\s*def\s+[A-Z]", "Use snake_case for function names."),
                _r("HUAWEI-PY-QUALITY-001", "python", "info", r"\bfor\s+\w+\s+in\s+range\s*\(\s*len\(", "Prefer direct iteration when the index is not needed.")],
}

EXTENSIONS = {".java": "java", ".js": "javascript", ".jsx": "javascript",
              ".mjs": "javascript", ".cjs": "javascript", ".ts": "typescript",
              ".tsx": "typescript", ".mts": "typescript", ".cts": "typescript",
              ".ets": "typescript", ".py": "python"}
SHEBANGS = (("python", "python"), ("node", "javascript"), ("deno", "javascript"))


def language_for(path: str, explicit: str = "auto", text: str = "") -> str:
    if explicit != "auto":
        return explicit if explicit in RULES else ""
    suffix = Path(path).suffix.lower()
    if suffix in EXTENSIONS:
        return EXTENSIONS[suffix]
    first = text.splitlines()[0].lower() if text.splitlines() else ""
    return next((lang for marker, lang in SHEBANGS if marker in first), "")


def files_for(inputs: Iterable[str], excludes: Iterable[str] = (), include_hidden: bool = False):
    found: list[tuple[str, str]] = []
    uncovered: list[dict] = []
    excluded = tuple(excludes)
    for raw in inputs:
        if raw == "-":
            found.append(("<stdin>", sys.stdin.read()))
            continue
        path = Path(raw)
        if not path.exists():
            uncovered.append({'path': str(path), 'reason': 'input path does not exist'})
            continue
        paths = path.rglob("*") if path.is_dir() else [path]
        for item in paths:
            if not item.is_file() or (item.name.startswith(".") and not include_hidden):
                continue
            if not include_hidden and any(part.startswith(".") for part in item.relative_to(path).parts):
                continue
            # Directory scans are source-oriented: documentation, lockfiles,
            # and binaries are outside the language coverage contract. Keep
            # extensionless executable scripts when their shebang identifies
            # a supported language.
            if path.is_dir() and item.suffix.lower() not in EXTENSIONS:
                if item.suffix:
                    continue
                try:
                    with item.open(encoding="utf-8") as source_file:
                        first_line = source_file.readline()
                except (UnicodeDecodeError, OSError):
                    continue
                if not first_line.startswith("#!") or not language_for(str(item), "auto", first_line):
                    continue
            if any(part in excluded or path_is_ignored(item, excluded, path if path.is_dir() else path.parent) for part in item.parts):
                continue
            try:
                with item.open(encoding="utf-8", newline="") as source_file:
                    found.append((str(item), source_file.read()))
            except (UnicodeDecodeError, OSError) as exc:
                uncovered.append({"path": str(item), "reason": f"cannot read file: {exc}"})
    return found, uncovered


def _severity_overrides(config: Config) -> dict[str, str]:
    result = {}
    for item in config.ignore:
        if item.startswith("__severity__:") and "=" in item:
            rule_id, severity = item[len("__severity__:"):].split("=", 1)
            if severity in {"info", "warning", "error"}:
                result[rule_id] = severity
    return result


def _ignored_rule_ids(patterns: Iterable[str]) -> set[str]:
    """Extract rule IDs from ignore options while leaving path globs intact."""
    known = {rule.id for rules in RULES.values() for rule in rules}
    return {item for item in patterns if item in known}


def check_legacy(inputs: Iterable[str], language: str = "auto", profile: str = "balanced", config: Config | None = None,
          excludes: Iterable[str] | None = None, ignore: Iterable[str] | None = None,
          fail_on: str | None = None, allow_uncovered: bool | None = None) -> dict:
    """Scan files and return the stable report schema used by CLI and adapters."""
    config = config or Config(language=language, profile=profile)
    selected_language = language if language != "auto" else config.language
    all_excludes = list(config.exclude) + list(excludes or [])
    all_ignore = list(config.ignore) + list(ignore or [])
    ignored_rule_ids = _ignored_rule_ids(all_ignore)
    files, uncovered = files_for(inputs, all_excludes, config.include_hidden)
    findings: list[dict] = []
    checked = 0
    severity_overrides = _severity_overrides(config)
    for path, text in files:
        lang = language_for(path, selected_language, text)
        if not lang:
            uncovered.append({"path": path, "reason": "language could not be inferred"})
            continue
        checked += 1
        code_lines = None
        java_positions = java_rule_positions(text) if lang == 'java' else None
        if lang == 'python':
            try:
                code_lines = code_only(text).splitlines()
            except (tokenize.TokenError, IndentationError, SyntaxError) as exc:
                uncovered.append({'path': path, 'reason': f'Python tokenization failed: {exc}'})
                continue
        active = RULES[lang]
        if config.enabled_rules is not None:
            active = [rule for rule in active if rule.id in config.enabled_rules]
        active = [rule for rule in active if rule.id not in config.disabled_rules]
        for number, line in enumerate(text.splitlines(), 1):
            for rule in active:
                scanned_line = (code_lines[number - 1] if code_lines is not None
                                and rule.id != 'HUAWEI-PY-FORMAT-002' else line)
                if java_positions is not None and rule.id in java_positions:
                    columns = [col for row, col in java_positions[rule.id] if row == number]
                    if not columns:
                        continue
                else:
                    match = rule.pattern.search(scanned_line)
                    if not match:
                        continue
                    columns = [match.start() + 1]
                if rule.id in ignored_rule_ids:
                    continue
                # Supports ``# huawei-ignore`` and ``# huawei-ignore RULE-ID``.
                marker = re.search(r"huawei-ignore(?:\s+([A-Za-z0-9_-]+))?", line, re.I)
                if marker and (not marker.group(1) or marker.group(1) == rule.id):
                    continue
                if path_is_ignored(path, all_ignore):
                    continue
                severity = severity_overrides.get(rule.id, rule.severity)
                for column in columns:
                    findings.append({"id": rule.id, "language": lang, "path": path, "line": number,
                        "column": column, "severity": severity, "confidence": rule.confidence,
                        "title": rule.title or rule.message.split(".")[0], "message": rule.message,
                        "evidence": line.strip()[:240], "source": SOURCE[lang],
                        "fix": {"description": "Review and update this line according to the referenced rule.", "autofixable": rule.autofixable}})
    counts = {level: sum(item["severity"] == level for item in findings) for level in ("error", "warning", "info")}
    threshold = fail_on or config.fail_on
    threshold_rank = {"none": None, "info": 2, "warning": 1, "error": 0}[threshold]
    failed_by_findings = threshold_rank is not None and any({"error": 0, "warning": 1, "info": 2}[item["severity"]] <= threshold_rank for item in findings)
    uncovered_fails = bool(uncovered) and not (allow_uncovered if allow_uncovered is not None else config.allow_uncovered)
    return {"schema_version": "1.0", "summary": {"files": checked, "findings": len(findings), **{f"{k}s": v for k, v in counts.items()},
            "pass": not failed_by_findings and not uncovered_fails}, "findings": findings, "uncovered": uncovered,
            "toolchain": {"checker": "huawei-code-review", "version": "1.1", "profile": config.profile,
                          "config": config.source, "fail_on": threshold}}


def check(inputs: Iterable[str], language: str = "auto", profile: str = "balanced", config: Config | None = None,
          excludes: Iterable[str] | None = None, ignore: Iterable[str] | None = None,
          fail_on: str | None = None, allow_uncovered: bool | None = None) -> dict:
    config = config or Config(language=language, profile=profile)
    if config.ruleset == "legacy":
        result = check_legacy(inputs, language, profile, config, excludes, ignore, fail_on, allow_uncovered)
        result['toolchain']['ruleset'] = 'legacy'
        result['coverage_summary'] = {'catalog_checked': False, 'complete': False,
                                      'note': 'Only 17 legacy checks; no full catalog compliance claim.'}
        return result
    try:
        from .catalog_engine import check_catalog
    except ImportError:
        from catalog_engine import check_catalog
    return check_catalog(inputs, language, config, excludes, ignore, fail_on, allow_uncovered)


def exit_code(report: dict, fail_on: str = "error", allow_uncovered: bool = False) -> int:
    if report.get("uncovered") and not allow_uncovered:
        return 2
    ranks = {"error": 0, "warning": 1, "info": 2, "none": 99}
    threshold = ranks.get(fail_on, 0)
    if fail_on != "none" and any(ranks.get(item.get("severity"), 99) <= threshold for item in report.get("findings", [])):
        return 1
    return 0


def render(report: dict, fmt: str = "json") -> str:
    if fmt == "json":
        return json.dumps(report, ensure_ascii=False, indent=2)
    if fmt == "markdown":
        out = ["# Huawei/OpenHarmony code review", "", f"- Files checked: {report['summary']['files']}",
               f"- Findings: {report['summary']['findings']}", f"- Pass: {report['summary']['pass']}", ""]
        if report.get('coverage_summary'):
            coverage = report['coverage_summary']
            out.extend([f"- Ruleset: {report['toolchain'].get('ruleset')}",
                        f"- Rule coverage complete: {coverage.get('complete', False)}",
                        f"- Selected rules: {coverage.get('selected_rules', 'legacy')}", ''])
        for finding in report["findings"]:
            out += [f"## {finding['severity'].upper()} {finding['id']} — `{finding['path']}:{finding['line']}:{finding['column']}`",
                    finding["message"], f"Evidence: `{finding['evidence']}`",
                    f"Source: `{finding['source']['id']}` ({finding['source']['status']})", ""]
        if report["uncovered"]:
            out += ["## Uncovered", ""] + [f"- `{item['path']}`: {item['reason']}" for item in report["uncovered"]]
        return "\n".join(out) + "\n"
    if fmt != "sarif":
        raise ValueError(f"unsupported output format: {fmt}")
    results = [{"ruleId": f["id"], "level": f["severity"] if f["severity"] != "info" else "note",
                "message": {"text": f["message"]}, "locations": [{"physicalLocation": {"artifactLocation": {"uri": f["path"]},
                "region": {"startLine": f["line"], "startColumn": f["column"]}}}]} for f in report["findings"]]
    return json.dumps({"version": "2.1.0", "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
                       "runs": [{"tool": {"driver": {"name": "huawei-code-review"}}, "results": results,
                           "invocations": [{"executionSuccessful": not bool(report.get('uncovered'))}],
                           "properties": {"coverage_summary": report.get('coverage_summary', {}),
                                          "uncovered": report.get('uncovered', []),
                                          "rule_coverage": report.get('rule_coverage', [])}}]}, ensure_ascii=False, indent=2)
