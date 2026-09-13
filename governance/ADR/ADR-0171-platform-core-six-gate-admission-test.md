# ADR-0171: Platform Core 六门准入测试——任何实现必须证明增强六维度之一才可进 Core

- **Status**: Accepted
- **Date**: 2026-09-13
- **Deciders**: project-owner
- **Supersedes**: null（是 `ADR-0169` §11 Vertical Pack 机制的可执行判据补充，
  不改动其内容）
- **Superseded By**: null

## Context

用户本次会话提交了一份体量很大的技术研究材料（涉及 Temporal World Model、
分层 Memory、Belief/Unknown 推理、Hierarchical Planning、Reflection、Hybrid
Retrieval、Capability Graph、MCP/A2A、多模型路由、因果推理局限、Outcome
Learning、Evaluation、法咪莉定位、安全合规、五个数据护城河、北极星指标、
FIC-001~006 六个里程碑），核心结论与已经冻结的 `ADR-0169`/
`AIFAMILY_STRATEGIC_CONSTITUTION_V1.md` 方向一致（Family World Model 而非
教育功能是核心资产，教育是训练场不是终局），但补充了一条此前没有的、
**可以立即执行且低风险**的治理规则：

> 从下一阶段开始，所有实现都必须证明它在增强 World Model、Memory、
> Goal/Planning、Action/Tool、Outcome Learning、Safety/Evaluation 六项中
> 的至少一项，否则不得进入 Platform Core。课程、测评、教师、直播等不能
> 再直接进入 Core。

材料里其余内容（FIC-002~006 的具体设计、Temporal Belief State 的字段结构、
分层 Memory 的具体实现、MCP/A2A 接入时机、Planner 分级、Evaluation 十项
框架等）体量巨大，每一项都值得独立的探查+设计+实现会话，本 ADR **不**把
它们当场批准为待执行任务——按 `ADR-0169`"战略边界宽、产品边界窄"与本次会话
已经反复验证的纪律（先证明 Child Growth 闭环，再扩张），一次性把整份研究
报告转成执行计划，会重犯用户自己在同一份材料第二十五节警告的错误："不要
同时引入五套框架""现在不要马上实现 A2A"。

本 ADR 只冻结这条**准入门槛规则本身**——它本身范围清晰、可执行、且与已经
做的 `ADR-0170`（agi_vertical_runtime.py 未来整改必须经 Principal）等既有
决定完全兼容,是把研究材料转化为治理动作里风险最低、价值最高的一步。

## Decision

**冻结六门 Platform Core 准入测试**，作为 `AIFAMILY_STRATEGIC_CONSTITUTION_V1.md`
§11 Vertical Pack 机制的可执行判据：

任何要进入 Platform Core（`Family Intelligence Core`：Family/Members/
Relationships/Consent/Family World State/Needs/Goals/Decisions/Plans/
Resources/Actions/Outcomes/Evidence/Unknowns/Risks 及其运行时）的新增代码，
必须能明确回答"这项改动增强了以下六项中的哪一项"，否则应归入 Vertical Pack
层，不得进入 Core：

```text
1. World Model      是否让系统更准确理解家庭状态？
2. Memory            是否改善了跨会话/跨时间的家庭记忆？
3. Goal / Planning   是否改善了目标澄清或行动规划的质量？
4. Action / Tool     是否改善了行动执行或工具调用的可靠性？
5. Outcome Learning  是否改善了从真实结果中学习的能力？
6. Safety / Evaluation 是否改善了安全边界或评估治理？
```

课程、测评、教师、直播、活动等业务内容，无论多重要，都归入 Vertical Pack
（`ADR-0169` §11），不能以"业务很重要"为理由直接写入 Core 的 schema 或
运行时。

**本 ADR 不批准**用户材料中提出的具体技术方案（Temporal Belief State 字段
结构、五层 Memory 实现、Planner 三分级、Hybrid Retrieval 四种检索、MCP/A2A
接入、FIC-002~006 里程碑排期）为已授权的执行任务——这些是有价值的候选方向，
留待下一阶段逐项单独立项、单独探查现状、单独设计，见 Enforcement 段。

## Alternatives Considered

**A. 把整份研究材料转成一份 `AIFAMILY_AGI_PLATFORM_MASTER_ARCHITECTURE.md`
canonical 文档，一次性冻结全部内容。**
支持理由：一次性建立完整技术蓝图，避免反复讨论。
否决理由：材料本身列出的六个里程碑（FIC-001~006）每一项体量都类似本次会话
已经做的 ADR-0170/FamilyNeed 证据类型化 这种量级的独立工作，一次性冻结全部
细节等于在没有逐项核实现有代码（例如 Memory Store 当前是否真的具备五层
分区、Model Gateway 当前是否已支持按任务路由多模型）的情况下批准大量具体
技术承诺——违反本仓库"没有代码和测试证据的内容只能标为 PLANNED 或 GAP"的
纪律（`CURRENT_PROGRAM_PLAN.md` 总控责任第三条）。

**B. 完全不处理这条消息，只口头确认方向一致。**
支持理由：避免过度处理一次性研究材料。
否决理由：六门准入测试是这份材料里少有的、能立即转化为可执行治理规则且
几乎零风险的内容——不落地成 ADR，下次任何人讨论"这个功能该不该进 Core"
时，仍然没有具体判据可以引用，白白浪费了这条建议的价值。

## Consequences

### 正面
- 给"课程/教师/专家不得进 Core"（已在 `ADR-0168`/`ADR-0169` 冻结）补了一条
  正向判据（不只是"排除清单"，还有"准入清单"），review 时更容易判断。
- 为后续任何新 Vertical Pack 或 Core 改动提供了一句话可以引用的门槛。

### 负面 / 代价
- 六项维度本身还没有对应的量化指标（例如"World Model 改善"目前无法用
  测试自动判定），短期内只能靠 code review 人工判断，不是自动化门槛。

### 需要接受的风险
- 用户材料中的其余内容（Temporal World Model 具体设计、Memory 分层实现、
  MCP/A2A、Planner 分级、Evaluation 十项框架、FIC-002~006 排期）目前只是
  已阅读、已认可方向、**未批准为执行任务**的候选——如果后续被误当作"已经
  决定要做"，会重犯"文档说要做、代码没做、别人以为做了"的错误，本 ADR
  的 Enforcement 段专门列出来防止这个误读。

## Enforcement

- **当前仅为文档层准入规则**，与既有 ADR 一致的诚实标注：暂无自动化测试。
- `docs/00_system/AIFAMILY_STRATEGIC_CONSTITUTION_V1.md` 新增 §21（六门准入
  测试），引用本 ADR。
- **本次会话不批准、不执行**以下候选任务，留给用户下次单独确认优先级后
  再逐项立项（不是清单式一次性排期，是"逐项单独确认"）：
  1. Temporal Family World Model（Family World State 的时序化+置信度+
     信息类型字段设计与落地）——与本次已完成的 `EvidenceRef.epistemic_status`
     增量属于同一方向，是其自然延伸，可作为下一阶段优先候选。
  2. Hierarchical Family Memory 五层实现（当前 `backend/intelligence/memory/`
     现状与目标态的差距，需要先核实现状）。
  3. Goal Engine 作为一级能力落地。
  4. Evaluation 十项框架。
  5. MCP/A2A 接入——用户材料本身已明确"现在不要马上实现"，本 ADR 重申。
  6. FIC-002~006 里程碑的具体排期是否 Supersede 现有 `CURRENT_PROGRAM_PLAN.md`
     P0-P6 排期，需要总架构师与项目负责人另行确认（与 `ADR-0169` Enforcement
     第4条同一纪律）。

## References

- `docs/00_system/AIFAMILY_STRATEGIC_CONSTITUTION_V1.md`（本次新增 §21）
- `governance/ADR/ADR-0169-family-agi-species-change-and-strategic-constitution.md`
  §11（Vertical Pack 机制，本 ADR 的可执行判据补充对象）
- `governance/ADR/ADR-0170-runtime-convergence-acceptance.md`（同一会话内的
  另一项 Runtime 治理决定，两者兼容）
