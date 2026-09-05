# ADR-0145: EngagementDraft durable Human Gate envelope

- 状态：Accepted for experiment
- 日期：2026-09-01
- 范围：`backend/intelligence/experience/engagement_review.py`

## 背景

Engagement API 已能从服务端真实 `ExperienceEvent` 生成 achievement candidate，
`build_achievement_action_proposal` 也能把候选转换为 Human Gate Named Action。
但此前 HTTP 响应返回后不保留完整 EngagementDraft，后续请求若携带候选正文、
scope 或 provenance，就会把客户端输入错误地当成审核事实。

既有 `ai_model_drafts` 只建模单一 `subject_person_id`，不能忠实表达
`ExperienceScope.subject_ids` 的多主体边界，因此不能作为本用例唯一存储。

## 决策

新增 `ai_engagement_draft_reviews`，保存服务端生成的 immutable DRAFT envelope：

- 完整 `ExperienceScope` 与 tenant/family/region/subjects/purpose/consent 标量；
- 本次授权的真实 `ExperienceEvent` IDs；
- 结构化模型输出和完整 `AiProvenance`；
- 内容稳定摘要、创建时间、有效期、retention policy 与 deletion reference；
- 数据库约束固定 `status=DRAFT`、`may_mutate_business_state=false`。

后续候选提交只接受 `draft_id + candidate_id`。服务端必须重新解析当前身份、
family scope、consent 和 deletion 状态，加载原始 envelope，重新读取真实事件，
再调用既有 proposal builder 和 `SqlAlchemyHumanGate`。客户端不得提交候选正文、
evidence、scope、provenance、action name 或 reviewer identity。

不同 HTTP 请求允许 correlation/causation ID 改变；数据授权维度必须与生成时完全
一致。跨 scope 查询统一表现为 not found，避免泄漏其他家庭草稿是否存在。

## 事务与成熟度

模型 attempt/safety/telemetry 和 EngagementDraft 保存必须处于同一请求级 UoW。
HumanTask 与审计记录也必须处于同一事务。Guardian 接受只生成
`NamedActionRequest`；accepted-action worker 后续在独立事务中写入成就、通知和
scope-local analytics，不写 Family/Journey/Service/Commerce 权威事实。

accepted-action worker 在写入前必须重新加载 immutable envelope、回读原始事件并
用服务端 builder 重建 action；请求中的正文、candidate、scope 或 provenance 与重建
结果不一致时 fail-closed。人工 ACCEPT 不是绕过执行时完整性校验的授权。

本决策只批准 EXPERIMENT。当前已实现 bearer→account→active guardian membership
reviewer resolver、候选提交/人工决策 HTTP、accepted worker 独立证据回查，以及
fresh Alembic head 上的 PostgreSQL HTTP E2E。完成执行时当前 consent/deletion 复核、
真实 bearer 并发 E2E、retention deletion worker 和部署调度前，不得晋级 PILOT。
