---
id: ADR-0032
title: 体验推荐采用召回与策略准入两阶段
status: proposed
date: 2026-08-30
owner: chief-architect
---

# ADR-0032：体验推荐采用召回与策略准入两阶段

## 背景

平台希望借鉴字节系产品在内容发现、反馈闭环和快速迭代上的工程经验，但 AiFamily
不能把家庭或儿童变成可比较的对象，也不能用停留时长、消费金额或脆弱情绪驱动分发。
现有 `RecommendationDecision` 已要求候选集、策略版本和解释字段，下一步需要一个可测试
的候选处理入口。

## 决策

1. 在 `backend/intelligence/experience/curation.py` 使用两阶段流程：先接收候选集合并按
   `candidate_id` 去重，再执行 scope、用途、语言、资格、频控和未成年人商业闸门。
2. 通过 `delivery_priority` 和稳定的 `candidate_id` 产生确定性顺序；该顺序只描述当前
   内容/行动的交付顺序，不是家庭、孩子或主体排名，也不写入分数。
3. 只将同一租户、区域、家庭、主体集合、用途和同意版本的候选送入
   `RecommendationDecision`，过滤原因以非敏感 reason code 记录。
4. `RecommendationCurator` 只经 `ExperienceGateway` 发布 `PROPOSED` 决定，不调用模型、
   不写领域事实；未来模型召回仍必须经 Principal/Context/Model Gateway，最终准入策略不
   被模型绕过。
5. 频控由 `cooldown_until` 表达，家庭可以通过反馈降低频率、暂停或清空推荐；不采用连续
   签到、倒计时、随机奖励等压力机制。

## 与五层架构对齐

- **业务**：候选服务 N1-N4 的内容/行动建议，不构成 FamilyNeed、Journey、Service 或
  Commerce 事实。
- **流程**：触达 → 候选召回 → 策略准入 → 展示 → 反馈，允许在 E0-E4 闸门前停止。
- **数据**：候选 scope 与 RecommendationDecision 共用租户/区域/主体/用途/同意边界；
  决定保留策略版本和过滤原因，可重放且不产生家庭总分。
- **应用**：Curator 是 ExperienceApplication 的 A3/A6 组件，Gateway 是共享追加/查询
  边界；持久化 Outbox、Projection Worker 和实验分流可在接口后替换。
- **AI**：Curator 不等于 Agent，不拥有模型供应商连接；模型只提供候选草案，审计、策略
  和人工/家庭确认仍在平台内核及业务 Named Action 内完成。

## 验收证据

- `tests/intelligence/experience/test_curation.py`
- `tests/intelligence/experience/test_gateway.py`
- `tests/intelligence/experience/test_contracts.py`

当前状态为 `proposed`。内存候选和策略适配器用于 dev/test 合同验证，不能宣称已经具备
生产级在线推荐、实验平台或跨区域事件流。
