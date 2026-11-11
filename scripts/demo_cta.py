"""Run a reproducible futures reversal or a long/short settlement example."""
import argparse
import json
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from cta_execution.engine import Runtime


def main():
    p=argparse.ArgumentParser(); p.add_argument('--db',default='cta-demo.sqlite')
    p.add_argument('--scenario',choices=['reverse','settle-long','settle-short'],default='reverse'); a=p.parse_args()
    side='short' if a.scenario=='settle-short' else 'long'
    f=json.loads((ROOT/'examples/cta'/side/'session.json').read_text(encoding='utf-8'))
    r=Runtime(a.db); r.initialize(**f); counter=0; results=[]
    def call(tool,data):
        nonlocal counter
        counter+=1
        request=dict(schema_version='1.0',request_id=str(counter),idempotency_key=str(counter),account_id=f['account']['account_id'],simulation_id=f['simulation_id'],asset_class='FUTURES',data=data)
        response=r.call(tool,request)
        if not response['ok']: raise ValueError(response)
        results.append(dict(tool=tool,result=response['data'])); return response['data']
    if a.scenario.startswith('settle-'):
        data=json.loads((ROOT/'examples/cta'/side/'settlement.json').read_text(encoding='utf-8'))['data']
        call('cta-daily-settle',data)
    else:
        plan=json.loads((ROOT/'examples/cta/plan.json').read_text(encoding='utf-8'))['data']
        plan=call('cta-order-plan',plan)
        account_version=1; now=f['account']['as_of']
        def submit(lid):
            return call('cta-order-submit',dict(leg_id=lid,account_version=account_version,submitted_at=now,client_order_id=lid))
        submit(plan['leg_ids'][0])
        for i,q in enumerate([2,1,1],start=1):
            b=json.loads((ROOT/'examples/cta/minute.json').read_text(encoding='utf-8'))
            b.update(event_id='demo-'+str(i),volume=q,start_at=now,end_at=f'2026-01-05T09:0{i+1}:00+08:00')
            result=call('cta-execution-simulate',dict(bar=b,visible_at=b['end_at'],participation_rate='1',slippage='0'))
            account_version=result['account']['version']; now=b['end_at']
            if i==2: submit(plan['leg_ids'][1])
        call('cta-order-query',dict(order_id='cta-o2'))
    print(json.dumps(results,ensure_ascii=False,indent=2)); r.db.close()


if __name__=='__main__': main()
