---
id: ADR-0041
title: FGCN Human Gate 控制面接入 family_api
status: accepted
date: 2026-08-30
decision_owner: project-owner
---

# ADR-0041：FGCN Human Gate 控制面接入 `family_api`

## 背景

ADR-0040 已经具备持久化 `HumanTask` 和 one-shot worker handler，但两者还
没有平台 HTTP 调用方。若只保留领域测试，真实平台仍停在“代码存在、用户
无法提交草案或作出决定”的状态；若把 `NamedActionRequest` 放进请求体，
客户端又可以伪造人工身份、scope 或业务动作。

## 决策

1. 在 `backend/domains/service/fgcn/api` 暴露四个窄端点：
   - `POST /families/{family_id}/fgcn/tasks/{service_task_id}/assignment-proposals`
   - `GET /families/{family_id}/fgcn/human-tasks/{task_id}`
   - `POST /families/{family_id}/fgcn/human-tasks/{task_id}/decisions`
   - `POST /families/{family_id}/fgcn/human-tasks/{task_id}/consume`
2. 提案端点只接受草案标识、provenance reference、候选 provider 和期限；
   action name 固定为 `CONFIRM_SERVICE_TASK_ASSIGNMENT`，而 tenant、family、
   subject、purpose、consent version、correlation 均从持久化 `ServiceCase` /
   `ServiceTask` 推导。请求体禁止额外字段。
3. 提案请求必须来自可信的 AI `ActorContext`；决定请求必须来自可信的
   `HumanReviewerContext`；消费请求必须来自可信的 system worker context。
   三类身份都由依赖注入解析，客户端不能在 body 中声明或覆盖。
4. 接受决定只由 `SqlAlchemyHumanGate` 持久化 `NamedActionRequest`，消费端
   只调用 `consume_accepted_human_task`，不得在路由内直接写 assignment。
   gate、FGCN repository 和审计使用同一个 request session；默认 session、
   identity、reviewer role 和 worker auth 未配置时 fail closed。
5. API 是 Human Gate/业务命令控制面，不把当前 `ModelGateway` fake provider
   或未完成的外部 provider 注册宣称为生产 AI 供应商。真实 AI 生成仍须经
   `backend/intelligence/model_gateway`，并由后续 production wiring 接入。

## 正向与反向询证

正向：HTTP 测试覆盖 AI 提案、人工接受、worker 消费、新请求读取和同一请求
重放；接受后可得到 `NamedActionRequest`，消费后返回同一个 assignment。

反向：错家庭、非 AI 提案、伪造 actor/scope/NamedActionRequest 字段、人工
拒绝后的消费请求均被拒绝；默认依赖未接线时不会发明 tenant、reviewer 或
worker 身份。FGCN 领域命令继续执行最终 scope、actor、状态和幂等重验。

## 后果与未完成项

正面是 FGCN 首次有了可部署的 HTTP 控制面，且 API 不绕过 Human Gate 或业务
命令。代价是 production 仍必须完成真实 Account → TenantMembership → Family
identity、reviewer role、consent store、session factory、迁移执行和 worker
队列 lease；当前 `consume` 端点只是受 system identity 保护的 one-shot handler
调用，不是常驻 workflow scheduler/dead-letter 实现。

此外，`provenance_ref` 的存在性和内容由后续 AI Runtime/Provenance Registry
核验；本端点只保证它被保留并随 HumanTask 持久化，不能把客户端提交的字符串
当作已完成的模型调用证明。

## Enforcement

- `backend/domains/service/fgcn/api/dependencies.py`
- `backend/domains/service/fgcn/api/requests.py`
- `backend/domains/service/fgcn/api/routes.py`
- `backend/apps/family_api/main.py`
- `tests/apps/family_api/test_fgcn_routes.py`
- `tests/domains/service/fgcn/test_workflow_worker.py`
