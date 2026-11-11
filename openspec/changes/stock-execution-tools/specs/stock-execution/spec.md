## ADDED Requirements

### Requirement: Complete portfolio normalization
The system SHALL validate full portfolio coverage, unique explicit instrument IDs, matching authoritative asset snapshots, decimal weights summing to at most one, known unadjusted reference prices and current-weight reconciliation; it SHALL freeze rounded target quantities and report deviations and cash requirements.

#### Scenario: Existing compatible leaves reduce the new order
- **GIVEN** target 1000 shares, actual 400 shares and a confirmed compatible BUY with 200 leaves
- **WHEN** a consistent full portfolio is planned
- **THEN** the new draft SHALL buy 400 shares and keep the compatible order.

#### Scenario: Invalid or conflicting inputs
- **GIVEN** uncovered holdings, duplicate IDs, weights above one, inconsistent snapshots, nonpositive prices or conflicting target versions
- **WHEN** planning is requested
- **THEN** the request SHALL fail with a machine-readable code without changing state.

### Requirement: Atomic resources and order lifecycle
The system SHALL reserve cash and sellable quantities atomically using expected versions, maintain quantity conservation and release only unused reservations after fills or cancellation.

#### Scenario: Concurrent reservations compete
- **GIVEN** two pending orders each affordable alone but not together
- **WHEN** both attempt reservation using the same account version
- **THEN** only one SHALL succeed and the other SHALL fail without becoming matchable.

#### Scenario: Partial fill cancellation
- **GIVEN** an order with a booked partial fill
- **WHEN** its remainder is canceled and released
- **THEN** the fill SHALL remain, leaves SHALL be zero and unused resources SHALL be released.

### Requirement: Deterministic causal matching
The system SHALL use completed unadjusted bars, explicit fixture sessions and frequency, conservative open-price LIMIT matching, protected MARKET matching, shared participation capacity and deterministic ordering.

#### Scenario: Signal bar cannot fill the new order
- **GIVEN** an order generated at a completed signal bar's end
- **WHEN** that signal bar is supplied for matching
- **THEN** no fill SHALL occur; a later eligible bar is required.

#### Scenario: Capacity and unsuitable bars
- **GIVEN** multiple orders for one instrument and bar
- **WHEN** matching occurs
- **THEN** total fills SHALL not exceed shared legal participation capacity; zero-volume, untradable and price-protected bars SHALL not force fills.

### Requirement: Durable idempotent accounting and recovery
The system SHALL durably record fills before order progression and account booking, reject changed idempotent payloads, prevent duplicate economic effects and block new dependent trading while recovery is pending.

#### Scenario: Restart after interrupted pipeline
- **GIVEN** a failure after fill record, order apply or account apply
- **WHEN** the process restarts and the original event is retried without the injected failure
- **THEN** exactly one economic effect SHALL result and residual resources SHALL be released.

#### Scenario: Duplicate completed market event
- **GIVEN** an already completed event
- **WHEN** the same event and model are retried with a new request key
- **THEN** the stored result SHALL be returned without additional capacity, fills or account version changes.

### Requirement: Fixture-specific settlement and expiry
The system SHALL keep same-day buys unsellable, advance eligible lots only using explicit configured trading dates and expire DAY leaves without fabricating fills.

#### Scenario: Next configured trade date
- **GIVEN** a booked purchase and remaining DAY leaves
- **WHEN** a bar for the next configured trading date is advanced
- **THEN** eligible purchased lots SHALL settle and prior DAY leaves SHALL expire and release resources.
