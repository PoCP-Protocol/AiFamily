---
id: ADR-0036
title: 游戏化成就只由家庭行动证据触发
status: proposed
date: 2026-08-30
owner: chief-architect
---

# ADR-0036：游戏化成就只由家庭行动证据触发

## 背景

平台要借鉴大型内容产品的即时反馈和持续回访体验，但 AiFamily 的游戏化必须让家庭获得
“我们完成了一步”的成就感，不能把家庭或孩子变成被比较、被评级的对象。仓库已有
`backend/packages/contracts/gamification.py` 的允许/禁止模式清单；本决定补齐事件驱动的
运行投影。

## 决策

1. `AchievementEngine` 只消费 `ExperienceEvent`，由真实的行动完成、暂停后重新开始和主动
   表达服务需要触发成就；每枚成就必须带 `evidence_refs`、provenance 和租户/家庭 scope。
2. `InMemoryAchievementProjection` 只保存家庭自己的成就时间线；同一成就重放幂等，跨租户、
   区域、主体、用途或同意版本不共享。
3. 成就文案表达过程和关系（第一步、按自己的节奏回来、把需要说出来），不表达能力等级、
   家庭价值、结果保证或社会比较；暂停不会产生连胜中断惩罚。
4. 成就不会自动开通订单、会员、服务或其他业务事实；后续奖励如涉及权益，必须由相应域的
   Named Action 和审计承接。

## 架构对齐

- **业务/流程**：成就是 N5/N7 过程证据和情绪反馈，不替代 Outcome、QualityDecision 或
  商业确认。
- **数据**：事件 → 成就投影为派生关系，保留证据引用和删除边界，不计算家庭总分。
- **应用**：属于 ExperienceApplication 的游戏化投影，服务 UI-04/05/09/10/11/28/31，
  与 Journey/loyalty_points 通过事件和 Query Port 交互，不共享 ORM。
- **技术**：可接入 Outbox/Projection Worker 和 Feature/Experiment 管线；模型不直接生成或
  确认成就，AI 只能提出草案。

## 验收证据

- `backend/intelligence/experience/achievement.py`
- `tests/intelligence/experience/test_achievement.py`
- `backend/packages/contracts/gamification.py`

当前状态为 `proposed`，内存投影用于 dev/test 合同验证，尚未宣称生产成就服务或权益发放已上线。
