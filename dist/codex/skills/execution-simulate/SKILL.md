---
name: execution-simulate
description: 模拟成交并记账。输入已完成行情，读取活动订单，按撮合规则计算价格、数量和费用，记录成交并更新订单、现金和持仓。
allowed-tools:
  - skill_run_script
metadata:
  version: "0.1.0"
  entry: scripts/run.py
  when_to_use: Explicit execution-simulate stock simulation requests.
---

Use this independent Upper interface for `execution-simulate`. Read [contract](references/contract.md) for its required inputs and preconditions. This tool uses synthetic stock rules and an authoritative mock account only.

Call `skill_run_script` with `scripts/run.py` and arguments `--db simulation.sqlite --input assets/example.json`. For a fresh session add `--init <session.json>` using an exchange fixture from the plugin examples. Run via Python directly with the same arguments when skill_run_script is unavailable.

Stdout is one JSON envelope. Exit 0 means transport/domain success, 1 means an error envelope; inspect `commit_status` for pending recovery. The database path must be shared by related calls. Never substitute real account credentials or infer a production rule profile.

## STOCK-U5 模拟成交并记账

输入已完成行情，读取活动订单，按撮合规则计算价格、数量和费用，记录成交并更新订单、现金和持仓。

对应 Atomic：STOCK-A4 `execution-fee-calculate`、STOCK-A8 `order-state-read`、STOCK-A10 `order-release-reserve`、STOCK-A11 `execution-match`、STOCK-A12 `execution-fill-record`、STOCK-A13 `order-apply-fill`、STOCK-A14 `account-apply-fill`。这些步骤由脚本编排执行，无需让调用者逐个运行 Atomic。

编号仅用于说明对应关系；Agent 调用必须使用完整工具名 `execution-simulate`。

明确 bar、visible_at、participation_rate 与 slippage；行情必须已完成、未复权且与会话频率一致。按订单优先级共享成交容量：读取订单 → 撮合 → 登记成交 → 更新订单 → 账户入账 → 释放多余占用。费用按订单累计金额计算增量，最低佣金不对每次部分成交重复收取；一笔成交只入账一次。

COMMITTED 返回本事件 fills 和 account；没有成交时 fills 可以为空。ACCOUNTING_PENDING/RECOVERY_REQUIRED 表示未完成：保留相同 bar/model、换新 idempotency_key、去掉 fail_after 后恢复；旧键只会返回旧响应。fail_after 仅用于测试。end_of_day 会撤销并释放到期 DAY 单。

调用：使用本技能 `scripts/run.py --db <共享数据库路径> --input <请求JSON路径>`；仅首次建立会话时添加 `--init <session.json>`。请求信封包含 schema_version、request_id、simulation_id、account_id 和 data；写操作还必须包含 idempotency_key。金额和价格用十进制字符串，数量用整数股，时间带 +08:00 时区。

先读 [输入契约](assets/input.schema.json) 和 [成功请求](assets/example.json)，再按真实会话状态填写；示例里的订单号、版本和账户不能直接代替当前会话。检查 JSON 的 ok 和 commit_status 后再推进后续业务。这里只操作本地模拟账户及 simulation_fixture 规则。
