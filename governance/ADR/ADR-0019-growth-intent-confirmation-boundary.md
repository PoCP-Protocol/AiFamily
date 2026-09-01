# ADR-0019: GrowthIntent 确认写入的 canonical owner 与原子边界

- **Status**: Accepted
- **Date**: 2026-09-01
- **Deciders**: chief-architect / growth-confirmation-owner
- **Supersedes**: null
- **Superseded By**: null

## Context

Assessment 拥有测评、解释草案与家长看到的 versioned understanding signal，Growth
拥有 `GrowthIntent`。此前 Assessment repository 直接写 `growth_intents`，造成 owner
越界；同时确认时重新运行 interpretation，使家长确认的内容与实际写入来源可能不同。

Platform 已提供 caller-owned `AsyncSession` 的 canonical Audit 与 Outbox append seam。
现有 `growth_intents` schema 通过 `(family_id, source_type, source_ref)` 唯一索引保护
Assessment 来源，但不包含 draft、provenance 或 Human Gate binding 列。

## Decision

1. `backend/domains/growth` 是 `GrowthIntent` 的唯一代码 owner。Assessment 只能经
   `GrowthIntentConfirmationPort` 请求确认，不能直接访问 `growth_intents`。
2. Assessment 在同一 atomic mutation callback 内验证 Guardian、Consent、Human Gate
   effective、scope 和 reviewed binding，并从 immutable signal 构造 command。Growth
   不复制或解析这些 ledger。
3. Growth 将 command 转换为 `ValidatedConfirmationBinding`，校验必填引用、正版本、
   canonical family scope 和 payload hash；`source_type` 固定为
   `ASSESSMENT_HYPOTHESIS`。
4. Growth 使用现有 `idempotency_keys` 表持久化 request hash 与完整 receipt。同 key
   同 payload 返回同 receipt；同 key 不同 payload fail-closed。
5. Intent、canonical Audit、Outbox 与 idempotency receipt 使用 caller-owned
   `AsyncSession`，adapter 不 commit。任一步失败由外层 UoW 全部回滚。
6. 完整 signal/draft/provenance/gate binding 持久化在 idempotency receipt、Audit 与
   Outbox envelope。MVP 不给 `growth_intents` 增加重复列，也不把 binding 塞进
   `goal_text`。
7. 该确认只创建 `OPEN` GrowthIntent，不创建 Fact、Outcome、诊断、计划、任务或商业
   决策；AI 不参与确认写入。
8. Reviewed understanding 的 canonical family scope 是封闭集合：
   `family://{tenant}/{family}/assessment` 与
   `family://{tenant}/{family}/problem-understanding`。后者保持独立语义，不得改写成
   assessment；Assessment 在写 reviewed signal 前校验 exact scope，Growth 对同一
   immutable binding 再做结构校验。新增 scope kind 必须另行 ADR 裁决。

## Alternatives Considered

### Assessment repository 继续写 GrowthIntent

否决。它复制 Growth owner 语义并让后续 Journey 无法只消费 canonical receipt。

### 给 growth_intents 增加全部 reviewed binding 列

否决。binding 已由 decision receipt、Audit 与 Outbox 持久化；重复列会产生漂移。

### Growth 再实现 Consent/Human Gate verifier

否决。验证由 Assessment caller 在同一 atomic callback 完成；Growth 重复实现会产生
第二套授权语义。

## Consequences

- Growth adapter 必须由已打开的 `AsyncSession` 构造，不能自行提交。
- API/composition 必须保证 Assessment 验证与 Growth 写入共享同一 UoW；本 ADR 不改
  `main.py`。
- Outbox worker/DLQ 与生产 wiring 仍是独立门，不因 adapter 存在而宣称生产可用。

## Enforcement

- `tests/domains/growth/test_growth_intent_confirmation_postgres.py` 覆盖真实 PostgreSQL
  首次写入、跨 session replay、payload conflict、existing intent mismatch、完整 binding
  和 Audit/Outbox/receipt 原子回滚。
- 架构测试继续禁止 Growth 直连 AI provider、重复 domain path 与无登记代码。

## References

- `docs/00_system/CURRENT_DOMAIN_MAP.md` §3.2
- `governance/REPOSITORY_CONSTITUTION.md` R2/R6/R8/R9
- `database/baseline/0020_growth_orchestration_v1.sql`
- `database/baseline/0044_ui03_growth_hypothesis_confirmation.sql`
- `backend/platform/persistence/atomic_mutation.py`
- `backend/platform/audit/recorder.py`
- `backend/platform/outbox/writer.py`
