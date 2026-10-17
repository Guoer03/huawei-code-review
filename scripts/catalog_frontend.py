"""Execute explicit exported frontend rule mappings via ESLint and typed ASTs."""
from __future__ import annotations
import json
import os
from pathlib import Path
import shutil
import subprocess

RUNTIME = Path(__file__).resolve().parent / 'frontend_rules' / 'runner.cjs'


def _node() -> str:
    return os.environ.get('HCR_NODE') or shutil.which('node') or 'node'


def runtime_status() -> dict:
    try:
        result = subprocess.run([_node(), str(RUNTIME), '--doctor'], capture_output=True, text=True, timeout=20)
        data = json.loads(result.stdout)
        return data
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        return {'available': False, 'reason': str(exc)}


def scan(files: list[tuple[str, str]], entries: list[dict]) -> dict:
    selected=[]
    for entry in entries:
        rule=entry.get('rule',entry)
        if rule.get('language','').upper() in ('JAVASCRIPT','TYPESCRIPT'):
            selected.append(rule)
    if not files or not selected:
        return {'findings': [], 'errors': []}
    # Extensionless scripts and stdin still have an explicit dispatcher language.
    languages={rule['language'].lower() for rule in selected}
    language=selected[0]['language'].lower()
    suffix='.ts' if language=='typescript' else '.js'
    payload_files=[]
    original_paths={}
    for path,text in files:
        runtime_path=path if Path(path).suffix.lower() in {'.js','.jsx','.mjs','.cjs','.ts','.tsx','.mts','.cts','.ets'} else path+suffix
        original_paths[runtime_path]=path
        payload_files.append({'path':runtime_path,'text':text,
                              **({'language':language} if len(languages)==1 else {})})
    payload={'files':payload_files, 'rules': selected}
    try:
        result=subprocess.run([_node(),str(RUNTIME)],input=json.dumps(payload,ensure_ascii=False),capture_output=True,text=True,timeout=max(120,len(files)*3))
        if result.returncode:
            detail=(result.stderr or result.stdout).strip()[:2000]
            return {'findings': [],'errors':[{'path':p,'reason':f'frontend runtime failed ({result.returncode}): {detail}'} for p,_ in files]}
        report=json.loads(result.stdout)
        if not isinstance(report,dict) or not isinstance(report.get('findings'),list) or not isinstance(report.get('errors'),list):
            raise ValueError('frontend runtime returned invalid report schema')
        for item in report['findings']+report['errors']:
            if item.get('path') in original_paths:
                item['path']=original_paths[item['path']]
        return report
    except (OSError,ValueError,subprocess.TimeoutExpired) as exc:
        return {'findings': [],'errors':[{'path':p,'reason':f'frontend runtime unavailable: {exc}'} for p,_ in files]}
