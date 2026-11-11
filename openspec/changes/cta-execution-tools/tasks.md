## 1. Contracts and design
- [x] 1.1 Freeze CTA scope, proposal, design and scenario specs.
- [x] 1.2 Define all 24 strict contracts and Agent routing boundaries (all_contracts_success_and_standalone_entries, hedged_positions_and_stock_payload_rejected).

## 2. Domain implementation
- [x] 2.1 Implement authoritative mock account, versioned reservations, contract rules and explicit sessions (concurrent_close_reservations_do_not_double_freeze, actual_night_execution_uses_explicit_future_trade_date).
- [x] 2.2 Implement target gap, close/open splitting and persisted dependencies (reverse_partial_close_then_open_and_actual_net, stale_preplanned_target_cannot_overtrade).
- [x] 2.3 Implement registration, cancellation, conservative matching, durable fills and recovery (registration_and_reservation_all_or_none, recovery_four_stages_after_restart).
- [x] 2.4 Implement marked-to-market settlement, equity bridge and idempotent day migration (long_short_settlement_and_conflicting_replay, second_day_uses_actual_previous_settlement_once).
- [x] 2.5 Implement linked roll plans and booked-fill progress (roll_partial_new_fill_reports_unconnected_exposure, roll_cannot_reuse_unlinked_opening_plan).

## 3. Packaging and verification
- [x] 3.1 Generate 24 independent native skills and Codex projections with successful examples (build_cta_assets and 24 real subprocess replays).
- [x] 3.2 Extend combined catalog, plugin manifest, package and monitoring to all 45 tools (catalog/manifest count, scripts/package.py and scripts/verify.py).
- [x] 3.3 Pass CTA acceptance scenarios and existing stock regression (42 tests: CTA 24 + stock 18).
- [x] 3.4 Validate standalone exports, skill format and official OpenSpec strict; record evidence and integration gaps (45/45 Codex skills, both OpenSpec changes strict-valid; verification-report.json).
