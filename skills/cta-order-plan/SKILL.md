---
name: cta-order-plan
description: 按整数目标净手数生成并持久化先平后开的调仓计划，不提交订单或冻结资源。 仅用于本地期货模拟。
when_to_use: 需要在本地期货模拟会话中生成调仓计划时使用。
version: 0.2.0
entry: scripts/run.py
allowed_tools:
  - skill_run_script
---

# 生成调仓计划

按整数目标净手数生成并持久化先平后开的调仓计划，不提交订单或冻结资源。

层级：Upper；业务编号：CTA-U1。调用时使用完整名称 `cta-order-plan`，编号仅作业务映射。仅操作本地模拟账户及 `simulation_fixture` 规则，不接入真实账户或推断生产规则。

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
| `data.contract_id` | string | 必填 | 显式配置的模拟期货合约标识 |
| `data.target_net_lots` | integer | 必填 | 目标净手数，多头为正、空头为负、零为清仓 |
| `data.target_id` | string | 必填 | 目标业务标识，同一目标版本保持规范化数量不变 |
| `data.target_version` | integer | 必填 | 目标版本；改变目标必须增加版本；最小值 1 |
| `data.account_version` | integer | 必填 | 当前账户版本，用于并发校验；从最新账户快照读取；最小值 1 |
| `data.as_of` | string | 必填 | 账户快照或本次业务的基准时点，须与当前会话相符 |
| `data.reference_price` | string | 必填 | 用于目标换算或计划的显式参考价；十进制字符串 |
| `data.buffer` | string | 可选，默认 `0` | 额外预留现金缓冲；十进制字符串 |
| `idempotency_key` | string | 必填 | 持久化操作的幂等键；相同键及载荷返回原结果，改动载荷须使用新键 |

金额和价格使用十进制字符串，时间使用带 `+08:00` 时区的显式时间。示例中的账户、标的、订单号和版本只适用于对应示例会话，实际调用须从当前会话读取。

## 调用

在技能目录中调用，关联步骤始终使用同一个数据库路径：

```text
skill_run_script { skill: "cta-order-plan", script: "scripts/run.py", args: ["--db", "cta.sqlite", "--input", "assets/example.json"] }
```

没有 `skill_run_script` 时，通过 Python 3.11 或以上版本直接执行相同入口：

```bash
python scripts/run.py --db cta.sqlite --input assets/example.json
```

`--input` 指向完整请求 JSON 文件；省略时从标准输入读取 JSON。首次建立新会话时附加 `--init <session.json>`；已有会话后续调用省略 `--init`。可用初始化文件来自项目的 `examples/cta/long/session.json` 或 `examples/cta/short/session.json`。先核对输入引用的账户及资源是否存在，仅初始化账户不会自动生成订单或成交。

运行依赖打包在本技能的 `scripts/` 中，运行条件见 [runtime.json](assets/runtime.json)。stdout 返回一个 JSON 信封；退出码 0 表示 `ok=true`，退出码 1 表示错误信封。

需要订单、计划腿或成交前置状态的示例，应从项目根目录运行 `python scripts/replay_cta_example.py --tool cta-order-plan`，脚本在独立临时数据库中装载本技能的 [prepared-state.json](assets/prepared-state.json) 后执行真实入口。该文件是可信测试夹具，不能作为公开交易接口的输入，也不能隐式借用其他技能的账户状态。

本接口持久化状态，必须提供非空 `idempotency_key`。完成操作重试保留原键和完全相同的载荷；同键改载荷返回 `IDEMPOTENCY_CONFLICT`。纠正被拒绝的请求后使用新键。

## 输出参数

成功与失败的完整结构见[输出契约](assets/output.schema.json)，并可对照[成功响应](assets/success.json)和[失败响应](assets/failure.json)。业务字段随成功路径、订单生命周期或中断阶段出现；下表汇总各分支，不表示所有字段总会同时返回。可扩展账户、规则及持仓对象的详细结构以契约和实际快照为准。

| 字段 | JSON 类型 | 出现条件与含义 |
| --- | --- | --- |
| `ok` | boolean | 成功为 true，失败为 false |
| `schema_version` | string | 请求和响应协议版本，固定为 1.0；固定值 `"1.0"` |
| `request_id` | string | 本次请求标识，响应原样返回以便追踪 |
| `data` | object | 业务请求或成功结果对象 |
| `data.plan_id` | string | 持久化调仓计划标识 |
| `data.contract_id` | string | 显式配置的模拟期货合约标识 |
| `data.target_net_lots` | integer | 目标净手数，多头为正、空头为负、零为清仓 |
| `data.leg_ids` | array of string | 已持久化计划腿标识列表 |
| `data.hash` | string | 持久化输入或状态的摘要 |
| `data.normalization` | object | 目标数量取整结果及权重偏差 |
| `data.normalization.actual_long_lots` | integer | 当前多头持仓手数 |
| `data.normalization.actual_short_lots` | integer | 当前空头持仓手数 |
| `data.normalization.actual_net_lots` | integer | 当前净持仓手数，多头为正、空头为负 |
| `data.normalization.pending_open_lots` | integer | 活动开仓订单剩余手数 |
| `data.normalization.pending_close_lots` | integer | 活动平仓订单剩余手数 |
| `data.normalization.gap_lots` | integer | 扣除活动开平指令后的有符号净手数缺口 |
| `data.normalization.conflicting_order_ids` | array | 与新目标冲突的活动订单标识 |
| `data.normalization.retained_order_ids` | array | 继续计入目标缺口的兼容活动订单标识 |
| `data.commit_status` | string | 业务提交状态；COMMITTED 表示本接口的状态已持久化，不等于订单成交 |
| `data.legs` | array of object | 按先平后开顺序拆分的指令或计划腿 |
| `data.legs[].leg_id` | string | 已持久化计划腿的标识，从计划结果读取 |
| `data.legs[].plan_id` | string | 持久化调仓计划标识 |
| `data.legs[].contract_id` | string | 显式配置的模拟期货合约标识 |
| `data.legs[].side` | string | 买卖方向：BUY 或 SELL |
| `data.legs[].offset` | string | 期货开平类型；股票成交分页入参中为从零开始的偏移量 |
| `data.legs[].lots` | integer | 整数手数 |
| `data.legs[].limit_price` | string | 限价委托价格 |
| `data.legs[].order_type` | string | 委托类型：LIMIT 限价，MARKET 市价保护 |
| `data.legs[].time_in_force` | string | 委托有效期，当前使用 DAY |
| `data.legs[].target_id` | string | 目标业务标识，同一目标版本保持规范化数量不变 |
| `data.legs[].target_version` | integer | 目标版本；改变目标必须增加版本 |
| `data.legs[].trade_date` | string | 会话日历中的交易日，夜盘不按自然日期推断 |
| `data.legs[].dependencies` | array | 开仓前必须完成成交并记账的平仓依赖 |
| `data.legs[].buffer` | string | 额外预留现金缓冲 |
| `data.legs[].order_id` | string / null | 已登记订单标识，从提交或登记结果读取 |
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

- [cta-contract-spec](../cta-contract-spec/SKILL.md)：查合约规则。读取指定合约及交易日的模拟合约规格、保证金与手续费规则。
- [cta-trading-session](../cta-trading-session/SKILL.md)：判交易日和时段。根据显式日历将输入时点解析为交易日及交易时段，包含夜盘归属。
- [cta-position-gap](../cta-position-gap/SKILL.md)：算持仓缺口。读取多空持仓及活动开平指令，计算有符号的净手数缺口。
- [cta-offset-split](../cta-offset-split/SKILL.md)：拆开平指令。按平仓优先级拆分方向、平今、平昨和剩余开仓手数，不登记订单。
