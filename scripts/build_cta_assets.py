"""Generate 24 independent futures skills, fixture sessions and executable examples."""
import copy
import json
import shutil
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from cta_execution.engine import Runtime, TOOLS, UPPER, WRITES
from cta_execution.contracts import schemas, obj, S
from scripts.cta_tool_layers import metadata, annotation


def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(value if isinstance(value,str) else json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def fixture(side='LONG',frequency='1m'):
    dates=['2026-01-05','2026-01-06','2026-01-12']
    rule=dict(profile_id='simulation_fixture',version='1',exchange='SIM_SHFE',product='SIM',multiplier=10,price_tick='1',min_lots=1,lot_step=1,margin_mode='RATE',margin=dict(LONG='0.10',SHORT='0.12'),fees={k:dict(mode='PER_LOT',value=v) for k,v in [('OPEN','2'),('CLOSE','2'),('CLOSE_TODAY','4'),('CLOSE_YESTERDAY','1')]},close_priority=['YESTERDAY','TODAY'],separate_close=True,lower_price='10',upper_price='200',trade_dates=dates,previous_settlement={dates[0]:'100',dates[1]:'110',dates[2]:'105'},disclaimer='Synthetic futures rules; no official exchange compliance claimed')
    contracts={cid:dict(copy.deepcopy(rule),contract_id=cid) for cid in ['SIM:OLD','SIM:NEW']}
    calendar=[]
    for cid in contracts:
        for day in dates:
            for lo,hi in [('09:00','10:15'),('10:30','11:30'),('13:30','15:00')]:
                calendar.append(dict(contract_id=cid,trade_date=day,start_at=day+'T'+lo+':00+08:00',end_at=day+'T'+hi+':00+08:00',phase='DAY'))
        calendar.append(dict(contract_id=cid,trade_date='2026-01-12',start_at='2026-01-09T21:00:00+08:00',end_at='2026-01-10T02:00:00+08:00',phase='NIGHT'))
    return dict(simulation_id='cta-demo',account=dict(account_id='mock-futures',asset_class='FUTURES',currency='CNY',balance='100000',as_of='2026-01-05T09:01:00+08:00',version=1),contracts=contracts,calendar=calendar,positions={'SIM:OLD':[dict(lot_id='initial',side=side,bucket='YESTERDAY',quantity=3,basis_price='100',opened_trade_date='2026-01-02')]},marks={'SIM:OLD':'100','SIM:NEW':'100'},frequency=frequency,trade_date='2026-01-05')


def bar(cid='SIM:OLD',event='cta-bar1',volume=2,start='2026-01-05T09:01:00+08:00',end='2026-01-05T09:02:00+08:00',price='100',frequency='1m'):
    return dict(event_id=event,contract_id=cid,multiplier=10,volume_unit='lots',frequency=frequency,trade_date='2026-01-05',start_at=start,end_at=end,open=price,high=price,low=price,close=price,volume=volume,tradable=True,price_limit_clear=True,price_basis='UNADJUSTED',synthetic=True,source='synthetic')


def request(data,key='example-1'):
    return dict(schema_version='1.0',request_id=key,account_id='mock-futures',simulation_id='cta-demo',asset_class='FUTURES',idempotency_key=key,data=data)


def plan_data():
    return dict(contract_id='SIM:OLD',target_net_lots=-2,target_id='target1',target_version=1,account_version=1,as_of='2026-01-05T09:01:00+08:00',reference_price='100')


def settle_data(side='LONG'):
    return dict(trade_date='2026-01-05',settlement_version=1,as_of='2026-01-05T15:00:00+08:00',prices=[dict(contract_id='SIM:OLD',prev_settlement_price='100',settlement_price='110')])


def scenario(tool):
    """Return an actually prepared state, request and successful response per interface."""
    r=Runtime(':memory:'); r.initialize(**fixture()); counter=0
    def call(t,data):
        nonlocal counter
        counter+=1; result=r.call(t,request(data,'setup'+str(counter)))
        if not result['ok']: raise RuntimeError((t,result))
        return result['data']
    plan=call('cta-order-plan',plan_data()); lid=plan['leg_ids'][0]
    leg=dict(leg_id=lid,account_version=1,submitted_at='2026-01-05T09:01:00+08:00')
    roll=dict(roll_id='roll1',old_contract_id='SIM:OLD',new_contract_id='SIM:NEW',lots=2,old_reference_price='100',new_reference_price='100',account_version=1,as_of='2026-01-05T09:01:00+08:00')
    b=bar(); simulate=dict(bar=b,visible_at=b['end_at'],participation_rate='1',slippage='0')
    samples={
      'cta-order-plan':plan_data(),'cta-order-precheck':leg,'cta-order-submit':dict(leg,client_order_id='client1'),
      'cta-order-cancel':dict(order_id='cta-o1',expected_version=1),'cta-execution-simulate':simulate,
      'cta-order-query':dict(order_id='cta-o1'),'cta-daily-settle':settle_data(),'cta-roll-plan':roll,
      'cta-contract-spec':dict(contract_id='SIM:OLD',trade_date='2026-01-05'),
      'cta-trading-session':dict(contract_id='SIM:OLD',timestamp='2026-01-09T23:59:00+08:00'),
      'cta-position-gap':dict(contract_id='SIM:OLD',target_net_lots=-2,target_id='target1',target_version=1),
      'cta-offset-split':dict(contract_id='SIM:OLD',trade_date='2026-01-05',gap_lots=-5),
      'cta-order-rule-check':leg,
      'cta-margin-calculate':dict(contract_id='SIM:OLD',trade_date='2026-01-05',price='100',lots=2,position_side='SHORT'),
      'cta-fee-calculate':dict(contract_id='SIM:OLD',trade_date='2026-01-05',price='100',lots=2,offset='CLOSE_TODAY'),
      'cta-order-register':dict(leg,client_order_id='client1'),'cta-order-release':dict(order_id='cta-o1',expected_version=2),
      'cta-order-match':dict(order_id='cta-o1',bar=b,participation_rate='1',slippage='0'),
      'cta-fill-record':dict(order_id='cta-o1',fill_id='f1',event_id=b['event_id'],expected_version=1),
      'cta-order-state-update':dict(order_id='cta-o1',event_type='FILL',fill_id='f1',expected_version=1),
      'cta-fill-book':dict(fill_id='f1'),'cta-order-detail':dict(order_id='cta-o1'),
      'cta-settlement-apply':settle_data(),'cta-roll-progress':dict(roll_id='roll1')}
    order_tools={'cta-order-cancel','cta-execution-simulate','cta-order-query','cta-order-release','cta-order-match','cta-fill-record','cta-order-state-update','cta-fill-book','cta-order-detail'}
    if tool in order_tools: call('cta-order-submit',dict(leg,client_order_id='client1'))
    if tool in {'cta-order-match','cta-fill-record','cta-order-state-update','cta-fill-book'}:
        r.publish_market_event('cta-demo',b,b['end_at'],'1','0')
    if tool in {'cta-order-state-update','cta-fill-book'}: call('cta-fill-record',samples['cta-fill-record'])
    if tool=='cta-fill-book': call('cta-order-state-update',samples['cta-order-state-update'])
    if tool=='cta-order-release': call('cta-order-state-update',dict(order_id='cta-o1',event_type='CANCEL',expected_version=1))
    if tool in {'cta-order-query','cta-order-detail'}: call('cta-execution-simulate',simulate)
    if tool=='cta-roll-progress': call('cta-roll-plan',roll)
    # Save the legitimate pre-state to make every example independently reproducible.
    state=json.loads(r.db.execute('SELECT payload FROM cta_sessions').fetchone()[0])
    req=request(samples[tool]); success=r.call(tool,req)
    if not success['ok']: raise RuntimeError((tool,success))
    r.db.close(); return state,req,success


DESCRIPTIONS={
'cta-order-plan':'Persist integer net-lot plans with close-before-open dependencies; do not accept stock weights.',
'cta-order-precheck':'Check the latest contract, session, dependencies and resources without freezing.',
'cta-order-submit':'Revalidate a persisted plan leg and atomically register and freeze resources.',
'cta-order-cancel':'Cancel remaining lots and release resources while preserving actual fills.',
'cta-execution-simulate':'Advance one completed futures bar through matching, booking and release.',
'cta-order-query':'Read order, fills, reservations and account reconciliation status.',
'cta-daily-settle':'Apply explicit-price daily marked-to-market settlement and day migration.',
'cta-roll-plan':'Persist linked old-close/new-open plans; plans do not imply executed progress.',
'cta-contract-spec':'Read the configured contract and trade-date rule profile.',
'cta-trading-session':'Resolve an explicit calendar interval to a trading day, including night sessions.',
'cta-position-gap':'Read gross positions and active open/close leaves to calculate signed net-lot gap.',
'cta-offset-split':'Calculate side and today/yesterday closing splits followed by opening lots.',
'cta-order-rule-check':'Read authoritative rules and resources to validate a persisted plan leg; do not freeze.',
'cta-margin-calculate':'Calculate explicit RATE or FIXED margin and notional; do not book money.',
'cta-fee-calculate':'Calculate per-lot or notional incremental fees using the explicit offset.',
'cta-order-register':'Atomically register and freeze one validated persisted plan leg.',
'cta-order-release':'Release only excess resources justified by persisted remaining lots and fills.',
'cta-order-match':'Calculate a conservative opening-price candidate; do not occupy capacity or book.',
'cta-fill-record':'Recompute from a persisted market event and atomically record a fill and occupy capacity.',
'cta-order-state-update':'Apply a persisted fill or versioned cancellation to order quantities only.',
'cta-fill-book':'Idempotently book an existing applied fill, fees, realized PnL and lot claims.',
'cta-order-detail':'Read current order, fills, reservations and accounting status without mutation.',
'cta-settlement-apply':'Book only incremental daily holding PnL and migrate lot buckets once.',
'cta-roll-progress':'Read actual booked old-close/new-open lots and unconnected exposure.'}
FLOW={
'cta-order-plan':'cta-contract-spec → cta-trading-session → cta-position-gap → cta-offset-split',
'cta-order-precheck':'cta-order-rule-check → cta-margin-calculate → cta-fee-calculate',
'cta-order-submit':'cta-order-rule-check → cta-order-register (registration and freeze are atomic)',
'cta-order-cancel':'cta-order-state-update(CANCEL) → cta-order-release → cta-order-detail',
'cta-execution-simulate':'cta-order-match → cta-fill-record → cta-order-state-update → cta-fill-book → cta-order-release',
'cta-order-query':'cta-order-detail',
'cta-daily-settle':'cta-settlement-apply (checks rules, expires DAY leaves, books MTM, migrates buckets)',
'cta-roll-plan':'cta-contract-spec → cta-trading-session → cta-position-gap → cta-offset-split; link persisted legs'}


def shape(value,key=''):
    if key=='order_id': return {'type':['string','null']}
    if value is None: return {'type':'null'}
    if isinstance(value,bool): return {'type':'boolean'}
    if type(value) is int: return {'type':'integer'}
    if isinstance(value,str): return {'type':'string'}
    if isinstance(value,list): return {'type':'array','items':shape(value[0]) if value else {}}
    if key in ('positions','fees','margin','previous_settlement'): return {'type':'object','additionalProperties':{}}
    return dict(type='object',properties={k:shape(v,k) for k,v in value.items()},required=[k for k in value if k not in ('average_price','bucket','cancel_pending')],additionalProperties=True)


def main():
    inputs=schemas(); write(ROOT/'cta_execution/contracts.json',inputs)
    for side in ('LONG','SHORT'):
        write(ROOT/'examples/cta'/side.lower()/'session.json',fixture(side))
        write(ROOT/'examples/cta'/side.lower()/'settlement.json',request(settle_data(side)))
        write(ROOT/'examples/cta'/side.lower()/'expected.json',dict(opening_equity='100000',holding_pnl='300' if side=='LONG' else '-300',closing_equity='100300' if side=='LONG' else '99700',position_margin='330' if side=='LONG' else '396',next_trade_date='2026-01-06'))
    write(ROOT/'examples/cta/minute.json',bar())
    write(ROOT/'examples/cta/daily.json',bar(event='cta-day1',volume=3,start='2026-01-05T09:00:00+08:00',end='2026-01-05T15:00:00+08:00',frequency='1d'))
    write(ROOT/'examples/cta/plan.json',request(plan_data()))
    catalog={}
    for tool in TOOLS:
        folder=ROOT/'skills'/tool; state,req,success=scenario(tool)
        data_shape=shape(success['data'])
        if tool=='cta-order-cancel':
            data_shape['properties']['release']={'anyOf':[data_shape['properties']['release'],{'type':'null'}]}
        if tool=='cta-order-match': data_shape={'anyOf':[data_shape,obj(dict(lots={'const':0},reason=S))]}
        if tool=='cta-execution-simulate': data_shape={'anyOf':[data_shape,obj(dict(commit_status={'enum':['ACCOUNTING_PENDING','RECOVERY_REQUIRED']},completed_steps={'type':'array'},failed_step=S,retryable={'const':True},event_id=S,reconciliation_status={'const':'PENDING'}))]}
        output={'$schema':'https://json-schema.org/draft/2020-12/schema','oneOf':[obj(dict(ok={'const':True},schema_version={'const':'1.0'},request_id=S,data=data_shape,warnings={'type':'array'})),obj(dict(ok={'const':False},schema_version={'const':'1.0'},request_id={'type':'string'},error=obj(dict(code=S,message={'type':'string'},retryable={'type':'boolean'},details={'type':'object'}))))]}
        for name,value in [('input.schema',inputs[tool]),('output.schema',output),('example',req),('success',success),('prepared-state',state),('runtime',dict(python='>=3.11',dependencies=[],mode='simulation_only',asset_class='FUTURES',shared_core=['cta_execution','execution_common']))]: write(folder/'assets'/(name+'.json'),value)
        failed=dict(req,simulation_id='does-not-exist')
        write(folder/'assets/failure-request.json',failed)
        r=Runtime(':memory:'); write(folder/'assets/failure.json',r.call(tool,failed)); r.db.close()
        write(folder/'scripts/run.py','from pathlib import Path\nimport sys\nsys.path.insert(0,str(Path(__file__).resolve().parent))\nfrom engine import execute\n\nif __name__=="__main__":\n    raise SystemExit(execute())\n')
        write(folder/'scripts/engine.py',f'from cta_execution.cli import run\n\ndef execute():\n    return run({tool!r})\n')
        for package in ('cta_execution','execution_common'): shutil.copytree(ROOT/package,folder/'scripts'/package,dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__'))
        layer='Upper' if tool in UPPER else 'Atomic'; catalog[tool]=dict(layer=layer,write=tool in WRITES,asset_class='FUTURES',description=DESCRIPTIONS[tool],**metadata(tool))
        write(folder/'SKILL.md',f'''---
name: {tool}
description: {DESCRIPTIONS[tool]} Futures simulation only; never route stock weights here.
when_to_use: Explicit {tool} futures simulation requests.
version: 0.2.0
entry: scripts/run.py
allowed_tools:
  - skill_run_script
---

This {layer} tool requires `asset_class=FUTURES`, an explicit account/simulation and integer lots. Read [contract](references/contract.md) and [input schema](assets/input.schema.json). Missing or ambiguous contract, trade date, offset or quantity is an error, not permission to guess.

Invoke `skill_run_script` with `scripts/run.py` and `--db cta.sqlite --input assets/example.json`. Direct Python accepts the same arguments; stdout is JSON and exit code is 0 for an envelope with ok=true, 1 for an error. A pending commit_status still requires recovery.

For a fresh planning session, add `--init <session.json>`. For other examples, reproduce the prerequisite state using the project replay script and assets/prepared-state.json. Never copy resources from sibling skills implicitly. Core dependencies are bundled within scripts/.

{annotation(tool)}
'''.rstrip()+'\n')
        write(folder/'references/contract.md',f'''# {tool}

Responsibility: {DESCRIPTIONS[tool]} Layer: {layer}. This interface does not connect to a live broker, use stock weight semantics or assume official exchange rules.

{annotation(tool)}

Business invariants: targets keep their normalized quantity for the same version; newer CTA targets supersede earlier unsubmitted legs. Stock order-plan persists normalization and requires an idempotency key. Cancel action REQUEST preserves live leaves and resources, REJECT clears only cancel_pending, CONFIRM cancels the remaining leaves and releases after bookkeeping. Omitted action retains the legacy synchronous mock confirmation. Use REQUEST explicitly for asynchronous simulations. Fill conflicts persist RECONCILE and block new submissions; valid recorded fills and queries remain available. Clearing RECONCILE requires the trusted runtime resolve_reconciliation boundary with independent evidence and CAS checks, not an agent tool. CTA reservation_policy defaults to UPPER_BOUND_V1; ORDER_PRICE_V1 is an explicit fixture policy, and fills exceeding the reserved budget (including retained leaves) do not match. These are local simulation contracts, not live broker callbacks.

Contracts: [input](../assets/input.schema.json), [output](../assets/output.schema.json). Executed fixtures: [request](../assets/example.json), [success](../assets/success.json), [failure request](../assets/failure-request.json), [failure](../assets/failure.json).

{'Writes require a nonempty idempotency_key: the same tool/key/payload returns the original result; changed payload returns IDEMPOTENCY_CONFLICT. All writes and resource freezes use SQLite transactions.' if tool in WRITES else 'Read/calculation only: no implicit account, order, fill or reservation updates.'}

Preconditions: initialized FUTURES account, configured explicit calendar and contract profile; persisted plan leg and current account version before registration; persisted market event before recording; persisted fill before state update and booking; current order version before state/release. Opening dependencies must be completely filled and booked. Registration and freeze either both commit or neither does.

{'Atomic order: '+FLOW[tool]+'.' if tool in FLOW else 'This Atomic performs one domain responsibility and never calls an Upper workflow.'}

Cancellation must be followed by release. Fill recovery sequence is record → state update → book → release. ACCOUNTING_PENDING/RECOVERY_REQUIRED blocks dependent trading. To recover an interrupted simulation, retry the same bar/model with a new idempotency key and without fail_after. Reusing the old key returns the original pending response. Completed event retries do not consume capacity twice.

Errors include ASSET_CLASS_MISMATCH/INVALID_REQUEST, PLAN_LEG_NOT_FOUND, STALE_SNAPSHOT, STALE_ORDER_VERSION, DEPENDENCY_NOT_BOOKED, INSUFFICIENT_MARGIN, INSUFFICIENT_CLOSEABLE, UNSUPPORTED_HEDGED_POSITION, OUTSIDE_TRADING_SESSION, ACCOUNTING_PENDING, RELEASE_PENDING, SETTLEMENT_CONFLICT and MISSING_SETTLEMENT_PRICE. These are simulation-domain failures; no internal step requires manual approval.

Reproduce: `python scripts/replay_cta_example.py --tool {tool}` from the source/plugin project. Prepared states are test-only trusted local fixtures and are not accepted by public trading tools.
''')
    write(ROOT/'contracts/cta-catalog.json',catalog)
    stock=json.loads((ROOT/'contracts/catalog.json').read_text(encoding='utf-8'))
    stock={k:v for k,v in stock.items() if not k.startswith('cta-')}
    write(ROOT/'contracts/catalog.json',dict(stock,**catalog))
    write(ROOT/'plugin.json',dict(name='execution-tools',version='0.2.0',description='21 stock + 24 CTA simulation tools',mode='simulation_only',skills=[dict(name=t,path='skills/'+t,entry='scripts/run.py',asset_class='FUTURES' if t.startswith('cta-') else 'STOCK') for t in list(stock)+TOOLS]))


if __name__=='__main__': main()
