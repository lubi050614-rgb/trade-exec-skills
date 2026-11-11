# order-submit

Layer: Upper. 职责：在同一 SQLite 事务中重新检查、登记并预留单笔订单。非职责：不承诺组合批次原子成交，不提前使用未成交卖单收入。

Business invariants: targets keep their normalized quantity for the same version; newer CTA targets supersede earlier unsubmitted legs. Stock order-plan persists normalization and requires an idempotency key. Cancel action REQUEST preserves live leaves and resources, REJECT clears only cancel_pending, CONFIRM cancels the remaining leaves and releases after bookkeeping. Omitted action retains the legacy synchronous mock confirmation. Use REQUEST explicitly for asynchronous simulations. Fill conflicts persist RECONCILE and block new submissions; valid recorded fills and queries remain available. Clearing RECONCILE requires the trusted runtime resolve_reconciliation boundary with independent evidence and CAS checks, not an agent tool. CTA reservation_policy defaults to UPPER_BOUND_V1; ORDER_PRICE_V1 is an explicit fixture policy, and fills exceeding the reserved budget (including retained leaves) do not match. These are local simulation contracts, not live broker callbacks.

Inputs are defined by [input schema](../assets/input.schema.json); outputs by [output schema](../assets/output.schema.json). Examples: [request](../assets/example.json), [success](../assets/success.json), [failure request](../assets/failure-request.json), [failure](../assets/failure.json). Success fixtures are executed by scripts/build_assets.py using a fresh initialized session and the legal prerequisite steps.

Persistent writes require idempotency_key. Same key and payload return the previous result; changed payload returns IDEMPOTENCY_CONFLICT.

Sequence: order-rule-check → execution-fee-calculate → order-resource-check → order-register → order-reserve. Upper reuses the same domain functions as independently invoked Atomic tools.

Preconditions: initialized simulation/account; configured fixture instrument; current order/account versions for applicable writes; persisted market event before recording fills; persisted fill before order/account application. Order registration remains PENDING_RESERVATION until reserve succeeds. Direct Atomic cancel must be followed by release. A pending fill blocks new plans, submissions and cancellation until order application and booking recover.

Recovery: retry using the original key for completed operations; use a new key after correcting a rejected request. Pending simulation results require a new key and the same bar/model with fail_after omitted. Do not treat ACCOUNTING_PENDING or RECOVERY_REQUIRED as completed execution. SQLite serializes reservations and capacity writes. All state is local mock state.

Errors include INVALID_REQUEST, IDEMPOTENCY_CONFLICT, STALE_ORDER_VERSION, STALE_SNAPSHOT, INSUFFICIENT_CASH, INSUFFICIENT_SELLABLE, INVALID_QUANTITY, INVALID_PRICE, UNSUPPORTED_RULE_PROFILE, ACCOUNTING_PENDING, MARKET_EVENT_NOT_FOUND and FILL_NOT_FOUND. No internal step needs manual approval.
