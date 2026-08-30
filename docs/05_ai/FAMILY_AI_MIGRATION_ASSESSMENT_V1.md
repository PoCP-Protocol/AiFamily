---
id: AI-MIGRATION-ASSESSMENT-001
title: 源仓库 Family AI 平台设计与代码迁移评估 V1
type: assessment
status: draft
version: 1.0
owner: chief-architect
created: 2026-08-30
updated: 2026-08-30
canonical: false
supersedes: null
superseded_by: null
---

# 源仓库 Family AI 平台设计与代码迁移评估 V1

> 本文只读审查旧系统仓库的规格、知识库、数据库迁移和 TypeScript 实现，目的不是
> 把旧系统整体搬回，而是识别可验证的设计资产、可重写的算法和必须淘汰的历史实现。
> 源仓库不作任何写操作；所有迁移必须登记到当前仓库的治理清单并重新通过 Python-only、
> AI Runtime 隔离、三区方法论和未成年人合规约束。

## 1. 总体判断

旧系统最有价值的不是某个 UI 或某个模型适配器，而是把“专业方法 → 证据 → Agent →
Action → Outcome → Learning”写成了可以检查的结构。它对当前 SPD-AI 的直接启发是：

```text
证据卡片和许可
  → 组件/方法的适用边界、剂量、禁忌、人工要求
  → 服务产品定义和可回放编译
  → 真人交付与质量复盘
```

迁移原则：**迁移语义和测试意图，重写运行时和数据适配器；不迁移第二套 canonical
模型，不迁移供应商耦合，不迁移只在 Dev fixture 中成立的产品能力。**

## 2. 设计思想评估

### 2.1 强价值：可作为当前平台的上位输入

| 旧系统资产 | 证据位置（源仓库相对路径） | 迁移等级 | 对 SPD-AI 的用法 |
|---|---|---|---|
| FGAIM 主链 `State → Decision → Action → Outcome → Learning` | `10_规格_spec/01_实施方法论/Family_FGAIM_实施方法论_V2.0.md` | A | 作为每个服务产品的 Outcome Link 和 Definition of Done |
| A0 + 8A 架构法 | 同上 §4 | A | 映射为价值/业务/本体/证据/AI/体验/工程/治理评审维度 |
| 九阶段生命周期与 Gate 0–6 | 同上 §5、§9 | A | 压缩成 SPD 的设计、编译、模拟、发布四道硬闸门 |
| “AI 是建议，Named Action 才改变事实” | `10_规格_spec/02_总体蓝图/Family_整体技术架构_V2.0.md` | A | 与当前 R7/R8/R9、Principal 控制面合并 |
| Modular Monolith First / Build vs Buy | 同上 §5、§22 | A | 支持当前 Python 模块化单体；不提前拆微服务 |
| 三条成长主线 Child/Parent/Relationship | `10_规格_spec/02_总体蓝图/Family_总体蓝图方案_V2.0.md` | B | 作为服务产品的适用对象和排除条件，不作为设计平台的三套数据库 |

### 2.2 可迁移但必须改写

- 旧系统把“家庭成长平台”和“服务编排”放在同一个产品蓝图里；当前应拆成
  `product_intelligence` 的设计真相、`service` 的交付事实、AI Runtime 的草案输出。
- 旧系统的 `Family Ontology`、`Intervention`、`Growth Profile` 命名可以保留语义，
  但字段、状态、租户和数据分类必须以当前仓库的 Domain Registry 与平台内核为准。
- 旧系统的 `30 → 100 → 500` Pilot 节奏可以保留为交付管理模板，不能当成已验证的
  商业结论或自动扩容规则。

## 3. 最值得迁移的代码资产

### M1：循证知识库五层模型（最高优先级）

源代码：

- `20_知识_knowledge/byresearch/evidence.py`
- `20_知识_knowledge/byresearch/schema.py`
- `20_知识_knowledge/byresearch/library.py`
- `20_知识_knowledge/byresearch/compile_principal_bundle.py`
- `20_知识_knowledge/library/*.yaml`

值得迁移的部分：

1. E0–E7 证据等级与 `Provenance` 分离；内部主张、推断、模拟数据不能支撑有效性结论。
2. `Evidence.gate()`、来源必须登记且可核验、Claim 不可越过证据等级的门禁。
3. Theory → Construct → Modality → Method → Program 五层卡片，以及跨层引用完整性检查。
4. `Library.validate()` 的未知字段拒绝、孤岛检查、构念可测量检查、方法禁忌/剂量/人工
   要求检查。
5. Python 构建、TypeScript 只消费编译 bundle 的边界；失败时 `grounded=false`，不编造引用。

迁移落点：在 `backend/intelligence/knowledge` 建立协议和适配器，把结果映射成当前
SPD-AI 的 KnowledgeSource/DocumentVersion/Claim/Binding；不要直接把 YAML 当作运行时
数据库，也不要让家庭私有事实进入共享卡片库。

不能原样迁移：`library/*.yaml` 的业务内容、年龄和工具适配结论仍需当前教研/合规审核；
源库当前有设计卡不等于工具效度或产品疗效已经验证。

### M2：声明式 Agent / Skill 治理

源代码：

- `50_开发_dev/agents/registry/*.yaml`
- `50_开发_dev/packages/principal-runtime/src/skill.ts`
- `50_开发_dev/agents/chief-architect/CAPABILITY_TRUTH_MODEL.md`

值得迁移的部分：

- Agent 必须声明 Purpose、Objects Read、Decision、Evidence、Knowledge、Tools、Memory、
  Allowed/Forbidden Actions、Autonomy、Human Gate、Eval。
- `ObjectSkill` 为属性声明 `truth_type`、owner、mutability；FACT 只能
  `named_action_only`，AI_INFERENCE/PROPOSAL 只能只读。
- `CapabilitySkill` 没有运行时授权就 FAIL CLOSED，Skill 不能自授权。
- L0–L6 能力成熟度和“文档/Schema/Mock/集成/用户价值”降级规则。

迁移落点：将这些字段并入 `governance/AI_USE_CASE_REGISTRY.yaml`、当前 Principal 路由
和能力登记；必要时在 `backend/intelligence/principal` 增加轻量 Skill Registry。不要
直接移植旧的 TypeScript runtime 包，否则会形成第二套 AI Runtime。

### M3：Principal 的确定性安全、质量和循证护栏

源代码：`50_开发_dev/packages/principal-ai/src/index.ts` 及其测试。

值得迁移的部分：

- `safetyPrecheck` / `safetyPostcheck`：生成前后都做风险升级，不能由模型降低风险等级。
- 家长本人已发生激烈言语升级、临界失控的确定性 REVIEW 护栏；只升不降，独立于生成式
  judge。
- `validatePrincipalOutput`、`deterministicQualityFloor`：结构、风险一致性、理解贴合、
  禁止诊断/排名/效果承诺、HIGH_RISK 必须有人工边界。
- `retrieveGroundedKnowledge` 与 `ungroundedRefs`：引用必须落在已审核 bundle 中，缺
  bundle 或来源不通过时安全降级。
- `PrincipalSoulCompiler` 的版本与 hash；Soul、Prompt、Schema、引用和输出 hash 一起
  进入模型运行记录。

迁移落点：改写为 Python 纯函数和 Pydantic 契约，接入现有 `backend/intelligence/model_gateway`
与 `principal`。中文关键词只是第一层护栏，必须用当前安全样本集、误报/漏报评估和人工
升级队列复核，不能把它当作完整风险分类器。

### M4：需求到服务执行的状态机与安全出口

源代码：

- `50_开发_dev/database/migrations/0020_growth_orchestration_v1.sql`
- `50_开发_dev/apps/api/src/modules/orchestration/orchestration.service.ts`
- `50_开发_dev/apps/api/src/modules/orchestration/eligibility.policy.ts`
- `50_开发_dev/apps/api/src/modules/orchestration/recommendation.policy.ts`
- `50_开发_dev/apps/api/src/modules/orchestration/decision-integrity.policy.ts`
- `50_开发_dev/packages/contracts/src/orchestration.ts`

值得迁移的部分：

1. `NeedSignal`（非 canonical）→ 家长确认的 `GrowthIntent` → T1 Eligibility →
   `ResourceRecommendation` → 家庭 `Decision` → 声明式 `OrchestrationPlan` → 执行态
   `ServiceCase`。
2. T1 推荐与 T2 执行分离；执行只接受已持久化的 exact offer snapshot，无法复验时
   FAIL CLOSED。
3. `NO_ACTION`、`RE_RECOMMEND_REQUIRED`、`EXTERNAL_REFERRAL` 作为显式安全出口，
   不静默替换资源。
4. 稳定 Offer ID、推荐版本、能力覆盖和 decision integrity，避免客户端注入任意资源。
5. `SERVICE` 与 `AI_PERSONALIZATION` 同意分离；年龄范围、安全路线、资源准入和容量
   都在 Eligibility 中检查。

迁移落点：当前 `backend/domains/family_need` 已有 NeedSignal/NeedContext/SolutionDraft
骨架，`journey` 已有幂等、审计、事务和计划状态机；应按上述状态机补齐跨域 Port 与
投影，不复制旧表。`service` 继续拥有 ServiceCase/Task/Delivery 真相。

### M5：版本化服务协作蓝图、质量复核和返工

源代码：

- `50_开发_dev/database/migrations/0055_service_collaboration_allocation_policy.sql`
- `50_开发_dev/database/migrations/0056_service_case_allocation_basis_and_runs.sql`
- `50_开发_dev/database/migrations/0057_service_task_rework_and_reviewer_gate.sql`
- `50_开发_dev/packages/contracts/src/orchestration.ts` 中 `ServiceCollaborationBlueprintDto`、
  `ServiceTaskDto`、`ServiceContributionAllocationDto`

值得迁移的部分：

- 蓝图按版本冻结，案件保存引用/快照；变更创建新版本。
- 角色、任务模板、能力要求、分配规则、质量保留和发布规则结构化。
- 一个任务只能有一个已接受分配；质量复核人必须与交付人职责分离。
- `REWORK_REQUIRED` 创建新的返工任务，保留原任务的审核历史，不静默重置状态。
- 贡献单位与支付/佣金/结算明确隔离，避免把质量记录误当财务事实。

迁移落点：与 SPD-AI 的 `ServiceBlueprintVersion` 对接，但先落“设计蓝图 + 质量状态”
而不是分配结算；当前仓库的 commerce 轴继续遵守冻结，不从这批代码扩展交易能力。

### M6：Draft → Review → Release 的运营操作模型

源代码：

- `50_开发_dev/database/migrations/0048_communication_21day_curriculum_subsystem.sql`
- `50_开发_dev/apps/api/src/modules/principal/principal.controller.ts`
- `50_开发_dev/apps/api/src/modules/principal/principal.repository.ts`

值得迁移的部分：

- Draft、ReviewOperation、ReleaseOperation 分离；每次操作带 actor、reason、idempotency、
  request hash、correlation 和 response snapshot。
- Human Handoff 有 OPEN/RESOLVED 轨迹，审核结果不会覆盖原始模型响应。
- 回放 API 以 trace/session 为键，能够复核当时的 prompt/schema/model/风险路线。

迁移落点：为 SPD-AI 的 CompileRun、SimulationRun、HumanReviewTask、BlueprintRelease
提供操作表和回放投影；发布仍由业务域 Named Action 完成。

## 4. 只迁移设计意图，不迁移实现

| 资产 | 原因 | 当前处理 |
|---|---|---|
| `packages/ai-gateway` 的供应商适配器 | 旧业务服务仍直接 `new OpenAICompatibleAiGateway`，违反当前 R7；配置/环境和 Python Gateway 不同 | 只吸收 structured output、超时、错误分类、attempt ledger、provider registry 语义；实现留在当前 Gateway |
| `packages/contracts` 全套 TS DTO | 会与当前 Python Domain/contract 形成第二 canonical source | 仅提取字段语义；当前领域实体和 contracts 负责唯一归属 |
| `dev-core-growth.service.ts` 的硬编码卡片/确定性文案 | 是 UI/Dev 演示基线，不是 AI 能力；缺真实模型、知识和 Outcome | 可作为 synthetic fixture，不得宣称生成式能力 |
| `family-llm-gateway.service.ts` 业务层直连 provider | 违反单一模型边界，且是旧架构反例 | 重写为当前 `backend/intelligence/model_gateway` Port |
| 旧 monorepo apps/packages/modules 目录 | 语言和部署形态不同，且当前宪章已冻结 Python-only | 迁移 bounded context 和测试意图，不搬目录 |
| Kafka/GraphDB/World Model 预留 | 旧规格自己也要求 M2 不提前引入；当前没有真实流量/Outcome | 保留演进条件，暂不实现 |
| 商城/会员/支付/返佣代码 | 与当前 commerce freeze、未成年人商业边界和当前任务无关 | 不迁移；如需重启另开 ADR 与任务 |

## 5. 迁移映射到当前仓库

| 源资产 | 当前目标位置 | 迁移动作 | 前置门槛 |
|---|---|---|---|
| Evidence/Library | `backend/intelligence/knowledge` + `governance` | Python 协议、来源登记、Claim/Binding 投影 | 知识 owner、许可、删除策略 |
| Agent/Skill registry | `governance/AI_USE_CASE_REGISTRY.yaml` + `backend/intelligence/principal` | 统一字段、路由和授权检查 | registry schema、Principal route 测试 |
| Principal safety/quality | `backend/intelligence/principal` + `tests/intelligence` | 纯函数重写、样本集、fail-closed | 安全/教研评审，误报漏报阈值 |
| Need→Intent→Eligibility | `backend/domains/family_need` | 补 T1/T2、exact snapshot、显式安全出口 | Domain Registry、Consent/Audit/Idempotency |
| Blueprint/Task quality | `backend/domains/service` + `product_intelligence` | 设计蓝图与交付快照分离 | 服务 owner、版本与返工状态机 |
| Draft/Review/Release | `backend/intelligence/design_copilot` + platform audit | CompileRun/SimulationRun/ReviewTask/Release 投影 | ADR、人工角色和回滚方案 |
| ModelRun provenance | `backend/intelligence/model_gateway` | 做契约对齐，不复制 TS gateway | provider registry、环境等价测试 |

## 6. 推荐迁移顺序

1. **P0：知识证据适配器**——先迁 E0–E7、Provenance、来源核验和五层卡片校验；不接家庭
   私有数据，不接模型训练。
2. **P1：Principal 安全/质量纯函数**——把 pre/post check、Grounding、Quality Floor
   接到当前 Principal Router；先用 Fake/Deterministic adapter 完成测试。
3. **P1：服务产品编译器输入契约**——把 M4 的 T1/T2、能力覆盖、exact snapshot 和
   `NO_ACTION` 语义映射到 SPD-AI 的 12 项 compiler checks。
4. **P2：服务蓝图与返工质量**——实现 BlueprintVersion、TaskTemplate、QualityReview、
   ReworkTask；不引入结算与佣金。
5. **P2：人工评审与回放**——补 CompileRun、SimulationRun、HumanReviewTask、Release 和
   trace replay，再接 `service` 的只读发布投影。
6. **P3：真实反馈学习**——只有具备交付、质量、成本和 Outcome 证据后，才允许生成组件
   改进候选；不自动修改历史事实。

## 7. 迁移验收标准

- 所有迁移能力在 `governance/DOMAIN_REGISTRY.yaml`、`CAPABILITY_REGISTRY.yaml`、
  `AI_USE_CASE_REGISTRY.yaml` 有唯一登记。
- 任何模型输出都能追溯 model/provider/prompt/schema/context/consent/provenance，且
  `may_mutate_business_state` 恒为 false。
- 任何高风险或中风险方法都有人工责任人和可回放 ReviewTask；AI 不能自动发布。
- T1 推荐与 T2 执行使用同一 exact snapshot，失效时显式安全停止。
- 设计蓝图版本与服务案件事实隔离；回滚不删除历史交付记录。
- 共享知识 Claim 有来源、许可、适用范围、失效和删除链；家庭/儿童私有数据不进入共享库。
- 至少一条从三区证据到蓝图编译、模拟、人工审批、发布投影的完整测试路径；模拟结果
  不得被解释为疗效或家庭结果。
- 运行 `uv run pytest tests/architecture -v` 与 `uv run ruff check .`；失败必须归因到
  当前改动，不能通过放宽基线掩盖。

## 8. 结论

旧系统值得迁移的是“可验证的专业和治理骨架”，不是“旧代码的目录和供应商实现”。
对当前 SPD-AI 最关键的前三项是：

1. 循证知识五层 + 来源/许可/证据门禁；
2. Principal 的确定性安全、Grounding 和质量闸门；
3. Need → Intent → Eligibility → Decision → Plan → ServiceCase 的可回放状态机。

这三项完成后，服务产品设计编译器才有可信输入；在此之前做大规模 AI 生成、自动发布
或复杂 World Model，都会把旧系统的“设计很完整、事实未闭环”问题重新带进当前平台。
