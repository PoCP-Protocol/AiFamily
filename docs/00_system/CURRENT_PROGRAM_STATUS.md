---
id: SYS-PROGRAM-STATUS-001
title: AiFamily Current Program Status
type: system
status: current
version: 1.1
owner: chief-architect
created: 2026-09-10
updated: 2026-09-10
canonical: true
supersedes: null
superseded_by: null
---

# AiFamily 当前项目状态

> 本文件所有"当前"判断均以下方 commit 为准：
> **`186407a7528fcc33334242bf0bcd94da74064f3a`**（`git log -1 --format=%H`，main 分支 HEAD）。
> 任何断言若无法追溯到这个 SHA 或本次验证动作，标注为 `not verified this pass`，不得沿用旧文档数字。

## 0. 结论

AiFamily 正在建设为一个面向家庭成长场景的、可治理的 AI 原生平台。当前仍处于平台内核与业务纵向切片持续收敛阶段，**尚不能宣称已完成 AGI 平台或生产级 AGI 能力**。

当前最重要的工程目标不是增加更多孤立 Agent，而是把 Context、Growth Graph、Model Gateway、Agent/Tool Runtime、Human Gate、Audit/Outbox 和业务 Domain 连接成同一条可回读、可审计、可恢复的生产闭环。

## 1. 状态分层

| 层级 | 当前判断 | 证据边界 |
|---|---|---|
| 治理与架构护栏 | 已建立，持续补强 | `governance/`、`tests/architecture/`；本地护栏不等于 CI 已执行 |
| AI Runtime 基础组件 | EXPERIMENT | 以 `CURRENT_AI_MAP.md` 的成熟度矩阵为准，不因目录或注册表存在而升级 |
| Context / Memory 持久化 | 部分 EXPERIMENT | 已有 durable adapter 与删除/作用域约束；生产跨流程接入、权限与 worker 证据仍需补齐 |
| Growth Graph / Family Growth | EXPERIMENT / 部分纵向切片 | 允许只读投影和草案输出；不得把 `PathDraft`、Perspective 或 Recommendation 写成家庭事实 |
| 业务 Agent | 未达到 PILOT/PRODUCTION | 需要真实上下文驱动、统一组合根、人工闸门、持久化与回读证据 |
| 生产部署与持续验证 | 未闭合 | 需要同一 ref 的 HTTP、PostgreSQL、重启回读、负向/恢复和 CI 证据 |

## 2. AGI 平台验收定义

“AGI 平台”在本项目中不是泛化的模型宣称，而是以下可验证能力的组合：

1. 能在授权范围内理解家庭上下文，并区分事实、观察、推断、建议和行动。
2. 能通过统一 Model Gateway 与 Agent/Tool Runtime 进行可追踪推理和受控工具调用。
3. 能把结果沉淀为带 provenance 的 Perspective/Recommendation/Draft，并由 Human Gate 决定是否产生业务状态变化。
4. 能跨请求、进程和重启读取同一家庭的持久化上下文、成长图和操作记录。
5. 能在租户、家庭、成员、同意、删除、过期、撤回和失败恢复边界内 fail closed。
6. 能以架构测试、业务验收测试、运行证据和 CI 门禁持续证明上述性质。

以下内容不构成 AGI 平台证据：静态 UI、硬编码候选、fixture/synthetic 数据、单元测试绿灯、页面刷新、仅内存实现、孤立分支或未接入组合根的代码。

## 3. 当前优先级门禁

按优先级，后续交付必须依次收敛：

| 优先级 | 门禁 | 完成判据 |
|---|---|---|
| P0 | 统一组合根 | production wiring 能解析真实 Context、Graph、Gateway、Agent、Gate、Audit/Outbox；缺依赖时 fail closed |
| P0 | Family Growth 闭环 | 同一 ref 完成 HTTP → PostgreSQL → Audit/Outbox → 重启回读；至少覆盖两个家庭隔离、版本冲突和恢复 |
| P0 | AI 输出边界 | 输出保持 DRAFT/PROPOSED，状态变更必须经过 Named Action 与 Human Gate，并可追溯 provenance |
| P1 | Runtime 生产化 | 跨进程 worker、队列 lease、失败重试/DLQ、幂等和运维观测具备真实验证 |
| P1 | 合规与删除 | 同意、读取审计、撤回/删除、派生数据清理和未成年人高影响动作阻断具备业务路径证据 |
| P1 | CI 执行 | 架构、lint、后端验收和数据库测试在 CI 中真实运行；禁止仅以本地结果宣称完成 |

## 4. 当前明确阻断

- `CURRENT_AI_MAP.md` 所列 AI 能力大多仍为 `EXPERIMENT`，五类业务 Agent 尚未达到 `PILOT/PRODUCTION`。
- Growth Graph 与 Family Growth 的跨流程事件接入、生产检索和同一 ref 的部署/重启证据尚未闭合。
- `CURRENT_SYSTEM_BASELINE.md` 记录的远端仓库与 CI 执行缺口仍未消除。
- 当前工作区存在并发未提交 WIP；任何后续变更必须只修改明确负责的文件，不能把混合工作区状态当作已验证交付。

## 5. 交付与汇报规则

每次声称能力推进时，必须同时给出：分支与 commit、明确 pathspec、实现入口、测试命令与结果、运行环境、数据库/重启/负向证据，以及仍未测量的项。证据不足时使用 `PARTIAL`、`BLOCKED`、`NO-GO` 或 `UNMEASURED`，不得将迁移、注册或局部测试升级为生产能力。

本文件只记录当前项目状态；能力细节以 `CURRENT_AI_MAP.md`、`CURRENT_SYSTEM_BASELINE.md`、`CURRENT_DOMAIN_MAP.md` 及相关 ADR 为准。

## 6. main 分支近况（as of 186407a）

- **并发会话合并事故已修复。** `c480db3`（`merge: integrate growth plan adoption`）把并发会话的 growth-plan-adoption 工作并入 main 后，引入 12 个测试失败。`186407a`（`fix: repair 12 test failures found on main after concurrent-session merge`）逐一定位并修复，未放宽任何断言。已核实的四类根因：
  1. `test_production_vertical_family_growth_install_guard.py`（4 例）：共享 `_Port` test double 缺少 `ProductionVerticalFamilyGrowthComposition.__post_init__` 新要求的 `generate_structured`/`published`/`latest` 方法。
  2. `test_production_experience_wiring.py`（4 例）：`_body()` 手抄的 output_schema 落后于 `standard_assets.py` 新增的必填 `path` 字段；改为调用 `family_experience_output_schema()` 而非手抄副本，避免再次静默漂移。
  3. `test_fgcn_routes.py`（1 例）：`ModelDraft.__post_init__` 现在在构造期即拒绝非 DRAFT 状态（R9），比该测试的伪造 draft 场景更早失败；已在 `submit_assignment_proposal` 补齐对应 except 分支，确保仍以 422（`fgcn_model_draft_not_reviewable`）fail closed 而非 500。
  4. `test_assessment_flow.py`（2 例）：测试用了过期的 "COMMUNICATION" 选项值，真实 UI-02 五主题选项已变更（其余细节以该 commit 的完整日志为准，未逐字复核第四类的剩余描述）。
- **本次会话本地跑 `pytest --collect-only` 出现 141 个 collection error**（多为 `ValueError: mutable default` / `SyntaxError`），怀疑是本机 Python/依赖版本与仓库锁定版本不一致，而非 186407a 引入的回归——**未在本次验证中确认其与 CI 环境的关系，标记为 not verified this pass**，不得据此判断 main 当前测试通过率。

## 7. 当前开放 PR（gh pr list --state open，已核实 4 条）

| PR | 分支 | 标题 | 涉及路径 |
|---|---|---|---|
| #23 | `feat/path-draft-persistence-clean` | path drafting persistence contract + honest AI_USE_CASE_REGISTRY | `backend/intelligence/path_orchestration/{contracts,planner,understand_adapter}.py`、`governance/AI_USE_CASE_REGISTRY.yaml`、`governance/MIGRATION_MANIFEST.yaml`、对应 `tests/intelligence/path_orchestration/*` |
| #24 | `feat/web-theme-token-parity` | web 端消费 mobile 的 design tokens，取代自造调色板 | `frontend/web/src/main.tsx`、`frontend/web/src/styles.css` 等 |
| #25 | `feat/path-orchestration-understand-gateway-adapter` | 真实 Model-Gateway 支撑的 UNDERSTAND adapter | 与 #23 重叠的 `path_orchestration` 合约/adapter/planner 文件 + 对应测试 |
| #26 | `feat/path-orchestration-knowledge-candidates` | 用知识检索 + 模型改写取代固定候选池 | 在 #25 基础上新增 `candidate_explanation_adapter.py`、`knowledge_backed_candidates.py`、`knowledge_candidate_source.py` + 对应测试 |

四条 PR 均未合并；#23/#25/#26 三者在 `backend/intelligence/path_orchestration/` 下有重叠改动（同名文件被多条 PR 各自新增/修改），合并顺序与冲突尚未验证，本次未检查其 CI 状态，标记为 not verified this pass。

## History

- 2026-09-10 之前版本的本文档以架构护栏叙事为主（P0/P1 门禁表、AGI 平台验收定义），未挂靠具体 commit SHA，历史判断已随 §0–§5 保留但不再单独复核其时间点；本次改版起，所有新增判断必须挂靠 commit。
