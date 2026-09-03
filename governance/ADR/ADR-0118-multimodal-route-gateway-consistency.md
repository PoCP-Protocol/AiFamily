# ADR-0118：多模态路由目录与 Model Gateway 一致性闸门

- 状态：Accepted
- 日期：2026-08-30
- 范围：`backend/intelligence/experience/multimodal_routing.py`、
  `backend/apps/family_api/production_experience_wiring.py`

## 决策

生产多模态组合根启动时必须验证路由目录与 Model Gateway 的 provider 集合、模型
身份及模态能力完全一致：每个路由 profile 都必须存在已装配的 Gateway adapter，且
`model/model_version` 与 Gateway 的 `ProviderRecord` 相同，profile 声明的模态必须是
adapter 的 `supported_modalities` 子集。任一缺失或漂移都在
启动期拒绝，而不是等到家庭请求到达后才返回不可解释的 provider 错误。

## 理由与边界

- 路由器继续只负责能力、成本、延迟和合规筛选；真实调用仍由 Model Gateway
  执行 admission、Safety、Attempt、Schema、Provenance 和 Human Gate 边界。
- Adapter 必须声明 `supported_modalities`；OpenAI-compatible 当前明确为 TEXT/IMAGE，
  AUDIO/VIDEO 不能静默降级，需由具备对应能力的独立 adapter 通过同一 Gateway 接入。
- fallback 仍必须是各自独立获准的 provider；一致性闸门不会放宽
  `sub_delegates`、data class 或环境准入。
- dev/test 使用同一校验逻辑，只替换 synthetic profile/adapter，不能通过模拟数据
  绕过模型身份漂移检查。
