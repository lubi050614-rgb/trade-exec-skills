---
name: order-apply-fill
description: 读取已登记成交，幂等推进订单成交量、剩余量、均价与状态；不计算虚构成交、不写账户余额。 仅用于本地股票模拟。
allowed-tools:
  - skill_run_script
metadata:
  version: "0.1.0"
  entry: scripts/run.py
  when_to_use: 需要在本地股票模拟会话中应用成交到订单时使用。
---

# 应用成交到订单

读取已登记成交，幂等推进订单成交量、剩余量、均价与状态；不计算虚构成交、不写账户余额。

层级：Atomic；业务编号：STOCK-A13。调用时使用完整名称 `order-apply-fill`，编号仅作业务映射。仅操作本地模拟账户及 `simulation_fixture` 规则，不接入真实账户或推断生产规则。

## 输入参数

参数位于 JSON 请求信封及其 `data` 对象中，下表使用完整字段路径；数组子项以 `[]` 表示。嵌套字段的必填要求在所属对象出现时适用。以[输入契约](assets/input.schema.json)为准，填写前核对[业务契约](references/contract.md)和[请求示例](assets/example.json)。

| 字段 | JSON 类型 | 必填 | 取值与含义 |
| --- | --- | --- | --- |
| `schema_version` | string | 必填 | 请求和响应协议版本，固定为 1.0；固定值 `"1.0"` |
| `request_id` | string | 必填 | 本次请求标识，响应原样返回以便追踪 |
| `account_id` | string | 必填 | 模拟账户标识，必须与初始化会话一致 |
| `simulation_id` | string | 必填 | 本地模拟会话标识，必须与初始化会话一致 |
| `data` | object | 必填 | 业务请求或成功结果对象；仅接受下列契约字段 |
| `data.order_id` | string | 必填 | 已登记订单标识，从提交或登记结果读取 |
| `data.fill_id` | string | 必填 | 持久化成交的唯一标识；登记时指定，后续应用和记账复用 |
| `data.expected_version` | integer | 必填 | 当前订单版本，用于比较并更新，须先查询最新版本；最小值 1 |
| `idempotency_key` | string | 必填 | 持久化操作的幂等键；相同键及载荷返回原结果，改动载荷须使用新键 |

金额和价格使用十进制字符串，时间使用带 `+08:00` 时区的显式时间。示例中的账户、标的、订单号和版本只适用于对应示例会话，实际调用须从当前会话读取。

## 调用

在技能目录中调用，关联步骤始终使用同一个数据库路径：

```text
skill_run_script { skill: "order-apply-fill", script: "scripts/run.py", args: ["--db", "simulation.sqlite", "--input", "assets/example.json"] }
```

没有 `skill_run_script` 时，通过 Python 3.11 或以上版本直接执行相同入口：

```bash
python scripts/run.py --db simulation.sqlite --input assets/example.json
```

`--input` 指向完整请求 JSON 文件；省略时从标准输入读取 JSON。首次建立新会话时附加 `--init <session.json>`；已有会话后续调用省略 `--init`。可用初始化文件来自项目的 `examples/SSE/session.json`、`examples/SZSE/session.json` 或 `examples/BSE/session.json`。先核对输入引用的账户及资源是否存在，仅初始化账户不会自动生成订单或成交。

运行依赖打包在本技能的 `scripts/` 中，运行条件见 [runtime.json](assets/runtime.json)。stdout 返回一个 JSON 信封；退出码 0 表示 `ok=true`，退出码 1 表示错误信封。

涉及订单的示例必须先执行合法的提交或登记步骤；涉及成交应用和记账时，先有持久化行情与成交。单独的请求示例不负责创建这些前置状态。

本接口持久化状态，必须提供非空 `idempotency_key`。完成操作重试保留原键和完全相同的载荷；同键改载荷返回 `IDEMPOTENCY_CONFLICT`。纠正被拒绝的请求后使用新键。

## 输出参数

成功与失败的完整结构见[输出契约](assets/output.schema.json)，并可对照[成功响应](assets/success.json)和[失败响应](assets/failure.json)。业务字段随成功路径、订单生命周期或中断阶段出现；下表汇总各分支，不表示所有字段总会同时返回。可扩展账户、规则及持仓对象的详细结构以契约和实际快照为准。

| 字段 | JSON 类型 | 出现条件与含义 |
| --- | --- | --- |
| `ok` | boolean | 成功为 true，失败为 false |
| `schema_version` | string | 请求和响应协议版本，固定为 1.0；固定值 `"1.0"` |
| `request_id` | string | 本次请求标识，响应原样返回以便追踪 |
| `data` | object | 业务请求或成功结果对象 |
| `data.instrument_id` | string | 会话规则中配置的模拟股票标识 |
| `data.side` | string | 买卖方向：BUY 或 SELL |
| `data.quantity` | integer | 整数股数 |
| `data.order_type` | string | 委托类型：LIMIT 限价，MARKET 市价保护 |
| `data.limit_price` | string | 限价委托价格 |
| `data.time_in_force` | string | 委托有效期，当前使用 DAY |
| `data.submitted_at` | string | 委托时点，使用带 +08:00 时区的时间并通过交易时段检查 |
| `data.target_id` | string | 目标业务标识，同一目标版本保持规范化数量不变 |
| `data.target_version` | integer | 目标版本；改变目标必须增加版本 |
| `data.account_version` | integer | 当前账户版本，用于并发校验；从最新账户快照读取 |
| `data.order_id` | string | 已登记订单标识，从提交或登记结果读取 |
| `data.client_order_id` | string | 唯一业务委托号，同一业务重试保持不变 |
| `data.status` | string | 订单或业务当前状态 |
| `data.version` | integer | 当前对象版本 |
| `data.filled_quantity` | integer | 订单累计已成交股数 |
| `data.leaves_quantity` | integer | 订单尚未成交或撤销的剩余股数 |
| `data.canceled_quantity` | integer | 已撤销股数；撤单结果中可表示本次撤销量 |
| `data.reserved_cash` | string | 订单当前预留现金 |
| `data.reserved_quantity` | integer | 订单当前冻结股数 |
| `data.notional` | string | 名义金额；费用计算入参中为本次成交金额 |
| `data.charged_fee` | string | 该订单此前已收取的累计费用 |
| `data.cancel_pending` | boolean | 是否正在等待撤单确认 |
| `data.average_price` | string | 订单累计成交均价；成交后可能出现 |
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

## 相关上层工具

本技能执行单个领域步骤，不调用 Upper 工作流。完整流程可按需求使用：

- [execution-simulate](../execution-simulate/SKILL.md)：模拟成交并记账。
