import copy
import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from stock_execution.engine import Runtime, TOOLS
from stock_execution.providers import map_daily_record, FixtureMarketDataProvider


class ExecutionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.path=Path(self.tmp.name)/'test.sqlite'
        self.r=Runtime(self.path); self.n=0
        self.fixture=json.loads((ROOT/'examples/SSE/session.json').read_text(encoding='utf-8'))
        self.plan=json.loads((ROOT/'examples/SSE/plan.json').read_text(encoding='utf-8'))
        self.bar=json.loads((ROOT/'examples/SSE/minute.json').read_text(encoding='utf-8'))
        self.r.initialize(**dict(simulation_id=self.fixture['simulation_id'],account=self.fixture['account'],rules=self.fixture['rules']))

    def tearDown(self):
        self.r.db.close(); self.tmp.cleanup()

    def call(self,t,data,key=None,runtime=None):
        self.n+=1
        req=dict(schema_version='1.0',request_id=str(self.n),simulation_id=self.fixture['simulation_id'],account_id=self.fixture['account']['account_id'],data=data,idempotency_key=key or str(self.n))
        return (runtime or self.r).call(t,req)

    def ok(self,t,data,key=None,runtime=None):
        result=self.call(t,data,key,runtime)
        self.assertTrue(result['ok'],result)
        return result['data']

    def draft(self):
        return self.ok('order-plan',self.plan['data'])['drafts'][0]

    def submit(self,order=None,key=None,client='c1'):
        return self.ok('order-submit',dict(order=order or self.draft(),client_order_id=client),key)['order']

    def simulate(self,bar=None,**kw):
        b=bar or self.bar
        return self.ok('execution-simulate',dict(bar=b,visible_at=b['end_at'],participation_rate='0.1',slippage='0',**kw))

    def query(self,oid='o-1'):
        return self.ok('order-query',dict(order_id=oid))

    def test_weight_open_gap_partial_cancel_and_fee(self):
        order=self.draft(); self.assertEqual(order['quantity'],600)
        first=dict(order,quantity=200); self.submit(first,client='old')
        # At the next consistent account snapshot the compatible 200 leaves are deducted.
        data=copy.deepcopy(self.plan['data']); data['account_snapshot_id']='2'
        plan=self.ok('order-plan',data); self.assertEqual(plan['drafts'][0]['quantity'],400)
        new=self.submit(plan['drafts'][0],client='new')
        # Submit order is deterministic: old consumes 200, new consumes 100 of capacity 300.
        result=self.simulate(); self.assertEqual(sum(f['quantity'] for f in result['fills']),300)
        self.assertEqual(result['account']['positions']['SSE:SIM0001']['quantity'],700)
        self.assertEqual(self.ok('order-open-quantity',dict(instrument_id='SSE:SIM0001'))['buy_quantity'],300)
        q=self.query(new['order_id']); canceled=self.ok('order-cancel',dict(order_id=new['order_id'],expected_version=q['order']['version']))
        self.assertEqual(canceled['order']['filled_quantity'],100)
        self.assertEqual(canceled['order']['canceled_quantity'],300)
        self.assertEqual(self.query(new['order_id'])['account']['frozen_cash'],'0.00')

    def test_idempotency(self):
        order=self.draft(); a=dict(order=order,client_order_id='c1')
        one=self.ok('order-submit',a,'same'); two=self.ok('order-submit',a,'same'); self.assertEqual(one,two)
        a['order']['quantity']=700
        self.assertEqual(self.call('order-submit',a,'same')['error']['code'],'IDEMPOTENCY_CONFLICT')
        self.simulate(); before=self.query(); self.simulate(); after=self.query()
        self.assertEqual(before['account']['cash_balance'],after['account']['cash_balance'])
        self.assertEqual(len(after['fills']),1)

    def test_recovery_all_phases_after_restart(self):
        for phase in ('record','order','account'):
            with self.subTest(phase=phase):
                # separate persistent session per injected failure
                db=Path(self.tmp.name)/(phase+'.sqlite'); rt=Runtime(db)
                rt.initialize(self.fixture['simulation_id'],self.fixture['account'],self.fixture['rules'])
                order=self.draft()
                self.ok('order-submit',dict(order=order,client_order_id='c'),runtime=rt)
                a=dict(bar=self.bar,visible_at=self.bar['end_at'],participation_rate='0.1',slippage='0',fail_after=phase)
                pending=self.ok('execution-simulate',a,runtime=rt)
                self.assertNotEqual(pending['commit_status'],'COMMITTED')
                code=self.call('order-plan',self.plan['data'],runtime=rt)['error']['code']
                self.assertIn(code,('ACCOUNTING_PENDING','RECOVERY_REQUIRED'))
                rt.db.close(); rt=Runtime(db); del a['fail_after']
                completed=self.ok('execution-simulate',a,runtime=rt)
                self.assertEqual(completed['account']['cash_balance'],'92995.00')
                self.assertEqual(completed['account']['positions']['SSE:SIM0001']['quantity'],700)
                rt.db.close()

    def test_partial_fee_minimum_once(self):
        self.submit(); self.simulate()
        b=dict(self.bar,event_id='bar2',start_at=self.bar['end_at'],end_at='2026-01-05T09:33:00+08:00')
        self.simulate(b)
        q=self.query(); self.assertEqual(q['order']['charged_fee'],'5.00')
        self.assertEqual(q['account']['cash_balance'],'89995.00')
        self.assertEqual(q['account']['positions']['SSE:SIM0001']['sellable_quantity'],400)
        self.assertEqual(q['order']['status'],'FILLED')

    def test_schema_and_business_rejections(self):
        original=self.plan['data']
        cases=[]
        for field,value,code in [('total_assets','99999','SNAPSHOT_MISMATCH'),('account_snapshot_id','9','SNAPSHOT_MISMATCH')]:
            a=copy.deepcopy(original); a[field]=value; cases.append((a,code))
        a=copy.deepcopy(original); a['targets']=[]; cases.append((a,'UNCOVERED_POSITION'))
        a=copy.deepcopy(original); a['targets']*=2; cases.append((a,'DUPLICATE_INSTRUMENT'))
        for field,value,code in [('target_weight','1.1','INVALID_WEIGHT'),('current_weight','0.5','CURRENT_WEIGHT_MISMATCH'),('reference_price','0','INVALID_REFERENCE_PRICE'),('price_basis','UNKNOWN','INVALID_REQUEST')]:
            a=copy.deepcopy(original); a['targets'][0][field]=value; cases.append((a,code))
        for a,code in cases: self.assertEqual(self.call('order-plan',a)['error']['code'],code)
        o=self.draft()
        for changes,code in [(dict(quantity=101),'INVALID_QUANTITY'),(dict(limit_price='10.001'),'INVALID_PRICE'),(dict(quantity=10000),'INSUFFICIENT_CASH'),(dict(side='SELL',quantity=500),'INSUFFICIENT_SELLABLE'),(dict(account_version=2),'STALE_SNAPSHOT'),(dict(submitted_at='2026-01-05T12:00:00+08:00'),'OUTSIDE_TRADING_SESSION')]:
            self.assertEqual(self.call('order-precheck',dict(order=dict(o,**changes)))['error']['code'],code)

    def test_concurrent_reservation(self):
        o=dict(self.draft(),quantity=6000)
        registered=self.ok('order-register',dict(order=o,client_order_id='first'))
        other=self.ok('order-register',dict(order=o,client_order_id='second'))
        def reserve(oid):
            rt=Runtime(self.path)
            req=dict(schema_version='1.0',request_id=oid,simulation_id=self.fixture['simulation_id'],account_id=self.fixture['account']['account_id'],idempotency_key=oid,data=dict(order_id=oid,expected_version=1,account_version=1))
            result=rt.call('order-reserve',req); rt.db.close(); return result
        with ThreadPoolExecutor(2) as pool: results=list(pool.map(reserve,[registered['order_id'],other['order_id']]))
        self.assertEqual(sum(x['ok'] for x in results),1)
        self.assertEqual([x['error']['code'] for x in results if not x['ok']],['STALE_SNAPSHOT'])

    def test_time_capacity_gap_and_expiry(self):
        self.submit()
        early=dict(self.bar,event_id='signal',start_at='2026-01-05T09:30:00+08:00',end_at='2026-01-05T09:31:00+08:00')
        self.assertEqual(self.simulate(early)['fills'],[])
        args=dict(bar=self.bar,visible_at=self.bar['start_at'],participation_rate='0.1',slippage='0')
        self.assertEqual(self.call('execution-simulate',args)['error']['code'],'BAR_NOT_COMPLETE')
        b=dict(self.bar,volume=0); self.assertEqual(self.simulate(b)['fills'],[])
        # Later event cannot force an untradable or price-protected order to fill.
        b=dict(self.bar,event_id='gap',start_at='2026-01-05T09:32:00+08:00',end_at='2026-01-05T09:33:00+08:00',open='11',high='11',low='11',close='11')
        result=self.simulate(b,end_of_day=True); self.assertEqual(result['fills'],[])
        q=self.query(); self.assertEqual(q['order']['status'],'EXPIRED'); self.assertEqual(q['account']['frozen_cash'],'0.00')

    def test_rule_profiles_and_daily_all_exchanges(self):
        for ex in ('SSE','SZSE','BSE'):
            for frequency in ('1m','1d'):
                with self.subTest(ex=ex,frequency=frequency):
                    f=json.loads((ROOT/f'examples/{ex}/session.json').read_text(encoding='utf-8'))
                    plan=json.loads((ROOT/f'examples/{ex}/plan.json').read_text(encoding='utf-8'))
                    b=json.loads((ROOT/'examples'/ex/('minute.json' if frequency=='1m' else 'daily.json')).read_text(encoding='utf-8'))
                    rt=Runtime(Path(self.tmp.name)/(ex+frequency+'.sqlite')); rt.initialize(f['simulation_id'],f['account'],f['rules'],frequency)
                    def call(t,data):
                        self.n+=1; req=dict(plan,data=data,request_id=str(self.n),idempotency_key=str(self.n)); result=rt.call(t,req); self.assertTrue(result['ok'],result); return result['data']
                    order=call('order-plan',plan['data'])['drafts'][0]
                    if frequency=='1d':
                        order['submitted_at']='2026-01-06T09:30:00+08:00'
                    call('order-submit',dict(order=order,client_order_id='c'))
                    result=call('execution-simulate',dict(bar=b,visible_at=b['end_at'],participation_rate='1',slippage='0'))
                    self.assertEqual(result['account']['positions'][ex+':SIM0001']['quantity'],1000)
                    q=call('order-query',dict(order_id='o-1')); self.assertEqual(q['account']['frozen_cash'],'0.00')
                    rt.db.close()
        # Different configured quantity semantics, not exchange-name guessing.
        o=self.draft(); self.assertEqual(self.call('order-rule-check',dict(order=dict(o,quantity=101)))['error']['code'],'INVALID_QUANTITY')

    def test_atomic_ordering_and_read_purity(self):
        o=self.ok('order-register',dict(order=self.draft(),client_order_id='c'))
        a=dict(order_id=o['order_id'],bar=self.bar,participation_rate='1',slippage='0')
        self.assertEqual(self.call('execution-match',a)['error']['code'],'INVALID_ORDER_STATE')
        self.assertEqual(self.call('account-apply-fill',dict(fill_id='invented'))['error']['code'],'FILL_NOT_FOUND')
        before=self.r.db.execute('SELECT payload FROM sessions').fetchone()[0]
        self.ok('order-state-read',dict(order_id=o['order_id']))
        after=self.r.db.execute('SELECT payload FROM sessions').fetchone()[0]
        self.assertEqual(before,after)

    def test_provider_mapping(self):
        raw=dict(market='SSE',security_code='000001',trade_date='2026-01-05',open='10',high='11',low='9',close='10',prev_close='9.8',volume=100,total_turnover='1000')
        mapped=map_daily_record(raw,price_basis='UNADJUSTED',source='fixture',volume_unit='shares',start_at='2026-01-05T09:30:00+08:00',end_at='2026-01-05T15:00:00+08:00')
        self.assertEqual(mapped['security_code'],'000001'); self.assertEqual(mapped['amount'],'1000')
        provider=FixtureMarketDataProvider([self.bar])
        self.assertEqual(provider.bars('SSE:SIM0001','1m',self.bar['start_at']),[])

    def test_exported_entrypoints_and_schemas(self):
        import jsonschema
        for tool in TOOLS:
            folder=ROOT/'skills'/tool
            schema=json.loads((folder/'assets/input.schema.json').read_text(encoding='utf-8'))
            example=json.loads((folder/'assets/example.json').read_text(encoding='utf-8'))
            jsonschema.Draft202012Validator.check_schema(schema); jsonschema.validate(example,schema)
            # Run outside repository to prove the sibling skills/root are not dependencies.
            run=subprocess.run([sys.executable,str(folder/'scripts/run.py'),'--db',str(Path(self.tmp.name)/(tool+'.sqlite')),'--input',str(folder/'assets/example.json')],cwd=self.tmp.name,capture_output=True,text=True)
            self.assertEqual(run.returncode,1,run.stderr)
            output=json.loads(run.stdout); self.assertEqual(output['error']['code'],'UNKNOWN_SIMULATION')
            jsonschema.validate(output,json.loads((folder/'assets/output.schema.json').read_text(encoding='utf-8')))
            success=json.loads((folder/'assets/success.json').read_text(encoding='utf-8'))
            jsonschema.validate(success,json.loads((folder/'assets/output.schema.json').read_text(encoding='utf-8')))

    def test_upper_atomic_equivalence(self):
        order=self.draft(); self.submit(order)
        upper=self.simulate()
        rt=Runtime(Path(self.tmp.name)/'atomic.sqlite')
        rt.initialize(self.fixture['simulation_id'],self.fixture['account'],self.fixture['rules'])
        reg=self.ok('order-register',dict(order=order,client_order_id='c1'),runtime=rt)
        reserved=self.ok('order-reserve',dict(order_id=reg['order_id'],expected_version=1,account_version=1),runtime=rt)
        rt.publish_market_event(self.fixture['simulation_id'],self.bar,self.bar['end_at'],'0.1','0')
        matched=self.ok('execution-match',dict(order_id='o-1',bar=self.bar,participation_rate='0.1',slippage='0'),runtime=rt)
        self.assertEqual(matched['quantity'],300)
        fill=self.ok('execution-fill-record',dict(order_id='o-1',fill_id='bar-1:o-1',event_id='bar-1',expected_version=reserved['version']),runtime=rt)
        updated=self.ok('order-apply-fill',dict(order_id='o-1',fill_id=fill['fill_id'],expected_version=reserved['version']),runtime=rt)
        self.ok('account-apply-fill',dict(fill_id=fill['fill_id']),runtime=rt)
        self.ok('order-release-reserve',dict(order_id='o-1',expected_version=updated['version']),runtime=rt)
        atomic=self.ok('order-query',dict(order_id='o-1'),runtime=rt)
        self.assertEqual(self.query()['order'],atomic['order'])
        self.assertEqual(upper['account'],atomic['account'])
        self.assertEqual(self.query()['fills'],atomic['fills'])
        rt.db.close()

    def test_atomic_cannot_skip_matching_priority_or_duplicate_order_event(self):
        order=self.draft(); self.submit(dict(order,quantity=200),client='first')
        second=dict(order,quantity=200,account_version=2)
        self.submit(second,client='second')
        self.r.publish_market_event(self.fixture['simulation_id'],self.bar,self.bar['end_at'],'0.1','0')
        a=dict(order_id='o-2',fill_id='f-late',event_id='bar-1',expected_version=2)
        self.assertEqual(self.call('execution-fill-record',a)['error']['code'],'MATCH_PRIORITY_CONFLICT')
        first=dict(order_id='o-1',fill_id='f-first',event_id='bar-1',expected_version=2)
        self.ok('execution-fill-record',first)
        applied=self.ok('order-apply-fill',dict(order_id='o-1',fill_id='f-first',expected_version=2))
        self.ok('account-apply-fill',dict(fill_id='f-first'))
        self.ok('order-release-reserve',dict(order_id='o-1',expected_version=applied['version']))
        self.ok('execution-fill-record',a)

    def test_duplicate_event_preserves_entire_account_and_order(self):
        self.submit(); self.simulate(); before=self.query()
        self.simulate(); after=self.query()
        self.assertEqual(before,after)
        b=dict(self.bar,volume=4000)
        args=dict(bar=b,visible_at=b['end_at'],participation_rate='0.1',slippage='0')
        self.assertEqual(self.call('execution-simulate',args)['error']['code'],'MARKET_EVENT_CONFLICT')

    def test_market_protection_halt_frequency_and_ohlc(self):
        o=self.draft(); del o['limit_price']; o.update(order_type='MARKET',protection_price='10')
        self.submit(o)
        b=dict(self.bar,open='11',high='11',low='11',close='11')
        self.assertEqual(self.simulate(b)['fills'],[])
        for field,value,code in [('frequency','1d','FREQUENCY_CONFLICT'),('high','9','INVALID_BAR')]:
            b=dict(self.bar,event_id='bad-'+field,**{field:value})
            self.assertEqual(self.call('execution-simulate',dict(bar=b,visible_at=b['end_at'],participation_rate='0.1',slippage='0'))['error']['code'],code)
        b=dict(self.bar,event_id='halt',start_at='2026-01-05T09:32:00+08:00',end_at='2026-01-05T09:33:00+08:00',tradable=False)
        self.assertEqual(self.simulate(b)['fills'],[])
        old=dict(self.bar,event_id='old')
        self.assertEqual(self.call('execution-simulate',dict(bar=old,visible_at=old['end_at'],participation_rate='0.1',slippage='0'))['error']['code'],'OUT_OF_ORDER_EVENT')

    def test_settlement_and_previous_day_expiry(self):
        self.submit(); self.simulate()
        b=dict(self.bar,event_id='nextday',trade_date='2026-01-06',start_at='2026-01-06T09:30:00+08:00',end_at='2026-01-06T09:31:00+08:00',volume=0)
        advanced=self.simulate(b)
        self.assertEqual(advanced['account']['positions']['SSE:SIM0001']['sellable_quantity'],700)
        self.assertEqual(self.query()['order']['status'],'EXPIRED')
        self.assertEqual(advanced['account']['frozen_cash'],'0.00')

    def test_open_conflicts_and_rule_differences(self):
        o=self.draft(); self.submit(dict(o,quantity=200))
        a=copy.deepcopy(self.plan['data']); a['account_snapshot_id']='2'; a['target_version']=2
        self.assertEqual(self.call('order-plan',a)['error']['code'],'OPEN_ORDER_CONFLICT')
        a['target_version']=1; a['targets'][0]['target_weight']='0'
        self.assertEqual(self.call('order-plan',a)['error']['code'],'TARGET_VERSION_CONFLICT')
        # Unknown instrument rules never borrow another board's profile.
        o['instrument_id']='SSE:UNKNOWN'
        self.assertEqual(self.call('order-rule-check',dict(order=o))['error']['code'],'UNSUPPORTED_RULE_PROFILE')
        for ex,q,valid in [('SSE',100,True),('SZSE',100,False),('BSE',101,True)]:
            f=json.loads((ROOT/'examples'/ex/'session.json').read_text(encoding='utf-8'))
            rt=Runtime(':memory:'); rt.initialize(f['simulation_id'],f['account'],f['rules'])
            template=json.loads((ROOT/'skills/order-rule-check/assets/example.json').read_text(encoding='utf-8'))['data']['order']
            o=dict(template,instrument_id=ex+':SIM0001',quantity=q)
            req=dict(schema_version='1.0',request_id='rules',simulation_id=f['simulation_id'],account_id=f['account']['account_id'],data=dict(order=o))
            self.assertEqual(rt.call('order-rule-check',req)['ok'],valid)
            rt.db.close()

    def test_actual_export_zip_is_self_contained(self):
        import shutil
        import zipfile
        subprocess.run([sys.executable,str(ROOT/'scripts/package.py')],check=True,capture_output=True)
        extracted=Path(self.tmp.name)/'extracted'
        with zipfile.ZipFile(ROOT/'dist/order-plan.zip') as z: z.extractall(extracted)
        shutil.copy(ROOT/'examples/SSE/session.json',extracted/'session.json')
        folder=extracted/'order-plan'
        result=subprocess.run([sys.executable,str(folder/'scripts/run.py'),'--db',str(extracted/'standalone.sqlite'),'--init',str(extracted/'session.json'),'--input',str(folder/'assets/example.json')],cwd=extracted,capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr+result.stdout)
        self.assertEqual(json.loads(result.stdout)['data']['drafts'][0]['quantity'],600)


if __name__=='__main__': unittest.main()
