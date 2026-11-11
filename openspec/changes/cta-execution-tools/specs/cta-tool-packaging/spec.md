## ADDED Requirements

### Requirement: Independent CTA interfaces
The project SHALL expose eight CTA Upper and sixteen CTA Atomic tools with schemas, examples, contracts, real scripts and bundled shared dependencies alongside the existing twenty-one stock tools.

#### Scenario: Agent selects the wrong asset domain
- **GIVEN** stock weights or a STOCK asset_class sent to a CTA tool
- **WHEN** the request is validated
- **THEN** it SHALL fail without mutating futures account state.

#### Scenario: Export runs outside the repository
- **GIVEN** an extracted CTA skill archive
- **WHEN** its script is executed with a valid fixture
- **THEN** it SHALL return JSON without importing sibling skills or relying on the repository location.
