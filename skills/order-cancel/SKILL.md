---
name: order-cancel
description: 输入订单号及预期版本，撤销尚未成交部分并释放相应资源，保留既有成交。 仅用于本地股票模拟。
when_to_use: 需要在本地股票模拟会话中撤销余单时使用。
version: 0.1.0
entry: scripts/run.py
allowed_tools:
  - skill_run_script
---

# 撤销余单

输入订单号及预期版本，撤销尚未成交部分并释放相应资源，保留既有成交。

层级：Upper；业务编号：STOCK-U4。调用时使用完整名称 `order-cancel`，编号仅作业务映射。仅操作本地模拟账户及 `simulation_fixture` 规则，不接入真实账户或推断生产规则。

先查询当前订单与 version。默认或 action=CONFIRM 同步确认撤单，撤销 leaves_quantity，随后释放剩余占用。异步模拟用 REQUEST 保留在途量和冻结；成交入账后重新查询，用最新 expected_version 执行 CONFIRM，或 REJECT 清除等待标记。

确认撤销返回 order、release 和本次 canceled_quantity，已成交量不回退。REQUEST/REJECT 的 release=null，尚未确认撤销，也不返回本次撤销量。遇到 ACCOUNTING_PENDING 先恢复成交入账，再以当前版本撤单。

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
| `data.expected_version` | integer | 必填 | 当前订单版本，用于比较并更新，须先查询最新版本；最小值 1 |
| `data.action` | string | 可选，默认 `CONFIRM` | 撤单动作：REQUEST 发起等待，CONFIRM 确认，REJECT 拒绝；取值 `REQUEST`、`CONFIRM`、`REJECT` |
| `idempotency_key` | string | 必填 | 持久化操作的幂等键；相同键及载荷返回原结果，改动载荷须使用新键 |

金额和价格使用十进制字符串，时间使用带 `+08:00` 时区的显式时间。示例中的账户、标的、订单号和版本只适用于对应示例会话，实际调用须从当前会话读取。

## 调用

在技能目录中调用，关联步骤始终使用同一个数据库路径：

```text
skill_run_script { skill: "order-cancel", script: "scripts/run.py", args: ["--db", "simulation.sqlite", "--input", "assets/example.json"] }
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
| `data.order` | object | 订单草稿、当前订单或经校验的委托对象 |
| `data.order.instrument_id` | string | 会话规则中配置的模拟股票标识 |
| `data.order.side` | string | 买卖方向：BUY 或 SELL |
| `data.order.quantity` | integer | 整数股数 |
| `data.order.order_type` | string | 委托类型：LIMIT 限价，MARKET 市价保护 |
| `data.order.limit_price` | string | 限价委托价格 |
| `data.order.time_in_force` | string | 委托有效期，当前使用 DAY |
| `data.order.submitted_at` | string | 委托时点，使用带 +08:00 时区的时间并通过交易时段检查 |
| `data.order.target_id` | string | 目标业务标识，同一目标版本保持规范化数量不变 |
| `data.order.target_version` | integer | 目标版本；改变目标必须增加版本 |
| `data.order.account_version` | integer | 当前账户版本，用于并发校验；从最新账户快照读取 |
| `data.order.order_id` | string | 已登记订单标识，从提交或登记结果读取 |
| `data.order.client_order_id` | string | 唯一业务委托号，同一业务重试保持不变 |
| `data.order.status` | string | 订单或业务当前状态 |
| `data.order.version` | integer | 当前对象版本 |
| `data.order.filled_quantity` | integer | 订单累计已成交股数 |
| `data.order.leaves_quantity` | integer | 订单尚未成交或撤销的剩余股数 |
| `data.order.canceled_quantity` | integer | 已撤销股数；撤单结果中可表示本次撤销量 |
| `data.order.reserved_cash` | string | 订单当前预留现金 |
| `data.order.reserved_quantity` | integer | 订单当前冻结股数 |
| `data.order.notional` | string | 名义金额；费用计算入参中为本次成交金额 |
| `data.order.charged_fee` | string | 该订单此前已收取的累计费用 |
| `data.order.cancel_pending` | boolean | 是否正在等待撤单确认 |
| `data.canceled_quantity` | integer | 已撤销股数；撤单结果中可表示本次撤销量 |
| `data.release` | object / null | 资源释放结果，未发生释放时可能为 null |
| `data.release.released_cash` | string | 本次实际释放的现金 |
| `data.release.remaining_cash` | string | 处理后仍需保留的冻结现金 |
| `data.release.remaining_quantity` | integer | 处理后仍需冻结的股数 |
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

- [order-state-read](../order-state-read/SKILL.md)：读取订单状态。读取订单方向、价格、委托/成交/撤销/剩余量、状态与版本；不读取或修改账户账本。
- [order-cancel-remainder](../order-cancel-remainder/SKILL.md)：撤销订单剩余量。基于预期版本撤销剩余量并保留已成交量；不释放预留，后续必须调用 order-release-reserve。
- [order-release-reserve](../order-release-reserve/SKILL.md)：释放多余预留。根据持久化订单和已记账事实计算仍需预留并释放多余资源；不信任调用者任意指定释放量，不进行成交记账。
