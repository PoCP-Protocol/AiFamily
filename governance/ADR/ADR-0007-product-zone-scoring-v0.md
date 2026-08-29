# ADR-0007: Product Zone Scoring Model V0（三区战略引擎打分模型）

- **Status**: Accepted
- **Date**: 2026-08-29
- **Deciders**: project-owner（迁自 family-ai `architecture/ADR_PRODUCT_ZONE_SCORING_V0.md`，PR-002/PR-002R）
- **Supersedes**: null
- **Superseded By**: null

## Context

`backend/domains/product_intelligence` 需要给 `ProductConcept` 做"同质区/优势区/独占区"三区归属评估（Three-Zone Strategy Engine）。这不是一个"AI 打个分"的黑箱，而是一条可审计、可复算、有人审的经营判断链路（见 ADR-0008 的治理部分）。本 ADR 只冻结**数学模型**本身：六维度语义、两指数公式、分区规则、以及"哪些是 policy 数据、哪些是可追溯算法版本"的边界。

本 ADR 是 family-ai 迁移资产（`governance/MIGRATION_MANIFEST.yaml` → `product_intelligence_v2`），内容取自源仓库 PR-002（首版）与 PR-002R（chief-architect 复审后的收口），迁移时未改动实质决策，仅同步了文件路径引用。

## Decision

### 1. subject_type（V0 范围）

V0 唯一合法 `subject_type` 是 **`PRODUCT_CONCEPT`**——即 `ProductZoneAssessment.subject_ref` 必须引用一个 `domains/product_intelligence` 的 `ProductConcept.id`。`ProductComponent`/`ProductDefinition`/`AIUseCase`/`Capability` 明确排除在 V0 范围外（这些对象目前只有结构壳，没有对应的已授权 PR，评它们没有对应的治理对象撑着）。

### 2. 六维度——方向语义已冻结

全部 `0..100` 打分，**方向不统一，必须显式区分**：

| 维度 | 方向 | 100 分含义 |
|---|---|---|
| `customer_scarcity` | 正向 | 客户极度稀缺、难以触达 |
| `replaceability` | **负向** | 极易被替代 |
| `data_advantage` | 正向 | 数据优势极强 |
| `network_effect` | 正向 | 网络效应极强（价值随用户数超线性增长） |
| `learning_effect` | 正向 | 越用越好效应极强 |
| `switching_cost` | 正向 | 客户迁移成本极高 |

`replaceability` 是唯一负向维度。任何消费它的计算必须用 `inverse_replaceability = 100 - replaceability`，不能直接用原始分数。

### 3. 维度间已知非独立性——不在 V0 强行去相关

`data_advantage`/`learning_effect` 高度共线；`network_effect`/`customer_scarcity` 因果关联；`replaceability`/`switching_cost` 本质是同一属性的两个视角。V0 **不做**基于真实历史数据的因子分析/PCA 去相关（没有数据支撑），而是用下面的两指数结构把共线维度分组处理，不假装六维完全正交。

### 4. 打分模型（确定性，非 LLM 黑箱）

```text
inverse_replaceability = 100 - replaceability

Differentiation Index = 组内归一化加权平均(customer_scarcity, inverse_replaceability; weights)

Defensibility Index = 组内归一化加权平均(data_advantage, network_effect, learning_effect, switching_cost; weights)
```

`weights` 来自 `ZonePolicyVersion.weights`，两组各自独立归一化（除以本组权重和，不是全局六维权重和）——V0 默认 fixture 是等权（每维 1.0），归一化后精确退化为等权平均，不改变既有业务结果；改权重只影响对应组的指数。

分类规则（floor-gate,不是纯线性加权求和）：

```text
UNIQUE      IF  Defensibility Index >= thresholds.unique_defensibility_min（V0 fixture=75）
            AND 每一个 {data_advantage, network_effect, learning_effect, switching_cost}
                >= thresholds.unique_floor_gate_min（V0 fixture=50）
            （floor gate：均值再高，任一支柱塌了也不算独占）

COMMODITY   IF  Differentiation Index < thresholds.commodity_differentiation_max（V0=40）
            AND Defensibility Index < thresholds.commodity_defensibility_max（V0=40）

ADVANTAGE   其余情况
```

阈值（75/50/40/40）是 `PROVISIONAL_POLICY_V0` fixture 值，未经真实历史数据校准，随 `ZonePolicyVersion` 版本化，可在不改代码的前提下调整。

三个分数（`commodity_score`/`advantage_score`/`unique_score`）由两指数映射而来，映射公式记录在 `zone_scoring_engine.py::compute_three_scores` 的代码注释里（ADR 未强制唯一公式，允许工程实现层给出自洽设计）。

### 5. 0.5 惩罚系数与算法版本可追溯性（PR-002R 收口新增）

非独占区的 `unique_score` 有一个惩罚系数，收进 `ZonePolicyVersion.thresholds["non_gated_unique_penalty_factor"]`（默认 0.5），不再是引擎代码里的字面常量——理由与阈值相同：影响结果的规则要么是 policy 数据要么是可追溯算法版本，不能是隐藏常量。

`ZonePolicyVersion.scoring_algorithm_version`（默认 `"ZONE_SCORING_V0"`）记录一个 policy 版本的分数是在哪个引擎版本下算出来的，纳入 `compute_checksum()`。引擎对不认识的算法版本 fail closed，防止未来 `ZONE_SCORING_V1` 静默用不兼容公式重算旧数据。

### 6. 每维度期望证据类型

| 维度 | 证据类型 |
|---|---|
| `customer_scarcity` | 目标客群渗透率/市占率、TAM 稀缺度、CAC 趋势 |
| `replaceability` | 竞品/替代方案数量、功能重叠度分析、价格弹性信号 |
| `data_advantage` | 数据规模/专有性、更新频率、竞品复制成本估算 |
| `network_effect` | MAU/DAU 超线性增长、跨边依赖强度 |
| `learning_effect` | 使用时长对效果改善曲线、经验曲线成本下降 |
| `switching_cost` | 历史流失率、迁移成本/时间调研、合同锁定条款 |

证据必须是历史行为数据或第三方可验证数据，不是产品经理主观判断——呼应 `docs/05_ai/AI_NATIVE_PRINCIPLES.md`/宪章 R9 的 `Perspective≠Fact` 原则，这不是给这条能力新发明一套证据体系。

## 相关文档

- `governance/ADR/ADR-0008-product-zone-governance-v0.md`（生命周期/证据门槛/Human Gate/Portfolio 口径）
- `backend/domains/product_intelligence/domain/zone_scoring_engine.py`（可执行实现）
- `governance/MIGRATION_MANIFEST.yaml` → `product_intelligence_v2`
