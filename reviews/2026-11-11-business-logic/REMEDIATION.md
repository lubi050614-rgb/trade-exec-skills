# 业务修复验收 — 2026-11-11

本记录对应原始 REPORT.md 的 R01–R08。原报告及 observations.json 保留为修复前证据；原复现脚本保存在 inputs/test_business_review_before_fix.py。当前复现脚本已成为回归，运行结果写入 observations-after-fix.json。

| 编号 | 修复结果 | 验证 |
|---|---|---|
| R01 | 通过市场事件与订单关联恢复持久化成交；完成前检查一致性 | 股票与 CTA 任意 fill ID、数据库重连、重复执行不重复记账 |
| R02 | 每个合约保存当前有效目标；新目标阻止旧腿提交 | 平仓完成后改为空仓目标，旧开仓腿被拒绝；不同目标 ID 同样替代旧计划 |
| R03 | 股票计划持久化目标股数、来源快照、原始归一化数量 | NAV 扣费后同版本仍为 1000 股；同版本改权重拒绝 |
| R04 | reserve 在事务内调用完整 precheck | 两个不兼容 pending 订单只能激活一个 |
| R05 | 增加显式 REQUEST / CONFIRM / REJECT，cancel_pending 独立于成交状态 | 请求保留冻结；拒绝清标记；交叉成交后确认只释放剩余；完全成交清理等待标志 |
| R06 | 财务回滚后单独持久化冲突证据和 RECONCILE；提交入口阻断 | 双领域财务不变、冲突保留、可信 CAS 核对后恢复 |
| R07 | 卖单预留保守费用差额，成交消耗差额，剩余按需释放 | 1 股卖价 1、费用 5：现金 0 拒绝；现金 4 可成交且最终现金/冻结均为 0 |
| R08 | 增加 UPPER_BOUND_V1 / ORDER_PRICE_V1；保留默认保守策略 | 显式 test-v1 策略下 D4 冻结 8010；更高价部分成交不能侵占剩余冻结 |

## 契约与兼容性

- 股票 `order-plan` 从只读变为持久化写入，必须提供幂等键。相同幂等键重放返回原结果；新快照需要新幂等键，目标版本不变时继续使用已保存股数。
- 同目标版本可更新执行参考价，但不能改变目标权重或使股数漂移。历史数据库中从未保存的归一化结果无法自动重建；升级后首次计划建立固定基准。
- 撤单默认仍表示旧版本地同步确认。异步案例必须显式传 `action=REQUEST`，确认必须使用交叉成交后的当前订单版本。Atomic 撤单仍是确认操作，不代表向真实柜台发送请求。
- CTA `reservation_policy` 位于合约规则 fixture。test-v1 测试显式选择 `ORDER_PRICE_V1`，没有改动 8010/91975 的金额断言；未配置时继续按 `UPPER_BOUND_V1` 执行。
- `resolve_reconciliation` 是可信本地维护边界，需要独立核对凭证、canonical fills 哈希、冲突数量和账户版本。它只接受保留已核对 canonical ledger 的恢复，不负责自动修改争议成交，也不作为 Agent 工具暴露。

## 验证方法

```powershell
python -m unittest discover -s tests -v
python reviews/2026-11-11-business-logic/test_business_review.py
python scripts/build_assets.py
python scripts/package.py
python scripts/verify.py --change business-logic-fixes --skill-validator C:/Users/EDY/.codex/skills/.system/skill-creator/scripts/quick_validate.py
```

正式结果见 openspec/changes/business-logic-fixes/verification-report.json。所有测试使用内存或临时数据库；未改动用户 local-cta-plan.sqlite。

## 保留边界

这是本地模拟器的 R01–R08 修复，不等于新文档每项生产能力全部验收。累计委托回报先于成交明细的 `FILLED_AWAITING_TRADES`、任意柜台回报归一化、真实交易所撤单禁撤时段、外部账本自动对账、Fm/Ff 独立报表等仍未实现。案例 A–E 验证通过等价合成 bar 回放可支持的账务步骤；外部回报扩展分支没有被宣称通过。
