---
name: cta-order-plan
description: Persist integer net-lot plans with close-before-open dependencies; do not accept stock weights. Futures simulation only; never route stock weights here.
when_to_use: Explicit cta-order-plan futures simulation requests.
version: 0.2.0
entry: scripts/run.py
allowed_tools:
  - skill_run_script
---

This Upper tool requires `asset_class=FUTURES`, an explicit account/simulation and integer lots. Read [contract](references/contract.md) and [input schema](assets/input.schema.json). Missing or ambiguous contract, trade date, offset or quantity is an error, not permission to guess.

Invoke `skill_run_script` with `scripts/run.py` and `--db cta.sqlite --input assets/example.json`. Direct Python accepts the same arguments; stdout is JSON and exit code is 0 for an envelope with ok=true, 1 for an error. A pending commit_status still requires recovery.

For a fresh planning session, add `--init <session.json>`. For other examples, reproduce the prerequisite state using the project replay script and assets/prepared-state.json. Never copy resources from sibling skills implicitly. Core dependencies are bundled within scripts/.
