---
name: cta-order-query
description: Read order, fills, reservations and account reconciliation status. Futures simulation only; never route stock weights here.
when_to_use: Explicit cta-order-query futures simulation requests.
version: 0.2.0
entry: scripts/run.py
allowed_tools:
  - skill_run_script
---

This Upper tool requires `asset_class=FUTURES`, an explicit account/simulation and integer lots. Read [contract](references/contract.md) and [input schema](assets/input.schema.json). Missing or ambiguous contract, trade date, offset or quantity is an error, not permission to guess.

Invoke `skill_run_script` with `scripts/run.py` and `--db cta.sqlite --input assets/example.json`. Direct Python accepts the same arguments; stdout is JSON and exit code is 0 for an envelope with ok=true, 1 for an error. A pending commit_status still requires recovery.

For a fresh planning session, add `--init <session.json>`. For other examples, reproduce the prerequisite state using the project replay script and assets/prepared-state.json. Never copy resources from sibling skills implicitly. Core dependencies are bundled within scripts/.

## CTA-U6 查订单和成交

层级：Upper。对应 Atomic：CTA-A14 `cta-order-detail`。

CTA 前缀区分期货与股票工具。编号仅用于说明对应关系；Agent 调用必须使用完整工具名 `cta-order-query`。对应关系表示业务职责的分解，包含间接复用的领域计算；实际执行顺序及前置条件见契约，不表示每次调用都会逐项执行所有 Atomic。
