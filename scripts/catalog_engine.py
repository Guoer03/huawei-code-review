"""Execute imported rules and make implementation/analysis gaps explicit."""
from __future__ import annotations

from collections import Counter, defaultdict
from copy import deepcopy
import hashlib
import importlib
import json
import platform
import re
from pathlib import Path
from typing import Iterable

try:
    from .config import Config, ConfigError, path_is_ignored
except ImportError:
    from config import Config, ConfigError, path_is_ignored

ROOT = Path(__file__).resolve().parents[1]
STATES = {'implemented', 'partial', 'manual', 'unavailable'}
MODULES = {'java': 'catalog_java', 'python': 'catalog_python',
           'javascript': 'catalog_frontend', 'typescript': 'catalog_frontend'}


def catalog_entries(config: Config | None = None) -> list[dict]:
    entries = json.loads((ROOT / 'rulesets/catalog.json').read_text(encoding='utf-8'))['rules']
    keys = [item['key'] for item in entries]
    if len(keys) != len(set(keys)):
        raise ConfigError('duplicate rule identity in catalog')
    if config and config.rule_options:
        known = {entry['id']: entry for entry in entries}
        known.update({entry['key']: entry for entry in entries})
        modified = set()
        for identity, options in config.rule_options.items():
            if identity not in known:
                raise ConfigError(f'unknown rule for options: {identity}')
            entry = known[identity]
            if entry['key'] in modified:
                raise ConfigError(f'duplicate option settings by ID and key: {identity}')
            modified.add(entry['key'])
            rule = entry['rule']
            exported = deepcopy(rule.get('options', []))
            entry['exported_options'] = exported
            declared = {option['optionKey']: option for option in rule.get('options', [])}
            for name, value in options.items():
                if name not in declared:
                    raise ConfigError(f'unknown option {name} for rule {identity}')
                if name == 'credentialWords':
                    if not isinstance(value, str) or not value.strip():
                        raise ConfigError(f'option {name} must be a nonempty comma-separated string')
                else:
                    if isinstance(value, bool) or not isinstance(value, (str, int)) or not re.fullmatch(r'\d+', str(value)):
                        raise ConfigError(f'option {name} must be a nonnegative integer')
                    if name == 'max-line-length' and int(value) == 0:
                        raise ConfigError(f'option {name} must be greater than zero')
                    value = str(int(value))
                declared[name]['optionValue'] = str(value)
            if options:
                entry['option_source'] = 'project-config'
    return entries


def implementation_manifest() -> dict[str, dict]:
    manifest = {}
    for language in MODULES:
        path = ROOT / 'rulesets/implementations' / (language + '.json')
        if not path.exists():
            continue
        rows = json.loads(path.read_text(encoding='utf-8'))
        for row in rows:
            key = (language, row['rule_id'])
            if key in manifest or row['status'] not in STATES:
                raise ConfigError(f'invalid or duplicate implementation manifest entry: {key}')
            if row['status'] == 'implemented' and (not row.get('detector') or not row.get('test_cases')):
                raise ConfigError(f'implemented rule lacks detector or test evidence: {key}')
            manifest[key] = row
    return manifest


def rule_inventory(config: Config, languages: set[str] | None = None) -> list[dict]:
    entries = catalog_entries(config)
    all_ids = {r['id'] for r in entries} | {r['key'] for r in entries}
    if config.enabled_rules is not None:
        unknown = set(config.enabled_rules) - all_ids
        if unknown:
            raise ConfigError('unknown selected rule: ' + ', '.join(sorted(unknown)))
    manifests = implementation_manifest()
    rows = []
    for entry in entries:
        rule = entry['rule']
        language = rule['language'].lower()
        if languages is not None and language not in languages:
            continue
        if config.enabled_rules is not None and rule['id'] not in config.enabled_rules and entry['key'] not in config.enabled_rules:
            continue
        if rule['id'] in config.disabled_rules or entry['key'] in config.disabled_rules:
            continue
        if rule['id'] in config.ignore or entry['key'] in config.ignore:
            continue
        impl = manifests.get((language, rule['id']), {})
        status = impl.get('status', 'unavailable')
        rows.append({'key': entry['key'], 'rule_id': rule['id'],
            'criterion_set_id': entry['criterion_set_id'], 'language': language,
            'title': rule.get('nameCn') or rule.get('name', rule['id']),
            'implementation_status': status, 'coverage_status': 'not-run', 'execution_status': 'not-run',
            'detector': impl.get('detector', ''),
            'reason': impl.get('reason') or 'No executable implementation registered.',
            'test_cases': [*impl.get('test_cases', []), *impl.get('supplementary_test_files', [])], 'options': rule.get('options', []),
            'exported_options': entry.get('exported_options', deepcopy(rule.get('options', []))),
            'option_source': entry.get('option_source', 'user-export'),
            'raw_severity': rule.get('severity'), 'findings': 0,
            'source': {'id': 'codearts-user-export', 'status': 'user-exported'}})
    return rows


def coverage_summary(rows: list[dict]) -> dict:
    counts = Counter(r['implementation_status'] for r in rows)
    return {'catalog_checked': True, 'selected_rules': len(rows),
        **{state: counts[state] for state in sorted(STATES)},
        'executed_rules': sum(r['execution_status'] == 'completed' for r in rows),
        'complete': bool(rows) and all(r['coverage_status'] == 'covered' for r in rows),
        'meaning': 'Coverage of the selected local interpretation; not equivalence to proprietary CodeArts engines.'}


def analyzer_evidence(language: str, result: dict) -> tuple[dict, str]:
    """Identify the actual analyzer and context used for a repair comparison."""
    scripts = ROOT / 'scripts'
    assets = [scripts / 'catalog_engine.py', scripts / 'engine.py',
              scripts / (MODULES[language] + '.py'),
              ROOT / 'rulesets/implementations' / (language + '.json')]
    if language == 'java':
        assets.append(scripts / 'java_rules/AstDump.java')
        assets.extend(sorted((scripts / 'java_rules').glob('*.py')))
    elif language == 'python':
        assets.extend(sorted(scripts.glob('python_*.py')))
    elif language in {'javascript', 'typescript'}:
        assets.extend(sorted((scripts / 'frontend_rules').glob('*.cjs')))
        assets.append(scripts / 'frontend_rules/mappings.json')
    digest = hashlib.sha256()
    for asset in assets:
        digest.update(str(asset.relative_to(ROOT)).encode('utf-8'))
        digest.update(asset.read_bytes())
    evidence = {'python': platform.python_version(), 'source_sha256': digest.hexdigest(),
                **{key: result[key] for key in ('engines', 'type_context', 'toolchain') if key in result}}
    fingerprint = hashlib.sha256(json.dumps(evidence, sort_keys=True).encode('utf-8')).hexdigest()
    return evidence, fingerprint


def inventory_report(config: Config) -> dict:
    langs = None if config.language == 'auto' else {config.language}
    rows = rule_inventory(config, langs)
    return {'schema_version': '1.0', 'summary': {'files': 0, 'findings': 0, 'errors': 0,
        'warnings': 0, 'infos': 0, 'pass': False}, 'findings': [], 'uncovered': [],
        'rule_coverage': rows, 'coverage_summary': coverage_summary(rows),
        'toolchain': {'checker': 'huawei-code-review', 'version': '0.4.0', 'ruleset': 'catalog', 'mode': 'inventory'}}


def affected_rule_ids(errors: list[dict], active: list[dict]) -> set[str]:
    """Accept explicit nonempty scopes only when every ID belongs to this scan.

    Parser/runtime failures omit scope and invalidate the whole language run.
    Malformed scopes also fail closed rather than silently losing coverage gaps.
    """
    available = {row['rule_id'] for row in active}
    failed = set()
    for error in errors:
        scope = error.get('affected_rule_ids') if isinstance(error, dict) else None
        if (not isinstance(scope, list) or not scope
                or any(not isinstance(item, str) or item not in available for item in scope)):
            return available
        failed.update(scope)
    return failed


def check_catalog(inputs: Iterable[str], language: str, config: Config, excludes=None,
                  ignore=None, fail_on=None, allow_uncovered=None) -> dict:
    try:
        from .engine import files_for, language_for, exit_code, _severity_overrides
    except ImportError:
        from engine import files_for, language_for, exit_code, _severity_overrides
    from dataclasses import replace
    config = replace(config, ignore=[*config.ignore, *(ignore or [])])
    files, uncovered = files_for(inputs, [*config.exclude, *(excludes or [])], config.include_hidden)
    selected_language = language if language != 'auto' else config.language
    grouped = defaultdict(list)
    for path, text in files:
        lang = language_for(path, selected_language, text)
        if not lang:
            uncovered.append({'path': path, 'reason': 'language could not be inferred'})
        elif not path_is_ignored(path, config.ignore):
            grouped[lang].append((path, text))
    if not grouped:
        uncovered.append({'path': '<inputs>', 'reason': 'No supported source files were selected.'})
    rows = rule_inventory(config, set(grouped))
    row_by_key = {(r['language'], r['rule_id']): r for r in rows}
    entries = {(e['rule']['language'].lower(), e['id']): e for e in catalog_entries(config)}
    findings = []
    analyzers = {}
    severity_overrides = _severity_overrides(config)
    file_text = dict(files)
    for lang, sources in grouped.items():
        selected = [r for r in rows if r['language'] == lang]
        active = [r for r in selected if r['implementation_status'] in {'implemented', 'partial'}]
        errors = []
        if active:
            try:
                module = importlib.import_module(('.' if __package__ else '') + MODULES[lang], package=__package__)
                result = module.scan(sources, [entries[(lang, row['rule_id'])] for row in active])
                if not isinstance(result, dict) or not isinstance(result.get('errors'), list) or not isinstance(result.get('findings'), list):
                    raise ValueError('Analyzer returned invalid findings/errors arrays')
                analyzers[lang], fingerprint = analyzer_evidence(lang, result)
                for row in active:
                    row['detector_fingerprint'] = fingerprint
                errors = result.get('errors', [])
                for finding in result.get('findings', []):
                    if not isinstance(finding, dict) or finding.get('path') not in dict(sources):
                        raise ValueError('Analyzer emitted a finding outside the scanned source files')
                    row = row_by_key.get((lang, finding.get('id')))
                    if row is None:
                        raise ValueError(f"Analyzer emitted an unselected rule: {finding.get('id')}")
                    item = dict(finding)
                    item.update({'rule_key': row['key'], 'criterion_set_id': row['criterion_set_id'],
                        'raw_severity': row['raw_severity'], 'implementation_status': row['implementation_status'],
                        'coverage_status': 'covered' if row['implementation_status'] == 'implemented' else 'candidate',
                        'source': row['source'], 'detector': row['detector']})
                    item['severity'] = severity_overrides.get(item['id'], item.get('severity', 'warning'))
                    # A numeric export severity is retained but never guessed into local levels.
                    item['severity_policy'] = 'local-detector; raw export severity retained without conversion'
                    line = int(item.get('line', 1))
                    source_lines = file_text.get(item['path'], '').splitlines()
                    if 0 < line <= len(source_lines):
                        item['evidence'] = source_lines[line - 1].strip()[:500]
                    findings.append(item)
            except (ImportError, OSError, ValueError, RuntimeError) as exc:
                errors = [{'path': '<' + lang + '-analyzer>', 'reason': str(exc)}]
            uncovered.extend(errors)
        failed_rules = affected_rule_ids(errors, active)
        for row in selected:
            status = row['implementation_status']
            failed = row['rule_id'] in failed_rules
            if status in {'implemented', 'partial'} and not failed:
                row['execution_status'] = 'completed'
                row['coverage_status'] = 'covered' if status == 'implemented' else 'candidate'
            else:
                row['execution_status'] = 'error' if failed and status in {'implemented', 'partial'} else 'not-run'
                row['coverage_status'] = 'error' if row['execution_status'] == 'error' else 'opaque'
        incomplete = [r for r in selected if r['coverage_status'] != 'covered']
        if incomplete:
            uncovered.append({'path': '<' + lang + '-rules>', 'reason': f'{len(incomplete)} selected rules lack complete verified execution.',
                              'rule_ids': [r['rule_id'] for r in incomplete]})
        if not selected:
            uncovered.append({'path': '<' + lang + '-rules>', 'reason': 'No rules selected for this language.'})
    for finding in findings:
        finding['coverage_status'] = row_by_key[(finding['language'], finding['id'])]['coverage_status']
    counts = Counter(f['severity'] for f in findings)
    by_rule = Counter((f['language'], f['id']) for f in findings)
    for row in rows:
        row['findings'] = by_rule[(row['language'], row['rule_id'])]
    findings.sort(key=lambda f: (f['path'], f['line'], f['column'], f['id']))
    threshold = fail_on or config.fail_on
    report = {'schema_version': '1.0', 'findings': findings, 'uncovered': uncovered,
        'input_files': [{'path': path, 'language': lang, 'sha256': hashlib.sha256(text.encode('utf-8')).hexdigest()}
                        for lang, sources in grouped.items() for path, text in sources],
        'summary': {'files': sum(map(len, grouped.values())), 'findings': len(findings),
                    **{s + 's': counts[s] for s in ('error', 'warning', 'info')}},
        'rule_coverage': rows, 'coverage_summary': coverage_summary(rows),
        'review_tasks': [{'rule_key': r['key'], 'rule_id': r['rule_id'], 'language': r['language'],
                          'title': r['title'], 'reason': r['reason'], 'status': 'pending',
                          'paths': [path for path, _ in grouped[r['language']]],
                          'instruction': 'Review source and project context against this rule; record evidence or unresolved context. Do not infer a violation from this task.'}
                         for r in rows if r['implementation_status'] in {'partial', 'manual'}],
        'toolchain': {'checker': 'huawei-code-review', 'version': '0.4.0', 'ruleset': 'catalog',
                      'profile': config.profile, 'config': config.source, 'fail_on': threshold,
                      'analyzers': analyzers}}
    permitted = config.allow_uncovered if allow_uncovered is None else allow_uncovered
    report['summary']['pass'] = exit_code(report, threshold, permitted) == 0
    report['coverage_summary']['complete'] = report['coverage_summary']['complete'] and not bool(uncovered)
    report['summary']['uncovered_allowed'] = permitted
    return report
