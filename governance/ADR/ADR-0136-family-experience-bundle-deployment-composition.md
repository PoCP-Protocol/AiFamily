# ADR-0136：家庭体验发布采用 Bundle-aware HTTP 同构组合

## 状态

Accepted — 2026-08-31

## 背景

ADR-0135 已将 Provider/Model、Prompt、Schema、Safety、Knowledge、评测和人工审批冻结为
不可拆分的 `FamilyExperienceReleaseBundle`。原通用 `HttpDeploymentPort` 只发送 Candidate
模型元数据；若家庭体验继续使用该路径，部署平台无法证明实际配置与已审批 Bundle 相同。
同时，测试环境不得用删减权限、审批、幂等或部署步骤的简化实现冒充生产验证。

## 决策

1. 新增 `HttpFamilyExperienceDeploymentPort`，复用通用 HTTP transport 的 token、mTLS、
   timeout、状态码和错误映射，但 apply/rollback payload 必须携带完整 metadata-only Bundle。
2. Bundle payload 包含内容寻址 ID、Prompt/Schema version、Safety、Knowledge refs、模型、
   evaluation/decision/control refs、Human Gate 与 DRAFT-only 边界；禁止包含 Prompt 原文、
   原始签名、token、tenant/family 标识或家庭内容。
3. 新增 `FamilyExperienceReleaseRuntime` 组合 identity、短期 scoped token、Bundle Store、
   Bundle-aware deployment、receipt 与 telemetry。真人身份必须具有 `ai.release.deploy`，
   candidate environment 必须与 runtime/identity 一致。
4. development、test、staging、production 使用同一 runtime、同一验证顺序和同一 HTTP
   契约；环境差异仅可来自显式注入的 URL、证书/令牌来源、Store、测试替身与数据。
5. 保留通用 ReleaseDeploymentService/HttpDeploymentPort 供其他 AI 用例使用，不把家庭体验
   专属 Prompt/Schema 字段扩散进通用 Candidate 合约。

## 结果与边界

- 灰度平台能够接收并核对被审批的完整发布组合，配置漂移在外部调用前失败。
- 测试环境能用 MockTransport 和模拟数据验证与生产相同的身份、授权、Bundle、幂等和
  receipt 路径，不构成功能阉割。
- 当前尚未提供真实部署平台 endpoint、证书、密钥轮换、回滚演练和灰度 SLO 证据；因此
  不宣称已完成真实生产发布。

## 验证

- `tests/apps/family_api/test_family_experience_release_wiring.py`
- `tests/intelligence/experience/test_release_bundle_runtime.py`
- `tests/intelligence/evaluation/test_http_deployment.py`
