---
id: SYS-PROGRAM-STATUS-001
title: AiFamily Current Program Status
type: system
status: current
version: 1.0
owner: chief-architect
created: 2026-09-10
updated: 2026-09-10
canonical: true
supersedes: null
superseded_by: null
---

# AiFamily 当前项目状态

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
