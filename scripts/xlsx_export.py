"""Small, dependency-free XLSX exporter for review reports.

The checker keeps JSON as its machine contract.  This module turns the same
report object into a conventional workbook for people who need to triage or
archive findings.  It deliberately writes the small subset of Office Open XML
needed by the four worksheets instead of requiring ``openpyxl`` at runtime.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
from xml.sax.saxutils import escape, quoteattr
import zipfile


FINDING_HEADERS = (
    "path", "line", "column", "language", "rule_id", "title", "severity",
    "raw_severity", "message", "evidence", "source", "coverage_status",
    "detector", "suggested_fix",
)
UNCOVERED_HEADERS = ("path", "reason", "affected_rule_ids")
COVERAGE_HEADERS = (
    "rule_id", "language", "title", "findings", "coverage_status", "detector", "source",
    "implementation_status", "execution_status", "reason", "test_cases",
    "options", "exported_options", "option_source",
)


def _text(value: Any) -> str:
    """Convert report values to readable cell text."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (dict, list, tuple)):
        if isinstance(value, dict):
            # Source dictionaries are much easier to scan in one cell than a
            # Python repr and this remains deterministic for JSON reports.
            if set(value) <= {"id", "status"}:
                return ": ".join(str(value.get(key, "")) for key in ("id", "status") if value.get(key))
        import json
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)


def _source_text(source: Any) -> str:
    if isinstance(source, Mapping):
        source_id = _text(source.get("id"))
        status = _text(source.get("status"))
        return f"{source_id} ({status})" if source_id and status else source_id or status
    return _text(source)


def _finding_row(finding: Mapping[str, Any]) -> list[str]:
    fix = finding.get("fix") or {}
    return [
        _text(finding.get("path")),
        _text(finding.get("line")),
        _text(finding.get("column")),
        _text(finding.get("language")),
        _text(finding.get("rule_id", finding.get("id"))),
        _text(finding.get("title")),
        _text(finding.get("severity")),
        _text(finding.get("raw_severity")),
        _text(finding.get("message")),
        _text(finding.get("evidence")),
        _source_text(finding.get("source")),
        _text(finding.get("coverage_status", "unverified")),
        _text(finding.get("detector", "")),
        _text(finding.get("suggested_fix", fix.get("description", ""))),
    ]


def _coverage_rows(report: Mapping[str, Any]) -> list[list[str]]:
    """Build the coverage worksheet from optional metadata or findings.

    Newer engine versions may attach a ``rule_coverage`` array.  Older reports
    only carry findings, so those rules are represented as observed rows with
    unverified coverage. A finding alone never proves exact rule coverage.
    """
    supplied = report.get("rule_coverage")
    if isinstance(supplied, list):
        rows: list[list[str]] = []
        for item in supplied:
            if not isinstance(item, Mapping):
                continue
            rows.append([
                _text(item.get("rule_id", item.get("id"))),
                _text(item.get("language")),
                _text(item.get("title", item.get("name"))),
                _text(item.get("findings", item.get("finding_count", 0))),
                _text(item.get("coverage_status", item.get("status", "opaque"))),
                _text(item.get("detector", "")),
                _source_text(item.get("source")),
                _text(item.get("implementation_status", "")),
                _text(item.get("execution_status", "")),
                _text(item.get("reason", "")),
                _text(item.get("test_cases", [])),
                _text(item.get("options", [])),
                _text(item.get("exported_options", [])),
                _text(item.get("option_source", "")),
            ])
        if rows:
            return sorted(rows, key=lambda row: (row[1], row[0]))

    findings = report.get("findings") or []
    groups: dict[str, dict[str, Any]] = {}
    for finding in findings:
        if not isinstance(finding, Mapping):
            continue
        rule_id = _text(finding.get("rule_id", finding.get("id")))
        if not rule_id:
            continue
        entry = groups.setdefault(rule_id, {
            "language": _text(finding.get("language")),
            "title": _text(finding.get("title")),
            "findings": 0,
            "coverage_status": _text(finding.get("coverage_status", "unverified")),
            "detector": _text(finding.get("detector", "")),
            "source": _source_text(finding.get("source")),
        })
        entry["findings"] += 1
    return [[rule_id, data["language"], data["title"], str(data["findings"]),
             data["coverage_status"], data["detector"], data["source"], "", "", "", "", "", "", ""]
            for rule_id, data in sorted(groups.items())]


def _summary_rows(report: Mapping[str, Any]) -> list[list[str]]:
    summary = report.get("summary") or {}
    toolchain = report.get("toolchain") or {}
    rows = [
        ["field", "value"],
        ["schema_version", _text(report.get("schema_version", ""))],
        ["files", summary.get("files", 0)],
        ["findings", summary.get("findings", len(report.get("findings") or []))],
        ["errors", summary.get("errors", 0)],
        ["warnings", summary.get("warnings", 0)],
        ["infos", summary.get("infos", 0)],
        ["pass", summary.get("pass", False)],
        ["uncovered", len(report.get("uncovered") or [])],
        ["checker", _text(toolchain.get("checker", "huawei-code-review"))],
        ["version", _text(toolchain.get("version", ""))],
        ["profile", _text(toolchain.get("profile", ""))],
        ["fail_on", _text(toolchain.get("fail_on", ""))],
        ["generated_at", datetime.now(timezone.utc).replace(microsecond=0).isoformat()],
    ]
    for key, value in (report.get('coverage_summary') or {}).items():
        rows.append(['coverage.' + key, _text(value)])
    return rows


def _sheet_rows(report: Mapping[str, Any]) -> list[tuple[str, list[str], list[list[str]]]]:
    findings = report.get("findings") or []
    finding_rows = [_finding_row(item) for item in findings if isinstance(item, Mapping)]
    uncovered_rows = [[_text(item.get("path")), _text(item.get("reason")), _text(item.get("affected_rule_ids", item.get("rule_ids", [])))]
                      for item in report.get("uncovered", []) if isinstance(item, Mapping)]
    return [
        ("Summary", ("field", "value"), _summary_rows(report)[1:]),
        ("Findings", FINDING_HEADERS, finding_rows),
        ("Uncovered", UNCOVERED_HEADERS, uncovered_rows),
        ("Rule Coverage", COVERAGE_HEADERS, _coverage_rows(report)),
    ]


def _col_name(number: int) -> str:
    result = ""
    while number:
        number, remainder = divmod(number - 1, 26)
        result = chr(65 + remainder) + result
    return result


def _cell(row: int, col: int, value: Any, style: int = 0) -> str:
    ref = f"{_col_name(col)}{row}"
    text = _text(value)
    style_attr = f' s="{style}"' if style else ""
    # Keep numeric summary values numeric in Excel, while preserving line and
    # column strings in Findings for stable round-tripping.
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f'<c r="{ref}"{style_attr}><v>{value}</v></c>'
    return f'<c r="{ref}" t="inlineStr"{style_attr}><is><t xml:space="preserve">{escape(text)}</t></is></c>'


def _worksheet_xml(headers: Sequence[str], rows: Iterable[Sequence[Any]], widths: Sequence[int] | None = None) -> str:
    all_rows = [list(headers), *[list(row) for row in rows]]
    max_col = max((len(row) for row in all_rows), default=1)
    max_row = max(len(all_rows), 1)
    cells: list[str] = []
    for row_index, row in enumerate(all_rows, 1):
        row_cells = []
        for col_index, value in enumerate(row, 1):
            row_cells.append(_cell(row_index, col_index, value, 1 if row_index == 1 else 0))
        cells.append(f'<row r="{row_index}">' + "".join(row_cells) + "</row>")
    width_values = list(widths or [18] * max_col)
    if len(width_values) < max_col:
        width_values.extend([18] * (max_col - len(width_values)))
    cols = "".join(f'<col min="{i}" max="{i}" width="{max(10, min(width_values[i - 1], 80))}" customWidth="1"/>'
                   for i in range(1, max_col + 1))
    end_ref = f"{_col_name(max_col)}{max_row}"
    return (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            f'<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            f'<dimension ref="A1:{end_ref}"/><sheetViews><sheetView workbookViewId="0">'
            f'<pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/>'
            f'<selection pane="bottomLeft" activeCell="A2" sqref="A2"/></sheetView></sheetViews>'
            f'<sheetFormatPr defaultRowHeight="15"/><cols>{cols}</cols><sheetData>{"".join(cells)}</sheetData>'
            f'<autoFilter ref="A1:{end_ref}"/></worksheet>')


def _styles_xml() -> str:
    return '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <numFmts count="0"/><fonts count="2">
    <font><sz val="11"/><name val="Calibri"/><family val="2"/></font>
    <font><b/><sz val="11"/><name val="Calibri"/><family val="2"/></font>
  </fonts>
  <fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill></fills>
  <borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>
  <cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
  <cellXfs count="2"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/><xf numFmtId="0" fontId="1" fillId="0" borderId="0"/></cellXfs>
  <cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>
  <dxfs count="0"/><tableStyles count="0" defaultTableStyle="TableStyleMedium2" defaultPivotStyle="PivotStyleLight16"/>
</styleSheet>'''


def _content_types_xml(sheet_count: int) -> str:
    overrides = "".join(
        f'<Override PartName="/xl/worksheets/sheet{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        for i in range(1, sheet_count + 1)
    )
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
            f'{overrides}</Types>')


def _workbook_xml(sheet_count: int) -> str:
    sheets = ["Summary", "Findings", "Uncovered", "Rule Coverage"][:sheet_count]
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            '<fileVersion appName="huawei-code-review"/><workbookPr/>'
            '<bookViews><workbookView/></bookViews><sheets>'
            + "".join(f'<sheet name={quoteattr(name)} sheetId="{i}" r:id="rId{i}"/>' for i, name in enumerate(sheets, 1))
            + '</sheets><calcPr fullCalcOnLoad="1"/></workbook>')


def _workbook_rels_xml(sheet_count: int) -> str:
    relationships = [f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i}.xml"/>'
                     for i in range(1, sheet_count + 1)]
    relationships.append('<Relationship Id="rId5" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>')
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            + "".join(relationships) + '</Relationships>')


def _root_rels_xml() -> str:
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
            '</Relationships>')


def workbook_bytes(report: Mapping[str, Any]) -> bytes:
    """Return a valid XLSX workbook containing the four report worksheets."""
    sheets = _sheet_rows(report)
    import io
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", _content_types_xml(len(sheets)))
        archive.writestr("_rels/.rels", _root_rels_xml())
        archive.writestr("xl/workbook.xml", _workbook_xml(len(sheets)))
        archive.writestr("xl/_rels/workbook.xml.rels", _workbook_rels_xml(len(sheets)))
        archive.writestr("xl/styles.xml", _styles_xml())
        for index, (_name, headers, rows) in enumerate(sheets, 1):
            widths = [max(12, min(60, max([len(_text(header)), *(len(_text(row[i])) for row in rows if i < len(row))], default=12) + 2))
                      for i, header in enumerate(headers)]
            archive.writestr(f"xl/worksheets/sheet{index}.xml", _worksheet_xml(headers, rows, widths))
    return output.getvalue()


def write_xlsx(report: Mapping[str, Any], output: str | Path) -> Path:
    """Write a report workbook and return its resolved output path."""
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(workbook_bytes(report))
    return path
