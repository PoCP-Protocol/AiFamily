---
id: ADR-0159
title: 将24节课程纳入服务产品设计平台
status: Proposed
date: 2026-09-08
---

# 决策

24节课程不作为独立的课程商城对象，而作为服务产品（Service Product）的内容交付模块。服务产品由市场洞察和家庭需求触发，课程体系负责提供可复用的学习与行动内容，服务蓝图负责定义真人/AI交付、节奏、SLA和结果确认。

## 统一产品链

```text
Market Evidence
  -> Demand Frame / Family Need
  -> Product Package Version
  -> Course System Version (6 stages / 24 lessons)
  -> Course Content Version
  -> Courseware BOM (PPT / worksheet / image / video / audio / document / skill)
  -> Service Blueprint (AI + human tasks)
  -> Human Gate / Release
  -> Journey Delivery (21 or 90 days)
  -> Outcome Evidence / Product Improvement
```

## 24节课的结构

| 阶段 | 课次 | 产品交付结果 | 典型服务动作 |
|---|---:|---|---|
| 家庭觉察 | 1-4 | 家庭问题地图 | AI引导访谈、需求澄清 |
| 关系连接 | 5-8 | 沟通与关系行动卡 | 家长练习、必要时真人辅导 |
| 成长目标 | 9-12 | 家庭成长目标树 | 目标共创、计划确认 |
| 日常行动 | 13-16 | 21天行动计划 | 每日行动、AI陪伴、异常升级 |
| 能力进阶 | 17-20 | 90天成长路径 | 阶段复盘、专家/管家协同 |
| 复盘共创 | 21-24 | 复盘报告与下一周期需求 | 结果确认、产品改进候选 |

## 每节课的最小主数据

每个 lesson 必须包含：

- `need_evidence_refs`：需求或市场证据引用；
- `stage_id` 与 `product_outcome`：所属阶段及阶段结果；
- `knowledge_point`、`action_task`：知识与家庭可执行行动；
- `service_task_refs`：对应 AI/真人服务任务；
- `courseware_bom_ref`：课件资产及版本血缘；
- `safety/rights/accuracy`：安全、版权、事实准确性状态；
- `measurement_refs`：只记录行动和结果证据，不生成家庭总分或家庭排名。

## 生成与发布规则

AI 可以基于已准入证据生成课程大纲、课件候选、练习和多模态草稿；AI 输出必须保留 provenance，不能直接写入家庭事实。课程内容、课件版权/安全、服务蓝图和面向家庭的高影响动作都经过人工闸门后才能发布。已发布版本不可原地修改，只能创建新版本。

## 分期实施

1. **P0：课程主链**：固定6阶段/24课次、ProductPackage 引用、课程内容草案、课件BOM和发布闸门；先支持文本、PPT、工作纸。
2. **P1：服务交付编排**：将每节课映射到21天/90天 Journey 的行动、AI Coach、管家和专家升级条件，沉淀结果证据。
3. **P2：多模态工厂**：接入成熟 Model Gateway 生成图片、音频、视频、短剧草稿，统一资产版权和安全审查。
4. **P3：闭环优化**：从完成、反馈、复盘和服务结果形成 Product Intelligence 的改进候选，驱动下一版课程和服务产品。

## 非目标

课程完成率不是家庭价值的唯一指标；平台不生成家庭总分、不做家庭排名，不允许 AI 自动把推断写成事实。
