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

内容状态一栏按 2026-08-29 磁盘实况标注。**空目录不是错误，是"尚未需要"** —— 标出来是为了让 Agent 不把"目录空"误判为"文档缺失/被删"。但**"空"与"该写而没写"是两件事**：前者标"尚未需要"，后者标"缺口"。`docs/06_platform/` 曾属后者，已于本次（T-10）补齐。

> 本表在 2026-08-29 有多个并发任务同时写入 `docs/`（T-07 合规设计、T-08 traceability、T-09 research）。计数按当时磁盘状态，可能落后于最新提交。

---

## 1. 16 层速查表

| 目录 | 层 | 职责 | 典型文档 | 当前内容 |
|---|---|---|---|---|
| `docs/00_system/` | L0 | 系统真相：系统是什么、现在到哪、哪些文档算真相 | `SYSTEM_MANIFEST.md`、`CURRENT_*.md`、本文件 | **8 份**：`SYSTEM_MANIFEST` / `CURRENT_SYSTEM_BASELINE` / `CURRENT_AI_MAP` / `CURRENT_TECHNOLOGY_BASELINE` / `CURRENT_DOMAIN_MAP` / `CURRENT_PRODUCT_MAP` / `TARGET_ARCHITECTURE` / 本文件。仍缺 Manifest §5.1 所列的 `CURRENT_PROGRAM_STATUS.md`；多出一份 Manifest 未列的 `TARGET_ARCHITECTURE.md`（Specification 类，非 Current Truth） |
| `docs/01_strategy/` | L1 | 商业战略、价值定位、三区方法论 | `COMMERCIAL_VALUE_STRATEGY.md` | **1 份** + `source_materials/` 3 份原始材料（中文 `.txt`，例外保留原名） |
| `docs/02_business/` | L1 | 业务架构、业务能力地图、业务场景与流程 | `BUSINESS_CAPABILITY_MAP.md` | **3 份**：`BUSINESS_ARCHITECTURE` / `BUSINESS_CAPABILITY_MAP` / `BUSINESS_SCENARIOS_AND_PROCESSES` |
| `docs/03_product/` | L1 | 产品愿景、产品能力、页面清单 `PAGE-NNN-*` | `PRODUCT_VISION.md` | **1 份**：`PRODUCT_VISION`。页面清单尚未建立（34 个 UI 的真实状态目前只在 `14_reference/legacy_audits/` 的矩阵里） |
| `docs/04_domains/` | L2 | 每个 Domain 一份：聚合、不变量、Command、Event、Port | `FAMILY.md`、`ASSESSMENT.md` | **空，且属"该写而没写"** —— `backend/domains/` 下已有 7 个域的真实 Python 代码（`product_intelligence` 50 个 `.py`、`membership` 20、`loyalty_points` 17、`product_strategy` 9、`market_intelligence` 4、`assessment` 3、`growth_plan` 3），但边界文档一份都没有。这是继 `06_platform` 之后**下一个最实质的文档缺口**（注：`DOMAIN_REGISTRY.yaml` 的 status 也仍全写 `NOT_STARTED`，与磁盘不符，见 `CURRENT_SYSTEM_BASELINE.md` §5 漂移表第 1 条） |
| `docs/05_ai/` | L2 | AI 原生原则、AI 架构、Agent 定义 | `AI_NATIVE_PRINCIPLES.md`、`AI_ARCHITECTURE.md` | **2 份**；`AI_USE_CASES/` **空** —— 尚无 AIUC 用例文档 |
| `docs/06_platform/` | L2 | 平台内核规格：identity/authorization/consent/audit/idempotency/persistence | `PLATFORM_ARCHITECTURE.md` | **7 份**（T-10 补齐）：`PLATFORM_ARCHITECTURE`（总览 + platform/domain 分界 + 六项协作链）+ 六项内核各一份 `IDENTITY` / `AUTHORIZATION` / `CONSENT` / `AUDIT` / `IDEMPOTENCY` / `PERSISTENCE`。全部从 `backend/platform/*` 与 `tests/platform/*` **反向记录实际契约**，每份含"已知缺口"节 |
| `docs/07_data/` | L2 | 数据架构、schema 归属、留存期限与目的绑定、级联删除 | `DATA_ARCHITECTURE.md` | **1 份** |
| `docs/08_experience/` | L3 | 交互与体验规范、设计 token、可访问性 | `EXPERIENCE_PRINCIPLES.md` | **空** —— 前端代码在 `frontend/mobile/`（34 个 UI 屏幕已入仓）但阻塞于后端未就绪，体验规范暂无消费方。属"尚未需要" |
| `docs/09_operations/` | L3 | 运维、可观测性、SLO、事故响应、成本控制 | `OBSERVABILITY.md`、`SLO.md` | **空** —— 尚无承载生产流量的服务（唯一端点是 `/health` `/ready`），暂无需要 |
| `docs/10_engineering/` | L3 | 工程架构、分层约定、测试策略、CI 设计 | `ENGINEERING_ARCHITECTURE.md` | **1 份** |
| `docs/11_delivery/` | L3 | 交付计划、迁移分析、Sprint/Release/Roadmap | `CURRENT_PROGRAM_PLAN.md` | **3 份**：`CURRENT_PROGRAM_PLAN`、`TASK_BACKLOG`（T-01…T-10 任务卡）、`TRACEABILITY_REPORT_SNAPSHOT`（T-08 检查器输出快照，非 canonical）+ `migration/` **6 份**（仓库清点、死代码审计、TS→Python 能力矩阵、Python 缺口分析、`MIGRATION_PLAN_V2`、Mobile 迁移笔记）；`sprints/` `releases/` `roadmap/` **均空** |
| `docs/12_governance/` | L4 | 人类可读治理规范 | `DOCUMENT_GOVERNANCE.md`、`COMPLIANCE_HARD_CONSTRAINTS.md` | **4 份**：上述两份 + `DPIA_MECHANISM_DESIGN`、`DATA_RETENTION_BINDING_DESIGN`（均 T-07 产出，`status: draft`，落地需先出 ADR） |
| `docs/13_research/` | L4 | 调研与证据，必标 `RESEARCH_ONLY` | `market/`、`technology/`、`compliance/` | **1 份**：`market/RESEARCH-ACN-TRANSFERABILITY-TO-FGCN.md`（T-09）。`technology/` `compliance/` 仍空 —— 已完成的合规 deep-research 结论直接固化为 `12_governance/COMPLIANCE_HARD_CONSTRAINTS.md`，未留研究稿 |
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
| 平台内核（identity/authz/consent/audit/idempotency/persistence）怎么用 | `docs/06_platform/PLATFORM_ARCHITECTURE.md`（总览）+ 该目录下六份单项规格 | 全部从代码反向记录；**每份的"已知缺口"节是关键** —— 六项内核全为 `IMPLEMENTED_TESTED`（有代码有测试、零生产流量），且 `AuditRecorder.flush()` 仍是 no-op，**R6 目前在机制上不成立** |
| platform 层与 domain 层怎么划分 | `docs/06_platform/PLATFORM_ARCHITECTURE.md` §1 三问判据 | platform = 共享技术能力（对业务语义无知）；domain = 业务真相 |
| 某个业务 Domain 的边界与不变量 | **暂无文档** → 直接读 `backend/domains/<域>/` | `docs/04_domains/` 为空但 7 个域已有真实代码，是当前最实质的文档缺口 |
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

> 本节在 2026-08-29 由 T-10 逐条核对过磁盘。已消化的条目用 ~~删除线~~ 保留，便于对照"曾经缺什么"。

1. **`SYSTEM_MANIFEST.md` §5.1 清单与磁盘仍不完全相符**：Manifest 列 8 份 L0 文档，磁盘有 8 份但**不是同一批** —— 仍缺 `CURRENT_PROGRAM_STATUS.md`，多出 Manifest 未列的 `TARGET_ARCHITECTURE.md`。Manifest §5.1 需同步（属 Manifest owner 范围，本任务未改 —— 铁律 8：改 Manifest 声明的 canonical 清单不是顺手能做的事）。
2. ~~**`docs/06_platform/` 为空但代码已存在**~~ —— **已补（T-10）**：7 份规格文档，全部从代码反向记录，每份含"已知缺口"节。**注意补的是文档，不是能力** —— 文档如实记录了六项内核零生产流量、`flush()` 为 no-op 等真实缺口。
3. **`docs/04_domains/` 为空但 7 个业务域已有真实代码** —— 这是接替第 2 条成为**当前最实质的文档缺口**。同时 `DOMAIN_REGISTRY.yaml` 的 status 仍全写 `NOT_STARTED`，与磁盘不符（见 `CURRENT_SYSTEM_BASELINE.md` §5 漂移表第 1、2 条）。
4. ~~**`CURRENT_SYSTEM_BASELINE.md` 内部标题与文件名不一致**~~ —— H1 现为「当前系统基线 (Current System Baseline)」，已一致。其正文旧路径引用已由 T-10 校正。
5. ~~**多份既有文档未使用 front matter**~~ —— **已补（T-10）**：20 份文档补齐 front matter，`docs/**/*.md` 现 100% 覆盖（新增的 `TRACEABILITY_REPORT_SNAPSHOT.md` 除外，属 T-08 在写的 WIP）。
   **但 front matter 的字段校验仍无护栏**：`status` 五值约束、`type`/目录一致性、`canonical` 唯一性目前全靠人工（`DOCUMENT_GOVERNANCE.md` §9 待办 6）。按 R14，未被测试覆盖的规则只是意图。
6. ~~**`governance/ADR/` 无一份 ADR**~~ —— 现有 ADR-0001…ADR-0009 共 9 份。
7. ~~**`contracts/openapi/`、`tools/architecture/` 为空目录**~~ —— `contracts/openapi/` 现有 2 份分析文档（**但仍无 OpenAPI 契约本体**，只有端点清单与合成字段分析）；`tools/architecture/check_traceability.py` 已存在（T-08）。**`governance/schemas/` 仍为空目录** —— 治理 YAML 无 schema，registry 的字段合法性无机械校验。
8. **`docs/03_product/` 缺页面清单**：34 个 UI 的真实状态目前只能从 `14_reference/legacy_audits/` 的旧系统审计矩阵推导，AiFamily 自身尚无 `PAGE-NNN-*` 文档。
9. **`docs/05_ai/AI_USE_CASES/` 为空**：`AI_NATIVE_PRINCIPLES.md` 与 `CLAUDE.md` 铁律 5 要求每个 AI 用例落 `AIUC-NNN-*.md`，当前零份 —— 与"尚无 AI 能力接线"一致，属"尚未需要"而非缺口。
10. **文档正文里的行内状态标记与 front matter 并存**：多份文档保留了 `DOC_KIND = ... / STATUS = BINDING / TARGET_FROZEN` 这类**自造状态词**（`COMMERCIAL_VALUE_STRATEGY.md`、`AI_NATIVE_PRINCIPLES.md`、`COMPLIANCE_HARD_CONSTRAINTS.md`、`MIGRATION_PLAN_V2.md` 等的首屏代码块）。T-10 未删这些块（它们记录了授权来源与证据链，属溯源信息），但**权威状态一律以 front matter 的 `status` 为准**。`DOCUMENT_GOVERNANCE.md` §3 禁止的是把自造状态**当作状态字段**，不禁止在正文记录历史授权口径。
