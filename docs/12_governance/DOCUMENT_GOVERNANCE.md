---
id: GOV-DOC-001
title: AiFamily 文档治理规范
type: governance
status: current
version: 1.0
owner: chief-architect
created: 2026-08-29
updated: 2026-08-29
canonical: true
supersedes: null
superseded_by: null
---

# AiFamily 文档治理规范 (Document Governance)

本文件规定 AiFamily 仓库内**文档如何分类、命名、标记、归档、与代码同步**。

它是 `docs/00_system/SYSTEM_MANIFEST.md` 的执行细则：Manifest 声明"哪些文档是真相"，本文件规定"怎么写才能成为真相、怎么退役"。两者冲突以 Manifest 为准。
导航（"我要的东西在哪"）见 `docs/00_system/DOCUMENTATION_MAP.md`。

本规范存在的原因是一个真实事故：源仓库 `family-ai` 同时存在**三份互相矛盾、各自声称"当前基线"**的文档（`CURRENT_SPRINT.md` / `governance/PROGRAM_STATUS_PLATFORM_V1.md` / `architecture/FAMILY_PLATFORM_V3_BLUEPRINT.md`），任何人和任何 AI Agent 都无法判断该信哪一份。宪章 R13 与本文件是对这个事故的护栏。

---

## 1. 五类信息必须区分（最关键的一条）

```text
Current Truth  ≠  Decision  ≠  Specification  ≠  Evidence  ≠  History
```

**Current Truth Never Mixes With History.**

任何一份资料必须能回答"我属于哪一类"。**不能确定的，标 `draft`，绝不默认 `current`。**

| 类别 | 是什么 | 位置 | 标记规则 |
|---|---|---|---|
| **Current Truth** | 系统**现在**是什么（含未完成项） | `docs/00_system/`、各层 canonical 文档 | `status: current`、`canonical: true` |
| **Decision** | 为什么这样选、推翻了什么 | `governance/ADR/` | ADR 自带 `Status: Proposed/Accepted/Superseded` |
| **Specification** | 应该被建成什么样（尚未全部成真） | `docs/03_product/`、`docs/04_domains/`、`docs/06_platform/` | `status: current` 或 `draft`，且必须与 Current Truth 显式区分 |
| **Evidence** | 我们调研到/审计到什么（不是决定） | `docs/13_research/`、`docs/14_reference/` | 正文前 2000 字符内必须含 `RESEARCH_ONLY` 或 `NOT_CANONICAL` 或 `STATUS: RESEARCH` |
| **History** | 曾经是真相，现已被取代 | `docs/99_archive/` | 必须含 `ARCHIVED` / `SUPERSEDED` / `DEPRECATED` / `DO_NOT_USE` 之一 |

**机械化强制**：`tests/architecture/test_docs_truth_boundary.py` 检查
(a) `docs/00_system/` 至少有一份非空 `CURRENT_*.md`；
(b) `SYSTEM_MANIFEST.md` 存在且非空；
(c) `docs/99_archive/` 下每个 `.md`/`.txt` 前 2000 字符含 superseded 标记；
(d) `docs/13_research/` 下每个 `.md` 前 2000 字符含 non-canonical 标记。
不满足即 CI 失败。**未被这个测试覆盖的部分（如 Specification 与 Current Truth 的混写）目前只靠人工评审。**

### 1.1 Specification 与 Current Truth 的混写是最常见的错误

一份文档写"系统有 Family Growth Graph"，读者无法分辨这是"已经有"还是"设计成这样"。规则：
- Current Truth 文档必须有一节"现状核对表"，逐项标 **真实存在 / 目标态骨架 / 不存在**，并给出代码路径证据。
- Specification 文档必须在首屏声明"本文件描述目标态，不描述现状；现状见 `docs/00_system/CURRENT_SYSTEM_BASELINE.md`"。

---

## 2. 16 层目录职责（放什么 / 不放什么）

| 目录 | 层 | 放什么 | **不放什么** |
|---|---|---|---|
| `docs/00_system/` | L0 | `SYSTEM_MANIFEST.md` + `CURRENT_*.md` 系统真相 + `DOCUMENTATION_MAP.md` | 设计方案、Sprint 记录、研究结论、任何历史内容 |
| `docs/01_strategy/` | L1 | 商业战略、价值定位、三区方法论；原始输入材料放 `source_materials/` | 产品功能设计、技术方案 |
| `docs/02_business/` | L1 | 业务架构、业务能力地图（Business Capability）、业务场景与流程 | 产品 UI、Domain 技术边界 |
| `docs/03_product/` | L1 | 产品愿景、产品能力（Product Capability）、页面清单 `PAGE-NNN-*.md` | 后端 Domain 模型、实现细节 |
| `docs/04_domains/` | L2 | 每个 Domain 一份边界文档：聚合、不变量、Command、Event、与其它域的 Port | 跨域全景（属 00_system）、UI 描述 |
| `docs/05_ai/` | L2 | AI 原生原则、AI 架构、Agent 定义；具体用例放 `AI_USE_CASES/AIUC-NNN-*.md` | 供应商比价（属 13_research）、模型调优实验记录 |
| `docs/06_platform/` | L2 | 平台内核规格：identity / authorization / consent / audit / idempotency / persistence | 业务规则、Domain 语义 |
| `docs/07_data/` | L2 | 数据架构、schema 归属、留存期限与目的绑定、向量化与级联删除设计 | SQL 迁移文件本体（在 `database/migrations/`） |
| `docs/08_experience/` | L3 | 交互与体验规范、设计 token、可访问性 | 组件代码、截图基线（在 `frontend/`） |
| `docs/09_operations/` | L3 | 运维、可观测性、SLO、事故响应、成本控制 | 开发规范（属 10_engineering） |
| `docs/10_engineering/` | L3 | 工程架构、分层约定、测试策略、代码规范、CI 设计 | 治理规则（属 governance/ 与 12_governance） |
| `docs/11_delivery/` | L3 | 交付计划 `CURRENT_PROGRAM_PLAN.md`；`migration/` 迁移分析；`sprints/YYYY/` `releases/` `roadmap/` | 系统现状（属 00_system） |
| `docs/12_governance/` | L4 | 人类可读治理规范：本文件、合规硬约束、评审流程 | **机器可执行治理**（`.yaml` registry、宪章 → 全部在 `governance/`） |
| `docs/13_research/` | L4 | 调研与证据，分 `market/` `technology/` `compliance/`；**必标 `RESEARCH_ONLY`** | 任何被当作决策的内容——晋升须先出 ADR |
| `docs/14_reference/` | L4 | 外部/旧系统参考，`legacy_audits/` 放对 `family-ai` 的审计矩阵 | AiFamily 自身的当前真相 |
| `docs/99_archive/` | L4 | 已退役文档，按 `YYYY/<类别>/` 组织；**必标 `ARCHIVED` + `SUPERSEDED_BY`** | 仍在生效的任何文档 |

**为什么治理拆成两处**：`governance/` 放要被代码和 CI 读取的部分（宪章、registry YAML、ADR），`docs/12_governance/` 放要被人读的规范。前者是护栏，后者是解释。**写成文档的策略不是策略（R14）** —— 任何可机械检验的规则必须落到 `governance/` + `tests/architecture/`。

---

## 3. Front Matter 规范

所有 `docs/**/*.md` 顶部使用 YAML front matter：

```yaml
---
id: <区域前缀>-<主题>-<序号>      # 如 SYS-MANIFEST-001 / DOM-FAMILY-001 / AIUC-001
title: <人类可读标题>
type: system | strategy | business | product | domain | ai | platform | data |
      experience | operations | engineering | delivery | governance | research |
      reference | adr | archive
status: draft | review | current | deprecated | archived   # 仅此五值
version: <主.次>
owner: <角色，如 chief-architect / product-owner>
created: YYYY-MM-DD
updated: YYYY-MM-DD
canonical: true | false
supersedes: <被本文件取代的文档 id 或 null>
superseded_by: <取代本文件的文档 id 或 null>
---
```

规则：
- **`status` 只允许 `draft|review|current|deprecated|archived` 五个值。**
  **禁止** `final` / `final-new` / `最新版` / `V2最终版` / `FROZEN` / `ACTIVE` 等自造状态——源仓库正是靠这类词把三份文档都变成了"最终版"。
- `canonical: true` 只能出现在 `status: current` 的文档上，且同一主题只能有一份。
- `status: archived` 必须有 `superseded_by`（或明确写 `superseded_by: null # 该主题整体废弃`）。
- `updated` 必须随实质修改更新；只改错别字不必。
- `type` 与所在目录必须一致（`docs/04_domains/` 下不得出现 `type: research`）。

**当前实况**：`docs/00_system/CURRENT_SYSTEM_BASELINE.md`、`CURRENT_AI_MAP.md`、`CURRENT_TECHNOLOGY_BASELINE.md` 等多份既有文档使用的是"`- **状态**: CURRENT`"这种行内标记，**尚未迁到 front matter**。这是已知债务，见第 9 节待办。

---

## 4. 命名规范

| 类型 | 规则 | 示例 |
|---|---|---|
| 正式文档 | `UPPER_SNAKE_CASE.md` | `AI_NATIVE_PRINCIPLES.md`、`DATA_ARCHITECTURE.md` |
| 当前真相 | `CURRENT_<主题>.md` | `CURRENT_SYSTEM_BASELINE.md` |
| 实例 / 用例 / 编号件 | `<前缀>-<编号>-<kebab-case>.md` | `AIUC-001-growth-insight.md`、`ADR-0001-python-only-backend.md`、`PAGE-001-family-home.md` |
| 目录 | `NN_lower_snake`（docs 层）或 `lower_snake`（子目录） | `05_ai/`、`legacy_audits/` |
| Sprint 归档 | `docs/11_delivery/sprints/YYYY/SPRINT-<编号>-<slug>.md` | `sprints/2026/SPRINT-001-platform-kernel.md` |

**禁止**：
- **中文文件名作为 canonical file。** 文件名必须 ASCII；**内容可以且应当用中文**。原因不只是整洁：中文路径在本环境的复合 shell 命令中会触发安全拦截，且源仓库的 `50_开发_dev` 路径已经证明它会破坏工具链。既有的 `docs/01_strategy/source_materials/*.txt` 与 `docs/99_archive/2026/strategy/*.txt` 是**原始输入材料**，按原名保留属例外，不得新增此类 canonical 文档。
- **日期作为 CURRENT 文档文件名**：不得出现 `CURRENT_STATUS_2026-08-29.md`。日期属 front matter 的 `updated` 字段，或归档时的目录层级。
- **版本号作为文件名**：不得出现 `BLUEPRINT_V3.md` / `PLAN_V2.md`。版本属 front matter 的 `version`；旧版本进 `docs/99_archive/`。

---

## 5. Current 文件唯一性规则

**`CURRENT_*.md` 永远只有一份。** 同一主题不得存在两份都自称基线的文档（R13）。

- **禁止在 Current 文件下方堆积历史。** 不要写"## 历史变更"、"## 2026-08 之前的状态"这类节。Current 文件只描述当下。
- Sprint / Wave 结束时：把该 Sprint 的过程记录**移入** `docs/11_delivery/sprints/YYYY/`，Current 文件**改写**为新的当下状态，不是追加。
- 若一份 Current 文档被完整取代：旧文件移入 `docs/99_archive/YYYY/<类别>/`，加归档标记 + `superseded_by`；新文件继承同一文件名，`supersedes` 指向被归档者的 id。
- 若发现两份文档都自称某主题的当前真相：**这是事故，不是待办**。立即在 `docs/00_system/SYSTEM_MANIFEST.md` §5 裁定哪一份是 canonical，另一份当场归档。

---

## 6. Traceability 链

每一行业务代码都必须能沿这条链回溯到战略意图：

```text
Strategy            docs/01_strategy/
  → Business Capability   docs/02_business/BUSINESS_CAPABILITY_MAP.md
    → Product Capability    docs/03_product/
      → Domain                docs/04_domains/ + governance/DOMAIN_REGISTRY.yaml
        → Command / Event       docs/04_domains/<domain> 的 Command/Event 清单
          → API                   contracts/openapi/
            → Code                  backend/<canonical_path>
              → Test                  tests/**
                → Metric                docs/09_operations/ 的 SLO / 业务指标
```

用法：
- **向下**：提新功能时，从 Strategy 出发逐层落到 Test 与 Metric。任何一层缺失就是设计未完成，不是"实现细节留待以后"。
- **向上**：读到一段代码不知道为什么存在时，沿链上溯。上溯断掉 = 该代码可能是孤儿（源仓库的 `waf-domain.service.ts` 就是这样被识别为死代码的）。

**这条链未来要能自动检查断链** —— 目标是一个 `tools/architecture/` 下的检查器，扫描每个 `DOMAIN_REGISTRY.yaml` 条目是否有对应 `docs/04_domains/` 文档、每个 OpenAPI 端点是否有测试、每个 Product Capability 是否落到某个 Domain。**该检查器目前不存在**，`tools/architecture/` 是空目录。见第 9 节待办。

---

## 7. 文档与代码同步规则

PR 若改动了以下任一项，**必须在同一 PR 内**同步更新对应 canonical 文档与 registry：

| 改动类型 | 必须同步的文档 | 必须同步的 registry |
|---|---|---|
| Domain 边界 / 新增 Domain | `docs/04_domains/<domain>.md`、`docs/00_system/CURRENT_DOMAIN_MAP.md` | `governance/DOMAIN_REGISTRY.yaml` |
| API 契约 | `contracts/openapi/`、对应 domain 文档 | — |
| Domain Event | `docs/04_domains/<domain>.md` 的 Event 清单 | — |
| AI use case / Agent 能力 | `docs/05_ai/AI_USE_CASES/AIUC-NNN-*.md`、`docs/00_system/CURRENT_AI_MAP.md` | `governance/AI_USE_CASE_REGISTRY.yaml`（**待建**） |
| 授权规则 / 角色 | `docs/06_platform/` 授权规格 | `governance/` 授权 registry（**待建**） |
| 数据归属 / 留存期限 / 敏感字段 | `docs/07_data/DATA_ARCHITECTURE.md`、`docs/12_governance/COMPLIANCE_HARD_CONSTRAINTS.md` | — |
| 从 `family-ai` 迁入任何代码 | `docs/11_delivery/migration/` | `governance/MIGRATION_MANIFEST.yaml` |
| 推翻宪章某条 / 重大技术选型 | — | `governance/ADR/ADR-NNNN-*.md` + 宪章第2节执行状态表 |

**注意：这条同步检查目前尚未在 CI 中实现，是待办（见第 9 节）。** 现阶段依赖人工评审 + PR 描述自述。已实现的机械检查只有 `tests/architecture/` 下 6 个文件覆盖的 R2/R3/R7/R11/R12/R13。**未被测试覆盖的规则只是意图，不是护栏**（R14）。

---

## 8. 生命周期流程

### 8.1 归档流程（正式文档废弃）

1. 确认已有取代者（或该主题整体废弃）。
2. 用 Python `shutil.move` 把文件移入 `docs/99_archive/YYYY/<类别>/`，`YYYY` 为归档年份，`<类别>` 沿用原所属层的语义（`strategy` / `architecture` / `delivery` / `product` …）。
3. 在文件顶部（**前 2000 字符内**，否则架构测试抓不到）加：

```yaml
---
status: archived
STATUS: ARCHIVED
SUPERSEDED_BY: <取代者路径或 id>
DO_NOT_USE_FOR_IMPLEMENTATION: TRUE
archived_date: YYYY-MM-DD
archive_reason: <一句话说明为什么退役>
---
```

4. 在取代者的 front matter 里写 `supersedes: <被归档者 id>`。
5. 若被归档者曾列在 `SYSTEM_MANIFEST.md` §5 的 canonical 清单里，同 PR 从清单移除。
6. 跑 `uv run pytest tests/architecture -v` 确认 `test_archive_docs_are_marked_as_superseded` 通过。

**不删除，只归档。** 历史是证据，删掉就无法回答"当时为什么这么决定"。

### 8.2 研究晋升流程

```text
Research (Evidence)  →  Decision (ADR)  →  Canonical Document (Current Truth / Specification)
```

1. **Research**：结论写入 `docs/13_research/<market|technology|compliance>/`，front matter `status: draft` + `canonical: false`，且正文前 2000 字符内必须出现 `RESEARCH_ONLY` 或 `NOT_CANONICAL`。研究文档**永不直接**成为实现依据。
2. **Decision**：要据此改架构，先写 `governance/ADR/ADR-NNNN-<slug>.md`，说明：被决定的是什么、依据哪份研究、被推翻的是哪条既有决定、影响哪些宪章条款。
3. **Canonical**：ADR 被接受后，把决定写入对应层的 canonical 文档，front matter `status: current`。研究文档**留在 13_research 不动**（它是证据，不是历史），只在 canonical 文档里引用它。

反向禁止：不得把研究文档直接改 `status: current` 就地"晋升"。ADR 是必经环节（铁律 8）。

### 8.3 新建文档检查清单

- [ ] 属于五类信息中的哪一类？位置与之匹配？
- [ ] front matter 齐全，`status` 取自五值，`type` 与目录一致？
- [ ] 命名符合第 4 节？无中文文件名、无日期、无版本号？
- [ ] 若声明 `canonical: true`：同一主题是否已有 canonical 文档？（有则先归档旧的）
- [ ] 是否需要同时更新 `SYSTEM_MANIFEST.md` §5 清单与 `DOCUMENTATION_MAP.md`？
- [ ] Research 文档是否有 `RESEARCH_ONLY` 标记？
- [ ] `uv run pytest tests/architecture -v` 通过？

---

## 9. 已知债务与待办（如实标注）

1. **既有文档未使用 front matter**：`docs/00_system/` 三份 `CURRENT_*.md` 及 `docs/01_strategy` / `docs/07_data` / `docs/10_engineering` / `docs/11_delivery` 下多份文档仍用行内 `- **状态**: CURRENT` 标记，需一次性迁移到 front matter。
2. **Manifest §5.1 清单与磁盘不符**：`SYSTEM_MANIFEST.md` §5.1 列出 8 份 L0 文档，实际只有 4 份存在（缺 `CURRENT_DOMAIN_MAP.md`、`CURRENT_PRODUCT_MAP.md`、`CURRENT_PROGRAM_STATUS.md`，`DOCUMENTATION_MAP.md` 本次补建）。
3. **文档内路径引用陈旧**：多份文档仍引用 `docs/00_foundation/`、`docs/20_product/`、`docs/10_domain/` 等 16 层结构启用前的旧路径，需批量校正。
4. **文档与代码同步的 CI 检查未实现**（第 7 节）。
5. **Traceability 断链检查器未实现**（第 6 节），`tools/architecture/` 为空目录。
6. **front matter 字段校验测试未实现**：`status` 五值约束、`type`/目录一致性、`canonical` 唯一性目前全靠人工。这三条都是可机械检验的，按 R14 应当补测试。
7. **`governance/ADR/` 与 `governance/schemas/` 目前为空目录**，尚无一份 ADR。
