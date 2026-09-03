# ADR-0110：Production Engagement Draft Runtime 组合根

- 状态：Accepted
- 日期：2026-08-30
- 范围：`backend/apps/family_api/production_engagement_wiring.py`

## 决策

新增 `ProductionEngagementRuntimeResolver`，将部署提供的 `ExperienceScope`
解析、Model Gateway、SQLAlchemy session、`SqlAlchemyEngagementEventReader` 和
请求级 Attempt/Safety/Telemetry sink 组装为一个生产 Engagement Draft runtime。
身份引用、actor 和 context snapshot ref 均由组合根注入，不从 HTTP body 或环境变量读取。

每次生成打开独立 SQL Unit of Work；事件读取、Gateway 证据、Safety 决策和 Telemetry
在同一事务提交。scope 不匹配、consent 缺失、删除中的 scope 或 synthetic data 在
生成前拒绝；AI 输出仍保持 DRAFT，不写业务域事实。

## 环境同构

staging/production 使用同一 resolver 和事件读取/网关协议，差异仅来自显式注入的
身份、数据库、provider 和 sink。test 的 synthetic resolver 不得注入此组合根。

## 未完成事项

主入口路由挂载、真实 identity/consent 服务、PostgreSQL 多 worker 演练和调度告警仍
需由部署 owner 完成；本 ADR 不把 fake provider 测试声明为真实供应商上线。
