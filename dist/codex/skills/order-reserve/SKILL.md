---
name: order-reserve
description: Execute the order-reserve stock simulation interface using explicit JSON inputs and a persistent mock session.
allowed-tools:
  - skill_run_script
metadata:
  version: "0.1.0"
  entry: scripts/run.py
  when_to_use: Explicit order-reserve stock simulation requests.
---

Use this independent Atomic interface for `order-reserve`. Read [contract](references/contract.md) for its required inputs and preconditions. This tool uses synthetic stock rules and an authoritative mock account only.

Call `skill_run_script` with `scripts/run.py` and arguments `--db simulation.sqlite --input assets/example.json`. For a fresh session add `--init <session.json>` using an exchange fixture from the plugin examples. Run via Python directly with the same arguments when skill_run_script is unavailable.

Stdout is one JSON envelope. Exit 0 means transport/domain success, 1 means an error envelope; inspect `commit_status` for pending recovery. The database path must be shared by related calls. Never substitute real account credentials or infer a production rule profile.
## STOCK-A7

层级：Atomic。编号仅用于说明对应关系；Agent 调用必须使用完整工具名 `order-reserve`。
