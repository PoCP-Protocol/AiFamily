---
id: ADR-0031
title: Experience Gateway 作为 34 个 UI 的统一体验应用边界
status: proposed
date: 2026-08-30
owner: chief-architect
---

# ADR-0031：Experience Gateway 作为统一体验应用边界

## 背景

34 个 UI 需要共享入口、推荐决定和反馈闭环。若每个页面各自记录埋点或直接调用
AI/业务域，会出现事件语义不一致、重复写入、跨家庭串读，以及把 AI 建议误当成业务事实。
现有 `ExperienceEvent`、`RecommendationDecision`、`FeedbackSignal` 已冻结契约，但尚未
形成应用层的统一接入点。

## 决策

1. 在 `backend/intelligence/experience/gateway.py` 提供 `ExperienceGateway`，作为
   ExperienceApplication 的最小运行边界，统一接收三类不可变体验记录。
2. 写入按租户作用域的 `IdempotencyKey` 去重；同键同记录返回原记录，同键不同记录直接拒绝。
3. 反馈只能绑定 Gateway 已接收、同租户、同家庭、同主体集合、同用途且同类型的事件或推荐
   决定；未注册的 `ActionProposal` 不得伪造为可反馈目标。
4. 时间线读取必须精确匹配 `tenant_id`、`region_id`、`family_id`、`subject_ids`、`purpose`
   和 `consent_version`，不做跨租户、跨区域或跨主体 join。
5. Gateway 只保存体验信号和建议，不拥有 Family/Journey/Service/Commerce 事实；确认后的
   领域写入仍由对应 Named Action、授权、同意、事务、审计和 Outbox 流程负责。
6. 当前实现使用内存存储作为 dev/test 合同适配器；持久化事件流、Projection Worker、
   ExperienceApplication 的内容发现/频控/商业闸门模块通过同一接口替换，不改变 UI 契约。

## 与五层架构对齐

- **业务架构**：体验记录服务 N0-N8 的交互证据，不替代 FamilyNeed、Journey、ServiceCase
  或 Commerce 事实。
- **流程架构**：对应“触达 → 候选 → 展示 → 反馈 → 下一次体验”闭环，并为 E0-E4 情绪到
  经济闸门保留可审计输入。
- **数据架构**：沿用统一 scope、provenance、deletion_ref 和幂等边界；事件是追加记录，
  时间线是读取投影，不创建跨租户特征。
- **应用架构**：Gateway 属于 ExperienceApplication/SharedApplicationKernel 的 A6
  运行组件；后续接入 identity、authorization、consent、transaction、audit、outbox
  适配器，34 个 UI 只通过语义用例调用。
- **AI 技术架构**：Gateway 不调用模型供应商；模型调用仍只能经 Context Broker、Principal
  和 `backend/intelligence/model_gateway`，输出维持 Draft/Recommendation 边界。

## 验收证据

- `tests/intelligence/experience/test_gateway.py`
- `tests/intelligence/experience/test_contracts.py`
- `tests/intelligence/experience/test_memory_adapter.py`

当前状态为 `proposed`：内存实现已可用于合同测试，不能据此宣称持久化生产事件流或生产推荐
能力已经上线。
