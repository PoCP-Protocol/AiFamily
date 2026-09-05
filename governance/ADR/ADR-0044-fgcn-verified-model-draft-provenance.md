---
id: ADR-0044
title: FGCN proposal 必须绑定受信任 ModelDraft provenance
status: accepted
date: 2026-08-30
decision_owner: project-owner
---

# ADR-0044：FGCN proposal 必须绑定受信任 `ModelDraft` provenance

## 背景

FGCN API 原先只把客户端提交的 `provenance_ref` 字符串保存到 HumanTask。
这能保留一个引用名，但不能证明引用确实来自 Model Gateway，也不能证明
草案仍处于 `DRAFT` 且没有写业务状态的能力。对未成年人相关服务匹配，
这种“字符串存在即视为有来源”的做法不足以支持可解释和可审计要求。

## 决策

1. 提案端点增加显式 `DraftProvenanceResolver` 依赖。resolver 必须按服务端
   推导的 tenant/family/subject/purpose/correlation scope 解析 `provenance_ref`
   为受信任的 `ModelDraft`。
2. 路由只接受 `status == DRAFT` 且 `may_mutate_business_state is False` 的模型
   草案；解析不到引用、返回非 `ModelDraft` 或返回可写状态均拒绝，不能用请求体
   替代 resolver。
3. 未配置 production resolver 时继续 fail-closed。测试可以提供显式 in-process
   resolver，但该替身不安装到 production app，也不因此宣称有真实模型调用。
4. 服务候选 `provider_id` 仍是被人工审核的候选服务方标识，不等同于 Model
   Gateway 的 provider identity；模型来源只能从已解析草案的 provenance 得到。

## 正向与反向询证

正向：受信任 resolver 返回合法 `ModelDraft` 时，FGCN proposal 可以进入 Human
Gate，原有 ACCEPT → Named Action → assignment 链不变。

反向：客户端提交不存在的 provenance 引用、resolver 返回非草案对象、或返回
非 `DRAFT`/可写草案时，proposal 不会建立 HumanTask；生产未接 resolver 时也
不会退回“只看字符串”的旧行为。

## Enforcement

- `backend/domains/service/fgcn/api/dependencies.py`
- `backend/domains/service/fgcn/api/routes.py`
- `tests/apps/family_api/test_fgcn_routes.py`
- `backend/intelligence/model_gateway/contracts.py`

