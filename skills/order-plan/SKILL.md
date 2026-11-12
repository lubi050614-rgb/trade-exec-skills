---
name: order-plan
description: 输入完整目标权重、当前账户快照和参考价；读取当前持仓与已有挂单，计算每只股票还需买卖多少股。 仅用于本地股票模拟。
when_to_use: 需要在本地股票模拟会话中生成订单草稿时使用。
version: 0.1.0
entry: scripts/run.py
allowed_tools:
  - skill_run_script
---

# 生成订单草稿

输入完整目标权重、当前账户快照和参考价；读取当前持仓与已有挂单，计算每只股票还需买卖多少股。

层级：Upper；业务编号：STOCK-U1。调用时使用完整名称 `order-plan`，编号仅作业务映射。仅操作本地模拟账户及 `simulation_fixture` 规则，不接入真实账户或推断生产规则。

先核对 account_snapshot_id、as_of、total_assets 和 current_weight。targets 必须覆盖当前持仓及活动挂单；清仓标的用 target_weight=0 表达。按规则把目标权重转换为整数股数，再扣除在途买卖剩余量。差额为零不生成订单。同一 target_id/target_version 固定目标股数；改变目标权重必须增加版本。

drafts 是可传给预检/提交的订单草稿；normalization 说明取整偏差。检查 funding_sufficient、requires_sell_proceeds 和 cash_buffer；依赖卖出收入时先等待实际成交入账，再用当前账户版本提交买单。计划本身不冻结资金或股票。

## 输入参数

参数位于 JSON 请求信封及其 `data` 对象中，下表使用完整字段路径；数组子项以 `[]` 表示。嵌套字段的必填要求在所属对象出现时适用。以[输入契约](assets/input.schema.json)为准，填写前核对[业务契约](references/contract.md)和[请求示例](assets/example.json)。

| 字段 | JSON 类型 | 必填 | 取值与含义 |
| --- | --- | --- | --- |
| `schema_version` | string | 必填 | 请求和响应协议版本，固定为 1.0；固定值 `"1.0"` |
| `request_id` | string | 必填 | 本次请求标识，响应原样返回以便追踪 |
| `account_id` | string | 必填 | 模拟账户标识，必须与初始化会话一致 |
| `simulation_id` | string | 必填 | 本地模拟会话标识，必须与初始化会话一致 |
| `data` | object | 必填 | 业务请求或成功结果对象；仅接受下列契约字段 |
| `data.account_snapshot_id` | string | 必填 | 账户快照标识，使用当前账户版本对应的快照 |
| `data.as_of` | string | 必填 | 账户快照或本次业务的基准时点，须与当前会话相符 |
| `data.total_assets` | string | 必填 | 当前账户总资产，须与持仓估值及现金一致；十进制字符串 |
| `data.coverage` | string | 必填 | 目标覆盖范围，固定 FULL，包含当前持仓及活动挂单标的；固定值 `"FULL"` |
| `data.target_id` | string | 必填 | 目标业务标识，同一目标版本保持规范化数量不变 |
| `data.target_version` | integer | 必填 | 目标版本；改变目标必须增加版本；最小值 1 |
| `data.targets` | array of object | 必填 | 完整目标清单，必须覆盖当前持仓及活动挂单 |
| `data.targets[].instrument_id` | string | 必填 | 会话规则中配置的模拟股票标识 |
| `data.targets[].target_weight` | string | 必填 | 目标持仓权重，零表示清仓；十进制字符串 |
| `data.targets[].current_weight` | string | 必填 | 当前持仓市值占总资产的权重，用于校验账户快照；十进制字符串 |
| `data.targets[].reference_price` | string | 必填 | 用于目标换算或计划的显式参考价；十进制字符串 |
| `data.targets[].price_basis` | string | 必填 | 价格口径，固定 UNADJUSTED，使用未复权价格；固定值 `"UNADJUSTED"` |
| `data.targets[].price_as_of` | string | 必填 | 参考价对应时点，须与快照及允许的时效一致 |
| `data.targets[].price_source` | string | 必填 | 参考价来源 |
| `data.weight_tolerance` | string | 可选，默认 `0.000001` | 当前权重与账户计算值之间允许的偏差；十进制字符串 |
| `data.cash_buffer` | string | 可选，默认 `0` | 计划要求保留的现金缓冲；十进制字符串 |
| `idempotency_key` | string | 必填 | 持久化操作的幂等键；相同键及载荷返回原结果，改动载荷须使用新键 |

金额和价格使用十进制字符串，时间使用带 `+08:00` 时区的显式时间。示例中的账户、标的、订单号和版本只适用于对应示例会话，实际调用须从当前会话读取。

## 调用

在技能目录中调用，关联步骤始终使用同一个数据库路径：

```text
skill_run_script { skill: "order-plan", script: "scripts/run.py", args: ["--db", "simulation.sqlite", "--input", "assets/example.json"] }
```

没有 `skill_run_script` 时，通过 Python 3.11 或以上版本直接执行相同入口：

```bash
python scripts/run.py --db simulation.sqlite --input assets/example.json
```

`--input` 指向完整请求 JSON 文件；省略时从标准输入读取 JSON。首次建立新会话时附加 `--init <session.json>`；已有会话后续调用省略 `--init`。可用初始化文件来自项目的 `examples/SSE/session.json`、`examples/SZSE/session.json` 或 `examples/BSE/session.json`。先核对输入引用的账户及资源是否存在，仅初始化账户不会自动生成订单或成交。

运行依赖打包在本技能的 `scripts/` 中，运行条件见 [runtime.json](assets/runtime.json)。stdout 返回一个 JSON 信封；退出码 0 表示 `ok=true`，退出码 1 表示错误信封。

涉及订单的示例必须先执行合法的提交或登记步骤；涉及成交应用和记账时，先有持久化行情与成交。单独的请求示例不负责创建这些前置状态。

本接口持久化状态，必须提供非空 `idempotency_key`。完成操作重试保留原键和完全相同的载荷；同键改载荷返回 `IDEMPOTENCY_CONFLICT`。`order-plan` 仅保存规范化目标和幂等结果，不提交订单或冻结资源。

## 输出参数

成功与失败的完整结构见[输出契约](assets/output.schema.json)，并可对照[成功响应](assets/success.json)和[失败响应](assets/failure.json)。业务字段随成功路径、订单生命周期或中断阶段出现；下表汇总各分支，不表示所有字段总会同时返回。可扩展账户、规则及持仓对象的详细结构以契约和实际快照为准。

| 字段 | JSON 类型 | 出现条件与含义 |
| --- | --- | --- |
| `ok` | boolean | 成功为 true，失败为 false |
| `schema_version` | string | 请求和响应协议版本，固定为 1.0；固定值 `"1.0"` |
| `request_id` | string | 本次请求标识，响应原样返回以便追踪 |
| `data` | object | 业务请求或成功结果对象 |
| `data.drafts` | array of object | 可供预检或提交的订单草稿，空数组表示无需委托 |
| `data.drafts[].instrument_id` | string | 会话规则中配置的模拟股票标识 |
| `data.drafts[].side` | string | 买卖方向：BUY 或 SELL |
| `data.drafts[].quantity` | integer | 整数股数 |
| `data.drafts[].order_type` | string | 委托类型：LIMIT 限价，MARKET 市价保护 |
| `data.drafts[].limit_price` | string | 限价委托价格 |
| `data.drafts[].time_in_force` | string | 委托有效期，当前使用 DAY |
| `data.drafts[].submitted_at` | string | 委托时点，使用带 +08:00 时区的时间并通过交易时段检查 |
| `data.drafts[].target_id` | string | 目标业务标识，同一目标版本保持规范化数量不变 |
| `data.drafts[].target_version` | integer | 目标版本；改变目标必须增加版本 |
| `data.drafts[].account_version` | integer | 当前账户版本，用于并发校验；从最新账户快照读取 |
| `data.normalization` | array of object | 目标数量取整结果及权重偏差 |
| `data.normalization[].instrument_id` | string | 会话规则中配置的模拟股票标识 |
| `data.normalization[].raw_target_quantity` | string | 按目标权重计算、尚未取整的目标股数 |
| `data.normalization[].target_quantity` | integer | 规则取整后的目标持仓股数 |
| `data.normalization[].rounding_weight_deviation` | string | 按规则取整引入的权重偏差 |
| `data.estimated_buy_cost` | string | 预计买入总支出，包含费用 |
| `data.estimated_sell_proceeds` | string | 预计卖出净收入，尚未成交时不可提前使用 |
| `data.estimated_post_trade_cash` | string | 假设计划成交后的现金估计值，尚未记账 |
| `data.cash_buffer` | string | 计划要求保留的现金缓冲 |
| `data.funding_sufficient` | boolean | 预计交易后现金是否满足现金缓冲要求 |
| `data.available_cash` | string | 扣除冻结后的可用现金 |
| `data.requires_sell_proceeds` | boolean | 买入是否依赖卖出收入；为 true 时须等待卖出实际入账 |
| `data.target_cash_weight` | string | 完整目标组合中现金的目标权重 |
| `data.commit_status` | string | 业务提交状态；COMMITTED 表示本接口的状态已持久化，不等于订单成交 |
| `warnings` | array of string | 成功响应中的提示列表，可能为空 |
| `error` | object | 失败时返回的错误对象 |
| `error.code` | string | 错误类别 |
| `error.message` | string | 具体错误原因 |
| `error.retryable` | boolean | 错误或中断是否支持按恢复条件重试 |
| `error.details` | object | 错误附加信息，按错误类别解释 |

先检查 `ok`；失败时读取 `error.code/message/details`，结合 `retryable` 和业务契约处理。若 `data.commit_status` 为 `ACCOUNTING_PENDING` 或 `RECOVERY_REQUIRED`，即使 `ok=true` 也未完成，须先恢复后再推进依赖交易。`COMMITTED` 仅表示当前接口的操作完成。

## 执行约束

账户及证券规则须已初始化；涉及更新时读取当前订单和账户版本。登记订单为 `PENDING_RESERVATION`，预留成功后才激活。直接撤销剩余量后须调用 `order-release-reserve`；登记成交前须有持久化行情，应用及记账前须有持久化成交。

待记账成交会阻止依赖交易。中断的模拟使用相同 bar/model、新的幂等键并去掉 fail_after 恢复；原键仍返回原中断响应。成交冲突导致 RECONCILE 时停止新提交，由可信运行时依据独立证据及版本校验完成对账，不能通过工具自行清除。详细前置条件、执行顺序和错误码见[业务契约](references/contract.md)。

## 可独立使用的原子工具

以下为业务职责分解，包含间接复用的计算；不表示每次调用均逐项执行。Upper 入口已负责流程编排，一般无需调用者逐一执行。独立调用时仍须满足各工具自身的前置状态。

- [order-open-quantity](../order-open-quantity/SKILL.md)：查询在途股数。读取指定证券有效订单剩余买卖量，排除未预留单和终态单；不把已成交量再次计入在途。
- [order-target-gap](../order-target-gap/SKILL.md)：计算目标股数缺口。计算 target - actual - buy_leaves + sell_leaves；不做权重转换或读写账户。
