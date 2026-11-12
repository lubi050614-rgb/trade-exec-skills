---
name: order-plan
description: 生成订单草稿。输入完整目标权重、当前账户快照和参考价；读取当前持仓与已有挂单，计算每只股票还需买卖多少股。
allowed-tools:
  - skill_run_script
metadata:
  version: "0.1.0"
  entry: scripts/run.py
  when_to_use: Explicit order-plan stock simulation requests.
---

Use this independent Upper interface for `order-plan`. Read [contract](references/contract.md) for its required inputs and preconditions. This tool uses synthetic stock rules and an authoritative mock account only.

Call `skill_run_script` with `scripts/run.py` and arguments `--db simulation.sqlite --input assets/example.json`. For a fresh session add `--init <session.json>` using an exchange fixture from the plugin examples. Run via Python directly with the same arguments when skill_run_script is unavailable.

Stdout is one JSON envelope. Exit 0 means transport/domain success, 1 means an error envelope; inspect `commit_status` for pending recovery. The database path must be shared by related calls. Never substitute real account credentials or infer a production rule profile.

## STOCK-U1 生成订单草稿

输入完整目标权重、当前账户快照和参考价；读取当前持仓与已有挂单，计算每只股票还需买卖多少股。

对应 Atomic：STOCK-A1 `order-open-quantity`、STOCK-A2 `order-target-gap`。这些步骤由脚本编排执行，无需让调用者逐个运行 Atomic。

编号仅用于说明对应关系；Agent 调用必须使用完整工具名 `order-plan`。

先核对 account_snapshot_id、as_of、total_assets 和 current_weight。targets 必须覆盖当前持仓及活动挂单；清仓标的用 target_weight=0 表达。按规则把目标权重转换为整数股数，再扣除在途买卖剩余量。差额为零不生成订单。同一 target_id/target_version 固定目标股数；改变目标权重必须增加版本。

drafts 是可传给预检/提交的订单草稿；normalization 说明取整偏差。检查 funding_sufficient、requires_sell_proceeds 和 cash_buffer；依赖卖出收入时先等待实际成交入账，再用当前账户版本提交买单。计划本身不冻结资金或股票。

调用：使用本技能 `scripts/run.py --db <共享数据库路径> --input <请求JSON路径>`；仅首次建立会话时添加 `--init <session.json>`。请求信封包含 schema_version、request_id、simulation_id、account_id 和 data；写操作还必须包含 idempotency_key。金额和价格用十进制字符串，数量用整数股，时间带 +08:00 时区。

先读 [输入契约](assets/input.schema.json) 和 [成功请求](assets/example.json)，再按真实会话状态填写；示例里的订单号、版本和账户不能直接代替当前会话。检查 JSON 的 ok 和 commit_status 后再推进后续业务。这里只操作本地模拟账户及 simulation_fixture 规则。
