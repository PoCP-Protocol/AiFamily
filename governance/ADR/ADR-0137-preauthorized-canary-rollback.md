# ADR-0137：灰度 SLO 仅可执行预签名人工回滚控制

## 状态

Accepted — 2026-08-31

## 背景

家庭多模态体验已经通过完整 Bundle 进入灰度部署，但仅有 deployment receipt 不能判断
canary 是否安全。直接让 AI、监控 worker 或阈值程序创建回滚授权，会绕过 R9 人工责任
边界；只返回内存判定又无法跨进程审计为何发生回滚。

## 决策

1. 新增 provider-neutral `CanaryObservationPort` 与 `CanarySloPolicy`。观测只包含 deployment
   receipt/candidate/environment、聚合请求量、错误率、P95 延迟及安全违规计数，不包含
   tenant/family/subject 标识、Prompt、模型输出或家庭内容。
2. 未成年人安全或一般安全违规是即时 hard stop，不等待最小样本量；错误率和延迟只在
   达到 `min_request_count` 后判定，避免小样本噪声触发回滚。
3. `CanaryAssessment` 以 observation、policy version、scope、聚合指标、health 与 reasons
   完整内容寻址，并写入 append-only SQL ledger。相同 observation/policy 重放幂等，指标
   或结论漂移必须拒绝。
4. breach 本身无权生成 ReleaseControl。协调器只按 control ID 从经 signature verifier
   写入的控制账本读取 `ROLLBACK` 事件；control 必须匹配 candidate/decision/environment、
   指向不同的目标候选、由真人签名，并处于显式 TTL 内。
5. 合法 breach 使用该真人 control 的 actor 与稳定幂等键调用既有 Bundle-aware rollback；
   重复监督只产生一个外部回滚和一个 receipt。健康或证据不足时不得回滚。
6. `HttpCanaryObservationPort` 使用显式 token、timeout、可选 mTLS 和注入 client；平台错误、
   非法 JSON、缺字段、naive 时间及 scope 不匹配均 fail-closed。
7. `FamilyExperienceCanaryRuntime` 在 development/test/staging/production 组装同一 observation、
   policy、assessment、control reader 与 Bundle rollback 路径；candidate/receipt/runtime 环境
   任一不一致均在观测外呼前拒绝。

## 结果与边界

- 自动化的是“执行已授权回滚”，不是“自动授权回滚”；AI 和监控系统仍不能充当责任人。
- assessment ledger 保存阈值判定所需聚合指标，支持审计且不形成家庭画像或跨家庭排名。
- 当前尚未接入生产 scheduler、真实观测 endpoint、告警确认和 PostgreSQL 并发演练，
  因此不宣称自动回滚已运行于生产。

## 验证

- `tests/intelligence/experience/test_canary_supervision.py`
- `tests/intelligence/experience/test_http_canary_observation.py`
- `tests/intelligence/experience/test_release_bundle_runtime.py`
- `tests/apps/family_api/test_family_experience_canary_wiring.py`
