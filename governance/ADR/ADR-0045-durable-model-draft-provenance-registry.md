---
id: ADR-0045
title: Durable ModelDraft provenance registry
status: accepted
date: 2026-08-30
decision_owner: project-owner
supersedes: null
superseded_by: null
---

# ADR-0045：持久化 `ModelDraft` provenance registry

## 背景

`backend/intelligence/model_gateway` 已能生成带完整 `AiProvenance` 的
`ModelDraft`，且输出只能是 `DRAFT`。FGCN 的 Human Gate 入口也已经拒绝仅凭
客户端字符串认定 provenance，但此前 production resolver 没有真实存储可查：
进程重启后无法证明 `provenance_ref` 来自哪个草案、哪个家庭作用域或哪个
`context_snapshot`。

这会把“可解释、可复核”退化成“有一个看起来像引用的字符串”，与
`AI_NATIVE_PRINCIPLES.md`、R9 和 PIPL 第24条要求的可追溯性不一致。现有
`ExperienceRun` 的 checkpoint 负责执行轨迹和重放，不是按精确业务作用域
解析 `ModelDraft` 的索引；把两者混用会使执行记录承担新的数据所有权。

## 决策

1. 在既有 `backend/intelligence/model_gateway` canonical 路径内增加
   `SqlAlchemyModelDraftRegistry`，使用 `ai_model_drafts` 表保存：
   `draft_id`、租户/家庭/主体/用途/因果作用域、完整模型 provenance、输出快照
   和创建时间。
2. `tenant_id + provenance_ref` 唯一；相同 draft 的重复保存必须是相同内容的
   幂等重放，不同内容拒绝。解析时五项作用域必须完全匹配；不存在和跨作用域
   引用统一表现为 not found，避免泄露另一家庭存在草案。
3. Python 层与数据库层都强制 `status = DRAFT`、
   `may_mutate_business_state = false`；输出拒绝家庭总分、家庭排名、排名、
   canonical fact 等事实形状字段。注册表不执行任何业务 Named Action。
4. FGCN 的默认 provenance dependency 改为从请求 session 构造该 durable registry。
   没有显式数据库接线时，session dependency 继续 fail-closed；测试可以注入
   SQLite registry，但不因此声称有真实供应商或 production identity。
5. `0009_ai_model_drafts` 接在现有 `0008_experience_runs` 后。它不向 Family、
   Growth、Service 或 Commerce 表添加外键，保持 AI Runtime 与业务事实隔离。
6. 多模态应用层通过显式 `ModelDraftRegistryPort` 登记生成结果。登记只执行
   `flush`，不由 Model Gateway 或应用服务自动 `commit`；组合根可以把注册表、
   ExperienceRun、审计和 outbox 放在同一 Unit of Work 中。
7. 草案身份由受信任的 `run_id` 稳定派生为 `draft_id` 与 `provenance_ref`。
   多主体 ContextScope 必须额外指定动作主体，不能把主体集合隐式压成一个
   `subject_person_id`。

## Alternatives Considered

### A. 继续接受客户端 `provenance_ref`

支持理由：改动最小，能立即让 HTTP 请求携带一个来源字段。

否决理由：客户端可以伪造不存在的引用，也无法在重启后恢复模型、版本、作用域
和原始草案；Human Gate 审计链条因此没有事实基础。

### B. 只把 provenance 放进 `ExperienceRun` checkpoint

支持理由：`ExperienceRun` 已有持久化表、事件序列和重放能力，可以少建一张表。

否决理由：run 是执行轨迹，FGCN 需要按 `provenance_ref` 和精确家庭/主体作用域
解析可复用草案。把查询索引、草案身份和执行重放硬绑在一起会扩大 Experience
Runtime 的数据所有权，也无法自然表达多个业务消费者共享一个草案引用。

### C. 把草案直接写入 FGCN 或 Service 表

支持理由：FGCN 已经有 durable repository，读取路径看起来更短。

否决理由：这会让业务域拥有 AI Runtime 产物并诱导 AI 直接写业务事实，违反 R7/R9
和 `test_ai_runtime_does_not_import_business_domains` 的隔离边界；也会把尚未
人工确认的模型输出混进 Service canonical state。

### D. 由 Model Gateway 内部持有数据库 session 并自动提交

支持理由：所有模型调用都能自动留下记录，调用方不容易忘记登记。

否决理由：Gateway 不应拥有应用事务边界，自动提交会破坏 run/outbox/审计的事务
组合；它还会使“生成成功但登记失败”的错误语义不透明。本 ADR 先提供显式
registry seam，自动保存由后续 composition-root/application slice 决定。

## 后果

### 正面

- FGCN proposal 现在可以基于重启后仍存在的受信任草案进入 Human Gate。
- provenance、模型版本、提示词版本、schema 版本、上下文引用和作用域可在同一
  条记录中复核，跨家庭引用不会被误读。
- Python 防护和数据库 CHECK 双重守住 Draft-only；注册表不具备业务事实写权限。
- SQLite 快速测试与 Alembic/PostgreSQL 生产表保持同一字段和约束意图。

### 负面 / 代价

- 新增一张 AI Runtime 表和一条迁移；生产数据库必须执行 `0009` 后才能使用默认
  FGCN resolver。
- 当前只把 context-bound 多模态应用切片接入 registry，并没有把所有 Model
  Gateway 调用自动接入；没有调用方登记的草案仍不能被 FGCN 解析，这是有意的
  fail-closed 缺口。
- 输出快照与 provenance 是个人信息派生记录，后续必须接入按主体删除、留存期限、
  导出和 DPIA 机制，不能把这张表当作无限期数据湖。

## Enforcement

- `backend/intelligence/model_gateway/provenance.py`：作用域、幂等、Draft-only、
  事实字段拒绝、持久化形状重验。
- `backend/intelligence/experience/multimodal_generation.py` 与
  `multimodal_context_application.py`：应用层 registry port、稳定草案身份、
  多主体动作主体约束和事务不自动提交。
- `backend/domains/service/fgcn/api/dependencies.py`：FGCN 默认 durable resolver。
- `database/migrations/versions/0009_ai_model_drafts.py`：唯一约束与数据库 CHECK。
- `tests/intelligence/model_gateway/test_provenance_registry.py`：跨作用域、伪造
  provenance、非草案、事实形状、重放和篡改反向测试。
- `tests/apps/family_api/test_fgcn_routes.py`：持久化 registry 到 FGCN Human Gate
  的 HTTP 正向链路。
- `tests/intelligence/experience/test_multimodal_registry_integration.py`：生成链路
  的新会话回读、未提交回滚、跨租户拒绝、多主体主体约束和事实形状反向测试。
- 当前未执行真实 PostgreSQL round-trip；未设置 `AIFAMILY_TEST_DATABASE_URL` 时，
  PostgreSQL 测试保持 skip，不以 SQLite 证据替代生产数据库证据。

## References

- `docs/05_ai/AI_NATIVE_PRINCIPLES.md`
- `docs/12_governance/COMPLIANCE_HARD_CONSTRAINTS.md`
- `governance/REPOSITORY_CONSTITUTION.md` R7 / R9 / R10 / R14
- `governance/ADR/ADR-0044-fgcn-verified-model-draft-provenance.md`
- `governance/ADR/ADR-0041-experience-run-durable-replay.md`
