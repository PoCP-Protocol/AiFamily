---
id: DEL-SCENARIO-MVP-REPLAN-002
title: AiFamily 场景驱动全量 MVP 实施计划 V2
type: delivery
status: draft
version: 2.0
owner: chief-architect
created: 2026-08-31
updated: 2026-08-31
canonical: false
supersedes: docs/11_delivery/CURRENT_PROGRAM_PLAN.md
superseded_by: null
---

# AiFamily 场景驱动全量 MVP 实施计划 V2

## 0. 当前执行阶段：PRD-first

本轮先完成并评审全量 MVP PRD，再恢复下一轮业务代码派工：

```text
场景研究 → PRD评审包 → 场景/接口/数据/体验契约冻结 → 按场景派工 → 代码施工 → 场景验收
```

已有代码候选保留为工程输入，不回滚，也不代表 PRD 已批准；未有对应 PRD 的新增功能暂停扩张。

## 1. 组织重组：场景小队负责结果，平台小队负责能力

### 总体结构

```text
总架构师/总设计师/项目经理
              │
              └── 唯一 PMO：排程、冲突裁决、证据板、每小时回报
                    ├── 家庭成长主链队：S1首达 + S2成长循环
                    ├── 理解智能队：S3知识 + AI Draft + 多模态输入
                    ├── 服务价值队：S4服务履约 + S6方案/会员/权益
                    ├── 家庭关系队：S5受控关系网络
                    └── 平台支援：Platform Core、Experience、QA/Release

小橘灯：独立产品队列，单独向 PMO 汇报，不进入 AiFamily MVP 依赖图
```

### 现有队列归并

| 原队列/角色 | 新归属 | 立即职责 | 不再承担 |
|---|---|---|---|
| 团队1/家庭首达 + Route C/Journey | 家庭成长主链队 DRI | 共同完成 S1+S2 PRD 和用户闭环 | 不再按技术模块分割用户结果 |
| 团队5/多模态 AI + 顾问组 | 理解智能队 | 完成 S3 PRD、知识结构、AI交互和评测设计 | 顾问不冒充代码 owner |
| Route E-Service + Commerce/Membership 角色 | 服务价值队 DRI | 共同完成 S4+S6 PRD 和价值链 | 不把购买从家庭需要中剥离 |
| 原 Community/关系工作 | 家庭关系队 DRI | 完成 S5 受控关系 PRD 和真实内容策略 | 不创建无限流或伪造内容 |
| 团队3/Experience | Experience 共享设计队 | 参加每个场景 PRD，交用户流程、内容、视觉和状态规范 | 不以静态页面作为交付 |
| 团队2/Platform Core | 平台支援唯一队列 | Consent、Audit/Outbox、PG、幂等、UoW | 不拥有任何家庭业务结果 |
| 团队6/QA Release | QA/Release 闸门 | 同 ref clean checkout、场景回放、真实环境证据 | 不只跑单元测试报绿 |
| 小橘灯团队4 | 独立产品队列 | 自己的 Charter→Control→H-LIVE 方案 | 不阻塞/改写 AiFamily MVP |
| 现有两个 PMO/总架构监督 | 唯一 PMO | 合并为一个决策入口，维护 PRD 版本和派工板 | 不保留重复裁决口 |

任何新 Agent 只能加入现有小队，不得新建同名 Chat；同一场景只有一个 DRI，平台接口另设 owner。

## 1.1 PRD 完成闸门（先设计，后施工）

本轮四个场景队先各交一张完整 PRD 卡，由 Experience、Platform、QA 会签；四张卡和总体验收脚本齐全后，PMO 才恢复下一轮业务代码派工。

每张 PRD 卡必须包含：用户/触发/前置条件、逐步交互、用户可见结果、业务对象与状态、知识/AI边界、前后端接口、异常/拒绝/恢复、数据来源、指标、正反验收脚本、负责人和 pathspec。缺任一项即 `PRD_INCOMPLETE`。

### PRD-01 家庭成长主链

由家庭成长主链队负责，覆盖 S1 测评理解确认和 S2 计划实践复盘；必须写出同一家庭从首页到复盘的完整路径，明确 confirmed-intent receipt 如何交接。

### PRD-02 理解智能

由理解智能队负责，覆盖一个具体家庭问题的知识检索、多模态输入、AI Draft、家长/人工确认和 provenance；必须写清家长如何纠正平台的理解。

### PRD-03 服务价值

由服务价值队负责，覆盖明确需要到服务履约、反馈补救，以及会员/方案/权益选择；必须写清主动购买、取消和失败恢复。

### PRD-04 家庭关系

由家庭关系队负责，覆盖主题活动/经验内容、加入/收藏、退出/举报和审核撤回；必须写清真实内容来源和空态。

### PRD-05 体验与质量总契约

由 Experience + QA 负责，统一四张 PRD 的信息架构、视觉语言、加载/空/错误/拒绝/恢复状态、录屏脚本和发布证据格式。

## 1.1 可直接派工的任务卡

以下任务卡是本阶段唯一执行清单。任务卡未完成前，成员不得自行扩大范围；卡片完成必须交代码和场景证据。

### MVP-S1-01｜首次测评到家长确认

- **DRI**：S1 首达小队（团队1/Assessment）；Experience 指定一名 UI 配对负责人。
- **输入**：现有 Assessment application handlers、UI-02/UI-03 contract；不得假设 S1 已有真实 HTTP。
- **允许范围**：S1 owner 自己的 assessment API/application/test 文件和 UI-02/UI-03 对应文件；禁止修改 S2 Journey、Platform Core、Registry、共享台账。
- **用户路径**：家庭困扰输入 → 完成版本化测评 → 看到有依据的理解 → 家长确认或拒绝 → 重新打开仍能看到结果。
- **必须运行**：`uv run pytest tests/domains/assessment -q`；前端安装、lint、typecheck、Playwright 用户路径；若有 HTTP 则提供 curl/脚本。
- **正向证据**：确认后有可回读 `GrowthIntent`/receipt。
- **反向证据**：拒绝无 intent；401/403、过期、重复、跨家庭、后端不可用均显示可理解的恢复状态。
- **交付物**：commit、clean checkout 命令、用户截图/录屏、测试输出、剩余真实 PG/HTTP 缺口。
- **完成条件**：UI 可点击完成，后端结果不是 fixture；仅有 UI03 空态或单测不算完成。

### MVP-S2-01｜确认意图到成长复盘

- **DRI**：S2 成长循环小队（Route C/Journey）。
- **输入**：`codex/chief-bc-plan` 候选链 `937f9c5`；S1 只通过 confirmed-intent contract 交接。
- **允许范围**：`backend/domains/journey/**`、Journey 专属测试、迁移文件；禁止修改 `backend/apps/family_api/main.py`，由 Route B 接线。
- **用户路径**：确认意图 → 生成计划 → 家长确认 → 添加实践 → 记录观察/阻碍 → CONTINUE/ADJUST/PAUSE 复盘 → 新会话回读。
- **必须运行**：`uv run pytest tests/domains/journey -q`、`uv run pytest tests/scenarios/test_family_first_arrival_mvp.py -q`，以及真实 PostgreSQL 同 ref 测试。
- **正向证据**：HTTP 200、计划/实践/复盘真实持久化、同请求重放同响应。
- **反向证据**：跨家庭、未确认意图、冲突 key、重启回读失败时 fail-closed。
- **交付物**：单一 commit、迁移 upgrade→downgrade→upgrade 输出、HTTP 场景脚本和回读日志。
- **完成条件**：Route H clean checkout 可复跑；没有真实 PG/HTTP 证据只能标候选。

### MVP-CORE-01｜共享平台合同

- **DRI**：Platform Core（团队2）。
- **输入**：S1/S2 现有调用契约；不得复制 domain 内的 Consent/Audit/Outbox/幂等实现。
- **允许范围**：`backend/platform/**` 及平台专属测试；迁移需单独登记并先报 PMO。
- **用户结果**：S1/S2 的授权、撤回、tenant/family scope、审计、Outbox 和重放在真实 PG 中一致。
- **必须运行**：平台专测、消费方反向测试、真实 PG 事务回滚/重启/重复请求测试。
- **交付物**：可消费 API/ref、schema/ORM 证明、失败注入日志、owner/pathspec 声明。
- **完成条件**：至少一个 S1 或 S2 场景消费该接口并通过；平台单测本身不算完成。

### MVP-S3-01｜知识依据与 AI Draft

- **DRI**：S3 知识与 AI 小队；顾问组只提供决策卡，不冒充实现 owner。
- **输入**：S1/S2 的 evidence_refs/knowledge_refs；只选择一个家庭问题主题。
- **允许范围**：知识条目、Model Gateway adapter、专属 replay/eval 测试；禁止领域直连供应商、禁止写 canonical Fact。
- **用户路径**：家庭问题 → 看到知识依据 → 生成可编辑 Draft → 家长/人工确认、拒绝或修改 → 回读 provenance。
- **必须运行**：固定数据集 replay、引用核对、prompt injection、PII、timeout/cost/provider missing 和人工接管测试。
- **交付物**：一个知识包、一个可展示 Draft 页面/接口、eval 输出、provenance artifact、阻断项。
- **完成条件**：家长可理解依据且能拒绝；泛化聊天 Demo 不算完成。若当前无实施 owner，PMO 必须在 1 小时内指定，否则标 `MISSING_OWNER`。

### MVP-S4-01｜明确需要到服务补救

- **DRI**：S4 服务履约小队（Route E-Service）。
- **输入**：已确认家庭需要；复用现有 Service/Booking/Delivery canonical 对象。
- **允许范围**：服务场景自己的 API/application/test/UI 文件；禁止重写 Platform Core 或把测评自动转购买。
- **用户路径**：主动表达需要 → 查看服务与负责人 → 预约 → 履约 → 家长反馈 → helpful/not helpful 补救。
- **必须运行**：真实 PG/HTTP、容量冲突、取消、幂等、交付失败、人工补救和回读测试。
- **交付物**：一条可演示服务链、交付记录、反馈/补救日志、失败路径截图。
- **完成条件**：家长能知道谁交付、出了问题如何恢复；只有 booking 单测不算完成。

### MVP-S5-01｜受控家庭关系连接

- **DRI**：关系网络小队；由 PMO 从现有 Experience/Community 队列指定，不新建 Chat。
- **输入**：一个明确主题和审核规则；没有真实内容时只能使用显式 synthetic 空态。
- **允许范围**：主题活动/经验卡、收藏/加入、退出/举报的最小 UI/API/测试；禁止无限流、公开私聊、家庭排名和伪造他人发言。
- **用户路径**：选择主题 → 查看审核内容/活动 → 加入或收藏 → 退出/举报后状态可回读。
- **必须运行**：审核、撤回、越权、空态、恢复和 synthetic source 标记测试。
- **交付物**：一条可点击关系场景、真实状态来源或诚实空态、正反录屏/日志。
- **完成条件**：不能以设计稿、硬编码他人发言或页面存在计完成。

### MVP-S6-01｜明确需要到方案/权益

- **DRI**：价值转化小队；由 PMO 从现有 Commerce/Membership 队列指定，不新建 Chat。
- **输入**：S1/S2 已确认需要；复用 canonical 商品/会员/权益对象。
- **允许范围**：目录、方案比较、权益读取、购买意向、取消/反馈；测试支付必须与生产 provider 隔离。
- **用户路径**：家庭需要 → 方案比较 → 查看价格/权益 → 家长主动确认购买意向 → 取消或反馈。
- **必须运行**：目录 DTO、权益回读、重复请求、取消、退款/补救和 synthetic payment 测试。
- **交付物**：一条可点击购买意向场景、后端 DTO、状态回读、错误恢复证据。
- **完成条件**：价格不得由前端硬编码；不能从孩子画像自动推送；无后端状态只能标 `NOT_IMPLEMENTED`。

## 1.2 PMO 派工规则

PMO 每小时只收以下格式，不收“正在研究/方案已完成”式状态：

```text
Task ID:
User scenario completed:
Command and environment:
Positive path:
Negative/recovery path:
Branch/commit/clean:
Artifact:
One blocker and next command:
```

PMO 必须在每张任务卡上填入实际 DRI 和 pathspec；没有 DRI 的 S3/S5/S6 立即标 `MISSING_OWNER`，不得让团队继续空转。全量 MVP 完成率按六张卡的“代码+可运行场景+证据”计算，不按文档数量计算。

## 2. Sprint 划分

采用 5 个短 Sprint，目标是第一阶段交付 S1–S6 全量 MVP。每个 Sprint 都交“能运行的场景 + 正反证据”，而不是只交设计稿。Sprint 可并行，但依赖图不得越级；并行是加速手段，不是削减业务场景。

### Sprint 0｜场景与契约锁定（2 天）

交付：本 PRD/蓝图评审、每个场景的 API/数据/UX contract、owner/pathspec、synthetic fixture 套件、用户验收脚本。禁止无场景代码。

### Sprint 1｜S1 首达闭环（3–5 天）

交付：测评→UI03 理解→确认/拒绝→GrowthIntent；真实 HTTP、PG、Audit/Outbox、幂等、撤回/跨家庭反例；Experience 完成可运行界面。

退出：一个合成家庭可以从首页完成并重新打开看到结果。

### Sprint 2｜S2 成长循环（3–5 天）

交付：Intent→JourneyPlan→Practice→Observation/Blocker→PhaseReview；21 天计划说明、知识引用、暂停/调整/继续；新会话回读和重启证据。

退出：家长完成一次实践并做出复盘决定，全部证据可回放。

### Sprint 3｜S3 知识与 AI + S5 关系网络（3–5 天）

交付：至少一个测评主题知识包、检索/引用、AI draft、家长/人工确认、provenance、replay eval；不可用 provider 和注入反例；同时交付一个审核主题活动/经验卡的受控关系场景、收藏/加入、退出/举报路径。

退出：家长能理解依据，AI 不写 Fact，所有结果可追溯；家庭关系场景不展示伪造他人内容。

### Sprint 4｜S4 服务履约 + S6 价值转化（3–5 天）

交付：从确认需要进入服务、预约、交付、反馈、补救；至少一个真实 PG/HTTP 场景；同时交付一个产品目录/方案、权益读取、购买意向、取消/退款说明路径。

退出：家长知道买的是什么、谁交付、出了问题如何恢复。

### Sprint 5｜全量 MVP 集成与 Release（5–7 天）

交付：把 S1–S6 串成同一家庭上下文，补齐跨场景入口、状态回读、错误恢复、Release 回滚和运行观测；逐场景出用户演示脚本。

退出：六条主场景均有用户演示脚本、正反 evidence、版本化 artifact 和回滚步骤；未达标场景明确标记 `NOT_IMPLEMENTED`，不得把部分 MVP 宣称为全量 MVP。

## 3. 依赖 DAG

```text
Sprint 0 场景契约
   ├── Platform Core 合同（Consent/Audit/Outbox/Idempotency/PG）
   ├── Experience 场景壳与状态矩阵
   └── S3 知识包准备
        ↓
S1 首达 ─────→ S2 成长循环 ─────→ S4 服务承接
    ├────────→ S3 知识/AI（可并行，不能绕过 S1 receipt）
    ├────────→ S5 关系网络（可并行，必须有家庭上下文）
    └────────→ S6 价值转化（必须由明确需要触发）
                                      ↓
                              全量 MVP 集成 Release
```

小橘灯独立 DAG：`Charter/ADR → Control/read/API → QA → H-LIVE-01 → 后续能力`，不成为 S1/S2 前置。

## 4. 每小时回报格式

每个小队只回报五项：

1. `User scenario`: 本小时家庭实际完成了什么。
2. `Command`: 可复现的运行命令和环境。
3. `Positive/negative`: 正向路径、失败/拒绝/恢复路径。
4. `Artifact`: 分支、commit、可展示页面或测试录像/日志。
5. `Gap/next`: 当前缺口、下一小时一个明确动作。

“写完文档”“局部测试通过”“有分支”只能作为 supporting evidence，不能替代用户场景完成。

## 5. 质量与冲突裁决

- 每个场景一个 DRI；跨域接口一个 owner；WIP≤1。
- 独立 worktree、branch、窄 pathspec；不得 `git add -A`，不得吞并他人 WIP。
- 任何冲突先停在边界并上报 PMO，PMO 依据场景契约裁决，不允许静默复制实现。
- synthetic/fake 只能替换外部依赖，不能替换业务事实；进入主线前必须有真实 HTTP/PG 证据。
- 生产放行仍需完整人工评审、回滚方案和正反 evidence；本计划不把测试环境绿灯写成生产许可。
