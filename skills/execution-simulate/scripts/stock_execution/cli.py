import argparse
import json
import sys
from pathlib import Path
from .engine import Runtime


def run(tool=None):
    parser=argparse.ArgumentParser()
    parser.add_argument('--db', default='simulation.sqlite')
    if tool is None:
        parser.add_argument('tool')
    parser.add_argument('--input', help='JSON file; otherwise read stdin')
    parser.add_argument('--init', help='Initialize a new simulation using a fixture JSON file')
    args=parser.parse_args()
    try:
        runtime=Runtime(args.db)
        if args.init:
            f=json.loads(Path(args.init).read_text(encoding='utf-8'))
            runtime.initialize(f['simulation_id'],f['account'],f['rules'],f.get('frequency','1m'),f.get('fee'))
        req=json.loads(Path(args.input).read_text(encoding='utf-8') if args.input else sys.stdin.read())
        result=runtime.call(tool or args.tool,req)
    except Exception as e:
        result=dict(ok=False,schema_version='1.0',request_id='',error=dict(code='CLI_ERROR',message=str(e),retryable=False,details={}))
    print(json.dumps(result,ensure_ascii=False))
    return 0 if result['ok'] else 1


if __name__=='__main__':
    sys.exit(run())
