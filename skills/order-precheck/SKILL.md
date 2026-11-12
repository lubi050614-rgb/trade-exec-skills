---
name: order-precheck
description: 下单前检查。输入订单草稿，读取当前账户，检查委托规则、预计费用、可用资金和可卖股数。
when_to_use: 下单前检查，用于股票模拟执行。
version: 0.1.0
entry: scripts/run.py
allowed_tools:
  - skill_run_script
---

Use this independent Upper interface for `order-precheck`. Read [contract](references/contract.md) for its required inputs and preconditions. This tool uses synthetic stock rules and an authoritative mock account only.

Call `skill_run_script` with `scripts/run.py` and arguments `--db simulation.sqlite --input assets/example.json`. For a fresh session add `--init <session.json>` using an exchange fixture from the plugin examples. Run via Python directly with the same arguments when skill_run_script is unavailable.

Stdout is one JSON envelope. Exit 0 means transport/domain success, 1 means an error envelope; inspect `commit_status` for pending recovery. The database path must be shared by related calls. Never substitute real account credentials or infer a production rule profile.

## STOCK-U2 下单前检查

输入订单草稿，读取当前账户，检查委托规则、预计费用、可用资金和可卖股数。

对应 Atomic：STOCK-A3 `order-rule-check`、STOCK-A4 `execution-fee-calculate`、STOCK-A5 `order-resource-check`。这些步骤由脚本编排执行，无需让调用者逐个运行 Atomic。

编号仅用于说明对应关系；Agent 调用必须使用完整工具名 `order-precheck`。

data.order 使用计划草稿或明确构造的订单，account_version 必须是当前版本。检查数量、价格、时段、在途冲突，再计算费用和资源需求。该接口只检查，不登记、不冻结；通过后提交时仍会重新校验。

成功返回 required_cash、required_quantity、fee 和 account_version。失败返回 ok=false 与 error.code/details，例如 INSUFFICIENT_CASH、INSUFFICIENT_SELLABLE、INVALID_QUANTITY 或 STALE_SNAPSHOT；不要把失败当作可提交结果。

调用：使用本技能 `scripts/run.py --db <共享数据库路径> --input <请求JSON路径>`；仅首次建立会话时添加 `--init <session.json>`。请求信封包含 schema_version、request_id、simulation_id、account_id 和 data；写操作还必须包含 idempotency_key。金额和价格用十进制字符串，数量用整数股，时间带 +08:00 时区。

先读 [输入契约](assets/input.schema.json) 和 [成功请求](assets/example.json)，再按真实会话状态填写；示例里的订单号、版本和账户不能直接代替当前会话。检查 JSON 的 ok 和 commit_status 后再推进后续业务。这里只操作本地模拟账户及 simulation_fixture 规则。
