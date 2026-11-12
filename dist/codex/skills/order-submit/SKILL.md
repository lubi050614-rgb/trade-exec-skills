---
name: order-submit
description: 提交订单。接收订单草稿，重新校验当时可用资源，登记订单并占用资金或股票；重复请求返回原结果。
allowed-tools:
  - skill_run_script
metadata:
  version: "0.1.0"
  entry: scripts/run.py
  when_to_use: Explicit order-submit stock simulation requests.
---

Use this independent Upper interface for `order-submit`. Read [contract](references/contract.md) for its required inputs and preconditions. This tool uses synthetic stock rules and an authoritative mock account only.

Call `skill_run_script` with `scripts/run.py` and arguments `--db simulation.sqlite --input assets/example.json`. For a fresh session add `--init <session.json>` using an exchange fixture from the plugin examples. Run via Python directly with the same arguments when skill_run_script is unavailable.

Stdout is one JSON envelope. Exit 0 means transport/domain success, 1 means an error envelope; inspect `commit_status` for pending recovery. The database path must be shared by related calls. Never substitute real account credentials or infer a production rule profile.

## STOCK-U3 提交订单

接收订单草稿，重新校验当时可用资源，登记订单并占用资金或股票；重复请求返回原结果。

对应 Atomic：STOCK-A3 `order-rule-check`、STOCK-A4 `execution-fee-calculate`、STOCK-A5 `order-resource-check`、STOCK-A6 `order-register`、STOCK-A7 `order-reserve`。这些步骤由脚本编排执行，无需让调用者逐个运行 Atomic。

编号仅用于说明对应关系；Agent 调用必须使用完整工具名 `order-submit`。

data.order 使用草稿，data.client_order_id 是唯一业务请求号。重新执行规则、费用及资源检查；登记为 PENDING_RESERVATION，预留成功后激活为 NEW。登记与预留在同一 SQLite 事务内，任一步失败整体回滚。每笔草稿分别提交，使用最新 account_version。

返回 order、commit_status 和 completed_steps。重试必须保留原 idempotency_key、client_order_id 和完全相同的 data，返回原订单；修改请求使用新键，同一 client_order_id 不能用于另一笔订单。提交不代表成交。

调用：使用本技能 `scripts/run.py --db <共享数据库路径> --input <请求JSON路径>`；仅首次建立会话时添加 `--init <session.json>`。请求信封包含 schema_version、request_id、simulation_id、account_id 和 data；写操作还必须包含 idempotency_key。金额和价格用十进制字符串，数量用整数股，时间带 +08:00 时区。

先读 [输入契约](assets/input.schema.json) 和 [成功请求](assets/example.json)，再按真实会话状态填写；示例里的订单号、版本和账户不能直接代替当前会话。检查 JSON 的 ok 和 commit_status 后再推进后续业务。这里只操作本地模拟账户及 simulation_fixture 规则。
