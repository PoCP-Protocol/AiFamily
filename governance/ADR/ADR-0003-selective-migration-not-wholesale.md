# ADR-0003: 精选式迁移（disposition 分类法）取代全量搬家

- **Status**: Accepted
- **Date**: 2026-08-29
- **Deciders**: project-owner / chief-architect
- **Supersedes**: null
- **Superseded By**: null

## Context

源仓库自己已经有一份迁移计划：`50_开发_dev/architecture/FAMILY_AI_PYTHON_ONLY_MIGRATION_PLAN_V1.md`（2026-08-28），且 `CURRENT_SPRINT.md` 记录了 7 条 project-owner Override 正按它推进 Batch 1-6。**V1 的默认前提是"全部代码分批迁移"** —— 批次序号回答"什么时候搬"，但没有任何字段回答"这段代码该不该搬"。

AIFAMILY-000 对源仓库 2060 个受控文件做资产审计后，发现"全部搬"这个前提本身不成立，因为迁移范围里混着三类不该迁的东西：

**1. 合成数据服务，但有真实消费者（最危险的一类）**
`50_开发_dev/apps/api/src/modules/family/dev-platform-surfaces.service.ts:26-33` 与 `dev-core-growth.service.ts:43-60` 在自己的返回体里写明 `data_source: 'SYNTHETIC_DEV_ONLY'`、`model_gateway: 'NOOP_NOT_INVOKED'`，内容是 24 张硬编码 UI 卡片和一本中文文案字典，零 DB 读写。**但它们通过 `family.controller.ts:280,295,313,326` 挂在生产路由 `/:familyId/dev/*` 上，被 `apps/mobile` 的 9+ 个真实屏幕（UI-10/11/12/22/23/25/27/28/29）消费。**
这打破了两个方向的天真判断：既不能当业务代码迁（是假数据），也不能当死代码删（前端真的在用）。全量迁移会把假数据洗成正式能力；无脑删除会让 34 个屏幕里 9 个白屏。

**2. 真死代码**
`apps/api/src/modules/family/../waf/waf-domain.service.ts`：纯内存 `Map`，零 DB，零路由引用，唯一消费者是它自己的 spec 文件。全量迁移会把它翻译成 Python 并从此维护。

**3. 空壳**
`50_开发_dev/apps/consumer-web` 与 `apps/ops-web`：目录内**只有 `node_modules`**，无 `package.json`，无源码。V1 的批次表把它们算作待迁移的前端应用。
`apps/fes-web`：11 行单函数，零网络调用，零 UI 框架。
`apps/web/src/case-access-client.spec.js`：与同目录 `.spec.ts` **逐字节相同**的重复文件，被 vitest 配置排除。

**4. "看起来是纯 DTO 实际含业务逻辑"的反向错误**
V1 把 `packages/contracts` 整体归为纯 DTO 层。实测 `src/family-growth-os.ts` 与 `src/ui01-ui09-first-slice.ts` 含真实投影函数（`projectTodayTask` 等）在计算 UI 状态机——按 DTO 直搬会把业务逻辑当 schema 复制，绕过重写审查。

也就是说：**批次序号无法表达"这段代码的价值判断"，而价值判断恰恰是迁移的主要工作量。**

## Decision

引入 **disposition 分类法**，取代"批次序号 + 默认全迁"。每个能力在进入任何 Batch 施工前，必须先有一个明确的 disposition 记录。

| disposition | 含义 | 处理方式 |
|---|---|---|
| `MIGRATE` | 有真实业务价值、有测试或可补测试、值得原样迁移语义 | 按四层结构重写，测试先行 |
| `REIMPLEMENT` | 业务规则值得保留，代码形态不值得 | 规则重译，源码作参考实现 |
| `CONTRACT_ONLY` | 只有契约/规则值得保留，代码本身不迁 | 提取为 docs / schema，原代码归档 |
| `ARCHIVE` | 有历史/参考价值但不进入生产目标态 | 保留在源仓库，不删除，不迁入 |
| `DELETE` | 已确认零价值（空壳 / 死代码 / 重复文件） | 标记待清理，需二次确认后删除 |
| `REVIEW_REQUIRED` | 证据不足以判定，需人类或补充调研裁决 | **阻塞，不得假设为 MIGRATE** |
| `TEST_ORACLE` | 不是生产代码，是验收口径来源 | 断言语义迁移，不作为覆盖率证明 |
| `KEEP_NON_PYTHON` | 与后端语言无关，留在原技术栈 | 不进入 Python 迁移范围 |

**关键规则：默认状态是 `REVIEW_REQUIRED`，不是 `MIGRATE`。** 没有证据支持迁移的代码，默认不迁。这与 R3（无 Manifest 不得入仓，默认 `NOT_APPROVED`）是同一条纪律在两个层面的表达。

分类结果登记在 `governance/MIGRATION_MANIFEST.yaml`，每条须带 `evidence` 字段（实测证据，不是判断），必要时带 `correction_to_plan`（明确记录它推翻了 V1 计划的哪个假设）与 `blocking_action`。架构测试 `tests/architecture/test_migration_manifest.py` 强制：`backend/` 下任何含文件的目录都必须能追溯到某条 manifest 条目的 `target`。

**禁止整体复制**：不得 `cp -R family-ai AiFamily`，不得"先全部迁入再删除"（R3）。

### 后续变更：project-owner override（必须记录）

2026-08-29，project-owner 指示 **"保险起见，先把所有 Python 代码都迁移过来"**，这在结果上部分回退了本 ADR 的严格性。受影响条目及其 override 记录：

| capability | 原 disposition | override 后 | override 附带的约束 |
|---|---|---|---|
| `membership` | `REVIEW_REQUIRED` / BLOCKED | `MIGRATE` | "迁移执行时必须原样带着这个已知缺口，**不得在迁移过程中假装测试已存在**" |
| `market_intelligence` | `ARCHIVE` | `MIGRATE` | "迁移后仍是空壳状态，**不假装已完整**" |
| `growth_plan_python_stub` | `ARCHIVE` | `MIGRATE` | "迁移后仍是错误类型 stub，**不假装已有实体模型**" |
| `design_copilot` | `CONTRACT_ONLY` | `MIGRATE` | "其能力状态不变：每个方法仍是 NotImplementedError，零调用方、零测试。**迁移不得被解读为该能力已存在**" |
| `frontend_mobile` | `KEEP_NON_PYTHON` | `MIGRATE` | "34 个 UI 已经做得很好，需要把整个 Mobile 迁移过来" |

**这个 override 是决定的变更，不是本 ADR 的失效。** 它改变的是"代码是否物理位于仓库内"，**没有**改变"代码是否构成一个能力"——后者仍由 `DOMAIN_REGISTRY.yaml` 的 status 与 R4（无测试不得称能力）裁决。每条 override 都自带一句"不得假装"，正是为了守住这个区分。本 ADR 的核心主张（价值判断必须显式记录、默认不是 MIGRATE）因此完整保留：override 恰恰是被显式记录下来的，而不是悄悄发生的。

## Alternatives Considered

### A. 沿用 V1 的"全量分批迁移"
**支持理由**：简单、进度可度量（第 N 批完成 = X% 迁移完成）、不需要为每个能力做判断，决策成本低。而且"先都搬过来再收拾"直观上不丢东西。

**否决理由**：会把上述四类问题一并继承。最具体的反例是 `dev-*.service.ts`——全量迁移会把一个自述 `SYNTHETIC_DEV_ONLY` 的服务重写成 Python 生产代码，从此它在新仓库里没有任何标记表明自己是假的（源仓库至少还在返回体里写着 `data_source`）。**全量迁移的真实成本不是搬运工作量，是把源仓库的错误判断洗白成新仓库的既有事实。**

### B. 只迁"有测试的代码"这一条硬规则
**支持理由**：客观、无需人工判断、直接对齐 R4。

**否决理由**：判据过窄，两个方向都会错。误杀：`membership` 2627 行含真实不变量（`assert_tier_transition_legal`）却零测试，直接扔掉会丢真实业务规则。误留：`waf-domain.service.ts` 有 spec 文件——**它唯一的消费者就是自己的 spec**，按此规则它会被判定为"有测试"从而迁入，而它是死代码。测试的存在与业务价值不是同一件事。

### C. 白纸重写，完全不参考源仓库
**支持理由**：最彻底，零继承债务，不需要 manifest 与 disposition 这整套机制。

**否决理由**：丢弃的东西比债务更贵。源仓库的 e2e 断言里含**无法从需求文档重新推导出的否定语义**，例如 `family-core-integration.e2e-spec.ts` 的 M1-E2E-07/08："不得从 relationship 推断 consent，不得从 birthdate 推断 lifestage"。这类"曾经踩过所以写成断言"的知识，白纸重写会原地重犯。因此保留 `TEST_ORACLE` 这个 disposition：代码不迁，验收口径迁。

## Consequences

### 正面
- 每个能力的去留有 evidence 支撑，可被复核、可被推翻（推翻需新 override 或新 ADR，留痕）。
- `REVIEW_REQUIRED` 让"我们还不知道"成为一个合法且可见的状态，而不是被默认值悄悄决定为 MIGRATE。
- `correction_to_plan` 字段使"本次审计推翻了 V1 计划的哪个假设"可检索——V1 与 V2 的差异不需要靠对读两份长文档还原。
- `TEST_ORACLE` 把"代码不要但知识要"这件事变成一等公民。

### 负面 / 代价
- 前置审计成本高：2060 个文件的分类工作产出了 `docs/11_delivery/migration/01`-`04` 四份分析文档，这些工作不产出任何可运行代码。
- 分类会过时。disposition 基于 2026-08-29 的磁盘快照，而源仓库有并发会话在改（manifest 的 `audit_caveat` 记录了审计时有 64 个未提交文件属于另一会话）。
- 每次开工前查 manifest 是额外一步流程摩擦，容易被"我知道这个该迁"的自信绕过。

### 需要接受的风险
- **`REVIEW_REQUIRED` 可能长期不被裁决而变成事实上的阻塞。** manifest 的 `review_required_index` 目前有 9 项，其中 `docs_current_baseline_CONTRADICTION`（本计划与源仓库既有 Python 迁移计划的关系）被标为最高优先级且**至今未裁决**。在它被裁决前，AiFamily 不得假设自己是"唯一正在进行的 Python 迁移工作"——这个不确定性目前真实存在。
- override 机制本身可被滥用：如果每条严格判定都被 override 推翻，disposition 分类法会退化为形式。缓释靠 override 必须自带"不得假装"约束并写进 manifest，且 `DOMAIN_REGISTRY.yaml` 的 status 独立于 disposition 判定成熟度（例如 `membership` 的 disposition 是 `MIGRATE` 但 status 是 `MIGRATED_UNTESTED`）。

## Enforcement

**部分由架构测试执行。**

- `tests/architecture/test_migration_manifest.py` — R3 的执行者：`backend/` 下每个含文件的目录必须被某条 manifest 条目的 `target` 精确覆盖或作为其后代覆盖。这条真的会拦住"直接 cp 一个目录进 backend/"。
- `tests/architecture/test_domain_registry.py` — R2 的执行者：capability 不得重复登记、不得一个 capability 两个 canonical_path。
- **未被机械执行的部分**：没有测试检查 disposition 值是否在合法枚举内、`MIGRATE` 条目是否带 `evidence`、`REVIEW_REQUIRED` 是否有对应的 blocking_action。这些目前只靠人工评审。补齐路径：给 `governance/MIGRATION_MANIFEST.yaml` 写一份 JSON Schema 放进 `governance/schemas/`，并在架构测试中校验。
- "默认 `REVIEW_REQUIRED`" 这条**无法机械执行**——它是关于"未登记的东西"的规则，而未登记的东西正是测试看不见的东西。它的真实护栏是 R3 那条 target 覆盖测试的否定形式：没登记就进不来。

## References

- `governance/REPOSITORY_CONSTITUTION.md` R3、R4、R5
- `governance/MIGRATION_MANIFEST.yaml`（全文，特别是 5 处 `project_owner_override` 与 `review_required_index`）
- `docs/11_delivery/migration/MIGRATION_PLAN_V2.md` §3–§6（disposition 分类法原文与初始分类表）
- `docs/11_delivery/migration/02_DEAD_LEGACY_DUPLICATE_AUDIT.md`
- 源仓库 `50_开发_dev/architecture/FAMILY_AI_PYTHON_ONLY_MIGRATION_PLAN_V1.md`（被本决定修正的对象）
- ADR-0001（后端单轨 Python，本决定的前提）
