import argparse
import json
import sys
from pathlib import Path
from .engine import Runtime


def run(tool):
    p=argparse.ArgumentParser(); p.add_argument('--db',default='cta.sqlite'); p.add_argument('--input'); p.add_argument('--init')
    a=p.parse_args()
    try:
        r=Runtime(a.db)
        if a.init: r.initialize(**json.loads(Path(a.init).read_text(encoding='utf-8')))
        request=json.loads(Path(a.input).read_text(encoding='utf-8') if a.input else sys.stdin.read())
        result=r.call(tool,request); r.db.close()
    except Exception as e:
        result=dict(ok=False,schema_version='1.0',request_id='',error=dict(code='CLI_ERROR',message=str(e),retryable=False,details={}))
    print(json.dumps(result,ensure_ascii=False))
    return 0 if result['ok'] else 1
