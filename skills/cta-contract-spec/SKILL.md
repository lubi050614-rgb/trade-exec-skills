---
name: cta-contract-spec
description: Read the configured contract and trade-date rule profile. Futures simulation only; never route stock weights here.
when_to_use: Explicit cta-contract-spec futures simulation requests.
version: 0.2.0
entry: scripts/run.py
allowed_tools:
  - skill_run_script
---

This Atomic tool requires `asset_class=FUTURES`, an explicit account/simulation and integer lots. Read [contract](references/contract.md) and [input schema](assets/input.schema.json). Missing or ambiguous contract, trade date, offset or quantity is an error, not permission to guess.

Invoke `skill_run_script` with `scripts/run.py` and `--db cta.sqlite --input assets/example.json`. Direct Python accepts the same arguments; stdout is JSON and exit code is 0 for an envelope with ok=true, 1 for an error. A pending commit_status still requires recovery.

For a fresh planning session, add `--init <session.json>`. For other examples, reproduce the prerequisite state using the project replay script and assets/prepared-state.json. Never copy resources from sibling skills implicitly. Core dependencies are bundled within scripts/.

## CTA-A1 查合约规则

层级：Atomic。负责单个领域步骤。编号仅用于说明对应关系；Agent 调用必须使用完整工具名 `cta-contract-spec`。
