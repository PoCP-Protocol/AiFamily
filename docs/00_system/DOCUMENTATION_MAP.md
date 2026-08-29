---
id: SYS-DOCMAP-001
title: AiFamily 文档体系导航
type: system
status: current
version: 1.0
owner: chief-architect
created: 2026-08-29
updated: 2026-08-29
canonical: true
supersedes: null
superseded_by: null
---

# AiFamily 文档体系导航 (Documentation Map)

**本文件只回答"我要的东西在哪"。** 写作规范（分类/命名/front matter/归档流程）见 `docs/12_governance/DOCUMENT_GOVERNANCE.md`；系统身份与 canonical 清单见 `docs/00_system/SYSTEM_MANIFEST.md`。

内容状态一栏按 2026-08-29 磁盘实况标注。**空目录不是错误，是"尚未需要"** —— 标出来是为了让 Agent 不把"目录空"误判为"文档缺失/被删"。

---

## 1. 16 层速查表

| 目录 | 层 | 职责 | 典型文档 | 当前内容 |
|---|---|---|---|---|
| `docs/00_system/` | L0 | 系统真相：系统是什么、现在到哪、哪些文档算真相 | `SYSTEM_MANIFEST.md`、`CURRENT_*.md`、本文件 | **4 份**：`SYSTEM_MANIFEST` / `CURRENT_SYSTEM_BASELINE` / `CURRENT_AI_MAP` / `CURRENT_TECHNOLOGY_BASELINE`（+ 本文件） |
| `docs/01_strategy/` | L1 | 商业战略、价值定位、三区方法论 | `COMMERCIAL_VALUE_STRATEGY.md` | **1 份** + `source_materials/` 3 份原始材料（中文 `.txt`，例外保留原名） |
| `docs/02_business/` | L1 | 业务架构、业务能力地图、业务场景与流程 | `BUSINESS_CAPABILITY_MAP.md` | **3 份**：`BUSINESS_ARCHITECTURE` / `BUSINESS_CAPABILITY_MAP` / `BUSINESS_SCENARIOS_AND_PROCESSES` |
| `docs/03_product/` | L1 | 产品愿景、产品能力、页面清单 `PAGE-NNN-*` | `PRODUCT_VISION.md` | **1 份**：`PRODUCT_VISION`。页面清单尚未建立（34 个 UI 的真实状态目前只在 `14_reference/legacy_audits/` 的矩阵里） |
| `docs/04_domains/` | L2 | 每个 Domain 一份：聚合、不变量、Command、Event、Port | `FAMILY.md`、`ASSESSMENT.md` | **空** —— 尚无任何业务 Domain 落地（`DOMAIN_REGISTRY.yaml` 全部 `NOT_STARTED`） |
| `docs/05_ai/` | L2 | AI 原生原则、AI 架构、Agent 定义 | `AI_NATIVE_PRINCIPLES.md`、`AI_ARCHITECTURE.md` | **2 份**；`AI_USE_CASES/` **空** —— 尚无 AIUC 用例文档 |
| `docs/06_platform/` | L2 | 平台内核规格：identity/authorization/consent/audit/idempotency/persistence | `PLATFORM_KERNEL.md` | **空** —— 六项内核**代码已存在**（`backend/platform/*` + `tests/platform/*`），但规格文档尚未回写。这是当前最明显的文档缺口 |
| `docs/07_data/` | L2 | 数据架构、schema 归属、留存期限与目的绑定、级联删除 | `DATA_ARCHITECTURE.md` | **1 份** |
| `docs/08_experience/` | L3 | 交互与体验规范、设计 token、可访问性 | `EXPERIENCE_PRINCIPLES.md` | **空** |
| `docs/09_operations/` | L3 | 运维、可观测性、SLO、事故响应、成本控制 | `OBSERVABILITY.md`、`SLO.md` | **空** —— 尚无可运行服务，暂无需要 |
| `docs/10_engineering/` | L3 | 工程架构、分层约定、测试策略、CI 设计 | `ENGINEERING_ARCHITECTURE.md` | **1 份** |
| `docs/11_delivery/` | L3 | 交付计划、迁移分析、Sprint/Release/Roadmap | `CURRENT_PROGRAM_PLAN.md` | **1 份** + `migration/` **6 份**（仓库清点、死代码审计、TS→Python 能力矩阵、Python 缺口分析、`MIGRATION_PLAN_V2`、Mobile 迁移笔记）；`sprints/` `releases/` `roadmap/` **均空** |
| `docs/12_governance/` | L4 | 人类可读治理规范 | `DOCUMENT_GOVERNANCE.md`、`COMPLIANCE_HARD_CONSTRAINTS.md` | **2 份** |
| `docs/13_research/` | L4 | 调研与证据，必标 `RESEARCH_ONLY` | `market/`、`technology/`、`compliance/` | **三个子目录全空** —— 已完成的合规 deep-research 结论已直接固化为 `12_governance/COMPLIANCE_HARD_CONSTRAINTS.md`，未留研究稿 |
| `docs/14_reference/` | L4 | 外部/旧系统参考 | `legacy_audits/` | `legacy_audits/` **2 份**：UI 前后端一致性矩阵 001、UI 后端场景一致性审计 V1。**这两份是判断 34 个 UI 真实状态的唯一依据** |
| `docs/99_archive/` | L4 | 已退役文档，`YYYY/<类别>/`，必标 `ARCHIVED` | `2026/strategy/` | **1 份**：`2026/strategy/Family家庭教育成长平台实施方案_V1.1.txt` |

### 1.1 不在 docs/ 下的关键文件

治理的**执行**部分不放 `docs/`，因为要被代码和 CI 读取：

| 路径 | 内容 | 当前状态 |
|---|---|---|
| `governance/REPOSITORY_CONSTITUTION.md` | 14 条工程宪章 R1–R14 + 第2节执行状态表 | 存在，ACTIVE |
| `governance/DOMAIN_REGISTRY.yaml` | Domain 唯一实现位置（R2 执行） | 存在，全部条目 `NOT_STARTED` |
| `governance/MIGRATION_MANIFEST.yaml` | 迁移处置登记（R3 执行：无登记不得入仓） | 存在 |
| `governance/ADR/` | 架构决策记录 | **空目录，尚无一份 ADR** |
| `governance/schemas/` | 治理 YAML 的 schema | **空目录** |
| `governance/CAPABILITY_REGISTRY.yaml` | capability 登记 | **尚不存在**（另有任务在建） |
| `governance/AI_USE_CASE_REGISTRY.yaml` | AI 用例登记 | **尚不存在**（另有任务在建） |
| `tests/architecture/` | R2/R3/R7/R11/R12/R13 机械化护栏 | 6 个测试文件，**12 passed** |
| `tools/architecture/` | 治理检查器（traceability 断链等） | **空目录，检查器未实现** |
| `contracts/openapi/` | API 契约 | 存在但**空** |
| `CLAUDE.md` / `AGENTS.md` | Agent 操作手册 | 根目录 |

---

## 2. 按问题导航

| 我想知道… | 读这个 | 备注 |
|---|---|---|
| 这个系统是什么、边界在哪、哪些文档算真相 | `docs/00_system/SYSTEM_MANIFEST.md` | 最高级文档，永远先读它 |
| 系统**现在**真实做到哪一步（含没做完的） | `docs/00_system/CURRENT_SYSTEM_BASELINE.md` §5「现状核对表」 | 别从架构图推断；那张图是**目标态**拓扑 |
| 为什么后端选 Python-only、不留 NestJS | `governance/REPOSITORY_CONSTITUTION.md` R1（含伤疤：源仓库四条并存的后端血脉） | 该决定尚**无 ADR**，只有宪章条文 |
| 为什么用 uv 而不是 pip/poetry | 宪章 R11 | 执行：`tests/architecture/test_single_toolchain.py` |
| 某个 Domain 的边界与不变量 | `governance/DOMAIN_REGISTRY.yaml`（唯一实现位置）+ `docs/04_domains/`（**目前空**） | 业务 Domain 全部 `NOT_STARTED`，边界文档尚未写 |
| 平台内核（identity/authz/consent/audit/idempotency/persistence）怎么用 | **暂无文档** → 直接读 `backend/platform/*` 与 `tests/platform/*` | `docs/06_platform/` 为空，是已知缺口 |
| AI 能力版图与各能力**真实成熟度** | `docs/00_system/CURRENT_AI_MAP.md`；判据见 `docs/05_ai/AI_NATIVE_PRINCIPLES.md` §1 五问 | 反面清单在 §4，别把硬编码文案当 AI 能力 |
| 什么算"AI 原生"、什么不算 | `docs/05_ai/AI_NATIVE_PRINCIPLES.md` | 是**上位约束**，与分项架构文档冲突时以它为准 |
| AI 输出能不能直接写进家庭事实 | 不能。宪章 R9 + `AI_NATIVE_PRINCIPLES.md` §2 | `Fact ≠ Perspective ≠ Recommendation ≠ Action` |
| 未成年人数据的法定硬约束 | `docs/12_governance/COMPLIANCE_HARD_CONSTRAINTS.md` | 与商业战略冲突时**以它为准**；§12 有冲突记录表 |
| 家长能不能看 14 岁以上孩子的数据 | `COMPLIANCE_HARD_CONSTRAINTS.md` §9 | 纠正了常见误解：14 岁线不得用于关闭监护人法定数据通道 |
| 34 个 UI 屏幕的**真实**前后端状态 | `docs/14_reference/legacy_audits/` 两份矩阵 | 唯一依据。UI 代码在 `frontend/mobile/app/ui/UI-02.tsx…UI-34.tsx`，**后端未就绪** |
| 商业战略与价值定位 | `docs/01_strategy/COMMERCIAL_VALUE_STRATEGY.md`；一句话定位见 `SYSTEM_MANIFEST.md` §2 | 原始材料在 `01_strategy/source_materials/` |
| 业务能力有哪些、闭环怎么走 | `docs/02_business/BUSINESS_CAPABILITY_MAP.md`、`BUSINESS_SCENARIOS_AND_PROCESSES.md` | |
| 迁移进度：哪些迁了、哪些不迁、为什么 | `governance/MIGRATION_MANIFEST.yaml`（逐 capability 的 disposition + evidence） | `docs/11_delivery/migration/` 是分析过程；manifest 是结论 |
| 某个能力为什么被判定不迁移 | manifest 对应条目的 `evidence` / `correction_to_plan` 字段 | 每条判定都附源文件路径与行号 |
| 某个判定被推翻的原因 | manifest 的 `project_owner_override` 字段 | 项目负责人推翻的判定原文保留，缺口不得抹掉 |
| 交付计划 / Wave 与 Batch 排期 | `docs/11_delivery/CURRENT_PROGRAM_PLAN.md`、`migration/MIGRATION_PLAN_V2.md` | |
| 某个架构决策的原因 | `governance/ADR/` | **目前为空**。已有决策的理由散在宪章的"伤疤"段落里 |
| 有哪些机械化护栏、跑什么命令 | `tests/architecture/`（6 个文件）；宪章第2节执行状态表 | `uv run pytest tests/architecture -v` |
| 哪些宪章规则**还没有**护栏 | 宪章第2节右列标"部分"的行：R1/R4/R13 部分，R6/R8/R9/R10 待接入 | **未被测试覆盖的规则只是意图**（R14） |
| 工程分层约定、测试策略 | `docs/10_engineering/ENGINEERING_ARCHITECTURE.md` | |
| 数据模型、schema 归属、留存期限 | `docs/07_data/DATA_ARCHITECTURE.md` | 合规侧约束以 `COMPLIANCE_HARD_CONSTRAINTS.md` 为准 |
| 我该怎么写/命名/归档一份文档 | `docs/12_governance/DOCUMENT_GOVERNANCE.md` | |
| 旧仓库 `family-ai` 能不能改 | 不能。`SYSTEM_MANIFEST.md` §7 + `CLAUDE.md` | 只读；内有其他会话的 WIP |

---

## 3. 已知的文档体系缺口（如实标注）

1. **`SYSTEM_MANIFEST.md` §5.1 清单与磁盘不符**：列出 8 份 L0 文档，实际存在 4 份 + 本文件。缺 `CURRENT_DOMAIN_MAP.md`、`CURRENT_PRODUCT_MAP.md`、`CURRENT_PROGRAM_STATUS.md`。
2. **`docs/06_platform/` 为空但代码已存在**：平台内核六项已有真实实现与测试，规格文档未回写 —— 这是当前最需要补的一份。
3. **`CURRENT_SYSTEM_BASELINE.md` 内部标题与文件名不一致**：其 H1 为「总体蓝图 (Master Blueprint)」，并大量引用 16 层结构启用前的旧路径（`docs/00_foundation/`、`docs/20_product/`、`governance/MIGRATION_PLAN_V2.md`）。内容有效，路径引用需校正。
4. **多份既有文档未使用 front matter**，仍用行内 `- **状态**: CURRENT`。
5. **`governance/ADR/` 无一份 ADR**：Python-only 后端、uv 工具链、16 层文档结构这三项重大决定目前只有宪章条文，没有决策记录。
6. **`contracts/openapi/`、`tools/architecture/`、`governance/schemas/` 均为空目录**。
7. **`docs/03_product/` 缺页面清单**：34 个 UI 的真实状态目前只能从 `14_reference/legacy_audits/` 的旧系统审计矩阵推导，AiFamily 自身尚无 `PAGE-NNN-*` 文档。
