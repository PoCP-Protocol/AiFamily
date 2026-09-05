# ADR-0063：Safety Runtime 接入 Model Gateway 请求闭环

## 状态

Accepted — 2026-08-30

## 背景

ADR-0062 建立了 provider-neutral Safety Runtime，但若只由上层业务调用，任一新的 AI caller 都可能绕过安全检查。Model Gateway 是唯一允许访问模型供应商的边界，因此安全策略必须在该边界执行。

## 决策

1. `ModelGateway` 接受可注入的 `SafetyRuntime`。
2. Safety Runtime 在 provider admission 之前检查请求：禁止用例或禁止字段直接 `POLICY_REJECTED`，不创建 provider attempt、也不触达供应商。
3. 模型返回并通过 JSON/schema 校验后再次检查输出：禁止字段、禁止用例或非 DRAFT/可变业务状态输出被阻断，并将已开始的 attempt 记为 `POLICY_REJECTED` 失败。
4. 高影响用例和未成年人数据返回 `REVIEW`，仍只返回 DRAFT；后续 Human Gate 决定是否可执行 Named Action。
5. `build_gateway` 默认注入 `SafetyRuntime`；测试/底层适配器可以显式传入 `None` 以隔离单元测试，但生产组合根必须使用默认工厂或显式注入。
6. 合成运行时显式注入同一 Safety Runtime，确保测试环境与生产调用顺序和策略一致；仅 provider 凭据和数据替身不同。

## 取舍

- 安全策略错误会在模型调用前失败，牺牲了“尽量给答案”换取 fail-closed 和零外泄。
- `REVIEW` 决策不把审核状态写进 `ModelDraft`，因为 Draft 合同必须保持 provider-neutral；Human Gate 依据 use case/主体上下文建立审核任务。
- Provider-specific moderation、SafetyDecision 持久化和审核反馈闭环不属于本 ADR，作为后续生产组合根工作项保留。

## 验证

- `tests/intelligence/model_gateway/test_safety_integration.py`
- `uv run pytest tests/intelligence/model_gateway -q`
- `uv run pytest tests/intelligence/experience/test_synthetic_runtime.py tests/intelligence/experience/test_multimodal_registry_integration.py -q`

