# 当前产品语言 (Current Product Vision)

- **状态**: CURRENT — 依据 `governance/REPOSITORY_CONSTITUTION.md` R13，本文件是本主题唯一当前真相
- **生效**: 2026-08-29 (AIFAMILY-000)

---

## 0. 本文件的性质

**本文件的产品语言来自对 source repo (`D:\family-ai`, baseline commit `1ff168123d147f4d6a6eaaa677bc2f80986233d9`) 的实测审计，不是本次重新设计。**

以下每一条断言都能在源仓库中找到对应文件与代码/契约证据（`CLAUDE.md`、`50_开发_dev/specs/policies/perspective-fact.policy.yaml`、`50_开发_dev/legacy-system/architecture/FELS_LM1_SEMANTIC_MAPPING_V1.md` 等）。本文件不描述"AiFamily 应该做什么产品"，只登记"source repo 已经确立、且被 `governance/MIGRATION_MANIFEST.yaml` 判定为应当保留的产品语言"。Wave 0 (AIFAMILY-000) 不产出业务代码，本文件是纯文档产物。

---

## 1. Family 是长期业务根对象

Family 是贯穿整个业务域的长期根实体，其生命周期覆盖 parent → child → relationship → lifestage → consent 全链路。这一点由源仓库最大的业务服务文件 `50_开发_dev/apps/api/src/modules/family/family.service.ts`（2293 行，全仓库最大服务文件，真实 Postgres 持久化：`families`/`persons`/`consents` 等表，60+ 路由）及其配套 e2e 测试 `family-core-integration.e2e-spec.ts`（测试标识 M1-E2E-01：family→parent→child→relationship→lifestage→consent 全链路）共同确立。

对应 `governance/MIGRATION_MANIFEST.yaml` 中的 `family_core`（disposition: REIMPLEMENT，目标 `backend/domains/family`）。

## 2. Fact ≠ Perspective ≠ Recommendation ≠ Action ≠ Outcome

源仓库在 `CLAUDE.md` 与 `50_开发_dev/specs/policies/perspective-fact.policy.yaml` 中反复声明五层区分，且有真实 e2e 断言支撑（例如 `fact_boundary: 'PERSPECTIVE_NOT_FACT'`）。这不是空话式的架构口号，而是有可执行测试守卫的边界：

- **Fact**：家庭权威事实（如 relationship、consent、lifestage 的真实状态）。
- **Perspective**：AI 或人对 Fact 的推断/解读，永不自动升格为 Fact。
- **Recommendation**：基于 Perspective 给出的建议，同样不是 Fact。
- **Action**：唯一改变权威状态的写入动作（见第 4 节 Named Action）。
- **Outcome**：Action 执行后产生的结果记录，与"打卡"等历史概念不可等同（见下）。

`family.e2e-spec.ts` 中的 E2E-M2-101~105 测试链（onboarding→perspective→profile→report→journey）包含一条关键否定断言：**"确认 profile" 产生零 AI/Model 事件**——即确认动作本身不得触发模型调用去"证实"一个 Perspective，这是防止 Perspective 被悄悄漂白为 Fact 的具体机制。

对应 `governance/REPOSITORY_CONSTITUTION.md` R9（AI 输出不得自动成为事实）与 `MIGRATION_MANIFEST.yaml` 中的 `docs_business_domain_language`。

## 3. 不做 Family Total Score / 不做 Family Ranking

这是从 FELS（源仓库中的旧世界参考实现，`50_开发_dev/legacy-system/`）迁移审计中提炼出的否定语义，被 R9 列为一等约束：

| 旧世界对象 | 迁移规则 | 红线 |
|---|---|---|
| `legacy_profile.family_score` | **RETIRE** | 永不入 Family / 非 GrowthState (M036) |
| `legacy_profile.ranking` | **RETIRE** | 永不入 Family / 无家庭排行 (M035) |

**AiFamily 不计算、不存储、不暴露家庭总分与家庭排行。** 这一规则有双重证据交叉确认：FELS 反面教材 + `CLAUDE.md` 的正面声明一致。

## 4. Named Action 是核心状态的唯一写入口

对家庭权威状态（Fact）的任何变更，必须通过一个具名的、可审计的 Action 完成，而不是通过 Perspective/Recommendation 的隐式副作用，也不是通过"打卡"一类的历史行为记录直接写入。这一约束由两条证据共同支撑：

1. `family.e2e-spec.ts` 的否定断言（确认 profile 零 AI 事件）——防止推断链路绕过 Named Action 直接改状态；
2. FELS 语义映射表中 `legacy_checkin` 的迁移规则为 **TRANSFORM**：`打卡 ≠ GrowthActionCompletionFact ≠ Outcome (M014)`——历史"打卡"行为不能被直接当作 Action 完成事实或 Outcome，必须先转换为符合当前语义的 Named Action 记录。

对应 `governance/REPOSITORY_CONSTITUTION.md` R6（无审计不得改状态）：任何权威状态写入必须产生 `AuditEvent`。

## 5. 与本文件相关的待裁决事项

源仓库 `50_开发_dev` 下存在三份互不引用、各自自称"当前基线"的文档（`CURRENT_SPRINT.md`、`governance/PROGRAM_STATUS_PLATFORM_V1.md`、`architecture/FAMILY_PLATFORM_V3_BLUEPRINT.md`），且源仓库已有一份独立推进中的 `architecture/FAMILY_AI_PYTHON_ONLY_MIGRATION_PLAN_V1.md`（2026-08-28）。本文件登记的产品语言（Family 根对象、四层区分、否定禁令、Named Action）在三份文档与该迁移计划之间未发现冲突，但两套迁移工作之间的关系本身尚待人工裁决，详见 `governance/MIGRATION_MANIFEST.yaml` 的 `docs_current_baseline_CONTRADICTION` 条目与 `docs/00_foundation/CURRENT_PROGRAM_PLAN.md` 第 5 节。
