# ADR-0004: 文档体系 V1.0（16 层 `docs/` 树 + 五类信息强制区分）

- **Status**: Accepted
- **Date**: 2026-08-29
- **Deciders**: project-owner / chief-architect
- **Supersedes**: null
- **Superseded By**: null

## Context

源仓库的文档不是"文档不足"，而是**文档在主动提供错误答案**。两个实测故障：

### 故障 1：三份互相矛盾、各自声称"当前基线"的文档

| 文档 | 自称 | 内容主张 |
|---|---|---|
| `50_开发_dev/CURRENT_SPRINT.md` | 当前 Sprint（2026-08-29） | Python-only 后端已在推进，含 7 条 project-owner Override |
| `50_开发_dev/governance/PROGRAM_STATUS_PLATFORM_V1.md` | 2026-08-16 裁定 | PR#36 / Principal-AI-Coach 为主线 |
| `50_开发_dev/architecture/FAMILY_PLATFORM_V3_BLUEPRINT.md` | 架构 SSOT，2026-08-16 冻结 | 平台 V3 蓝图 |

三份**互不引用**。任何人（或任何 agent）问"现在的基线是什么"，会根据先打开哪个文件得到三个不同答案，且每个答案都自带权威声明。更糟的是第四份：`architecture/FAMILY_AI_PYTHON_ONLY_MIGRATION_PLAN_V1.md`（2026-08-28）也在推进中，而它与 AIFAMILY-000 的关系至今未裁决（`MIGRATION_MANIFEST.yaml` → `docs_current_baseline_CONTRADICTION`，`status: BLOCKED`，标记为最高优先级待人工裁决项）。

### 故障 2："研究过"被读成"已实现"

研究材料与正式设计混放在同一目录层级，且研究文档不标注自身状态。后果是一份"我们调研了 X 的可行性"的笔记，与一份"X 是我们的架构"的规格，在文件系统里长得一模一样。对 LLM agent 而言这尤其致命——agent 读到一份详尽的技术方案，没有任何信号提示它"这只是候选方案，从未被采纳"，于是把它当既有事实继续推理。

### 故障 3：536 个历史证据文件与当前真相混居

`50_开发_dev/reports/` 下 536 个历史 Sprint / Gate 证据文件，其中只有 2 份值得作为最新快照参考。剩下 534 份每一份都在描述某个时刻曾为真的状态，且没有任何一份标注"我已过期"。

三个故障的共同结构：**系统里存在多个自称权威的真相源，且"真相的种类"没有被区分。** 一份 Sprint 记录、一份架构决定、一份目标态规格、一份调研笔记、一份历史快照——它们承担完全不同的认知角色，混在一起时读者无法知道自己在读哪一种。

## Decision

### 1. 五类信息强制区分（本决定的核心，比目录结构更重要）

```text
Current Truth  ≠  Decision  ≠  Specification  ≠  Evidence  ≠  History
```

| 类型 | 回答的问题 | 位置 | 强制标记 |
|---|---|---|---|
| **Current Truth** | 系统**现在**是什么（含未完成项） | `docs/00_system/` + 各层 canonical 文档 | `status: current`、`canonical: true` |
| **Decision** | 为什么这样选、推翻了什么 | `governance/ADR/` | ADR 自带 `Status: Proposed/Accepted/Superseded` |
| **Specification** | 应该被建成什么样（尚未全部成真） | `docs/03_product/`、`docs/04_domains/`、`docs/06_platform/` | `status: current` 或 `draft`，且须与 Current Truth 显式区分 |
| **Evidence** | 我们调研到 / 审计到什么（**不是决定**） | `docs/13_research/`、`docs/14_reference/` | 正文前 2000 字符内必须含 `RESEARCH_ONLY` / `NOT_CANONICAL` / `STATUS: RESEARCH` |
| **History** | 曾经是真相，现已被取代 | `docs/99_archive/` | 必须含 `ARCHIVED` / `SUPERSEDED` / `DEPRECATED` / `DO_NOT_USE` 之一 |

**Current Truth Never Mixes With History.**

### 2. 16 层目录树，按"系统真相层级"（L0–L4）组织，不按"部门"或"文档类型"

| 层 | 目录 | 承载 |
|---|---|---|
| L0 | `docs/00_system/` | `SYSTEM_MANIFEST.md` + `CURRENT_*.md` + `DOCUMENTATION_MAP.md` + `TARGET_ARCHITECTURE.md` |
| L1 | `01_strategy/` `02_business/` `03_product/` | 商业战略、业务架构、产品能力 |
| L2 | `04_domains/` `05_ai/` `06_platform/` `07_data/` | Domain 边界、AI 原则与架构、平台内核规格、数据架构 |
| L3 | `08_experience/` `09_operations/` `10_engineering/` `11_delivery/` | 体验、运维、工程规范、交付与迁移 |
| L4 | `12_governance/` `13_research/` `14_reference/` `99_archive/` | 人类可读治理、调研证据、外部参考、退役文档 |

每层附**排除清单**（"什么不该放在这里"），因为归属歧义比缺目录更常见。例如 `docs/12_governance/` 放人类可读治理规范，而**机器可执行治理**（`.yaml` registry、宪章）全部在仓库根的 `governance/`——这个分裂是有意的：机器执行的东西必须与被架构测试引用的路径一致。

### 3. 三级晋升链

```text
Research (Evidence)  →  Decision (ADR)  →  Canonical Document (Current Truth / Specification)
```

调研结论**不得**直接晋升为 canonical 文档。要据此改架构，必须先出一份 `governance/ADR/ADR-NNNN-<slug>.md`，说明：被决定的是什么、依据哪份研究、推翻了哪条既有决定、影响哪些宪章条款。这条与宪章第 3 节的修宪程序同源。

### 4. 机械执行

由 `tests/architecture/test_docs_truth_boundary.py`（R13）执行可检验部分：`docs/00_system/` 存在且有非空 `CURRENT_*.md`、`SYSTEM_MANIFEST.md` 存在、`docs/99_archive/` 下所有文档带 superseded 标记、`docs/13_research/` 下所有文档带 non-canonical 标记。

## Alternatives Considered

### A. 保持单一扁平 `docs/` + 靠命名约定（`CURRENT_*` / `ARCHIVE_*`）区分
**支持理由**：零结构成本，无需决定归属，文件少时完全够用。前缀本身已经携带类型信息。

**否决理由**：源仓库实测就是这个模式的失败——`CURRENT_SPRINT.md`、`PROGRAM_STATUS_PLATFORM_V1.md`、`FAMILY_PLATFORM_V3_BLUEPRINT.md` 三份都在同一片扁平空间里，前两者甚至都带"当前/状态"语义的名字。**命名约定不能表达"这份是决定、那份是现状、另一份是目标态"这个三元区分**，而这恰恰是需要被区分的东西。

### B. 按部门/角色分（`docs/engineering/`、`docs/product/`、`docs/business/`）
**支持理由**：符合组织直觉，每个人知道去哪个目录，权限划分自然。

**否决理由**：同一个主题会在多个部门目录下各有一份，于是"哪份是真的"这个问题**从跨文件变成跨目录**，没有解决只是搬家。而且按部门分无法表达 L0–L4 的层级依赖（战略约束业务、业务约束产品、产品约束 Domain），而这个依赖关系正是判断"冲突时以谁为准"的依据。

### C. 用文档工具（Docusaurus / MkDocs / Notion）管理，靠工具的状态字段而非目录
**支持理由**：状态字段、版本、搜索、交叉引用全部由工具提供，比目录约定强得多。

**否决理由**：**架构测试读不到工具里的状态。** 本仓库的核心治理手段是"可机械检验的规则必须有架构测试"（R14），而 R14 的伤疤（源仓库把策略写成 TS 常量然后违反它）恰恰说明：**不能被 CI 检查的规则等于不存在**。文档必须以纯文件形式驻留在仓库内、以 `pytest` 可读的方式携带状态标记。工具层可以后加作为渲染前端，但不能作为真相载体。

### D. 只写 `ADR/`，不建文档树
**支持理由**：ADR 是最高信息密度的文档形态，只记决定不记状态，无过期问题（ADR 天然不可变，靠 Supersedes 链演进）。

**否决理由**：ADR 回答"为什么这样选"，回答不了"现在真实到什么程度"。而后者是本仓库最紧缺的信息——例如"`membership` 有 2627 行代码但它的核心不变量没有测试"这个事实，不属于任何一个决定，它是现状。缺 Current Truth 层，就会再次出现"读到代码存在就以为能力存在"。`docs/00_system/CURRENT_DOMAIN_MAP.md` 的存在价值正在此。

## Consequences

### 正面
- "现在是什么"有唯一入口（`docs/00_system/SYSTEM_MANIFEST.md`），且冲突时的优先序被显式定义。
- 研究材料无法被误读为已采纳设计——由 CI 强制标记，不靠自觉。
- 归档文档必须标注被取代者，`CURRENT` 与 `ARCHIVE` 之间不存在歧义（R13）。
- 对 LLM agent 特别有效：agent 读到任何文档都能从首屏 frontmatter 判断它是现状、决定、目标态、证据还是历史。

### 负面 / 代价
- 16 层目录对小规模仓库是过度设计，多数目录当前是空的或只有 1-2 份文档。
- 归属判断成本：新文档要先决定属于哪层哪类。排除清单缓解但不消除。
- **每份 Current Truth 文档都有维护义务**：状态一变就必须更新，否则它变成新的漂移源。本次修复 `DOMAIN_REGISTRY.yaml` 就是这个代价的实例——registry 头部声明"全部 NOT_STARTED"与磁盘实况漂移了。
- 机器治理（`governance/`）与人类治理（`docs/12_governance/`）分裂，需要读者理解为何分开。

### 需要接受的风险
- **Specification 与 Current Truth 混写是最难防的错误**，且 `test_docs_truth_boundary.py` **不覆盖它**（`docs/12_governance/DOCUMENT_GOVERNANCE.md` §1.1 明确承认这一点，只靠人工评审）。一份 Specification 文档若不在首屏声明"本文件描述目标态"，读者会把它当现状——这与源仓库的故障 2 是同一个错误换了个位置。缓释：Current Truth 文档必须有"现状核对表"，逐项标真实存在 / 目标态骨架 / 不存在，并给代码路径证据。
- 已发现的执行缺口：`SYSTEM_MANIFEST.md` §5.1 列出 8 份 L0 文档，实际曾只有 4 份存在（`DOCUMENT_GOVERNANCE.md` §末记录）。**Manifest 声称的清单与磁盘不符本身就是一次漂移**，且现有测试只检查"至少有一份非空 `CURRENT_*.md`"，不检查 manifest 列出的每一份是否真的存在。

## Enforcement

**部分由架构测试执行，缺口已知。**

`tests/architecture/test_docs_truth_boundary.py` 执行：
- `docs/00_system/` 存在，且有至少一份非空 `CURRENT_*.md`
- `docs/00_system/SYSTEM_MANIFEST.md` 存在且非空
- `docs/99_archive/` 下每份 `.md`/`.txt` 的前 2000 字符含 `SUPERSEDED` / `ARCHIVED` / `DEPRECATED` / `已被取代` / `DO_NOT_USE` 之一
- `docs/13_research/` 下每份 `.md` 的前 2000 字符含 `RESEARCH_ONLY` / `NOT_CANONICAL` / `STATUS: RESEARCH` 之一

**当前仅为意图、无机械执行的部分**：
- 16 层目录的归属正确性（一份 Domain 文档被放进 `docs/03_product/` 不会被拦）
- Specification 与 Current Truth 的混写
- `SYSTEM_MANIFEST.md` §5.1 声称的文档清单与磁盘一致性
- 三级晋升链（研究直接晋升为 canonical 而不出 ADR，无测试可拦）
- ADR 编号连续性与 `Supersedes` 链完整性

## References

- `governance/REPOSITORY_CONSTITUTION.md` R13、R14
- `docs/12_governance/DOCUMENT_GOVERNANCE.md`（本决定的完整规范正文，含各层排除清单）
- `docs/00_system/SYSTEM_MANIFEST.md`、`docs/00_system/DOCUMENTATION_MAP.md`
- `tests/architecture/test_docs_truth_boundary.py`
- `governance/MIGRATION_MANIFEST.yaml` → `docs_current_baseline_CONTRADICTION`（三方矛盾的原始记录，`status: BLOCKED`）、`docs_reports_536files`、`docs_truth_hierarchy`
- 源仓库 `50_开发_dev/governance/TRUTH_HIERARCHY.md`（7 级真相优先序，其思路被 R13 吸收）
