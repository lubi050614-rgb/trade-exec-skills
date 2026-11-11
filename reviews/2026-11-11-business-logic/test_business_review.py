"""Independent business-oracle review. Regression assertions for reviewed business invariants.

Run: python -m unittest discover -s reviews/2026-11-11-business-logic -v
Uses only in-memory sessions; does not modify application code or user databases.
"""
import copy
import json
import sys
import unittest
from decimal import Decimal as D
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from stock_execution.engine import Runtime as StockRuntime
from cta_execution.engine import Runtime as CTARuntime

DAY='2026-11-11'
NEXT='2026-11-12'
THIRD='2026-11-13'
OBSERVATIONS={}


class Harness:
    def __init__(self,domain,cash='20000',quantity=0,fee='5',stock_price='10'):
        self.domain=domain; self.n=0
        self.runtime=(StockRuntime if domain=='stock' else CTARuntime)(':memory:')
        if domain=='stock':
            rule=dict(profile_id='simulation_fixture',version='review-test-v1',exchange='SSE',board='SIM_MAIN',instrument_type='STOCK',price_tick='0.01',buy_min=100,buy_step=100,sell_step=100,odd_lot_liquidation=True,lower_price='9',upper_price='11',sessions=[['09:30','11:30'],['13:00','15:00']],trade_dates=[DAY,NEXT,THIRD])
            if stock_price=='1': rule.update(lower_price='0.01',upper_price='2')
            positions={'SYNTH_A':dict(quantity=quantity,settled_quantity=quantity,valuation_price=stock_price,exchange='SSE',board='SIM_MAIN',unsettled=[])} if quantity else {}
            self.runtime.initialize('review',dict(account_id='account',currency='CNY',cash_balance=cash,as_of=DAY+'T10:00:00+08:00',version=1,positions=positions),{'SYNTH_A':rule},fee=dict(rate='0',minimum=fee,sell_tax='0',profile_id='simulation_fixture'))
        else:
            rule=dict(profile_id='simulation_fixture',version='review-test-v1',reservation_policy='ORDER_PRICE_V1',exchange='SIM_EXCHANGE',product='SYNTH',contract_id='SYNTH_F',multiplier=10,price_tick='1',min_lots=1,lot_step=1,margin_mode='RATE',margin=dict(LONG='0.10',SHORT='0.10'),fees={k:dict(mode='PER_LOT',value='5') for k in ['OPEN','CLOSE','CLOSE_TODAY','CLOSE_YESTERDAY']},close_priority=['YESTERDAY','TODAY'],separate_close=True,lower_price='3600',upper_price='4400',trade_dates=[DAY,NEXT,THIRD],previous_settlement={DAY:'4000',NEXT:'4050',THIRD:'4030'})
            calendar=[dict(contract_id='SYNTH_F',trade_date=day,start_at=day+'T'+lo+':00+08:00',end_at=day+'T'+hi+':00+08:00',phase='DAY') for day in [DAY,NEXT,THIRD] for lo,hi in [('09:00','11:30'),('13:30','15:00')]]
            positions={'SYNTH_F':[dict(lot_id='initial-long',side='LONG',bucket='YESTERDAY',quantity=quantity,basis_price='4000',opened_trade_date='2026-11-10')]} if quantity else {}
            self.runtime.initialize('review',dict(account_id='account',asset_class='FUTURES',currency='CNY',balance=cash,as_of=DAY+'T10:00:00+08:00',version=1),{'SYNTH_F':rule},calendar,positions=positions,marks={'SYNTH_F':'4000'},trade_date=DAY)

    def state(self):
        table='sessions' if self.domain=='stock' else 'cta_sessions'
        return json.loads(self.runtime.db.execute('SELECT payload FROM '+table).fetchone()[0])

    def call(self,tool,data):
        self.n+=1
        req=dict(schema_version='1.0',request_id='r'+str(self.n),idempotency_key='k'+str(self.n),account_id='account',simulation_id='review',data=data)
        if self.domain=='cta': req['asset_class']='FUTURES'
        return self.runtime.call(tool,req)

    def ok(self,tool,data):
        result=self.call(tool,data)
        if not result['ok']: raise AssertionError((tool,result))
        return result['data']

    def stock_order(self,quantity=100,side='BUY',target_version=1):
        return dict(instrument_id='SYNTH_A',side=side,quantity=quantity,order_type='LIMIT',limit_price='10',time_in_force='DAY',submitted_at=self.state()['account']['as_of'],target_id='target',target_version=target_version,account_version=self.state()['account']['version'])

    def stock_submit(self,quantity=100,side='BUY',target_version=1):
        return self.ok('order-submit',dict(order=self.stock_order(quantity,side,target_version),client_order_id='client'+str(self.n)))['order']

    def bar(self,quantity,price=None,index=0,day=DAY):
        price=price or ('10' if self.domain=='stock' else '4000')
        b=dict(event_id='event-'+day+'-'+str(index),frequency='1m',trade_date=day,start_at=f'{day}T10:{index:02d}:00+08:00',end_at=f'{day}T10:{index+1:02d}:00+08:00',open=price,high=price,low=price,close=price,volume=quantity,tradable=True,price_limit_clear=True,price_basis='UNADJUSTED',source='independent-review-fixture',synthetic=True)
        if self.domain=='stock': b.update(instrument_id='SYNTH_A',amount=str(D(price)*quantity))
        else: b.update(contract_id='SYNTH_F',multiplier=10,volume_unit='lots')
        return b

    def sim(self,quantity,price=None,index=0,day=DAY):
        b=self.bar(quantity,price,index,day)
        tool='execution-simulate' if self.domain=='stock' else 'cta-execution-simulate'
        return self.ok(tool,dict(bar=b,visible_at=b['end_at'],participation_rate='1',slippage='0'))

    def cta_plan(self,target,version=1,price='4000',as_of=None):
        return self.ok('cta-order-plan',dict(contract_id='SYNTH_F',target_net_lots=target,target_id='target',target_version=version,account_version=self.state()['account']['version'],as_of=as_of or self.state()['account']['as_of'],reference_price=price))

    def cta_submit(self,lid):
        return self.ok('cta-order-submit',dict(leg_id=lid,account_version=self.state()['account']['version'],submitted_at=self.state()['account']['as_of'],client_order_id='client'+str(self.n)))

    def settle(self,day,previous,current):
        return self.ok('cta-daily-settle',dict(trade_date=day,settlement_version=1,as_of=day+'T15:00:00+08:00',prices=[dict(contract_id='SYNTH_F',prev_settlement_price=previous,settlement_price=current)]))


class ReviewTests(unittest.TestCase):
    def keep(self,key,value): OBSERVATIONS[key]=value

    def test_case_A_cancel_request_must_not_release_before_confirmation(self):
        h=Harness('stock',fee='0'); submitted=h.stock_submit(1000)
        self.assertEqual(D(submitted['reserved_cash']),10000)
        account=h.sim(400,'9.90')['account']
        self.assertEqual((D(account['cash_balance']),D(account['frozen_cash']),account['positions']['SYNTH_A']['quantity']),(D('16040'),D('6000'),400))
        o=h.state()['orders']['o-1']
        canceled=h.ok('order-cancel',dict(order_id='o-1',expected_version=o['version'],action='REQUEST'))
        q=h.ok('order-query',dict(order_id='o-1'))
        self.keep('A3_cancel_request',dict(actual_status=canceled['order']['status'],actual_frozen=q['account']['frozen_cash'],expected_frozen='6000',note='Explicit REQUEST must retain leaves and reservation until CONFIRM.'))
        self.assertEqual((canceled['order']['status'],D(q['account']['frozen_cash'])),('PARTIALLY_FILLED',D('6000')))

    def test_case_B_exact_cash_including_fee(self):
        for cash in ('10000','10004.99','10005'):
            with self.subTest(cash=cash):
                h=Harness('stock',cash=cash)
                result=h.call('order-submit',dict(order=h.stock_order(1000),client_order_id='B'))
                if cash!='10005':
                    self.assertFalse(result['ok']); self.assertEqual(h.state()['orders'],{})
                else:
                    self.assertTrue(result['ok']); self.assertEqual(D(result['data']['order']['reserved_cash']),D('10005'))
                    account=h.sim(1000)['account']
                    self.assertEqual(D(account['cash_balance']),0); self.assertEqual(D(account['available_cash']),0)
                    self.assertEqual(account['positions']['SYNTH_A']['sellable_quantity'],0)
                self.keep('B_'+cash,result)

    def test_case_C_two_day_equity_bridge(self):
        h=Harness('cta',cash='100000'); p=h.cta_plan(2); c1=h.cta_submit(p['leg_ids'][0])['account']; c2=h.sim(2)['account']
        c3=h.settle(DAY,'4000','4050')['account']
        h.sim(0,'4020',day=NEXT); p=h.cta_plan(1,version=2,price='4020')
        c4=h.cta_submit(p['leg_ids'][0])['account']; c5=h.sim(1,'4020',index=1,day=NEXT)['account']
        c6=h.settle(NEXT,'4050','4030')['account']
        rows=[c1,c2,c3,c4,c5,c6]
        expected=[('100000','0','91990','8010','100000','0'),('99990','8000','91990','0','99990','0'),('100990','8100','92890','0','100990','0'),('100390','8040','92345','5','100990','-600'),('100385','4020','96365','0','100685','-300'),('100485','4030','96455','0','100485','0')]
        keys=('equity','position_margin','available_cash','frozen_cash','balance','floating_pnl')
        for row,oracle in zip(rows,expected): self.assertEqual(tuple(D(row[k]) for k in keys),tuple(map(D,oracle)))
        self.keep('C1_C6',rows)

    def test_case_D_reversal_reservation_matches_test_v1(self):
        h=Harness('cta',cash='100000',quantity=3); p=h.cta_plan(-2)
        d1=h.cta_submit(p['leg_ids'][0])['account']; d2=h.sim(2)['account']; d3=h.sim(1,index=1)['account']
        d4=h.cta_submit(p['leg_ids'][1])['account']; d5=h.sim(2,index=2)['account']
        self.assertEqual(D(d2['available_cash']),D('95985')); self.assertEqual(D(d3['equity']),D('99985'))
        self.assertEqual(D(d5['equity']),D('99975')); self.assertEqual(D(d5['available_cash']),D('91975'))
        self.keep('D1_D5',dict(accounts=[d1,d2,d3,d4,d5],expected_D4_frozen='8010',actual_D4_frozen=d4['frozen_cash']))
        self.assertEqual((D(d4['frozen_cash']),D(d4['available_cash'])),(D('8010'),D('91975')))

    def test_case_E_supported_fill_idempotence(self):
        h=Harness('stock'); h.stock_submit(100); result=h.sim(100); fid=result['fills'][0]['fill_id']
        before=h.state()
        h.ok('account-apply-fill',dict(fill_id=fid)); h.ok('order-apply-fill',dict(order_id='o-1',fill_id=fid,expected_version=before['orders']['o-1']['version']))
        h.ok('execution-fill-list',dict(order_id='o-1'))
        after=h.state()
        for key in ('account','orders','fills'): self.assertEqual(before[key],after[key])
        self.assertEqual(D(after['account']['cash_balance']),D('18995'))
        self.keep('E_supported_projection',dict(cash=after['account']['cash_balance'],fills=len(after['fills']),note='External cumulative order callbacks and E-prime are not implemented.'))

    def test_cta_new_target_invalidates_old_opening_leg(self):
        h=Harness('cta',cash='100000',quantity=3); old=h.cta_plan(-2)
        h.cta_submit(old['leg_ids'][0]); h.sim(3)
        new=h.cta_plan(0,version=2)
        self.assertEqual(new['leg_ids'],[])
        result=h.call('cta-order-submit',dict(leg_id=old['leg_ids'][1],account_version=h.state()['account']['version'],submitted_at=h.state()['account']['as_of'],client_order_id='stale-open'))
        self.keep('stale_cta_target',dict(new_target=0,new_plan=new,old_leg_submission=result))
        self.assertFalse(result['ok'],'Version 1 opening must not survive accepted version 2 flat target')

    def test_stock_target_quantity_stays_fixed_for_same_version(self):
        h=Harness('stock',cash='96000',quantity=400)
        def plan(snapshot):
            total=D(snapshot['total_assets']); quantity=snapshot['positions']['SYNTH_A']['quantity']
            return h.ok('order-plan',dict(account_snapshot_id=snapshot['snapshot_id'],as_of=snapshot['as_of'],total_assets=str(total),coverage='FULL',target_id='target',target_version=1,targets=[dict(instrument_id='SYNTH_A',target_weight='0.1',current_weight=str(D(quantity)*10/total),reference_price='10',price_basis='UNADJUSTED',price_as_of=snapshot['as_of'],price_source='review')]))
        initial=dict(total_assets='100000',snapshot_id='1',as_of=DAY+'T10:00:00+08:00',positions={'SYNTH_A':{'quantity':400}})
        first=plan(initial); h.ok('order-submit',dict(order=first['drafts'][0],client_order_id='target-buy')); snapshot=h.sim(600)['account']
        repeated=plan(snapshot)
        self.keep('stock_target_drift',dict(original=first['normalization'],after_fee=repeated['normalization'],new_drafts=repeated['drafts']))
        self.assertEqual(repeated['drafts'],[],'Same target version should remain at 1000 shares after its fee is booked')

    def test_stock_atomic_reservation_rechecks_open_order_conflicts(self):
        h=Harness('stock',cash='96000',quantity=400)
        buy=h.ok('order-register',dict(order=h.stock_order(100,'BUY',1),client_order_id='buy'))
        sell=h.ok('order-register',dict(order=h.stock_order(100,'SELL',2),client_order_id='sell'))
        h.ok('order-reserve',dict(order_id=buy['order_id'],expected_version=1,account_version=1))
        result=h.call('order-reserve',dict(order_id=sell['order_id'],expected_version=1,account_version=2))
        self.keep('stock_reserve_conflict',dict(result=result,orders=h.state()['orders']))
        self.assertFalse(result['ok'],'Reserve must recheck incompatible active orders, not only resource availability')

    def test_upper_recovers_arbitrary_persisted_fill_ids(self):
        for domain in ('stock','cta'):
            with self.subTest(domain=domain):
                h=Harness(domain,cash='100000',quantity=3 if domain=='cta' else 0)
                if domain=='stock':
                    h.stock_submit(1000); oid='o-1'; version=2; quantity=400; record='execution-fill-record'
                else:
                    p=h.cta_plan(-2); h.cta_submit(p['leg_ids'][0]); oid='cta-o1'; version=1; quantity=2; record='cta-fill-record'
                b=h.bar(quantity)
                h.runtime.publish_market_event('review',b,b['end_at'],'1','0')
                h.ok(record,dict(order_id=oid,expected_version=version,fill_id='adapter-trade-001',event_id=b['event_id']))
                result=h.sim(quantity)
                status=h.state()['fills']['adapter-trade-001']['accounting_status']
                self.keep(domain+'_external_fill_recovery',dict(upper_commit=result['commit_status'],fill_status=status,account=result['account']))
                self.assertFalse(result['commit_status']=='COMMITTED' and status!='BOOKED','Cannot report closed-loop success with an unbooked persisted fill')

    def test_conflicting_fill_requires_persistent_reconciliation(self):
        h=Harness('stock'); h.stock_submit(100); first=h.sim(100); fid=first['fills'][0]['fill_id']
        original=h.state()
        conflict=h.call('execution-fill-record',dict(order_id='o-1',fill_id=fid,event_id='conflicting-market-event',expected_version=2))
        self.assertEqual(conflict['error']['code'],'FILL_CONFLICT')
        after_conflict=h.state()
        new=h.call('order-submit',dict(order=h.stock_order(100),client_order_id='after-conflict'))
        self.keep('conflict_not_latched',dict(conflict=conflict,state_unchanged=original==after_conflict,new_order=new))
        self.assertFalse(new['ok'],'Conflict must persist and block new risk pending authoritative reconciliation')

    def test_stock_sell_fee_shortfall_must_fail_before_reserving(self):
        h=Harness('stock',cash='0',quantity=1,fee='5',stock_price='1')
        order=h.stock_order(1,'SELL'); order['limit_price']='1'
        result=h.call('order-submit',dict(order=order,client_order_id='odd-lot-sell'))
        b=h.bar(1,'1')
        execution=h.call('execution-simulate',dict(bar=b,visible_at=b['end_at'],participation_rate='1',slippage='0'))
        self.keep('sell_fee_shortfall',dict(submission=result,execution=execution,orders=h.state()['orders'],expected='Reject at submission: available 0 plus proceeds 1 cannot cover fee 5.'))
        self.assertFalse(result['ok'],'A sell order must reserve any fee shortfall not covered by conservative sale proceeds')


if __name__=='__main__':
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(ReviewTests)
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    out=Path(__file__).with_name('observations-after-fix.json')
    out.write_text(json.dumps(dict(tests=result.testsRun,failures=len(result.failures),errors=len(result.errors),observations=OBSERVATIONS),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    raise SystemExit(0 if result.wasSuccessful() else 1)
