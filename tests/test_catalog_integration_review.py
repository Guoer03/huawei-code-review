"""Independent end-to-end checks against false-clean and false-resolution states."""
import copy
from contextlib import redirect_stdout,redirect_stderr
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.engine import check,exit_code
from scripts.check import main as cli_main
from scripts.config import Config
from scripts.compare_reports import compare_reports

RULE='da6b2b5d6db811eea68ffa163e0fa374'


class CatalogIntegrationReviewTests(unittest.TestCase):
    def scan(self,paths):
        return check(paths,config=Config(enabled_rules=[RULE],fail_on='warning'))

    def test_project_helper_changes_invalidate_analyzer_fingerprint(self):
        import shutil
        from unittest.mock import patch
        from scripts import catalog_engine
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shutil.copytree(ROOT / 'scripts', root / 'scripts', ignore=shutil.ignore_patterns('__pycache__'))
            shutil.copytree(ROOT / 'rulesets', root / 'rulesets')
            for language, helper in [
                ('python', 'python_project.py'), ('python', 'python_stdlib_models.py'),
                ('java', 'java_rules/project_symbols.py'), ('java', 'java_rules/control_flow.py'),
                ('javascript', 'frontend_rules/completion_flow.cjs'),
                ('typescript', 'frontend_rules/completion_flow.cjs'),
            ]:
                with self.subTest(language=language), patch.object(catalog_engine, 'ROOT', root):
                    _, before = catalog_engine.analyzer_evidence(language, {})
                    path = root / 'scripts' / helper
                    path.write_text(path.read_text() + '\n# detector implementation changed\n')
                    _, after = catalog_engine.analyzer_evidence(language, {})
                    self.assertNotEqual(before, after)

    def test_explicit_missing_path_cannot_hide_beside_a_clean_file(self):
        with tempfile.TemporaryDirectory() as directory:
            clean=Path(directory)/'clean.py'
            clean.write_text('def collect(items=None):\n    return items\n')
            report=self.scan([str(clean),str(Path(directory)/'missing.py')])
            self.assertEqual(exit_code(report,'warning'),2)
            self.assertFalse(report['coverage_summary']['complete'])

    def test_parser_error_cannot_masquerade_as_resolved(self):
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/'code.py'
            source.write_text('def collect(items=[]):\n    return items\n')
            before=self.scan([str(source)])
            source.write_text('def collect(items=[:\n')
            after=self.scan([str(source)])
            delta=compare_reports(before,after)
            self.assertEqual(exit_code(after,'warning'),2)
            self.assertEqual(delta['resolved'],[])
            self.assertEqual(len(delta['unverified_resolutions']),1)

    def test_selected_rule_removal_cannot_masquerade_as_resolved(self):
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/'code.py'
            source.write_text('def collect(items=[]):\n    return items\n')
            before=self.scan([str(source)])
            after=check([str(source)],config=Config(enabled_rules=['da6b7a386db811eea68ffa163e0fa374']))
            delta=compare_reports(before,after)
            self.assertEqual(delta['resolved'],[])
            self.assertEqual(len(delta['unverified_resolutions']),1)

    def test_path_removal_cannot_masquerade_as_resolved(self):
        with tempfile.TemporaryDirectory() as directory:
            bad=Path(directory)/'bad.py';good=Path(directory)/'good.py'
            bad.write_text('def collect(items=[]):\n    return items\n')
            good.write_text('def collect(items=None):\n    return items\n')
            before=self.scan([str(bad),str(good)]);after=self.scan([str(good)])
            delta=compare_reports(before,after)
            self.assertEqual(delta['resolved'],[])
            self.assertEqual(len(delta['unverified_resolutions']),1)

    def test_changed_rule_options_cannot_masquerade_as_fix(self):
        finding={'id':RULE,'language':'python','path':'code.py','line':1,'column':1,'message':'violation'}
        row={'rule_id':RULE,'language':'python','coverage_status':'covered','execution_status':'completed','detector':'example','options':[{'optionKey':'limit','optionValue':'120'}]}
        before={'findings':[finding],'rule_coverage':[row],'input_files':[{'path':'code.py','sha256':'same'}]}
        after=copy.deepcopy(before);after['findings']=[]
        after['rule_coverage'][0]['options'][0]['optionValue']='200'
        delta=compare_reports(before,after)
        self.assertEqual(delta['resolved'],[])
        self.assertEqual(len(delta['unverified_resolutions']),1)

    def test_required_adapter_failure_invalidates_complete_coverage_summary(self):
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/'clean.py'
            source.write_text('def collect(items=None):\n    return items\n')
            output=io.StringIO()
            with redirect_stdout(output),redirect_stderr(io.StringIO()):
                code=cli_main([str(source),'--select',RULE,'--require-tool','nonexistent-adapter'])
            self.assertEqual(code,2)
            report=json.loads(output.getvalue())
            self.assertFalse(report['summary']['pass'])
            self.assertFalse(report['coverage_summary']['complete'])

    def test_catalog_selection_cannot_be_silently_ignored_by_legacy_mode(self):
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/'bad.py'
            source.write_text('def collect(items=[]):\n    return items\n')
            with redirect_stdout(io.StringIO()),redirect_stderr(io.StringIO()):
                code=cli_main([str(source),'--ruleset','legacy','--select',RULE])
            self.assertEqual(code,2)

    def test_catalog_comparison_without_after_source_inventory_is_unverified(self):
        finding={'id':RULE,'language':'python','path':'code.py','line':1,'column':1,'message':'violation'}
        row={'rule_id':RULE,'language':'python','coverage_status':'covered','execution_status':'completed'}
        before={'findings':[finding],'rule_coverage':[row]}
        after={'findings':[],'rule_coverage':[row]}
        delta=compare_reports(before,after)
        self.assertEqual(delta['resolved'],[])
        self.assertEqual(len(delta['unverified_resolutions']),1)

    def test_analyzer_change_is_not_a_verified_repair(self):
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/'code.py'
            source.write_text('def collect(items=[]):\n    return items\n')
            before=self.scan([str(source)])
            source.write_text('def collect(items=None):\n    return items\n')
            after=self.scan([str(source)])
            self.assertEqual(len(compare_reports(before,after)['resolved']),1)
            after['rule_coverage'][0]['detector_fingerprint']='different-analyzer-version'
            delta=compare_reports(before,after)
            self.assertEqual(delta['resolved'],[])
            self.assertEqual(len(delta['unverified_resolutions']),1)

    def test_removing_context_file_cannot_verify_cross_file_repair(self):
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/'code.py'
            context=Path(directory)/'base.py'
            source.write_text('def collect(items=[]):\n    return items\n')
            context.write_text('class Base: pass\n')
            before=self.scan([str(source),str(context)])
            source.write_text('def collect(items=None):\n    return items\n')
            after=self.scan([str(source)])
            delta=compare_reports(before,after)
            self.assertEqual(delta['resolved'],[])
            self.assertEqual(len(delta['unverified_resolutions']),1)

if __name__=='__main__':unittest.main()
