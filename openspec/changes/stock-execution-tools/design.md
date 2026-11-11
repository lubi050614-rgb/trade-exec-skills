## Context

空项目，规范来源为 Downloads 的 execution_tools_ai_spec.md，原文复制到项目根目录便于追溯。第一部分解释为股票命名空间的全部 21 个入口，CTA 留待下一阶段。

## Goals / Non-Goals

目标：可重复运行的模拟闭环、独立 Atomic、跨进程持久化、可审计失败恢复。

非目标：实盘、生产账本、真实行情、官方交易规则认证、CTA。

## Decisions

1. 所有数值运算用 Decimal；JSON 金额、价格、权重使用字符串，股数为整数。
2. 每个仿真会话的完整状态放在 SQLite 一行 JSON；BEGIN IMMEDIATE 串行化状态变更，避免预留和成交容量竞争。该模型适合本地模拟，不宣称高吞吐服务架构。
3. MockAccountServiceAdapter 是模拟账户的权威状态来源，承担原子预留、释放、应用成交和按显式交易日推进交收。
4. Upper 与 Atomic 复用 Runtime 的领域函数；工具目录包含共享核心副本，通过生成器同步，避免跨兄弟技能引用。
5. 注册单为 PENDING_RESERVATION。Upper 提交在同库事务中登记和预留，失败回滚；独立 Atomic 分步运行时未预留订单不能撮合。
6. 行情由 FixtureMarketDataProvider 或可信 fixture 导入，先持久化完成事件，再按固定顺序分配容量。Atomic fill-record 重算候选并比较订单版本，禁止调用者伪造成交价和量。
7. 常规 Upper 成交同库事务完成。测试 fail_after 在 record/order/account 阶段保留已完成步骤，返回待恢复；重启后以同一事件、新幂等键且不带 fail_after 恢复。成交事实存在而未入账时阻塞新交易。
8. 每个写操作以 tool+idempotency_key 为作用域，校验规范化 JSON hash。行情事件也有独立内容 hash，完成事件缓存结果，不重复消费容量或改变资源版本。
9. 规则均为 simulation_fixture，以配置展示数量差异，不引用或声称当前真实交易所规则。交易日期必须显式列出。

## Risks / Trade-offs

- 本地 JSON 状态不适合大规模生产数据，后续应拆分表及迁移接口。
- 便携 Python 用于当前环境；正式部署需要 Python 3.11+。
- plugin.json/frontmatter 保留规范字段，但未提供平台模板及验证器，不能声明平台正式接入成功。
- OpenSpec CLI 已在项目 .runtime 内安装 1.17.0，严格校验通过。可移植验证脚本也支持 PATH 中的 OpenSpec；缺少 CLI 会明确记录 not_run。

## Validation

运行 unittest 场景、独立 jsonschema 校验、仓库外独立入口启动，并对照验收矩阵更新 tasks.md。
