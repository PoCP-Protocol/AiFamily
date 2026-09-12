---
id: STRATEGY-AGI-HUMAN-DEVELOPMENT-001
title: AGI 时代 Human Development 与 Family Intelligence 战略方向
type: strategy
status: current
version: 1.0
owner: strategy
created: 2026-09-11
updated: 2026-09-11
canonical: true
---

# AGI 时代 Human Development 与 Family Intelligence 战略方向

## 定位

本文件是长期战略方向，观察周期为 10–20 年。它定义 AiFamily 要解决的问题与能力演进方向，不描述当前已经交付的产品能力。当前事实以 [`CURRENT_SYSTEM_BASELINE.md`](../00_system/CURRENT_SYSTEM_BASELINE.md) 为准，建设顺序以已接受 ADR 与对应 PR 为准。

AiFamily 的长期坐标从“AI 家教、AI 课程、AI 作业辅导”上移到：

> 在 AGI 时代，帮助孩子成长、帮助家庭成为更好的成长环境，并让社会资源更有效地围绕家庭工作。

教育是高频、长期且关系密集的切入口；终局是 **Human Development × Family Intelligence × Social Resource Network**。

## 第一性变化

AGI 使解释、检索、练习、翻译和个性化反馈趋向丰富，稀缺性转向动机、自主学习、判断 AI、创造、合作、韧性、关系、真实世界经验和长期方向。因此产品价值从“传递知识”转向“支持人的发展”。

长期目标是形成 **Human Development Model**，逐步理解认知、学习能力、好奇心、自主性、创造力、批判性思维、情绪与关系能力、合作、执行、身体状态、兴趣、优势、价值观以及 AI 协作能力。该模型是目标态；不能把它写入当前事实或当作诊断、排名、家庭总分。

## 家庭是变化单位

孩子仍是中心，但家庭是系统单位，社会是资源网络。Family World Model 的目标不是建立第二个 FamilyNeed，而是围绕现有 canonical FamilyNeed，形成理解、目标、计划、技能、行动、结果、反思与重新规划的连续链：

```text
Family World Model → Goal → Plan → Skill → Action → Outcome → Reflection → Replan
```

任何 AI 输出保持 draft/proposal 边界；事实、结果、服务履约和人类决定必须由相应领域流程确认。

## 三类长期智能

| 长期能力 | 核心问题 | 目标态组成 |
|---|---|---|
| Family Brain | 这个家庭现在需要什么？ | World Model、Need、Goal、Plan、Outcome |
| Society Brain | 什么社会资源适合帮助它？ | Resource Graph、教师、专家、学校、服务 |
| Evolution Brain | 什么方法在什么条件下有效？ | Outcome Learning、Evaluation、Capability Gap、Evolution |

这是能力分工，不是要求建立三套独立 Runtime。执行、账本、授权与审计必须继续遵守既有边界和 R2 收敛原则。

## Family Foresight Engine

长期产品演进需要持续观察七类信号：AI 能力、教育制度、儿童发展、家庭变化、劳动力市场、政策和资源供给。目标工作流是：

```text
Signal → Trend → Implication → Family Need Hypothesis
       → Capability / Skill Hypothesis → Small Experiment
       → Outcome → Scale / Kill
```

Foresight 输出是研究与产品假设，不能自动成为 FamilyNeed、DomainFact、Outcome 或产品决策。进入正式建设前必须经过 ADR、治理登记、人工审查和真实证据。

## 资源网络与 AI Parenting

AiFamily 不以替代教师为目标。AI 适合理解、分析、准备、个性化、跟踪和重复辅导；教师、家长及其他专业人员保留关系、判断、启发、真实互动、价值引导和专业干预责任。

长期需要支持家庭建立 AI 使用规则、隐私边界、独立思考规则、依赖识别和数字生活协议。这些是目标能力，不代表当前已存在 Family AI Guardian 产品。

## Outcome Intelligence

长期护城河不是未治理的用户资料，而是在合法授权、去标识化、最小化和治理前提下，逐步理解：什么方法，对什么类型的问题，在什么条件下，更可能产生什么结果。目标关系为：

```text
Family Pattern × Need × Context × Intervention × Resource × Duration × Outcome
```

任何 Outcome Intelligence 建设必须区分观察、推断、建议、事实和结果；不得将模型相关性描述为因果，不得以聚合数据反推个体身份。

## 产品演进坐标

长期 Child & Family Growth Stack：

```text
Understand Me → Help Me Grow → Help My Family
              → Connect The Right People → Learn What Works
```

技术路线仍按既有蓝图推进：R2 统一智能内核，R3 Family World Model，R4 目标与动态规划，R5 将课程、专家和服务转为可组合 Skill；R6–R8 再逐步建设 Outcome Learning 与平台演进。路线图不授权跳过 R0、R2 前置条件，也不授权当前新增 World Model、Planner 或 Skill Runtime。

## 战略护栏

1. Family 是变化单位；不得退化为单一学生评分产品。
2. Human Development 是理解与支持范围；不得升级为诊断、排名或家庭总分。
3. FamilyNeed、Goal、Outcome 等语义各有 canonical owner；不得复制第二套聚合或账本。
4. AI 输出只能形成 draft、proposal 或 evidence；不得自动写入事实、结果、履约或人类决定。
5. 需要模型执行时走统一 AgentRuntime/ModelGateway；不得按能力继续增加平行 Runtime。
6. 教师、家长、专家和学校是受治理的人类能力与资源，不是可任意替代的商品接口。
7. 研究信号先形成假设，再以小实验、真实结果和人工审查决定是否扩大。

## 当前状态边界

本战略确认方向，不宣称以下能力已经存在：Human Development Model、Family Foresight Engine、Family/Society/Evolution Brain、Family AI Guardian、Outcome Intelligence、完整 Resource Graph 或跨生命周期 Growth Stack。它们必须分别进入后续 ADR、registry、实现分支和验证证据。

