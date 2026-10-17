#!/usr/bin/env python3
"""Record reproducible real-source scans without running target project code.

Manifest shape: {"projects": [{"name": "example", "root": "/repo",
"paths": ["src"], "provenance": {...}, "config": {}}]}.
Run with the installed checker Python so validation also tests wheel assets.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
import zipfile

from scripts.engine import files_for
from scripts.config import Config
from scripts.xlsx_export import write_xlsx


def workbook_check(path, report):
    ns = {'s': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
    with zipfile.ZipFile(path) as archive:
        assert archive.testzip() is None
        book = ET.fromstring(archive.read('xl/workbook.xml'))
        names = [sheet.attrib['name'] for sheet in book.findall('s:sheets/s:sheet', ns)]
        assert names == ['Summary', 'Findings', 'Uncovered', 'Rule Coverage'], names
        findings = ET.fromstring(archive.read('xl/worksheets/sheet2.xml'))
        coverage = ET.fromstring(archive.read('xl/worksheets/sheet4.xml'))
        finding_rows = findings.findall('s:sheetData/s:row', ns)[1:]
        coverage_rows = coverage.findall('s:sheetData/s:row', ns)[1:]
        assert len(finding_rows) == len(report['findings'])
        assert len(coverage_rows) == len(report['rule_coverage'])
        def cells(row):
            return [''.join(cell.itertext()) for cell in row.findall('s:c', ns)]
        assert [cells(row)[4] for row in finding_rows] == [f['id'] for f in report['findings']]
        expected = sorted(report['rule_coverage'], key=lambda r: (r['language'], r['rule_id']))
        assert [(cells(row)[0], cells(row)[7], cells(row)[8]) for row in coverage_rows] == [
            (row['rule_id'], row['implementation_status'], row['execution_status']) for row in expected]
    return {'sheets': names, 'findings': len(finding_rows), 'rules': len(coverage_rows), 'verified': True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    manifest = json.loads(args.manifest.read_text())
    results = []
    for project in manifest['projects']:
        name = project['name']
        if not name.replace('-', '').replace('_', '').isalnum():
            raise ValueError('Project names must be simple filenames')
        root = Path(project['root']).resolve()
        paths = [str(root / path) for path in project['paths']]
        config = {'ruleset': 'catalog', 'fail_on': 'warning', **project.get('config', {})}
        config_path = (args.output / (name + '.config.json')).resolve()
        config_path.write_text(json.dumps(config, indent=2))
        report_path = (args.output / (name + '.json')).resolve()
        sources, errors = files_for(paths, config.get('exclude', Config().exclude))
        if errors or not sources:
            raise ValueError(f'{name}: unreadable or empty source scope: {errors}')
        before = {path: hashlib.sha256(Path(path).read_bytes()).hexdigest() for path, _ in sources}
        command = [sys.executable, '-m', 'scripts.check', *paths, '--config', str(config_path),
                   '--format', 'json', '--output', str(report_path)]
        start = time.monotonic()
        run = subprocess.run(command, cwd=args.output, capture_output=True, text=True, timeout=600)
        duration = round(time.monotonic() - start, 3)
        if run.returncode not in (0, 1, 2) or not report_path.exists():
            raise RuntimeError(f'{name}: CLI failed: {run.stderr}')
        report = json.loads(report_path.read_text())
        assert before == {path: hashlib.sha256(Path(path).read_bytes()).hexdigest() for path in before}, 'Target source changed'
        assert len(before) == report['summary']['files'], 'Unexpected scan scope reduction'
        assert {row['path']: row['sha256'] for row in report['input_files']} == before
        workbook = args.output / (name + '.xlsx')
        write_xlsx(report, workbook)
        excel = workbook_check(workbook, report)
        git_sha = None
        provenance = project.get('provenance', {})
        if provenance.get('kind') in {'local-git-project', 'downloaded-open-source-git'}:
            revision = subprocess.run(['git', '-C', str(root), 'rev-parse', 'HEAD'],
                                      capture_output=True, text=True, timeout=10)
            git_sha = revision.stdout.strip() if revision.returncode == 0 else None
            if provenance.get('expected_sha') and git_sha != provenance['expected_sha']:
                raise ValueError(f'{name}: source revision changed: {git_sha}')
        # An npm package inside our worktree must never inherit our repository SHA.
        record = {**project, 'git_sha': git_sha,
                  'command': command, 'exit_code': run.returncode, 'seconds': duration,
                  'source_files': len(before), 'source_lines': sum(len(text.splitlines()) for _, text in sources),
                  'source_unchanged': True, 'findings': report['summary']['findings'],
                  'analysis_errors': [row for row in report['uncovered'] if not row.get('rule_ids')],
                  'coverage': report['coverage_summary'], 'xlsx': excel,
                  'json_sha256': hashlib.sha256(report_path.read_bytes()).hexdigest(),
                  'stderr': run.stderr}
        results.append(record)
        (args.output / 'run.json').write_text(json.dumps({'projects': results}, ensure_ascii=False, indent=2))
        print(json.dumps({key: record[key] for key in ('name', 'source_files', 'findings', 'exit_code', 'seconds')}), flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
