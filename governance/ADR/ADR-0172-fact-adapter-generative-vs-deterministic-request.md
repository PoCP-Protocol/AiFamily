# ADR-0172: Deterministic Truth Projection + Generative Cognition——FACT 与认知层正式分离

- **Status**: Accepted
- **Date**: 2026-09-13
- **Deciders**: project-owner
- **Supersedes**: null（本 ADR 是对自身 Proposed 状态的裁决落地，不是推翻
  其他 ADR；正文由请示改为决定记录，Context 段保留原始冲突陈述）
- **Superseded By**: null

## Context

本次会话完成 AIFAMILY-WM-001~003（Family World State Kernel + Family/
FamilyNeed/Growth/Outcome Truth Plane 适配器）后，项目负责人提出"要按照
AGI 和 World Model 来做，而不是 if/then/else 写出来"，追问澄清后明确表示
——**是想把 FACT 适配器本身**（`family_source_adapter.py`/
`family_need_source_adapter.py`/`growth_source_adapter.py`/
`family_need_outcome_source_adapter.py`）**换成生成式**。

这与同一系列会话里已经冻结的多条决定直接冲突：

1. `governance/REPOSITORY_CONSTITUTION.md` R9（AI 输出不直写 canonical
   事实）。
2. `ADR-0169` §4（"禁止 AI 推断被静默升级为家庭事实"）。
3. `database/migrations/versions/0080_ai_family_world_atoms.py` 的数据库
   CHECK 约束 `ck_ai_family_world_atoms_ai_cannot_assert_fact`。
4. 项目负责人自己在本次会话早前发出的 `AIFAMILY-WM-001` 任务书原文
   （"V0.1 应该 70–90% Deterministic Projection"、"不要接入 LLM
   Provider"）。

Agent 未自行裁决，写成 ADR-0172（`Proposed`）正式请示。项目负责人复核
GitHub 现行架构约束（R9、`AI_NATIVE_PRINCIPLES`）与 World Model 的
replay/full rebuild/stable fingerprint/drift detection/bitemporal audit
技术要求后，给出本次正式裁决。

## Decision

**ACCEPT OPTION A 作为强制架构原则；ACCEPT OPTION C 作为 WM-004 的独立
派生能力（必须与 FACT Adapter 物理和语义分离）；REJECT OPTION B。**

正式原则命名为 **Deterministic Truth Projection + Generative Cognition**
（确定性真相投影 + 生成式认知推理）：

> AiFamily 将"真相构建"与"智能构建"严格分离。权威 FACT 仅由受治理的
> 人类/领域真相源确定性投影产生；生成式模型在其上产生明确非权威的假设、
> 未知、系统推断、解释与建议。AI 原生不是"由模型生成真相"，而是在可信
> 世界状态之上实现生成式认知。

**具体冻结条款**：

1. **FACT 投影永远保持确定性**。生成式模型不得参与 FACT atom 的创建、
   校验、转换、晋升或重写。`R9`、`ADR-0169`、数据库 CHECK 约束
   `ck_ai_family_world_atoms_ai_cannot_assert_fact` 全部保持不变，
   **不放宽数据库约束**。
2. **World Model 正式分层**：

   ```text
   Authoritative Domains
           ↓
   Deterministic Truth Adapters
           ↓
       FACT / OBSERVATION
           ↓
   Temporal Epistemic State
           ├──────────────┐
           ↓              ↓
     Conflict Engine  Generative Cognition
                           ↓
                 HYPOTHESIS / UNKNOWN / SYSTEM_INFERENCE
                           ↓
                      Belief State
   ```

   `Truth Layer ≠ Cognition Layer`。

3. **FACT Adapter 职责边界**：只做 `authoritative source → deterministic
   semantic mapping → FACT atom`，禁止 LLM summarization/classification/
   paraphrasing/inference/confidence scoring/contradiction resolution/
   ontology selection 参与。必须满足
   `stable_fingerprint(Source) == stable_fingerprint(Rebuild(Source))`，
   生成式模型不得成为这个公式的变量。

4. **AI Native 的正确解释**：不是"所有能力都要调模型"，是"确定性基础设施
   支撑生成式智能"。Identity/Consent/Authorization/Audit/Idempotency/
   Fact Projection/Temporal versioning/Deletion/Data classification
   保持确定性；Understanding/Hypothesis generation/Need reasoning/
   Unknown discovery/Explanation/Goal proposal/Planning/Resource
   reasoning/Reflection 才是生成式优先的能力。

5. **Option C 的具体落地边界**：AI 摘要/解释可以存在，但：
   - 不得实现在 FACT Adapter 内部，必须放在独立的 Generative Cognition
     Layer（WM-004 范围）。
   - 命名优先用 `SYSTEM_INFERENCE`（或独立的 `DerivedNarrative`/
     `ExplanationProjection`），不占用 `PERSPECTIVE`（`PERSPECTIVE`
     保留给真实的人/成员/专业人员观点）。
   - 若进入 Atom Store：`epistemic_kind = SYSTEM_INFERENCE`，
     `authority = DERIVED_AI`，`status = PROPOSED`，
     `source_refs`/`evidence_refs` 指向原始 FACT/证据，
     `model_ref`/`prompt_version`/`context_snapshot_ref`/`provenance`
     必填，且携带等价于 `truth_authority = NONE` 的契约——永远不能成为
     `FACT`，也不能成为新的 FACT Adapter 输入。

6. **防止 Derived AI 自我强化**：`AI-derived state MUST NOT recursively
   become authoritative evidence for FACT`。禁止
   `FACT→AI推断→AI推断→AI推断→FACT`链路；正确结构是
   `FACT→SYSTEM_INFERENCE→（人工/权威域真实动作）→新的Domain Fact`，
   只有真实权威域事件才能创造新 FACT。

7. **Model Gateway 边界与故障降级**：WM-004 生成式能力必须走
   `World Model → Context Projection → Model Gateway → Structured
   Output → Schema/Policy Validation → PROPOSED derived state`，禁止
   `World Model → provider SDK` 直连。**Model outage ≠ World Model
   truth ingestion outage**——FACT 摄入不得等待模型；Belief
   update/Unknown generation/Explanation 可以延迟或不可用，但权威 FACT
   不能丢失。FACT Adapter 事务边界不依赖 LLM latency/provider
   availability/token quota/cost。

## Alternatives Considered

**A.（本次 ACCEPTED）保持 FACT Adapter 确定性，生成式集中到 WM-004。**
支持理由：与 R9/`ADR-0169`/数据库 CHECK 约束/项目负责人自己的 WM-001
任务书原文完全一致；保证 replay/full rebuild/stable fingerprint/drift
detection/bitemporal audit 全部可靠；零额外工程量，已通过全部测试。
否决理由：无——已被采纳为强制原则。

**B.（本次 REJECTED）把 FACT 适配器换成生成式，同时收窄 R9 适用范围。**
支持理由：如果目标是让 Truth Plane 本身也展示"更像 AGI"的叙事效果，
这条路径能做到表面效果。
否决理由（正式裁定）：给一个不需要推理的格式转换任务引入 LLM，会破坏
Full Rebuild（同一 source 两次模型调用可能产生不同语义）、Drift
Detection（无法区分真实业务变化与模型输出变化）、Bitemporal Audit（
无法可靠回答"某历史时刻系统认为什么"）、Provenance（fact lineage 从
authoritative source 污染成 source+model+prompt+temperature+provider
version）、Outcome Learning（未来 State→Action→Outcome→State 的训练
标签会被污染）。唯一的效果是引入不确定性和幻觉风险，却没有对应真实收益。

**C.（本次 ACCEPTED，但作为 WM-004 独立派生层，不进入 FACT Adapter）
确定性 FACT + 生成式伴生摘要/解释。**
支持理由：既保留 R9 合规的确定性 FACT，又能在上层提供生成式解释能力，
且伴生对象本身就该是 `SYSTEM_INFERENCE`/`DerivedNarrative` 语义，不违反
任何红线。
否决理由（唯一的执行前提）：**不能做成"FACT Adapter 顺手调用一次模型"**
——那样表面遵守"FACT 还是确定性的"，实际又把模型延迟、成本、供应商故障
和非确定性耦合回 Truth Pipeline。正确结构是
`Canonical Source→Deterministic FACT Adapter→FACT committed→Outbox/
State Change Event→Generative Cognition→HYPOTHESIS/UNKNOWN/
SYSTEM_INFERENCE`，生成式部分在 commit 之后、异步、不阻塞 Truth
Pipeline。

## Consequences

### 正面
- WM-001~003 已完成的确定性实现无需任何代码变更，直接符合本次裁决。
- 给"Option C 怎么落地"提供了明确、可执行的边界（Atom 契约字段、
  异步 Outbox 触发、不得阻塞 Truth commit），不是留白的原则宣言。
- 为未来 `State→Action→Outcome→State` Transition Model 和因果学习保住
  一份不被模型自身推断污染的 Ground Truth——这是本次裁决最核心的长期
  技术理由，不只是合规问题。

### 负面 / 代价
- WM-004 需要新增 Generative Cognition Layer 的调用边界（Model Gateway
  接入、Structured Output 校验、Policy Validation），本 ADR 只定边界，
  具体实现留给 WM-004 任务本身。
- Option C 的 `DerivedNarrative`/`ExplanationProjection` 对象契约本 ADR
  只给出最低字段要求，完整设计留给 WM-004。

### 需要接受的风险
- 无——本裁决是收紧而非放宽，风险方向是"WM-004 若实现不当会绕开本 ADR
  的边界"，已在 Enforcement 段给出对应架构测试作为防线。

## Enforcement

**本次会话已执行**：

1. 新增 `tests/architecture/test_fact_adapter_determinism.py`：
   - **Test A**：静态检查 `backend/intelligence/context_engine/
     source_adapters/*.py` 不得 `import` `model_gateway` 或任何供应商
     SDK（`openai`/`anthropic`/`google.generativeai`/`deepseek` 等）。
   - **Test B**：复核（不新增，指向既有测试）AI+FACT 在 Python 构造期
     （`WorldStateAtom.__post_init__`）与数据库 CHECK 约束
     （`ck_ai_family_world_atoms_ai_cannot_assert_fact`）双层拒绝，
     已在 `test_world_state_kernel.py`/
     `test_postgres_world_state_repository.py` 覆盖，本测试文件做一次
     跨文件的存在性断言（防止未来这些测试被误删）。
   - **Test C**：确定性重建——同一个真实域对象（`FamilyRelationship`），
     用同一个 adapter 函数投影两次，除 `atom_id`（调用方决定，不属于
     语义）外全部字段必须相等，验证"same source → same semantic FACT"。
   - **Test D**：结构断言——当前全部 FACT adapter 函数签名的输入参数
     类型均为原始域实体（`Family`/`FamilyMember`/`FamilyRelationship`/
     `FamilyNeed`/`ValidatedConfirmationBinding`/`FamilyConfirmedOutcome`），
     没有任何函数接受 `WorldStateAtom`（尤其是 `HYPOTHESIS`/
     `SYSTEM_INFERENCE` kind）作为输入去产出 FACT——即"推断不能自我
     晋升为事实"这条不变量目前是结构性成立（没有对应函数存在），
     不是靠运行时判断维持的。

2. **WM-004（Conflict/Belief/Unknown Engine）范围声明**（不在本次实现，
   仅记录边界供下次任务遵守）：
   - Conflict Engine 第一阶段确定性检测候选冲突（same subject + same
     predicate + overlapping valid time + different value/perspective），
     模型只能解释/分类/提出澄清问题，不能删除观点、决定谁是真的、把
     Perspective 升级 FACT。
   - Belief Engine 输入 FACT/OBSERVATION/SELF_REPORT/OTHER_REPORT/
     PERSPECTIVE/PROFESSIONAL_OPINION/CONFLICT，产出 HYPOTHESIS/
     SYSTEM_INFERENCE，V1 用 support_level/contradiction_level/
     uncertainty 三档，不伪造精确概率。
   - Unknown Engine 的 `WorldUnknown` 必须经 ontology validation/
     deduplication/scope validation/subject validation。
   - 三者的确定性代码负责 scope/ontology/evidence/consent/provenance/
     status/dedup；模型负责 hypothesis generation/semantic explanation/
     evidence association proposal。

## References

- `governance/REPOSITORY_CONSTITUTION.md` R9
- `governance/ADR/ADR-0169-family-agi-species-change-and-strategic-constitution.md` §4/§5
- `governance/ADR/ADR-0171-platform-core-six-gate-admission-test.md`
- `docs/05_ai/AI_NATIVE_PRINCIPLES.md`
- `database/migrations/versions/0080_ai_family_world_atoms.py`
  （`ck_ai_family_world_atoms_ai_cannot_assert_fact`）
- `backend/intelligence/context_engine/source_adapters/`（本 ADR 约束对象）
- `tests/architecture/test_fact_adapter_determinism.py`（本次新增执行机制）
