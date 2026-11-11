"""Review oracles plus regressions for new state transitions and policy boundaries."""
import importlib.util
from pathlib import Path
import unittest
from decimal import Decimal as D
from stock_execution.engine import digest

path=Path(__file__).resolve().parents[1]/'reviews/2026-11-11-business-logic/test_business_review.py'
spec=importlib.util.spec_from_file_location('business_oracles',path)
module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
ReviewTests=module.ReviewTests
Harness=module.Harness


class RemediationTests(unittest.TestCase):
    def test_cancel_crossing_fill_confirm_and_reject_both_domains(self):
        for domain in ('stock','cta'):
            with self.subTest(domain=domain):
                h=Harness(domain,cash='100000',fee='0')
                if domain=='stock':
                    h.stock_submit(1000); oid='o-1'; tool='order-cancel'; initial=400; cross=100; quantity='filled_quantity'
                else:
                    plan=h.cta_plan(3); h.cta_submit(plan['leg_ids'][0]); oid='cta-o1'; tool='cta-order-cancel'; initial=1; cross=1; quantity='filled_lots'
                h.sim(initial)
                def cancel(action):
                    return h.ok(tool,dict(order_id=oid,expected_version=h.state()['orders'][oid]['version'],action=action))
                before=h.state()['orders'][oid]['reserved_cash']
                request=cancel('REQUEST')['order']
                self.assertTrue(request['cancel_pending']); self.assertEqual(request['reserved_cash'],before)
                import json
                from jsonschema import validate
                schema=json.loads((path.parents[2]/'skills'/tool/'assets/output.schema.json').read_text(encoding='utf-8'))
                validate(dict(ok=True,schema_version='1.0',request_id='test',data=dict(order=request,release=None,commit_status='COMMITTED'),warnings=[]),schema)
                cancel('REJECT'); self.assertFalse(h.state()['orders'][oid]['cancel_pending'])
                cancel('REQUEST'); result=h.sim(cross,index=1)
                self.assertEqual(result['commit_status'],'COMMITTED')
                o=cancel('CONFIRM')['order']
                self.assertEqual(o['status'],'CANCELED'); self.assertEqual(o[quantity],initial+cross)
                self.assertEqual(D(o['reserved_cash']),0); self.assertFalse(o['cancel_pending'])

    def test_case_A_complete_money_and_t_plus_one(self):
        h=Harness('stock',fee='0'); h.stock_submit(1000); h.sim(400,'9.90')
        def cancel(action): return h.ok('order-cancel',dict(order_id='o-1',expected_version=h.state()['orders']['o-1']['version'],action=action))
        cancel('REQUEST'); a=h.sim(100,index=1)['account']
        self.assertEqual((D(a['cash_balance']),D(a['frozen_cash'])),(15040,5000))
        cancel('CONFIRM'); a=h.ok('order-query',dict(order_id='o-1'))['account']
        self.assertEqual((a['positions']['SYNTH_A']['quantity'],D(a['frozen_cash'])),(500,0))
        result=h.call('order-submit',dict(order=h.stock_order(100,'SELL'),client_order_id='same-day-sell'))
        self.assertEqual(result['error']['code'],'INSUFFICIENT_SELLABLE')

    def test_conflict_latch_preserves_finances_and_requires_cas_resolution(self):
        for domain in ('stock','cta'):
            with self.subTest(domain=domain):
                h=Harness(domain,cash='100000')
                if domain=='stock': h.stock_submit(100); q=100; record='execution-fill-record'; oid='o-1'
                else:
                    p=h.cta_plan(1); h.cta_submit(p['leg_ids'][0]); q=1; record='cta-fill-record'; oid='cta-o1'
                fill=h.sim(q)['fills'][0]; before=h.state()
                result=h.call(record,dict(order_id=oid,expected_version=1,fill_id=fill['fill_id'],event_id='wrong'))
                self.assertEqual(result['error']['code'],'FILL_CONFLICT'); after=h.state()
                self.assertEqual(before['account'],after['account']); self.assertEqual(before['fills'],after['fills'])
                self.assertEqual(after['reconciliation']['status'],'RECONCILE')
                with self.assertRaises(ValueError if domain=='cta' else Exception):
                    h.runtime.resolve_reconciliation('review',after['account']['version'],0,digest(after['fills']),'independent-check')
                if domain=='cta':
                    p=h.cta_plan(2,version=2)
                    blocked=h.call('cta-order-submit',dict(leg_id=p['leg_ids'][0],account_version=after['account']['version'],submitted_at=after['account']['as_of'],client_order_id='blocked'))
                    self.assertEqual(blocked['error']['code'],'RECONCILE_REQUIRED')
                h.runtime.resolve_reconciliation('review',after['account']['version'],1,digest(after['fills']),'fixture-ledger-verified')
                self.assertEqual(h.state()['reconciliation']['status'],'CONSISTENT')
                self.assertEqual(len(h.state()['reconciliation']['conflicts']),1)

    def test_sell_fee_shortfall_exact_cash_booked(self):
        h=Harness('stock',cash='4',quantity=1,stock_price='1')
        order=h.stock_order(1,'SELL'); order['limit_price']='1'
        o=h.ok('order-submit',dict(order=order,client_order_id='odd'))['order']
        self.assertEqual(D(o['reserved_cash']),4)
        a=h.sim(1,'1')['account']; self.assertEqual(D(a['cash_balance']),0); self.assertEqual(D(a['frozen_cash']),0)

    def test_order_price_policy_never_overdraws_on_higher_short_fill(self):
        h=Harness('cta',cash='100000'); p=h.cta_plan(-2); o=h.cta_submit(p['leg_ids'][0])['order']
        self.assertEqual(D(o['reserved_cash']),8010)
        result=h.sim(1,'4400'); self.assertEqual(result['fills'],[])
        self.assertGreaterEqual(D(result['account']['available_cash']),0)
        result=h.sim(2,'4000',index=1); self.assertEqual(len(result['fills']),1)

    def test_fully_filled_cancel_request_is_cleared(self):
        for domain in ('stock','cta'):
            with self.subTest(domain=domain):
                h=Harness(domain,cash='100000')
                if domain=='stock': h.stock_submit(100); oid='o-1'; q=100; tool='order-cancel'
                else:
                    p=h.cta_plan(1); h.cta_submit(p['leg_ids'][0]); oid='cta-o1'; q=1; tool='cta-order-cancel'
                h.ok(tool,dict(order_id=oid,expected_version=h.state()['orders'][oid]['version'],action='REQUEST'))
                h.sim(q); self.assertFalse(h.state()['orders'][oid]['cancel_pending'])

    def test_arbitrary_fill_recovery_survives_reconnect(self):
        import tempfile
        from stock_execution.engine import Runtime as StockRuntime
        from cta_execution.engine import Runtime as CTARuntime
        for domain,cls,record in [('stock',StockRuntime,'execution-fill-record'),('cta',CTARuntime,'cta-fill-record')]:
            with self.subTest(domain=domain), tempfile.TemporaryDirectory() as directory:
                h=Harness(domain,cash='100000')
                if domain=='stock': h.stock_submit(100); q=100; oid='o-1'; version=2
                else:
                    p=h.cta_plan(1); h.cta_submit(p['leg_ids'][0]); q=1; oid='cta-o1'; version=1
                b=h.bar(q); h.runtime.publish_market_event('review',b,b['end_at'],'1','0')
                h.ok(record,dict(order_id=oid,expected_version=version,fill_id='broker-independent-id',event_id=b['event_id']))
                database=str(Path(directory)/'recovery.sqlite'); reopened=cls(database)
                h.runtime.db.backup(reopened.db); h.runtime.db.close(); reopened.db.close()
                h.runtime=cls(database); first=h.sim(q); state=h.state(); second=h.sim(q)
                self.assertEqual(first,second); self.assertEqual(state['account'],h.state()['account'])
                self.assertEqual(h.state()['fills']['broker-independent-id']['accounting_status'],'BOOKED'); h.runtime.db.close()
