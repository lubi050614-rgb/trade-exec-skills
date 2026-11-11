## 1. 规范和接口

- [x] 1.1 固定股票范围为 6 Upper + 15 Atomic；复制原始基线并编写 proposal/design/specs（OpenSpec strict 校验）。
- [x] 1.2 定义每个独立入口的输入输出 Schema、错误和样例（test_exported_entrypoints_and_schemas）。
- [x] 1.3 保留原生 frontmatter 并单独生成 Codex 投影（21 个投影通过 skill-creator quick_validate）。

## 2. 共享领域实现

- [x] 2.1 权重、覆盖、快照与当前持仓核对，冻结目标数量并报告费用、现金缓冲和舍入偏差（test_schema_and_business_rejections、test_weight_open_gap_partial_cancel_and_fee）。
- [x] 2.2 在途扣减与旧单冲突检测（test_weight_open_gap_partial_cancel_and_fee、test_open_conflicts_and_rule_differences）。
- [x] 2.3 SQLite 持久化及 MockAccountServiceAdapter 权威预留、释放、记账、交收（test_concurrent_reservation、test_settlement_and_previous_day_expiry）。
- [x] 2.4 15 个单职责 Atomic 和 6 个复用核心的 Upper（每个成功样例均由 build_assets 实际执行生成；test_upper_atomic_equivalence）。

## 3. 撮合和恢复

- [x] 3.1 保守开盘价模型、限价/市价保护、完整 bar 可见性及单会话单频率（test_time_capacity_gap_and_expiry、test_market_protection_halt_frequency_and_ohlc）。
- [x] 3.2 共享容量、部分成交、累计最低费用和撤单资源释放（test_weight_open_gap_partial_cancel_and_fee、test_partial_fee_minimum_once）。
- [x] 3.3 请求、成交和行情事件幂等，重复事件不改变账户/订单（test_idempotency、test_duplicate_event_preserves_entire_account_and_order）。
- [x] 3.4 成交登记/订单推进/账户记账后故障注入及进程重启恢复（test_recovery_all_phases_after_restart）。
- [x] 3.5 Atomic 乱序拒绝、持久化事件与成交前置条件（test_atomic_ordering_and_read_purity、test_upper_atomic_equivalence）。

## 4. 样例与交付

- [x] 4.1 三所不同规则 profile、账户、目标、日线/分钟线及预期结果（test_rule_profiles_and_daily_all_exchanges、test_open_conflicts_and_rule_differences）。
- [x] 4.2 行情字段映射、价格口径与 provider 边界（test_provider_mapping）。
- [x] 4.3 独立目录自包含导出、仓库外运行与 ZIP 验证（test_exported_entrypoints_and_schemas、test_actual_export_zip_is_self_contained）。
- [x] 4.4 README、demo、打包脚本与未集成项说明。
- [x] 4.5 官方 OpenSpec CLI strict 校验，持续检查脚本与验收证据（verification.md）。

真实账户/ClickHouse/正式交易规则、CTA、平台原生验证器不属于本次股票模拟交付；其未接入状态保留在 verification.md，不把它们标记为已经通过。
