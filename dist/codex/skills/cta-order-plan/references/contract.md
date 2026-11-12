# cta-order-plan

Responsibility: Persist integer net-lot plans with close-before-open dependencies; do not accept stock weights. Layer: Upper. This interface does not connect to a live broker, use stock weight semantics or assume official exchange rules.

## CTA-U1 生成调仓计划

层级：Upper。对应 Atomic：CTA-A1 `cta-contract-spec`、CTA-A2 `cta-trading-session`、CTA-A3 `cta-position-gap`、CTA-A4 `cta-offset-split`。

CTA 前缀区分期货与股票工具。编号仅用于说明对应关系；Agent 调用必须使用完整工具名 `cta-order-plan`。对应关系表示业务职责的分解，包含间接复用的领域计算；实际执行顺序及前置条件见契约，不表示每次调用都会逐项执行所有 Atomic。


Business invariants: targets keep their normalized quantity for the same version; newer CTA targets supersede earlier unsubmitted legs. Stock order-plan persists normalization and requires an idempotency key. Cancel action REQUEST preserves live leaves and resources, REJECT clears only cancel_pending, CONFIRM cancels the remaining leaves and releases after bookkeeping. Omitted action retains the legacy synchronous mock confirmation. Use REQUEST explicitly for asynchronous simulations. Fill conflicts persist RECONCILE and block new submissions; valid recorded fills and queries remain available. Clearing RECONCILE requires the trusted runtime resolve_reconciliation boundary with independent evidence and CAS checks, not an agent tool. CTA reservation_policy defaults to UPPER_BOUND_V1; ORDER_PRICE_V1 is an explicit fixture policy, and fills exceeding the reserved budget (including retained leaves) do not match. These are local simulation contracts, not live broker callbacks.

Contracts: [input](../assets/input.schema.json), [output](../assets/output.schema.json). Executed fixtures: [request](../assets/example.json), [success](../assets/success.json), [failure request](../assets/failure-request.json), [failure](../assets/failure.json).

Writes require a nonempty idempotency_key: the same tool/key/payload returns the original result; changed payload returns IDEMPOTENCY_CONFLICT. All writes and resource freezes use SQLite transactions.

Preconditions: initialized FUTURES account, configured explicit calendar and contract profile; persisted plan leg and current account version before registration; persisted market event before recording; persisted fill before state update and booking; current order version before state/release. Opening dependencies must be completely filled and booked. Registration and freeze either both commit or neither does.

Atomic order: cta-contract-spec → cta-trading-session → cta-position-gap → cta-offset-split.

Cancellation must be followed by release. Fill recovery sequence is record → state update → book → release. ACCOUNTING_PENDING/RECOVERY_REQUIRED blocks dependent trading. To recover an interrupted simulation, retry the same bar/model with a new idempotency key and without fail_after. Reusing the old key returns the original pending response. Completed event retries do not consume capacity twice.

Errors include ASSET_CLASS_MISMATCH/INVALID_REQUEST, PLAN_LEG_NOT_FOUND, STALE_SNAPSHOT, STALE_ORDER_VERSION, DEPENDENCY_NOT_BOOKED, INSUFFICIENT_MARGIN, INSUFFICIENT_CLOSEABLE, UNSUPPORTED_HEDGED_POSITION, OUTSIDE_TRADING_SESSION, ACCOUNTING_PENDING, RELEASE_PENDING, SETTLEMENT_CONFLICT and MISSING_SETTLEMENT_PRICE. These are simulation-domain failures; no internal step requires manual approval.

Reproduce: `python scripts/replay_cta_example.py --tool cta-order-plan` from the source/plugin project. Prepared states are test-only trusted local fixtures and are not accepted by public trading tools.
