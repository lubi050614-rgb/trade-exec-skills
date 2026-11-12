"""CTA business-layer identifiers from CTA_tool_list.png, scoped to FUTURES."""

ATOMIC = [
    ('cta-contract-spec', '查合约规则'),
    ('cta-trading-session', '判交易日和时段'),
    ('cta-position-gap', '算持仓缺口'),
    ('cta-offset-split', '拆开平指令'),
    ('cta-order-rule-check', '检查委托'),
    ('cta-margin-calculate', '算保证金'),
    ('cta-fee-calculate', '算手续费'),
    ('cta-order-register', '登记并冻结'),
    ('cta-order-release', '释放冻结'),
    ('cta-order-match', '模拟撮合'),
    ('cta-fill-record', '登记成交'),
    ('cta-order-state-update', '更新订单状态'),
    ('cta-fill-book', '成交记账'),
    ('cta-order-detail', '读订单明细'),
    ('cta-settlement-apply', '结转交易日'),
    ('cta-roll-progress', '查换月进度'),
]

UPPER = {
    'cta-order-plan': ('U1', '生成调仓计划', [1, 2, 3, 4]),
    'cta-order-precheck': ('U2', '下单前检查', [1, 2, 5, 6, 7]),
    'cta-order-submit': ('U3', '提交订单', [5, 6, 7, 8]),
    'cta-order-cancel': ('U4', '撤销余单', [9, 12, 14]),
    'cta-execution-simulate': ('U5', '模拟成交并记账', [1, 2, 6, 7, 9, 10, 11, 12, 13]),
    'cta-order-query': ('U6', '查订单和成交', [14]),
    'cta-daily-settle': ('U7', '日终结算', [1, 2, 6, 15]),
    'cta-roll-plan': ('U8', '生成换月计划', [1, 2, 3, 4, 16]),
}


def metadata(tool):
    if tool in UPPER:
        number, title, atoms = UPPER[tool]
        return dict(id='CTA-'+number, title=title,
                    atomic_ids=['CTA-A'+str(i) for i in atoms],
                    atomic_tools=[ATOMIC[i-1][0] for i in atoms])
    index = next(i for i, (name, _) in enumerate(ATOMIC, 1) if name == tool)
    return dict(id='CTA-A'+str(index), title=ATOMIC[index-1][1])


def annotation(tool):
    item = metadata(tool)
    heading = f"{item['id']} {item['title']}"
    if tool in UPPER:
        mapping = '、'.join(f'CTA-A{i} `{ATOMIC[i-1][0]}`' for i in UPPER[tool][2])
        return f'''## {heading}

层级：Upper。对应 Atomic：{mapping}。

CTA 前缀区分期货与股票工具。编号仅用于说明对应关系；Agent 调用必须使用完整工具名 `{tool}`。对应关系表示业务职责的分解，包含间接复用的领域计算；实际执行顺序及前置条件见契约，不表示每次调用都会逐项执行所有 Atomic。
'''
    return f'''## {heading}

层级：Atomic。负责单个领域步骤。编号仅用于说明对应关系；Agent 调用必须使用完整工具名 `{tool}`。
'''
