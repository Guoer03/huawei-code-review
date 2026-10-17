"""Subprocess adapters and output normalisation for common linters.

This module intentionally uses only the Python standard library.  Linters are
optional integrations: an absent executable is represented as ``missing`` and
never causes the host review to crash.  A non-zero linter exit code is normal
when findings exist, so it is retained in the result while the status remains
``completed`` if output was parsed.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


@dataclass
class Finding:
    """Canonical finding shape shared by every external adapter."""

    id: str
    language: str
    path: str
    line: int
    column: int
    severity: str
    confidence: str
    title: str
    message: str
    evidence: str
    source: dict[str, str]
    fix: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AdapterSpec:
    name: str
    executable: str
    language: str
    args: tuple[str, ...]


ADAPTERS: dict[str, AdapterSpec] = {
    "eslint": AdapterSpec("eslint", "eslint", "javascript", ("--format", "json")),
    "tsc": AdapterSpec("tsc", "tsc", "typescript", ("--noEmit", "--pretty", "false")),
    "ruff": AdapterSpec("ruff", "ruff", "python", ("check", "--output-format", "json")),
    "flake8": AdapterSpec("flake8", "flake8", "python", ()),
    "checkstyle": AdapterSpec("checkstyle", "checkstyle", "java", ("-f", "xml")),
}

_TS_RE = re.compile(
    r"^(?P<path>.*?)(?:\((?P<line>\d+),(?P<column>\d+)\)|:(?P<line2>\d+):(?P<column2>\d+)):\s*(?P<kind>error|warning)\s*(?P<code>[A-Za-z]+\d+)?\s*:?[ \t]*(?P<message>.*)$",
    re.IGNORECASE,
)
_FLAKE_RE = re.compile(r"^(?P<path>.*?):(?P<line>\d+):(?P<column>\d+):[ \t]*(?P<code>[A-Za-z]\d+)[ \t]+(?P<message>.*)$")


def available_adapters() -> dict[str, bool]:
    """Return whether each configured executable is discoverable on PATH."""

    return {name: shutil.which(spec.executable) is not None for name, spec in ADAPTERS.items()}


def _path(value: Any, cwd: str | Path | None) -> str:
    result = str(value or "<unknown>")
    if cwd and os.path.isabs(result):
        try:
            return os.path.relpath(result, str(cwd))
        except ValueError:
            pass
    return result.replace("\\", "/")


def _severity(value: Any, default: str = "warning") -> str:
    if isinstance(value, int):
        return {1: "warning", 2: "error", 3: "error"}.get(value, default)
    text = str(value or "").lower()
    if text in {"error", "fatal", "failure", "err", "e", "f"}:
        return "error"
    if text in {"info", "information", "note", "i"}:
        return "info"
    return "warning"


def _title(message: str, rule_id: str) -> str:
    first = re.split(r"[.!?]\s+", message.strip(), maxsplit=1)[0].strip()
    return first or rule_id


def _finding(
    tool: str,
    language: str,
    path: Any,
    line: Any,
    column: Any,
    severity: Any,
    rule_id: Any,
    message: Any,
    cwd: str | Path | None,
    evidence: Any = "",
    fix: Any = None,
) -> dict[str, Any]:
    rid = str(rule_id or f"{tool.upper()}-UNKNOWN")
    msg = str(message or "External checker reported a finding.")
    return Finding(
        id=rid,
        language=language,
        path=_path(path, cwd),
        line=max(1, int(line or 1)),
        column=max(1, int(column or 1)),
        severity=_severity(severity),
        confidence="high" if rule_id else "medium",
        title=_title(msg, rid),
        message=msg,
        evidence=str(evidence or msg)[:240],
        source={"id": f"external-{tool}", "status": "external-tool"},
        fix={"description": str(fix) if fix else "Review the external checker guidance.", "autofixable": False},
    ).as_dict()


def _parse_eslint(data: Any, cwd: str | Path | None) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    if not isinstance(data, list):
        raise ValueError("ESLint JSON must be an array")
    for result in data:
        if not isinstance(result, Mapping):
            continue
        path = result.get("filePath", result.get("file", "<unknown>"))
        language = "typescript" if Path(str(path)).suffix.lower() in {".ts", ".tsx", ".mts", ".cts"} else "javascript"
        for item in result.get("messages", []) or []:
            if not isinstance(item, Mapping):
                continue
            findings.append(_finding("eslint", language, path, item.get("line"), item.get("column"), item.get("severity"), item.get("ruleId"), item.get("message"), cwd, fix=item.get("fix")))
    return findings


def _parse_ruff(data: Any, cwd: str | Path | None) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    if not isinstance(data, list):
        raise ValueError('Ruff JSON must be an array')
    records = data
    for item in records:
        if not isinstance(item, Mapping):
            continue
        location = item.get("location") or {}
        fix = item.get("fix")
        code = str(item.get("code") or "")
        severity = "error" if code.startswith(("E", "F", "S", "B")) else "warning"
        findings.append(_finding("ruff", "python", item.get("filename", item.get("file")), location.get("row"), location.get("column"), severity, code, item.get("message"), cwd, evidence=item.get("message"), fix=(fix or {}).get("message") if isinstance(fix, Mapping) else fix))
    return findings


def _parse_flake8(text: str, cwd: str | Path | None) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for raw in text.splitlines():
        match = _FLAKE_RE.match(raw.strip())
        if not match:
            continue
        code = match.group("code")
        severity = "error" if code.startswith(("E", "F")) else "warning"
        findings.append(_finding("flake8", "python", match.group("path"), match.group("line"), match.group("column"), severity, code, match.group("message"), cwd, evidence=raw.strip()))
    return findings


def _parse_tsc(text: str, cwd: str | Path | None) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for raw in text.splitlines():
        match = _TS_RE.match(raw.strip())
        if not match:
            continue
        findings.append(_finding("tsc", "typescript", match.group("path"), match.group("line") or match.group("line2"), match.group("column") or match.group("column2"), match.group("kind"), match.group("code") or "TSC", match.group("message"), cwd, evidence=raw.strip()))
    return findings


def _parse_checkstyle(text: str, cwd: str | Path | None) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise ValueError(f"Checkstyle XML parse failed: {exc}") from exc
    for file_node in root.findall(".//file"):
        path = file_node.attrib.get("name", "<unknown>")
        for error in file_node.findall("error"):
            findings.append(_finding("checkstyle", "java", path, error.attrib.get("line"), error.attrib.get("column"), error.attrib.get("severity"), error.attrib.get("source") or error.attrib.get("key") or "CHECKSTYLE", error.attrib.get("message"), cwd, evidence=error.attrib.get("message")))
    return findings


def _parse_sarif(data: Mapping[str, Any], cwd: str | Path | None, tool: str, language: str) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for run in data.get("runs", []) or []:
        driver = ((run.get("tool") or {}).get("driver") or {})
        rules = driver.get("rules") or []
        rule_help = {str(rule.get("id")): rule.get("shortDescription", {}).get("text", "") for rule in rules if isinstance(rule, Mapping)}
        for result in run.get("results", []) or []:
            if not isinstance(result, Mapping):
                continue
            location = ((result.get("locations") or [{}])[0].get("physicalLocation") or {})
            artifact = location.get("artifactLocation") or {}
            region = location.get("region") or {}
            rid = str(result.get("ruleId") or "SARIF")
            msg = ((result.get("message") or {}).get("text") or rule_help.get(rid) or "SARIF finding")
            findings.append(_finding(tool, language, artifact.get("uri"), region.get("startLine"), region.get("startColumn"), result.get("level"), rid, msg, cwd, evidence=msg))
    return findings


def parse_output(tool: str, stdout: str, stderr: str = "", *, cwd: str | Path | None = None, format_hint: str | None = None) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """Parse a checker stream into findings and non-fatal diagnostics.

    ``format_hint`` is useful for callers that force a JSON/SARIF output mode.
    Parsers skip unrecognised lines and report them as diagnostics so malformed
    output cannot silently look like a clean review.
    """
    name = tool.lower()
    diagnostics: list[dict[str, str]] = []
    try:
        if format_hint == "sarif" or (stdout.lstrip().startswith("{") and '"runs"' in stdout[:1000]):
            data = json.loads(stdout)
            if not isinstance(data, Mapping):
                raise ValueError("SARIF output must be an object")
            return _parse_sarif(data, cwd, name, ADAPTERS.get(name, AdapterSpec(name, name, "unknown", ())).language), diagnostics
        if name in {"eslint", "ruff"}:
            data = json.loads(stdout)
            if name == 'eslint' and isinstance(data, list):
                for file in data:
                    for item in file.get('messages', []):
                        if item.get('fatal'):
                            diagnostics.append({'kind': 'analysis_error', 'message': f"{file.get('filePath')}: {item.get('message')}"})
            return (_parse_eslint(data, cwd) if name == "eslint" else _parse_ruff(data, cwd)), diagnostics
        if name == "checkstyle":
            return _parse_checkstyle(stdout, cwd), diagnostics
        if name == "tsc":
            return _parse_tsc(stdout + ("\n" + stderr if stderr else ""), cwd), diagnostics
        if name == "flake8":
            return _parse_flake8(stdout + ("\n" + stderr if stderr else ""), cwd), diagnostics
        raise ValueError(f"unknown adapter: {tool}")
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        diagnostics.append({"kind": "parse_error", "message": str(exc)})
        return [], diagnostics


def run_adapter(
    tool: str,
    paths: Sequence[str | Path],
    *,
    cwd: str | Path | None = None,
    timeout: float = 30.0,
    executable: str | None = None,
    extra_args: Iterable[str] = (),
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Run an optional checker and return a serialisable adapter result."""
    name = tool.lower()
    extra_args = tuple(extra_args)
    spec = ADAPTERS.get(name)
    started = time.monotonic()
    base = {"name": name, "status": "error", "findings": [], "diagnostics": [], "command": [], "returncode": None, "duration_ms": 0}
    if spec is None:
        base["status"] = "skipped"
        base["diagnostics"] = [{"kind": "unsupported_tool", "message": f"No adapter is registered for {tool!r}."}]
        return base
    command_name = executable or spec.executable
    command_path = command_name if os.path.sep in command_name else shutil.which(command_name)
    if not command_path:
        base["status"] = "missing"
        base["diagnostics"] = [{"kind": "missing_tool", "executable": command_name, "message": f"{command_name} is not installed or not on PATH."}]
        return base
    if name == "checkstyle" and "-c" not in extra_args and "--config" not in extra_args:
        base["status"] = "skipped"
        base["diagnostics"] = [{"kind": "missing_config", "message": "Checkstyle requires a configuration file; pass it with extra_args=['-c', PATH]."}]
        return base
    command = [command_path, *spec.args, *list(extra_args), *(str(path) for path in paths)]
    base["command"] = command
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    try:
        completed = subprocess.run(command, cwd=str(cwd) if cwd else None, env=merged_env, text=True, capture_output=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired as exc:
        base["status"] = "timeout"
        base["diagnostics"] = [{"kind": "timeout", "message": f"{name} exceeded {timeout:g}s."}]
        base["duration_ms"] = round((time.monotonic() - started) * 1000, 2)
        return base
    except OSError as exc:
        base["status"] = "error"
        base["diagnostics"] = [{"kind": "execution_error", "message": str(exc)}]
        base["duration_ms"] = round((time.monotonic() - started) * 1000, 2)
        return base
    findings, diagnostics = parse_output(name, completed.stdout, completed.stderr, cwd=cwd)
    base["findings"] = findings
    base["diagnostics"] = diagnostics
    base["returncode"] = completed.returncode
    base["duration_ms"] = round((time.monotonic() - started) * 1000, 2)
    fatal_exit = name in {'eslint', 'ruff', 'flake8'} and completed.returncode not in {0, 1}
    if fatal_exit or (completed.returncode != 0 and not findings):
        if not diagnostics:
            diagnostics.append({"kind": "tool_error", "message": (completed.stderr or completed.stdout or f"{name} exited with code {completed.returncode}").strip()[:1000]})
        base["status"] = "error"
    else:
        base["status"] = "completed" if not diagnostics else "error"
    return base
