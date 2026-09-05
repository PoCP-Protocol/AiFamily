# ADR-0130：反馈偏好作为受控的多模态生成上下文

## 状态

Accepted — 2026-08-31

## 背景

UI-05 已经可以对多模态草稿提交 `helpful`、`not_helpful` 和
`request_human`。如果反馈只停留在 Run Ledger，下一次草稿无法改善节奏；如果把原始
理由、模型输出或客户端自报的偏好直接拼进 Prompt，又会扩大未成年人数据暴露面并绕过
作用域校验。

## 决策

1. 以现有 append-only `ExperienceRunInteraction` 为唯一事实来源，在精确的
   `tenant_id/family_id/subject_ids` scope 内计算 `FeedbackPreferenceSnapshot`。
2. 快照只保留三类信号计数和样本量（最多读取最近 5,000 条反馈），不保留或传递原始
   `reason`、媒体、模型原文、用户身份、家庭总分或家庭排名；已删除 Run 的反馈不进入
   快照。
3. `MultimodalDraftRuntime` 在生成前读取可选快照，`ContextBoundMultimodalCommand`
   校验 scope 后，将服务端快照写入保留键 `experience_feedback`。该键覆盖客户端同名
   输入，防止 Prompt-side forgery；没有快照能力的旧 Ledger 继续生成但不附加偏好上下文。
4. 内存 Ledger、SQL Ledger、async bridge、session-per-call 和 committed wrapper 都
   实现同一读取契约。读取只产生 metadata，不调用 Provider，不写 Family/Growth/
   Service/Commerce canonical fact。
5. `request_human` 仍是反馈/人工闸门信号；偏好上下文只能帮助 AI 调整表达和节奏，不能
   自动确认草稿或关闭人工复核。

## 结果

- AI 生成链路具备可解释、可审计的反馈闭环，且 Provider 仍只能通过 Model Gateway
  访问。
- 反馈聚合天然按家庭和主体隔离，并复用现有删除与幂等语义，无需新增事实表。
- 后续如果要引入衰减、时间窗或偏好标签，必须扩展快照契约并重新评估隐私、评测和
  Prompt/Schema Registry 绑定，不得在 UI 或模型适配器中自行推断。

## 验证

- `tests/intelligence/experience/test_run_http.py`
- `tests/intelligence/experience/test_sql_run_ledger.py`
- `tests/intelligence/experience/test_multimodal_context_application.py`
- `uv run pytest tests/intelligence/experience -q`（261 passed）
