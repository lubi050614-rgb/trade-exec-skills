---
name: cta-fill-book
description: 对已应用到订单的持久化成交幂等记账，处理费用、已实现盈亏及持仓批次。 仅用于本地期货模拟。
allowed-tools:
  - skill_run_script
metadata:
  version: "0.2.0"
  entry: scripts/run.py
  when_to_use: 需要在本地期货模拟会话中成交记账时使用。
---

# 成交记账

对已应用到订单的持久化成交幂等记账，处理费用、已实现盈亏及持仓批次。

层级：Atomic；业务编号：CTA-A13。调用时使用完整名称 `cta-fill-book`，编号仅作业务映射。仅操作本地模拟账户及 `simulation_fixture` 规则，不接入真实账户或推断生产规则。

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
| `data.fill_id` | string | 必填 | 持久化成交的唯一标识；登记时指定，后续应用和记账复用 |
| `idempotency_key` | string | 必填 | 持久化操作的幂等键；相同键及载荷返回原结果，改动载荷须使用新键 |

金额和价格使用十进制字符串，时间使用带 `+08:00` 时区的显式时间。示例中的账户、标的、订单号和版本只适用于对应示例会话，实际调用须从当前会话读取。

## 调用

在技能目录中调用，关联步骤始终使用同一个数据库路径：

```text
skill_run_script { skill: "cta-fill-book", script: "scripts/run.py", args: ["--db", "cta.sqlite", "--input", "assets/example.json"] }
```

没有 `skill_run_script` 时，通过 Python 3.11 或以上版本直接执行相同入口：

```bash
python scripts/run.py --db cta.sqlite --input assets/example.json
```

`--input` 指向完整请求 JSON 文件；省略时从标准输入读取 JSON。首次建立新会话时附加 `--init <session.json>`；已有会话后续调用省略 `--init`。可用初始化文件来自项目的 `examples/cta/long/session.json` 或 `examples/cta/short/session.json`。先核对输入引用的账户及资源是否存在，仅初始化账户不会自动生成订单或成交。

运行依赖打包在本技能的 `scripts/` 中，运行条件见 [runtime.json](assets/runtime.json)。stdout 返回一个 JSON 信封；退出码 0 表示 `ok=true`，退出码 1 表示错误信封。

需要订单、计划腿或成交前置状态的示例，应从项目根目录运行 `python scripts/replay_cta_example.py --tool cta-fill-book`，脚本在独立临时数据库中装载本技能的 [prepared-state.json](assets/prepared-state.json) 后执行真实入口。该文件是可信测试夹具，不能作为公开交易接口的输入，也不能隐式借用其他技能的账户状态。

本接口持久化状态，必须提供非空 `idempotency_key`。完成操作重试保留原键和完全相同的载荷；同键改载荷返回 `IDEMPOTENCY_CONFLICT`。纠正被拒绝的请求后使用新键。

## 输出参数

成功与失败的完整结构见[输出契约](assets/output.schema.json)，并可对照[成功响应](assets/success.json)和[失败响应](assets/failure.json)。业务字段随成功路径、订单生命周期或中断阶段出现；下表汇总各分支，不表示所有字段总会同时返回。可扩展账户、规则及持仓对象的详细结构以契约和实际快照为准。

| 字段 | JSON 类型 | 出现条件与含义 |
| --- | --- | --- |
| `ok` | boolean | 成功为 true，失败为 false |
| `schema_version` | string | 请求和响应协议版本，固定为 1.0；固定值 `"1.0"` |
| `request_id` | string | 本次请求标识，响应原样返回以便追踪 |
| `data` | object | 业务请求或成功结果对象 |
| `data.account_id` | string | 模拟账户标识，必须与初始化会话一致 |
| `data.asset_class` | string | 资产类别，期货接口固定为 FUTURES |
| `data.currency` | string | 模拟账户币种 |
| `data.balance` | string | 模拟账户账面余额 |
| `data.as_of` | string | 账户快照或本次业务的基准时点，须与当前会话相符 |
| `data.version` | integer | 当前对象版本 |
| `data.equity` | string | 模拟期货账户权益 |
| `data.floating_pnl` | string | 当前浮动盈亏 |
| `data.position_margin` | string | 当前持仓占用保证金 |
| `data.frozen_cash` | string | 当前冻结现金 |
| `data.available_cash` | string | 扣除冻结后的可用现金 |
| `data.margin_shortfall` | string | 保证金不足金额 |
| `data.risk_status` | string | 模拟账户风险状态 |
| `data.positions` | object | 按标的保存的当前持仓与批次信息 |
| `data.trade_date` | string | 会话日历中的交易日，夜盘不按自然日期推断 |
| `data.reconciliation_status` | string | 账户对账状态，未完成时先处理恢复或对账 |
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

## 相关上层工具

本技能执行单个领域步骤，不调用 Upper 工作流。完整流程可按需求使用：

- [cta-execution-simulate](../cta-execution-simulate/SKILL.md)：模拟成交并记账。
