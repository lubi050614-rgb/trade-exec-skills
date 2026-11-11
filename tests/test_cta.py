import copy
import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT)); sys.path.insert(0,str(ROOT/'scripts'))
from cta_execution.engine import Runtime, TOOLS
from cta_execution.providers import map_record, FixtureMarketDataProvider
from execution_common.values import D
from build_cta_assets import fixture, bar, plan_data, settle_data, request, scenario


class CTATests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.path=Path(self.tmp.name)/'cta.sqlite'
        self.r=Runtime(self.path); self.r.initialize(**fixture()); self.n=0

    def tearDown(self): self.r.db.close(); self.tmp.cleanup()

    def call(self,tool,data,key=None,r=None):
        self.n+=1
        return (r or self.r).call(tool,request(data,key or 'req'+str(self.n)))

    def ok(self,tool,data,key=None,r=None):
        result=self.call(tool,data,key,r); self.assertTrue(result['ok'],result); return result['data']

    def error(self,tool,data,code,r=None): self.assertEqual(self.call(tool,data,r=r)['error']['code'],code)

    def state(self,r=None): return json.loads((r or self.r).db.execute('SELECT payload FROM cta_sessions').fetchone()[0])

    def plan(self,target=-2,r=None,**kw):
        data=dict(plan_data(),target_net_lots=target,**kw)
        return self.ok('cta-order-plan',data,r=r)

    def submit(self,leg,at='2026-01-05T09:01:00+08:00',r=None,**kw):
        version=self.state(r)['account']['version']
        return self.ok('cta-order-submit',dict(leg_id=leg,account_version=version,submitted_at=at,client_order_id=leg,**kw),r=r)['order']

    def sim(self,b=None,r=None,**kw):
        b=b or bar()
        return self.ok('cta-execution-simulate',dict(bar=b,visible_at=b['end_at'],participation_rate='1',slippage='0',**kw),r=r)

    def test_reverse_partial_close_then_open_and_actual_net(self):
        p=self.plan(); self.assertEqual([(l['side'],l['offset'],l['lots']) for l in p['legs']],[('SELL','CLOSE_YESTERDAY',3),('SELL','OPEN',2)])
        close,opening=p['leg_ids']; self.submit(close)
        blocked=dict(leg_id=opening,account_version=2,submitted_at='2026-01-05T09:01:00+08:00',client_order_id='opening')
        self.error('cta-order-submit',blocked,'DEPENDENCY_NOT_BOOKED')
        first=self.sim(); position=first['account']['positions']['SIM:OLD']
        self.assertEqual(position['net_lots'],1); self.assertEqual(position['short_today'],0)
        blocked['account_version']=self.state()['account']['version']; blocked['submitted_at']='2026-01-05T09:02:00+08:00'
        self.error('cta-order-submit',blocked,'DEPENDENCY_NOT_BOOKED')
        b=bar(event='bar2',volume=1,start='2026-01-05T09:02:00+08:00',end='2026-01-05T09:03:00+08:00')
        self.sim(b); self.submit(opening,at=b['end_at'])
        b=bar(event='bar3',volume=1,start=b['end_at'],end='2026-01-05T09:04:00+08:00')
        result=self.sim(b)
        self.assertEqual(result['account']['positions']['SIM:OLD']['net_lots'],-1)
        self.assertEqual(result['account']['positions']['SIM:OLD']['short_today'],1)
        self.assertEqual(self.state()['orders']['cta-o2']['leaves_lots'],1)

    def test_registration_and_reservation_all_or_none(self):
        f=fixture(); f['account']['balance']='1'; rt=Runtime(':memory:'); rt.initialize(**f)
        p=self.plan(r=rt)
        before=self.state(rt)
        self.error('cta-order-register',dict(leg_id=p['leg_ids'][0],account_version=1,submitted_at=plan_data()['as_of'],client_order_id='c'),'INSUFFICIENT_MARGIN',rt)
        self.assertEqual(before,self.state(rt)); rt.db.close()

    def test_concurrent_close_reservations_do_not_double_freeze(self):
        first=self.plan(target=0,target_id='one'); second=self.plan(target=0,target_id='two')
        def register(lid):
            rt=Runtime(self.path)
            result=rt.call('cta-order-register',request(dict(leg_id=lid,account_version=1,submitted_at=plan_data()['as_of'],client_order_id=lid),lid)); rt.db.close(); return result
        with ThreadPoolExecutor(2) as pool: results=list(pool.map(register,[first['leg_ids'][0],second['leg_ids'][0]]))
        self.assertEqual(sum(x['ok'] for x in results),1)
        s=self.state(); self.assertEqual(sum(c['quantity'] for o in s['orders'].values() for c in o['claims']),3)

    def test_today_yesterday_fees_freeze_and_cancel(self):
        f=fixture(); f['positions']['SIM:OLD'].append(dict(lot_id='today',side='LONG',bucket='TODAY',quantity=2,basis_price='100',opened_trade_date='2026-01-05'))
        rt=Runtime(':memory:'); rt.initialize(**f); p=self.plan(target=0,r=rt)
        self.assertEqual([l['offset'] for l in p['legs']],['CLOSE_YESTERDAY','CLOSE_TODAY'])
        self.submit(p['leg_ids'][0],r=rt); self.submit(p['leg_ids'][1],r=rt)
        result=self.sim(bar(volume=4),r=rt)
        self.assertEqual(sum(D(f['fee']) for f in result['fills']),D(7)) # yesterday 3*1 + today 1*4
        o=self.state(rt)['orders']['cta-o2']; self.assertEqual(o['claims'][0]['quantity'],1)
        canceled=self.ok('cta-order-cancel',dict(order_id='cta-o2',expected_version=o['version']),r=rt)
        self.assertEqual(canceled['order']['filled_lots'],1); self.assertEqual(canceled['order']['canceled_lots'],1)
        self.assertEqual(D(canceled['order']['reserved_cash']),0); self.assertEqual(canceled['order']['claims'],[])
        rt.db.close()

    def test_idempotency_and_event_conflicts(self):
        p=self.plan(); args=dict(leg_id=p['leg_ids'][0],account_version=1,submitted_at=plan_data()['as_of'],client_order_id='c')
        self.assertEqual(self.ok('cta-order-submit',args,'same'),self.ok('cta-order-submit',args,'same'))
        changed=dict(args,client_order_id='other')
        self.assertEqual(self.call('cta-order-submit',changed,'same')['error']['code'],'IDEMPOTENCY_CONFLICT')
        result=self.sim(); before=self.state(); again=self.sim()
        self.assertEqual(result,again)
        for key in ('account','orders','fills','capacity','positions'): self.assertEqual(before[key],self.state()[key])
        changedbar=bar(volume=3)
        self.error('cta-execution-simulate',dict(bar=changedbar,visible_at=changedbar['end_at'],participation_rate='1',slippage='0'),'MARKET_EVENT_CONFLICT')

    def test_recovery_four_stages_after_restart(self):
        for phase in ('record','state','book','release'):
            with self.subTest(phase=phase):
                path=Path(self.tmp.name)/(phase+'.sqlite'); rt=Runtime(path); rt.initialize(**fixture())
                p=self.plan(r=rt); self.submit(p['leg_ids'][0],r=rt)
                result=self.sim(r=rt,fail_after=phase); self.assertNotEqual(result['commit_status'],'COMMITTED')
                code=self.call('cta-order-plan',dict(plan_data(),account_version=self.state(rt)['account']['version']),r=rt)['error']['code']
                self.assertIn(code,('ACCOUNTING_PENDING','RECOVERY_REQUIRED'))
                rt.db.close(); rt=Runtime(path); recovered=self.sim(r=rt)
                self.assertEqual(recovered['account']['positions']['SIM:OLD']['net_lots'],1)
                self.assertEqual(D(recovered['account']['balance']),D('99998'))
                self.assertEqual(len(self.state(rt)['fills']),1); rt.db.close()

    def test_calendar_night_holiday_and_no_midnight_settlement(self):
        for ts in ('2026-01-09T21:01:00+08:00','2026-01-10T00:01:00+08:00'):
            result=self.ok('cta-trading-session',dict(contract_id='SIM:OLD',timestamp=ts))
            self.assertEqual(result['trade_date'],'2026-01-12'); self.assertEqual(result['phase'],'NIGHT')
        self.error('cta-trading-session',dict(contract_id='SIM:OLD',timestamp='2026-01-11T10:00:00+08:00'),'OUTSIDE_TRADING_SESSION')
        self.assertEqual(self.state()['settlements'],{})

    def test_long_short_settlement_and_conflicting_replay(self):
        for side,expected,margin in [('LONG','100300','330'),('SHORT','99700','396')]:
            with self.subTest(side=side):
                rt=Runtime(':memory:'); rt.initialize(**fixture(side))
                a=settle_data(); result=self.ok('cta-daily-settle',a,r=rt)
                self.assertEqual(D(result['closing_equity']),D(expected)); self.assertEqual(D(result['account']['position_margin']),D(margin))
                self.assertEqual(D(result['incremental_booking_adjustment']),D(300 if side=='LONG' else -300))
                before=self.state(rt); replay=self.ok('cta-daily-settle',a,r=rt); self.assertEqual(result,replay)
                self.assertEqual(before['account'],self.state(rt)['account'])
                bad=copy.deepcopy(a); bad['settlement_version']=2
                self.error('cta-daily-settle',bad,'SETTLEMENT_CONFLICT',rt)
                bad=copy.deepcopy(a); bad['prices'][0]['settlement_price']='111'
                self.error('cta-daily-settle',bad,'SETTLEMENT_CONFLICT',rt); rt.db.close()

    def test_settlement_does_not_double_count_closed_pnl_or_fees(self):
        p=self.plan(target=0); self.submit(p['leg_ids'][0])
        # Close two yesterday lots at 110 => realized +200, fees 2. One remains.
        result=self.sim(bar(price='110',volume=2)); self.assertEqual(D(result['account']['balance']),D('100198'))
        settled=self.ok('cta-daily-settle',settle_data())
        self.assertEqual(D(settled['realized_pnl']),200); self.assertEqual(D(settled['holding_pnl']),100)
        self.assertEqual(D(settled['fees']),2); self.assertEqual(D(settled['closing_equity']),D('100298'))
        self.assertEqual(self.state()['orders']['cta-o1']['status'],'EXPIRED')
        self.assertEqual(D(settled['account']['frozen_cash']),0)
        self.assertEqual(self.state()['positions']['SIM:OLD'][0]['bucket'],'YESTERDAY')

    def test_missing_settlement_price_and_too_early(self):
        a=settle_data(); a['prices']=[]
        self.error('cta-daily-settle',a,'MISSING_SETTLEMENT_PRICE')
        a=settle_data(); a['as_of']='2026-01-05T14:59:00+08:00'
        self.error('cta-daily-settle',a,'SETTLEMENT_TOO_EARLY')
        a=settle_data(); a['prices'][0]['prev_settlement_price']='99'
        self.error('cta-daily-settle',a,'PREVIOUS_SETTLEMENT_MISMATCH')

    def test_roll_partial_new_fill_reports_unconnected_exposure(self):
        args=dict(roll_id='r1',old_contract_id='SIM:OLD',new_contract_id='SIM:NEW',lots=2,old_reference_price='100',new_reference_price='100',account_version=1,as_of=plan_data()['as_of'])
        roll=self.ok('cta-roll-plan',args); s=self.state()
        old=s['plans'][roll['old_plan_id']]['leg_ids'][0]; new=s['plans'][roll['new_plan_id']]['leg_ids'][0]
        self.submit(old); self.sim()
        self.submit(new,at='2026-01-05T09:02:00+08:00')
        self.sim(bar(cid='SIM:NEW',event='new1',volume=1,start='2026-01-05T09:02:00+08:00',end='2026-01-05T09:03:00+08:00'))
        p=self.ok('cta-roll-progress',dict(roll_id='r1'))
        self.assertEqual((p['closed_old_lots'],p['opened_new_lots'],p['unconnected_lots']),(2,1,1)); self.assertFalse(p['complete'])

    def test_hedged_positions_and_stock_payload_rejected(self):
        f=fixture(); f['positions']['SIM:OLD'].append(dict(lot_id='hedge',side='SHORT',bucket='YESTERDAY',quantity=3,basis_price='100',opened_trade_date='2026-01-02'))
        rt=Runtime(':memory:'); rt.initialize(**f); self.error('cta-order-plan',plan_data(),'UNSUPPORTED_HEDGED_POSITION',rt); rt.db.close()
        req=request(plan_data()); req['asset_class']='STOCK'; self.assertEqual(self.r.call('cta-order-plan',req)['error']['code'],'INVALID_REQUEST')
        a=plan_data(); a['target_weight']='0.5'; self.error('cta-order-plan',a,'INVALID_REQUEST')
        a=plan_data(); a['target_net_lots']='-2'; self.error('cta-order-plan',a,'INVALID_REQUEST')

    def test_market_short_protection_and_margin_conversion(self):
        p=self.plan(target=5); opening=p['leg_ids'][0]
        o=self.submit(opening,order_type='MARKET',protection_price='100')
        self.assertGreater(D(o['reserved_cash']),0)
        result=self.sim(bar(price='110')); self.assertEqual(result['fills'],[])
        result=self.sim(bar(event='next',volume=1,start='2026-01-05T09:02:00+08:00',end='2026-01-05T09:03:00+08:00',price='100'))
        self.assertEqual(len(result['fills']),1); self.assertEqual(D(result['account']['balance']),D('99998'))
        self.assertEqual(result['account']['positions']['SIM:OLD']['long_today'],1)

    def test_risk_shortfall_blocks_new_open(self):
        f=fixture(); f['account']['balance']='350'; rt=Runtime(':memory:'); rt.initialize(**f)
        p=self.plan(target=4,r=rt)
        # A price fall creates unrealized loss while retaining margin requirements.
        self.sim(bar(volume=0,price='80'),r=rt)
        a=dict(leg_id=p['leg_ids'][0],account_version=self.state(rt)['account']['version'],submitted_at='2026-01-05T09:02:00+08:00',client_order_id='c')
        self.error('cta-order-submit',a,'MARGIN_SHORTFALL',rt); rt.db.close()

    def test_atomic_path_matches_upper_and_wrong_order_rejected(self):
        p=self.plan(); self.submit(p['leg_ids'][0]); b=bar(price='110'); upper=self.sim(b)
        rt=Runtime(':memory:'); rt.initialize(**fixture()); p=self.plan(r=rt)
        self.ok('cta-order-register',dict(leg_id=p['leg_ids'][0],account_version=1,submitted_at=plan_data()['as_of'],client_order_id=p['leg_ids'][0]),r=rt)
        self.error('cta-fill-book',dict(fill_id='invented'),'FILL_NOT_FOUND',rt)
        rt.publish_market_event('cta-demo',b,b['end_at'],'1','0')
        f=self.ok('cta-fill-record',dict(order_id='cta-o1',expected_version=1,fill_id='cta-bar1:cta-o1',event_id=b['event_id']),r=rt)
        self.error('cta-fill-book',dict(fill_id=f['fill_id']),'ORDER_FILL_NOT_APPLIED',rt)
        o=self.ok('cta-order-state-update',dict(order_id='cta-o1',expected_version=1,event_type='FILL',fill_id=f['fill_id']),r=rt)
        self.ok('cta-fill-book',dict(fill_id=f['fill_id']),r=rt); self.ok('cta-order-release',dict(order_id='cta-o1',expected_version=o['version']),r=rt)
        a=self.state(rt); u=self.state()
        for k in ('positions','orders','fills','capacity'): self.assertEqual(a[k],u[k])
        self.assertEqual(D(a['account']['balance']),D(upper['account']['balance'])); rt.db.close()

    def test_shared_capacity_and_causal_bars(self):
        f=fixture(); f['positions']['SIM:OLD'][0]['bucket']='TODAY'
        f['positions']['SIM:OLD'].append(dict(lot_id='yday',side='LONG',bucket='YESTERDAY',quantity=2,basis_price='100',opened_trade_date='2026-01-02'))
        rt=Runtime(':memory:'); rt.initialize(**f); p=self.plan(target=0,r=rt)
        for lid in p['leg_ids']: self.submit(lid,r=rt)
        early=bar(event='signal',start='2026-01-05T09:00:00+08:00',end=plan_data()['as_of'])
        self.assertEqual(self.sim(early,r=rt)['fills'],[])
        result=self.sim(bar(volume=3),r=rt); self.assertEqual(sum(f['lots'] for f in result['fills']),3)
        rt.db.close()

    def test_daily_and_minute_and_market_data_boundaries(self):
        rt=Runtime(':memory:'); rt.initialize(**fixture(frequency='1d')); p=self.plan(target=0,r=rt)
        self.submit(p['leg_ids'][0],r=rt)
        signal=bar(event='daily',frequency='1d',start='2026-01-05T09:00:00+08:00',end='2026-01-05T15:00:00+08:00')
        self.assertEqual(self.sim(signal,r=rt)['fills'],[]) # submitted after daily start
        rt.db.close()
        data=bar(); provider=FixtureMarketDataProvider([data]); self.assertEqual(provider.bars('SIM:OLD','1m',data['start_at']),[])
        mapped=map_record(dict(data,prev_close='90')); self.assertNotIn('prev_settlement_price',mapped)
        with self.assertRaises(ValueError): map_record(dict(contract_id='SSE:600000',prev_close='90'))
        # A target known at the daily interval start is eligible for that next interval.
        f=fixture(frequency='1d'); f['account']['as_of']='2026-01-05T09:00:00+08:00'
        rt=Runtime(':memory:'); rt.initialize(**f)
        p=self.plan(target=0,r=rt,as_of=f['account']['as_of'])
        self.submit(p['leg_ids'][0],at=f['account']['as_of'],r=rt)
        self.assertEqual(sum(x['lots'] for x in self.sim(signal,r=rt)['fills']),2)
        rt.db.close()

    def test_fixed_margin_and_notional_fees(self):
        f=fixture(); r=f['contracts']['SIM:OLD']; r['margin_mode']='FIXED'; r['margin']={'LONG':'25','SHORT':'30'}
        r['fees']['OPEN']=dict(mode='NOTIONAL',value='0.001')
        rt=Runtime(':memory:'); rt.initialize(**f)
        margin=self.ok('cta-margin-calculate',dict(contract_id='SIM:OLD',trade_date='2026-01-05',price='100',lots=2,position_side='SHORT'),r=rt)
        fee=self.ok('cta-fee-calculate',dict(contract_id='SIM:OLD',trade_date='2026-01-05',price='100',lots=2,offset='OPEN'),r=rt)
        self.assertEqual(D(margin['margin']),60); self.assertEqual(D(fee['fee']),2); rt.db.close()

    def test_actual_night_execution_uses_explicit_future_trade_date(self):
        f=fixture(); f['trade_date']='2026-01-12'; f['account']['as_of']='2026-01-09T21:01:00+08:00'
        f['positions']['SIM:OLD'][0]['basis_price']='105'; f['marks']['SIM:OLD']='105'
        rt=Runtime(':memory:'); rt.initialize(**f)
        p=self.plan(target=0,r=rt,as_of=f['account']['as_of'],reference_price='105')
        self.submit(p['leg_ids'][0],at=f['account']['as_of'],r=rt)
        b=bar(price='105',start=f['account']['as_of'],end='2026-01-09T21:02:00+08:00'); b['trade_date']='2026-01-12'
        result=self.sim(b,r=rt)
        self.assertEqual(result['fills'][0]['trade_date'],'2026-01-12')
        self.assertEqual(result['account']['trade_date'],'2026-01-12')
        self.assertEqual(self.state(rt)['settlements'],{}); rt.db.close()

    def test_stale_preplanned_target_cannot_overtrade(self):
        first=self.plan(target=4,target_id='one'); second=self.plan(target=4,target_id='two')
        args=dict(leg_id=first['leg_ids'][0],account_version=self.state()['account']['version'],submitted_at=plan_data()['as_of'],client_order_id='stale')
        self.error('cta-order-submit',args,'STALE_TARGET_VERSION')
        self.submit(second['leg_ids'][0]); self.sim(bar(volume=1))

    def test_roll_cannot_reuse_unlinked_opening_plan(self):
        self.plan(target=2,target_id='roll-unsafe',contract_id='SIM:NEW')
        args=dict(roll_id='roll-unsafe',old_contract_id='SIM:OLD',new_contract_id='SIM:NEW',lots=2,old_reference_price='100',new_reference_price='100',account_version=1,as_of=plan_data()['as_of'])
        self.error('cta-roll-plan',args,'PLAN_DEPENDENCY_CONFLICT')
        self.assertNotIn('roll-unsafe',self.state()['rolls'])

    def test_second_day_uses_actual_previous_settlement_once(self):
        first=settle_data(); first['prices'][0]['settlement_price']='109'
        self.ok('cta-daily-settle',first)
        second=dict(trade_date='2026-01-06',settlement_version=1,as_of='2026-01-06T15:00:00+08:00',prices=[dict(contract_id='SIM:OLD',prev_settlement_price='109',settlement_price='105')])
        settled=self.ok('cta-daily-settle',second)
        self.assertEqual(D(settled['opening_equity']),D(100270))
        self.assertEqual(D(settled['holding_pnl']),D(-120))
        self.assertEqual(D(settled['closing_equity']),D(100150))
        self.assertEqual(settled['next_trade_date'],'2026-01-12')
        self.assertEqual(self.ok('cta-daily-settle',second),settled)

    def test_all_contracts_success_and_standalone_entries(self):
        import jsonschema
        for tool in TOOLS:
            with self.subTest(tool=tool):
                folder=ROOT/'skills'/tool
                _,req,success=scenario(tool)
                input_schema=json.loads((folder/'assets/input.schema.json').read_text(encoding='utf-8'))
                output_schema=json.loads((folder/'assets/output.schema.json').read_text(encoding='utf-8'))
                jsonschema.Draft202012Validator.check_schema(input_schema); jsonschema.validate(req,input_schema); jsonschema.validate(success,output_schema)
                result=subprocess.run([sys.executable,str(ROOT/'scripts/replay_cta_example.py'),'--tool',tool],cwd=self.tmp.name,capture_output=True,text=True)
                self.assertEqual(result.returncode,0,result.stdout+result.stderr)
                jsonschema.validate(json.loads(result.stdout),output_schema)

    def test_exported_cta_skill_without_repository_imports(self):
        subprocess.run([sys.executable,str(ROOT/'scripts/package.py')],capture_output=True,check=True)
        extracted=Path(self.tmp.name)/'export'
        with zipfile.ZipFile(ROOT/'dist/cta-order-plan.zip') as z: z.extractall(extracted)
        folder=extracted/'cta-order-plan'
        result=subprocess.run([sys.executable,str(folder/'scripts/run.py'),'--db',str(extracted/'test.sqlite'),'--init',str(ROOT/'examples/cta/long/session.json'),'--input',str(folder/'assets/example.json')],cwd=extracted,capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertEqual(json.loads(result.stdout)['data']['target_net_lots'],-2)


if __name__=='__main__': unittest.main()
