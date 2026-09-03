# ADR-0111：Authenticated Engagement Scope 适配

- 状态：Accepted
- 日期：2026-08-30
- 范围：`backend/apps/family_api/trusted_experience_scope.py`

## 决策

新增 `AuthenticatedEngagementScopeResolver`，复用既有
`AuthenticatedExperienceScopeResolver` 的 principal、trusted tenant/family
binding 与 `ConsentGate` 校验，将通过授权的 `ContextScope` 映射为
EngagementDraft 所需的 `ExperienceScope`。适配器只转换不可变 scope envelope，
不重新解析请求 JSON，也不接受客户端提供的 tenant、subject、consent 或事件。

`global_id` 由 tenant/family/consent version 组成，删除句柄沿用 consent snapshot
并附加显式 retention policy；四级 locale 缺省回退到已验证的 locale。这样
`ProductionEngagementRuntimeResolver` 可以直接接入真实身份/同意边界，同时保持
staging/production 与 test 的组合形状一致。

## 约束

- 缺失、撤回或失效 consent 在 ContextScope 阶段 fail-closed；不得生成 Engagement
  draft。
- 适配器不写 canonical business fact，AI 输出仍只能是 DRAFT，成就必须经过 Human
  Gate。
- 真实 identity/consent store、主入口 request-auth middleware、PostgreSQL 并发和
  删除证明仍属于部署验收，不因本适配器存在而宣称已上线。
