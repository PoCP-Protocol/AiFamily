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

## 1. 组织重组：场景小队负责结果，平台小队负责能力

### 总体结构

```text
总架构师/总设计师/项目经理
              │
              └── 唯一 PMO：排程、冲突裁决、证据板、每小时回报
                    ├── S1 首达小队：测评→理解→确认
                    ├── S2 成长循环小队：计划→实践→复盘
                    ├── S3 知识与 AI 小队：知识→Draft→Provenance→Human Gate
                    ├── S4 服务履约小队：需求→预约→交付→反馈/补救
                    ├── S5 关系网络小队：主题活动→受控互助
                    ├── S6 价值转化小队：会员→方案→权益/购买
                    └── 平台支援：Platform Core、Experience、QA/Release

小橘灯：独立产品队列，单独向 PMO 汇报，不进入 AiFamily MVP 依赖图
```

### 现有队列归并

| 原队列/角色 | 新归属 | 立即职责 | 不再承担 |
|---|---|---|---|
| 团队1/家庭首达 | S1 首达小队 DRI | 完成 S1 UI+HTTP+真实数据场景 | 不再只写架构说明 |
| Route C/Journey | S2 成长循环小队 DRI | 消费 S1 receipt，完成 S2 用户链 | 不单独以 service PASS 结案 |
| 团队5/多模态 AI + 顾问组 | S3 知识与 AI 小队 | 知识引用、AI draft、评测和产品文案研究 | 不产生无场景的泛化 demo |
| Route E-Service | S4 服务履约小队 DRI | 预约、履约、反馈、补救场景 | 不吞并 S1/S2 业务事实 |
| 团队3/Experience | 全部场景 Experience 支援，指定 S1 主设计师 | 把场景做成可用 UI，真实状态/文案/视觉 | 不以静态页面作为交付 |
| 团队2/Platform Core | 平台支援唯一队列 | Consent、Audit/Outbox、PG、幂等、UoW | 不拥有任何家庭业务结果 |
| 团队6/QA Release | QA/Release 闸门 | 同 ref clean checkout、场景回放、真实环境证据 | 不只跑单元测试报绿 |
| 小橘灯团队4 | 独立产品队列 | 自己的 Charter→Control→H-LIVE 方案 | 不阻塞/改写 AiFamily MVP |
| PMO/总架构监督 | 合并为唯一 PMO | 每小时调度、冲突裁决、统一状态 | 不创建第二 PMO 或重复队列 |

任何新 Agent 只能加入现有小队，不得新建同名 Chat；同一场景只有一个 DRI，平台接口另设 owner。

## 2. Sprint 划分

采用 6 个短 Sprint，每个 Sprint 都交“能运行的场景 + 正反证据”，而不是只交设计稿。Sprint 可并行，但依赖图不得越级。

### Sprint 0｜场景与契约锁定（2 天）

交付：本 PRD/蓝图评审、每个场景的 API/数据/UX contract、owner/pathspec、synthetic fixture 套件、用户验收脚本。禁止无场景代码。

### Sprint 1｜S1 首达闭环（3–5 天）

交付：测评→UI03 理解→确认/拒绝→GrowthIntent；真实 HTTP、PG、Audit/Outbox、幂等、撤回/跨家庭反例；Experience 完成可运行界面。

退出：一个合成家庭可以从首页完成并重新打开看到结果。

### Sprint 2｜S2 成长循环（3–5 天）

交付：Intent→JourneyPlan→Practice→Observation/Blocker→PhaseReview；21 天计划说明、知识引用、暂停/调整/继续；新会话回读和重启证据。

退出：家长完成一次实践并做出复盘决定，全部证据可回放。

### Sprint 3｜S3 知识与 AI（3–5 天）

交付：至少一个测评主题知识包、检索/引用、AI draft、家长/人工确认、provenance、replay eval；不可用 provider 和注入反例。

退出：家长能理解依据，AI 不写 Fact，所有结果可追溯。

### Sprint 4｜S4 服务履约（3–5 天）

交付：从确认需要进入服务、预约、交付、反馈、补救；至少一个真实 PG/HTTP 场景。

退出：家长知道买的是什么、谁交付、出了问题如何恢复。

### Sprint 5｜S5/S6 最小扩展与 MVP Release（5–7 天）

交付：受控关系网络、目录/会员/购买意向的最小闭环；与 S1/S2 统一家庭上下文；Release 回滚和运行观测。

退出：五条主场景均有用户演示脚本、正反 evidence、版本化 artifact 和回滚步骤；未达标场景明确降级为空态/人工入口，不伪造能力。

## 3. 依赖 DAG

```text
Sprint 0 场景契约
   ├── Platform Core 合同（Consent/Audit/Outbox/Idempotency/PG）
   ├── Experience 场景壳与状态矩阵
   └── S3 知识包准备
        ↓
S1 首达 ─────→ S2 成长循环 ─────→ S4 服务承接
    └────────→ S3 知识/AI（可并行，不能绕过 S1 receipt）
                                      ↓
                              S5/S6 扩展与 Release
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
