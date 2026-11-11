## Why

当前目录没有股票执行工具。按用户指定的 0.2.0 编写规范先交付股票模拟执行闭环，并通过 OpenSpec 追踪实现与验收。

## What Changes

- 提供 6 个 Upper、15 个 Atomic 独立工具入口、Schema、调用样例和契约。
- 使用共享领域核心、SQLite 状态和 MockAccountServiceAdapter，完成预留、撮合、记账、查询与恢复。
- 提供 SSE/SZSE/BSE 合成规则与日线/分钟线样例。
- 提供自包含的技能导出，以及验收测试和运行说明。

## Capabilities

### New Capabilities

- `stock-execution`: 完整权重清单转换、订单生命周期、模拟成交和账户记账。
- `stock-tool-packaging`: 21 个独立技能及自包含发布包。

### Modified Capabilities

无已有能力。

## Impact

新增 Python 本地模拟插件，不连接实盘。真实账户 API、ClickHouse、正式交易规则、平台导出校验器均属后续集成；CTA 不在本次实现范围。
