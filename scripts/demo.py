"""Reproducible end-to-end example; prints one JSON document."""
import argparse
import json
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from stock_execution.engine import Runtime


def main():
    p=argparse.ArgumentParser(); p.add_argument('--exchange',choices=['SSE','SZSE','BSE'],default='SSE'); p.add_argument('--frequency',choices=['1m','1d'],default='1m'); p.add_argument('--db',default='demo.sqlite'); a=p.parse_args()
    folder=ROOT/'examples'/a.exchange
    load=lambda name:json.loads((folder/(name+'.json')).read_text(encoding='utf-8'))
    fixture=load('session'); request=load('plan'); r=Runtime(a.db)
    r.initialize(fixture['simulation_id'],fixture['account'],fixture['rules'],a.frequency)
    results={}
    def call(t,data):
        req=dict(request,request_id=t,idempotency_key=t,data=data); result=r.call(t,req)
        if not result['ok']: raise RuntimeError(json.dumps(result,ensure_ascii=False))
        results[t]=result
        return result['data']
    plan=call('order-plan',request['data']); order=plan['drafts'][0]
    if a.frequency=='1d': order['submitted_at']='2026-01-06T09:30:00+08:00'
    call('order-precheck',dict(order=order)); submitted=call('order-submit',dict(order=order,client_order_id='demo-order'))
    bar=load('minute' if a.frequency=='1m' else 'daily')
    call('execution-simulate',dict(bar=bar,visible_at=bar['end_at'],participation_rate='1',slippage='0'))
    call('order-query',dict(order_id=submitted['order']['order_id']))
    print(json.dumps(results,ensure_ascii=False,indent=2)); r.db.close()


if __name__=='__main__': main()
