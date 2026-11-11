# 股票与 CTA 执行模拟工具

依据 `execution_tools_ai_spec.md` 0.2.0，实现股票 **6 Upper + 15 Atomic** 和 CTA **8 Upper + 16 Atomic**，共 **45 个独立入口**。使用本地 SQLite 和 mock 账户，不接实盘、真实账户服务或 ClickHouse。所有规则均是 `simulation_fixture`，不是交易所官方规则。

## 运行

需要 Python 3.11+，运行时无第三方依赖。当前机器可用 `.runtime/python/python.exe`（本地便携版，不纳入发布包）。

```powershell
python scripts/demo.py --exchange SSE --frequency 1m --db demo.sqlite
python scripts/demo.py --exchange SZSE --frequency 1d --db daily.sqlite
python scripts/demo.py --exchange BSE --frequency 1m --db bse.sqlite
```

每次 demo 使用新的数据库路径。输出包含计划、提交、模拟与查询结果。

独立入口例子：

```powershell
python skills/order-plan/scripts/run.py --db session.sqlite --init examples/SSE/session.json --input examples/SSE/plan.json
```

后续调用使用相同数据库路径和 simulation_id/account_id；依据上一步返回的账户、订单版本构造请求。所有写接口需要幂等键，同键同数据返回原结果，同键不同数据报错。stdout 只输出 JSON；退出码 0 表示成功信封，1 表示错误。必须额外检查 `commit_status`，待恢复结果不表示业务完成。

## 接口与原子流程

完整入口见 `contracts/catalog.json`，各技能的 `references/contract.md` 和 `assets/input.schema.json` 定义输入。工具核心在 `stock_execution/`；`scripts/build_assets.py` 同步各独立技能的自包含副本。

提交：`order-register` → `order-reserve`。未预留订单保持 `PENDING_RESERVATION`，不能撮合。Upper 提交失败整体回滚。

成交：可信 fixture provider 先通过 `Runtime.publish_market_event(...)` 持久化完成行情（不是新增 tool），再 `execution-match` → `execution-fill-record` → `order-apply-fill` → `account-apply-fill` → `order-release-reserve`。fill-record 从持久化事件重算价格、数量并原子占容量，不接受调用者伪造成交。

撤单：`order-cancel-remainder` → `order-release-reserve`，使用每步返回的新版本。Atomic 只执行一个领域步骤。

恢复：`execution-simulate` 支持测试故障点 `fail_after=record/order/account`。结果为 `ACCOUNTING_PENDING` 或 `RECOVERY_REQUIRED` 时，以同一 bar/model、新幂等键、不带 fail_after 重试。相同幂等键仍返回原结果。SQLite 持久化所有已完成步骤；相关账户新交易会被阻塞。

金额、价格、权重传十进制字符串；只支持显式 +08:00 时间。账户净资产以 mock 持仓估值价计算；本期不实现行情驱动自动重估和公司行动，请使用一致快照。

计划可用 `cash_buffer` 指定预期成交后现金缓冲，返回 `funding_sufficient`、`estimated_post_trade_cash` 及 `requires_sell_proceeds`。依赖卖出收入的买单仍需等待实际成交入账，然后用当前账户版本提交。

## 验证与打包

```powershell
python scripts/build_assets.py
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
python scripts/package.py
python scripts/verify.py
```

每个技能包含自己的共享核心，可以独立复制导出。发布包位于 `dist/`，不包含数据库、便携解释器或凭证。

`dist/stock-execution-tools.zip` 是原生插件包；`dist/stock-execution-codex.zip` 是 Codex frontmatter 投影，保留扩展字段到 metadata。原生字段不因 Codex 的字段约束被删除。

当前完整发布使用 `dist/execution-tools.zip` 和 `dist/execution-tools-codex.zip`；上述旧文件名保留为完整包兼容别名。CTA 可单独使用 `dist/cta-execution-tools.zip` 或 `dist/cta-execution-codex.zip`，每个工具还有独立 ZIP。

OpenSpec 变更分别在 `openspec/changes/stock-execution-tools/` 和 `openspec/changes/cta-execution-tools/`，任务进度和证据见各自的 `tasks.md`、`verification.md`。`scripts/verify.py` 默认运行完整测试并校验两个变更；可用 `--change cta-execution-tools` 指定变更。

尚待集成：真实账户 API/鉴权/字段映射、ClickHouse 表与价格口径、正式交易日历/规则/费用，以及平台原生 plugin 模板和导出验证器。没有这些输入不能声称生产接入或官方交易规则合规。

## CTA 运行与 Agent 调用

```powershell
python scripts/demo_cta.py --db reverse.sqlite
python scripts/demo_cta.py --scenario settle-long --db long.sqlite
python scripts/demo_cta.py --scenario settle-short --db short.sqlite
python scripts/replay_cta_example.py --tool cta-roll-progress
```

每个 demo 使用新数据库路径。`reverse` 展示多 3 转空 2：先平成交 2、再平 1，最后开空仅成交 1，所以最终实际净空 1，未成交的开仓 1 手仍保留。

CTA 请求必须带 `asset_class=FUTURES`；`target_net_lots` 必须为整数。股票权重、未知合约、模糊时间、缺失开平或虚构成交均明确拒绝。优先让 Agent 使用 Upper，Atomic 仍保留完整前置条件。

计划会持久化 `leg_id` 和平仓依赖，提交仅接受已存在的计划腿、当前账户版本和明确提交时间。开仓必须等待所依赖的全部平仓真实成交且入账。注册 Atomic 同时完成登记和冻结。独立 Atomic 成交流程为可信 provider 先 `publish_market_event`，再 `cta-order-match` → `cta-fill-record` → `cta-order-state-update(FILL)` → `cta-fill-book` → `cta-order-release`。撤单用 `cta-order-state-update(CANCEL)` 后释放；未释放前新交易会被阻塞。

`cta-execution-simulate` 支持 `fail_after=record/state/book/release` 测试故障点。待恢复时使用同一事件/模型、新幂等键并去掉故障参数重试；原幂等键始终返回原响应。结果包含 commit_status、completed_steps、failed_step、retryable、event_id 和 reconciliation_status。

费用支持按手/按名义金额；保证金支持费率/定额。`reservation_policy` 默认 `UPPER_BOUND_V1`：卖开订单按 profile 价格上限预留保证金。显式选择 `ORDER_PRICE_V1` 时按委托价或保护价预留；若成交价格导致预算不足（包括剩余委托需保留的冻结），不撮合该笔成交。手续费始终按价格上界预算。成交后转为持仓保证金并释放多余冻结，释放金额不记作利润。

2026-11-11 业务修复：股票 `order-plan` 现在持久化同一目标版本的目标股数，需要 `idempotency_key`；使用新快照重新规划不会因费用改变目标股数，同版本改权重会返回 `TARGET_VERSION_CONFLICT`。CTA 新计划生效后，旧目标未提交腿会返回 `STALE_TARGET_VERSION`。

异步撤单模拟请在 `order-cancel` / `cta-order-cancel` 的 data 中明确传入 `action: REQUEST`，保留在途数量和冻结；允许交叉成交入账后，以最新 `expected_version` 传 `CONFIRM` 释放剩余冻结，或传 `REJECT` 清除撤单等待标志。省略 action 保持旧的本地同步确认行为；Atomic 撤单接口仍是确认原语。

成交冲突会持久化 `RECONCILE` 并阻止新提交。查询和既有合法成交恢复仍可进行；只有可信模拟维护入口 `Runtime.resolve_reconciliation` 能在核对凭证、成交哈希、冲突数量与账户版本后解除阻断，Agent 工具没有强制清除入口。完整修复记录见 [业务修复验收](reviews/2026-11-11-business-logic/REMEDIATION.md)。

日历明确列出自然时间区间与 trade_date，包括夜盘和假期；不推断“日期加一”。必须先结算当前交易日，才能进入后续交易日。结算需要显式昨/今结算价，以逐日盯市核算；同日已实现盈亏与费用不重复记账，今仓迁移和 DAY 单释放仅发生一次。本期不提供入出金接口，桥接报表 net_deposits 固定为 0。

CTA 和股票各有独立 mock 账户与会话，不宣称共享真实账户资金。未来若同一生产账户同时交易两类资产，必须由统一权威账户服务协调现金和保证金。

24 个 CTA 成功样例均有 `assets/prepared-state.json`，通过 `scripts/replay_cta_example.py` 在临时数据库执行真实独立入口；prepared-state 仅用于可信本地测试，不是 Agent 可调用的交易接口。
