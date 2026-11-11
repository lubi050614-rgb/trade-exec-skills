"""Run the implementation checks and the official OpenSpec validator when available."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from datetime import datetime, timezone, timedelta

ROOT=Path(__file__).resolve().parents[1]


def main():
    p=argparse.ArgumentParser(); p.add_argument('--skip-tests',action='store_true')
    p.add_argument('--change',action='append',help='Change name; default validates both stock and CTA')
    p.add_argument('--skill-validator',help='Optional skill-creator quick_validate.py path')
    a=p.parse_args(); changes=a.change or ['stock-execution-tools','cta-execution-tools']
    checks=[]
    def run(name,cmd):
        env=dict(os.environ,OPENSPEC_TELEMETRY='0',PYTHONUTF8='1')
        result=subprocess.run(cmd,cwd=ROOT,capture_output=True,text=True,encoding='utf-8',env=env)
        checks.append(dict(name=name,status='passed' if result.returncode==0 else 'failed',command=cmd,stdout=result.stdout,stderr=result.stderr))
        print(name+': '+checks[-1]['status'])
    if not a.skip_tests: run('unittest',[sys.executable,'-m','unittest','discover','-s','tests','-v'])
    node=ROOT/'.runtime/node-v22.16.0-win-x64/node.exe'
    cli=ROOT/'.runtime/openspec/node_modules/@fission-ai/openspec/bin/openspec.js'
    if node.exists() and cli.exists(): command=[str(node),str(cli)]
    elif shutil.which('openspec'): command=[shutil.which('openspec')]
    else: command=None
    if command:
        for change in changes:
            run('openspec-strict:'+change,command+['validate',change,'--strict'])
            run('openspec-status:'+change,command+['status','--change',change,'--json'])
    else: checks.append(dict(name='openspec-strict',status='not_run',reason='Official OpenSpec CLI not installed'))
    if a.skill_validator:
        run('codex-skill-validation',[sys.executable,'scripts/validate_skills.py','--validator',a.skill_validator])
    report=dict(timestamp=datetime.now(timezone(timedelta(hours=8))).isoformat(),checks=checks,
                external_checks_not_run=['real_account_api','ClickHouse','official_exchange_rules','native_platform_export_validator'])
    for change in changes:
        dest=ROOT/'openspec/changes'/change/'verification-report.json'
        dest.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return 1 if any(c['status']=='failed' for c in checks) else 0


if __name__=='__main__': raise SystemExit(main())
