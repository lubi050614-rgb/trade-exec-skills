---
name: order-open-quantity
description: Execute the order-open-quantity stock simulation interface using explicit JSON inputs and a persistent mock session.
when_to_use: Explicit order-open-quantity requests for simulated stock execution.
version: 0.1.0
entry: scripts/run.py
allowed_tools:
  - skill_run_script
---

Use this independent Atomic interface for `order-open-quantity`. Read [contract](references/contract.md) for its required inputs and preconditions. This tool uses synthetic stock rules and an authoritative mock account only.

Call `skill_run_script` with `scripts/run.py` and arguments `--db simulation.sqlite --input assets/example.json`. For a fresh session add `--init <session.json>` using an exchange fixture from the plugin examples. Run via Python directly with the same arguments when skill_run_script is unavailable.

Stdout is one JSON envelope. Exit 0 means transport/domain success, 1 means an error envelope; inspect `commit_status` for pending recovery. The database path must be shared by related calls. Never substitute real account credentials or infer a production rule profile.
