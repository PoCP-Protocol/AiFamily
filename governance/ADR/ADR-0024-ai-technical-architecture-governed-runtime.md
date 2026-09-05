---
id: ADR-0024
title: AI 技术架构采用受治理的 Family Growth Intelligence Runtime
type: adr
status: proposed
version: 0.1
owner: chief-architect
created: 2026-08-30
updated: 2026-08-30
canonical: false
---

# ADR-0024：AI 技术架构采用受治理的 Family Growth Intelligence Runtime

## Context

业务架构、分级流程架构、数据架构和应用架构已经确定。AI 层如果直接从
“五个 Agent”或“选一个模型”开始，容易重新落回传统业务系统加 AI 插件的形态，
也会违反家是港湾、AI 不写事实、未成年人保护和三环境功能等价等上位约束。

当前工作区已有 Model Gateway 的实验代码，以及 Context Engine 的内存原语；
尚无 Agent Runtime、Tool Runtime、Prompt/Schema Registry、统一 Safety、
Human Gate、Evaluation 和 durable AI trace。技术设计必须区分当前能力和目标形态。

## Decision

1. **平台中心采用 Family Growth Intelligence OS**：Family Context、Family State、
   Evidence、Growth Graph、Intervention 和 Service Blueprint 是核心资产；Agent
   是执行者，模型是可替换件。
2. **保留三个进程边界**：family_api 负责身份、权限、同意、业务事实和 Named Action；
   ai_runtime 负责上下文、生成、工具和安全；workflow_worker 负责跨时长调度、
   人工任务、重试、补偿、评估和投影重建。
3. **AI Runtime 只读业务投影，不读业务 ORM，不写业务事实**。AI 输出固定为
   Draft、Perspective、Recommendation 或 HumanTask；跨到 Fact 必须经非 AI
   Actor 的 Human Decision 和业务域 Named Action。
4. **Model Gateway 是唯一供应商边界**。凭据、供应商准入、data_class、超时、
   Attempt、schema 校验、Provenance 和受控路由集中在该边界；默认不自动重试，
   只有已批准供应商的基础设施失败才允许切换。
5. **先建 Family Context 和 Evidence，再建单一 Agent 闭环**。优先把
   S04→S05→S06→S07 的 Context Snapshot、Hypothesis Draft、Human Decision、
   ActionRecord 和 Feedback 跑通；多 Agent 协同延后。
6. **PostgreSQL 是 AI 技术对象的首选持久化边界**。业务事实仍在各业务 schema；
   AI 使用独立技术表。向量索引可以采用 pgvector，但必须先通过主体级删除、
   留存、访问控制和重建测试，不能以不可删除的外部向量库作为前提。
7. **Prompt、Schema、Knowledge、Agent、Tool 都版本化登记**。治理边界统一登记在
   `governance/AI_USE_CASE_REGISTRY.yaml`；已发布版本不可
   原地修改；每次生成绑定版本、ContextSnapshot、Evidence refs 和完整
   Provenance。
8. **dev/test/prod 功能等价**。三环境共享同一 AI 用例、状态机、错误、闸门、
   工作流和评估门槛，只替换 synthetic data factory、Fake/Deterministic/
   sandbox adapter、容量和密钥。
9. **采用能力路由而不是供应商路由**。业务用例声明推理能力和数据等级，不在
   领域代码中声明具体模型名称；供应商是否可处理未成年人数据由治理登记决定。

## Consequences

正面影响：

- 护城河落在长期家庭上下文、证据、服务蓝图和反馈闭环，而不是某个模型品牌。
- Draft/Fact、Perspective/Recommendation、Action/Outcome 边界可以被类型、路由、
  事件和测试共同执行。
- 可在无获准外部供应商时使用完全等价的 deterministic/fake adapter 验证完整流程。
- 删除权、DPIA、审计、解释权和人工复核在数据与运行链中有固定落点。

代价和限制：

- 首批交付不能同时铺开五个 Agent；必须先完成 Context、Human Gate、Eval 和
  一条真实业务纵向切片。
- AI 技术表、事件 envelope、Workflow Worker 和运维能力投入较大，不能只做
  一个同步 HTTP 调用。
- 外部模型供应商的合规准入可能长期为零，production 必须保留人工/确定性
  降级路径。

## Rejected alternatives

### A. 以 LLM/Agent 为中心的“超级助手”

拒绝原因：会把领域语义、事实写入和权限判断推给概率模型，破坏 R7、R8、R9，
也无法解释数据删除和人工责任。

### B. 每个业务域各自接入模型

拒绝原因：供应商调用、凭据、重试和审计会重新散落，复现源系统已发生的
直连和治理失效。

### C. 先建多 Agent 协同，再补上下文和评估

拒绝原因：会放大未解决的身份、记忆、工具权限、人工接管和质量漂移问题；
不符合商业战略中 P0 Context、P1 增量智能、P2 Intervention、P3 多 Agent 的顺序。

### D. 只在开发环境返回假 AI 结果

拒绝原因：测试环境会失去完整路径，无法验证 schema、Safety、Provenance、
Human Gate、超时、重试和删除；违反功能等价规范。

## Guardrails

本 ADR 落地后，以下检查必须进入架构/CI：

- ai_runtime 不得 import backend.domains.* repository 或 ORM；
- ModelDraft 不得变更 may_mutate_business_state=false；
- AI 请求必须有 data_class、purpose、context_snapshot_ref、prompt/schema version；
- 生成物 evidence_refs 非空，禁止家庭总分、排名和儿童商业营销字段；
- 高影响动作必须有 HumanTask 和非 AI Actor 的 HumanDecision；
- AI 技术对象和向量索引必须支持主体级删除与留存证明；
- dev/test/prod 的 AI contract、状态机和错误码必须相同。

## References

- docs/01_strategy/COMMERCIAL_VALUE_STRATEGY.md
- docs/05_ai/AI_NATIVE_PRINCIPLES.md
- docs/05_ai/AI_ARCHITECTURE.md
- docs/05_ai/AI_TECHNICAL_ARCHITECTURE.md
- docs/06_platform/APPLICATION_ARCHITECTURE.md
- docs/07_data/DATA_OBJECT_TABLE_RELATIONSHIP_CATALOG.md
- docs/10_engineering/ENVIRONMENT_PARITY.md
- docs/12_governance/COMPLIANCE_HARD_CONSTRAINTS.md
- governance/REPOSITORY_CONSTITUTION.md
