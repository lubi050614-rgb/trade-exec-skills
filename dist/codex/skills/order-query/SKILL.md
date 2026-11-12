---
name: order-query
description: 查询订单与成交。输入订单号，返回委托量、已成交量、已撤数量、仍在挂单的数量和逐笔成交明细。
allowed-tools:
  - skill_run_script
metadata:
  version: "0.1.0"
  entry: scripts/run.py
  when_to_use: Explicit order-query stock simulation requests.
---

Use this independent Upper interface for `order-query`. Read [contract](references/contract.md) for its required inputs and preconditions. This tool uses synthetic stock rules and an authoritative mock account only.

Call `skill_run_script` with `scripts/run.py` and arguments `--db simulation.sqlite --input assets/example.json`. For a fresh session add `--init <session.json>` using an exchange fixture from the plugin examples. Run via Python directly with the same arguments when skill_run_script is unavailable.

Stdout is one JSON envelope. Exit 0 means transport/domain success, 1 means an error envelope; inspect `commit_status` for pending recovery. The database path must be shared by related calls. Never substitute real account credentials or infer a production rule profile.

## STOCK-U6 查询订单与成交

输入订单号，返回委托量、已成交量、已撤数量、仍在挂单的数量和逐笔成交明细。

对应 Atomic：STOCK-A8 `order-state-read`、STOCK-A15 `execution-fill-list`。这些步骤由脚本编排执行，无需让调用者逐个运行 Atomic。

编号仅用于说明对应关系；Agent 调用必须使用完整工具名 `order-query`。

data.order_id 指定订单，可用 offset/limit 分页读取成交。该接口读取订单现状及逐笔成交，不推进撮合或修复记账。

order.quantity/filled_quantity/canceled_quantity/leaves_quantity 分别为委托、成交、撤销和剩余数量；order 还包含状态及版本。fills 返回数量、价格、费用与记账状态，返回 total 和 next_offset；用 next_offset 作为下一页 offset，为 null 时结束。account 是当前账户快照；ACCOUNTING_PENDING 表示账户仍有待记账成交。

调用：使用本技能 `scripts/run.py --db <共享数据库路径> --input <请求JSON路径>`；仅首次建立会话时添加 `--init <session.json>`。请求信封包含 schema_version、request_id、simulation_id、account_id 和 data；写操作还必须包含 idempotency_key。金额和价格用十进制字符串，数量用整数股，时间带 +08:00 时区。

先读 [输入契约](assets/input.schema.json) 和 [成功请求](assets/example.json)，再按真实会话状态填写；示例里的订单号、版本和账户不能直接代替当前会话。检查 JSON 的 ok 和 commit_status 后再推进后续业务。这里只操作本地模拟账户及 simulation_fixture 规则。
