## ADDED Requirements

### Requirement: Durable event recovery
The simulator SHALL recover canonical fills by event and order association and SHALL NOT finalize with unbooked fills.

#### Scenario: Arbitrary fill identity after restart
- **WHEN** an Atomic fill with an arbitrary ID persists before process restart
- **THEN** Upper replay SHALL book it once and return the same completed result on retry.

### Requirement: Stable execution targets
Stock normalization SHALL remain fixed for a target version, and CTA submission SHALL require the current accepted target for its contract.

#### Scenario: Fees reduce stock NAV
- **WHEN** a completed target is replanned with the same version after fees reduce NAV
- **THEN** no fee-driven reverse trade SHALL be generated.

#### Scenario: New flat CTA target
- **WHEN** a newer flat target supersedes an old reversal plan
- **THEN** the old unsubmitted opening leg SHALL be rejected.

### Requirement: Activation revalidation
Stock reservation SHALL revalidate current active-order conflicts inside the reservation transaction.

#### Scenario: Competing pending registrations
- **WHEN** incompatible pending orders are registered and one activates
- **THEN** the other SHALL fail activation without acquiring resources.

### Requirement: Explicit asynchronous cancellation
REQUEST SHALL preserve leaves and reservations, REJECT SHALL clear only the cancellation request, and CONFIRM SHALL cancel remaining leaves using current order version checks.

#### Scenario: Crossing fill
- **WHEN** a valid fill arrives between REQUEST and CONFIRM
- **THEN** it SHALL book normally and confirmation SHALL release only the remaining reservation.

### Requirement: Durable conflict reconciliation
Conflicting fill evidence SHALL persist without changing canonical finances and SHALL block new submissions until trusted reconciliation completes.

#### Scenario: Conflicting duplicate fill
- **WHEN** the same fill ID is reused with conflicting content
- **THEN** FILL_CONFLICT SHALL be returned, RECONCILE SHALL persist, and new submissions SHALL fail.

### Requirement: Explicit resource policies
Stock sells SHALL reserve fee shortfalls, and CTA opening reservations SHALL apply an explicit versioned policy with conservative default and no unfunded fills.

#### Scenario: Odd lot fee shortfall
- **WHEN** a one-share sale at 1 has fee 5 and available cash zero
- **THEN** submission SHALL fail before registration or reservation commits.

#### Scenario: Test-v1 short opening
- **WHEN** ORDER_PRICE_V1 selects two short lots at 4000, multiplier 10, margin rate 0.1 and per-lot fee 5
- **THEN** opening reservation SHALL be 8010 and a higher-price partial fill SHALL NOT consume the reserve required by remaining leaves.
