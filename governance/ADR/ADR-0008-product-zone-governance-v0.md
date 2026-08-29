# ADR-0008: Product Zone Assessment Governance V0（三区评估治理：生命周期/证据门槛/Human Gate）

- **Status**: Accepted
- **Date**: 2026-08-29
- **Deciders**: project-owner / chief-architect（迁自 family-ai `architecture/ADR_PRODUCT_ZONE_GOVERNANCE_V0.md`，PR-002/PR-002R）
- **Supersedes**: null
- **Superseded By**: null

## Context

ADR-0007 冻结了三区评估的数学模型；本 ADR 冻结围绕这个模型的治理外壳——谁能批准、什么时候能批准、批准前必须满足什么证据门槛、历史结果能不能被后来的 policy 改写。这条治理链路直接沿用宪章 R6（无审计不得改状态）、R8（高影响行为过闸）、R9（AI 输出不得自动成为事实）的既有原则，不新造一套。

## Decision

### 1. Evidence 是硬门槛，复用既有证据体系

每条 `DimensionAssessment` 必须携带 `dimension/score/rationale/evidence_refs/evidence_strength/assessed_by/assessed_at`，`evidence_refs` 非空是 schema 级校验，不是软提醒。**不新建第二套证据体系**——`evidence_refs` 指向 `product_intelligence` 域已有的 `Evidence`/`MarketSignal`/`CustomerInsight` 对象。

硬规则：**无证据 → 不可进入 Review。** 评估可以被打分（`SCORED` 状态，产出 `recommended_zone`），但没有六个维度全部有证据引用，不能进入 `UNDER_REVIEW`/`APPROVED`。

### 2. 分类 vs 分数——三分数并存，zone 是派生标签不是互斥分类

`commodity_score`/`advantage_score`/`unique_score` 三个分数独立存储，**不互斥**——一个能力可以同时有一定的同质基础和一定的独占层。`recommended_zone`/`approved_zone` 是从三分数派生的单值字段，用于 Portfolio 汇总和 Human Gate 决策，但不取代三分数本身。

`recommended_zone`（算法结果）与 `approved_zone`（人工经营判断）是**两个永不互相覆盖的独立字段**。二者不一致时，`override_reason` 是必填项，不是可选元数据。

### 3. `ZonePolicyVersion`——"重算不重写历史"的机制

```text
policy_id / version / dimension_definitions / weights / thresholds /
classification_rules / review_policy / effective_from / status / checksum /
scoring_algorithm_version
```

每条 `ProductZoneAssessment` 记录自己是哪个 `zone_policy_version` 算出来的。**改 policy 产生新版本、向后重算，绝不改写历史评估已存的分数/`recommended_zone`。** 相同维度输入 + 相同 policy + 相同算法版本 = 相同结果与相同 checksum，这是可测试的不变量，不是设计意愿。

**PR-002R 收口新增（同 policy_id 唯一 ACTIVE 版本）**：任意时刻，同一个 `policy_id` 最多有一个 `status=ACTIVE` 的版本。应用层读取时 fail closed 校验（发现多个 ACTIVE 立即报错，不静默取第一条），数据库层用 partial unique index 双重保证（`WHERE status='ACTIVE'`）。

### 4. Human Gate——权限模式与"UNIQUE 双签"的诚实立场

延续 `product_intelligence` 域已有的 Permission Pattern，新增权限 `product_intelligence.zone.review`：

```text
approved_zone 只能由 actor_type == HUMAN 且持有 product_intelligence.zone.review 权限的 actor 设置
AI / SYSTEM 无论持有什么权限字符串都不得批准
```

**关于"UNIQUE 是否必须双签"**：源仓库的只读研究给出的建议是"产品负责人+战略负责人双签"作为**通用**评审政策，不是"仅 UNIQUE 需要双签、其它档位单人即可"这条具体规则的证据。本 ADR 如实记录这个证据边界，不把研究结论套到一个更窄的具体规则上：

- `ZonePolicyVersion.review_policy`（如 `{"unique_requires_reviewers": 1}`）是可配置字段，V0 默认单人审核。
- 代码层面支持未来把这个值改成 >1（对应"收集多个 approve 调用"的机制扩展点），但 V0 不实现真正的多签收集逻辑，也不把"仅 UNIQUE 双签"硬编码为业务规则。

复审有效期：`APPROVED` 评估默认 6 个月复审窗口（比通用年度周期更短，因为 AI 能力/竞争格局变化快）。到期不自动失效，查询层标注为"待复审"（`PortfolioZoneRow.is_pending_re_review`），不静默把过期结果当作仍然有效。

### 5. 生命周期——冻结状态机

```text
DRAFT → SCORED → UNDER_REVIEW → APPROVED
                       ↓
                   REJECTED

APPROVED → RETIRED
```

`DRAFT → APPROVED` 直接跳非法。AI/SYSTEM 不能触发任何进入 `APPROVED` 的迁移。每次迁移递增 `version`，记录 `actor_id/actor_type/timestamp/reason/trace_id`——与 `GrowthHypothesis.mark_validated` 同一套审计形状，不为这个新对象重新发明一套。

### 6. Portfolio 口径——严格六桶（PR-002R 收口）

六个 assessment 状态与六个统计桶一一对应，不重不漏：

```text
unreviewed_count  = DRAFT + SCORED + UNDER_REVIEW
rejected_count    = REJECTED（独立成桶，不混入 unreviewed）
retired_count     = RETIRED（独立成桶，不进任何"当前活跃分布"，包括不进 unreviewed）
commodity/advantage/unique_count = APPROVED 状态按 approved_zone 拆分
```

六桶之和 = `total_count`，这是运行时断言的不变量，不只是测试断言。**Portfolio 统计口径严格用 `approved_zone`，不用 `recommended_zone`**——一个已打分但未经人工批准的 UNIQUE 建议，不计入 `unique_count`，只计入 `unreviewed_count`。

### 7. AI 边界（V0）

`live_model_call_authorized = false`（见 `governance/AUTHORIZATION_REGISTRY.yaml` 等价登记，AiFamily 内暂无对应 YAML，登记状态见 `governance/MIGRATION_MANIFEST.yaml` → `product_intelligence_v2`）。`assessment_origin` 可以是 `HUMAN | RULE | AI_PROPOSAL`，V0 不接真实模型调用，真实 AI 建议留给未来的 AI Use Case 注册机制（宪章 R10）。

### 8. Postgres 跨租户 trigger——纵深防御，不是主修复手段

`migrations/0059_product_zone_engine_v0.sql` 里的跨租户校验 trigger 是数据库层纵深防御。**主要修复手段在应用层**：`application/zone_commands.py::create_zone_assessment` 会先加载 `ProductConcept`（通过 `product_intelligence` 域已有的、tenant-scoped 的 `ProductIntelligenceRepositoryPort.load_product_concept`），跨租户引用在应用层就已经被拦截，trigger 只是防止应用层被绕过时的最后一道防线。两者都需要真实 Postgres 测试验证（`tests/test_zone_postgres_integration.py`），不能只靠 SQLite 内存测试证明。

## Alternatives Considered

**A. `zone` 只做单值互斥分类（三选一），不保留三个独立分数**——支持理由：模型更简单，前端展示只需要一个标签。否决理由：真实场景里一个能力可以同时有同质基础和独占层（例如底层 OCR 是同质区，叠加专有语料后的整体能力是独占区），互斥分类会强迫做无信息量的取舍，丢失"这个能力该在哪一层继续投入护城河"这个真正有决策价值的信息。

**A2. `recommended_zone` 与 `approved_zone` 共用一个 `zone` 字段，人工批准时直接覆盖**——支持理由：字段更少，模型更简洁。否决理由：一旦覆盖，AI 建议的原始值就永久丢失，无法做"AI 建议 vs 人工判定"的偏差分析（例如发现 AI 在某类场景系统性高估独占区），也违反宪章 R9 的 Perspective/Fact 分层精神——覆盖等于让 Recommendation 直接变成了 Fact。

**A3. UNIQUE 档位硬编码要求两名不同 HUMAN 双签**——支持理由：独占区判断影响重大，直觉上应该更审慎。否决理由：本 ADR 依据的只读研究给出的证据是"双签应作为通用政策"，不是"仅 UNIQUE 需要、其它档位单人即可"这条具体规则的证据——把一般性建议套到一条更窄的具体规则上，是在编造研究没有支持的结论（这类"没有科学验证却假装已验证"的模式正是 `docs/00_system/CURRENT_SYSTEM_BASELINE.md` 与 ADR-0007 都在防的）。改为可配置 `review_policy` 字段，V0 默认单人审核，双签机制留作未来按真实数据决策的开放项。

**A4. 用一张独立的 ProductZoneEvidence 表/对象存三区专用证据**——支持理由：证据结构可以完全为三区场景定制。否决理由：违反"不新建第二套证据体系"的原则（本 ADR §1），会造成两套并行的证据溯源路径，增加维护与审计成本，且 `product_intelligence` 域已有的 `Evidence`/`MarketSignal`/`CustomerInsight` 完全够用。

## Consequences

### 正面
- `recommended_zone`/`approved_zone` 分离使得未来可以量化"AI 建议准确率"，为后续引入真实 AI 打分（当前仍 `live_model_call_authorized=false`）积累校准数据。
- Portfolio 严格六桶口径让经营层看到的"当前独占区占比"永远只反映**已批准**的判断，不会被"AI 建议但还没人审"的乐观分数污染。
- Active Policy 唯一性的双重保证（应用层 + DB 约束）让"policy 数据不一致"这种故障模式在数据层面就不可能发生，不依赖应用代码永远正确。

### 负面 / 代价
- 六个状态到六个桶的严格映射增加了实现与测试的复杂度（对比"REJECTED 混进 unreviewed"这种更简单但语义模糊的旧口径）。
- 双签机制"只搭骨架不强制启用"意味着如果经营层现在就想要 UNIQUE 双签，还需要一次新的 policy 配置改动+可能的新 ADR，不能立等可用。

### 需要接受的风险
- Postgres 跨租户 trigger 是纵深防御，如果应用层的主修复（`load_product_concept` 校验）出现回归，trigger 是最后一道防线，但 trigger 本身依赖真实 Postgres 环境才会生效——本地 SQLite 测试环境下这层防御不存在，只能靠应用层测试兜底。

## Enforcement

由 `backend/domains/product_intelligence/tests/test_zone_review_governance.py`（HUMAN+无权限/HUMAN+错权限/HUMAN+对权限/AI+权限仍拒/SYSTEM+权限仍拒五个场景）、`test_zone_active_policy_uniqueness.py`（同 policy_id 两个 ACTIVE 版本 fail closed）、`test_portfolio_zone_view.py`（六桶口径与不变量）、`test_zone_postgres_integration.py`（真实 Postgres 上的跨租户 trigger 与唯一索引）共同强制执行。`migrations/0059_product_zone_engine_v0.sql` 与 `migrations/0060_product_zone_engine_canonical_cleanup.sql`（见 `migrations/README.md`，当前是 pre-Alembic 的域内 raw SQL）承载对应的数据库层约束。

## References

- `governance/ADR/ADR-0007-product-zone-scoring-v0.md`（数学模型）
- `backend/domains/product_intelligence/domain/zone_entities.py`（可执行实现）
- `backend/domains/product_intelligence/application/zone_commands.py` / `zone_queries.py`
- `governance/MIGRATION_MANIFEST.yaml` → `product_intelligence_v2`
