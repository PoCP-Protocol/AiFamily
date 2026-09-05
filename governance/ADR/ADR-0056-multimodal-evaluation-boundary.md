---
id: ADR-0056
title: Multimodal Evaluation Boundary and Release Claims
status: Accepted
date: 2026-08-30
decision_owner: project-owner
---

# ADR-0056：多模态评估边界与发布声明

## 背景

多模态体验需要比较不同模型的结构化质量、安全拒答、延迟和成本，
但评估夹具不能复制原始家庭媒体，也不能把模型输出直接变成家庭事实或
教育效果分数。离线评估还必须能在没有供应商网络的环境运行。

## 决策

1. `MultimodalEvalRunner` 只接受版本化 synthetic/anonymous gold case 和
   注入的 provider-neutral adapter；评估器本身不读取凭据、不打开网络、不
   保存媒体字节。
2. 一个 case 只有同时通过 schema、预期拒答、安全标签、安全结果和
   `AiProvenance` 一致性检查，才计为通过；失败原因进入聚合报告。
3. 报告只发布 provider/model/version、契约质量、安全拒答、延迟和成本等
   技术指标；不得称为家庭总分、孩子成绩或教育疗效。
4. 该原语不能单独解锁生产 provider 或发布 gate。真实 provider、长期 gold
   set、Durable Run/feedback 关联和 owner approval 仍须另行完成并留证。

## Enforcement

- `backend/intelligence/experience/multimodal_eval.py`
- `tests/intelligence/experience/test_multimodal_eval.py`

