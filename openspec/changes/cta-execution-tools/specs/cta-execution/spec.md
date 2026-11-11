## ADDED Requirements

### Requirement: Explicit futures targets and persisted dependencies
The system SHALL accept integer net lots with explicit FUTURES routing, reject hedged positions, and persist close-before-open plan dependencies.

#### Scenario: Long three reverses to short two
- **GIVEN** three long lots and target minus two
- **WHEN** the plan closes only two lots
- **THEN** one long SHALL remain and the two-lot short opening SHALL remain blocked until the last close is filled and booked.

### Requirement: Atomic reservation and causal matching
The system SHALL atomically register and freeze margin, fees, buffers or specific today/yesterday close lots using authoritative rules and versions; it SHALL match only eligible completed bars with shared capacity.

#### Scenario: Competing close orders
- **GIVEN** two orders competing for the same closeable lots
- **WHEN** registration is attempted
- **THEN** no lot SHALL be frozen twice and a failed registration SHALL create neither order nor reservation.

### Requirement: Durable idempotent fill lifecycle
The system SHALL persist fills before order progression, bookkeeping and release, reject fabricated events and block trading during recovery.

#### Scenario: Restart after each pipeline stage
- **GIVEN** an interruption after record, state update, booking or release
- **WHEN** the original market event is recovered
- **THEN** exactly one economic effect SHALL occur and the resulting account and reservations SHALL reconcile.

### Requirement: Calendar-based trading days
The system SHALL determine trade_date from explicit contract session intervals rather than natural-day arithmetic.

#### Scenario: Night before a holiday gap
- **GIVEN** a configured night interval belonging to the next listed trading day
- **WHEN** a timestamp in that interval is queried
- **THEN** its explicit trading day SHALL be returned without inferring adjacent dates or settling at midnight.

### Requirement: Daily marked-to-market settlement
The system SHALL require explicit previous and current settlement prices, apply only incremental unbooked PnL, expire DAY leaves and migrate today lots once with versioned idempotency.

#### Scenario: Long and short carried across settlement
- **GIVEN** a hand-calculable long or short position and explicit settlement prices
- **WHEN** settlement is applied and retried
- **THEN** equity SHALL bridge from opening equity plus realized and holding PnL minus fees, and the retry SHALL not change balances again.

### Requirement: Actual roll progress
The system SHALL link old close and new open plans and derive progress from booked fills.

#### Scenario: Old close two and new open one
- **GIVEN** a two-lot roll with two old lots closed and one new lot opened
- **WHEN** progress is read
- **THEN** one lot SHALL be reported unconnected and the roll SHALL not be complete.
