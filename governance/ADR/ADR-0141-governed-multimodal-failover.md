# ADR-0141：家庭多模态模型切换仅限独立准入的基础设施故障

## 状态

Accepted — 2026-09-01

## 背景

多模态路由器已经能给出首选与备用模型顺序，Model Gateway 也具备受限的跨供应商
`RoutingModelGateway`，但家庭体验应用层只调用首选模型，备用顺序没有进入真实生成路径。
此外，备用模型成功产生的持久化 Draft 会因 provider 与首选 provider 不同而在幂等回放时
被误判为契约漂移。

## 决策

1. `RoutedMultimodalExperienceService` 将路由器给出的首选与备用顺序完整传给生成服务；
   所有调用仍只经过 Model Gateway。
2. 只有 `TIMEOUT`、`NETWORK_ERROR`、`PROVIDER_5XX` 可以推进到下一模型。政策、安全、
   凭据、4xx、JSON 或 Schema 错误立即 fail-closed，禁止通过多次采样寻找“看起来可用”的答案。
3. 每个备用 provider 必须由 Gateway 独立执行环境、数据类别和第16条准入；一次失败不能
   替另一个供应商取得授权。
4. 每次实际外呼分别写 Attempt 并递增 `route_sequence`。HTTP route 字段表示计划首选，
   provenance 表示实际生成 Draft 的 provider，二者不得混写。
5. Draft 幂等回放允许 provenance provider 位于当次批准的 provider order 中，但
   use-case、Prompt、Schema、data class 与 ContextSnapshot 仍须完全一致。
6. HTTP 边界校验客户端声明的 modalities 必须与服务端从 media input types 派生的集合
   完全一致；路由容量按实际媒体条目数而不是模态类别数计算。

## 结果与边界

- 家庭多模态体验具备真正可执行、可审计且不绕过合规的模型故障切换。
- 测试与生产复用同一应用/Gateway 状态机；模拟 provider 只替换网络适配器和数据。
- 当前客户端 token estimate 仍只是提示，尚无 release-bound rate card、持久化预算预留/
  核销与 active Bundle 路由绑定；这些是下一项架构切片，不能把本决策描述为成本闭环。

## 验证

- `tests/intelligence/experience/test_multimodal_application.py`
- `tests/intelligence/experience/test_multimodal_generation.py`
- `tests/intelligence/experience/test_multimodal_routing.py`
- `tests/intelligence/experience/test_api_contract.py`
- `tests/apps/family_api/test_production_experience_wiring.py`
- `tests/intelligence/model_gateway/test_routing_and_attempts.py`
