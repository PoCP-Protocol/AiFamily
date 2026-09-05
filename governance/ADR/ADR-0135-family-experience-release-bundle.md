# ADR-0135：家庭多模态体验采用不可拆分的 AI 发布包

## 状态

Accepted — 2026-08-31

## 背景

现有 AI Release Gate、Candidate Catalog、Release Control 和 Deployment Port 已能管理
模型评测、Provider 准入、人工签名审批和部署回执，但通用 `ReleaseCandidate` 只冻结
Provider、Model 与 report ref。若部署系统分别读取 Prompt、Schema、Safety 或 Human
Gate 配置，某一项漂移仍可能让“评测过的候选”与“实际运行的组合”不同。

## 决策

1. 新增 `FamilyExperienceReleaseBundle`，把下列既有对象绑定为一个 metadata-only、
   内容寻址的部署前清单：
   - Provider、Model、Model Version 与 data class；
   - 已发布 family-experience Prompt/Schema 及其内容摘要；
   - Safety policy、Knowledge refs、Human Gate rule；
   - ReleaseDecision、evaluation report ref；
   - 经外部 verifier 验证后写入的 ReleaseControl approval、actor 与 signature ref。
2. Bundle 仅接受 `ADMITTED` 且 failures 为空的 ReleaseDecision、`PUBLISHED` 资产和
   `APPROVAL` 控制事件。Provider Registry 必须再次按 environment/data class 准入，
   Provider/Model/Version 任一不一致即拒绝。
3. Bundle 固定 `draft_only=true`、`may_mutate_business_state=false`，并要求
   `human_gate_rule=REVIEW_REQUIRED`；它不调用 Provider、不部署、不持有密钥，也不能
   写家庭或业务事实。
4. `asset_digest` 覆盖 Prompt 文本、Schema、禁止字段、Safety、Knowledge 和 Human
   Gate；`bundle_id` 再绑定 candidate、report、decision 与 signed control。相同输入
   确定性得到相同 ID，任何受治理内容改变都必须形成新 Bundle。
5. Bundle 通过独立 SQL 表按 `bundle_id` 和 `candidate_id + environment` 不可变保存；
   重放相同内容幂等，同一候选绑定不同 Bundle 必须拒绝。表内只保存 metadata，不保存
   Prompt 原文、原始签名、密钥或家庭数据。长生命周期部署 runtime 使用 session-per-call
   Reader，每次读取创建并关闭独立 AsyncSession，不保留启动期数据库会话。
6. 家庭体验灰度/激活/回滚使用专用 `FamilyExperienceDeploymentPort`。服务在外呼前从
   Store 读取 Bundle，并逐项核对 Candidate、Decision、Provider/Model/Version、report
   与 control；apply 还必须使用 Bundle 绑定的同一审批 control。外部端口收到完整 Bundle，
   不接受裸 Candidate。

## 结果与边界

- SQL Store 与 Bundle-aware Deployment Port 已避免独立配置漂移；缺 Bundle、Candidate
  元数据漂移或审批 control 不一致时均在外部副作用前 fail-closed。
- 不扩展通用 Candidate 表，避免把 family-experience 专属 Prompt/Schema 合约泄漏到其他
  AI 用例；通过专属组合服务与端口实现边界收窄。
- 当前尚未接入真实灰度平台 adapter，因此不宣称发布包已实际部署。
- 签名验证仍由 `ReleaseControlStore` 的外部 verifier 执行；Bundle 只绑定已生成的
  signature ref，不读取或保存原始签名与密钥。

## 验证

- `tests/intelligence/experience/test_release_bundle.py`
- `tests/intelligence/experience/test_release_bundle_runtime.py`
- `tests/intelligence/evaluation/test_release_control.py`
- `tests/intelligence/evaluation/test_release_gate.py`
