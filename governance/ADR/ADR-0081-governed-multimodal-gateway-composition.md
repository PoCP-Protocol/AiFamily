# ADR-0081: Governed multimodal Gateway composition

- 状态：Accepted for experiment
- 日期：2026-08-30
- 范围：`backend/intelligence/model_gateway/composition.py`

## 决策

新增 `build_openai_compatible_gateway_from_registry` 作为 OpenAI-compatible
多模态适配器的唯一便捷组装入口。部署必须显式列出 `provider_ids`；工厂启动时
校验 ProviderRegistry 的 callable status 与 environment，再读取 registry 声明的
credential/base URL 环境变量。请求执行时仍由 ModelGateway 重新执行 data class、
安全、Attempt、schema、Provenance 和 Human Gate 相关策略。

Qwen、Doubao、OpenAI-compatible 等未完成合规审查的候选不会因为有凭据就自动可用；
`TECHNICALLY_VALIDATED`、环境不匹配、缺少凭据或重复 provider id 均 fail-closed。
同一适配器契约覆盖不同厂商，避免业务层绑定供应商 SDK。

## 结果

测试环境可以使用 FakeProvider 或注入的 MockTransport 走同一 Gateway 流程；staging/
production 只有在 ProviderRegistry 明确批准后才能组装真实网络 adapter。供应商切换
只替换 registry record、凭据绑定和 adapter 配置，不改变多模态体验服务、Safety、
Provenance、Human Gate 或业务域闭环。
