## Why

The 2026-11-11 business review identified lost recovery of Atomic fills, mutable target quantities, stale CTA legs, incomplete activation checks, and missing cancellation/reconciliation transitions. These can report completion prematurely or admit invalid orders in the local simulator.

## What Changes

- Recover persisted fills by event/order association and check consistency before finalization.
- Persist stock normalized targets; make order-plan an idempotent write. Reject changed weights under the same version.
- Bind CTA submissions to the latest accepted target per contract; recheck stock activation against current orders.
- Add explicit REQUEST/CONFIRM/REJECT cancellation phases while retaining omitted-action synchronous mock compatibility.
- Persist fill conflict evidence independently of rejected financial changes and block new submissions until trusted mock reconciliation.
- Reserve stock sell fee shortfalls and introduce explicit versioned CTA reservation policies.
- Regenerate all standalone skills, contracts and exports; include review oracles in normal regression discovery.

## Capabilities

### New Capabilities
- `business-invariants`: Recovery, target stability, cancellation races, durable reconciliation and resource policy acceptance.

### Modified Capabilities

## Impact

Both runtime engines, request/result schemas, asset generators, 45 standalone tools, tests and review evidence. Stock order-plan now requires an idempotency key. No live account integration or mutation of the user's simulation database.
