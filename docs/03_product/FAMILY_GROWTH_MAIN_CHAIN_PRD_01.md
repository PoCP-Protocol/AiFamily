---
id: PRD-FAMILY-GROWTH-MAIN-CHAIN-001
title: AiFamily 家庭成长主链 PRD-01
type: product
status: review-draft
version: 1.0
owner: family-assessment-s01
created: 2026-08-31
canonical: false
evidence_basis: d7b65b8
---

# AiFamily 家庭成长主链 PRD-01

## 0. 目的与范围

本 PRD 定义一个家庭可以完成的连续结果：同一家庭首页进入真实困扰，完成最小测评，看见带依据的家庭理解，由授权成人确认或拒绝，确认后进入家庭计划，实践一小步，记录观察并复盘。

本文件是执行契约草案，不代表真实生产能力已经存在。当前已验证的是 `d7b65b8` 的 S1 UI receipt 窄交付及 assessment 局部测试；真实身份、授权、PG、审计和重启回读仍是独立环境门。

非目标：家庭总分/排名、儿童诊断或公开画像、AI 自动确认、自动派单、商业决策、无授权公开互动、把 AI draft 写入 Fact/GrowthProfile/Outcome。

## 1. 用户结果与角色

用户结果：家长能说清一件家庭小事，判断“这份理解像不像我们家”，确认后得到一份可回看的家庭关注，并自主决定是否进入计划。

- 授权成人：唯一可以确认/拒绝理解、确认计划、记录实践和复盘的人。
- 儿童：家庭成长的受益对象，不是授权人、营销主体或公开互动主体。
- AI/知识服务：提供带知识引用和 provenance 的解释草案；不能确认、诊断或改变业务状态。
- Platform Core：提供 Identity、Consent、tenant/family scope、Audit、Outbox、Deletion、幂等和数据库事务；不拥有用户结果。
- S1 首达小队：对“理解并确认重点”负责。
- S2 Journey 小队：对“计划、实践、观察、复盘”负责；只消费 S1 receipt。

## 2. 主链与状态

```text
HOME
  → EXPRESSION_DRAFT
  → ASSESSMENT_IN_PROGRESS
  → ASSESSMENT_SUBMITTED
  → PERSPECTIVE_DRAFT
  → HUMAN_DECISION
      ├─ DISMISSED → STOPPED / 可修改后重试
      └─ CONFIRMED → CONFIRMED_INTENT_RECEIPT
                         → PLAN_DRAFT
                         → PLAN_CONFIRMED
                         → PRACTICE_IN_PROGRESS
                         → OBSERVATION_RECORDED
                         → PHASE_REVIEWED
```

状态只表示本场景可回读的业务事实。`loading/saving/error/retry` 是界面传输状态，不得被当作业务成功。任何状态转换都需要 actor、family scope、Consent（如适用）、request/correlation/idempotency key 和可回放 receipt。

## 3. 逐屏交互契约

### UI-01｜同一家庭首页

首屏只呈现“我想先理清家里最近的一件事”，不展示 tenant、scope、技术状态或家庭排名。已认证成人进入后，后台解析 canonical Identity 与当前 family context；无可用家庭时显示空态和安全退出。

关键动作：进入 S1、查看未完成草稿、恢复上次未完成测评。

失败恢复：session 过期要求重新认证；family context 不匹配停止并显示“暂时不能打开这个家庭空间”；网络失败可重试，不创建测评。

### UI-02｜困扰表达与最小测评

1. 先问：“你现在最想解决什么？”成人可文字表达，也可在 sandbox 中使用语音转写；语音不是生产前置条件。
2. 用一句白话确认：“我听到你最近最想理清的是……”，成人可以修改。
3. 在开始保存家庭相关内容前，展示一次白话用途说明：“只用于这次家庭理解和后续回看；仅限你的家庭，你可以随时撤回。”由成人明确同意；Consent 由 canonical contract 产生，不在 UI 复制。
4. 选择一个最相关主题，完成 3 题最小题集。每题说明为什么问；允许跳过、返回、保存、退出和恢复。
5. 提交后只生成 assessment evidence/result projection；不生成 GrowthIntent，不创建计划，不写 canonical Fact。

页面状态：首次进入、loading、空态、题集加载失败、保存失败、Consent 缺失/撤回、提交重复、提交成功、退出恢复。

成功理解断言：成人能复述“我说了什么、平台依据什么、还不知道什么”，且不需要看到分数或诊断词。

### UI-03｜家庭理解与知识依据

结果先展示四件事：

- 我们听到的家庭关注：直接连接成人的原话与已提交回答。
- 可能的方向：确定性规则和知识卡组织出的可讨论草案。
- 还不确定的地方：明确未回答、未观察和不能推断的部分。
- 今天可以尝试的一小步：仅作为家庭可选建议，不自动启动行动。

AI 若被调用，必须经 `backend/intelligence/model_gateway`，输出 Draft，携带 provider/model/model_version/prompt_version/context_snapshot_ref/provenance_refs，且 `may_mutate_business_state=false`。AI 不得成为总分、诊断、确认人或事实写入者。

成人动作：确认这份理解、暂不采用、补充一句、返回修改、保存、退出。确认前不显示进入计划的可用动作。

### UI-03A｜确认/拒绝与 receipt

确认请求只提交第一条 hypothesis 的引用和 assessment session；服务端验证 actor、tenant/family scope、有效 Consent、证据存在和幂等键。成功必须返回并展示：

```json
{
  "action": "CONFIRM_GROWTH_HYPOTHESIS",
  "outcome": "INTENT_CREATED",
  "hypothesis_ref": "...",
  "intent": {
    "intent_id": "...",
    "boundary": "HUMAN_CONFIRMED_INTENT_NOT_OUTCOME"
  },
  "replayed": false
}
```

该 `confirmed intent receipt` 是 S1→S2 唯一交接凭据。S2 只消费 receipt/公开 contract，不读取 S1 内部表。相同 idempotency key 与相同请求体必须返回同一业务 receipt，并标记 `replayed=true`；同 key 不同请求体必须拒绝。

拒绝返回 `outcome=NO_ACTION`、`intent=null`，不得创建计划、行动、推荐或商业状态。撤回/过期/跨家庭/无权限均 fail-closed；receipt 不得在门禁失败时产生。

### UI-04｜计划

仅当 UI-03 已获得 confirmed intent receipt，才允许读取或创建计划草案。计划必须说明目标来自哪条已确认 intent、引用哪些证据、分为哪些阶段；首次确认计划仍由成人完成。

计划确认交接给实践阶段的 receipt 至少包含 `plan_id/intent_id/plan_version/status/actor/family_id/replayed`。S1 不实现或复制 Journey plan confirm/readback/phase-review。

### UI-05｜实践、观察、复盘

计划确认后，成人选择一小步并可暂停。实践记录描述发生了什么，不推断儿童状态，不生成医疗/心理结论。成人可记录“帮助了/没变化/没尝试”和一句观察；到期后可选择 CONTINUE、ADJUST、PAUSE 或 HUMAN_REVIEW_REQUIRED。复盘 receipt 交给 Journey canonical contract，不能由 S1 本地拼装。

## 4. Receipt 交接与对象边界

| 交接 | 生产拥有者 | 消费者 | 最小内容 | 禁止 |
|---|---|---|---|---|
| Identity → S1 | Platform Core | S1 | actor、tenant、family、membership、role、session | S1 复制身份表 |
| Consent → assessment | Platform Consent | assessment | purpose、subject、status、effective window、version | 本地 Consent 语义 |
| assessment → UI-03 | Assessment | UI-03 | immutable evidence、projection、tool/version、source refs | 把 projection 当 Fact |
| UI-03 CONFIRM → S2 | Assessment/GrowthIntent owner | Journey | `confirmed intent receipt`、intent、evidence refs、boundary、replayed | AI 自动确认、Outcome |
| S2 plan → practice | Journey | practice/review | plan receipt、version、phase、scope | S1 复制 Journey 状态 |
| 任一写入 → audit/outbox | Platform Core | compliance/deletion | correlation、idempotency、actor、scope、event | 本地第二审计/事件总线 |

## 5. HTTP contract 摘要

S1 消费或调用的 canonical 路径：

- `GET /families/{familyId}/ui/01/home`
- `GET /families/{familyId}/ui/02/assessment`
- `POST /families/{familyId}/assessments/sessions`
- `POST /families/{familyId}/assessments/sessions/{sessionId}/responses`
- `POST /families/{familyId}/assessments/sessions/{sessionId}/submit`
- `GET /families/{familyId}/assessments/results/latest`
- `GET /families/{familyId}/ui/03/growth-hypothesis`
- `POST /families/{familyId}/growth-hypotheses/decisions`

所有 mutation 要求 bearer session、`idempotency-key`、`x-correlation-id` 和 `x-source`；响应必须能区分新建与 replay。API 错误至少映射：未授权、跨家庭、Consent 缺失/撤回、找不到 session、版本冲突、重复 key、provider 不可用和数据库不可用。

S2 contract（plan confirm/readback/phase-review）属于 Journey owner；本 PRD 只定义交接，不新增 endpoint 或数据库表。

## 6. 指标与保护指标

业务结果：

- `S1_completion_rate`：进入 S1 的授权成人中完成最小测评并看到理解的比例。
- `perspective_confirmation_rate`：看到 UI-03 后确认或拒绝的比例，分母和拒绝必须同时报告。
- `confirmed_intent_readback_rate`：确认后在新会话可回读同一 intent receipt 的比例。
- `S2_start_rate`：confirmed intent 中成人主动打开计划的比例；不得以自动跳转计数。
- `practice_observation_rate`：计划确认后至少有一条成人观察记录的比例。

理解与安全：

- `comprehension_pass_rate`：用户能指出“依据/未知/可修改”三项的比例。
- `dismissal_without_side_effect_rate`：拒绝后无 plan/action/commerce mutation 的比例，应为 100%。
- `scope_denial_rate`：跨家庭请求被拒绝的比例，应为 100%。
- `consent_revoke_block_rate`：撤回后读取和写入被阻断的比例，应为 100%。
- `ai_canonical_mutation_count`：AI 直接写 Fact/GrowthProfile/Plan/Outcome 次数，应为 0。
- `duplicate_side_effect_rate`：幂等 replay 产生重复业务副作用的比例，应为 0。

所有指标按 synthetic/dev/test 与真实环境分开；局部 PASS、expected-red 和未配置环境不得合并进生产分母。

## 7. 验收脚本

### 正向脚本 P1｜同一家庭完成 S1→S2 入口

1. 成人登录并进入自己的家庭首页。
2. 输入“最近晚饭后总因为作业安排起冲突”，修改系统确认句并同意白话用途说明。
3. 完成 3 题，提交一次；刷新 UI-03，看到关注、可能方向、知识依据和未知项。
4. 点击“确认这份理解”，断言返回 `INTENT_CREATED`、`intent_id`、边界为 `HUMAN_CONFIRMED_INTENT_NOT_OUTCOME`。
5. 重新打开页面，断言同一家庭可回读 intent；进入计划必须由成人主动点击。

### 反向脚本 N1｜撤回 Consent

1. 成人完成测评但撤回用于家庭理解的 Consent。
2. 读取 UI-03 或提交 CONFIRM。
3. 断言返回 Consent blocked；页面给出安全说明与退出/重新授权入口；不产生 intent、plan 或 outbox side effect。

### 反向脚本 N2｜跨家庭与重复请求

1. 有效成人 session 请求另一个 familyId。
2. 断言 403 scope denial，不泄露结果。
3. 对同一 CONFIRM 请求重放相同 idempotency key，断言同一 receipt 且 `replayed=true`。
4. 使用同 key 改写 hypothesis 或 family，断言冲突并保持单一 intent。

### 反向脚本 N3｜AI/数据库/网络失败与恢复

1. provider timeout 或知识引用不可用时，断言只产生 blocked/failed draft，不产生确认 receipt；确定性解释仍可显示或安全退出。
2. 提交或读取网络失败时，页面显示明确重试；重试不重复创建 session、evidence、intent 或 plan。
3. 退出 UI-02 后重新进入，断言未完成回答可恢复；放弃草稿不会伪造完成。

## 8. 当前证据与交付门

已存在：`d7b65b8` 在 UI-03 捕获并展示 confirmed intent receipt；UI-03 专测 6 passed；assessment route/flow 25 passed；TypeScript 与 diff check PASS。

当前未完成：真实 connected session 的成人操作、Consent read-time revoke、PG assessment/result、Audit/Outbox 事务、幂等重启回读、跨家庭负测、S2 plan confirm/readback/phase-review 真实 HTTP/PG，以及持久化截图/录屏 artifact。

因此本 PRD 的状态为 review-draft；只有 P1 与 N1/N2/N3 在真实环境通过并有五层证据（用户动作、UI/API、业务 receipt、持久化/审计、回放/恢复）后，才可标记 S1→S2 主链验收通过。
