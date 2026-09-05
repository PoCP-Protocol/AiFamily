# ADR-0082: AI achievement candidate Human Gate landing

- 状态：Accepted for experiment
- 日期：2026-08-30
- 范围：`backend/intelligence/experience/accepted_achievement.py`

## 决策

EngagementDraft 的 `achievement_candidates` 只能通过
`build_achievement_action_proposal` 转换为 evidence-bound
`PUBLISH_EXPERIENCE_ACHIEVEMENT` Named Action。提案携带完整的
ExperienceScope、AI provenance 和真实 ExperienceEvent refs，并保持
`draft_status=DRAFT`。

只有 Guardian/Professional 等人类 actor 在 Human Gate 接受后，
`ExperienceAchievementActionHandler` 才将候选投影为 `AI_EVIDENCE_MOMENT`。
投影写入既有 `ai_achievement_projections` read model，保留 scope、evidence、
provenance 和幂等键；同一事务还幂等写入家庭通知 inbox 与 scope-local
achievement analytics，避免出现“成就已落地、反馈未生成”的部分成功。
AI 不直接写 Family/Journey/Service/Commerce 事实。

## 约束

候选 scope 必须与服务端解析的 EngagementDraft scope 完全一致；证据必须来自
本次请求授权的事件；action key、scope、provenance 缺失或被篡改均拒绝。投影
不包含家庭总分、排名、streak 或商业奖励字段。
