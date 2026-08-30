---
id: ADR-0069
title: Environment wiring and authenticated experience fail closed
status: Accepted
date: 2026-08-30
decision_owner: chief-architect
---

# ADR-0069：环境接线与 Experience 身份边界必须 fail-closed

## 背景

`dev_auth` 用任意 `external_ref` 换取进程内 token，只能作为 development/test
的合成适配器。若 `AIFAMILY_ENV` 缺失或拼写错误仍被当作 development，合成身份
就会在未明确授权的进程中出现。Experience 路由还必须区分“没有可信身份”和
“身份已认证但没有家庭/同意范围”，否则客户端无法安全重试，审计也无法判断拒绝
原因。

## 决策

1. `AIFAMILY_ENV` 是唯一环境选择入口。只有显式 allow-list 值才可启用 synthetic
   wiring；未设置、空值或未知值一律禁止 dev wiring（不得默认为 development）。
2. `dev_auth` 只能在 development/dev/test/local 挂载；production/staging 的
   OpenAPI 不得出现 `/auth/account-session`，也不得由任意 external_ref 签发 token。
3. Experience 的 scope resolver 必须从可信 Bearer 身份、租户-家庭绑定和实时
   Consent 组装 `ContextScope`；请求 JSON 的 tenant/family/subject 字段不是权威。
4. HTTP 错误语义固定为：缺失或无效可信身份 `401 + WWW-Authenticate: Bearer`；
   已认证但跨家庭/租户 `403 family_access_denied`；同意缺失、撤回或过期
   `403 CONSENT_REQUIRED`。所有拒绝必须发生在 Model Gateway 调用之前。
5. development/test/production 复用同一业务路由、状态机、权限、同意、审计、
   幂等和人工闸门；环境只替换数据集与外部适配器。生产必须提供真实 auth/session/
   tenant/consent 适配器，不能以移除路由代替能力。

## Enforcement

- `tests/apps/family_api/test_environment_wiring_acceptance.py` 锁定 unset/非法
  环境不启用 synthetic auth（当前 unset 用例应保持红灯，直到 ENV-01 owner 收口）。
- `tests/apps/family_api/test_production_dev_auth_gate.py` 锁定 production OpenAPI
  与 `/auth/account-session` 负向行为。
- `tests/apps/family_api/test_experience_auth_error_mapping.py` 锁定 401/403/
  `CONSENT_REQUIRED` 的 scope 边界语义。
- `backend/intelligence/experience/api.py::_resolve_request_runtime` 是错误映射
  的唯一 HTTP 边界；真实 resolver 与 composition root 仍需完成身份和持久化同意接线。

## 状态与残余风险

本 ADR 锁定目标合同，不宣称生产能力已完成。`dev_wiring.py` 与
`production_experience_wiring.py` 当前存在其他 Agent 的未提交 WIP；在 owner 收口
前不得覆盖这些文件或将 ENV-01 标记为 GO。真实 session、tenant membership、Consent
存储、撤回实时生效和 production TestClient 三环境 parity 仍是 P0。
