## Context

The two engines use SQLite transactions containing JSON session state. Atomic operations and Upper orchestration share the same facts. Original review evidence is retained under reviews/2026-11-11-business-logic.

## Goals / Non-Goals

Goals: close R01–R08 for the supported local simulator and make policy differences explicit.
Non-goals: live broker integration, arbitrary cumulative order-status callback ingestion, official exchange-rule verification, and automatic correction of conflicting financial facts.

## Decisions

- Locate fills by market_event_id and order_id: the record API already enforces at most one fill per order/event. Require consistent booked state before marking an event done.
- Stock target/version stores normalized quantities and source snapshot. Current weights and snapshots remain current validation inputs; reference price may refresh an execution draft but cannot resize the fixed target. Changed target weights require a new version. Planning now has durable effects and requires idempotency.
- CTA active target is per session/account/contract, including target identity and version. A newer accepted plan prevents old unsubmitted legs from activating, including when the new plan has no legs. Existing open orders must satisfy existing conflict checks before replacement planning succeeds.
- Stock reserve calls the same precheck as registration using the fresh account version inside its transaction.
- Explicit cancellation action REQUEST keeps status/leaves/reservations, REJECT clears cancel_pending, and CONFIRM applies cancellation and release. Omitted action preserves the existing synchronous mock meaning. Asynchronous callers must specify REQUEST. Atomic cancellation remains a confirmation primitive. CAS prevents stale confirmations from overwriting crossing fills.
- FILL_CONFLICT rolls back financial effects, then writes conflict evidence in a fresh transaction. Queries and canonical fill recovery remain available. New submissions reject RECONCILE_REQUIRED. Trusted resolve_reconciliation requires canonical-fill hash, conflict count, account version and an independently retained receipt; it is not an Agent tool and is not production reconciliation.
- Sell fee coverage reserves the upper-bound remaining fee minus the minimum possible executable slice proceeds, floored at zero. Booking consumes only actual fee shortfall; release retains the remaining conservative reserve.
- CTA UPPER_BOUND_V1 remains the default conservative short-opening policy. ORDER_PRICE_V1 explicitly selects the test-v1 opening-margin basis. Fees remain upper-bound conservative; matching cannot consume the budget needed by retained leaves.

## Risks / Trade-offs

Default cancellation remains synchronous for compatibility: agents need the documented explicit action for asynchronous cases. Existing databases receive added state lazily; this does not reconstruct historical target normalizations that were never stored. Reconciliation evidence is local mock evidence, not proof of a broker ledger match. Cumulative callbacks awaiting missing trade details, exchange cancellation blackout windows, and general broker callback normalization remain outside this change.

## Validation

Run baseline tests plus 11 review oracles and additional recovery/cancellation/reconciliation/resource regressions. Preserve original observations and original review harness; new observations use a separate file. Build skills and packages, validate schemas/standalone entrypoints, run official OpenSpec strict validation and Codex skill validation.
