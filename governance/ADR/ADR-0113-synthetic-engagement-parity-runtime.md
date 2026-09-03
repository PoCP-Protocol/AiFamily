# ADR-0113：Synthetic Engagement Parity Runtime

- 状态：Accepted
- 日期：2026-08-30
- 范围：`backend/intelligence/experience/synthetic_engagement_runtime.py`

## 决策

在 dev/test 组合根增加独立的 `SyntheticEngagementRuntimeResolver`，通过
`dev_wiring.py` 的已认证 bearer session 解析家庭路径，并使用确定性 provider、
合成 `ExperienceEvent` 和同一 `EngagementDraftApplication` 生成 DRAFT。这样测试
环境保留完整的 HTTP → scope → 事件读取 → Model Gateway → provenance 响应链，不能
因为数据是模拟的而删减功能。

## 安全边界

- 合成 runtime 只允许 development/dev/test/local，数据分类固定为 `SYNTHETIC`，
  不得注入 `ProductionEngagementRuntimeResolver` 或进入成就投影。
- bearer session 仍必须与 URL family 一致；未认证和跨家庭请求在 resolver 前拒绝。
- provider 仍通过 Model Gateway registry 调用，输出保持 DRAFT-only 和
  `requires_human_confirmation=true`。
- 生产仍必须接入真实 identity/consent store、SQL event reader、密钥服务和部署
  scheduler；本 ADR 只证明功能 parity，不宣称生产供应商已上线。
