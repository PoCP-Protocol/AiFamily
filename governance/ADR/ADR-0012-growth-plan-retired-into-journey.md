# ADR-0012: `growth_plan` 降级 RETIRE，语义并入 `journey` 域

- **Status**: Accepted
- **Date**: 2026-08-29
- **Deciders**: chief-architect（project-owner 可 override）
- **Supersedes**: null
- **Superseded By**: null

## Context

`governance/DOMAIN_REGISTRY.yaml:229-237` 的 `growth_plan_python_stub.r2_overlap_risk` 自己声明
「**R2 风险已知且未解决**」，并规定裁决时点为 `MIGRATION_PLAN_V2.md` Batch 4（JOURNEY 闭环）开工前，
必须以 ADR 在三个选项中择一。`governance/ADR/README.md:44` 亦把本项列为「必须写 ADR」的典型触发。
`docs/00_system/TARGET_ARCHITECTURE.md` §6 把它列为等架构师裁决的第 4 项。本 ADR 是该裁决。

裁决所依据的实测证据（不是语义相似性推断）：

1. **`backend/domains/growth_plan/` 全域只有一个文件 `domain/errors.py`，38 行，5 个异常类，零实体、
   零行为、零测试。** `DOMAIN_REGISTRY.yaml:226` 的登记原文即「单文件 37 行，仅错误类型枚举。无实体，
   无行为，零测试」。`status: MIGRATED_STRUCTURE_ONLY`，按同文件 L26-27 的口径等价于
   「能力不存在，但代码占了位置」。

2. **决定性证据：这个文件里装的错误码字面量本身就是 journey 的。** `errors.py:1-6` 的模块 docstring
   自述 "mirroring the NestJS exception types used in `journey-plan.service.ts`"，
   而 `errors.py:33-37` 保留的错误码字符串是 `journey_plan_not_draft`、`journey_plan_not_active`、
   `journey_phase_review_not_due`；`errors.py:26-30` 是 `journey_plan_not_found`、
   `active_growth_priority_not_found`、`active_growth_onboarding_not_found`。
   **五个类名前缀是 `GrowthPlan*`，但它们承载的错误码有三个直接以 `journey_` 开头。**
   这不是两个能力的边界模糊，是**一个能力被起了两个名字**——源仓库的 Python 侧目录名与它自己
   镜像的 TS 服务名不一致，AiFamily 原样继承了这个命名分裂。

3. `docs/00_system/CURRENT_DOMAIN_MAP.md` §3.4 已把 `GrowthPlan` 列为 `journey` 域的 Owns 之一。
   若 `journey` 建成而本 stub 保留，即构成「一个能力两个实现位置」的违宪状态（R2）。

4. 迁入依据是 `MIGRATION_MANIFEST.yaml → growth_plan_python_stub.project_owner_override`
   （2026-08-29「先把所有 Python 代码都迁移过来」），override 原文同时要求「迁移后仍是错误类型
   stub，**不假装已有实体模型**」。本 ADR 不推翻该 override 的理由——代码确实该被迁进来看一眼；
   看清之后判定它不构成一个独立能力，是发现新事实后的独立裁决，与 `product_strategy` /
   `market_intelligence` 在 `DOMAIN_REGISTRY.yaml:212-218` 走的是同一条路径。

## Decision

采纳 `r2_overlap_risk` 的选项 **(a)**：**`growth_plan` 并入 `journey` 后删除其 capability 条目。**

具体执行（`journey` 域开工的同一个 PR 内完成，不单独开 PR 制造一个空的 journey 目录）：

1. `backend/domains/growth_plan/domain/errors.py` 的 5 个异常类迁入
   `backend/domains/journey/domain/errors.py`，**类名前缀由 `GrowthPlan*` 改为 `Journey*`**——
   保留 `code` 字符串字面量不变（它们是 API 可观测行为，改了会破坏与源仓库的行为等价性，
   见 `errors.py:4-6` 的原意），只改 Python 类名以消除命名分裂。
2. 删除 `backend/domains/growth_plan/` 目录。
   **⚠ 删除前必须取得 project-owner 的二次确认，不得由执行者自行删除。**
   依据有二：(a) `MIGRATION_PLAN_V2.md` §1 规定 `DELETE` 处置需二次确认；
   (b) **这类动作刚刚发生过一次并被回滚**——`TASK_BACKLOG.md` §0.1 偏离 #3 记录
   「已提交的 `market_intelligence`/`product_strategy` 被删除，无二次确认记录 →
   违反 project-owner『先把所有 Python 代码都迁移过来』指示 → 已从 git 恢复」。
   本 ADR 的裁决理由（38 行错误码 stub 不构成独立能力）与那两个域的情形同类，
   因此**同一个程序约束适用**：ADR 提供裁决依据，不替代二次确认。
   若二次确认未取得，执行 §3 的 registry 降级但**保留目录**，
   并在 registry 的 `note` 里记明「目录待二次确认后删除」——
   一个被降级为 `RETIRED_CANONICAL_CONFLICT` 但仍在磁盘上的目录，
   优于一次未经确认的删除。
3. `DOMAIN_REGISTRY.yaml` 的 `growth_plan_python_stub` 条目 **status 改 `RETIRED_CANONICAL_CONFLICT`**
   （沿用 `product_strategy` / `market_intelligence` 已有的处置词，不新造词表项），
   保留条目行本身作为历史记录，`note` 追加指向本 ADR。
4. `MIGRATION_MANIFEST.yaml` 对应条目同步，`disposition` 保持 `MIGRATE`（它确实被迁入过），
   `status` 改 `RETIRED_CANONICAL_CONFLICT`。
5. `governance/CAPABILITY_REGISTRY.yaml` 若含相关行同步；无则不新增。

**在 `journey` 域实际开工前，`growth_plan` 目录保持原样不动，且不得向其添加任何实体模型**
（这是 `r2_overlap_risk:237` 的原有约束，本 ADR 继续沿用）。本 ADR 是决定，不是立即执行的指令——
它解除的是 Batch 4 的裁决阻塞。

## Alternatives Considered

### B. `growth_plan` 降级为 `journey` 的内部子模块，不再是独立 capability
**支持理由**：不删任何文件，风险最低。若将来「成长计划」确实长出独立于 journey 节奏的语义
（例如计划可以脱离 21/90 天周期存在），已有目录可以直接升回独立域，改动成本低。
保留目录也保留了「这段代码曾经存在过」的物理痕迹。

**否决理由**：子模块与独立域在磁盘上长得一模一样（都是 `backend/domains/<name>/`），
区别只存在于 registry 的一行字。**R2 要防的恰恰是「看起来像两个域」这件事本身**——
下一个开发者看到 `backend/domains/growth_plan/` 与 `backend/domains/journey/` 并列，
不会先去读 registry 才决定往哪个里写代码。宪章 R2 的伤疤原文点名禁止的
`family` / `family_core` / `family_domain_v2` 并存，就是这个形态。
保留一个 38 行的空壳目录换取的「未来升回」灵活性，代价是持续的 R2 歧义。

### C. 明确 `growth_plan` 与 `journey` 是两个不同能力并写出边界
**支持理由**：「计划」（做什么）与「旅程」（按什么节奏做）在概念上确实可分。
若边界写清楚，两个域各自内聚，也符合 DDD 的一般做法。产品侧将来若要支持
「不绑定 21/90 天节奏的自由成长计划」，这个切分是前置条件。

**否决理由**：**证据直接反驳这个切分。** 若两者是不同能力，`growth_plan` 里不该出现
`journey_plan_not_draft` / `journey_phase_review_not_due` 这类错误码——而 `errors.py:33-37`
里就是它们。这个文件不是「计划域的错误」，是「旅程计划服务的错误」被放在了一个叫计划的目录里。
在没有任何实体、任何行为的情况下写一份边界文档，写出来的是**对不存在能力的想象**，
按 `docs/05_ai/AI_NATIVE_PRINCIPLES.md` 的口径这属于「设计过 ≠ 已实现」的典型误读源。
需要这个切分时再出新 ADR 推翻本决定，比现在预留一个空域更诚实。

### D. 推迟裁决到 `journey` 真正开工时
**支持理由**：那时对 journey 的真实需求了解更多，裁决质量更高。且现在裁决不产生任何代码改动，
看起来收益为零。

**否决理由**：推迟的成本不是零。`r2_overlap_risk:237` 已经因为这个未决状态而加了一条禁令
（「裁决前不得向本 stub 添加实体模型」）——**一个未决的架构问题正在以禁令形式限制施工**。
且 `TASK_BACKLOG.md` 的 T-05（Assessment 四层）与 Batch 4 都排在它后面。
架构师不裁决就是在阻塞执行者，这本身是本 ADR 存在的理由。

## Consequences

### 正面
- 解除 Batch 4 的裁决阻塞，同时解除 `r2_overlap_risk` 附加的施工禁令。
- 消除命名分裂：`journey_*` 错误码今后住在 `journey` 域里。
- 域数量减一。`CURRENT_DOMAIN_MAP.md` 的 19 个登记域里少一个空壳，
  「已登记 ≠ 能力存在」的解释负担减轻一分。

### 负面 / 代价
- 若将来「成长计划」确实需要独立于 journey，要走新 ADR 推翻本决定并重建域。
- 删目录会让 `MIGRATION_MANIFEST` 里一条 `disposition: MIGRATE` 的条目最终指向一个
  不存在的 target。**必须确认 `tests/architecture/test_migration_manifest.py` 的
  ancestor-prefix 匹配逻辑不会因 target 目录消失而失败**——该测试是从 `backend/` 侧
  遍历「含文件的目录」反查 manifest 覆盖，方向是 code→manifest，所以目录消失应当安全，
  但执行 PR 必须实跑验证，不得假设。

### 需要接受的风险
- 本 ADR 的证据强度依赖对 38 行代码的解读。如果源仓库的 `journey-plan.service.ts` 实际上
  管的是两件事（我未读该文件，它在只读的 `D:\family-ai` 内），则「一个能力两个名字」的
  判断可能过强。缓释：执行 PR 的领取者应先读源文件确认；若发现确为两个能力，
  **不要静默按本 ADR 执行**，回来推翻它。

## Enforcement

**当前为决定，尚无机械执行——如实记录。**

- 本 ADR 的执行状态由 `DOMAIN_REGISTRY.yaml` 的 `growth_plan_python_stub.status` 字段体现。
  `tests/architecture/test_domain_registry.py` 会校验 status 属合法词表，
  但**不会**校验「status 是否与磁盘实况一致」——所以改了 registry 而没删目录，测试仍绿。
- 补齐路径：`test_domain_registry.py` 增加一条断言——status 为
  `RETIRED_CANONICAL_CONFLICT` 的条目，其 `canonical_path` **必须不存在于磁盘**。
  这一条可机械检验且成本极低，应在执行 PR 内同批落地。目前不存在此断言。
- R2 本身由 `test_domain_registry.py::test_no_capability_has_multiple_canonical_paths` 执行，
  但它检查的是「同一 capability 是否有多个 path」，**不检查「两个 capability 的语义是否重叠」**
  ——语义重叠原理上不可机械检验，只能靠本 ADR 这类裁决。这是 R2 执行的固有边界。

## References

- `governance/DOMAIN_REGISTRY.yaml:221-237`（`growth_plan_python_stub` 条目与 `r2_overlap_risk` 三选项）
- `governance/DOMAIN_REGISTRY.yaml:212-218`（`market_intelligence` 的同类 RETIRE 降级先例）
- `backend/domains/growth_plan/domain/errors.py:1-6, 26-37`（journey 错误码证据）
- `docs/00_system/CURRENT_DOMAIN_MAP.md` §3.4（`GrowthPlan` 归 `journey` 域 Owns）
- `docs/00_system/TARGET_ARCHITECTURE.md` §6 第 4 项
- `governance/MIGRATION_MANIFEST.yaml → growth_plan_python_stub.project_owner_override`
- `governance/REPOSITORY_CONSTITUTION.md` R2、R4
- `governance/ADR/README.md:44`（本项为「必须写 ADR」的列名触发）
