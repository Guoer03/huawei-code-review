"""Tests for the dependency-free XLSX report artifact."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree
import zipfile


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check.py"
FIXTURES = ROOT / "tests" / "fixtures"
sys.path.insert(0, str(ROOT / "scripts"))

from xlsx_export import workbook_bytes, write_xlsx  # noqa: E402


NS = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def sheet_values(archive: zipfile.ZipFile, sheet_number: int) -> list[list[str]]:
    root = ElementTree.fromstring(archive.read(f"xl/worksheets/sheet{sheet_number}.xml"))
    rows: list[list[str]] = []
    for row in root.findall("x:sheetData/x:row", NS):
        values = []
        for cell in row.findall("x:c", NS):
            inline = cell.find("x:is/x:t", NS)
            value = inline.text if inline is not None and inline.text is not None else ""
            numeric = cell.find("x:v", NS)
            if numeric is not None and numeric.text is not None:
                value = numeric.text
            values.append(value)
        rows.append(values)
    return rows


class XlsxExportTests(unittest.TestCase):
    def report(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--ruleset", "legacy", str(FIXTURES / "violations.js"), "--format", "json"],
            cwd=ROOT, capture_output=True, text=True, check=False,
        )
        self.assertEqual(result.returncode, 1)
        return json.loads(result.stdout)

    def test_workbook_has_expected_parts_and_four_sheets(self):
        report = self.report()
        raw = workbook_bytes(report)
        with zipfile.ZipFile(__import__("io").BytesIO(raw)) as archive:
            names = set(archive.namelist())
            self.assertIn("[Content_Types].xml", names)
            self.assertIn("xl/workbook.xml", names)
            self.assertIn("xl/styles.xml", names)
            self.assertEqual({archive.read(f"xl/worksheets/sheet{i}.xml")[0:5] for i in range(1, 5)}, {b"<?xml"})
            workbook = ElementTree.fromstring(archive.read("xl/workbook.xml"))
            names = [node.attrib["name"] for node in workbook.findall("x:sheets/x:sheet", NS)]
            self.assertEqual(names, ["Summary", "Findings", "Uncovered", "Rule Coverage"])

    def test_findings_sheet_matches_json_findings(self):
        report = self.report()
        with zipfile.ZipFile(__import__("io").BytesIO(workbook_bytes(report))) as archive:
            rows = sheet_values(archive, 2)
        self.assertEqual(rows[0], [
            "path", "line", "column", "language", "rule_id", "title", "severity",
            "raw_severity", "message", "evidence", "source", "coverage_status",
            "detector", "suggested_fix",
        ])
        self.assertEqual(len(rows) - 1, len(report["findings"]))
        exported_ids = [row[4] for row in rows[1:]]
        json_ids = [item["id"] for item in report["findings"]]
        self.assertEqual(exported_ids, json_ids)
        self.assertEqual(rows[1][0], report["findings"][0]["path"])
        self.assertEqual(rows[1][9], report["findings"][0]["evidence"])

    def test_uncovered_and_coverage_sheets_are_present_for_empty_lists(self):
        report = {"schema_version": "1.0", "summary": {"files": 1, "findings": 0, "pass": True},
                  "findings": [], "uncovered": [], "toolchain": {"checker": "test"}}
        with zipfile.ZipFile(__import__("io").BytesIO(workbook_bytes(report))) as archive:
            uncovered = sheet_values(archive, 3)
            coverage = sheet_values(archive, 4)
        self.assertEqual(uncovered, [["path", "reason", "affected_rule_ids"]])
        self.assertEqual(coverage, [["rule_id", "language", "title", "findings", "coverage_status", "detector", "source", "implementation_status", "execution_status", "reason", "test_cases", "options", "exported_options", "option_source"]])

    def test_write_xlsx_creates_parent_and_valid_archive(self):
        report = self.report()
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "nested" / "report.xlsx"
            returned = write_xlsx(report, destination)
            self.assertEqual(returned, destination)
            self.assertTrue(destination.is_file())
            with zipfile.ZipFile(destination) as archive:
                self.assertTrue(archive.testzip() is None)

    def test_export_does_not_invent_verified_coverage_or_original_severity(self):
        report = self.report()
        with zipfile.ZipFile(__import__('io').BytesIO(workbook_bytes(report))) as archive:
            finding = sheet_values(archive, 2)[1]
            coverage = sheet_values(archive, 4)[1]
        self.assertEqual(finding[7], '')
        self.assertEqual(finding[11], 'unverified')
        self.assertEqual(coverage[4], 'unverified')

    def test_explicit_source_severity_is_preserved_without_conversion(self):
        report = self.report()
        report['findings'][0]['raw_severity'] = '0'
        with zipfile.ZipFile(__import__('io').BytesIO(workbook_bytes(report))) as archive:
            finding = sheet_values(archive, 2)[1]
        self.assertEqual(finding[7], '0')

    def test_cli_writes_xlsx_and_prints_artifact_path(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "reports" / "review.xlsx"
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--ruleset", "legacy", str(FIXTURES / "clean.py"),
                 "--format", "xlsx", "--output", str(destination)],
                cwd=ROOT, capture_output=True, text=True, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(Path(result.stdout.strip()), destination)
            self.assertTrue(destination.is_file())


if __name__ == "__main__":
    unittest.main()
