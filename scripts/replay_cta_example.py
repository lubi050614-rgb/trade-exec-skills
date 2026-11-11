"""Replay a trusted prepared local fixture through its real standalone skill entry."""
import argparse
import json
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]


def main():
    p=argparse.ArgumentParser(); p.add_argument('--tool',required=True); a=p.parse_args()
    catalog=json.loads((ROOT/'contracts/cta-catalog.json').read_text(encoding='utf-8'))
    if a.tool not in catalog: p.error('Unknown CTA tool')
    folder=ROOT/'skills'/a.tool
    state=json.loads((folder/'assets/prepared-state.json').read_text(encoding='utf-8'))
    req=json.loads((folder/'assets/example.json').read_text(encoding='utf-8'))
    with tempfile.TemporaryDirectory() as tmp:
        path=Path(tmp)/'replay.sqlite'; db=sqlite3.connect(path)
        db.execute('CREATE TABLE cta_sessions (id TEXT PRIMARY KEY,payload TEXT NOT NULL)')
        db.execute('INSERT INTO cta_sessions VALUES (?,?)',(req['simulation_id'],json.dumps(state))); db.commit(); db.close()
        result=subprocess.run([sys.executable,str(folder/'scripts/run.py'),'--db',str(path),'--input',str(folder/'assets/example.json')],cwd=tmp,capture_output=True,text=True)
        print(result.stdout.strip())
        if result.stderr: print(result.stderr,file=sys.stderr)
        return result.returncode


if __name__=='__main__': raise SystemExit(main())
