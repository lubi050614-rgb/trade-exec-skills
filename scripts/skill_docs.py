"""Render Chinese skill guides from the maintained interface schemas and catalog."""
import argparse
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.stock_upper_skills import UPPER as STOCK_UPPER
from scripts.cta_tool_layers import metadata as cta_metadata


# These explain domain meaning; types, required fields and ranges come from schemas.
LABELS = dict(line.split('|', 1) for line in '''
accepting|当前会话是否接受新委托
account|当前权威模拟账户快照
account_id|模拟账户标识，必须与初始化会话一致
account_snapshot_id|账户快照标识，使用当前账户版本对应的快照
account_version|当前账户版本，用于并发校验；从最新账户快照读取
accounting_status|成交记账状态，检查是否仍待入账
action|撤单动作：REQUEST 发起等待，CONFIRM 确认，REJECT 拒绝
actual_long_lots|当前多头持仓手数
actual_net_lots|当前净持仓手数，多头为正、空头为负
actual_quantity|当前实际持仓股数
actual_short_lots|当前空头持仓手数
amount|行情成交金额
as_of|账户快照或本次业务的基准时点，须与当前会话相符
asset_class|资产类别，期货接口固定为 FUTURES
available_cash|扣除冻结后的可用现金
average_price|订单累计成交均价；成交后可能出现
balance|模拟账户账面余额
bar|已完成的模拟行情，标的、频率与当前会话一致
board|模拟证券板块
bucket|持仓所属今仓或昨仓桶
buffer|额外预留现金缓冲
buy_quantity|尚在挂单的买入剩余股数
cancel_pending|是否正在等待撤单确认
canceled_lots|已撤销手数
canceled_quantity|已撤销股数；撤单结果中可表示本次撤销量
cash|现金需求或预留现金金额
cash_balance|模拟账户实际现金余额
cash_buffer|计划要求保留的现金缓冲
charged_fee|该订单此前已收取的累计费用
claims|平仓占用的持仓批次及手数
client_order_id|唯一业务委托号，同一业务重试保持不变
close|行情收盘价
close_priority|今仓与昨仓的平仓优先顺序
closed_old_lots|旧合约实际已成交并记账的平仓手数
closing_equity|本次结算后的账户权益
code|错误类别
commit_status|业务提交状态；COMMITTED 表示本接口的状态已持久化，不等于订单成交
complete|换月是否已经按实际成交与记账完成
completed_steps|已完成的处理步骤
conflicting_order_ids|与新目标冲突的活动订单标识
contract_id|显式配置的模拟期货合约标识
coverage|目标覆盖范围，固定 FULL，包含当前持仓及活动挂单标的
cumulative_notional|该订单此前累计成交金额
currency|模拟账户币种
current_weight|当前持仓市值占总资产的权重，用于校验账户快照
data|业务请求或成功结果对象
dependencies|开仓前必须完成成交并记账的平仓依赖
depends_on_close|本指令是否依赖先完成平仓
details|错误附加信息，按错误类别解释
direction|调仓方向
disclaimer|模拟规则适用范围说明
drafts|可供预检或提交的订单草稿，空数组表示无需委托
end_at|行情结束时点，使用带 +08:00 时区的时间
end_of_day|是否在事件结束后处理到期 DAY 订单
equity|模拟期货账户权益
error|失败时返回的错误对象
estimated_buy_cost|预计买入总支出，包含费用
estimated_post_trade_cash|假设计划成交后的现金估计值，尚未记账
estimated_sell_proceeds|预计卖出净收入，尚未成交时不可提前使用
event_id|已持久化行情事件标识；行情对象内为本事件唯一标识
event_type|订单状态更新事件：FILL 为成交，CANCEL 为撤销
exchange|模拟交易所标识
executed_at|成交执行时点
expected_version|当前订单版本，用于比较并更新，须先查询最新版本
fail_after|测试专用故障注入点，正常调用省略
failed_step|中断或失败的处理步骤
fee|本次增量费用或费用计算结果
fees|按开平类型配置的费用规则
fill_id|持久化成交的唯一标识；登记时指定，后续应用和记账复用
filled_lots|订单累计已成交手数
filled_quantity|订单累计已成交股数
fills|逐笔成交及其处理状态
floating_pnl|当前浮动盈亏
frequency|会话行情频率：1m 或 1d
frozen_cash|当前冻结现金
frozen_sell_quantity|已被卖单冻结的持仓股数
funding_sufficient|预计交易后现金是否满足现金缓冲要求
gap|净缺口计算结果
gap_lots|扣除活动开平指令后的有符号净手数缺口
hash|持久化输入或状态的摘要
high|行情最高价
holding_pnl|本交易日持仓盯市盈亏
idempotency_key|持久化操作的幂等键；相同键及载荷返回原结果，改动载荷须使用新键
incremental_booking_adjustment|本次结算实际入账的增量调整，避免重复记入已有盈亏
instrument_id|会话规则中配置的模拟股票标识
leaves_lots|订单尚未成交或撤销的剩余手数
leaves_quantity|订单尚未成交或撤销的剩余股数
leg_id|已持久化计划腿的标识，从计划结果读取
leg_ids|已持久化计划腿标识列表
legs|按先平后开顺序拆分的指令或计划腿
limit|每页最多返回的成交条数
limit_price|限价委托价格
lot_id|持仓批次标识
lot_step|委托手数步长
lots|整数手数
low|行情最低价
lower_price|模拟规则允许的价格下界
margin|保证金金额或保证金规则
margin_mode|保证金模式：RATE 按比例，FIXED 按每手固定金额
margin_shortfall|保证金不足金额
market_event_id|成交所依据的持久化行情事件标识
message|具体错误原因
min_lots|最小委托手数
mode|费用或保证金计算模式
model_version|撮合模型版本
multiplier|合约乘数，必须与当前合约规则一致
net_deposits|累计净入金
new_contract_id|换月目标新合约标识
new_plan_id|新合约开仓计划标识
new_reference_price|新合约计划参考价
next_offset|下一页成交偏移量，null 表示没有下一页
next_trade_date|完成日结后迁移到的下一交易日
normalization|目标数量取整结果及权重偏差
notional|名义金额；费用计算入参中为本次成交金额
offset|期货开平类型；股票成交分页入参中为从零开始的偏移量
ok|成功为 true，失败为 false
old_contract_id|需要平仓的旧合约标识
old_plan_id|旧合约平仓计划标识
old_reference_price|旧合约计划参考价
open|行情开盘价
opened_new_lots|新合约实际已成交并记账的开仓手数
opening_equity|本次结算前账户权益
order|订单草稿、当前订单或经校验的委托对象
order_applied|成交是否已经应用到订单数量与状态
order_id|已登记订单标识，从提交或登记结果读取
order_type|委托类型：LIMIT 限价，MARKET 市价保护
order_version|当前订单版本
orders|本次查询涉及的订单列表
original_lots|订单原始委托手数
participation_rate|本事件可参与成交量的比例，按会话共享容量约束
pending_close_lots|活动平仓订单剩余手数
pending_open_lots|活动开仓订单剩余手数
phase|当前交易时段，例如日盘或夜盘
plan_id|持久化调仓计划标识
position_margin|当前持仓占用保证金
position_side|保证金计算的持仓方向：LONG 或 SHORT
positions|按标的保存的当前持仓与批次信息
prev_settlement_price|显式提供的上一结算价
previous_settlement|合约规则配置的历史结算价
price|价格或模拟成交价
price_as_of|参考价对应时点，须与快照及允许的时效一致
price_basis|价格口径，固定 UNADJUSTED，使用未复权价格
price_limit_clear|行情是否满足模拟涨跌停可成交条件
price_source|参考价来源
price_tick|最小价格变动单位
prices|逐合约提供上一结算价与本次结算价
product|模拟期货品种标识
profile_id|模拟规则配置标识，仅使用 simulation_fixture
profile_version|规则配置版本
protection_price|市价委托保护价，MARKET 时必须提供
quantity|整数股数
raw_target_quantity|按目标权重计算、尚未取整的目标股数
realized_pnl|已经确认的平仓盈亏
reason|本次未成交或未生成动作的原因
reconciliation_status|账户对账状态，未完成时先处理恢复或对账
reference_price|用于目标换算或计划的显式参考价
release|资源释放结果，未发生释放时可能为 null
release_pending|是否仍存在待释放资源
released_cash|本次实际释放的现金
remaining_cash|处理后仍需保留的冻结现金
remaining_claims|处理后仍需保留的平仓批次占用
remaining_new_lots|新合约尚需开仓的手数
remaining_old_lots|旧合约尚需平仓的手数
remaining_quantity|处理后仍需冻结的股数
request_id|本次请求标识，响应原样返回以便追踪
required_cash|委托需要的现金或保证金及费用
required_quantity|卖单需要的可卖股数
requires_sell_proceeds|买入是否依赖卖出收入；为 true 时须等待卖出实际入账
reserved_cash|订单当前预留现金
reserved_consumption|本次成交实际消耗的预留资源金额
reserved_quantity|订单当前冻结股数
resources|委托需要的现金、保证金或可平仓资源
retained_order_ids|继续计入目标缺口的兼容活动订单标识
retryable|错误或中断是否支持按恢复条件重试
risk_status|模拟账户风险状态
roll_id|换月业务唯一标识
rounding_weight_deviation|按规则取整引入的权重偏差
rule_version|本次使用的规则版本
schema_version|请求和响应协议版本，固定为 1.0
sell_quantity|尚在挂单的卖出剩余股数
sellable_quantity|扣除冻结后的可卖股数
separate_close|是否区分平今与平昨
sequence|订单优先级序号
settled_quantity|已完成交收的持仓股数
settlement_price|本交易日显式结算价
settlement_version|日结版本，同日重复或冲突结算按版本及输入校验
side|买卖方向：BUY 或 SELL
simulation_id|本地模拟会话标识，必须与初始化会话一致
slippage|撮合使用的显式价格滑点
snapshot_id|当前账户快照标识
source|模拟行情来源
source_hash|原始事件或请求载荷摘要
start_at|行情开始时点，使用带 +08:00 时区的时间
status|订单或业务当前状态
strategy|计划采用的执行策略
submitted_at|委托时点，使用带 +08:00 时区的时间并通过交易时段检查
synthetic|是否为合成模拟行情
target_cash_weight|完整目标组合中现金的目标权重
target_id|目标业务标识，同一目标版本保持规范化数量不变
target_net_lots|目标净手数，多头为正、空头为负、零为清仓
target_quantity|规则取整后的目标持仓股数
target_version|目标版本；改变目标必须增加版本
target_weight|目标持仓权重，零表示清仓
targets|完整目标清单，必须覆盖当前持仓及活动挂单
time_in_force|委托有效期，当前使用 DAY
timestamp|待解析的显式日历时点，包含 +08:00 时区
total|符合查询条件的成交总条数
total_assets|当前账户总资产，须与持仓估值及现金一致
tradable|本行情是否允许模拟交易
trade_date|会话日历中的交易日，夜盘不按自然日期推断
trade_dates|显式配置的可交易日期
unconnected_lots|旧仓平仓与新仓开仓之间尚未衔接的敞口手数
unsettled|尚未完成交收的持仓明细
upper_price|模拟规则允许的价格上界
valid|规则或资源校验是否通过
valuation_price|账户持仓估值价
version|当前对象版本
visible_at|行情对本次模拟可见的时点，不能早于行情完成时点
volume|行情成交量；股票单位为股，期货单位为手
volume_unit|期货行情成交量单位，固定 lots
warnings|成功响应中的提示列表，可能为空
weight_tolerance|当前权重与账户计算值之间允许的偏差
'''.strip().splitlines())

STOCK_TITLES = dict(zip(
    ['order-open-quantity', 'order-target-gap', 'order-rule-check', 'execution-fee-calculate',
     'order-resource-check', 'order-register', 'order-reserve', 'order-state-read',
     'order-cancel-remainder', 'order-release-reserve', 'execution-match',
     'execution-fill-record', 'order-apply-fill', 'account-apply-fill', 'execution-fill-list'],
    ['查询在途股数', '计算目标股数缺口', '检查委托规则', '计算成交费用', '检查委托资源',
     '登记订单', '预留订单资源', '读取订单状态', '撤销订单剩余量', '释放多余预留',
     '计算模拟成交候选', '登记模拟成交', '应用成交到订单', '成交账户记账', '查询成交列表']))

CTA_PURPOSES = {
    'cta-order-plan': '按整数目标净手数生成并持久化先平后开的调仓计划，不提交订单或冻结资源。',
    'cta-order-precheck': '读取最新合约、时段、计划依赖与账户资源，检查计划腿能否提交，不冻结资源。',
    'cta-order-submit': '重新校验已持久化的计划腿，在同一事务内登记订单并冻结资源。',
    'cta-order-cancel': '按当前版本撤销订单剩余手数并释放资源，保留已成交部分。',
    'cta-execution-simulate': '推进一根已完成的期货行情，编排撮合、成交登记、订单更新、记账与释放。',
    'cta-order-query': '查询订单、成交、资源占用及账户对账状态，不修改业务状态。',
    'cta-daily-settle': '使用显式结算价进行每日盯市与交易日迁移，处理到期委托。',
    'cta-roll-plan': '持久化关联的旧合约平仓与新合约开仓计划，计划数量不代表实际成交进度。',
    'cta-contract-spec': '读取指定合约及交易日的模拟合约规格、保证金与手续费规则。',
    'cta-trading-session': '根据显式日历将输入时点解析为交易日及交易时段，包含夜盘归属。',
    'cta-position-gap': '读取多空持仓及活动开平指令，计算有符号的净手数缺口。',
    'cta-offset-split': '按平仓优先级拆分方向、平今、平昨和剩余开仓手数，不登记订单。',
    'cta-order-rule-check': '读取权威规则及账户资源，校验已持久化计划腿，不冻结资源。',
    'cta-margin-calculate': '按显式 RATE 或 FIXED 规则计算保证金和名义金额，不进行记账。',
    'cta-fee-calculate': '根据显式开平类型，按每手或名义金额规则计算增量手续费。',
    'cta-order-register': '重新校验计划腿，在同一事务内登记订单并冻结现金或可平仓资源。',
    'cta-order-release': '根据持久化剩余手数与成交记账事实释放多余占用，不接受任意释放量。',
    'cta-order-match': '按开盘价、价格边界与共享容量计算保守成交候选，不占容量或记账。',
    'cta-fill-record': '读取持久化行情并重算成交，原子登记成交及占用容量，不推进账户记账。',
    'cta-order-state-update': '将持久化成交或带版本的撤单应用到订单数量，不进行账户记账。',
    'cta-fill-book': '对已应用到订单的持久化成交幂等记账，处理费用、已实现盈亏及持仓批次。',
    'cta-order-detail': '读取订单、成交、资源预留及记账状态，不修改业务状态。',
    'cta-settlement-apply': '只入账每日持仓盈亏的增量，并将持仓桶迁移至下一交易日，防止重复日结。',
    'cta-roll-progress': '读取旧合约实际平仓、新合约实际开仓及尚未衔接的敞口手数。',
}

DEFAULTS = {'weight_tolerance': '0.000001', 'cash_buffer': '0', 'buffer': '0',
            'offset': '0', 'limit': '100', 'cumulative_notional': '0',
            'charged_fee': '0', 'end_of_day': 'false', 'action': 'CONFIRM',
            'order_type': 'LIMIT'}


def merged(schema):
    """Union result alternatives for documentation without altering the contract."""
    if not any(k in schema for k in ('anyOf', 'oneOf')):
        return schema
    result = dict(schema)
    properties = dict(schema.get('properties', {}))
    for option in schema.get('anyOf', schema.get('oneOf', [])):
        option = merged(option)
        for key, value in option.get('properties', {}).items():
            properties.setdefault(key, value)
    result['properties'] = properties
    return result


def json_type(schema):
    if 'type' in schema:
        value = schema['type']
        if isinstance(value, list):
            return ' / '.join(value)
        if value == 'array':
            return 'array of ' + json_type(schema['items']) if schema.get('items') else 'array'
        return value
    if 'const' in schema:
        v = schema['const']
        return 'boolean' if isinstance(v, bool) else 'integer' if isinstance(v, int) else 'string'
    if 'enum' in schema:
        return 'string'
    alternatives = schema.get('anyOf', schema.get('oneOf', []))
    return ' / '.join(dict.fromkeys(json_type(s) for s in alternatives)) if alternatives else '由契约定义'


def meaning(key, schema, tool, path, is_input):
    text = LABELS[key]
    if not is_input and key == 'ok':
        return LABELS[key]
    if key == 'offset' and not tool.startswith('cta-'):
        text = '成交分页偏移量，从 0 开始' if 'fill-list' in tool or tool == 'order-query' else text
    if key == 'fill_id' and tool == 'cta-order-state-update' and is_input:
        text += '；event_type=FILL 时必填，CANCEL 时省略'
    if key == 'limit_price' and is_input:
        text += '；order_type=LIMIT 时必填'
    if key == 'lots' and tool.endswith('order-match') and not is_input:
        text += '；0 表示未成交，此时返回 reason'
    if key == 'quantity' and tool == 'execution-match' and not is_input:
        text += '；0 表示未成交，此时返回 reason'
    if 'const' in schema:
        text += '；固定值 `' + json.dumps(schema['const'], ensure_ascii=False) + '`'
    elif 'enum' in schema:
        text += '；取值 ' + '、'.join('`' + str(v) + '`' for v in schema['enum'])
    if 'minimum' in schema:
        text += f"；最小值 {schema['minimum']}"
    if 'pattern' in schema:
        text += '；十进制字符串'
    if is_input and schema.get('type') == 'object' and schema.get('additionalProperties') is False:
        text += '；仅接受下列契约字段'
    return text.replace('|', '\\|').replace('\n', ' ')


def rows(schema, tool, prefix='', is_input=True, depth=0):
    schema = merged(schema)
    required = schema.get('required', [])
    for key, child in schema.get('properties', {}).items():
        path = prefix + key
        requirement = '必填' if key in required else '可选'
        if not prefix and key == 'idempotency_key' and key not in required:
            requirement = '可选（只读接口）'
        if is_input and key not in required and key in DEFAULTS:
            requirement += '，默认 `' + DEFAULTS[key] + '`'
        if is_input and key == 'fill_id' and tool == 'cta-order-state-update':
            requirement = '条件必填'
        if is_input and key in ('limit_price', 'protection_price'):
            requirement = '条件必填'
        description = meaning(key, child, tool, path, is_input)
        if is_input:
            yield f'| `{path}` | {json_type(child)} | {requirement} | {description} |'
        else:
            yield f'| `{path}` | {json_type(child)} | {description} |'
        nested = child.get('items', {}) if child.get('type') == 'array' else child
        nested = merged(nested)
        # Account/contract snapshots are extensible; keep their large trees in the schema.
        expand = is_input or (depth < 2 and key not in ('account', 'positions', 'fees', 'previous_settlement'))
        if expand and nested.get('properties'):
            suffix = '[].' if child.get('type') == 'array' else '.'
            yield from rows(nested, tool, path + suffix, is_input, depth + 1)


def context(tool):
    if tool.startswith('cta-'):
        meta = cta_metadata(tool)
        return meta['title'], CTA_PURPOSES[tool]
    if tool in STOCK_UPPER:
        return STOCK_UPPER[tool][1], STOCK_UPPER[tool][3]
    contract = (ROOT/'skills'/tool/'references/contract.md').read_text(encoding='utf-8')
    duty = re.search(r'职责：(.*?)。非职责：(.*?)。', contract)
    if not duty:
        raise ValueError(f'Missing responsibility: {tool}')
    return STOCK_TITLES[tool], duty[1] + '；' + duty[2] + '。'


def render(tool, catalog):
    folder = ROOT/'skills'/tool
    load = lambda name: json.loads((folder/'assets'/name).read_text(encoding='utf-8'))
    request, response = load('input.schema.json'), load('output.schema.json')
    title, purpose = context(tool)
    cta = tool.startswith('cta-')
    domain = '期货' if cta else '股票'
    when = f'需要在本地{domain}模拟会话中{title}时使用。'
    meta = catalog[tool]
    version = '0.2.0' if cta else '0.1.0'
    sections = [f'''---
name: {tool}
description: {purpose} 仅用于本地{domain}模拟。
when_to_use: {when}
version: {version}
entry: scripts/run.py
allowed_tools:
  - skill_run_script
---

# {title}

{purpose}

层级：{meta['layer']}；业务编号：{meta['id']}。调用时使用完整名称 `{tool}`，编号仅作业务映射。仅操作本地模拟账户及 `simulation_fixture` 规则，不接入真实账户或推断生产规则。
''']
    if cta:
        sections.append('期货请求必须显式指定 `asset_class=FUTURES`，数量使用整数手，目标使用有符号净手数。合约、交易日、开平类型及数量必须明确，不能用股票权重代替。\n')
    if tool in STOCK_UPPER:
        sections.extend([STOCK_UPPER[tool][4] + '\n', STOCK_UPPER[tool][5] + '\n'])
    sections.append('''## 输入参数

参数位于 JSON 请求信封及其 `data` 对象中，下表使用完整字段路径；数组子项以 `[]` 表示。嵌套字段的必填要求在所属对象出现时适用。以[输入契约](assets/input.schema.json)为准，填写前核对[业务契约](references/contract.md)和[请求示例](assets/example.json)。

| 字段 | JSON 类型 | 必填 | 取值与含义 |
| --- | --- | --- | --- |''')
    sections.append('\n'.join(rows(request, tool)))
    sections.append('金额和价格使用十进制字符串，时间使用带 `+08:00` 时区的显式时间。示例中的账户、标的、订单号和版本只适用于对应示例会话，实际调用须从当前会话读取。')
    db = 'cta.sqlite' if cta else 'simulation.sqlite'
    sections.append(f'''## 调用

在技能目录中调用，关联步骤始终使用同一个数据库路径：

```text
skill_run_script {{ skill: "{tool}", script: "scripts/run.py", args: ["--db", "{db}", "--input", "assets/example.json"] }}
```

没有 `skill_run_script` 时，通过 Python 3.11 或以上版本直接执行相同入口：

```bash
python scripts/run.py --db {db} --input assets/example.json
```

`--input` 指向完整请求 JSON 文件；省略时从标准输入读取 JSON。首次建立新会话时附加 `--init <session.json>`；已有会话后续调用省略 `--init`。可用初始化文件来自项目的 `{'examples/cta/long/session.json` 或 `examples/cta/short/session.json' if cta else 'examples/SSE/session.json`、`examples/SZSE/session.json` 或 `examples/BSE/session.json'}`。先核对输入引用的账户及资源是否存在，仅初始化账户不会自动生成订单或成交。

运行依赖打包在本技能的 `scripts/` 中，运行条件见 [runtime.json](assets/runtime.json)。stdout 返回一个 JSON 信封；退出码 0 表示 `ok=true`，退出码 1 表示错误信封。''')
    if cta:
        sections.append(f'需要订单、计划腿或成交前置状态的示例，应从项目根目录运行 `python scripts/replay_cta_example.py --tool {tool}`，脚本在独立临时数据库中装载本技能的 [prepared-state.json](assets/prepared-state.json) 后执行真实入口。该文件是可信测试夹具，不能作为公开交易接口的输入，也不能隐式借用其他技能的账户状态。')
    else:
        sections.append('涉及订单的示例必须先执行合法的提交或登记步骤；涉及成交应用和记账时，先有持久化行情与成交。单独的请求示例不负责创建这些前置状态。')
    if meta['write']:
        sections.append('本接口持久化状态，必须提供非空 `idempotency_key`。完成操作重试保留原键和完全相同的载荷；同键改载荷返回 `IDEMPOTENCY_CONFLICT`。`order-plan` 仅保存规范化目标和幂等结果，不提交订单或冻结资源。' if tool == 'order-plan' else '本接口持久化状态，必须提供非空 `idempotency_key`。完成操作重试保留原键和完全相同的载荷；同键改载荷返回 `IDEMPOTENCY_CONFLICT`。纠正被拒绝的请求后使用新键。')
    else:
        sections.append('本接口只读或只计算，不隐式修改账户、订单、成交或冻结资源。')
    sections.append('''## 输出参数

成功与失败的完整结构见[输出契约](assets/output.schema.json)，并可对照[成功响应](assets/success.json)和[失败响应](assets/failure.json)。业务字段随成功路径、订单生命周期或中断阶段出现；下表汇总各分支，不表示所有字段总会同时返回。可扩展账户、规则及持仓对象的详细结构以契约和实际快照为准。

| 字段 | JSON 类型 | 出现条件与含义 |
| --- | --- | --- |''')
    branches = response.get('oneOf', [response])
    success = branches[0]
    sections.append('\n'.join(rows(success, tool, is_input=False)))
    if len(branches) > 1:
        error = branches[1].get('properties', {}).get('error', {})
        sections.append('\n'.join(rows({'properties': {'error': error}}, tool, is_input=False)))
    sections.append('先检查 `ok`；失败时读取 `error.code/message/details`，结合 `retryable` 和业务契约处理。若 `data.commit_status` 为 `ACCOUNTING_PENDING` 或 `RECOVERY_REQUIRED`，即使 `ok=true` 也未完成，须先恢复后再推进依赖交易。`COMMITTED` 仅表示当前接口的操作完成。')
    sections.append('## 执行约束\n')
    if cta:
        sections.append('提交或登记前须存在持久化计划腿，账户版本为当前版本；依赖平仓的开仓腿须等平仓全部成交并记账。登记和冻结在同一事务内完成。日结使用显式上一结算价及本次结算价，避免重复入账与重复迁移。')
        if tool in ('cta-order-cancel', 'cta-order-state-update'):
            sections.append('撤单 REQUEST 只标记等待，保留剩余手数和冻结；REJECT 清除等待标记；CONFIRM（默认）确认剩余撤销并按契约释放。直接以 `cta-order-state-update` 执行 CANCEL 后，必须再用 `cta-order-release` 释放资源。成交已发生的部分不能撤回。' if tool == 'cta-order-cancel' else 'event_type=FILL 时必须提供已登记的 fill_id；CANCEL 只更新订单数量，随后必须调用 cta-order-release 释放资源，不能将订单状态更新当作账户记账。')
        sections.append('成交前先持久化行情，再按登记成交 → 更新订单 → 成交记账 → 释放资源恢复。撮合候选本身不占用容量。默认预留策略为 `UPPER_BOUND_V1`，`ORDER_PRICE_V1` 仅可由显式夹具配置；成交及剩余委托不得超出预留预算。')
    else:
        sections.append('账户及证券规则须已初始化；涉及更新时读取当前订单和账户版本。登记订单为 `PENDING_RESERVATION`，预留成功后才激活。直接撤销剩余量后须调用 `order-release-reserve`；登记成交前须有持久化行情，应用及记账前须有持久化成交。')
    sections.append('待记账成交会阻止依赖交易。中断的模拟使用相同 bar/model、新的幂等键并去掉 fail_after 恢复；原键仍返回原中断响应。成交冲突导致 RECONCILE 时停止新提交，由可信运行时依据独立证据及版本校验完成对账，不能通过工具自行清除。详细前置条件、执行顺序和错误码见[业务契约](references/contract.md)。')
    atoms = meta.get('atomic_tools', [])
    if atoms:
        sections.append('## 可独立使用的原子工具\n\n以下为业务职责分解，包含间接复用的计算；不表示每次调用均逐项执行。Upper 入口已负责流程编排，一般无需调用者逐一执行。独立调用时仍须满足各工具自身的前置状态。\n')
        for atom in atoms:
            atom_title, atom_purpose = context(atom)
            sections.append(f'- [{atom}](../{atom}/SKILL.md)：{atom_title}。{atom_purpose}')
    else:
        parents = [name for name, item in catalog.items() if tool in item.get('atomic_tools', [])]
        sections.append('## 相关上层工具\n\n本技能执行单个领域步骤，不调用 Upper 工作流。' + ('完整流程可按需求使用：\n\n' + '\n'.join(f'- [{p}](../{p}/SKILL.md)：{context(p)[0]}。' for p in parents) if parents else '该步骤可独立使用，或按业务契约接入相关流程。'))
    # Consecutive table/list rows need one newline; logical blocks need a blank line.
    text = '\n\n'.join(sections).replace('| --- | --- | --- | --- |\n\n|', '| --- | --- | --- | --- |\n|').replace('| --- | --- | --- |\n\n|', '| --- | --- | --- |\n|')
    text = text.replace('\n\n- [', '\n- [')
    text = re.sub(r'(\|[^\n]*\|)\n\n(?=\| `error`)', r'\1\n', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    # Preserve CommonMark separation before the first item of each list.
    text = text.replace('前置状态。\n- [', '前置状态。\n\n- [')
    text = text.replace('按需求使用：\n- [', '按需求使用：\n\n- [')
    return text.rstrip() + '\n'


def build_docs(tools=None):
    catalog = json.loads((ROOT/'contracts/catalog.json').read_text(encoding='utf-8'))
    for tool in tools or catalog:
        (ROOT/'skills'/tool/'SKILL.md').write_text(render(tool, catalog), encoding='utf-8')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sync-copies', action='store_true', help='Update existing Codex and local SKILL.md copies only')
    args = parser.parse_args()
    build_docs()
    if args.sync_copies:
        from scripts.package import codex_skill
        for source in (ROOT/'skills').glob('*/SKILL.md'):
            for base in (ROOT/'dist/codex/skills', ROOT/'.agents/skills'):
                target = base/source.parent.name/'SKILL.md'
                if target.exists():
                    try:
                        target.write_text(codex_skill(source.read_text(encoding='utf-8')), encoding='utf-8')
                    except PermissionError:
                        raise PermissionError(f'Cannot update protected skill copy: {target}') from None
    print('Rendered 45 skill guides' + (' and synchronized existing copies.' if args.sync_copies else '.'))
