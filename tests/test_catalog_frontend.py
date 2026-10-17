"""Catalog-level positive/negative and failure-boundary tests for the frontend engine."""
import json
import os
import sys
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from catalog_frontend import scan, runtime_status

class FrontendCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = json.loads((ROOT/'rulesets/catalog.json').read_text())['rules']
        cls.entries = [r for r in cls.catalog if r['rule']['language'] in ('JAVASCRIPT','TYPESCRIPT')]
        cls.manifest = sum([json.loads((ROOT/f'rulesets/implementations/{lang}.json').read_text()) for lang in ('javascript','typescript')], [])
        cls.cases = json.loads((ROOT/'tests/catalog_cases/frontend.json').read_text())

    def test_all_161_rules_have_honest_manifest(self):
        self.assertEqual(len(self.manifest), 161)
        self.assertEqual({r['id'] for r in self.entries},{r['rule_id'] for r in self.manifest})
        for row in self.manifest:
            self.assertIn(row['status'], ('implemented','partial','manual','unavailable'))
            self.assertTrue(row['reason'])
            if row['status']=='implemented':
                self.assertTrue(row['test_cases'], row['title'])
                self.assertTrue(any(c['rule_id']==row['rule_id'] for c in self.cases))

    def test_each_detector_positive_negative(self):
        if not runtime_status()['available']:
            self.skipTest('Install frontend_rules dependencies or set HCR_NODE_MODULES')
        files=[]
        for i,c in enumerate(self.cases):
            suffix='ts' if c['language']=='typescript' else 'js'
            files += [(f'/virtual_hcr/case_{i}_bad.{suffix}',c['bad']), (f'/virtual_hcr/case_{i}_good.{suffix}',c['good'])]
        report=scan(files,self.entries)
        self.assertEqual(len(report['errors']),0,report['errors'][:5])
        actual={(f['path'],f['id']) for f in report['findings']}
        for i,c in enumerate(self.cases):
            suffix='ts' if c['language']=='typescript' else 'js'
            with self.subTest(rule=c['rule_id'], name=c['name']):
                if c['rule_id']=='da6b955c6db811eea68ffa163e0fa374':
                    # Each fixture is an independent project. Cross-file duplicate
                    # detection must not compare unrelated fixture programs.
                    selected=[r for r in self.entries if r['id']==c['rule_id']]
                    bad=scan([(f'/virtual_hcr/case_{i}_bad.{suffix}',c['bad'])],selected)
                    good=scan([(f'/virtual_hcr/case_{i}_good.{suffix}',c['good'])],selected)
                    self.assertEqual(bad['errors']+good['errors'],[])
                    self.assertTrue(bad['findings'],'positive example not detected')
                    self.assertFalse(good['findings'],'negative example incorrectly detected')
                else:
                    self.assertTrue((f'/virtual_hcr/case_{i}_bad.{suffix}',c['rule_id']) in actual, 'positive example not detected')
                    self.assertFalse((f'/virtual_hcr/case_{i}_good.{suffix}',c['rule_id']) in actual, 'negative example incorrectly detected')

    def test_comments_and_strings_not_executable_code(self):
        if not runtime_status()['available']:
            self.skipTest('frontend runtime unavailable')
        ids={'da73a29a6db811eea68ffa163e0fa374','da739ee36db811eea68ffa163e0fa374','da73b88f6db811eea68ffa163e0fa374'}
        entries=[r for r in self.entries if r['id'] in ids]
        r=scan([('safe.js','// debugger; eval(code); a == b;\nconst text = "debugger; eval(code); a == b;";')],entries)
        self.assertEqual(r['findings'],[])
        self.assertEqual(r['errors'],[])

    def test_parse_failure_is_not_a_clean_result(self):
        if not runtime_status()['available']:
            self.skipTest('frontend runtime unavailable')
        r=scan([('broken.ts','export const = ;')],self.entries)
        self.assertTrue(r['errors'])

    def test_filename_case_is_checked_without_parser_failure(self):
        if not runtime_status()['available']:
            self.skipTest('frontend runtime unavailable')
        rid='da73d87c6db811eea68ffa163e0fa374'
        entries=[r for r in self.entries if r['id']==rid]
        result=scan([('Upper.JS','const value=1;'),('lower.js','const value=1;')],entries)
        self.assertEqual(result['errors'],[])
        self.assertEqual([f['path'] for f in result['findings']],['Upper.JS'])

    def test_project_inline_directives_cannot_disable_catalog_policy(self):
        if not runtime_status()['available']:
            self.skipTest('frontend runtime unavailable')
        rid='da73a29a6db811eea68ffa163e0fa374'
        entries=[r for r in self.entries if r['id']==rid]
        report=scan([('file.js','/* eslint-disable */\ndebugger;')],entries)
        self.assertEqual(report['errors'],[])
        self.assertEqual([f['id'] for f in report['findings']],[rid])
        self.assertEqual(report['findings'][0]['raw_severity'],entries[0]['rule']['severity'])
        self.assertIn('local',report['findings'][0]['severity_policy'])
        for key in ('node','eslint','typescript','typescript_eslint_parser','typescript_eslint_plugin','frontend_rules_sha256'):
            self.assertTrue(report['engines'][key])
        for key in ('compiler_options_sha256','declaration_files_sha256'):
            self.assertEqual(len(report['type_context'][key]),64)

    def test_vue_patterns_do_not_become_false_bug_candidates(self):
        if not runtime_status()['available']:
            self.skipTest('frontend runtime unavailable')
        ids={'da6bbc486db811eea68ffa163e0fa374','da6d2a466db811eea68ffa163e0fa374'}
        entries=[r for r in self.entries if r['id'] in ids]
        source="""
function warn(): void {}
declare const enabled: boolean;
enabled && warn();
function stop(): void { return warn(); }
const values: number[] = [];
while (enabled) { const last = values[0]; if (last) break; values.push(1); }
"""
        result=scan([('vue-pattern.ts',source)],entries)
        self.assertEqual(result['errors'],[])
        self.assertEqual(result['findings'],[])

    def test_template_and_regex_content_is_not_a_comment(self):
        if not runtime_status()['available']:
            self.skipTest('frontend runtime unavailable')
        ids={'da73e2a76db811eea68ffa163e0fa374','da73e1d06db811eea68ffa163e0fa374'}
        entries=[r for r in self.entries if r['id'] in ids]
        source='const value = `hello ${name} // author: jane@company.com`;\nconst regex = /author: jane@company.com/;'
        result=scan([('literals.js',source)],entries)
        self.assertEqual(result['errors'],[])
        self.assertEqual(result['findings'],[])

    def test_missing_import_type_information_is_incomplete(self):
        if not runtime_status()['available']:
            self.skipTest('frontend runtime unavailable')
        entries=[r for r in self.entries if r['id']=='da6bd7d46db811eea68ffa163e0fa374']
        result=scan([('/virtual_hcr/import.ts','import {values} from \"missing-hcr-test-package\"; for(const key in values) {}')],entries)
        self.assertTrue(result['errors'])
        self.assertTrue(any('module' in e['reason'].lower() for e in result['errors']))

    def test_imported_array_is_resolved_across_supplied_sources(self):
        if not runtime_status()['available']:
            self.skipTest('frontend runtime unavailable')
        entries=[r for r in self.entries if r['id']=='da6bd7d46db811eea68ffa163e0fa374']
        result=scan([('/virtual_hcr/values.ts','export const values = [1,2];'),('/virtual_hcr/use.ts','import {values} from \"./values\"; for(const key in values) {}')],entries)
        self.assertEqual(result['errors'],[])
        self.assertEqual([f['path'] for f in result['findings']],['/virtual_hcr/use.ts'])

    def test_explicit_project_path_aliases_and_catalog_options(self):
        if not runtime_status()['available']:
            self.skipTest('frontend runtime unavailable')
        import tempfile
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as tmp:
            cfg=Path(tmp)/'tsconfig.json'
            cfg.write_text(json.dumps({'compilerOptions':{'baseUrl':'.','paths':{'@model/*':['models/*']}}}))
            entries=[r for r in self.entries if r['id']=='da6bd7d46db811eea68ffa163e0fa374']
            with patch.dict(os.environ, {'HCR_TS_CONFIG':str(cfg)}):
                result=scan([(str(Path(tmp)/'models/values.ts'),'export const values = [1,2];'),(str(Path(tmp)/'use.ts'),'import {values} from \"@model/values\"; for(const key in values) {}')],entries)
            self.assertEqual(result['errors'],[])
            self.assertEqual(len(result['findings']),1)
        import copy
        entry=copy.deepcopy(next(r for r in self.entries if r['id']=='da6d4f676db811eea68ffa163e0fa374'))
        entry['rule']['options'][0]['optionValue']='1'
        result=scan([('/virtual_hcr/options.ts','switch(value){case 1: break; case 2: break;}')],[entry])
        self.assertEqual(result['errors'],[])
        self.assertEqual(len(result['findings']),1)

    def test_vue_dataflow_candidates_respect_reads_and_delegation(self):
        if not runtime_status()['available']:
            self.skipTest('frontend runtime unavailable')
        ids={'da6bc7c46db811eea68ffa163e0fa374','da6b55d06db811eea68ffa163e0fa374','da6b49c76db811eea68ffa163e0fa374'}
        source="""
function normalize(value: number) { value = value + 1; return value; }
const stack: number[] = [];
stack.push(1);
const last = stack.pop();
class State { _set(value: number) {} set value(value: number) { this._set(value); } }
"""
        result=scan([('/virtual_hcr/vue-dataflow.ts',source)],[r for r in self.entries if r['id'] in ids])
        self.assertEqual(result['errors'],[])
        self.assertEqual(result['findings'],[])

    def test_unknown_rule_is_incomplete(self):
        if not runtime_status()['available']:
            self.skipTest('frontend runtime unavailable')
        result=scan([('file.js','const value=1;')],[{'rule':{'id':'unknown-export-id','language':'JAVASCRIPT'}}])
        self.assertTrue(result['errors'])

    def test_explicit_dependency_source_is_not_ignored_by_eslint(self):
        if not runtime_status()['available']:
            self.skipTest('frontend runtime unavailable')
        entry=next(r for r in self.entries if r['id']=='da73a29a6db811eea68ffa163e0fa374')
        result=scan([('/virtual_hcr/node_modules/example/index.js','debugger;')],[entry])
        self.assertEqual(result['errors'],[])
        self.assertEqual([f['id'] for f in result['findings']],[entry['id']])

    def test_missing_project_type_library_is_not_complete(self):
        if not runtime_status()['available']:
            self.skipTest('frontend runtime unavailable')
        import tempfile
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as tmp:
            config=Path(tmp)/'tsconfig.json'
            config.write_text(json.dumps({'compilerOptions':{'types':['missing-hcr-types']}}))
            with patch.dict(os.environ, {'HCR_TS_CONFIG':str(config)}):
                result=scan([(str(Path(tmp)/'input.ts'),'export const values: number[] = [];')],self.entries)
        self.assertTrue(any('missing-hcr-types' in e['reason'] for e in result['errors']),result)

    def test_missing_runtime_is_reported(self):
        from unittest.mock import patch
        with patch.dict(os.environ, {'HCR_NODE':'/missing/hcr-node'}):
            result=scan([('file.js','debugger;')],self.entries)
        self.assertTrue(result['errors'])

if __name__=='__main__': unittest.main()
