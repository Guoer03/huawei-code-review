#!/usr/bin/env python3
"""Compare two huawei-code-review JSON reports.

The checker report is the deterministic source of truth for a repair loop.  A
skill can run a scan before and after edits, then use this small utility to
classify findings without having to understand the whole report schema.

Findings are matched exactly by path, line, column, rule id, and a normalized
message.  An unmatched pair with the same path, rule id, and normalized
message but a different location is classified as ``moved``.  Matching is
one-to-one and deterministic, so duplicate findings do not disappear during a
comparison.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Iterable, Mapping


def normalize_message(value: Any) -> str:
    """Return a stable message form for comparison.

    Reports may be produced by different adapters which wrap text or use
    slightly different casing.  Collapsing whitespace and case-folding keeps
    those equivalent messages together while retaining the actual message in
    the output records.
    """

    return " ".join(str(value or "").split()).casefold()


def _rule_id(finding: Mapping[str, Any]) -> str:
    return str(finding.get("rule_id", finding.get("id", "")) or "")


def _path(finding: Mapping[str, Any]) -> str:
    return str(finding.get("path", "") or "")


def _location_number(finding: Mapping[str, Any], field: str) -> int | str:
    value = finding.get(field, 0)
    # Keep malformed locations comparable and visible rather than failing the
    # complete report.  Normal checker output uses positive integers.
    try:
        return int(value)
    except (TypeError, ValueError):
        return str(value or "")


def _message(finding: Mapping[str, Any]) -> str:
    return normalize_message(finding.get("message", ""))


def _exact_key(finding: Mapping[str, Any]) -> tuple[str, int | str, int | str, str, str]:
    return (
        _path(finding),
        _location_number(finding, "line"),
        _location_number(finding, "column"),
        _rule_id(finding),
        _message(finding),
    )


def _move_key(finding: Mapping[str, Any]) -> tuple[str, str, str]:
    return (_path(finding), _rule_id(finding), _message(finding))


def _sort_key(finding: Mapping[str, Any]) -> tuple[str, str, str, str, str]:
    # Stringified values make ordering total even for hand-written reports
    # containing a non-numeric line or column.
    return (
        _path(finding),
        str(_location_number(finding, "line")),
        str(_location_number(finding, "column")),
        _rule_id(finding),
        _message(finding),
    )


def _load_report(path: str | Path) -> dict[str, Any]:
    report_path = Path(path)
    try:
        data = json.loads(report_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"cannot read report {report_path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in {report_path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"report {report_path} must contain a JSON object")
    findings = data.get("findings", [])
    if not isinstance(findings, list) or any(not isinstance(item, Mapping) for item in findings):
        raise ValueError(f"report {report_path} must contain a findings array of objects")
    return data


def _findings(report: Mapping[str, Any]) -> list[dict[str, Any]]:
    # Copy each object so callers can safely consume the result without the
    # comparison mutating the parsed source report.
    return [dict(item) for item in report.get("findings", []) if isinstance(item, Mapping)]


def _pop_matches(
    before: list[dict[str, Any]],
    after: list[dict[str, Any]],
    key_fn,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Match one-to-one records by ``key_fn`` and return leftovers plus pairs.

    Lists are sorted before matching to make duplicate handling independent of
    JSON array order.  The returned pairs contain ``before`` and ``after``
    records in that stable order.
    """

    before_sorted = sorted(before, key=_sort_key)
    after_sorted = sorted(after, key=_sort_key)
    after_by_key: dict[Any, list[dict[str, Any]]] = {}
    for item in after_sorted:
        after_by_key.setdefault(key_fn(item), []).append(item)

    matched_before: list[dict[str, Any]] = []
    before_left: list[dict[str, Any]] = []
    for item in before_sorted:
        bucket = after_by_key.get(key_fn(item))
        if bucket:
            matched_before.append(item)
            bucket.pop(0)
        else:
            before_left.append(item)

    after_left = [item for bucket in after_by_key.values() for item in bucket]
    # ``matched_before`` is not needed by callers, but the pair list is built
    # by matching the same key again against the original records below.
    matched_after_by_key: dict[Any, list[dict[str, Any]]] = {}
    for item in after_sorted:
        matched_after_by_key.setdefault(key_fn(item), []).append(item)
    pairs: list[dict[str, Any]] = []
    for item in matched_before:
        bucket = matched_after_by_key[key_fn(item)]
        pairs.append({"before": item, "after": bucket.pop(0)})
    return before_left, after_left, pairs


def compare_reports(before_report: Mapping[str, Any], after_report: Mapping[str, Any]) -> dict[str, Any]:
    """Return a deterministic delta between two checker reports."""

    before = _findings(before_report)
    after = _findings(after_report)

    before_left, after_left, unchanged_pairs = _pop_matches(before, after, _exact_key)
    # Exact matches are emitted as the finding itself because both records are
    # semantically identical for the comparison contract.  Keep the before
    # value to preserve any auxiliary fields from the original scan.
    unchanged = [pair["before"] for pair in unchanged_pairs]

    before_left, after_left, moved_pairs = _pop_matches(before_left, after_left, _move_key)
    # Exact matches were removed first, so every pair left in this pass has a
    # location change by definition.
    moved = [{"before": pair["before"], "after": pair["after"]} for pair in moved_pairs]

    resolved = sorted(before_left, key=_sort_key)
    new = sorted(after_left, key=_sort_key)
    unchanged.sort(key=_sort_key)
    moved.sort(key=lambda pair: (_sort_key(pair["before"]), _sort_key(pair["after"])))

    before_uncovered = before_report.get("uncovered", [])
    after_uncovered = after_report.get("uncovered", [])
    unverified_resolutions = []
    if 'rule_coverage' in before_report or 'rule_coverage' in after_report:
        def identity(row):
            return (str(row.get('key', row.get('rule_key', row.get('rule_id', row.get('id', ''))))), row.get('language', ''))
        def semantics(row):
            return (row.get('detector'), json.dumps(row.get('options', []), sort_keys=True), row.get('detector_fingerprint'))
        prior_rules = {identity(row): row for row in before_report.get('rule_coverage', [])}
        executed = {identity(row) for row in after_report.get('rule_coverage', [])
                    if row.get('coverage_status') == 'covered' and row.get('execution_status') == 'completed'
                    and identity(row) in prior_rules and semantics(row) == semantics(prior_rules[identity(row)])}
        checked_paths = {str(row['path']) for row in after_report.get('input_files', [])}
        # Project analyses depend on companion source files, not just the file
        # where a diagnostic is emitted. Preserve the entire language scope.
        def scope(report, language):
            return {str(row['path']) for row in report.get('input_files', [])
                    if row.get('language', '') == language}
        def verified(f):
            language = f.get('language', '')
            return (identity(f) in executed and _path(f) in checked_paths
                    and scope(before_report, language) == scope(after_report, language))
        unverified_resolutions = [f for f in resolved if not verified(f)]
        resolved = [f for f in resolved if verified(f)]
    elif after_uncovered:
        # Legacy reports cannot establish per-rule coverage after a failed scan.
        unverified_resolutions, resolved = resolved, []
    summary = {
        "before_findings": len(before),
        "after_findings": len(after),
        "resolved": len(resolved),
        "new": len(new),
        "unchanged": len(unchanged),
        "moved": len(moved),
        "net_change": len(new) - len(resolved),
        "before_uncovered": len(before_uncovered) if isinstance(before_uncovered, list) else 0,
        "after_uncovered": len(after_uncovered) if isinstance(after_uncovered, list) else 0,
    }
    return {
        "resolved": resolved,
        "new": new,
        "unchanged": unchanged,
        "moved": moved,
        "summary": summary,
        "unverified_resolutions": unverified_resolutions,
        "verification": {'disappeared_without_coverage': len(unverified_resolutions),
                         'note': 'A disappearing diagnostic is not proof of behavioral correctness; run project tests.'},
    }


def _write_delta(delta: Mapping[str, Any], output: str | Path | None) -> None:
    rendered = json.dumps(delta, ensure_ascii=False, indent=2) + "\n"
    if output:
        output_path = Path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered, encoding="utf-8")
    else:
        sys.stdout.write(rendered)


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="huawei-code-review-compare",
        description="Compare before and after huawei-code-review JSON reports",
    )
    parser.add_argument("before", help="before-scan JSON report")
    parser.add_argument("after", help="after-scan JSON report")
    parser.add_argument("--output", help="write the JSON delta to this file")
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        delta = compare_reports(_load_report(args.before), _load_report(args.after))
        _write_delta(delta, args.output)
        return 0
    except (OSError, ValueError) as exc:
        print(f"huawei-code-review-compare: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
