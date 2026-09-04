---
id: SYS-MANIFEST-001
title: AiFamily System Manifest
type: system
status: current
version: 1.0
owner: chief-architect
created: 2026-08-29
updated: 2026-09-04
canonical: true
supersedes: null
superseded_by: null
---

# AiFamily System Manifest

> **这是本仓库的最高级文档。任何人或 AI Agent 进入仓库后，必须首先读取本文件。**
> 它只回答"这个系统是什么、边界在哪、哪些文档是正式真相"。
> 它不描述实现细节，也不描述未来愿景。

---

## 1. 系统身份

```text
Product              AiFamily —— AI 原生家庭成长平台
Canonical Repository D:\AiFamily  (计划远端: PoCP-Protocol/AiFamily, 尚未创建)
Legacy Repository    D:\family-ai (PoCP-Protocol/family-ai) —— 迁移源, 非当前系统
Legacy Baseline      commit 1ff168123d147f4d6a6eaaa677bc2f80986233d9

Backend              Python 3.12 / FastAPI / SQLAlchemy 2 / PostgreSQL
Frontend             TypeScript (Expo / React Native)
Architecture         Modular Monolith (三进程: family_api / ai_runtime / workflow_worker)
Canonical Database   PostgreSQL (按域分 schema)
AI Runtime           backend/intelligence/
Dependency Toolchain uv + pyproject.toml (唯一)
```

## 2. 服务谁，解决什么问题

**服务对象**：中国家庭 —— 家长（商业主体）、孩子（成长主体）、以及为家庭提供服务的教师/专家/机构。

**解决的问题**：家庭在孩子成长过程中反复出现的真实困境（亲子沟通、学习习惯、手机管理、自驱力不足），不是"卖课程"。

**价值定位**（来自 `docs/01_strategy/COMMERCIAL_VALUE_STRATEGY.md` §0.1，项目负责人确认）：

> 家是港湾，孩子是希望。We are family.
>
> 目标：构建一种新型的、和谐的家庭关系——家庭内部的关系，也包括家庭与家庭之间的关系。

这句话是**产品设计的价值筛选器**，不是营销口号：任何新功能都要能回答"这是在帮助家庭变得更和谐，还是在制造焦虑、贩卖排名、把孩子变成绩效指标？"

## 3. 系统边界

### 3.1 在边界内

- 家庭档案与成员关系（Family Domain）
- 成长评估、洞察、规划、行动、复盘（Growth / Assessment Domain）
- 服务供给网络：教师、专家、机构、预约、履约（Service / Teacher / Institution Domain）
- 商品、订单、会员、权益（Commerce / Entitlement Domain）
- 社区与家庭间互助（Community Domain）
- AI 运行时：Model Gateway / Context / Memory / Agent / Tool / Safety / Human Gate / Eval

### 3.2 明确在边界外（不做）

以下是**红线级排除项**，不是"暂不做"：

| 排除项 | 依据 |
|---|---|
| 家庭总分 / 家庭排名 | `governance/REPOSITORY_CONSTITUTION.md` R9；与"家是港湾"定位直接冲突 |
| AI 输出自动成为家庭事实 | R9；`docs/05_ai/AI_NATIVE_PRINCIPLES.md` |
| 临床诊断 | 合规约束 + 产品边界 |
| 向未成年人做自动化决策商业营销 | **法定绝对禁止**，《未成年人网络保护条例》第24条第3款 |
| 领域代码直连模型供应商 | R7 |

完整合规硬约束见 `docs/12_governance/COMPLIANCE_HARD_CONSTRAINTS.md`。

## 4. 当前版本与状态

```text
Wave              Wave 1 完成 (平台内核骨架), Wave 2 部分完成 (Python 域迁移)
System Baseline   docs/00_system/CURRENT_SYSTEM_BASELINE.md
Program Status    docs/00_system/CURRENT_PROGRAM_STATUS.md
```

**当前状态一句话**：治理体系与文档架构已建立，Python 平台内核骨架可运行，5 个 Python 域与整个 Mobile 前端已迁入；截至 2026-09-04，`family_need`/FGCN/AI Coach/product_intelligence 已有 85 个真实业务 HTTP 端点与真实 Postgres 持久化，Mobile 前端能否消费尚未核实——详见 `CURRENT_SYSTEM_BASELINE.md` §0.4。

详细状态（含"哪些没完成"）必须读 `CURRENT_SYSTEM_BASELINE.md`，不要从本文件推断。

## 5. 正式真相文档（Canonical Documents）

**只有以下文档是正式真相。** 其余一切（研究、参考、归档、旧仓库文档）都不是。

### 5.1 系统真相层（L0）—— 最高优先级

| 文档 | 回答什么 |
|---|---|
| `docs/00_system/SYSTEM_MANIFEST.md` | 本文件：系统是什么、哪些文档算真相 |
| `docs/00_system/CURRENT_SYSTEM_BASELINE.md` | 系统**现在**到底是什么（含未完成项） |
| `docs/00_system/CURRENT_DOMAIN_MAP.md` | 业务真相由哪些 Domain 管理 |
| `docs/00_system/CURRENT_AI_MAP.md` | AI 能力版图与各能力真实成熟度 |
| `docs/00_system/CURRENT_TECHNOLOGY_BASELINE.md` | 当前正式技术基线 |
| `docs/00_system/CURRENT_PRODUCT_MAP.md` | 当前产品地图 |
| `docs/00_system/CURRENT_PROGRAM_STATUS.md` | 当前实施进度 |
| `docs/00_system/DOCUMENTATION_MAP.md` | 文档体系导航与写作规范 |

### 5.2 机器可执行治理（governance/）

治理的**执行**部分不放 docs，放 `governance/`，因为它们要被代码和 CI 读取：

| 文件 | 作用 |
|---|---|
| `governance/REPOSITORY_CONSTITUTION.md` | 14 条工程宪章（R1–R14），最高工程约束 |
| `governance/DOMAIN_REGISTRY.yaml` | 每个 Domain 的唯一正式实现位置（R2 执行） |
| `governance/MIGRATION_MANIFEST.yaml` | 每项能力的迁移处置（R3 执行：无登记不得入仓） |
| `governance/AI_USE_CASE_REGISTRY.yaml` | AI 用例、Agent、Tool、输出和人工闸门的机器可执行治理登记 |
| `governance/ADR/` | 架构决策记录 |

### 5.3 约束级文档（优先于分项设计）

以下文档与分项架构文档冲突时，**以它们为准**：

| 文档 | 约束内容 |
|---|---|
| `docs/05_ai/AI_NATIVE_PRINCIPLES.md` | AI 原生 5 条判据；反面清单 |
| `docs/12_governance/COMPLIANCE_HARD_CONSTRAINTS.md` | 未成年人与家庭数据法定硬约束 |

### 5.4 分层设计文档（L1–L4）

见 `docs/00_system/DOCUMENTATION_MAP.md` 的完整导航。分层原则：

```text
L0  docs/00_system                     系统真相
L1  01_strategy 02_business 03_product 为什么 / 是什么
L2  04_domains 05_ai 06_platform 07_data  系统语义
L3  08_experience 09_operations 10_engineering 11_delivery  如何建 / 如何运行
L4  12_governance 13_research 14_reference 99_archive  治理 / 知识
```

## 6. 五类信息必须区分（最关键的一条规则）

```text
Current Truth  ≠  Decision  ≠  Specification  ≠  Evidence  ≠  History
```

**Current Truth Never Mixes With History.**

任何一份资料必须明确自己属于哪一类。**如果不能确定，标 `draft`，绝不能默认为 `current`。**

| 类别 | 位置 | 状态标记 |
|---|---|---|
| Current Truth | `docs/00_system/`、各层 canonical 文档 | `status: current` |
| Decision | `governance/ADR/` | ADR 自带 Status |
| Specification | `docs/04_domains/`、`docs/03_product/` | `status: current` 或 `draft` |
| Evidence | `docs/13_research/`、`docs/14_reference/` | `RESEARCH_ONLY` / `NOT_CANONICAL` |
| History | `docs/99_archive/` | `ARCHIVED` + `SUPERSEDED_BY` |

这条规则由架构测试 `tests/architecture/test_docs_truth_boundary.py` 强制执行——研究文档不声明非权威、归档文档不声明被取代，CI 直接失败。

## 7. 旧仓库政策（Legacy Policy）

`D:\family-ai` 是**迁移源与历史证据库**，不是当前系统。

- 旧仓库的任何文档**不得**作为 AiFamily 的当前真相引用。
- 旧仓库代码进入 AiFamily 必须先在 `governance/MIGRATION_MANIFEST.yaml` 登记并获批 disposition（R3）。
- 旧仓库存在**三份互相矛盾、各自声称"当前基线"**的文档（`CURRENT_SPRINT.md` / `governance/PROGRAM_STATUS_PLATFORM_V1.md` / `architecture/FAMILY_PLATFORM_V3_BLUEPRINT.md`）——这正是本文档体系存在的原因。
- 旧仓库对 AiFamily **只读**。禁止修改（其中有其他并发会话的 WIP）。

## 8. AI Agent 工作入口

任何 AI Agent 开始任务前的强制顺序：

```text
1. 读 docs/00_system/SYSTEM_MANIFEST.md          (本文件)
2. 读 docs/00_system/CURRENT_SYSTEM_BASELINE.md  (系统现状, 含未完成项)
3. 读 governance/REPOSITORY_CONSTITUTION.md      (14条工程宪章)
4. 按任务类型读对应约束:
   - 涉及 AI    → docs/05_ai/AI_NATIVE_PRINCIPLES.md
   - 涉及数据   → docs/12_governance/COMPLIANCE_HARD_CONSTRAINTS.md
   - 涉及新 Domain → governance/DOMAIN_REGISTRY.yaml
   - 涉及迁移   → governance/MIGRATION_MANIFEST.yaml
```

行为规则见根目录 `CLAUDE.md` / `AGENTS.md`。

## 9. 本文件的维护规则

- 本文件描述**身份与边界**，变更频率应当很低。
- 系统进度变化 → 改 `CURRENT_SYSTEM_BASELINE.md`，**不改本文件**。
- 系统边界变化（新增/移除排除项）→ 必须先有 ADR，再改本文件。
- 禁止在本文件堆积架构细节。它是导航，不是百科。
