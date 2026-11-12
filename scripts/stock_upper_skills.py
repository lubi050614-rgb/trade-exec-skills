"""Stock Upper skill instructions and globally unique STOCK-U / STOCK-A IDs."""

ATOMIC = [
    'order-open-quantity', 'order-target-gap', 'order-rule-check',
    'execution-fee-calculate', 'order-resource-check', 'order-register',
    'order-reserve', 'order-state-read', 'order-cancel-remainder',
    'order-release-reserve', 'execution-match', 'execution-fill-record',
    'order-apply-fill', 'account-apply-fill', 'execution-fill-list',
]

# Includes indirect domain calls, not just the top-level pipeline.
UPPER = {
    'order-plan': ('U1', '生成订单草稿', [1, 2],
        '输入完整目标权重、当前账户快照和参考价；读取当前持仓与已有挂单，计算每只股票还需买卖多少股。',
        '先核对 account_snapshot_id、as_of、total_assets 和 current_weight。targets 必须覆盖当前持仓及活动挂单；清仓标的用 target_weight=0 表达。按规则把目标权重转换为整数股数，再扣除在途买卖剩余量。差额为零不生成订单。同一 target_id/target_version 固定目标股数；改变目标权重必须增加版本。',
        'drafts 是可传给预检/提交的订单草稿；normalization 说明取整偏差。检查 funding_sufficient、requires_sell_proceeds 和 cash_buffer；依赖卖出收入时先等待实际成交入账，再用当前账户版本提交买单。计划本身不冻结资金或股票。'),
    'order-precheck': ('U2', '下单前检查', [3, 4, 5],
        '输入订单草稿，读取当前账户，检查委托规则、预计费用、可用资金和可卖股数。',
        'data.order 使用计划草稿或明确构造的订单，account_version 必须是当前版本。检查数量、价格、时段、在途冲突，再计算费用和资源需求。该接口只检查，不登记、不冻结；通过后提交时仍会重新校验。',
        '成功返回 required_cash、required_quantity、fee 和 account_version。失败返回 ok=false 与 error.code/details，例如 INSUFFICIENT_CASH、INSUFFICIENT_SELLABLE、INVALID_QUANTITY 或 STALE_SNAPSHOT；不要把失败当作可提交结果。'),
    'order-submit': ('U3', '提交订单', [3, 4, 5, 6, 7],
        '接收订单草稿，重新校验当时可用资源，登记订单并占用资金或股票；重复请求返回原结果。',
        'data.order 使用草稿，data.client_order_id 是唯一业务请求号。重新执行规则、费用及资源检查；登记为 PENDING_RESERVATION，预留成功后激活为 NEW。登记与预留在同一 SQLite 事务内，任一步失败整体回滚。每笔草稿分别提交，使用最新 account_version。',
        '返回 order、commit_status 和 completed_steps。重试必须保留原 idempotency_key、client_order_id 和完全相同的 data，返回原订单；修改请求使用新键，同一 client_order_id 不能用于另一笔订单。提交不代表成交。'),
    'order-cancel': ('U4', '撤销余单', [8, 9, 10],
        '输入订单号及预期版本，撤销尚未成交部分并释放相应资源，保留既有成交。',
        '先查询当前订单与 version。默认或 action=CONFIRM 同步确认撤单，撤销 leaves_quantity，随后释放剩余占用。异步模拟用 REQUEST 保留在途量和冻结；成交入账后重新查询，用最新 expected_version 执行 CONFIRM，或 REJECT 清除等待标记。',
        '确认撤销返回 order、release 和本次 canceled_quantity，已成交量不回退。REQUEST/REJECT 的 release=null，尚未确认撤销，也不返回本次撤销量。遇到 ACCOUNTING_PENDING 先恢复成交入账，再以当前版本撤单。'),
    'execution-simulate': ('U5', '模拟成交并记账', [4, 8, 10, 11, 12, 13, 14],
        '输入已完成行情，读取活动订单，按撮合规则计算价格、数量和费用，记录成交并更新订单、现金和持仓。',
        '明确 bar、visible_at、participation_rate 与 slippage；行情必须已完成、未复权且与会话频率一致。按订单优先级共享成交容量：读取订单 → 撮合 → 登记成交 → 更新订单 → 账户入账 → 释放多余占用。费用按订单累计金额计算增量，最低佣金不对每次部分成交重复收取；一笔成交只入账一次。',
        'COMMITTED 返回本事件 fills 和 account；没有成交时 fills 可以为空。ACCOUNTING_PENDING/RECOVERY_REQUIRED 表示未完成：保留相同 bar/model、换新 idempotency_key、去掉 fail_after 后恢复；旧键只会返回旧响应。fail_after 仅用于测试。end_of_day 会撤销并释放到期 DAY 单。'),
    'order-query': ('U6', '查询订单与成交', [8, 15],
        '输入订单号，返回委托量、已成交量、已撤数量、仍在挂单的数量和逐笔成交明细。',
        'data.order_id 指定订单，可用 offset/limit 分页读取成交。该接口读取订单现状及逐笔成交，不推进撮合或修复记账。',
        'order.quantity/filled_quantity/canceled_quantity/leaves_quantity 分别为委托、成交、撤销和剩余数量；order 还包含状态及版本。fills 返回数量、价格、费用与记账状态，返回 total 和 next_offset；用 next_offset 作为下一页 offset，为 null 时结束。account 是当前账户快照；ACCOUNTING_PENDING 表示账户仍有待记账成交。'),
}


def metadata(tool):
    if tool in UPPER:
        number, title, atoms, purpose, _, _ = UPPER[tool]
        return dict(id='STOCK-'+number, title=title, description=purpose,
                    atomic_ids=['STOCK-A'+str(i) for i in atoms],
                    atomic_tools=[ATOMIC[i-1] for i in atoms])
    return dict(id='STOCK-A'+str(ATOMIC.index(tool)+1))


def instructions(tool):
    number, title, atoms, purpose, steps, result = UPPER[tool]
    mapping = '、'.join(f'STOCK-A{i} `{ATOMIC[i-1]}`' for i in atoms)
    return f'''\n## STOCK-{number} {title}

{purpose}

对应 Atomic：{mapping}。这些步骤由脚本编排执行，无需让调用者逐个运行 Atomic。

编号仅用于说明对应关系；Agent 调用必须使用完整工具名 `{tool}`。

{steps}

{result}

调用：使用本技能 `scripts/run.py --db <共享数据库路径> --input <请求JSON路径>`；仅首次建立会话时添加 `--init <session.json>`。请求信封包含 schema_version、request_id、simulation_id、account_id 和 data；写操作还必须包含 idempotency_key。金额和价格用十进制字符串，数量用整数股，时间带 +08:00 时区。

先读 [输入契约](../assets/input.schema.json) 和 [成功请求](../assets/example.json)，再按真实会话状态填写；示例里的订单号、版本和账户不能直接代替当前会话。检查 JSON 的 ok 和 commit_status 后再推进后续业务。这里只操作本地模拟账户及 simulation_fixture 规则。
'''.replace('../assets/', 'assets/')
