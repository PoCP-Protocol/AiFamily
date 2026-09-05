---
id: ADR-0071
title: Unified AI telemetry span boundary
status: Accepted
date: 2026-08-30
owners: [ai-architecture]
---

# ADR-0071：统一 AI Telemetry Span 边界

## Context

Model Attempt、SafetyDecision、AgentRun/Trace 和体验运行记录分别能证明局部
状态，但没有一个统一的 trace/span 语义。直接在各个业务域接入供应商 SDK
会造成重复埋点、敏感数据泄露和测试/生产行为漂移。

## Decision

新增 `backend/intelligence/observability` 作为 AI Runtime 唯一的 span 接缝：

- `TelemetryContext` 贯穿 trace、request、session、tenant/family、use case 与
  data class；主体和请求范围在构造时转为稳定 opaque ref；
- `TelemetrySink` 只接受低基数 allowlist 属性，拒绝 prompt、payload、output、
  media、凭据和自由文本；
- `SqlAlchemyTelemetrySink` 将 span 生命周期写入 `ai_telemetry_spans`（0021），
  `(trace_id, operation_id, name)` 保证重放幂等，事务由组合根提交；
- Model Gateway 包住安全检查、准入、provider 外呼、结构校验与输出安全，生产
  Agent/Experience 组合根必须注入 durable sink；telemetry 故障不掩盖模型/策略结果。

该契约是 OpenTelemetry 的 provider-neutral 适配层；`OpenTelemetrySpanSink`
与 `CompositeTelemetrySink` 已提供 SDK/exporter 桥接，collector、监控后端和
retention/deletion worker 在部署阶段配置，不改变业务域边界。

## Consequences

- 测试与生产共享相同 span 生命周期和脱敏规则，能够按 trace 查询而不暴露家庭原文。
- Attempt/SafetyDecision/AgentRun 继续作为各自领域审计账本；Telemetry 不替代它们。
- 业务 Agent 不得自行创建供应商 span 或记录原始上下文；所有扩展属性必须先进入
  allowlist 评审。
