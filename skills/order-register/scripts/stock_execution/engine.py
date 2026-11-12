"""Shared Upper/Atomic domain implementation backed by a transactional mock store."""
import copy
import hashlib
import json
import sqlite3
from pathlib import Path
from datetime import datetime
from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP

D = Decimal
ACTIVE = {'NEW', 'PARTIALLY_FILLED'}
WRITES = {'order-plan', 'order-register', 'order-reserve', 'order-cancel-remainder',
          'order-release-reserve', 'execution-fill-record', 'order-apply-fill',
          'account-apply-fill', 'order-submit', 'order-cancel', 'execution-simulate'}
TOOLS = ['order-plan', 'order-precheck', 'order-submit', 'order-cancel',
         'execution-simulate', 'order-query', 'order-open-quantity', 'order-target-gap',
         'order-rule-check', 'execution-fee-calculate', 'order-resource-check',
         'order-register', 'order-reserve', 'order-state-read', 'order-cancel-remainder',
         'order-release-reserve', 'execution-match', 'execution-fill-record',
         'order-apply-fill', 'account-apply-fill', 'execution-fill-list']


class ToolError(Exception):
    def __init__(self, code, message='', **details):
        super().__init__(message or code)
        self.code, self.details = code, details


def require(condition, code, **details):
    if not condition:
        raise ToolError(code, **details)


def dec(value):
    require(isinstance(value, (str, int)) and not isinstance(value, bool), 'INVALID_DECIMAL')
    v = D(value)
    require(v.is_finite(), 'INVALID_DECIMAL')
    return v


def stamp(value):
    v = datetime.fromisoformat(value)
    require(v.tzinfo is not None, 'TIMEZONE_REQUIRED')
    require(v.utcoffset().total_seconds() == 28800, 'SHANGHAI_TIME_REQUIRED')
    return v


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def money(value):
    return str(value.quantize(D('.01'), rounding=ROUND_HALF_UP))


class AccountServiceAdapter:
    """Production boundary: consistent reads, CAS reservation, release, idempotent posting.

    Implementations must provide authoritative snapshots and durable processing receipts.
    This package only ships MockAccountServiceAdapter; no production endpoint is assumed.
    """
    def snapshot(self):
        raise NotImplementedError

    def reserve(self, order, cash, quantity, expected_version):
        raise NotImplementedError

    def release(self, order, remaining_cash, remaining_quantity):
        raise NotImplementedError

    def apply_fill(self, order, fill, rules):
        raise NotImplementedError

    def advance_trade_date(self, trade_date):
        raise NotImplementedError


class MockAccountServiceAdapter(AccountServiceAdapter):
    def __init__(self, state):
        self.state = state

    def snapshot(self):
        a = copy.deepcopy(self.state['account'])
        a['frozen_cash'] = money(sum((dec(o['reserved_cash']) for o in self.state['orders'].values()), D(0)))
        a['available_cash'] = money(dec(a['cash_balance']) - dec(a['frozen_cash']))
        for k, p in a['positions'].items():
            frozen = sum(o['reserved_quantity'] for o in self.state['orders'].values() if o['instrument_id'] == k)
            p['frozen_sell_quantity'] = frozen
            p['sellable_quantity'] = p['settled_quantity'] - frozen
        a['total_assets'] = money(dec(a['cash_balance']) + sum((dec(p['valuation_price']) * p['quantity'] for p in a['positions'].values()), D(0)))
        a['snapshot_id'] = str(a['version'])
        a['reconciliation_status']=self.state.get('reconciliation',{}).get('status','CONSISTENT')
        return a

    def reserve(self, order, cash, quantity, expected_version):
        account=self.state['account']; snap=self.snapshot()
        require(account['version']==expected_version, 'STALE_SNAPSHOT')
        require(dec(snap['available_cash'])>=dec(cash), 'INSUFFICIENT_CASH')
        require(snap['positions'].get(order['instrument_id'],{}).get('sellable_quantity',0)>=quantity, 'INSUFFICIENT_SELLABLE')
        order.update(reserved_cash=cash,reserved_quantity=quantity)
        account['version']+=1

    def release(self, order, remaining_cash, remaining_quantity):
        released=dec(order['reserved_cash'])-remaining_cash
        require(released>=0 and order['reserved_quantity']>=remaining_quantity,'RESERVATION_MISMATCH')
        changed=released!=0 or order['reserved_quantity']!=remaining_quantity
        order.update(reserved_cash=money(remaining_cash),reserved_quantity=remaining_quantity)
        if changed: self.state['account']['version']+=1
        return released

    def apply_fill(self, order, fill, rules):
        if fill['accounting_status']=='BOOKED': return self.snapshot()
        account=self.state['account']; k=order['instrument_id']
        p=account['positions'].setdefault(k,dict(quantity=0,settled_quantity=0,valuation_price=fill['price'],exchange=rules['exchange'],board=rules['board'],unsettled=[]))
        p.setdefault('unsettled',[]); amount=dec(fill['notional']); fees=dec(fill['fees']); q=fill['quantity']
        if order['side']=='BUY':
            require(dec(order['reserved_cash'])>=amount+fees,'INSUFFICIENT_RESERVATION')
            account['cash_balance']=money(dec(account['cash_balance'])-amount-fees)
            order['reserved_cash']=money(dec(order['reserved_cash'])-amount-fees); p['quantity']+=q
            p['unsettled'].append(dict(quantity=q,trade_date=fill['executed_at'][:10]))
        else:
            require(order['reserved_quantity']>=q and p['settled_quantity']>=q,'INSUFFICIENT_SELLABLE')
            p['quantity']-=q; p['settled_quantity']-=q; order['reserved_quantity']-=q
            shortfall=max(D(0),fees-amount)
            require(dec(order['reserved_cash'])>=shortfall,'INSUFFICIENT_RESERVATION')
            order['reserved_cash']=money(dec(order['reserved_cash'])-shortfall)
            account['cash_balance']=money(dec(account['cash_balance'])+amount-fees)
        require(dec(account['cash_balance'])>=0,'INSUFFICIENT_CASH')
        account['version']+=1; account['as_of']=fill['executed_at']; fill['accounting_status']='BOOKED'
        return self.snapshot()

    def advance_trade_date(self, trade_date):
        if trade_date<=self.state['trade_date']: return
        for p in self.state['account']['positions'].values():
            eligible=[x for x in p.get('unsettled',[]) if x['trade_date']<trade_date]
            p['settled_quantity']+=sum(x['quantity'] for x in eligible)
            p['unsettled']=[x for x in p.get('unsettled',[]) if x not in eligible]
        self.state['trade_date']=trade_date
        self.state['account']['version']+=1


def load_state(runtime, simulation_id):
    row=runtime.db.execute('SELECT payload FROM sessions WHERE id=?',(simulation_id,)).fetchone()
    require(row is not None,'UNKNOWN_SIMULATION')
    runtime.s=json.loads(row[0]); runtime.adapter=MockAccountServiceAdapter(runtime.s)


class Runtime:
    def __init__(self, database='simulation.sqlite'):
        self.db = sqlite3.connect(str(database), timeout=30, isolation_level=None)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, payload TEXT NOT NULL)')

    def initialize(self, simulation_id, account, rules, frequency='1m', fee=None):
        require(frequency in ('1m', '1d'), 'INVALID_FREQUENCY')
        a = copy.deepcopy(account)
        a.setdefault('version', 1)
        require(a['currency'] == 'CNY', 'INVALID_CURRENCY')
        stamp(a['as_of'])
        require(dec(a['cash_balance']) >= 0, 'INVALID_ACCOUNT')
        for p in a['positions'].values():
            require(0 <= p['settled_quantity'] <= p['quantity'], 'INVALID_ACCOUNT')
            require(p.get('exchange') in ('SSE','SZSE','BSE') and dec(p['valuation_price'])>0, 'INVALID_ACCOUNT')
        configured_fee=fee or dict(rate='0.0003',minimum='5',sell_tax='0.0005',profile_id='simulation_fixture')
        require(all(dec(configured_fee[k])>=0 for k in ('rate','minimum','sell_tax')), 'INVALID_FEE_PROFILE')
        state = dict(account=a, rules=rules, frequency=frequency,
                     fee=configured_fee,
                     orders={}, fills={}, events={}, capacity={}, idempotency={}, trace=[], last_bar={}, trade_date=a['as_of'][:10])
        self.db.execute('INSERT INTO sessions VALUES (?,?)', (simulation_id, json.dumps(state)))

    def publish_market_event(self, simulation_id, bar, visible_at, participation_rate, slippage):
        """Trusted fixture provider ingestion, not an additional agent tool.

        Allows the Atomic path to record persisted market events without invoking Upper.
        Ingestion performs no matching, reservation, fill recording or account posting.
        """
        self.db.execute('BEGIN IMMEDIATE')
        try:
            load_state(self,simulation_id)
            result=self.admit_event(bar,visible_at,dict(participation_rate=participation_rate,slippage=slippage),False)
            self.db.execute('UPDATE sessions SET payload=? WHERE id=?',(json.dumps(self.s),simulation_id))
            self.db.execute('COMMIT')
            return copy.deepcopy(result)
        except Exception:
            self.db.execute('ROLLBACK'); raise

    def admit_event(self,b,visible_at,model,end_of_day):
        self.validate_bar(b)
        require(stamp(visible_at)>=stamp(b['end_at']),'BAR_NOT_COMPLETE')
        rate=dec(model['participation_rate']); slip=dec(model['slippage'])
        require(0<=rate<=1 and slip>=0,'INVALID_MODEL')
        h=digest(dict(bar=b,model=model,end_of_day=end_of_day)); eid=b['event_id']
        event=self.s['events'].get(eid)
        if event:
            require(event['hash']==h,'MARKET_EVENT_CONFLICT')
            return event
        self.consistent()
        last=self.s['last_bar'].get(b['instrument_id'])
        require(last is None or stamp(b['start_at'])>=stamp(last),'OUT_OF_ORDER_EVENT')
        event=dict(bar=b,model=model,hash=h,done=False)
        self.s['events'][eid]=event; self.s['last_bar'][b['instrument_id']]=b['end_at']
        return event

    def call(self, tool, request):
        rid = request.get('request_id', '') if isinstance(request,dict) else ''
        try:
            require(tool in TOOLS, 'UNKNOWN_TOOL')
            from .validation import validate
            contracts = json.loads(Path(__file__).with_name('contracts.json').read_text(encoding='utf-8'))
            validate(request, contracts[tool])
            require(request.get('schema_version') == '1.0' and rid, 'INVALID_REQUEST')
            self.db.execute('BEGIN IMMEDIATE')
            row = self.db.execute('SELECT payload FROM sessions WHERE id=?', (request['simulation_id'],)).fetchone()
            require(row is not None, 'UNKNOWN_SIMULATION')
            self.s = json.loads(row[0])
            self.request_id=rid
            self.adapter = MockAccountServiceAdapter(self.s)
            require(request['account_id'] == self.s['account']['account_id'], 'ACCOUNT_MISMATCH')
            args = request.get('data', {})
            if tool in WRITES:
                key = request.get('idempotency_key')
                require(isinstance(key, str) and key, 'IDEMPOTENCY_KEY_REQUIRED')
                scope = tool + ':' + key
                h = digest(args)
                old = self.s['idempotency'].get(scope)
                if old:
                    require(old['hash'] == h, 'IDEMPOTENCY_CONFLICT')
                    self.db.execute('COMMIT')
                    return dict(ok=True, schema_version='1.0', request_id=rid, data=old['result'], warnings=[])
            result = self.invoke(tool, args)
            if tool in WRITES:
                self.s['idempotency'][scope] = dict(hash=h, result=copy.deepcopy(result))
            self.db.execute('UPDATE sessions SET payload=? WHERE id=?', (json.dumps(self.s), request['simulation_id']))
            self.db.execute('COMMIT')
            return dict(ok=True, schema_version='1.0', request_id=rid, data=result, warnings=[])
        except (ToolError, KeyError, ValueError, TypeError, ArithmeticError) as e:
            if self.db.in_transaction:
                self.db.execute('ROLLBACK')
            if getattr(e,'code',None)=='FILL_CONFLICT':
                self.db.execute('BEGIN IMMEDIATE')
                row=self.db.execute('SELECT payload FROM sessions WHERE id=?',(request['simulation_id'],)).fetchone()
                state=json.loads(row[0])
                evidence=dict(tool=tool,request_id=rid,data=copy.deepcopy(request['data']),code='FILL_CONFLICT')
                state.setdefault('reconciliation',dict(status='RECONCILE',conflicts=[]))['conflicts'].append(evidence)
                state['reconciliation']['status']='RECONCILE'
                self.db.execute('UPDATE sessions SET payload=? WHERE id=?',(json.dumps(state),request['simulation_id']))
                self.db.execute('COMMIT')
            return dict(ok=False, schema_version='1.0', request_id=rid,
                        error=dict(code=getattr(e, 'code', 'INVALID_REQUEST'), message=str(e), retryable=False, details=getattr(e, 'details', {})))

    def resolve_reconciliation(self,simulation_id,expected_version,expected_conflict_count,canonical_fills_hash,receipt):
        """Trusted mock operator boundary, never an agent tool or live-broker reset.

        Caller must independently reconcile the canonical fills and retain a receipt.
        CAS checks prevent clearing a newer account or newly received conflict.
        """
        self.db.execute('BEGIN IMMEDIATE')
        try:
            row=self.db.execute('SELECT payload FROM sessions WHERE id=?',(simulation_id,)).fetchone()
            require(row is not None,'UNKNOWN_SIMULATION'); state=json.loads(row[0])
            rec=state.get('reconciliation',{})
            require(rec.get('status')=='RECONCILE','RECONCILIATION_NOT_PENDING')
            require(state['account']['version']==expected_version and len(rec['conflicts'])==expected_conflict_count,'STALE_RECONCILIATION')
            require(digest(state['fills'])==canonical_fills_hash,'RECONCILIATION_MISMATCH')
            require(all(f['accounting_status']=='BOOKED' for f in state['fills'].values()),'ACCOUNTING_PENDING')
            require(not any(e.get('recovery_required') for e in state['events'].values()),'RECOVERY_REQUIRED')
            require(isinstance(receipt,str) and receipt.strip(),'RECONCILIATION_RECEIPT_REQUIRED')
            rec.setdefault('resolutions',[]).append(dict(receipt=receipt,canonical_fills_hash=canonical_fills_hash,conflict_count=expected_conflict_count,account_version=expected_version))
            rec['status']='CONSISTENT'
            self.db.execute('UPDATE sessions SET payload=? WHERE id=?',(json.dumps(state),simulation_id))
            self.db.execute('COMMIT')
        except Exception:
            self.db.execute('ROLLBACK'); raise

    def invoke(self, tool, a):
        result = getattr(self, tool.replace('-', '_'))(a)
        if tool in WRITES:
            self.s['trace'].append(dict(tool=tool, request_id=getattr(self,'request_id',None), event_id=a.get('fill_id', a.get('event_id')), order_id=a.get('order_id')))
        return result

    def order(self, a):
        require(a['order_id'] in self.s['orders'], 'ORDER_NOT_FOUND')
        return self.s['orders'][a['order_id']]

    def consistent(self):
        require(not any(f['accounting_status'] != 'BOOKED' for f in self.s['fills'].values()), 'ACCOUNTING_PENDING')
        require(not any(e.get('recovery_required') for e in self.s['events'].values()), 'RECOVERY_REQUIRED')

    def version(self, o, a):
        require(a.get('expected_version') == o['version'], 'STALE_ORDER_VERSION')

    def rule(self, instrument):
        r = self.s['rules'].get(instrument)
        require(r is not None and r.get('profile_id') == 'simulation_fixture', 'UNSUPPORTED_RULE_PROFILE')
        return r

    def order_open_quantity(self, a):
        orders = [o for o in self.s['orders'].values() if o['instrument_id'] == a['instrument_id'] and o['status'] in ACTIVE]
        return dict(buy_quantity=sum(o['leaves_quantity'] for o in orders if o['side'] == 'BUY'),
                    sell_quantity=sum(o['leaves_quantity'] for o in orders if o['side'] == 'SELL'), orders=copy.deepcopy(orders))

    def order_target_gap(self, a):
        for k in ('target_quantity', 'actual_quantity', 'buy_quantity', 'sell_quantity'):
            require(type(a[k]) is int and a[k] >= 0, 'INVALID_QUANTITY')
        gap = a['target_quantity'] - a['actual_quantity'] - a['buy_quantity'] + a['sell_quantity']
        return dict(gap=gap, side='BUY' if gap > 0 else 'SELL' if gap < 0 else None, quantity=abs(gap))

    def order_plan(self, a):
        self.consistent()
        snap = self.adapter.snapshot()
        require(a['account_snapshot_id'] == snap['snapshot_id'] and a['as_of'] == snap['as_of'] and dec(a['total_assets']) == dec(snap['total_assets']), 'SNAPSHOT_MISMATCH')
        require(a.get('coverage') == 'FULL', 'INCOMPLETE_PORTFOLIO')
        items = a['targets']; ids = [x['instrument_id'] for x in items]
        require(len(ids) == len(set(ids)), 'DUPLICATE_INSTRUMENT')
        require(set(snap['positions']).issubset(ids), 'UNCOVERED_POSITION')
        require(all(o['instrument_id'] in ids for o in self.s['orders'].values() if o['status'] in ACTIVE), 'OPEN_ORDER_CONFLICT')
        weights = [dec(x['target_weight']) for x in items]
        require(all(0 <= w <= 1 for w in weights) and sum(weights) <= 1, 'INVALID_WEIGHT')
        current=[dec(x['current_weight']) for x in items]
        require(all(0<=w<=1 for w in current) and sum(current)<=1,'INVALID_WEIGHT')
        require(dec(a.get('weight_tolerance','0.000001'))>=0,'INVALID_TOLERANCE')
        key=json.dumps([a['target_id'],a['target_version']])
        definition=digest(sorted((x['instrument_id'],str(dec(x['target_weight']))) for x in items))
        targets=self.s.setdefault('normalized_targets',{})
        saved=targets.get(key)
        require(saved is None or saved['definition']==definition,'TARGET_VERSION_CONFLICT')
        if saved is None:
            saved=dict(definition=definition,snapshot_id=snap['snapshot_id'],quantities={},raw_quantities={})
            targets[key]=saved
        drafts, audit = [], []
        for x, w in zip(items, weights):
            k = x['instrument_id']; r = self.rule(k); price = dec(x['reference_price'])
            require(price > 0, 'INVALID_REFERENCE_PRICE')
            require(x['price_basis'] == 'UNADJUSTED', 'UNKNOWN_PRICE_BASIS')
            require(stamp(x['price_as_of']) <= stamp(a['as_of']) and x.get('price_source'), 'FUTURE_REFERENCE_PRICE')
            p = snap['positions'].get(k, dict(quantity=0, valuation_price=str(price)))
            actual_weight = D(p['quantity']) * dec(p['valuation_price']) / dec(snap['total_assets'])
            require(abs(actual_weight - dec(x['current_weight'])) <= dec(a.get('weight_tolerance', '0.000001')), 'CURRENT_WEIGHT_MISMATCH')
            raw = dec(snap['total_assets']) * w / price
            target = int(raw / r['buy_step']) * r['buy_step']
            if target and target < r['buy_min']:
                target = 0
            target=saved['quantities'].setdefault(k,target)
            raw=dec(saved.setdefault('raw_quantities',{}).setdefault(k,str(raw)))
            q = self.invoke('order-open-quantity', dict(instrument_id=k))
            desired = target - p['quantity']
            for o in q['orders']:
                require(o['target_id'] == a['target_id'] and o['target_version'] == a['target_version'] and ((o['side'] == 'BUY' and desired > 0) or (o['side'] == 'SELL' and desired < 0)), 'OPEN_ORDER_CONFLICT', cancel_order_id=o['order_id'])
            require(q['buy_quantity'] + q['sell_quantity'] <= abs(desired), 'OPEN_ORDER_CONFLICT')
            gap = self.invoke('order-target-gap', dict(target_quantity=target, actual_quantity=p['quantity'], buy_quantity=q['buy_quantity'], sell_quantity=q['sell_quantity']))
            if gap['quantity']:
                drafts.append(dict(instrument_id=k, side=gap['side'], quantity=gap['quantity'], order_type='LIMIT', limit_price=str(price), time_in_force='DAY', submitted_at=a['as_of'], target_id=a['target_id'], target_version=a['target_version'], account_version=snap['version']))
            audit.append(dict(instrument_id=k, raw_target_quantity=str(raw), target_quantity=target, rounding_weight_deviation=str(D(target)*price/dec(snap['total_assets'])-w)))
        buy_cost = sum((dec(o['limit_price'])*o['quantity'] + dec(self.execution_fee_calculate(dict(side=o['side'], notional=str(dec(o['limit_price'])*o['quantity']), cumulative_notional='0', charged_fee='0'))['fee']) for o in drafts if o['side']=='BUY'), D(0))
        buffer=dec(a.get('cash_buffer','0'))
        require(buffer>=0,'INVALID_CASH_BUFFER')
        sell_proceeds=sum((dec(o['limit_price'])*o['quantity']-dec(self.execution_fee_calculate(dict(side='SELL',notional=str(dec(o['limit_price'])*o['quantity'])))['fee']) for o in drafts if o['side']=='SELL'),D(0))
        post_cash=dec(snap['available_cash'])+sell_proceeds-buy_cost
        return dict(drafts=drafts, normalization=audit, estimated_buy_cost=money(buy_cost), estimated_sell_proceeds=money(sell_proceeds), estimated_post_trade_cash=money(post_cash), cash_buffer=money(buffer), funding_sufficient=post_cash>=buffer, available_cash=snap['available_cash'], requires_sell_proceeds=buy_cost+buffer > dec(snap['available_cash']), target_cash_weight=str(1-sum(weights)), commit_status='COMMITTED')

    def order_rule_check(self, a):
        o = a.get('order', a); r = self.rule(o['instrument_id']); t = stamp(o['submitted_at'])
        require(o['side'] in ('BUY', 'SELL') and o['order_type'] in ('MARKET', 'LIMIT') and o.get('time_in_force') == 'DAY', 'UNSUPPORTED_ORDER_TYPE')
        require(t.date().isoformat() in r['trade_dates'] and any(lo <= t.strftime('%H:%M') < hi for lo, hi in r['sessions']), 'OUTSIDE_TRADING_SESSION')
        q = o['quantity']; require(type(q) is int and q > 0, 'INVALID_QUANTITY')
        if o['side'] == 'BUY':
            require(q >= r['buy_min'] and q % r['buy_step'] == 0, 'INVALID_QUANTITY')
        else:
            snap = self.adapter.snapshot(); p = snap['positions'].get(o['instrument_id'], {})
            require(q % r['sell_step'] == 0 or (r['odd_lot_liquidation'] and q == p.get('sellable_quantity')), 'INVALID_QUANTITY')
        price = dec(o['limit_price'] if o['order_type'] == 'LIMIT' else o['protection_price'])
        require(price > 0 and price % dec(r['price_tick']) == 0, 'INVALID_PRICE')
        require(dec(r['lower_price']) <= price <= dec(r['upper_price']), 'PRICE_LIMIT')
        return dict(valid=True, profile_version=r['version'])

    def execution_fee_calculate(self, a):
        f = self.s['fee']; total = dec(a.get('cumulative_notional', '0')) + dec(a['notional'])
        require(total >= 0 and a['side'] in ('BUY', 'SELL'), 'INVALID_FEE_INPUT')
        cost = max(dec(f['minimum']), total * dec(f['rate'])) if total else D(0)
        if a['side'] == 'SELL': cost += total * dec(f['sell_tax'])
        return dict(fee=money(max(D(0), cost.quantize(D('.01'), rounding=ROUND_HALF_UP)-dec(a.get('charged_fee', '0')))), profile_id=f['profile_id'])

    def sell_cash_needed(self,o,quantity):
        if not quantity: return D(0)
        r=self.rule(o['instrument_id'])
        price=dec(o['limit_price'] if o['order_type']=='LIMIT' else o['protection_price'])
        fee=self.execution_fee_calculate(dict(side='SELL',notional=str(dec(r['upper_price'])*quantity),cumulative_notional=o.get('notional','0'),charged_fee=o.get('charged_fee','0')))['fee']
        # Cover commission even when only the smallest executable slice fills.
        return max(D(0),dec(fee)-price*min(quantity,r['sell_step']))

    def order_resource_check(self, a):
        o = a.get('order', a); snap = self.adapter.snapshot()
        price = dec(o.get('limit_price') if o['order_type'] == 'LIMIT' else o['protection_price'])
        fee = self.execution_fee_calculate(dict(side=o['side'], notional=str(price*o['quantity'])))['fee']
        cash = price*o['quantity']+dec(fee) if o['side']=='BUY' else self.sell_cash_needed(o,o['quantity'])
        q = o['quantity'] if o['side']=='SELL' else 0
        available_cash=dec(snap['available_cash'])
        available_quantity=snap['positions'].get(o['instrument_id'], {}).get('sellable_quantity', 0)
        require(available_cash >= cash, 'INSUFFICIENT_CASH', required_cash=money(cash),
                available_cash=money(available_cash), shortfall_cash=money(max(D(0),cash-available_cash)), fee=fee)
        require(available_quantity >= q, 'INSUFFICIENT_SELLABLE', required_quantity=q,
                available_quantity=available_quantity, shortfall_quantity=max(0,q-available_quantity), fee=fee)
        return dict(required_cash=money(cash), required_quantity=q, fee=fee, account_version=snap['version'])

    def order_precheck(self, a):
        self.consistent(); o = a.get('order', a)
        require(self.s.get('reconciliation',{}).get('status')!='RECONCILE','RECONCILE_REQUIRED')
        require(o['account_version'] == self.s['account']['version'], 'STALE_SNAPSHOT')
        latest=self.s['last_bar'].get(o['instrument_id'],self.s['account']['as_of'])
        require(stamp(o['submitted_at'])>=max(stamp(latest),stamp(self.s['account']['as_of'])), 'STALE_ORDER_TIME')
        for existing in self.s['orders'].values():
            if existing['status'] in ACTIVE and existing['instrument_id']==o['instrument_id']:
                require(existing['target_id']==o['target_id'] and existing['target_version']==o['target_version'] and existing['side']==o['side'], 'OPEN_ORDER_CONFLICT')
        self.invoke('order-rule-check', dict(order=o))
        return self.invoke('order-resource-check', dict(order=o))

    def order_register(self, a):
        self.consistent(); o = copy.deepcopy(a['order'])
        self.order_precheck(dict(order=o))
        require(not any(x['client_order_id'] == a['client_order_id'] for x in self.s['orders'].values()), 'CLIENT_ORDER_CONFLICT')
        oid = 'o-' + str(len(self.s['orders'])+1)
        o.update(order_id=oid, client_order_id=a['client_order_id'], status='PENDING_RESERVATION', version=1, filled_quantity=0, leaves_quantity=o['quantity'], canceled_quantity=0, reserved_cash='0', reserved_quantity=0, notional='0', charged_fee='0')
        self.s['orders'][oid] = o
        o['cancel_pending']=False
        return copy.deepcopy(o)

    def order_reserve(self, a):
        self.consistent(); o = self.order(a); self.version(o, a)
        require(o['status']=='PENDING_RESERVATION', 'INVALID_ORDER_STATE')
        require(a['account_version']==self.s['account']['version'], 'STALE_SNAPSHOT')
        latest=self.s['last_bar'].get(o['instrument_id'],self.s['account']['as_of'])
        require(stamp(o['submitted_at'])>=stamp(latest),'STALE_ORDER_TIME')
        current=dict(o,account_version=a['account_version'])
        resources=self.order_precheck(dict(order=current))
        self.adapter.reserve(o,resources['required_cash'],resources['required_quantity'],a['account_version'])
        o.update(status='NEW',version=o['version']+1)
        return copy.deepcopy(o)

    def order_submit(self, a):
        o = self.invoke('order-register', a)
        o = self.invoke('order-reserve', dict(order_id=o['order_id'], expected_version=o['version'], account_version=a['order']['account_version']))
        return dict(order=o, commit_status='COMMITTED', completed_steps=['order-register','order-reserve'])

    def order_state_read(self, a):
        return copy.deepcopy(self.order(a))

    def order_cancel_remainder(self, a):
        self.consistent(); o = self.order(a); self.version(o,a)
        require(o['status'] in ACTIVE or o['status']=='PENDING_RESERVATION', 'INVALID_ORDER_STATE')
        canceled = o['leaves_quantity']; o['canceled_quantity'] += canceled
        o.update(cancel_pending=False,leaves_quantity=0, status='CANCELED', version=o['version']+1)
        return dict(canceled_quantity=canceled, order=copy.deepcopy(o))

    def order_release_reserve(self, a):
        o = self.order(a); self.version(o,a)
        require(not any(f['order_id']==o['order_id'] and f['accounting_status']!='BOOKED' for f in self.s['fills'].values()), 'ACCOUNTING_PENDING')
        needed = D(0); qty = 0
        if o['leaves_quantity'] and o['status'] in ACTIVE:
            if o['side']=='BUY':
                price = dec(o.get('limit_price') if o['order_type']=='LIMIT' else o['protection_price'])
                remain = price*o['leaves_quantity']
                fee = self.execution_fee_calculate(dict(side='BUY', notional=str(remain), cumulative_notional=o['notional'], charged_fee=o['charged_fee']))
                needed = remain+dec(fee['fee'])
            else:
                qty = o['leaves_quantity']; needed=self.sell_cash_needed(o,qty)
        released=self.adapter.release(o,needed,qty)
        o['version']+=1
        return dict(released_cash=money(released), remaining_cash=o['reserved_cash'], remaining_quantity=qty)

    def order_cancel(self, a):
        self.invoke('order-state-read',a)
        action=a.get('action','CONFIRM'); o=self.order(a)
        if action in ('REQUEST','REJECT'):
            self.version(o,a)
            require(o['status'] in ACTIVE,'INVALID_ORDER_STATE')
            if action=='REJECT': require(o.get('cancel_pending',False),'CANCEL_NOT_PENDING')
            o['cancel_pending']=action=='REQUEST'; o['version']+=1
            return dict(order=copy.deepcopy(o),release=None,commit_status='COMMITTED')
        result = self.invoke('order-cancel-remainder', a)
        release = self.invoke('order-release-reserve', dict(order_id=a['order_id'], expected_version=result['order']['version']))
        return dict(order=self.order_state_read(a), canceled_quantity=result['canceled_quantity'], release=release, commit_status='COMMITTED')

    def validate_bar(self, b):
        require(b['price_basis']=='UNADJUSTED', 'UNKNOWN_PRICE_BASIS')
        require(b['frequency']==self.s['frequency'], 'FREQUENCY_CONFLICT')
        start, end = stamp(b['start_at']), stamp(b['end_at'])
        require(start < end and b['trade_date']==start.date().isoformat()==end.date().isoformat() and start.second==end.second==0, 'INVALID_BAR_TIME')
        r = self.rule(b['instrument_id'])
        require(b['trade_date'] in r['trade_dates'], 'INVALID_TRADE_DATE')
        if b['frequency']=='1m':
            require((end-start).total_seconds()==60 and any(lo <= start.strftime('%H:%M') < hi and end.strftime('%H:%M') <= hi for lo,hi in r['sessions']), 'INVALID_BAR_TIME')
        else:
            require(start.strftime('%H:%M')==r['sessions'][0][0] and end.strftime('%H:%M')==r['sessions'][-1][1], 'INVALID_BAR_TIME')
        op,hi,lo,cl = [dec(b[k]) for k in ('open','high','low','close')]
        require(0 < lo <= min(op,cl) <= max(op,cl) <= hi and type(b['volume']) is int and b['volume']>=0 and dec(b['amount'])>=0, 'INVALID_BAR')
        return r

    def execution_match(self, a):
        o = self.order(a); b = a['bar']; r = self.validate_bar(b)
        require(o['status'] in ACTIVE, 'INVALID_ORDER_STATE')
        require(o['instrument_id']==b['instrument_id'], 'INSTRUMENT_MISMATCH')
        if stamp(b['start_at']) < stamp(o['submitted_at']) or b['trade_date'] != o['submitted_at'][:10]:
            return dict(quantity=0, reason='NO_ELIGIBLE_NEXT_BAR')
        if not b['tradable'] or b['volume']==0 or not b.get('price_limit_clear',False):
            return dict(quantity=0, reason='UNTRADABLE_BAR')
        rate = dec(a['participation_rate']); slip = dec(a['slippage'])
        require(0 <= rate <= 1 and slip >= 0, 'INVALID_MODEL')
        price = dec(b['open'])
        if o['order_type']=='MARKET':
            price += slip if o['side']=='BUY' else -slip
        bound = dec(o['limit_price'] if o['order_type']=='LIMIT' else o['protection_price'])
        if (o['side']=='BUY' and price>bound) or (o['side']=='SELL' and price<bound):
            return dict(quantity=0, reason='PRICE_PROTECTION')
        if price <= 0 or price < dec(b['low']) or price > dec(b['high']) or price % dec(r['price_tick']) or not dec(r['lower_price']) <= price <= dec(r['upper_price']):
            return dict(quantity=0, reason='PRICE_LIMIT')
        cap = int(D(b['volume'])*rate)-self.s['capacity'].get(b['event_id'],0)
        q = min(o['leaves_quantity'], max(0,cap))
        step = r['buy_step'] if o['side']=='BUY' else r['sell_step']
        if not (o['side']=='SELL' and r['odd_lot_liquidation'] and q==o['leaves_quantity']): q = q//step*step
        if o['side']=='BUY' and q < r['buy_min']: q=0
        return dict(quantity=q, price=str(price), expected_version=o['version'], event_id=b['event_id'], model_version='open-conservative-v1')

    def execution_fill_record(self, a):
        fid=a['fill_id']
        if fid in self.s['fills']:
            require(self.s['fills'][fid]['source_hash']==digest(a), 'FILL_CONFLICT')
            return copy.deepcopy(self.s['fills'][fid])
        self.consistent()
        o=self.order(a); self.version(o,a)
        event=self.s['events'].get(a['event_id'])
        require(event is not None, 'MARKET_EVENT_NOT_FOUND')
        require(not any(f['order_id']==o['order_id'] and f['market_event_id']==a['event_id'] for f in self.s['fills'].values()), 'ORDER_EVENT_ALREADY_RECORDED')
        for prior in sorted(self.s['orders'].values(),key=lambda x:(x['submitted_at'],x['order_id'])):
            if prior['order_id']==o['order_id']: break
            recorded=any(f['order_id']==prior['order_id'] and f['market_event_id']==a['event_id'] for f in self.s['fills'].values())
            if not recorded and prior['status'] in ACTIVE and prior['instrument_id']==o['instrument_id']:
                earlier=self.execution_match(dict(order_id=prior['order_id'],bar=event['bar'],**event['model']))
                require(earlier['quantity']==0,'MATCH_PRIORITY_CONFLICT')
        candidate=self.execution_match(dict(order_id=o['order_id'], bar=event['bar'], **event['model']))
        require(candidate['quantity']>0, 'NO_MATCH')
        q=candidate['quantity']; price=dec(candidate['price'])
        fee=self.execution_fee_calculate(dict(side=o['side'], notional=str(price*q), cumulative_notional=o['notional'], charged_fee=o['charged_fee']))['fee']
        if o['side']=='BUY': require(dec(o['reserved_cash'])>=price*q+dec(fee), 'INSUFFICIENT_RESERVATION')
        else: require(o['reserved_quantity']>=q, 'INSUFFICIENT_RESERVATION')
        f=dict(fill_id=fid, order_id=o['order_id'], quantity=q, price=str(price), notional=money(price*q), fees=fee, executed_at=event['bar']['end_at'], market_event_id=a['event_id'], model_version=candidate['model_version'], accounting_status='ACCOUNTING_PENDING', order_applied=False, source_hash=digest(a))
        self.s['fills'][fid]=f
        self.s['capacity'][a['event_id']]=self.s['capacity'].get(a['event_id'],0)+q
        return copy.deepcopy(f)

    def order_apply_fill(self, a):
        o=self.order(a); f=self.s['fills'].get(a['fill_id'])
        require(f is not None and f['order_id']==o['order_id'], 'FILL_NOT_FOUND')
        if f['order_applied']: return copy.deepcopy(o)
        self.version(o,a); require(o['status'] in ACTIVE and f['quantity']<=o['leaves_quantity'], 'INVALID_ORDER_STATE')
        o['filled_quantity']+=f['quantity']; o['leaves_quantity']-=f['quantity']
        o['notional']=money(dec(o['notional'])+dec(f['notional'])); o['charged_fee']=money(dec(o['charged_fee'])+dec(f['fees']))
        o['average_price']=str(dec(o['notional'])/o['filled_quantity'])
        o['status']='FILLED' if not o['leaves_quantity'] else 'PARTIALLY_FILLED'; o['version']+=1; f['order_applied']=True
        if not o['leaves_quantity']: o['cancel_pending']=False
        return copy.deepcopy(o)

    def account_apply_fill(self, a):
        f=self.s['fills'].get(a['fill_id']); require(f is not None, 'FILL_NOT_FOUND')
        o=self.s['orders'][f['order_id']]
        if f['accounting_status']=='BOOKED': return self.adapter.snapshot()
        require(f['order_applied'], 'ORDER_FILL_NOT_APPLIED')
        return self.adapter.apply_fill(o,f,self.rule(o['instrument_id']))

    def execution_fill_list(self, a):
        self.order(a)
        offset=a.get('offset',0); limit=a.get('limit',100)
        require(type(offset) is int and offset>=0 and type(limit) is int and 1<=limit<=1000, 'INVALID_PAGINATION')
        rows=[copy.deepcopy(f) for f in self.s['fills'].values() if f['order_id']==a['order_id']]
        return dict(fills=rows[offset:offset+limit], total=len(rows), next_offset=offset+limit if offset+limit<len(rows) else None)

    def order_query(self, a):
        return dict(order=self.invoke('order-state-read',a), **self.invoke('execution-fill-list',a), account=self.adapter.snapshot(), commit_status='ACCOUNTING_PENDING' if any(f['accounting_status']!='BOOKED' for f in self.s['fills'].values()) else 'COMMITTED')

    def execution_simulate(self, a):
        # A single event is durable before the separately retryable fill pipeline.
        # Failpoint persists completed phases to exercise process-restart recovery.
        b=a['bar']; eid=b['event_id']; model=dict(participation_rate=a['participation_rate'],slippage=a['slippage'])
        event=self.admit_event(b,a['visible_at'],model,a.get('end_of_day',False))
        if event['done']: return copy.deepcopy(event['result'])
        event['recovery_required']=False
        # Expire prior DAY leaves and settle eligible lots before a later trading day.
        if b['trade_date']>self.s['trade_date']:
            self.consistent()
            for o in self.s['orders'].values():
                if o['status'] in ACTIVE and o['submitted_at'][:10]<b['trade_date']:
                    self.invoke('order-cancel-remainder',dict(order_id=o['order_id'],expected_version=o['version']))
                    o['status']='EXPIRED'
                    self.invoke('order-release-reserve',dict(order_id=o['order_id'],expected_version=o['version']))
            self.adapter.advance_trade_date(b['trade_date'])
        # Complete pending fills first, including a replay after restart.
        for o in sorted(self.s['orders'].values(),key=lambda o:(o['submitted_at'],o['order_id'])):
            f=next((f for f in self.s['fills'].values() if f['market_event_id']==eid and f['order_id']==o['order_id']),None)
            fid=f['fill_id'] if f else eid+':'+o['order_id']
            if not f and not event['done'] and o['status'] in ACTIVE and o['instrument_id']==b['instrument_id']:
                match=self.invoke('execution-match',dict(order_id=o['order_id'],bar=b,**model))
                if match['quantity']:
                    f=self.invoke('execution-fill-record',dict(order_id=o['order_id'],fill_id=fid,event_id=eid,expected_version=o['version']))
                    if a.get('fail_after')=='record': return dict(commit_status='ACCOUNTING_PENDING',failed_step='order-apply-fill',retryable=True)
            if f and self.s['fills'][fid]['accounting_status']!='BOOKED':
                self.invoke('order-apply-fill',dict(order_id=o['order_id'],fill_id=fid,expected_version=o['version']))
                if a.get('fail_after')=='order': return dict(commit_status='ACCOUNTING_PENDING',failed_step='account-apply-fill',retryable=True)
                self.invoke('account-apply-fill',dict(fill_id=fid))
                if a.get('fail_after')=='account':
                    event['recovery_required']=True
                    return dict(commit_status='RECOVERY_REQUIRED',failed_step='order-release-reserve',retryable=True)
            if f:
                self.invoke('order-release-reserve',dict(order_id=o['order_id'],expected_version=o['version']))
        if a.get('end_of_day'):
            for o in self.s['orders'].values():
                if o['status'] in ACTIVE and o['submitted_at'][:10]<=b['trade_date']:
                    self.invoke('order-cancel-remainder',dict(order_id=o['order_id'],expected_version=o['version']))
                    o['status']='EXPIRED'
                    self.invoke('order-release-reserve',dict(order_id=o['order_id'],expected_version=o['version']))
        self.consistent()
        event['done']=True
        event['result']=dict(commit_status='COMMITTED', fills=[copy.deepcopy(f) for f in self.s['fills'].values() if f['market_event_id']==eid], account=self.adapter.snapshot())
        return copy.deepcopy(event['result'])
