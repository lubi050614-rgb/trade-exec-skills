"""Generate per-tool contracts and portable plugin assets from one interface catalog."""
import json
import shutil
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from stock_execution.engine import TOOLS, WRITES


def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n' if not isinstance(value,str) else value,encoding='utf-8')


S={'type':'string'}
I={'type':'integer','minimum':0}
DEC={'type':'string','pattern':r'^-?[0-9]+(\.[0-9]+)?$'}
POS={'type':'integer','minimum':1}
def obj(fields,optional=()):
    return dict(type='object',properties=fields,required=[k for k in fields if k not in optional],additionalProperties=False)

ORDER=obj(dict(instrument_id=S,side={'enum':['BUY','SELL']},quantity=POS,order_type={'enum':['LIMIT','MARKET']},limit_price=DEC,protection_price=DEC,time_in_force={'const':'DAY'},submitted_at={'type':'string','format':'date-time'},target_id=S,target_version=POS,account_version=POS),('limit_price','protection_price'))
ORDER['allOf']=[{'if':{'properties':{'order_type':{'const':'LIMIT'}}},'then':{'required':['limit_price']},'else':{'required':['protection_price']}}]
BAR=obj(dict(event_id=S,instrument_id=S,frequency={'enum':['1m','1d']},trade_date=S,start_at=S,end_at=S,open=DEC,high=DEC,low=DEC,close=DEC,volume=I,amount=DEC,tradable={'type':'boolean'},price_limit_clear={'type':'boolean'},price_basis={'const':'UNADJUSTED'},source=S,synthetic={'type':'boolean'}))
TARGET=obj(dict(instrument_id=S,target_weight=DEC,current_weight=DEC,reference_price=DEC,price_basis={'const':'UNADJUSTED'},price_as_of=S,price_source=S))
FIELDS={
 'order-plan':dict(account_snapshot_id=S,as_of=S,total_assets=DEC,coverage={'const':'FULL'},target_id=S,target_version=POS,targets={'type':'array','items':TARGET},weight_tolerance=DEC,cash_buffer=DEC),
 'order-precheck':dict(order=ORDER), 'order-submit':dict(order=ORDER,client_order_id=S),
 'order-cancel':dict(order_id=S,expected_version=POS,action={'enum':['REQUEST','CONFIRM','REJECT']}),
 'execution-simulate':dict(bar=BAR,visible_at=S,participation_rate=DEC,slippage=DEC,end_of_day={'type':'boolean'},fail_after={'enum':['record','order','account']}),
 'order-query':dict(order_id=S,offset=I,limit=POS),
 'order-open-quantity':dict(instrument_id=S),
 'order-target-gap':{k:I for k in ('target_quantity','actual_quantity','buy_quantity','sell_quantity')},
 'order-rule-check':dict(order=ORDER),
 'execution-fee-calculate':dict(side={'enum':['BUY','SELL']},notional=DEC,cumulative_notional=DEC,charged_fee=DEC),
 'order-resource-check':dict(order=ORDER), 'order-register':dict(order=ORDER,client_order_id=S),
 'order-reserve':dict(order_id=S,expected_version=POS,account_version=POS),
 'order-state-read':dict(order_id=S), 'order-cancel-remainder':dict(order_id=S,expected_version=POS),
 'order-release-reserve':dict(order_id=S,expected_version=POS),
 'execution-match':dict(order_id=S,bar=BAR,participation_rate=DEC,slippage=DEC),
 'execution-fill-record':dict(order_id=S,fill_id=S,event_id=S,expected_version=POS),
 'order-apply-fill':dict(order_id=S,fill_id=S,expected_version=POS),
 'account-apply-fill':dict(fill_id=S), 'execution-fill-list':dict(order_id=S,offset=I,limit=POS)}
OPTIONAL={'order-cancel':('action',),'order-plan':('weight_tolerance','cash_buffer'),'execution-simulate':('end_of_day','fail_after'),'order-query':('offset','limit'),'execution-fee-calculate':('cumulative_notional','charged_fee'),'execution-fill-list':('offset','limit')}
FLOW={'order-plan':'order-open-quantity → order-target-gap', 'order-precheck':'order-rule-check → execution-fee-calculate → order-resource-check', 'order-submit':'order-rule-check → execution-fee-calculate → order-resource-check → order-register → order-reserve', 'order-cancel':'order-state-read → order-cancel-remainder → order-release-reserve', 'execution-simulate':'execution-match → execution-fill-record → order-apply-fill → account-apply-fill → order-release-reserve', 'order-query':'order-state-read → execution-fill-list'}
RESPONSIBILITIES={
'order-plan':('完整权重清单确定性转换为目标股数，并扣减兼容在途委托；返回舍入偏差、费用和现金依赖','不提交或冻结，不随行情自动重算目标'),
'order-precheck':('读取当前账户并检查订单数量、价格、时间、费用和资源','不登记、不冻结；检查通过不保证后续提交成功'),
'order-submit':('在同一 SQLite 事务中重新检查、登记并预留单笔订单','不承诺组合批次原子成交，不提前使用未成交卖单收入'),
'order-cancel':('读取当前订单版本、撤销剩余量并释放资源','不撤回既有成交'),
'execution-simulate':('推进一个已完成行情事件并编排成交、订单进度、记账和资源释放','不使用未完成 bar、不接真实行情、不保证必然成交'),
'order-query':('组合查询订单、逐笔成交和账户状态','不进行成交、记账或状态修复'),
'order-open-quantity':('读取指定证券有效订单剩余买卖量，排除未预留单和终态单','不把已成交量再次计入在途'),
'order-target-gap':('计算 target - actual - buy_leaves + sell_leaves','不做权重转换或读写账户'),
'order-rule-check':('按显式证券规则 profile 检查订单时间、数量、价格、类型','不验证生产交易所规则、不冻结资源'),
'execution-fee-calculate':('按订单累计成交金额计算本次增量佣金与卖出税；最低费按订单累计','不对每次部分成交重复收取最低费，不记账'),
'order-resource-check':('按权威账户快照检查所需现金或扣除冻结后的可卖量','不冻结、不写入账户'),
'order-register':('登记唯一 client_order_id，状态为 PENDING_RESERVATION','不预留、不激活；原请求重试使用相同幂等键'),
'order-reserve':('比较订单和账户版本，原子预留后激活订单','不在预留失败时把订单变为活动单'),
'order-state-read':('读取订单方向、价格、委托/成交/撤销/剩余量、状态与版本','不读取或修改账户账本'),
'order-cancel-remainder':('基于预期版本撤销剩余量并保留已成交量','不释放预留，后续必须调用 order-release-reserve'),
'order-release-reserve':('根据持久化订单和已记账事实计算仍需预留并释放多余资源','不信任调用者任意指定释放量，不进行成交记账'),
'execution-match':('纯计算基于开盘价、保护价、规则和剩余共享容量的成交候选','不占用容量、不持久化成交、不修改账户'),
'execution-fill-record':('读取可信已持久化行情，重算候选、比较订单版本并原子登记成交和占容量','不接收调用者伪造价格/数量，不推进订单或记账'),
'order-apply-fill':('读取已登记成交，幂等推进订单成交量、剩余量、均价与状态','不计算虚构成交、不写账户余额'),
'account-apply-fill':('通过账户适配器对已推进订单的持久化成交幂等入账','不接受调用者指定余额或利润，不替代真实生产账户服务'),
'execution-fill-list':('分页读取订单逐笔成交及处理状态','不推进订单或修复记账')}


def success_example(tool,example,samples,fixture):
    from stock_execution.engine import Runtime
    r=Runtime(':memory:'); r.initialize(fixture['simulation_id'],fixture['account'],fixture['rules'])
    counter=0
    def call(t,data):
        nonlocal counter
        counter+=1
        req=dict(example,request_id='setup-'+str(counter),idempotency_key='setup-'+str(counter),data=data)
        result=r.call(t,req)
        if not result['ok']: raise RuntimeError(result)
        return result['data']
    needs_order={'order-cancel','execution-simulate','order-query','order-state-read','order-cancel-remainder','order-release-reserve','execution-match','execution-fill-record','order-apply-fill','account-apply-fill','execution-fill-list'}
    if tool in needs_order: call('order-submit',samples['order-submit'])
    if tool=='order-reserve': call('order-register',samples['order-register'])
    if tool=='order-release-reserve': call('order-cancel-remainder',samples['order-cancel-remainder'])
    if tool in {'execution-fill-record','order-apply-fill','account-apply-fill','execution-match'}:
        b=samples['execution-simulate']['bar']
        r.publish_market_event(fixture['simulation_id'],b,b['end_at'],'0.1','0')
    if tool in {'order-apply-fill','account-apply-fill'}: call('execution-fill-record',samples['execution-fill-record'])
    if tool=='account-apply-fill': call('order-apply-fill',samples['order-apply-fill'])
    if tool in {'order-query','execution-fill-list'}: call('execution-simulate',samples['execution-simulate'])
    result=r.call(tool,example)
    if not result['ok']: raise RuntimeError(result)
    r.db.close()
    return result


def result_schema(value, path=''):
    """Type the stable result fields, leaving map keys/data extensions open."""
    fields={}
    for k,v in value.items():
        if isinstance(v,bool): s={'type':'boolean'}
        elif type(v) is int: s={'type':'integer'}
        elif isinstance(v,str): s={'type':'string'}
        elif v is None: s={'type':['integer','null']}
        elif isinstance(v,list): s={'type':'array','items':result_schema(v[0],path+'.'+k) if v and isinstance(v[0],dict) else {}}
        elif k=='positions': s={'type':'object','additionalProperties':result_schema(next(iter(v.values())),path+'.'+k) if v else {'type':'object'}}
        else: s=result_schema(v,path+'.'+k)
        fields[k]=s
    # Average price and settled/unsettled details can appear later in the lifecycle.
    return dict(type='object',properties=fields,required=[k for k in fields if k not in ('average_price','cancel_pending')],additionalProperties=True)


def main():
    catalog={}; contracts={}
    for ex,board,minimum,step in [('SSE','SIM_MAIN',100,100),('SZSE','SIM_GROWTH',200,100),('BSE','SIM_BSE',100,1)]:
        k=ex+':SIM0001'; asof='2026-01-05T09:31:00+08:00'
        rule=dict(profile_id='simulation_fixture',version='1',exchange=ex,board=board,instrument_type='STOCK',price_tick='0.01',buy_min=minimum,buy_step=step,sell_step=step,odd_lot_liquidation=True,lower_price='1',upper_price='100',sessions=[['09:30','11:30'],['13:00','15:00']],trade_dates=['2026-01-05','2026-01-06'],settlement='T+1',disclaimer='Synthetic rules; not official exchange rules')
        fixture=dict(simulation_id='demo-'+ex,frequency='1m',account=dict(account_id='mock-'+ex,currency='CNY',cash_balance='96000',as_of=asof,version=1,positions={k:dict(quantity=400,settled_quantity=400,valuation_price='10',exchange=ex,board=board,unsettled=[])}),rules={k:rule})
        plan=dict(schema_version='1.0',request_id='plan-1',account_id=fixture['account']['account_id'],simulation_id=fixture['simulation_id'],data=dict(account_snapshot_id='1',as_of=asof,total_assets='100000',coverage='FULL',target_id='target-1',target_version=1,targets=[dict(instrument_id=k,target_weight='0.10',current_weight='0.04',reference_price='10',price_basis='UNADJUSTED',price_as_of=asof,price_source='synthetic')]))
        bar=dict(event_id='bar-1',instrument_id=k,frequency='1m',trade_date='2026-01-05',start_at=asof,end_at='2026-01-05T09:32:00+08:00',open='10',high='10.1',low='9.9',close='10',volume=3000,amount='30000',tradable=True,price_limit_clear=True,price_basis='UNADJUSTED',source='synthetic',synthetic=True)
        plan['idempotency_key']='plan-1'
        daily=dict(bar,event_id='day-1',frequency='1d',trade_date='2026-01-06',start_at='2026-01-06T09:30:00+08:00',end_at='2026-01-06T15:00:00+08:00')
        for name,value in [('session',fixture),('plan',plan),('minute',bar),('daily',daily),('expected',dict(target_quantity=1000,order_quantity=600,full_fill_fee='5.00',cash_balance='89995.00',position_quantity=1000))]: write(ROOT/'examples'/ex/(name+'.json'),value)
        if ex=='SSE':
            base=plan; sample_fixture=fixture
            sample_order=dict(instrument_id=k,side='BUY',quantity=600,order_type='LIMIT',limit_price='10',time_in_force='DAY',submitted_at=asof,target_id='target-1',target_version=1,account_version=1); sample_bar=bar
    samples={
      'order-plan':base['data'],'order-precheck':dict(order=sample_order),'order-submit':dict(order=sample_order,client_order_id='client-1'),
      'order-cancel':dict(order_id='o-1',expected_version=2),'execution-simulate':dict(bar=sample_bar,visible_at=sample_bar['end_at'],participation_rate='0.1',slippage='0'),
      'order-query':dict(order_id='o-1'),'order-open-quantity':dict(instrument_id='SSE:SIM0001'),
      'order-target-gap':dict(target_quantity=1000,actual_quantity=400,buy_quantity=200,sell_quantity=0),
      'order-rule-check':dict(order=sample_order),'execution-fee-calculate':dict(side='BUY',notional='3000',cumulative_notional='0',charged_fee='0'),
      'order-resource-check':dict(order=sample_order),'order-register':dict(order=sample_order,client_order_id='client-1'),
      'order-reserve':dict(order_id='o-1',expected_version=1,account_version=1),'order-state-read':dict(order_id='o-1'),
      'order-cancel-remainder':dict(order_id='o-1',expected_version=2),'order-release-reserve':dict(order_id='o-1',expected_version=3),
      'execution-match':dict(order_id='o-1',bar=sample_bar,participation_rate='0.1',slippage='0'),
      'execution-fill-record':dict(order_id='o-1',fill_id='bar-1:o-1',event_id='bar-1',expected_version=2),
      'order-apply-fill':dict(order_id='o-1',fill_id='bar-1:o-1',expected_version=2),
      'account-apply-fill':dict(fill_id='bar-1:o-1'),'execution-fill-list':dict(order_id='o-1')}
    for tool in TOOLS:
        folder=ROOT/'skills'/tool
        data=obj(FIELDS[tool],OPTIONAL.get(tool,()))
        request=obj(dict(schema_version={'const':'1.0'},request_id=S,account_id=S,simulation_id=S,data=data,idempotency_key=S),() if tool in WRITES else ('idempotency_key',))
        request['$schema']='https://json-schema.org/draft/2020-12/schema'
        contracts[tool]=request
        response=dict(**{'$schema':'https://json-schema.org/draft/2020-12/schema'},oneOf=[obj(dict(ok={'const':True},schema_version={'const':'1.0'},request_id=S,data={'type':'object'},warnings={'type':'array','items':S})),obj(dict(ok={'const':False},schema_version={'const':'1.0'},request_id=S,error=obj(dict(code=S,message=S,retryable={'type':'boolean'},details={'type':'object'}))))])
        example=dict(base,data=samples[tool],request_id='example-'+tool)
        if tool in WRITES: example['idempotency_key']='example-1'
        catalog[tool]=dict(layer='Upper' if tool in FLOW else 'Atomic',write=tool in WRITES,fields=list(FIELDS[tool]))
        write(folder/'assets/input.schema.json',request); write(folder/'assets/output.schema.json',response)
        write(folder/'assets/example.json',example)
        write(folder/'assets/failure.json',dict(ok=False,schema_version='1.0',request_id=example['request_id'],error=dict(code='UNKNOWN_SIMULATION',message='UNKNOWN_SIMULATION',retryable=False,details={})))
        write(folder/'assets/runtime.json',dict(python='>=3.11',dependencies=[],mode='simulation_only',database='SQLite',core='bundled scripts/stock_execution'))
        write(folder/'scripts/run.py','from pathlib import Path\nimport sys\nsys.path.insert(0,str(Path(__file__).resolve().parent))\nfrom engine import execute\n\nif __name__ == "__main__":\n    raise SystemExit(execute())\n')
        write(folder/'scripts/engine.py',f'from stock_execution.cli import run\n\ndef execute():\n    return run({tool!r})\n')
        write(folder/'SKILL.md',f'''---
name: {tool}
description: Execute the {tool} stock simulation interface using explicit JSON inputs and a persistent mock session.
when_to_use: Explicit {tool} requests for simulated stock execution.
version: 0.1.0
entry: scripts/run.py
allowed_tools:
  - skill_run_script
---

Use this independent {catalog[tool]['layer']} interface for `{tool}`. Read [contract](references/contract.md) for its required inputs and preconditions. This tool uses synthetic stock rules and an authoritative mock account only.

Call `skill_run_script` with `scripts/run.py` and arguments `--db simulation.sqlite --input assets/example.json`. For a fresh session add `--init <session.json>` using an exchange fixture from the plugin examples. Run via Python directly with the same arguments when skill_run_script is unavailable.

Stdout is one JSON envelope. Exit 0 means transport/domain success, 1 means an error envelope; inspect `commit_status` for pending recovery. The database path must be shared by related calls. Never substitute real account credentials or infer a production rule profile.
''')
        duty,exclusion=RESPONSIBILITIES[tool]
        write(folder/'references/contract.md',f'''# {tool}

Layer: {catalog[tool]['layer']}. 职责：{duty}。非职责：{exclusion}。

Business invariants: targets keep their normalized quantity for the same version; newer CTA targets supersede earlier unsubmitted legs. Stock order-plan persists normalization and requires an idempotency key. Cancel action REQUEST preserves live leaves and resources, REJECT clears only cancel_pending, CONFIRM cancels the remaining leaves and releases after bookkeeping. Omitted action retains the legacy synchronous mock confirmation. Use REQUEST explicitly for asynchronous simulations. Fill conflicts persist RECONCILE and block new submissions; valid recorded fills and queries remain available. Clearing RECONCILE requires the trusted runtime resolve_reconciliation boundary with independent evidence and CAS checks, not an agent tool. CTA reservation_policy defaults to UPPER_BOUND_V1; ORDER_PRICE_V1 is an explicit fixture policy, and fills exceeding the reserved budget (including retained leaves) do not match. These are local simulation contracts, not live broker callbacks.

Inputs are defined by [input schema](../assets/input.schema.json); outputs by [output schema](../assets/output.schema.json). Examples: [request](../assets/example.json), [success](../assets/success.json), [failure request](../assets/failure-request.json), [failure](../assets/failure.json). Success fixtures are executed by scripts/build_assets.py using a fresh initialized session and the legal prerequisite steps.

{'Persistent writes require idempotency_key. Same key and payload return the previous result; changed payload returns IDEMPOTENCY_CONFLICT.' if tool in WRITES else 'Read/calculation interface: does not mutate account, orders, fills or reservations.'}

{'Sequence: '+FLOW[tool]+'. Upper reuses the same domain functions as independently invoked Atomic tools.' if tool in FLOW else 'Single domain step only. Does not call an Upper workflow.'}

Preconditions: initialized simulation/account; configured fixture instrument; current order/account versions for applicable writes; persisted market event before recording fills; persisted fill before order/account application. Order registration remains PENDING_RESERVATION until reserve succeeds. Direct Atomic cancel must be followed by release. A pending fill blocks new plans, submissions and cancellation until order application and booking recover.

Recovery: retry using the original key for completed operations; use a new key after correcting a rejected request. Pending simulation results require a new key and the same bar/model with fail_after omitted. Do not treat ACCOUNTING_PENDING or RECOVERY_REQUIRED as completed execution. SQLite serializes reservations and capacity writes. All state is local mock state.

Errors include INVALID_REQUEST, IDEMPOTENCY_CONFLICT, STALE_ORDER_VERSION, STALE_SNAPSHOT, INSUFFICIENT_CASH, INSUFFICIENT_SELLABLE, INVALID_QUANTITY, INVALID_PRICE, UNSUPPORTED_RULE_PROFILE, ACCOUNTING_PENDING, MARKET_EVENT_NOT_FOUND and FILL_NOT_FOUND. No internal step needs manual approval.
''')
    write(ROOT/'plugin.json',dict(name='stock-execution-tools',version='0.1.0',description='Stock simulation: 6 Upper + 15 Atomic tools',skills=[dict(name=t,path='skills/'+t,entry='scripts/run.py') for t in TOOLS],mode='simulation_only'))
    write(ROOT/'contracts/catalog.json',catalog)
    write(ROOT/'stock_execution/contracts.json',contracts)
    for tool in TOOLS:
        folder=ROOT/'skills'/tool
        example=json.loads((folder/'assets/example.json').read_text(encoding='utf-8'))
        success=success_example(tool,example,samples,sample_fixture)
        write(folder/'assets/success.json',success)
        failure_request=dict(example,simulation_id='does-not-exist')
        write(folder/'assets/failure-request.json',failure_request)
        schema=json.loads((folder/'assets/output.schema.json').read_text(encoding='utf-8'))
        shape=result_schema(success['data'])
        if tool=='order-cancel':
            shape['properties']['release']={'anyOf':[shape['properties']['release'],{'type':'null'}]}
        if tool=='execution-match':
            shape={'anyOf':[shape,obj(dict(quantity={'const':0},reason=S))]}
        if tool=='execution-simulate':
            shape={'anyOf':[shape,obj(dict(commit_status={'enum':['ACCOUNTING_PENDING','RECOVERY_REQUIRED']},failed_step=S,retryable={'const':True}))]}
        schema['oneOf'][0]['properties']['data']=shape
        write(folder/'assets/output.schema.json',schema)
    for tool in TOOLS:
        shutil.copytree(ROOT/'stock_execution',ROOT/'skills'/tool/'scripts/stock_execution',dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__'))
    from build_cta_assets import main as build_cta
    build_cta()


if __name__=='__main__': main()
