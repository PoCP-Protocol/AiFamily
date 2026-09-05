# ADR-0132：多模态体验运行时绑定版本化 Prompt/Schema

## 状态

Accepted — 2026-08-31

## 背景

多模态 HTTP 请求此前只把 `prompt_version`、`schema_version` 和
`output_schema` 作为客户端生成意图传入。即使 Model Gateway 记录了版本，调用方仍可能
提交未发布版本或与注册表不同的 schema，导致评测、回放和真实生成无法复现。

## 决策

1. 提供 `MultimodalContractRegistryBinding`，同时解析同一 `use_case` 与 `agent_id` 下
   的 reviewed/published PromptBundle 和 SchemaDefinition；支持同步内存 Registry 与
   异步 SQL Registry。
2. Prompt 的 `output_schema_ref` 必须等于绑定的 schema ref；Prompt、Schema 的版本、
   use-case、agent 都必须完全一致。Schema 必须有非空 `json_schema`，且客户端声明的
   `output_schema` 必须与注册版本结构相等，否则在 Provider 外呼前拒绝。
3. `MultimodalDraftRuntime.contract_binding` 是组合根显式注入项。未注入时保留旧的
   contract-only/dev 兼容路径；注入后拒绝未注册、非生效或 schema 漂移请求，不静默
   降级为客户端版本。
4. 绑定失败只返回稳定的 `PROMPT_SCHEMA_BINDING_REJECTED`，不泄露 Registry 细节；绑定
   不调用 Provider、不写业务事实，仍由 Model Gateway 负责真正外呼、Safety、Provenance
   和 Human Gate。

## 结果与后续

- 生产组合根可以在启动时注入 SQL Prompt/Schema Registry，测试环境可注入同构内存
  Registry，保持功能 parity。
- 生产 wiring 现在强制要求注入 `contract_binding`；缺失时启动即拒绝，避免 staging/
  production 静默退回 contract-only。若应用完全未安装生产 resolver，路由仍保持既有
  503 fail-closed，不能据此宣称真实资产已完成部署。
- 后续需把标准 `family-experience` Prompt/Schema 资产纳入受审发布流程，并在离线
  Multimodal Eval 中固定对应版本。

## 验证

- `tests/intelligence/experience/test_contract_binding.py`
- `tests/intelligence/experience/test_api_contract.py`
- `tests/apps/family_api/test_production_experience_wiring.py`
