---
name: execution-simulate
description: 输入已完成行情，读取活动订单，按撮合规则计算价格、数量和费用，记录成交并更新订单、现金和持仓。 仅用于本地股票模拟。
when_to_use: 需要在本地股票模拟会话中模拟成交并记账时使用。
version: 0.1.0
entry: scripts/run.py
allowed_tools:
  - skill_run_script
---

# 模拟成交并记账

输入已完成行情，读取活动订单，按撮合规则计算价格、数量和费用，记录成交并更新订单、现金和持仓。

层级：Upper；业务编号：STOCK-U5。调用时使用完整名称 `execution-simulate`，编号仅作业务映射。仅操作本地模拟账户及 `simulation_fixture` 规则，不接入真实账户或推断生产规则。

明确 bar、visible_at、participation_rate 与 slippage；行情必须已完成、未复权且与会话频率一致。按订单优先级共享成交容量：读取订单 → 撮合 → 登记成交 → 更新订单 → 账户入账 → 释放多余占用。费用按订单累计金额计算增量，最低佣金不对每次部分成交重复收取；一笔成交只入账一次。

COMMITTED 返回本事件 fills 和 account；没有成交时 fills 可以为空。ACCOUNTING_PENDING/RECOVERY_REQUIRED 表示未完成：保留相同 bar/model、换新 idempotency_key、去掉 fail_after 后恢复；旧键只会返回旧响应。fail_after 仅用于测试。end_of_day 会撤销并释放到期 DAY 单。

## 输入参数

参数位于 JSON 请求信封及其 `data` 对象中，下表使用完整字段路径；数组子项以 `[]` 表示。嵌套字段的必填要求在所属对象出现时适用。以[输入契约](assets/input.schema.json)为准，填写前核对[业务契约](references/contract.md)和[请求示例](assets/example.json)。

| 字段 | JSON 类型 | 必填 | 取值与含义 |
| --- | --- | --- | --- |
| `schema_version` | string | 必填 | 请求和响应协议版本，固定为 1.0；固定值 `"1.0"` |
| `request_id` | string | 必填 | 本次请求标识，响应原样返回以便追踪 |
| `account_id` | string | 必填 | 模拟账户标识，必须与初始化会话一致 |
| `simulation_id` | string | 必填 | 本地模拟会话标识，必须与初始化会话一致 |
| `data` | object | 必填 | 业务请求或成功结果对象；仅接受下列契约字段 |
| `data.bar` | object | 必填 | 已完成的模拟行情，标的、频率与当前会话一致；仅接受下列契约字段 |
| `data.bar.event_id` | string | 必填 | 已持久化行情事件标识；行情对象内为本事件唯一标识 |
| `data.bar.instrument_id` | string | 必填 | 会话规则中配置的模拟股票标识 |
| `data.bar.frequency` | string | 必填 | 会话行情频率：1m 或 1d；取值 `1m`、`1d` |
| `data.bar.trade_date` | string | 必填 | 会话日历中的交易日，夜盘不按自然日期推断 |
| `data.bar.start_at` | string | 必填 | 行情开始时点，使用带 +08:00 时区的时间 |
| `data.bar.end_at` | string | 必填 | 行情结束时点，使用带 +08:00 时区的时间 |
| `data.bar.open` | string | 必填 | 行情开盘价；十进制字符串 |
| `data.bar.high` | string | 必填 | 行情最高价；十进制字符串 |
| `data.bar.low` | string | 必填 | 行情最低价；十进制字符串 |
| `data.bar.close` | string | 必填 | 行情收盘价；十进制字符串 |
| `data.bar.volume` | integer | 必填 | 行情成交量；股票单位为股，期货单位为手；最小值 0 |
| `data.bar.amount` | string | 必填 | 行情成交金额；十进制字符串 |
| `data.bar.tradable` | boolean | 必填 | 本行情是否允许模拟交易 |
| `data.bar.price_limit_clear` | boolean | 必填 | 行情是否满足模拟涨跌停可成交条件 |
| `data.bar.price_basis` | string | 必填 | 价格口径，固定 UNADJUSTED，使用未复权价格；固定值 `"UNADJUSTED"` |
| `data.bar.source` | string | 必填 | 模拟行情来源 |
| `data.bar.synthetic` | boolean | 必填 | 是否为合成模拟行情 |
| `data.visible_at` | string | 必填 | 行情对本次模拟可见的时点，不能早于行情完成时点 |
| `data.participation_rate` | string | 必填 | 本事件可参与成交量的比例，按会话共享容量约束；十进制字符串 |
| `data.slippage` | string | 必填 | 撮合使用的显式价格滑点；十进制字符串 |
| `data.end_of_day` | boolean | 可选，默认 `false` | 是否在事件结束后处理到期 DAY 订单 |
| `data.fail_after` | string | 可选 | 测试专用故障注入点，正常调用省略；取值 `record`、`order`、`account` |
| `idempotency_key` | string | 必填 | 持久化操作的幂等键；相同键及载荷返回原结果，改动载荷须使用新键 |

金额和价格使用十进制字符串，时间使用带 `+08:00` 时区的显式时间。示例中的账户、标的、订单号和版本只适用于对应示例会话，实际调用须从当前会话读取。

## 调用

在技能目录中调用，关联步骤始终使用同一个数据库路径：

```text
skill_run_script { skill: "execution-simulate", script: "scripts/run.py", args: ["--db", "simulation.sqlite", "--input", "assets/example.json"] }
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
| `data.commit_status` | string | 业务提交状态；COMMITTED 表示本接口的状态已持久化，不等于订单成交 |
| `data.fills` | array of object | 逐笔成交及其处理状态 |
| `data.fills[].fill_id` | string | 持久化成交的唯一标识；登记时指定，后续应用和记账复用 |
| `data.fills[].order_id` | string | 已登记订单标识，从提交或登记结果读取 |
| `data.fills[].quantity` | integer | 整数股数 |
| `data.fills[].price` | string | 价格或模拟成交价 |
| `data.fills[].notional` | string | 名义金额；费用计算入参中为本次成交金额 |
| `data.fills[].fees` | string | 按开平类型配置的费用规则 |
| `data.fills[].executed_at` | string | 成交执行时点 |
| `data.fills[].market_event_id` | string | 成交所依据的持久化行情事件标识 |
| `data.fills[].model_version` | string | 撮合模型版本 |
| `data.fills[].accounting_status` | string | 成交记账状态，检查是否仍待入账 |
| `data.fills[].order_applied` | boolean | 成交是否已经应用到订单数量与状态 |
| `data.fills[].source_hash` | string | 原始事件或请求载荷摘要 |
| `data.account` | object | 当前权威模拟账户快照 |
| `data.failed_step` | string | 中断或失败的处理步骤 |
| `data.retryable` | boolean | 错误或中断是否支持按恢复条件重试；固定值 `true` |
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

- [execution-fee-calculate](../execution-fee-calculate/SKILL.md)：计算成交费用。按订单累计成交金额计算本次增量佣金与卖出税；最低费按订单累计；不对每次部分成交重复收取最低费，不记账。
- [order-state-read](../order-state-read/SKILL.md)：读取订单状态。读取订单方向、价格、委托/成交/撤销/剩余量、状态与版本；不读取或修改账户账本。
- [order-release-reserve](../order-release-reserve/SKILL.md)：释放多余预留。根据持久化订单和已记账事实计算仍需预留并释放多余资源；不信任调用者任意指定释放量，不进行成交记账。
- [execution-match](../execution-match/SKILL.md)：计算模拟成交候选。纯计算基于开盘价、保护价、规则和剩余共享容量的成交候选；不占用容量、不持久化成交、不修改账户。
- [execution-fill-record](../execution-fill-record/SKILL.md)：登记模拟成交。读取可信已持久化行情，重算候选、比较订单版本并原子登记成交和占容量；不接收调用者伪造价格/数量，不推进订单或记账。
- [order-apply-fill](../order-apply-fill/SKILL.md)：应用成交到订单。读取已登记成交，幂等推进订单成交量、剩余量、均价与状态；不计算虚构成交、不写账户余额。
- [account-apply-fill](../account-apply-fill/SKILL.md)：成交账户记账。通过账户适配器对已推进订单的持久化成交幂等入账；不接受调用者指定余额或利润，不替代真实生产账户服务。
