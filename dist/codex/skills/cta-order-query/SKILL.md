---
name: cta-order-query
description: 查询订单、成交、资源占用及账户对账状态，不修改业务状态。 仅用于本地期货模拟。
allowed-tools:
  - skill_run_script
metadata:
  version: "0.2.0"
  entry: scripts/run.py
  when_to_use: 需要在本地期货模拟会话中查订单和成交时使用。
---

# 查订单和成交

查询订单、成交、资源占用及账户对账状态，不修改业务状态。

层级：Upper；业务编号：CTA-U6。调用时使用完整名称 `cta-order-query`，编号仅作业务映射。仅操作本地模拟账户及 `simulation_fixture` 规则，不接入真实账户或推断生产规则。

期货请求必须显式指定 `asset_class=FUTURES`，数量使用整数手，目标使用有符号净手数。合约、交易日、开平类型及数量必须明确，不能用股票权重代替。

## 输入参数

参数位于 JSON 请求信封及其 `data` 对象中，下表使用完整字段路径；数组子项以 `[]` 表示。嵌套字段的必填要求在所属对象出现时适用。以[输入契约](assets/input.schema.json)为准，填写前核对[业务契约](references/contract.md)和[请求示例](assets/example.json)。

| 字段 | JSON 类型 | 必填 | 取值与含义 |
| --- | --- | --- | --- |
| `schema_version` | string | 必填 | 请求和响应协议版本，固定为 1.0；固定值 `"1.0"` |
| `request_id` | string | 必填 | 本次请求标识，响应原样返回以便追踪 |
| `simulation_id` | string | 必填 | 本地模拟会话标识，必须与初始化会话一致 |
| `account_id` | string | 必填 | 模拟账户标识，必须与初始化会话一致 |
| `asset_class` | string | 必填 | 资产类别，期货接口固定为 FUTURES；固定值 `"FUTURES"` |
| `data` | object | 必填 | 业务请求或成功结果对象；仅接受下列契约字段 |
| `data.order_id` | string | 必填 | 已登记订单标识，从提交或登记结果读取 |
| `idempotency_key` | string | 可选（只读接口） | 持久化操作的幂等键；相同键及载荷返回原结果，改动载荷须使用新键 |

金额和价格使用十进制字符串，时间使用带 `+08:00` 时区的显式时间。示例中的账户、标的、订单号和版本只适用于对应示例会话，实际调用须从当前会话读取。

## 调用

在技能目录中调用，关联步骤始终使用同一个数据库路径：

```text
skill_run_script { skill: "cta-order-query", script: "scripts/run.py", args: ["--db", "cta.sqlite", "--input", "assets/example.json"] }
```

没有 `skill_run_script` 时，通过 Python 3.11 或以上版本直接执行相同入口：

```bash
python scripts/run.py --db cta.sqlite --input assets/example.json
```

`--input` 指向完整请求 JSON 文件；省略时从标准输入读取 JSON。首次建立新会话时附加 `--init <session.json>`；已有会话后续调用省略 `--init`。可用初始化文件来自项目的 `examples/cta/long/session.json` 或 `examples/cta/short/session.json`。先核对输入引用的账户及资源是否存在，仅初始化账户不会自动生成订单或成交。

运行依赖打包在本技能的 `scripts/` 中，运行条件见 [runtime.json](assets/runtime.json)。stdout 返回一个 JSON 信封；退出码 0 表示 `ok=true`，退出码 1 表示错误信封。

需要订单、计划腿或成交前置状态的示例，应从项目根目录运行 `python scripts/replay_cta_example.py --tool cta-order-query`，脚本在独立临时数据库中装载本技能的 [prepared-state.json](assets/prepared-state.json) 后执行真实入口。该文件是可信测试夹具，不能作为公开交易接口的输入，也不能隐式借用其他技能的账户状态。

本接口只读或只计算，不隐式修改账户、订单、成交或冻结资源。

## 输出参数

成功与失败的完整结构见[输出契约](assets/output.schema.json)，并可对照[成功响应](assets/success.json)和[失败响应](assets/failure.json)。业务字段随成功路径、订单生命周期或中断阶段出现；下表汇总各分支，不表示所有字段总会同时返回。可扩展账户、规则及持仓对象的详细结构以契约和实际快照为准。

| 字段 | JSON 类型 | 出现条件与含义 |
| --- | --- | --- |
| `ok` | boolean | 成功为 true，失败为 false |
| `schema_version` | string | 请求和响应协议版本，固定为 1.0；固定值 `"1.0"` |
| `request_id` | string | 本次请求标识，响应原样返回以便追踪 |
| `data` | object | 业务请求或成功结果对象 |
| `data.order` | object | 订单草稿、当前订单或经校验的委托对象 |
| `data.order.leg_id` | string | 已持久化计划腿的标识，从计划结果读取 |
| `data.order.plan_id` | string | 持久化调仓计划标识 |
| `data.order.contract_id` | string | 显式配置的模拟期货合约标识 |
| `data.order.side` | string | 买卖方向：BUY 或 SELL |
| `data.order.offset` | string | 期货开平类型；股票成交分页入参中为从零开始的偏移量 |
| `data.order.lots` | integer | 整数手数 |
| `data.order.limit_price` | string | 限价委托价格 |
| `data.order.order_type` | string | 委托类型：LIMIT 限价，MARKET 市价保护 |
| `data.order.time_in_force` | string | 委托有效期，当前使用 DAY |
| `data.order.target_id` | string | 目标业务标识，同一目标版本保持规范化数量不变 |
| `data.order.target_version` | integer | 目标版本；改变目标必须增加版本 |
| `data.order.trade_date` | string | 会话日历中的交易日，夜盘不按自然日期推断 |
| `data.order.dependencies` | array | 开仓前必须完成成交并记账的平仓依赖 |
| `data.order.buffer` | string | 额外预留现金缓冲 |
| `data.order.order_id` | string / null | 已登记订单标识，从提交或登记结果读取 |
| `data.order.submitted_at` | string | 委托时点，使用带 +08:00 时区的时间并通过交易时段检查 |
| `data.order.account_version` | integer | 当前账户版本，用于并发校验；从最新账户快照读取 |
| `data.order.client_order_id` | string | 唯一业务委托号，同一业务重试保持不变 |
| `data.order.sequence` | integer | 订单优先级序号 |
| `data.order.status` | string | 订单或业务当前状态 |
| `data.order.version` | integer | 当前对象版本 |
| `data.order.original_lots` | integer | 订单原始委托手数 |
| `data.order.filled_lots` | integer | 订单累计已成交手数 |
| `data.order.leaves_lots` | integer | 订单尚未成交或撤销的剩余手数 |
| `data.order.canceled_lots` | integer | 已撤销手数 |
| `data.order.reserved_cash` | string | 订单当前预留现金 |
| `data.order.claims` | array of object | 平仓占用的持仓批次及手数 |
| `data.order.charged_fee` | string | 该订单此前已收取的累计费用 |
| `data.order.notional` | string | 名义金额；费用计算入参中为本次成交金额 |
| `data.order.release_pending` | boolean | 是否仍存在待释放资源 |
| `data.order.cancel_pending` | boolean | 是否正在等待撤单确认 |
| `data.order.average_price` | string | 订单累计成交均价；成交后可能出现 |
| `data.fills` | array of object | 逐笔成交及其处理状态 |
| `data.fills[].fill_id` | string | 持久化成交的唯一标识；登记时指定，后续应用和记账复用 |
| `data.fills[].order_id` | string / null | 已登记订单标识，从提交或登记结果读取 |
| `data.fills[].contract_id` | string | 显式配置的模拟期货合约标识 |
| `data.fills[].side` | string | 买卖方向：BUY 或 SELL |
| `data.fills[].offset` | string | 期货开平类型；股票成交分页入参中为从零开始的偏移量 |
| `data.fills[].lots` | integer | 整数手数 |
| `data.fills[].price` | string | 价格或模拟成交价 |
| `data.fills[].notional` | string | 名义金额；费用计算入参中为本次成交金额 |
| `data.fills[].fee` | string | 本次增量费用或费用计算结果 |
| `data.fills[].reserved_consumption` | string | 本次成交实际消耗的预留资源金额 |
| `data.fills[].executed_at` | string | 成交执行时点 |
| `data.fills[].trade_date` | string | 会话日历中的交易日，夜盘不按自然日期推断 |
| `data.fills[].market_event_id` | string | 成交所依据的持久化行情事件标识 |
| `data.fills[].model_version` | string | 撮合模型版本 |
| `data.fills[].accounting_status` | string | 成交记账状态，检查是否仍待入账 |
| `data.fills[].order_applied` | boolean | 成交是否已经应用到订单数量与状态 |
| `data.fills[].realized_pnl` | string | 已经确认的平仓盈亏 |
| `data.fills[].source_hash` | string | 原始事件或请求载荷摘要 |
| `data.account` | object | 当前权威模拟账户快照 |
| `data.commit_status` | string | 业务提交状态；COMMITTED 表示本接口的状态已持久化，不等于订单成交 |
| `warnings` | array | 成功响应中的提示列表，可能为空 |
| `error` | object | 失败时返回的错误对象 |
| `error.code` | string | 错误类别 |
| `error.message` | string | 具体错误原因 |
| `error.retryable` | boolean | 错误或中断是否支持按恢复条件重试 |
| `error.details` | object | 错误附加信息，按错误类别解释 |

先检查 `ok`；失败时读取 `error.code/message/details`，结合 `retryable` 和业务契约处理。若 `data.commit_status` 为 `ACCOUNTING_PENDING` 或 `RECOVERY_REQUIRED`，即使 `ok=true` 也未完成，须先恢复后再推进依赖交易。`COMMITTED` 仅表示当前接口的操作完成。

## 执行约束

提交或登记前须存在持久化计划腿，账户版本为当前版本；依赖平仓的开仓腿须等平仓全部成交并记账。登记和冻结在同一事务内完成。日结使用显式上一结算价及本次结算价，避免重复入账与重复迁移。

成交前先持久化行情，再按登记成交 → 更新订单 → 成交记账 → 释放资源恢复。撮合候选本身不占用容量。默认预留策略为 `UPPER_BOUND_V1`，`ORDER_PRICE_V1` 仅可由显式夹具配置；成交及剩余委托不得超出预留预算。

待记账成交会阻止依赖交易。中断的模拟使用相同 bar/model、新的幂等键并去掉 fail_after 恢复；原键仍返回原中断响应。成交冲突导致 RECONCILE 时停止新提交，由可信运行时依据独立证据及版本校验完成对账，不能通过工具自行清除。详细前置条件、执行顺序和错误码见[业务契约](references/contract.md)。

## 可独立使用的原子工具

以下为业务职责分解，包含间接复用的计算；不表示每次调用均逐项执行。Upper 入口已负责流程编排，一般无需调用者逐一执行。独立调用时仍须满足各工具自身的前置状态。

- [cta-order-detail](../cta-order-detail/SKILL.md)：读订单明细。读取订单、成交、资源预留及记账状态，不修改业务状态。
