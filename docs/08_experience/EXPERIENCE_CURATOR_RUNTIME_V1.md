---
id: EXPERIENCE-CURATOR-001
title: Experience Curator 两阶段运行契约 V1
type: specification
status: draft
version: 0.1
owner: ai-runtime
canonical: false
---

# Experience Curator 两阶段运行契约 V1

## 运行链路

```text
候选召回（内容/行动/服务候选）
  → candidate_id 去重
  → scope / locale / consent / purpose 校验
  → 资格与频控
  → 未成年人商业闸门
  → 稳定交付顺序
  → RecommendationDecision(PROPOSED)
  → ExperienceGateway
```

这条链路借鉴大型内容产品的“候选集合 + 策略准入”分层经验，但优化目标限定为家庭
理解、成长采纳、服务质量和退出安全，不优化停留时长、消费金额、家庭比较或儿童画像。

## 当前实现

- `ExperienceCandidate`：候选引用及其 scope、语言、交付优先级、资格和频控信息；
- `RecommendationCurator`：确定性去重、策略过滤和决定生成；
- `ExperienceGateway`：幂等追加、目标绑定和精确时间线读取。

当前使用内存适配器。生产接入应保持相同输入输出契约，再替换候选目录、区域事件流、
频控存储、实验分流和 Projection Worker；不得通过测试环境删除商业闸门、人工闸门或审计。
