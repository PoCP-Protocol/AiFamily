---
id: DLV-AIFAMILY-AGENT-TEAM-001
title: AiFamily 多模态 AI 体验子项目 Agent 团队章程
type: delivery-specification
status: draft
version: 1.0
owner: AG-00
created: 2026-08-30
updated: 2026-08-30
canonical: false
evidence_class: NOT_CANONICAL
---

# AiFamily 多模态 AI 体验子项目 Agent 团队章程 V1

> 本章程只约束本子项目的敏捷协作、编号、战场和交付责任，不改变系统宪章、领域边界或供应商准入决策。
> 子项目范围为 Web UI 的多模态 AI 体验；移动端、未经准入的真实家庭数据和直接供应商调用不在授权范围内。

## 1. 项目目标与成功定义

### 1.1 目标

用成熟多模态 LLM 先跑通一条可回放的 Web 纵向切片：

```text
文字/图片输入
  → 同意、权限、媒体登记
  → Model Gateway 结构化生成
  → AI 解释、节奏、反馈、叙事和难度建议
  → 用户接受/改写/跳过/暂停/人工接管
  → 真实行动事件、反馈、评估和回放
```

### 1.2 成功定义

本项目的“极致用户体验、极致游戏感、极致成就感”必须由 AI 在授权上下文内动态实现：

- AI 根据真实上下文生成个性化节奏、即时反馈、成长叙事和下一步难度；
- Web UI 让用户随时知道当前状态、可以选择、暂停、重试、回到上次位置或请求人工；
- 成就不是模型叙事或预设奖励，而是由真实 `ExperienceEvent`、`ActionOutcome` 等行动事件触发，能够回放并引用证据；
- 不以虚构积分、家庭总分、家庭排名、儿童商业画像或焦虑刺激来替代成长体验。

“模型能回答”不等于项目成功。成功必须同时具备可调用路径、失败路径、治理证据和可复现测试。

## 2. 团队编号与角色

编号只在本子项目内使用，绑定角色而非单次任务；编号永不复用。每个 Agent 必须只修改自己的战场，跨战场需求通过交付说明或由 AG-00 安排集成窗口处理。

| 编号 | 角色 | 核心职责 | 独占战场 | 不得修改 |
|---|---|---|---|---|
| **AG-00** | 总 PM / 集成负责人 | 目标、优先级、Sprint、依赖协调、集成、验收、风险和发布闸门 | `docs/11_delivery/`、集成记录、项目看板 | AG-01~04 的实现战场；不得为“过绿”改动他人测试断言 |
| **AG-01** | 产品与敏捷 PM | 市场洞察、竞品证据、IPD/PDM/PLM 切片、用户故事、验收标准、体验与商业价值假设 | `docs/01_strategy/`、`docs/02_business/`、`docs/03_product/`、本章程引用的产品交付文档 | `backend/`、Web 实现、治理 YAML；不得把未核验竞品内容写成事实 |
| **AG-02** | AI Runtime / Model Gateway | 多模态契约、Provider Adapter、Agent/Skill 编排、Run 状态、Prompt/Schema、Provenance、成本和评估 | `backend/intelligence/` 及对应 `tests/intelligence/` | 领域 Repository、Web 页面、业务事实表；不得直接 import 供应商 SDK |
| **AG-03** | Web 体验工程 | Web Experience Studio、输入/媒体状态、Run 状态、草稿查看、确认/反馈/暂停/回放、无障碍和可访问性 | 独立 Web 前端目录（若尚未建立则由 AG-00 先登记路径）及其专项测试 | `backend/intelligence/`、`backend/domains/`、治理文件；不得用硬编码假 AI 结果冒充能力 |
| **AG-04** | QA / 合规 / 评估与发布守护 | 测试策略、拒绝集、gold set、架构与合规检查、故障注入、环境 parity、发布/回滚证据 | `tests/architecture/`、专项 QA/Eval 夹具、发布检查记录 | 未授权业务实现；不得为了通过 CI 放宽规则或删除失败测试 |

### 2.1 AG-00 的最终责任

AG-00 对“是否可以标记完成”负最终责任，但不替代专业 Agent 实现。只有当代码、测试、文档、治理和回滚证据齐全时，AG-00 才能把任务标为 `DONE_WITH_EVIDENCE`；供应商生产准入仍需合规和项目负责人批准。

## 3. 角色输入、输出和依赖

| Agent | 必须输入 | 必须输出 | 主要依赖 |
|---|---|---|---|
| AG-00 | 当前基线、项目目标、各 Agent 报告、CI/测试结果 | Sprint 目标、任务卡、依赖裁决、集成记录、验收结论、风险/阻塞台账 | 全体 Agent、canonical docs、治理闸门 |
| AG-01 | 用户场景、市场/竞品证据、三区方法论、IPD/PDM/PLM 文档 | 用户故事、价值假设、场景流程、优先级、验收矩阵、产品版本边界 | AG-00 目标；AG-04 证据质量反馈 |
| AG-02 | AG-01 的验收 schema、授权上下文、Model Gateway 契约、供应商准入状态 | 可审计的结构化请求/响应、Run/Attempt、Prompt/Schema 版本、Provenance、AI 失败语义 | AG-01 schema；AG-04 评测与安全用例；平台授权/同意能力 |
| AG-03 | AG-01 用户流程和状态字典、AG-02 API/事件契约、视觉与无障碍要求 | 可运行 Web 纵向切片、状态呈现、反馈/确认/暂停/回放交互、前端测试 | AG-02 契约；AG-04 可访问性与端到端验收 |
| AG-04 | 所有 Agent 的变更、测试、gold set、拒绝矩阵、合规约束 | 实测测试输出、咬人验证、质量报告、发布 Gate、阻塞与回滚建议 | AG-00 范围；AG-02 评估指标；AG-03 可访问性路径 |

依赖原则：上游未给出可执行契约时，下游不得自行发明第二套对象；发现缺口必须提交 `BLOCKED` 报告，由 AG-00 裁决是补契约、缩小切片还是暂停任务。

## 4. 敏捷实施任务分解

### Sprint 0：团队与契约对齐

- AG-00：冻结 Web-only 范围、任务卡模板、状态机和集成窗口。
- AG-01：把市场洞察、竞品证据和真实家庭场景转成 P0 用户故事。
- AG-02：确认 text/image 首批模态，统一 `StructuredRequest`、`MediaInput`、Provenance 和错误码。
- AG-03：产出 Experience Studio 低保真交互和状态清单。
- AG-04：建立匿名/合成 gold set、拒绝集、合规检查和验收脚本。

退出条件：所有 P0 故事有输入/输出/异常/权限/测试定义；未准入 provider、无同意、越权媒体、schema 错误至少各有一条可重复拒绝测试。

### Sprint 1：文字 + 图片 Web 纵向切片

- AG-01：验收“输入—理解草稿—用户选择”的最小体验，并冻结文案与可解释性要求。
- AG-02：通过 Model Gateway 生成 DRAFT；记录 attempt、版本、媒体 hash、延迟和成本（可得时）。
- AG-03：实现输入、上传、loading、success、refused、timeout、retry、human review 和 draft 展示。
- AG-04：执行成功、失败、超时、未准入、跨租户和原始媒体不入日志测试。
- AG-00：完成纵向集成演示和退出评审。

退出条件：Web sandbox 能完成一次真实契约调用；模型不可用时有可恢复错误；AI 输出仍为 `DRAFT`，不写入 canonical Fact。

### Sprint 2：游戏化体验、成就和可恢复闭环

- AG-01：定义“节奏、反馈、叙事、难度、成就”的体验验收，不把点击量当成长效果。
- AG-02：将授权上下文和真实事件注入 AI 生成链路，提供可回放的 Run、checkpoint 和反馈输入。
- AG-03：实现接受、改写、跳过、暂停、恢复、请求人工、反馈和回放；展示证据与可调整项。
- AG-04：验证成就只能由真实行动事件触发，验证重复提交、删除、重启、回放和人工闸门。
- AG-00：裁决是否进入 Pilot，登记所有未完成能力。

退出条件：成功、拒绝、暂停、恢复、人工升级、删除、重放均有实测证据；不存在虚构积分、家庭总分、家庭排名或模型直接改事实的路径。

### Sprint 3：评估与多模态扩展准备

- AG-01：基于市场反馈更新需求优先级和产品版本假设。
- AG-02：完成模型/Prompt/Schema 版本比较、成本预算和音频/视频异步契约预研。
- AG-03：完善低带宽、替代文本、媒体权限和多语言体验。
- AG-04：生成质量、安全、延迟、成本、可访问性和环境 parity 报告。
- AG-00：以证据决定是否扩大到音频/视频；未达阈值不得打开生产路由。

## 5. 通用任务卡格式

每张任务卡必须包含：

```text
任务编号 / Agent 编号 / Sprint
业务场景与用户价值
输入、活动、输出、规则、异常
契约：API / Command / Event / Projection / Gateway 对象
权限、同意、数据分类、保留和删除边界
成功、拒绝、超时、重试、暂停、人工、删除、回放测试
依赖、风险、回滚点
修改文件清单（仅限本 Agent 战场）
实际命令与输出
未完成项与下一步
```

## 6. 协作和同步要求

### 6.1 每日异步同步格式

每天由各 Agent 在项目线程提交一条不超过 10 行的同步：

```text
[AG-xx][YYYY-MM-DD]
昨日证据：完成了什么，命令/链接是什么
今日产出：准备交付什么
风险/阻塞：事实、影响、解除条件
需要 AG-00 决策：没有则写“无”
战场变更：文件路径和是否影响其他 Agent
```

不得只写“已完成”“代码已提交”；必须给出可核验路径或命令输出。

### 6.2 状态流转

```text
PLANNED → READY_FOR_DEV → IN_PROGRESS → READY_FOR_REVIEW
        → DONE_WITH_EVIDENCE → PILOT_CANDIDATE → ADMITTED
```

任何进行中状态都可以进入 `BLOCKED`。阻塞必须记录触发证据、影响范围、解除条件和负责人。`ADMITTED` 不是 Agent 自行决定的状态，必须有供应商、合规、DPIA、人工闸门和发布批准证据。

### 6.3 并发安全

- 不使用 `git add -A`、`git add .` 或 `git commit -a`；提交只带明确 pathspec。
- 不覆盖、格式化或清理其他 Agent 的未提交修改。
- 不创建第二个 Model Gateway、第二套 Experience 契约或第二个业务后端。
- 发现共享文件冲突时，停止修改并向 AG-00 报告，不通过强制覆盖解决。

## 7. Definition of Done（DoD）

任务只有同时满足以下条件，才能标记 `DONE_WITH_EVIDENCE`：

1. 用户故事、Web 流程、成功路径和拒绝/超时/重试/暂停/人工/删除路径已明确。
2. 代码只使用既有 canonical 契约；AI 调用统一经过 `backend/intelligence/model_gateway`。
3. 单元、契约、集成、架构或端到端测试按任务范围真实运行，并贴出命令和输出。
4. 修改文件范围符合 Agent 战场；相关 Ruff/类型/前端检查通过，新增错误已登记。
5. AI 输出带完整 provenance，初始状态为 `DRAFT`/`PROPOSED`，且不能自动改变 canonical Fact。
6. 媒体处理具备 purpose、consent、scope、retention、deletion_ref 和删除证明；普通日志不含原始儿童媒体。
7. Web UI 能表达 loading、partial、success、refused、timeout、retry、waiting、human review 和 deleted 等适用状态，并支持无障碍。
8. 极致体验所需的个性化节奏、即时反馈、成长叙事和难度调整有授权上下文和模型版本依据；成就只能绑定真实 `ExperienceEvent`/`ActionOutcome`，可回放。
9. 不产生家庭总分、家庭排名、虚构积分、儿童商业画像、临床诊断或疗效承诺。
10. sandbox/test/production 的路由、状态机、错误语义、权限和人工闸门一致；外部适配器差异已登记。
11. 交付说明列出未完成项、已知风险、回滚方式和下一步；“文档存在”或“页面能打开”不得单独作为完成证据。

## 8. 质量红线与升级机制

以下任一情况出现，AG-04 可直接将任务置为 `BLOCKED`，AG-00 必须在下一个同步窗口裁决：

- 未经准入的 Provider 被用于真实家庭/未成年人数据；
- 领域代码直接调用供应商，或 AI Runtime 导入业务 Repository；
- AI 结果直接写成 Family/Growth/Service/Commerce 事实；
- 成就由模型自由编造，或出现家庭总分、排名、虚构积分；
- 媒体无同意、跨租户、无法删除或删除证明缺失；
- 测试、拒绝路径或回滚证据缺失却要求标记完成；
- 竞品或市场结论没有来源，被当作产品事实使用。

AG-00 的裁决必须包含：事实证据、受影响任务、选择（修复/缩小/暂停/回滚）、责任人和下一次复核时间。任何 Agent 不得以进度压力自行越过红线。

## 9. 本章程的维护

本文件是本子项目的执行章程，属于 `NOT_CANONICAL` 交付文档。若要改变系统边界、AI 权限、数据治理、供应商准入或宪章约束，必须先由 AG-00 提交对应 ADR/治理变更，不得在本文件中悄然放宽。

