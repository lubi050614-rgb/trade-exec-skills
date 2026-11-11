## Why

股票 21 个工具已交付，需要在同一项目实现规范 0.2.0 的国内期货 CTA 模拟工具，保证 Agent 在净目标、开平、今昨仓和交易日之间不会依赖猜测。

## What Changes

- 新增独立 CTA 领域核心、8 Upper + 16 Atomic 工具、严格输入输出契约与自包含技能包。
- 实现净目标反手、实际成交依赖、保证金与费用冻结、可靠成交恢复、逐日盯市结算和换月进度。
- 使用显式合成交易日历、夜盘时段和合约规则；增加多空跨日结算及故障验收。
- 更新项目生成器、打包、目录索引和 OpenSpec 监测，保留现有股票能力。

## Capabilities

### New Capabilities

- `cta-execution`: 单账户合约净目标、开平撮合、记账、结算、换月。
- `cta-tool-packaging`: Agent 路由、24 独立技能、自包含导出和 45 接口索引。

### Modified Capabilities

无；股票领域算法保持独立。

## Impact

新增 cta_execution 与 execution_common。仅本地仿真，无实盘、真实行情、正式交易规则或生产跨资产账户接入。
