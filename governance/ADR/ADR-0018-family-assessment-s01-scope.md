# ADR-0018: 家庭测评 S-01 的唯一 owner 与结果投影边界

- **Status**: Accepted
- **Date**: 2026-08-30
- **Deciders**: project-owner / family-assessment-dri
- **Supersedes**: null
- **Superseded By**: null

## Context

当前仓库已经有 `backend/domains/assessment`，并由 `governance/DOMAIN_REGISTRY.yaml`
登记为 Assessment 的唯一实现位置。它已有版本化 `AssessmentTool`、
`AssessmentSession`、`AssessmentResponse`、提交证据与 `GrowthHypothesis` 投影，
以及 `tests/domains/assessment/` 和 `tests/apps/family_api/` 的验收链。

同时，现有 UI-03 代码曾暴露 `overall_score`、维度分数和 `peer_reference` 形状；
这与宪章 R9 的“家庭总分/家庭排名永不计算、存储、暴露”冲突。首个服务必须回答
一个已授权成人在一个 family scope 内完成最小测评后能看到什么，而不是新增第二套
FamilyNeed、Consent、Identity 或 Journey 语义。

## Decision

1. S-01 的唯一 domain owner 继续是 `backend/domains/assessment`。已有 session、
   response、evidence、need catalog 和 hypothesis 语义复用，不新建 `family_need`
   或平行 assessment domain。
2. 首小时最小答案集是已认证 guardian 在当前有效 `ASSESSMENT` consent 下选择一个
   `FOCUS`。其他上下文题保持可选，不得通过缺省值推断家庭事实。
3. 新增 `ASSESSMENT_RESULT_V1` family-scoped read projection。它只从提交 session
   与 evidence lineage 派生，含解释、建议草案、版本与来源引用；不写 canonical
   Fact、GrowthIntent、Journey、Task、Outcome 或商业状态。
4. 结果读取重新校验 consent；撤回后只返回 `CONSENT_REQUIRED`，不返回提交内容。
5. S-01 的确定性解释仅用于 `dev/test/sandbox` 可回放验证，并明确标记
   `DETERMINISTIC_TEST_BASELINE` / `NOT_INVOKED`。未来模型解释必须经
   `backend/intelligence/model_gateway`，携带完整 provenance，且
   `may_mutate_business_state=false`。
6. UI 允许成人确认、拒绝并重新开始；拒绝不产生 GrowthIntent，重新开始沿用现有
   versioned session Named Action 和幂等键。

## Alternatives Considered

### 方案 A：直接扩展现有 Assessment（采用）

支持理由：已存在唯一 owner、family scope、consent port、幂等、audit/outbox 与
测试夹具，最短路径能形成可回放纵切片。

否决理由：无。它是唯一不复制领域语义的方案。

### 方案 B：新建 `family_result` 或 `family_need` domain

支持理由：可以快速为产品命名一个面向结果的 API。

否决理由：会复制 FamilyNeed/assessment 事实归属，违反 R2，并使 Consent、删除和
审计责任出现第二入口。

### 方案 C：保留 scorecard，增加“非诊断”免责声明

支持理由：视觉上容易复用已有 UI-03 雷达图，迁移成本低。

否决理由：免责声明不能改变总分/同龄参考形状的实际含义，仍撞 R9；S-01 只保留
方向、证据、解释与建议草案。

## Consequences

### 正面

- 首个服务能用一条 family-scoped 结果读取路径回读来源、版本和边界。
- 拒绝、撤回和重开均有明确状态，不把确定性 fixture 冒充生产 AI。
- 评分/题库、AI eval、前端视觉、真实 PG 可以按 owner 独立推进。

### 负面 / 代价

- 当前仓库仍使用进程内 fake repository，不能证明生产持久化或并发安全。
- 当前 deterministic adapter 不是 AI 能力；外部供应商准入仍被合规状态阻断。
- 真实读取审计与 Consent record store 仍需平台 owner 接入。

### 需要接受的风险

- 若未配置 `PY_ASSESSMENT_TEST_DATABASE_URL`，Postgres 证据只能标记 skip，不能写成
  production pass。
- 现有 UI-04 及后续 Journey 不属于 S-01，不能因确认结果而宣称计划已交付。

## Enforcement

- `tests/domains/assessment/test_assessment_flow.py` 锁定最小 `FOCUS` 答案、family scope、
  撤回保护和结果无 score/ranking 字段。
- `tests/apps/family_api/test_assessment_routes.py` 锁定真实 FastAPI 结果路由与幂等链。
- `governance/CAPABILITY_REGISTRY.yaml` 登记结果投影的 code/test/API 追踪。
- 真实 Consent record、读取 AuditEvent、PostgreSQL 集成仍是依赖项，当前不宣称已完成。

## References

- `governance/REPOSITORY_CONSTITUTION.md` R2/R4/R6/R9/R10
- `docs/05_ai/AI_NATIVE_PRINCIPLES.md`
- `docs/12_governance/COMPLIANCE_HARD_CONSTRAINTS.md`
- `backend/domains/assessment/application/queries.py`
- `backend/domains/assessment/infrastructure/fake_repository.py`
