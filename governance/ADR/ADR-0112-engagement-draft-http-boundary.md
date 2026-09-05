# ADR-0112：Engagement Draft HTTP 边界

- 状态：Accepted
- 日期：2026-08-30
- 范围：`backend/intelligence/experience/engagement_api.py`

## 决策

新增 `POST /families/{family_id}/experience/engagement/drafts`，把证据绑定的
EngagementDraft 能力暴露为与多模态 Draft 同形状的生产 API。请求只允许
`request_id`、服务端事件 ID 列表和生成意图 payload；家庭/租户/主体、consent、
actor、授权引用、context snapshot、provider 和密钥均由注入的 runtime resolver
提供。

路由始终挂载到 `family_api`，未安装 resolver 时返回稳定的 503。解析器完成 scope
校验后，runtime 从受信任的 SQL Event Reader 读取真实事件并调用 Model Gateway；
响应明确标记 `DRAFT`、证据事件和 `requires_human_confirmation=true`，不创建成就
或写入业务域事实。

## 环境同构与安全

测试可以注入合成 runtime 验证同一 HTTP 契约，生产必须注入
`ProductionEngagementRuntimeResolver`。payload 递归拒绝 scope/provider/credential
控制字段，跨家庭 scope、缺失事件、consent 失败和 provider 错误统一 fail-closed。
真人接受和 Human Gate 仍是成就落地的唯一入口。
