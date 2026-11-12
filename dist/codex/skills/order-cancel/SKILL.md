---
name: order-cancel
description: 撤销余单。输入订单号及预期版本，撤销尚未成交部分并释放相应资源，保留既有成交。
allowed-tools:
  - skill_run_script
metadata:
  version: "0.1.0"
  entry: scripts/run.py
  when_to_use: Explicit order-cancel stock simulation requests.
---

Use this independent Upper interface for `order-cancel`. Read [contract](references/contract.md) for its required inputs and preconditions. This tool uses synthetic stock rules and an authoritative mock account only.

Call `skill_run_script` with `scripts/run.py` and arguments `--db simulation.sqlite --input assets/example.json`. For a fresh session add `--init <session.json>` using an exchange fixture from the plugin examples. Run via Python directly with the same arguments when skill_run_script is unavailable.

Stdout is one JSON envelope. Exit 0 means transport/domain success, 1 means an error envelope; inspect `commit_status` for pending recovery. The database path must be shared by related calls. Never substitute real account credentials or infer a production rule profile.

## STOCK-U4 撤销余单

输入订单号及预期版本，撤销尚未成交部分并释放相应资源，保留既有成交。

对应 Atomic：STOCK-A8 `order-state-read`、STOCK-A9 `order-cancel-remainder`、STOCK-A10 `order-release-reserve`。这些步骤由脚本编排执行，无需让调用者逐个运行 Atomic。

编号仅用于说明对应关系；Agent 调用必须使用完整工具名 `order-cancel`。

先查询当前订单与 version。默认或 action=CONFIRM 同步确认撤单，撤销 leaves_quantity，随后释放剩余占用。异步模拟用 REQUEST 保留在途量和冻结；成交入账后重新查询，用最新 expected_version 执行 CONFIRM，或 REJECT 清除等待标记。

确认撤销返回 order、release 和本次 canceled_quantity，已成交量不回退。REQUEST/REJECT 的 release=null，尚未确认撤销，也不返回本次撤销量。遇到 ACCOUNTING_PENDING 先恢复成交入账，再以当前版本撤单。

调用：使用本技能 `scripts/run.py --db <共享数据库路径> --input <请求JSON路径>`；仅首次建立会话时添加 `--init <session.json>`。请求信封包含 schema_version、request_id、simulation_id、account_id 和 data；写操作还必须包含 idempotency_key。金额和价格用十进制字符串，数量用整数股，时间带 +08:00 时区。

先读 [输入契约](assets/input.schema.json) 和 [成功请求](assets/example.json)，再按真实会话状态填写；示例里的订单号、版本和账户不能直接代替当前会话。检查 JSON 的 ok 和 commit_status 后再推进后续业务。这里只操作本地模拟账户及 simulation_fixture 规则。
