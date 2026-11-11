## ADDED Requirements

### Requirement: Independent stock tool interfaces
The plugin SHALL expose exactly six Upper and fifteen Atomic stock tools, each with SKILL.md, scripts/run.py, scripts/engine.py, schemas, a request example, errors and a contract; Upper SHALL reuse the Atomic domain implementation.

#### Scenario: Standalone exported execution
- **GIVEN** a tool folder copied outside the source repository
- **WHEN** scripts/run.py is invoked with a valid fixture session and JSON request
- **THEN** the shared core SHALL import locally and return a structured JSON result without sibling skill imports.

### Requirement: Exchange fixtures and honest integration boundaries
The plugin SHALL provide synthetic SSE, SZSE and BSE account/target/rule/day/minute fixtures, explicit adapter boundaries and a record of unavailable external checks.

#### Scenario: Each exchange closes a simulation
- **GIVEN** any provided exchange fixture
- **WHEN** planning, submission, daily or minute matching and query run
- **THEN** orders, fills, account and reservations SHALL agree, with fixture rules clearly identified as synthetic.
