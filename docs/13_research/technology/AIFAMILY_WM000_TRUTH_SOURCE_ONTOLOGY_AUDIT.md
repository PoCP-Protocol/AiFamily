---
id: RES-TECH-AIFAMILY-WM000-001
title: "AIFAMILY-WM-000: Truth Source & Ontology Code Audit"
type: research
status: draft
version: 1.0
owner: chief-architect
created: 2026-09-13
updated: 2026-09-13
canonical: false
supersedes: null
superseded_by: null
---

```text
STATUS: RESEARCH_ONLY
NOT_CANONICAL: TRUE
DOC_KIND = EVIDENCE / CODE AUDIT
本文件是证据与审计结论，不是决定、不是实现规格、不是当前系统真相。
晋升须走 ADR（docs/12_governance/DOCUMENT_GOVERNANCE.md §8.2）。
```

# AIFAMILY-WM-000: Truth Source & Ontology Code Audit

> 目的：在继续 World Model 后续增量（WM-003 及以后）之前，先把每个真实
> Domain 能提供给 World Model 的事实、时间字段、Consent、Outbox、现有表
> 全部逐项列出来——避免设计出一套与现有代码脱节的模型。本文件只记录
> **代码现状**，不做设计决定；已完成的 `WorldStateAtom`/`PredicateRegistry`/
> `PostgresWorldStateRepository`（WM-001）与 Family/FamilyNeed 适配器
> （WM-002）见 `backend/intelligence/context_engine/`，不在本文件重复。

## 0. 时区约定核对表（World State Kernel 强制要求 tz-aware）

| 域 | 时间戳 | tz-aware? |
|---|---|---|
| Family Core（Family/FamilyMember/FamilyRelationship） | created_at/updated_at | **naive**（故意，见 `entities.py` `utcnow()` 注释） |
| Consent | granted_at/withdrawn_at/created_at | **naive**（已知gap，`models.py:188-195`承认） |
| FamilyNeed（NeedSignal/FamilyNeed/NeedProfile/SolutionDraft/FamilyConfirmedOutcome） | captured_at/created_at/confirmed_at | **tz-aware (UTC)** |
| Growth（growth_intents） | confirmed_at | **tz-aware (UTC)** |
| Assessment（AssessmentSession/AssessmentResponse） | started_at/submitted_at/captured_at | **naive**（Pydantic，NestJS遗留） |
| Assessment（AiRunRecord/ai_run_ledger） | started_at/completed_at | **tz-aware (UTC)** |
| Action（DailyActionProjection） | 强制 `require_event_time` tzinfo校验 | **tz-aware (UTC)** |
| Service（BookingRequest/ServiceRecord/ServiceEvent） | created_at/updated_at | **naive**（故意，SQLite兼容） |
| Memory（MemoryRefRow） | created_at/expires_at | **tz-aware (UTC)** |
| Growth Graph（ai_growth_graph_edges） | observed_at/expires_at | **tz-aware (UTC)** |

**结论**：naive/aware 混用是既有事实，不是本次要修的 bug。任何 WM-003+
的 source adapter 都必须在适配器内部做 naive→aware 转换（WM-002 的
`family_source_adapter.py`/`family_need_source_adapter.py` 已经这么做，
后续 adapter 应复用同一模式：`_aware()` helper，非空naive一律
`.replace(tzinfo=UTC)`）。

## 1. Family Core（已有适配器，WM-002）

- 实体：`Family`/`FamilyMember`/`FamilyRelationship`
  （`backend/domains/family/domain/entities.py`）
- 表：baseline `0001_family_identity.sql`（`families`/`persons`/
  `family_relationships`）
- 确认概念：无AI角色，全部人工建立的关系事实，`FamilyRelationship`本身
  "authorises nothing"（不推断consent）
- Outbox：无（Family Core 变更频率低，暂无事件流）
- Evidence/Provenance：无专门字段——这是权威域本身，不需要自证
- **已有适配器**：`family_member_atom`/`family_relationship_atom`
  （`source_adapters/family_source_adapter.py`），产出 `family.member_of`/
  `family.relationship` FACT

## 2. FamilyNeed（部分已有适配器，WM-002；Outcome部分未接）

- 实体：`NeedSignal`(N0) / `FamilyNeed`(N1-N8) / `NeedProfile`(N2) /
  `SolutionDraft`(N3) / `AssignmentPlan`(N4) / `FamilyConfirmedOutcome`(N6/N7)
  （`backend/domains/family_need/domain/entities.py`）
- 表：`family_need_signals`/`family_needs`/`need_profiles`/`solution_drafts`
  （migration 0055）；`family_need_confirmed_outcomes`/
  `family_need_assignment_plans`（migration 0058）
- 确认概念：`.confirm()`只能由`FAMILY_GUARDIAN`/`FAMILY_MEMBER`/`OPERATOR`
  调用；`FamilyConfirmedOutcome.confirmed_by`强制人工
  （`assert_family_outcome_confirmer`）；`SolutionDraft`若`author_type=AI`
  则不能超过DRAFT状态
- Outbox：事件名`"family_need.outcome_confirmed"`，已有真实消费者
  `backend/intelligence/context_engine/family_need_outcome_consumer.py`
  + `family_need_outcome_poller.py`——**这是 WM-003 最值得复用的既有模式**
- Evidence/Provenance：`evidence_refs`（tuple of `EvidenceRef`，本次会话
  刚加了`epistemic_status`字段）；`AssignmentPlan.authorization_basis`
  记录"哪个家庭动作授权了这个分派"
- **已有适配器**：`family_need_atom`（`family_need_source_adapter.py`），
  只覆盖 `family.active_need`/`family.confirmed_need`；**`raw_text`（家庭
  原始表达，SELF_REPORT/OTHER_REPORT候选）与`FamilyConfirmedOutcome`（
  HELPED/PARTIALLY_HELPED/DID_NOT_HELP，Outcome信号）尚未有适配器**——
  是 WM-003/WM-004 最自然的下一步，且 Outcome 已经有现成 outbox 消费者
  模式可以照抄

## 3. Assessment / Growth（无适配器，需新建）

- Assessment 实体：`AssessmentSession`/`AssessmentResponse`
  （baseline `0043_ui02_versioned_family_assessment.sql`，NestJS所有）；
  `AiRunRecord`（`ai_run_ledger`，migration 0069，诊断用途无family FK）
- Growth 实体：`growth_intents`（baseline 0020 + 0044扩展；无独立Python
  entity class，只有SQL+command handler）
- 确认概念：`DecideGrowthHypothesisCommand.actor_type`强制`HUMAN`，
  `PolicyEngine.human_only=True`——R9边界在Assessment层，Growth只接收
  已确认的意图
- Outbox：Growth 有真实 `OutboxEvent`：`GrowthIntentConfirmed`
  （`sqlalchemy_growth_intent_confirmation.py:83`），payload含
  `signal_ref`/`provenance_ref`/`evidence_refs`/`human_gate_receipt_ref`
- Evidence/Provenance：`growth_intents.evidence_refs`（uuid[]）+
  `boundary='HUMAN_CONFIRMED_INTENT_NOT_OUTCOME'`（显式schema约束，不是
  推断出来的边界）
- 现有消费者：`backend/intelligence/growth_graph/projectors.py`
  `project_growth_hypothesis_confirmation()`，同UoW内联投影，**不是**
  独立outbox poller
- **无适配器**——`growth_intents`是 WM-003 最该优先接的表：已有确认边界、
  已有evidence_refs、已有outbox事件，比Service/FGCN成熟得多

## 4. Action / Service / FGCN（无适配器，成熟度不均）

- Action：`DailyActionProjection`（`application/daily_action.py`），
  `execution_status`枚举完整（NOT_STARTED→COMPLETED/PARTIAL/
  NOT_COMPLETED/CANCELLED），`require_event_time`强制tz-aware
- Service：`BookingRequest`/`ServiceRecord`/`ServiceEvent`（outbox）/
  `FamilyFeedback`（HELPED/PARTIALLY_HELPED/DID_NOT_HELP，append-only，
  allow-list文本）——`ServiceEvent`有outbox表`family_service_events`但
  **无内置consumer**，事件停留在PENDING直到外部adapter处理
- FGCN：`ServiceCase`/`ServiceTask`/`TaskAssignment`是真实持久化对象
  （baseline表），`ServiceDelivery`的证据目前塞在`ServiceTask.deliverable`
  JSON字段里，**独立`service_deliveries`表尚不存在**（fgcn代码自己承认
  "is still a target-state object"）
- **无适配器**——这三个域比Family/FamilyNeed/Growth都不成熟（Service
  outbox无consumer、FGCN证据表未独立化），列为 WM-004 及以后候选，
  不建议在WM-003优先做

## 5. 支撑子系统：Consent / Memory / Growth Graph

- **Consent**（`family/domain/entities.py:259` `Consent`类 +
  `backend/platform/consent/gate.py` `ConsentGate.check()` +
  `models.py` `ConsentGrant.is_active_at()`）：`purpose`枚举
  （SERVICE/ASSESSMENT/AI_PERSONALIZATION/GROWTH_TRACKING）、
  `status`（GRANTED/REFUSED/WITHDRAWN/EXPIRED）、naive UTC时间戳
  （已知gap）。**这是`ContextScope.consent_version`/`consent_granted`
  的真实上游**——WM-003+的source adapter在构造scope时应该经
  `ConsentGate.check()`，不是自己编一个`consent_granted=True`。
- **Memory**（`backend/intelligence/memory/store.py`
  `MemoryRefRow`/`MemoryRef`）：tz-aware UTC，`assert_readable_by`模式与
  World State Kernel的`assert_readable_by`几乎同构（同一治理纪律的两处
  独立实现）——**只存provenance引用，不存原始内容**，这条纪律
  World Model也应该继续遵守（已经遵守，`WorldStateAtom.value_ref`目前
  是value_ref字符串，未来长文本应该像Memory一样只存ref不存全文，是个
  待办但本次不追加范围）。
- **Growth Graph**（`backend/intelligence/growth_graph/store.py`
  `GrowthGraphEdgeRow`，migration 0023）：确认是**纯只读投影**——
  `SqlAlchemyGrowthGraphProjection.project()`只被Growth的confirmation
  adapter调用（worker专属写入），AI侧只能`query()`读取并经
  `assert_readable_by`。这个模式和WM-001的Atom Store设计几乎一样
  （scope校验、evidence_refs必填、tz-aware），说明本次WM-001的设计
  方向与仓库既有模式一致，不是另起一套。

## 6. WM-003 优先级建议（证据，非决定）

按"已有确认边界+已有Outbox/Consumer模式+tz-aware"三项成熟度排序：

```text
1. Growth（growth_intents）      — 已有OutboxEvent，只是内联而非独立poller
2. FamilyConfirmedOutcome        — 已有独立consumer模式可以照抄
                                    (family_need_outcome_consumer.py)
3. NeedSignal.raw_text           — 需要新设计SELF_REPORT/OTHER_REPORT
                                    的适配（当前只适配了确认后的FamilyNeed）
4. Action（DailyActionProjection）— tz-aware但无outbox，需要新写consumer
5. Service/FGCN                  — outbox无consumer、证据表未独立化，
                                    成熟度最低，建议排最后
```

本表是证据排序，不是本次会话的执行承诺——是否照此顺序做 WM-003，
以及具体范围，留给下一次会话确认。
