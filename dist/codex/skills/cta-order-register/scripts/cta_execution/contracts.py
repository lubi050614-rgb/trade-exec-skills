"""Single maintained source for all CTA input contracts."""
from .engine import TOOLS, WRITES

S=dict(type='string',minLength=1)
DEC=dict(type='string',pattern=r'^-?[0-9]+(\.[0-9]+)?$')
I=dict(type='integer')
P=dict(type='integer',minimum=1)
N=dict(type='integer',minimum=0)


def obj(fields,optional=()):
    return dict(type='object',properties=fields,required=[k for k in fields if k not in optional],additionalProperties=False)


BAR=obj(dict(event_id=S,contract_id=S,multiplier=P,volume_unit={'const':'lots'},frequency={'enum':['1m','1d']},trade_date=S,start_at=S,end_at=S,open=DEC,high=DEC,low=DEC,close=DEC,volume=N,tradable=dict(type='boolean'),price_limit_clear=dict(type='boolean'),price_basis={'const':'UNADJUSTED'},synthetic={'const':True},source=S))
PLAN=dict(contract_id=S,target_net_lots=I,target_id=S,target_version=P,account_version=P,as_of=S,reference_price=DEC,buffer=DEC)
LEG=dict(leg_id=S,account_version=P,submitted_at=S,order_type={'enum':['LIMIT','MARKET']},protection_price=DEC)
ORDER=dict(order_id=S,expected_version=P)
MATCH=dict(order_id=S,bar=BAR,participation_rate=DEC,slippage=DEC)
SETTLE=dict(trade_date=S,settlement_version=P,as_of=S,prices=dict(type='array',items=obj(dict(contract_id=S,prev_settlement_price=DEC,settlement_price=DEC))))
FIELDS={
 'cta-order-plan':PLAN,'cta-order-precheck':LEG,'cta-order-submit':dict(LEG,client_order_id=S),
 'cta-order-cancel':dict(ORDER,action={'enum':['REQUEST','CONFIRM','REJECT']}),'cta-execution-simulate':dict(bar=BAR,visible_at=S,participation_rate=DEC,slippage=DEC,fail_after={'enum':['record','state','book','release']}),
 'cta-order-query':dict(order_id=S),'cta-daily-settle':SETTLE,
 'cta-roll-plan':dict(roll_id=S,old_contract_id=S,new_contract_id=S,lots=P,old_reference_price=DEC,new_reference_price=DEC,account_version=P,as_of=S,buffer=DEC),
 'cta-contract-spec':dict(contract_id=S,trade_date=S),'cta-trading-session':dict(contract_id=S,timestamp=S),
 'cta-position-gap':dict(contract_id=S,target_net_lots=I,target_id=S,target_version=P),
 'cta-offset-split':dict(contract_id=S,trade_date=S,gap_lots=I),
 'cta-order-rule-check':LEG,
 'cta-margin-calculate':dict(contract_id=S,trade_date=S,price=DEC,lots=N,position_side={'enum':['LONG','SHORT']}),
 'cta-fee-calculate':dict(contract_id=S,trade_date=S,price=DEC,lots=N,offset={'enum':['OPEN','CLOSE','CLOSE_TODAY','CLOSE_YESTERDAY']}),
 'cta-order-register':dict(LEG,client_order_id=S),'cta-order-release':ORDER,'cta-order-match':MATCH,
 'cta-fill-record':dict(ORDER,fill_id=S,event_id=S),
 'cta-order-state-update':dict(ORDER,event_type={'enum':['FILL','CANCEL']},fill_id=S),
 'cta-fill-book':dict(fill_id=S),'cta-order-detail':dict(order_id=S),'cta-settlement-apply':SETTLE,
 'cta-roll-progress':dict(roll_id=S)}
OPTIONAL={'cta-order-cancel':('action',),'cta-order-plan':('buffer',),'cta-roll-plan':('buffer',),'cta-execution-simulate':('fail_after',),'cta-order-state-update':('fill_id',)}
for t in ('cta-order-precheck','cta-order-submit','cta-order-rule-check','cta-order-register'):
    OPTIONAL[t]=('order_type','protection_price')


def schemas():
    result={}
    for tool in TOOLS:
        fields=dict(schema_version={'const':'1.0'},request_id=S,simulation_id=S,account_id=S,asset_class={'const':'FUTURES'},data=obj(FIELDS[tool],OPTIONAL.get(tool,())),idempotency_key=S)
        result[tool]=dict(obj(fields,() if tool in WRITES else ('idempotency_key',)),**{'$schema':'https://json-schema.org/draft/2020-12/schema'})
    return result
