# 股票模拟执行验收记录

日期：2026-11-11（Asia/Shanghai）。本阶段仅股票 21 个工具，不包含 CTA。

## 已执行的检查

- `python -m unittest discover -s tests -v`：18 组测试通过，包含三所 × 日线/分钟线子场景。
- 21 个工具的实际成功样例由 `scripts/build_assets.py` 在独立新会话内按合法前置顺序执行生成。
- 输入 Schema 和成功/失败输出通过独立 `jsonschema` 校验；所有独立入口在仓库外子进程启动。
- 实际导出 ZIP 解压到临时目录后，order-plan 在没有源码仓库依赖的环境成功运行。
- 21 个 Codex 投影通过 skill-creator 的 `quick_validate.py`；原生 frontmatter 保留规范要求的扩展字段，未拿原生格式冒充 Codex 格式。
- 官方 OpenSpec CLI **1.17.0**：`validate stock-execution-tools --strict` 通过。
- `scripts/verify.py` 可重新执行测试和官方 OpenSpec 校验，机器可读输出为同目录 `verification-report.json`。

## 核心验收对应

| 规范第 10 节 | 证据 |
|---|---|
| 1 权重转换、舍入、费用、残余 | weight_open_gap_partial_cancel_and_fee、成功计划样例 |
| 2 在途扣减、部分成交后持仓/在途一致 | weight_open_gap_partial_cancel_and_fee |
| 3 重复提交/行情/记账 | idempotency、duplicate_event_preserves_entire_account_and_order、recovery_all_phases_after_restart |
| 4 资源/价格/数量/快照拒绝 | schema_and_business_rejections |
| 5 并发资源竞争 | concurrent_reservation |
| 6 部分成交与撤单 | weight_open_gap_partial_cancel_and_fee |
| 7 日线/分钟线闭环及无未来数据 | rule_profiles_and_daily_all_exchanges、time_capacity_gap_and_expiry |
| 8 三所与不同规则配置 | rule_profiles_and_daily_all_exchanges、open_conflicts_and_rule_differences |
| 9 非法清单/重复/权重/快照/价格 | schema_and_business_rejections |
| 10 保护价/零量/停牌/日终失效 | market_protection_halt_frequency_and_ohlc、time_capacity_gap_and_expiry |
| 11 记账失败重启恢复与阻塞 | recovery_all_phases_after_restart |
| 12 共享容量及累计最低费 | weight_open_gap_partial_cancel_and_fee、partial_fee_minimum_once |

追加验收：upper_atomic_equivalence 验证手工 Atomic 路径与 Upper 的订单/成交/账户/冻结一致；atomic_ordering_and_read_purity 验证前置条件与只读语义；settlement_and_previous_day_expiry 验证 T+1 和旧 DAY 单失效。

atomic_cannot_skip_matching_priority_or_duplicate_order_event 验证独立 Atomic 也不能绕过早先订单抢占共享 bar 容量。

## 明确未验证/未接入

- 真实账户服务、生产鉴权与跨服务事务：未提供 API，只有 AccountServiceAdapter 和本地 mock。
- ClickHouse、真实分钟行情与真实行情价格口径：未接入；只有 fixture provider 和显式字段映射。
- 实际 A 股交易所、板块规则与费用认证：未验证；所有 profile 均标记 simulation_fixture。
- 原生插件平台模板及正式导出验证器：用户未提供，plugin.json 与原生 SKILL 保留所给规范结构，不能声称平台验收完成。
- 公司行动自动处理、实时估值、生产高吞吐、CTA：未实现，分别属规范非目标或下一阶段。

OpenSpec 格式依据：[官方 concepts](https://github.com/Fission-AI/OpenSpec/blob/main/docs/concepts.md)。
