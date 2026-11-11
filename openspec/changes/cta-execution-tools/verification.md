# CTA 开发与验收记录

日期：2026-11-11，Asia/Shanghai。规范：execution_tools_ai_spec.md 0.2.0 第 15–20 节。

## 交付范围

新增 8 Upper + 16 Atomic 独立 CTA 技能，同项目包含股票 21 个入口，共 45 个。CTA 核心为 cta_execution，协议基础设施为 execution_common，独立技能内包含完整本地依赖。输入严格要求 FUTURES 和整数目标手数，不接受股票权重或推断开平。

最终验证：**42 组测试通过（CTA 24 + 股票 18）**；**45/45 Codex 技能投影通过 skill-creator quick_validate**；官方 **OpenSpec CLI 1.17.0** 对两个变更的 strict 校验均通过。便携 Python 另外执行反手、多仓结算、空仓结算 demo，结果分别为实际净空 1、期末权益 100300、期末权益 99700。

## 验收映射

| 场景 | 测试证据 |
|---|---|
| 24 个独立接口、成功/失败契约、实际脚本运行 | all_contracts_success_and_standalone_entries；每个成功样例均由 build_cta_assets 实际执行生成 |
| 多 3 转空 2；平 2 后保留多 1、开仓阻塞；平完后开 1 仅报告净空 1 | reverse_partial_close_then_open_and_actual_net |
| 原子登记冻结失败不留订单，竞争不重复占用今昨仓 | registration_and_reservation_all_or_none、concurrent_close_reservations_do_not_double_freeze |
| 今昨仓费用差异、部分成交和撤单释放 | today_yesterday_fees_freeze_and_cancel |
| 费率/定额保证金、按手/按金额费用、开仓保证金转换 | fixed_margin_and_notional_fees、market_short_protection_and_margin_conversion |
| 共享容量、信号 bar、保护价和完整行情可见性 | shared_capacity_and_causal_bars、daily_and_minute_and_market_data_boundaries、market_short_protection_and_margin_conversion |
| 显式夜盘/周末归属、真实夜盘成交不按自然日结算 | calendar_night_holiday_and_no_midnight_settlement、actual_night_execution_uses_explicit_future_trade_date |
| 多头/空头跨日结算、权益桥接、重复不再入账 | long_short_settlement_and_conflicting_replay、second_day_uses_actual_previous_settlement_once |
| 平仓盈亏与费用已入账后，结算只增加剩余持仓盯市调整 | settlement_does_not_double_count_closed_pnl_or_fees |
| 结算价缺失、昨结算不符、过早结算或同日修改输入拒绝 | missing_settlement_price_and_too_early、long_short_settlement_and_conflicting_replay |
| 换月旧平 2、新开 1，未衔接 1，不能假报完成 | roll_partial_new_fill_reports_unconnected_exposure |
| 四阶段故障后重启，经济效果仅发生一次 | recovery_four_stages_after_restart（record/state/book/release） |
| Upper 与手工 Atomic 的订单/成交/持仓/容量一致 | atomic_path_matches_upper_and_wrong_order_rejected |
| 伪造成交、股票字段、对锁持仓、风险缺口、过期计划拒绝 | hedged_positions_and_stock_payload_rejected、risk_shortfall_blocks_new_open、stale_preplanned_target_cannot_overtrade |
| 换月不能借用未关联依赖的已有开仓计划 | roll_cannot_reuse_unlinked_opening_plan |
| 导出 ZIP 脱离仓库独立运行 | exported_cta_skill_without_repository_imports |

测试及官方 OpenSpec 的实际结果写入 verification-report.json，Codex 投影校验结果写入 skill-validation.json。既有股票测试也在同一套 unittest 回归中执行。

## 可手算结算 fixture

examples/cta/long 和 short 各有 session、settlement、expected：期初余额/权益 100000，持有昨仓 3 手，乘数 10，昨结算 100，今结算 110，无当日成交或费用。

- 多头：持仓盯市 +300，期末权益 100300，持仓保证金 110 × 10 × 3 × 10% = 330。
- 空头：持仓盯市 -300，期末权益 99700，持仓保证金 110 × 10 × 3 × 12% = 396。
- 今/昨仓跨日迁移只执行一次，下一交易日来自显式日历。

## 未接入与边界

所有合约、规则、夜盘与价格均明确标记为 simulation_fixture/synthetic，不代表真实交易所或经纪商规则。未接入实盘、生产账户服务、真实行情、ClickHouse、原生插件平台验证器；没有认证正式交易规则，也不实现自动强平或组合保证金优惠。

股票和 CTA 分别使用 mock 账户，不共享生产资金。多资产同一真实账户的现金与保证金必须由未来统一权威账户适配器协调。本地测试不编造跨服务事务或鉴权成功记录。

本地 SQLite 记录订单、计划、依赖、资源、事件、成交、幂等结果和步骤追踪。生产账户适配器契约已定义，但本次仅交付本地事务 mock。结算无入出金功能，net_deposits=0。
