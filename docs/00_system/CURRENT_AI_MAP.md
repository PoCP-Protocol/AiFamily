---
id: SYS-AI-MAP-001
title: AiFamily Current AI Capability Map
type: system
status: current
version: 3.0
owner: chief-architect
created: 2026-08-29
updated: 2026-09-10
canonical: true
supersedes: docs/00_foundation/CURRENT_AI_ARCHITECTURE.md
superseded_by: null
---

# 当前 AI 能力版图 (Current AI Map)

> 本文件回答一个问题：**AiFamily 有哪些 AI 能力，各自真实成熟到什么程度。**
> 本轮（2026-09-10）内容基于本次会话对 `governance/AI_USE_CASE_REGISTRY.yaml`、
> `governance/CAPABILITY_REGISTRY.yaml` 与 `backend/intelligence/` 实际目录的重新核查，
> 不沿用旧版本任何未重新验证的数字。历史叙述见文末 §History，不与当前状态混排。

---

## 0. 一句话结论

```text
governance/AI_USE_CASE_REGISTRY.yaml 登记 42 个 use case：
  EXPERIMENT: 6   PLANNED: 36   PILOT: 0   PRODUCTION: 0   BLOCKED: 0

governance/CAPABILITY_REGISTRY.yaml 用 `- id:` 风格登记条目本次未按该模式匹配到
（登记格式与旧版本不同，需要用不同的解析方式复核——见 §2 的诚实说明），
但 status 字段扫描到 57 处 IMPLEMENTED_TESTED、1 处 NOT_STARTED。

∴ 两份 registry 一致指向同一个结论：AiFamily 目前没有任何 AI 能力
   达到 PILOT 或 PRODUCTION。
```

---

## 1. backend/intelligence/ 实际子包清单（本次 `ls` 核查）

```text
backend/intelligence/
  agent_runtime/        11 个 .py 文件
  principal/             3 个 .py 文件
  model_gateway/        20 个 .py 文件
  growth_graph/          3 个 .py 文件（outbox_consumer.py / projectors.py / store.py）
  memory/                1 个 .py 文件（store.py）
  context_engine/       11 个 .py 文件
  tool_runtime/          7 个 .py 文件
  experience/           72 个 .py 文件（本轮体量最大的子包）
  knowledge/             4 个 .py 文件
  evaluation/           16 个 .py 文件
  human_gate/            7 个 .py 文件
  safety/                3 个 .py 文件
  observability/         5 个 .py 文件
  prompt_registry/       4 个 .py 文件
  schema_registry/       5 个 .py 文件
  capability_registry/   3 个 .py 文件
  intervention/          3 个 .py 文件
  market_insight/        1 个 .py 文件
  media_factory/        26 个 .py 文件
  product_management/   10 个 .py 文件
  design_copilot/        3 个 .py 文件（compiler.py / simulation.py / __init__.py；
                          simulation.py 内仍有 1 处 NotImplementedError，
                          compiler.py 与 __init__.py 本轮扫描未发现 NotImplementedError，
                          但也未发现实质业务逻辑——真实成熟度仍应视为接近空壳，
                          不建议据此升级其状态）
```

**`backend/intelligence/` 顶层还散落 8 个 `agi_*.py` 模块**（不在任何子包目录下）：
`agi_assessment_bridge.py`、`agi_growth_path_projection.py`、
`agi_vertical_composition.py`、`agi_vertical_dev_wiring.py`、
`agi_vertical_durable.py`、`agi_vertical_feedback.py`、
`agi_vertical_runtime.py`、`agi_vertical_service.py`。

**`path_orchestration` 本次未在 `backend/intelligence/` 下找到对应子包**——
唯一匹配的路径是一个临时验证产物
（`.codex-tmp/verify-understand-4736bf5/.../path_orchestration`），
不是仓库正式代码。任务说明中把它列为「应存在的子包」，但本次现场核查
结果是：它当前不是 `backend/intelligence/` 下的真实目录。not verified as a
real package this pass — 需要在下一次任务或 ADR 更新中澄清它是否已改名/合并
进 `principal` 或其它子包。

---

## 2. 与两份治理 registry 的交叉核对

### 2.1 `governance/AI_USE_CASE_REGISTRY.yaml`（753 行，本次通读）

status 枚举为 `[PLANNED, EXPERIMENT, PILOT, PRODUCTION, BLOCKED]`。本次对全文件
做 `status:` 计数：

| status | 数量 |
|---|---|
| EXPERIMENT | 6 |
| PLANNED | 36 |
| PILOT | 0 |
| PRODUCTION | 0 |
| BLOCKED | 0 |

已进入 EXPERIMENT 的 use case 包括 `parent_advisor`、`growth_planner`、
`read_context`、`assessment_interpretation` 等（完整清单见该 YAML 文件本身，
本文件不逐条复制以避免与源文件产生第二份可能过期的副本）。

### 2.2 `governance/CAPABILITY_REGISTRY.yaml`（2495 行）

该文件文件头明确写着治理纪律："当前尚无 capability 达到 PRODUCTION"、
"不预先登记未实现的能力"。本次对 `status:` 字段做全文扫描，命中
**57 处 `IMPLEMENTED_TESTED`、1 处 `NOT_STARTED`**，未命中 `PRODUCTION`
或 `PILOT`，与文件头声明一致。未对每条 capability 逐条核对其代码指针
是否仍然存在（not verified this pass，量级较大，留给下一轮聚焦任务）。

---

## 3. 已知架构收敛缺口：三套并行的"智能执行"机制

本次现场核查确认，当前 `backend/intelligence/` 下**同时存在三类彼此独立、
尚未统一的"智能执行"路径**：

1. **`agent_runtime/`**（11 文件）—— Agent/Authorization/Trace/Registry/
   Composition 这一套通用 agent 运行时。
2. **顶层 8 个 `agi_vertical_*.py` / `agi_*.py` 模块** —— 一条更像"纵切
   打通"风格的独立执行链路（composition/durable/feedback/runtime/service
   等命名表明它是围绕某个具体纵切场景手工搭起来的路径，不在
   `agent_runtime/` 抽象之内）。
3. **`principal/`**（3 文件）—— Principal runtime，为
   `parent_advisor`/`assessment_interpretation` 等 use case 提供
   `principal_profile` 路由（见 `AI_USE_CASE_REGISTRY.yaml` 第 39/704 行
   附近），走的又是第三条路径。

**这不是过渡期的临时重叠，而是当前需要正名的架构事实**：三者各自都有
真实代码和测试，但彼此之间没有统一的调用/编排边界。`governance/ADR/
ADR-0167-family-agi-runtime-architecture.md`（status: Proposed，
2026-09-10）已经把这个问题摆上台面——该 ADR 的核心主张是
"AiFamily = Family Domain AGI Platform"，并明确指出当前定位介于
"AGI-0（AI Assistant）与 AGI-1（Family Copilot）之间"，`path_orchestration`
这类切片"只是读取一次 context→打分→返回候选"，尚不构成完整闭环；
ADR 同时列出 Family Graph / Evidence Graph / Experience Graph / Service
Graph / Skill Graph 五张"世界模型图"目前均为雏形或未建立。

在 ADR-0167 落地一个明确的收敛决定之前，**不要把 `agent_runtime`、
`agi_vertical_*`、`principal` 三者中任何一个默认当作"唯一正确的智能执行
入口"**——本文件后续版本应以 ADR-0167 的裁决结果为准更新本节。

---

## 4. 本轮未验证 / 遗留问题清单

- `CAPABILITY_REGISTRY.yaml` 中每条 capability 的代码指针是否仍然真实存在：
  not verified this pass（仅验证了 status 字段的全局计数）。
- `design_copilot/compiler.py`、`__init__.py` 是否真的有业务逻辑，还是
  单纯占位：本次只做了 NotImplementedError 关键字扫描，未逐文件读源码，
  not fully verified this pass。
- `path_orchestration` 子包是否已被重命名/合并：not verified this pass，
  需要下一轮任务专门核查 `principal/` 或 `agi_vertical_*` 是否已经吸收了
  它的职责。
- `AI_USE_CASE_REGISTRY.yaml` 中 6 个 EXPERIMENT use case 与 3 套执行机制
  （§3）的一一对应关系：本次只核对了 `parent_advisor`/`assessment_
  interpretation` 与 `principal` 的关联，其余尚未逐条核对，not verified
  this pass。

---

## History

> 以下内容为历史记录，描述"曾经的状态"或"曾经的判断"，不代表当前事实。
> 不要把本节内容当作当前架构现状引用。

- 旧版本（version 2.1，updated 2026-09-04）声称 `backend/intelligence/`
  下有 12 项能力子包处于 EXPERIMENT（`model_gateway`、`context_engine`、
  `agent_runtime`、`tool_runtime`、`human_gate`、`evaluation`、`safety`、
  `prompt_registry`、`schema_registry`、`observability`、`memory`、
  `design_copilot`），并称 Growth Graph "已进入 EXPERIMENT 投影阶段"，
  design_copilot "每个方法仍是 NotImplementedError"。本轮重新核查发现：
  子包列表本身大体仍存在，但"12 项 EXPERIMENT"这个数字是对
  `backend/intelligence/` 子包目录数的描述，并不等同于本轮从
  `AI_USE_CASE_REGISTRY.yaml` 实际统计出的"6 个 EXPERIMENT use case"——
  两者统计对象不同（代码子包 vs. 治理登记的 use case），旧版本存在把
  两个不同维度的"成熟度"叙述混在一起、容易让读者误以为是同一个数字的
  风险，本轮已改为分别呈现且各自标注数据来源。
- 旧版本未记录 ADR-0167 与"三套并行智能执行机制"这一架构收敛缺口——
  ADR-0167 的创建日期是 2026-09-10，属于本轮新纳入的治理事实。
