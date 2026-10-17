#!/usr/bin/env python3
"""Rehearse scan/behavior-test/repair/rescan on a disposable Python example.

This validates the CLI contract used by the Skill, not an autonomous AI model.
Never point --output at a source repository: the dedicated demo.py is replaced.
"""
import argparse
import difflib
import json
from pathlib import Path
import subprocess
import sys

from scripts.compare_reports import compare_reports
from scripts.xlsx_export import write_xlsx

RULE = 'da6b2b5d6db811eea68ffa163e0fa374'
BAD = 'def append_item(item, values=[]):\n    values.append(item)\n    return values\n'
GOOD = 'def append_item(item, values=None):\n    if values is None:\n        values = []\n    values.append(item)\n    return values\n'
BEHAVIOR = '''import demo
assert demo.append_item(1) == [1]
assert demo.append_item(2) == [2], "default list leaked across calls"
owned = []
assert demo.append_item(3, owned) is owned
assert owned == [3], "explicit list behavior changed"
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    source = output / 'demo.py'
    if source.exists():
        raise ValueError('Use a fresh output directory for immutable repair evidence')
    commands=[]
    def scan(label):
        path=output/(label+'.json')
        command=[sys.executable,'-m','scripts.check',str(source),'--select',RULE,
                 '--fail-on','warning','--output',str(path)]
        run=subprocess.run(command,cwd=output,text=True,capture_output=True,timeout=30)
        commands.append({'command':command,'exit_code':run.returncode,'stderr':run.stderr})
        report=json.loads(path.read_text())
        write_xlsx(report,output/(label+'.xlsx'))
        return report,run.returncode
    def behavior(label):
        command=[sys.executable,'-B','-c',BEHAVIOR]
        run=subprocess.run(command,cwd=output,text=True,capture_output=True,timeout=30)
        (output/(label+'-test.log')).write_text(run.stdout+run.stderr)
        commands.append({'command':command,'exit_code':run.returncode})
        return run.returncode
    source.write_text(BAD)
    before,before_exit=scan('before')
    assert before_exit==1 and len(before['findings'])==1
    assert behavior('before')==1, 'Behavior regression must fail before repair'
    plan={'rule_id':RULE,'path':str(source),'reason':'Default list persists between calls',
          'edit':'Create a fresh list only when caller omits the values argument',
          'tests':['independent repeated calls','explicit caller-owned list identity'],
          'provenance':'deterministic repair workflow rehearsal'}
    (output/'repair-plan.json').write_text(json.dumps(plan,indent=2))
    source.write_text(GOOD)
    assert behavior('after')==0, 'Repaired behavior must pass'
    after,after_exit=scan('after')
    assert after_exit==0 and after['coverage_summary']['complete']
    delta=compare_reports(before,after)
    assert len(delta['resolved'])==1 and not delta['unverified_resolutions']
    (output/'delta.json').write_text(json.dumps(delta,indent=2))
    (output/'changes.diff').write_text(''.join(difflib.unified_diff(BAD.splitlines(True),GOOD.splitlines(True),fromfile='before/demo.py',tofile='after/demo.py')))
    (output/'run.json').write_text(json.dumps({'commands':commands,'verified':True,
        'scope':'disposable fixture; selected mutable-default rule only; no AI autonomy claim'},indent=2))
    print(json.dumps({'verified':True,'resolved':len(delta['resolved']),'output':str(output)}))


if __name__=='__main__':main()
