"""Futures domain: explicit calendars, lot buckets, durable dependencies and daily MTM."""
import copy
import json
import sqlite3
from pathlib import Path
from execution_common.values import D, dec, stamp, amount, digest, require, ToolError
from execution_common.schema import validate

UPPER=['cta-order-plan','cta-order-precheck','cta-order-submit','cta-order-cancel',
       'cta-execution-simulate','cta-order-query','cta-daily-settle','cta-roll-plan']
ATOMIC=['cta-contract-spec','cta-trading-session','cta-position-gap','cta-offset-split',
        'cta-order-rule-check','cta-margin-calculate','cta-fee-calculate','cta-order-register',
        'cta-order-release','cta-order-match','cta-fill-record','cta-order-state-update',
        'cta-fill-book','cta-order-detail','cta-settlement-apply','cta-roll-progress']
TOOLS=UPPER+ATOMIC
WRITES=set(UPPER)-{'cta-order-precheck','cta-order-query'} | {
    'cta-order-register','cta-order-release','cta-fill-record','cta-order-state-update',
    'cta-fill-book','cta-settlement-apply'}
ACTIVE={'NEW','PARTIALLY_FILLED'}


class AccountServiceAdapter:
    """Integration contract; production implementation must provide durable CAS receipts.

    snapshot: equity, margin, closeable today/yesterday lots and version;
    reserve/release: all-or-none margin/fees/lot claims;
    book: fill-ID idempotency; settle: trade-date/version idempotency.
    Only the transactional local mock implementation below is supplied.
    """
    def snapshot(self): raise NotImplementedError
    def reserve(self, order, resources): raise NotImplementedError
    def release(self, order, cash, claims): raise NotImplementedError
    def book(self, order, fill): raise NotImplementedError


class MockAccountServiceAdapter(AccountServiceAdapter):
    def __init__(self, runtime): self.r=runtime

    def snapshot(self):
        s=self.r.s; a=copy.deepcopy(s['account']); positions={}; floating=D(0); margin=D(0)
        for contract,lots in s['positions'].items():
            rule=self.r.rule(contract,s['trade_date']); price=dec(s['marks'][contract])
            p=dict(long_today=0,long_yesterday=0,short_today=0,short_yesterday=0,available_long_today=0,available_long_yesterday=0,available_short_today=0,available_short_yesterday=0)
            for lot in lots:
                key=lot['side'].lower()+'_'+lot['bucket'].lower()
                frozen=sum(c['quantity'] for o in s['orders'].values() for c in o['claims'] if c['lot_id']==lot['lot_id'])
                p[key]+=lot['quantity']; p['available_'+key]+=lot['quantity']-frozen
                direction=1 if lot['side']=='LONG' else -1
                floating+=(price-dec(lot['basis_price']))*dec(rule['multiplier'])*lot['quantity']*direction
                margin+=self.r.margin_value(rule,price,lot['quantity'],lot['side'])
            p['net_lots']=p['long_today']+p['long_yesterday']-p['short_today']-p['short_yesterday']
            p['lots']=copy.deepcopy(lots); positions[contract]=p
        reserved=sum((dec(o['reserved_cash']) for o in s['orders'].values()),D(0))
        equity=dec(a['balance'])+floating; available=equity-margin-reserved
        a.update(equity=amount(equity),floating_pnl=amount(floating),position_margin=amount(margin),frozen_cash=amount(reserved),available_cash=amount(available),margin_shortfall=amount(max(D(0),-available)),risk_status='MARGIN_SHORTFALL' if available<0 else 'NORMAL',positions=positions,trade_date=s['trade_date'],asset_class='FUTURES')
        a['reconciliation_status']=s.get('reconciliation',{}).get('status','CONSISTENT')
        return a

    def reserve(self, order, resources):
        require(dec(self.snapshot()['available_cash'])>=dec(resources['cash']),'INSUFFICIENT_MARGIN')
        order['reserved_cash']=resources['cash']; order['claims']=copy.deepcopy(resources['claims'])
        self.r.s['account']['version']+=1

    def release(self, order, cash, claims):
        released=dec(order['reserved_cash'])-cash
        require(released>=0,'RESERVATION_MISMATCH')
        changed=released!=0 or order['claims']!=claims
        order['reserved_cash']=amount(cash); order['claims']=copy.deepcopy(claims)
        if changed: self.r.s['account']['version']+=1
        return amount(released)

    def book(self, order, fill):
        if fill['accounting_status']=='BOOKED': return self.snapshot()
        s=self.r.s; rule=self.r.rule(order['contract_id'],order['trade_date'])
        lots=s['positions'].setdefault(order['contract_id'],[]); q=fill['lots']; price=dec(fill['price']); realized=D(0)
        if order['offset']=='OPEN':
            lots.append(dict(lot_id=fill['fill_id'],side='LONG' if order['side']=='BUY' else 'SHORT',bucket='TODAY',quantity=q,basis_price=amount(price),opened_trade_date=order['trade_date']))
        else:
            left=q
            for claim in order['claims']:
                used=min(left,claim['quantity']); left-=used
                if not used: continue
                lot=next(x for x in lots if x['lot_id']==claim['lot_id'])
                require(lot['quantity']>=used,'INSUFFICIENT_CLOSEABLE')
                realized+=(price-dec(lot['basis_price']))*dec(rule['multiplier'])*used*(1 if lot['side']=='LONG' else -1)
                lot['quantity']-=used; claim['quantity']-=used
            require(left==0,'INSUFFICIENT_CLOSEABLE')
            order['claims']=[c for c in order['claims'] if c['quantity']]
            s['positions'][order['contract_id']]=[x for x in lots if x['quantity']]
        order['reserved_cash']=amount(max(D(0),dec(order['reserved_cash'])-dec(fill['reserved_consumption'])))
        s['account']['balance']=amount(dec(s['account']['balance'])+realized-dec(fill['fee']))
        s['account']['version']+=1; s['account']['as_of']=fill['executed_at']
        day=s['day_totals'].setdefault(order['trade_date'],dict(realized='0',fees='0'))
        day['realized']=amount(dec(day['realized'])+realized); day['fees']=amount(dec(day['fees'])+dec(fill['fee']))
        fill.update(accounting_status='BOOKED',realized_pnl=amount(realized))
        return self.snapshot()


class Runtime:
    def __init__(self,database='cta.sqlite'):
        self.db=sqlite3.connect(str(database),timeout=30,isolation_level=None)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('CREATE TABLE IF NOT EXISTS cta_sessions (id TEXT PRIMARY KEY,payload TEXT NOT NULL)')

    def initialize(self,simulation_id,account,contracts,calendar,positions=None,marks=None,frequency='1m',trade_date=None):
        require(account.get('asset_class')=='FUTURES' and account['currency']=='CNY','ASSET_CLASS_MISMATCH')
        require(frequency in ('1m','1d'),'FREQUENCY_CONFLICT'); stamp(account['as_of'])
        require(dec(account['balance'])>=0,'INVALID_ACCOUNT')
        require(len({(x['contract_id'],x['start_at'],x['end_at']) for x in calendar})==len(calendar),'INVALID_CALENDAR')
        for x in calendar: require(stamp(x['start_at'])<stamp(x['end_at']) and x['contract_id'] in contracts,'INVALID_CALENDAR')
        for cid in contracts:
            intervals=sorted([x for x in calendar if x['contract_id']==cid],key=lambda x:stamp(x['start_at']))
            require(all(stamp(a['end_at'])<=stamp(b['start_at']) for a,b in zip(intervals,intervals[1:])),'INVALID_CALENDAR')
        a=copy.deepcopy(account); a.setdefault('version',1)
        day=trade_date or next(x['trade_date'] for x in calendar if x['contract_id'] in contracts and stamp(x['start_at'])<=stamp(a['as_of'])<stamp(x['end_at']))
        s=dict(account=a,contracts=copy.deepcopy(contracts),calendar=copy.deepcopy(calendar),positions=copy.deepcopy(positions or {}),marks=copy.deepcopy(marks or {}),frequency=frequency,trade_date=day,orders={},fills={},plans={},legs={},rolls={},events={},last_bar={},capacity={},idempotency={},settlements={},day_totals={},day_opening={day:a['balance']},trace=[])
        self.s=s; self.adapter=MockAccountServiceAdapter(self)
        require(set(contracts)<=set(s['marks']) and all(dec(v)>0 for v in s['marks'].values()),'MISSING_MARK_PRICE')
        lot_ids=[x['lot_id'] for lots in s['positions'].values() for x in lots]
        require(len(lot_ids)==len(set(lot_ids)),'DUPLICATE_POSITION_LOT')
        s['previous_settlement']={cid:self.rule(cid,day)['previous_settlement'][day] for cid in contracts}
        for cid,lots in s['positions'].items():
            self.rule(cid,day)
            require(cid in s['marks'],'MISSING_MARK_PRICE')
            for lot in lots:
                require(lot['side'] in ('LONG','SHORT') and lot['bucket'] in ('TODAY','YESTERDAY') and type(lot['quantity']) is int and lot['quantity']>0 and dec(lot['basis_price'])>0,'INVALID_POSITION')
        self.db.execute('INSERT INTO cta_sessions VALUES (?,?)',(simulation_id,json.dumps(s)))

    def load(self,sid):
        row=self.db.execute('SELECT payload FROM cta_sessions WHERE id=?',(sid,)).fetchone()
        require(row is not None,'UNKNOWN_SIMULATION'); self.s=json.loads(row[0]); self.adapter=MockAccountServiceAdapter(self)

    def call(self,tool,request):
        rid=request.get('request_id','') if isinstance(request,dict) else ''
        try:
            require(tool in TOOLS,'UNKNOWN_TOOL')
            contracts=json.loads(Path(__file__).with_name('contracts.json').read_text(encoding='utf-8'))
            validate(request,contracts[tool])
            self.db.execute('BEGIN IMMEDIATE'); self.load(request['simulation_id'])
            require(request['account_id']==self.s['account']['account_id'],'ACCOUNT_MISMATCH')
            self.request_id=rid; self.root_tool=tool; data=request['data']; scope=tool+':'+request.get('idempotency_key','')
            if tool in WRITES:
                require(bool(request.get('idempotency_key')),'IDEMPOTENCY_KEY_REQUIRED')
                previous=self.s['idempotency'].get(scope)
                if previous:
                    require(previous['hash']==digest(data),'IDEMPOTENCY_CONFLICT')
                    self.db.execute('COMMIT'); return self.envelope(rid,previous['result'])
            result=self.invoke(tool,data)
            if tool in WRITES: self.s['idempotency'][scope]=dict(hash=digest(data),result=copy.deepcopy(result))
            self.db.execute('UPDATE cta_sessions SET payload=? WHERE id=?',(json.dumps(self.s),request['simulation_id']))
            self.db.execute('COMMIT'); return self.envelope(rid,result)
        except (ValueError,KeyError,TypeError,ArithmeticError,StopIteration) as e:
            if self.db.in_transaction: self.db.execute('ROLLBACK')
            if getattr(e,'code',None)=='FILL_CONFLICT':
                self.db.execute('BEGIN IMMEDIATE')
                row=self.db.execute('SELECT payload FROM cta_sessions WHERE id=?',(request['simulation_id'],)).fetchone()
                state=json.loads(row[0])
                evidence=dict(tool=tool,request_id=rid,data=copy.deepcopy(request['data']),code='FILL_CONFLICT')
                state.setdefault('reconciliation',dict(status='RECONCILE',conflicts=[]))['conflicts'].append(evidence)
                state['reconciliation']['status']='RECONCILE'
                self.db.execute('UPDATE cta_sessions SET payload=? WHERE id=?',(json.dumps(state),request['simulation_id']))
                self.db.execute('COMMIT')
            return dict(ok=False,schema_version='1.0',request_id=rid,error=dict(code=getattr(e,'code','INVALID_REQUEST'),message=str(e),retryable=False,details=getattr(e,'details',{})))

    @staticmethod
    def envelope(rid,result): return dict(ok=True,schema_version='1.0',request_id=rid,data=result,warnings=[])

    def resolve_reconciliation(self,simulation_id,expected_version,expected_conflict_count,canonical_fills_hash,receipt):
        """Trusted mock operator boundary, never an agent tool or live-broker reset.

        Caller must independently reconcile the canonical fills and retain a receipt.
        CAS checks prevent clearing a newer account or newly received conflict.
        """
        self.db.execute('BEGIN IMMEDIATE')
        try:
            row=self.db.execute('SELECT payload FROM cta_sessions WHERE id=?',(simulation_id,)).fetchone()
            require(row is not None,'UNKNOWN_SIMULATION'); state=json.loads(row[0])
            rec=state.get('reconciliation',{})
            require(rec.get('status')=='RECONCILE','RECONCILIATION_NOT_PENDING')
            require(state['account']['version']==expected_version and len(rec['conflicts'])==expected_conflict_count,'STALE_RECONCILIATION')
            require(digest(state['fills'])==canonical_fills_hash,'RECONCILIATION_MISMATCH')
            require(all(f['accounting_status']=='BOOKED' for f in state['fills'].values()),'ACCOUNTING_PENDING')
            require(not any(e.get('recovering') for e in state['events'].values()) and not any(o.get('release_pending') for o in state['orders'].values()),'RECOVERY_REQUIRED')
            require(isinstance(receipt,str) and receipt.strip(),'RECONCILIATION_RECEIPT_REQUIRED')
            rec.setdefault('resolutions',[]).append(dict(receipt=receipt,canonical_fills_hash=canonical_fills_hash,conflict_count=expected_conflict_count,account_version=expected_version))
            rec['status']='CONSISTENT'
            self.db.execute('UPDATE cta_sessions SET payload=? WHERE id=?',(json.dumps(state),simulation_id))
            self.db.execute('COMMIT')
        except Exception:
            self.db.execute('ROLLBACK'); raise

    def invoke(self,tool,a):
        result=getattr(self,tool.replace('-','_'))(a)
        # Pure calls remain observationally pure; Upper traces only persisted actions.
        if tool in WRITES or (getattr(self,'root_tool',None) in WRITES and getattr(self,'root_tool',None) in UPPER):
            self.s['trace'].append(dict(tool=tool,request_id=getattr(self,'request_id',None),event_id=a.get('event_id',a.get('fill_id')),order_id=a.get('order_id')))
        return result

    def consistent(self):
        require(not any(f['accounting_status']!='BOOKED' for f in self.s['fills'].values()),'ACCOUNTING_PENDING')
        require(not any(e.get('recovering') for e in self.s['events'].values()),'RECOVERY_REQUIRED')
        require(not any(o.get('release_pending') for o in self.s['orders'].values()),'RELEASE_PENDING')

    def rule(self,cid,day):
        r=self.s['contracts'].get(cid)
        require(r is not None and r.get('profile_id')=='simulation_fixture' and day in r['trade_dates'],'UNSUPPORTED_RULE_PROFILE')
        require(r['multiplier']>0 and dec(r['price_tick'])>0 and r['margin_mode'] in ('RATE','FIXED'),'UNSUPPORTED_RULE_PROFILE')
        return r

    def session(self,cid,timestamp):
        t=stamp(timestamp)
        intervals=[x for x in self.s['calendar'] if x['contract_id']==cid and stamp(x['start_at'])<=t<stamp(x['end_at'])]
        require(len(intervals)==1,'OUTSIDE_TRADING_SESSION')
        return intervals[0]

    def order(self,a):
        o=self.s['orders'].get(a['order_id']); require(o is not None,'ORDER_NOT_FOUND'); return o

    def version(self,o,a): require(o['version']==a['expected_version'],'STALE_ORDER_VERSION')

    def cta_contract_spec(self,a): return copy.deepcopy(self.rule(a['contract_id'],a['trade_date']))

    def cta_trading_session(self,a):
        s=self.session(a['contract_id'],a['timestamp'])
        return dict(trade_date=s['trade_date'],phase=s['phase'],accepting=True,start_at=s['start_at'],end_at=s['end_at'])

    def gross(self,cid):
        lots=self.s['positions'].get(cid,[])
        long=sum(x['quantity'] for x in lots if x['side']=='LONG'); short=sum(x['quantity'] for x in lots if x['side']=='SHORT')
        require(not(long and short),'UNSUPPORTED_HEDGED_POSITION')
        return long,short

    def cta_position_gap(self,a):
        cid=a['contract_id']; self.rule(cid,self.s['trade_date']); long,short=self.gross(cid)
        orders=[o for o in self.s['orders'].values() if o['contract_id']==cid and o['status'] in ACTIVE]
        conflicts=[o['order_id'] for o in orders if o['target_id']!=a['target_id'] or o['target_version']!=a['target_version']]
        desired=a['target_net_lots']-(long-short)
        conflicts+= [o['order_id'] for o in orders if (1 if o['side']=='BUY' else -1)*desired<=0]
        signed=sum(o['leaves_lots']*(1 if o['side']=='BUY' else -1) for o in orders)
        require(abs(signed)<=abs(desired) or not orders,'OPEN_ORDER_CONFLICT')
        return dict(actual_long_lots=long,actual_short_lots=short,actual_net_lots=long-short,pending_open_lots=sum(o['leaves_lots'] for o in orders if o['offset']=='OPEN'),pending_close_lots=sum(o['leaves_lots'] for o in orders if o['offset']!='OPEN'),gap_lots=desired-signed,conflicting_order_ids=sorted(set(conflicts)),retained_order_ids=[o['order_id'] for o in orders if o['order_id'] not in conflicts])

    def close_claims(self,cid,side,offset,lots,exclude=None):
        required_side='LONG' if side=='SELL' else 'SHORT'; left=lots; claims=[]
        priority=self.rule(cid,self.s['trade_date'])['close_priority']
        positions=sorted(self.s['positions'].get(cid,[]),key=lambda x:(priority.index(x['bucket']),x['lot_id']))
        for lot in positions:
            if lot['side']!=required_side or (offset=='CLOSE_TODAY' and lot['bucket']!='TODAY') or (offset=='CLOSE_YESTERDAY' and lot['bucket']!='YESTERDAY'): continue
            frozen=sum(c['quantity'] for o in self.s['orders'].values() if o['order_id']!=exclude for c in o['claims'] if c['lot_id']==lot['lot_id'])
            q=min(left,lot['quantity']-frozen)
            if q>0: claims.append(dict(lot_id=lot['lot_id'],quantity=q,bucket=lot['bucket'])); left-=q
        require(left==0,'INSUFFICIENT_CLOSEABLE'); return claims

    def cta_offset_split(self,a):
        cid=a['contract_id']; r=self.rule(cid,a['trade_date']); long,short=self.gross(cid); gap=a['gap_lots']
        side='BUY' if gap>0 else 'SELL'; close=min(abs(gap),short if gap>0 else long); legs=[]
        if close:
            claims=self.close_claims(cid,side,'CLOSE',close)
            for bucket in r['close_priority']:
                q=sum(x['quantity'] for x in claims if x['bucket']==bucket)
                if q: legs.append(dict(side=side,offset=('CLOSE_'+bucket) if r['separate_close'] else 'CLOSE',lots=q,bucket=bucket,depends_on_close=True))
        opening=abs(gap)-close
        if opening: legs.append(dict(side=side,offset='OPEN',lots=opening,depends_on_close=bool(close)))
        return dict(legs=legs,strategy='CLOSE_THEN_OPEN')

    def create_plan(self,a,prefix=None,extra_dependencies=None):
        self.consistent(); require(a['account_version']==self.s['account']['version'],'STALE_SNAPSHOT')
        cid=a['contract_id']; session=self.invoke('cta-trading-session',dict(contract_id=cid,timestamp=a['as_of']))
        self.invoke('cta-contract-spec',dict(contract_id=cid,trade_date=session['trade_date']))
        require(session['trade_date']==self.s['trade_date'],'TRADE_DATE_NOT_ADVANCED')
        price=dec(a['reference_price']); require(price>0,'INVALID_PRICE')
        gap=self.invoke('cta-position-gap',a)
        require(not gap['conflicting_order_ids'],'OPEN_ORDER_CONFLICT',cancel_order_ids=gap['conflicting_order_ids'])
        pid=prefix or a['target_id']+':'+str(a['target_version'])+':'+cid
        payload={k:a[k] for k in ('contract_id','target_id','target_version','target_net_lots','reference_price')}
        payload['buffer']=amount(a.get('buffer','0'))
        current=self.s.setdefault('active_targets',{}).get(cid)
        if current and current['target_id']==a['target_id']:
            require(a['target_version']>=current['target_version'],'STALE_TARGET_VERSION')
        old=self.s['plans'].get(pid)
        if old:
            require(old['hash']==digest(payload),'TARGET_VERSION_CONFLICT')
            require(all(set(extra_dependencies or [])<=set(self.s['legs'][lid]['dependencies']) for lid in old['leg_ids'] if self.s['legs'][lid]['offset']=='OPEN'),'PLAN_DEPENDENCY_CONFLICT')
            return copy.deepcopy(old)
        split=self.invoke('cta-offset-split',dict(contract_id=cid,trade_date=session['trade_date'],gap_lots=gap['gap_lots']))
        close_ids=[]; ids=[]
        for i,leg in enumerate(split['legs']):
            lid=pid+':leg'+str(i+1)
            dependencies=(close_ids+list(extra_dependencies or [])) if leg['offset']=='OPEN' else []
            canonical=dict(leg_id=lid,plan_id=pid,contract_id=cid,side=leg['side'],offset=leg['offset'],lots=leg['lots'],limit_price=amount(price),order_type='LIMIT',time_in_force='DAY',target_id=a['target_id'],target_version=a['target_version'],trade_date=session['trade_date'],dependencies=copy.deepcopy(dependencies),buffer=amount(a.get('buffer','0')),order_id=None)
            self.s['legs'][lid]=canonical; ids.append(lid)
            if leg['offset']!='OPEN': close_ids.append(lid)
        plan=dict(plan_id=pid,contract_id=cid,target_net_lots=a['target_net_lots'],leg_ids=ids,hash=digest(payload),normalization=gap,commit_status='COMMITTED')
        self.s['plans'][pid]=plan
        self.s['active_targets'][cid]=dict(target_id=a['target_id'],target_version=a['target_version'])
        return copy.deepcopy(plan)

    def cta_order_plan(self,a):
        plan=self.create_plan(a)
        return dict(**plan,legs=[copy.deepcopy(self.s['legs'][k]) for k in plan['leg_ids']])

    @staticmethod
    def margin_value(rule,price,lots,side):
        value=dec(rule['margin'][side])
        require(value>=0,'INVALID_RULE_PROFILE')
        return value*lots if rule['margin_mode']=='FIXED' else price*dec(rule['multiplier'])*lots*value

    def cta_margin_calculate(self,a):
        r=self.rule(a['contract_id'],a['trade_date']); price=dec(a['price']); require(price>0,'INVALID_PRICE')
        return dict(notional=amount(price*r['multiplier']*a['lots']),margin=amount(self.margin_value(r,price,a['lots'],a['position_side'])),mode=r['margin_mode'],profile_version=r['version'])

    def fee_value(self,r,offset,price,lots):
        f=r['fees'][offset]; rate=dec(f['value']); require(rate>=0,'INVALID_RULE_PROFILE')
        require(f['mode'] in ('PER_LOT','NOTIONAL'),'UNSUPPORTED_FEE_PROFILE')
        return rate*lots if f['mode']=='PER_LOT' else rate*price*r['multiplier']*lots

    def cta_fee_calculate(self,a):
        r=self.rule(a['contract_id'],a['trade_date']); price=dec(a['price']); require(price>0,'INVALID_PRICE')
        return dict(fee=amount(self.fee_value(r,a['offset'],price,a['lots'])),mode=r['fees'][a['offset']]['mode'],profile_version=r['version'])

    def leg_order(self,a):
        leg=self.s['legs'].get(a['leg_id']); require(leg is not None,'PLAN_LEG_NOT_FOUND')
        order=copy.deepcopy(leg); order['submitted_at']=a['submitted_at']
        order['account_version']=a['account_version']
        if 'order_type' in a: order['order_type']=a['order_type']
        if 'protection_price' in a: order['protection_price']=a['protection_price']
        return order

    def check_order(self,a):
        self.consistent(); o=self.leg_order(a)
        require(self.s.get('reconciliation',{}).get('status')!='RECONCILE','RECONCILE_REQUIRED')
        current=self.s.get('active_targets',{}).get(o['contract_id'])
        require(current is None or (current['target_id']==o['target_id'] and current['target_version']==o['target_version']),'STALE_TARGET_VERSION')
        require(o['account_version']==self.s['account']['version'],'STALE_SNAPSHOT')
        require(o['order_id'] is None,'PLAN_LEG_ALREADY_SUBMITTED')
        session=self.session(o['contract_id'],o['submitted_at']); r=self.rule(o['contract_id'],session['trade_date'])
        require(session['trade_date']==o['trade_date']==self.s['trade_date'],'TRADE_DATE_MISMATCH')
        require(not self.s['settlements'].get(o['trade_date']),'TRADE_DATE_SETTLED')
        latest=self.s['last_bar'].get(o['contract_id'],self.s['account']['as_of'])
        require(stamp(o['submitted_at'])>=max(stamp(latest),stamp(self.s['account']['as_of'])),'STALE_ORDER_TIME')
        active=[x for x in self.s['orders'].values() if x['contract_id']==o['contract_id'] and x['status'] in ACTIVE]
        require(all(x['target_id']==o['target_id'] and x['target_version']==o['target_version'] and x['side']==o['side'] for x in active),'OPEN_ORDER_CONFLICT')
        long,short=self.gross(o['contract_id'])
        pending=sum(x['leaves_lots']*(1 if x['side']=='BUY' else -1) for x in active)
        gap=self.s['plans'][o['plan_id']]['target_net_lots']-(long-short)-pending
        signed=o['lots']*(1 if o['side']=='BUY' else -1)
        require(gap*signed>0 and abs(signed)<=abs(gap),'STALE_PLAN_QUANTITY')
        require(o['lots']>=r['min_lots'] and o['lots']%r['lot_step']==0,'INVALID_LOTS')
        for dependency in o['dependencies']:
            leg=self.s['legs'][dependency]; dep=self.s['orders'].get(leg['order_id'])
            require(dep is not None and dep['filled_lots']==leg['lots'] and all(f['accounting_status']=='BOOKED' for f in self.s['fills'].values() if f['order_id']==dep['order_id']),'DEPENDENCY_NOT_BOOKED',leg_id=dependency)
        price=dec(o['limit_price'] if o['order_type']=='LIMIT' else o['protection_price'])
        require(price>0 and price%dec(r['price_tick'])==0,'INVALID_PRICE')
        require(dec(r['lower_price'])<=price<=dec(r['upper_price']),'PRICE_LIMIT')
        require(dec(o['buffer'])>=0,'INVALID_BUFFER')
        reserve_price=self.reservation_price(o,r)
        margin=self.invoke('cta-margin-calculate',dict(contract_id=o['contract_id'],trade_date=o['trade_date'],price=amount(reserve_price),lots=o['lots'],position_side='LONG' if o['side']=='BUY' else 'SHORT'))['margin'] if o['offset']=='OPEN' else '0'
        claims=self.close_claims(o['contract_id'],o['side'],o['offset'],o['lots']) if o['offset']!='OPEN' else []
        fee=self.order_fee(o,dec(r['upper_price']),o['lots'],claims)
        cash=dec(margin)+fee+dec(o['buffer'])
        snap=self.adapter.snapshot()
        if o['offset']=='OPEN': require(snap['risk_status']=='NORMAL','MARGIN_SHORTFALL')
        require(dec(snap['available_cash'])>=cash,'INSUFFICIENT_MARGIN')
        return o,dict(cash=amount(cash),margin=margin,fee=amount(fee),claims=claims,account_version=self.s['account']['version'])

    @staticmethod
    def reservation_price(o,r):
        # A SELL limit/protection bounds price below, so use the configured upper
        # price bound for its worst-case opening margin. Fees also use that bound.
        policy=r.get('reservation_policy','UPPER_BOUND_V1')
        require(policy in ('UPPER_BOUND_V1','ORDER_PRICE_V1'),'INVALID_RESERVATION_POLICY')
        return dec(r['upper_price']) if o['side']=='SELL' and policy=='UPPER_BOUND_V1' else dec(o['limit_price'] if o['order_type']=='LIMIT' else o['protection_price'])

    def order_fee(self,o,price,lots,claims):
        r=self.rule(o['contract_id'],o['trade_date'])
        if o['offset']=='OPEN': return self.fee_value(r,'OPEN',price,lots)
        left=lots; fee=D(0)
        for c in claims:
            q=min(left,c['quantity']); fee+=self.fee_value(r,'CLOSE_'+c['bucket'],price,q); left-=q
        require(left==0,'INSUFFICIENT_CLOSEABLE'); return fee

    def cta_order_rule_check(self,a):
        o,resources=self.check_order(a)
        return dict(valid=True,resources=resources,rule_version=self.rule(o['contract_id'],o['trade_date'])['version'])

    def cta_order_precheck(self,a): return self.invoke('cta-order-rule-check',a)

    def cta_order_register(self,a):
        self.invoke('cta-order-rule-check',a)
        o,resources=self.check_order(a)
        require(not any(x['client_order_id']==a['client_order_id'] for x in self.s['orders'].values()),'CLIENT_ORDER_CONFLICT')
        oid='cta-o'+str(len(self.s['orders'])+1)
        o.update(order_id=oid,client_order_id=a['client_order_id'],sequence=len(self.s['orders'])+1,status='NEW',version=1,original_lots=o['lots'],filled_lots=0,leaves_lots=o['lots'],canceled_lots=0,reserved_cash='0',claims=[],charged_fee='0',notional='0',release_pending=False)
        self.adapter.reserve(o,resources); self.s['orders'][oid]=o; self.s['legs'][o['leg_id']]['order_id']=oid
        o['cancel_pending']=False
        return dict(order=copy.deepcopy(o),account=self.adapter.snapshot(),commit_status='COMMITTED')

    def cta_order_submit(self,a): return self.invoke('cta-order-register',a)

    def cta_order_state_update(self,a):
        o=self.order(a)
        if a['event_type']=='CANCEL':
            self.consistent(); self.version(o,a); require(o['status'] in ACTIVE,'INVALID_ORDER_STATE')
            o['canceled_lots']+=o['leaves_lots']; o.update(cancel_pending=False,leaves_lots=0,status='CANCELED',version=o['version']+1,release_pending=True)
        else:
            f=self.s['fills'].get(a.get('fill_id')); require(f is not None and f['order_id']==o['order_id'],'FILL_NOT_FOUND')
            if f['order_applied']: return copy.deepcopy(o)
            self.version(o,a); require(o['status'] in ACTIVE and f['lots']<=o['leaves_lots'],'INVALID_ORDER_STATE')
            o['filled_lots']+=f['lots']; o['leaves_lots']-=f['lots']; o['notional']=amount(dec(o['notional'])+dec(f['notional'])); o['charged_fee']=amount(dec(o['charged_fee'])+dec(f['fee']))
            o['average_price']=amount(dec(o['notional'])/self.rule(o['contract_id'],o['trade_date'])['multiplier']/o['filled_lots'])
            o['status']='FILLED' if not o['leaves_lots'] else 'PARTIALLY_FILLED'; o['version']+=1; f['order_applied']=True
            if not o['leaves_lots']: o['cancel_pending']=False
        return copy.deepcopy(o)

    def cta_order_release(self,a):
        o=self.order(a); self.version(o,a)
        require(not any(f['order_id']==o['order_id'] and f['accounting_status']!='BOOKED' for f in self.s['fills'].values()),'ACCOUNTING_PENDING')
        q=o['leaves_lots']; claims=o['claims'] if q else []; cash=D(0)
        if q and o['status'] in ACTIVE:
            r=self.rule(o['contract_id'],o['trade_date']); price=self.reservation_price(o,r)
            cash=self.order_fee(o,dec(r['upper_price']),q,claims)+dec(o['buffer'])
            if o['offset']=='OPEN': cash+=self.margin_value(r,price,q,'LONG' if o['side']=='BUY' else 'SHORT')
        released=self.adapter.release(o,cash,claims); o['release_pending']=False; o['version']+=1
        return dict(released_cash=released,remaining_cash=o['reserved_cash'],remaining_claims=copy.deepcopy(o['claims']),order_version=o['version'])

    def cta_order_cancel(self,a):
        action=a.get('action','CONFIRM'); o=self.order(a)
        if action in ('REQUEST','REJECT'):
            self.version(o,a); require(o['status'] in ACTIVE,'INVALID_ORDER_STATE')
            if action=='REJECT': require(o.get('cancel_pending',False),'CANCEL_NOT_PENDING')
            o['cancel_pending']=action=='REQUEST'; o['version']+=1
            return dict(order=copy.deepcopy(o),release=None,commit_status='COMMITTED')
        a={k:v for k,v in a.items() if k!='action'}
        result=self.invoke('cta-order-state-update',dict(**a,event_type='CANCEL'))
        released=self.invoke('cta-order-release',dict(order_id=a['order_id'],expected_version=result['version']))
        return dict(order=copy.deepcopy(self.order(a)),release=released,commit_status='COMMITTED')

    def validate_bar(self,b):
        require(b['volume_unit']=='lots' and b['price_basis']=='UNADJUSTED','MARKET_UNIT_OR_BASIS_MISMATCH')
        require(b['frequency']==self.s['frequency'],'FREQUENCY_CONFLICT')
        r=self.rule(b['contract_id'],b['trade_date']); require(b['multiplier']==r['multiplier'],'MULTIPLIER_MISMATCH')
        start,end=stamp(b['start_at']),stamp(b['end_at']); require(start<end,'INVALID_BAR_TIME')
        intervals=[s for s in self.s['calendar'] if s['contract_id']==b['contract_id'] and s['trade_date']==b['trade_date']]
        if b['frequency']=='1m': require((end-start).total_seconds()==60 and any(stamp(s['start_at'])<=start<end<=stamp(s['end_at']) for s in intervals),'INVALID_BAR_TIME')
        else: require(bool(intervals) and start==min(stamp(s['start_at']) for s in intervals) and end==max(stamp(s['end_at']) for s in intervals),'INVALID_BAR_TIME')
        op,hi,lo,cl=[dec(b[k]) for k in ('open','high','low','close')]
        require(0<lo<=min(op,cl)<=max(op,cl)<=hi and type(b['volume']) is int and b['volume']>=0,'INVALID_BAR')
        return r

    def admit_event(self,b,visible_at,model):
        self.validate_bar(b); require(stamp(visible_at)>=stamp(b['end_at']),'BAR_NOT_COMPLETE')
        require(0<=dec(model['participation_rate'])<=1 and dec(model['slippage'])>=0,'INVALID_MODEL')
        h=digest(dict(bar=b,model=model)); old=self.s['events'].get(b['event_id'])
        if old: require(old['hash']==h,'MARKET_EVENT_CONFLICT'); return old
        self.consistent(); require(b['trade_date']==self.s['trade_date'],'TRADE_DATE_NOT_ADVANCED')
        require(not self.s['settlements'].get(b['trade_date']),'TRADE_DATE_SETTLED')
        latest=self.s['last_bar'].get(b['contract_id']); require(latest is None or stamp(b['start_at'])>=stamp(latest),'OUT_OF_ORDER_EVENT')
        event=dict(hash=h,bar=copy.deepcopy(b),model=copy.deepcopy(model),done=False,recovering=False)
        self.s['events'][b['event_id']]=event; self.s['last_bar'][b['contract_id']]=b['end_at']
        # Completed bars are already observable at ingestion. Both independent
        # Atomic and Upper paths use the same authoritative valuation snapshot.
        self.s['marks'][b['contract_id']]=b['close']
        self.s['account']['as_of']=b['end_at']; self.s['account']['version']+=1
        return event

    def publish_market_event(self,simulation_id,bar,visible_at,participation_rate,slippage):
        """Trusted fixture ingestion for independent Atomic use, not an agent tool."""
        self.db.execute('BEGIN IMMEDIATE')
        try:
            self.load(simulation_id); result=self.admit_event(bar,visible_at,dict(participation_rate=participation_rate,slippage=slippage))
            self.db.execute('UPDATE cta_sessions SET payload=? WHERE id=?',(json.dumps(self.s),simulation_id)); self.db.execute('COMMIT'); return copy.deepcopy(result)
        except Exception:
            self.db.execute('ROLLBACK'); raise

    def cta_order_match(self,a):
        o=self.order(a); b=a['bar']; r=self.validate_bar(b)
        require(o['status'] in ACTIVE,'INVALID_ORDER_STATE'); require(o['contract_id']==b['contract_id'],'CONTRACT_MISMATCH')
        if b['trade_date']!=o['trade_date'] or stamp(b['start_at'])<stamp(o['submitted_at']): return dict(lots=0,reason='NO_ELIGIBLE_NEXT_BAR')
        if not b['tradable'] or not b['price_limit_clear'] or not b['volume']: return dict(lots=0,reason='UNTRADABLE_BAR')
        rate=dec(a['participation_rate']); slip=dec(a['slippage']); require(0<=rate<=1 and slip>=0,'INVALID_MODEL')
        price=dec(b['open'])+(slip*(1 if o['side']=='BUY' else -1) if o['order_type']=='MARKET' else D(0))
        bound=dec(o['limit_price'] if o['order_type']=='LIMIT' else o['protection_price'])
        if (o['side']=='BUY' and price>bound) or (o['side']=='SELL' and price<bound): return dict(lots=0,reason='PRICE_PROTECTION')
        if price<=0 or price%dec(r['price_tick']) or not dec(r['lower_price'])<=price<=dec(r['upper_price']) or not dec(b['low'])<=price<=dec(b['high']): return dict(lots=0,reason='PRICE_LIMIT')
        cap=int(D(b['volume'])*rate)-self.s['capacity'].get(b['event_id'],0)
        q=min(o['leaves_lots'],max(0,cap)); q=q//r['lot_step']*r['lot_step']
        if o['offset']=='OPEN' and o['side']=='SELL':
            # SELL protection is a minimum execution price, not an upper margin bound.
            # Recheck actual margin against the finite reservation at the execution price.
            per=self.margin_value(r,price,1,'SHORT')+self.fee_value(r,'OPEN',price,1)
            q=min(q,int(dec(o['reserved_cash'])/per)) if per else q
            q=q//r['lot_step']*r['lot_step']
            if q and r.get('reservation_policy')=='ORDER_PRICE_V1':
                remaining=o['leaves_lots']-q
                retained=self.margin_value(r,self.reservation_price(o,r),remaining,'SHORT')+self.order_fee(o,dec(r['upper_price']),remaining,[])+dec(o['buffer']) if remaining else D(0)
                if per*q+retained>dec(o['reserved_cash']): return dict(lots=0,reason='INSUFFICIENT_RESERVATION')
        return dict(lots=q,price=amount(price),expected_version=o['version'],model_version='cta-open-v1')

    def cta_fill_record(self,a):
        fid=a['fill_id']; old=self.s['fills'].get(fid)
        if old: require(old['source_hash']==digest(a),'FILL_CONFLICT'); return copy.deepcopy(old)
        self.consistent(); o=self.order(a); self.version(o,a)
        event=self.s['events'].get(a['event_id']); require(event is not None,'MARKET_EVENT_NOT_FOUND')
        require(not any(f['order_id']==o['order_id'] and f['market_event_id']==a['event_id'] for f in self.s['fills'].values()),'ORDER_EVENT_ALREADY_RECORDED')
        for prior in sorted(self.s['orders'].values(),key=lambda x:x['sequence']):
            if prior['order_id']==o['order_id']: break
            recorded=any(f['order_id']==prior['order_id'] and f['market_event_id']==a['event_id'] for f in self.s['fills'].values())
            if not recorded and prior['status'] in ACTIVE and prior['contract_id']==o['contract_id']:
                earlier=self.cta_order_match(dict(order_id=prior['order_id'],bar=event['bar'],**event['model']))
                require(not earlier['lots'],'MATCH_PRIORITY_CONFLICT')
        candidate=self.cta_order_match(dict(order_id=o['order_id'],bar=event['bar'],**event['model']))
        q=candidate['lots']; require(q>0,'NO_MATCH'); price=dec(candidate['price']); r=self.rule(o['contract_id'],o['trade_date'])
        fee=self.order_fee(o,price,q,o['claims']); consumed=fee
        if o['offset']=='OPEN': consumed+=self.margin_value(r,price,q,'LONG' if o['side']=='BUY' else 'SHORT')
        require(consumed<=dec(o['reserved_cash']),'INSUFFICIENT_RESERVATION')
        f=dict(fill_id=fid,order_id=o['order_id'],contract_id=o['contract_id'],side=o['side'],offset=o['offset'],lots=q,price=amount(price),notional=amount(price*q*r['multiplier']),fee=amount(fee),reserved_consumption=amount(consumed),executed_at=event['bar']['end_at'],trade_date=o['trade_date'],market_event_id=a['event_id'],model_version=candidate['model_version'],accounting_status='ACCOUNTING_PENDING',order_applied=False,realized_pnl='0',source_hash=digest(a))
        self.s['fills'][fid]=f; self.s['capacity'][a['event_id']]=self.s['capacity'].get(a['event_id'],0)+q
        return copy.deepcopy(f)

    def cta_fill_book(self,a):
        f=self.s['fills'].get(a['fill_id']); require(f is not None,'FILL_NOT_FOUND')
        require(f['order_applied'],'ORDER_FILL_NOT_APPLIED')
        return self.adapter.book(self.s['orders'][f['order_id']],f)

    def cta_order_detail(self,a):
        o=self.order(a); fills=[copy.deepcopy(f) for f in self.s['fills'].values() if f['order_id']==o['order_id']]
        pending=any(f['accounting_status']!='BOOKED' for f in fills)
        return dict(order=copy.deepcopy(o),fills=fills,account=self.adapter.snapshot(),commit_status='ACCOUNTING_PENDING' if pending else 'RELEASE_PENDING' if o['release_pending'] else 'COMMITTED')

    def cta_order_query(self,a): return self.invoke('cta-order-detail',a)

    def pending_result(self,phase,eid,completed):
        self.s['events'][eid]['recovering']=True
        next_step={'record':'cta-order-state-update','state':'cta-fill-book','book':'cta-order-release','release':'event-finalize'}[phase]
        return dict(commit_status='RECOVERY_REQUIRED' if phase in ('book','release') else 'ACCOUNTING_PENDING',completed_steps=completed,failed_step=next_step,retryable=True,event_id=eid,reconciliation_status='PENDING')

    def cta_execution_simulate(self,a):
        b=a['bar']; eid=b['event_id']; event=self.admit_event(b,a['visible_at'],dict(participation_rate=a['participation_rate'],slippage=a['slippage']))
        if event['done']: return copy.deepcopy(event['result'])
        event['recovering']=False; completed=[]
        for o in sorted(self.s['orders'].values(),key=lambda x:x['sequence']):
            if o['contract_id']!=b['contract_id']: continue
            f=next((f for f in self.s['fills'].values() if f['market_event_id']==eid and f['order_id']==o['order_id']),None)
            fid=f['fill_id'] if f else eid+':'+o['order_id']
            if not f and o['status'] in ACTIVE:
                candidate=self.invoke('cta-order-match',dict(order_id=o['order_id'],bar=b,**event['model']))
                if candidate['lots']:
                    f=self.invoke('cta-fill-record',dict(order_id=o['order_id'],fill_id=fid,event_id=eid,expected_version=o['version']))
                    completed.append('cta-fill-record')
                    if a.get('fail_after')=='record': return self.pending_result('record',eid,completed)
            if f:
                if self.s['fills'][fid]['accounting_status']!='BOOKED':
                    self.invoke('cta-order-state-update',dict(order_id=o['order_id'],event_type='FILL',fill_id=fid,expected_version=o['version'])); completed.append('cta-order-state-update')
                    if a.get('fail_after')=='state': return self.pending_result('state',eid,completed)
                    self.invoke('cta-fill-book',dict(fill_id=fid)); completed.append('cta-fill-book')
                    if a.get('fail_after')=='book': return self.pending_result('book',eid,completed)
                self.invoke('cta-order-release',dict(order_id=o['order_id'],expected_version=o['version'])); completed.append('cta-order-release')
                if a.get('fail_after')=='release': return self.pending_result('release',eid,completed)
        self.consistent()
        event['done']=True
        event['result']=dict(commit_status='COMMITTED',completed_steps=completed,failed_step=None,retryable=False,event_id=eid,reconciliation_status='CONSISTENT',fills=[copy.deepcopy(f) for f in self.s['fills'].values() if f['market_event_id']==eid],account=self.adapter.snapshot())
        return copy.deepcopy(event['result'])

    def cta_settlement_apply(self,a):
        day=a['trade_date']; old=self.s['settlements'].get(day)
        h=digest(a)
        if old:
            require(old['hash']==h,'SETTLEMENT_CONFLICT'); return copy.deepcopy(old['result'])
        self.consistent()
        require(day==self.s['trade_date'],'TRADE_DATE_MISMATCH')
        require(stamp(a['as_of'])>=max(stamp(x['end_at']) for x in self.s['calendar'] if x['trade_date']==day),'SETTLEMENT_TOO_EARLY')
        relevant={cid for cid,lots in self.s['positions'].items() if lots} | {o['contract_id'] for o in self.s['orders'].values() if o['trade_date']==day}
        prices={x['contract_id']:x for x in a['prices']}
        require(len(prices)==len(a['prices']) and relevant<=set(prices),'MISSING_SETTLEMENT_PRICE')
        # Validate all prices/calendar before mutating or expiring leaves.
        for cid,p in prices.items():
            r=self.rule(cid,day)
            require(dec(p['settlement_price'])>0 and dec(p['prev_settlement_price'])>0,'INVALID_SETTLEMENT_PRICE')
            require(dec(p['prev_settlement_price'])==dec(self.s['previous_settlement'][cid]),'PREVIOUS_SETTLEMENT_MISMATCH')
            require(dec(p['settlement_price'])%dec(r['price_tick'])==0 and dec(r['lower_price'])<=dec(p['settlement_price'])<=dec(r['upper_price']),'INVALID_SETTLEMENT_PRICE')
            for lot in self.s['positions'].get(cid,[]):
                if lot['bucket']=='YESTERDAY': require(dec(lot['basis_price'])==dec(p['prev_settlement_price']),'PREVIOUS_SETTLEMENT_MISMATCH')
        next_days=sorted({x['trade_date'] for x in self.s['calendar'] if x['trade_date']>day})
        require(bool(next_days),'NEXT_TRADE_DATE_UNKNOWN'); next_day=next_days[0]
        for cid in relevant: self.rule(cid,next_day)
        for o in self.s['orders'].values():
            if o['status'] in ACTIVE and o['trade_date']==day:
                self.invoke('cta-order-state-update',dict(order_id=o['order_id'],expected_version=o['version'],event_type='CANCEL')); o['status']='EXPIRED'
                self.invoke('cta-order-release',dict(order_id=o['order_id'],expected_version=o['version']))
        adjustment=D(0)
        for cid,p in prices.items():
            r=self.rule(cid,day); settlement=dec(p['settlement_price'])
            for lot in self.s['positions'].get(cid,[]):
                adjustment+=(settlement-dec(lot['basis_price']))*r['multiplier']*lot['quantity']*(1 if lot['side']=='LONG' else -1)
                lot.update(basis_price=amount(settlement),bucket='YESTERDAY')
            self.s['marks'][cid]=amount(settlement)
            self.s['previous_settlement'][cid]=amount(settlement)
        totals=self.s['day_totals'].get(day,dict(realized='0',fees='0')); opening=dec(self.s['day_opening'][day])
        closing=dec(self.s['account']['balance'])+adjustment
        require(closing==opening+dec(totals['realized'])+adjustment-dec(totals['fees']),'EQUITY_BRIDGE_MISMATCH')
        self.s['account']['balance']=amount(closing); self.s['account']['version']+=1; self.s['account']['as_of']=a['as_of']
        self.s['trade_date']=next_day; self.s['day_opening'][next_day]=amount(closing)
        result=dict(commit_status='COMMITTED',trade_date=day,settlement_version=a['settlement_version'],opening_equity=amount(opening),net_deposits='0',realized_pnl=totals['realized'],holding_pnl=amount(adjustment),fees=totals['fees'],incremental_booking_adjustment=amount(adjustment),closing_equity=amount(closing),next_trade_date=next_day,account=self.adapter.snapshot())
        self.s['settlements'][day]=dict(hash=h,result=copy.deepcopy(result)); return result

    def cta_daily_settle(self,a): return self.invoke('cta-settlement-apply',a)

    def cta_roll_plan(self,a):
        self.consistent(); require(a['old_contract_id']!=a['new_contract_id'],'INVALID_ROLL')
        h=digest(a); old=self.s['rolls'].get(a['roll_id'])
        if old: require(old['hash']==h,'ROLL_CONFLICT'); return copy.deepcopy(old)
        long,short=self.gross(a['old_contract_id']); q=a['lots']; direction=1 if long else -1
        require(q>0 and q<=long+short,'INSUFFICIENT_CLOSEABLE')
        newlong,newshort=self.gross(a['new_contract_id']); require(not(newshort if direction>0 else newlong),'ROLL_DIRECTION_CONFLICT')
        base=dict(account_version=a['account_version'],as_of=a['as_of'],target_id=a['roll_id'],target_version=1,buffer=a.get('buffer','0'))
        oldplan=self.create_plan(dict(base,contract_id=a['old_contract_id'],target_net_lots=long-short-direction*q,reference_price=a['old_reference_price']))
        dependencies=[k for k in oldplan['leg_ids'] if self.s['legs'][k]['offset']!='OPEN']
        newplan=self.create_plan(dict(base,contract_id=a['new_contract_id'],target_net_lots=newlong-newshort+direction*q,reference_price=a['new_reference_price']),extra_dependencies=dependencies)
        roll=dict(roll_id=a['roll_id'],old_plan_id=oldplan['plan_id'],new_plan_id=newplan['plan_id'],lots=q,direction=direction,hash=h,commit_status='COMMITTED')
        self.s['rolls'][a['roll_id']]=roll
        return copy.deepcopy(roll)

    def cta_roll_progress(self,a):
        roll=self.s['rolls'].get(a['roll_id']); require(roll is not None,'ROLL_NOT_FOUND')
        def booked(pid):
            lids=set(self.s['plans'][pid]['leg_ids'])
            return sum(f['lots'] for f in self.s['fills'].values() if f['accounting_status']=='BOOKED' and self.s['orders'][f['order_id']]['leg_id'] in lids)
        closed,opened=booked(roll['old_plan_id']),booked(roll['new_plan_id'])
        return dict(roll_id=a['roll_id'],closed_old_lots=closed,opened_new_lots=opened,remaining_old_lots=roll['lots']-closed,remaining_new_lots=roll['lots']-opened,unconnected_lots=closed-opened,complete=closed==opened==roll['lots'])
