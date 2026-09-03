# ADR-0133：家庭体验采用可审查的标准 Prompt/Schema 资产基线

## 状态

Accepted — 2026-08-31

## 背景

ADR-0132 已经要求多模态请求在 Provider 外呼前绑定已发布的 Prompt/Schema，
但仅有 ref selector 仍无法证明 dev/test 与生产使用的是同一份内容。UI-05
当前固定发送 `family-companion.v1` 与 `family-experience-draft.v1`，需要一个
可加载、可校验且不会绕过人工审核的资产基线。

## 决策

1. `backend/intelligence/experience/standard_assets.py` 提供不可变的
   `FamilyExperienceAssetBundle`，同时构造 `family_assistant_v1` Prompt 与
   `assistant_response_v1` Schema；两者固定绑定到
   `family_assistant_conversation` / `parent_advisor`。
2. 标准输出只允许 `understanding`、`next_step`、`limitations`，要求保留至少一条
   limitation，并拒绝诊断、法律/医疗结论、面向未成年人的商业营销、权威事实、
   家庭总分和家庭排名字段。输出仍是 Draft，Schema 的 Human Gate 为
   `REVIEW_REQUIRED`。
3. 工厂默认返回 `DRAFT`。只有调用方显式提供 `reviewer` 与 `effective_at` 才能
   创建 `PUBLISHED` 快照；生产组合根仍必须显式注册经审批的 Registry 版本，工厂
   不会自动发布或自动写入 SQL。
4. dev/test 可用同一工厂创建合成的已发布 fixture，再注入内存 Registry；生产使用
   相同的 ref/version/schema 契约，但由 SQL Registry 和真实审批流程提供资产。
5. `standard_asset_registration.py` 在注册前同时预检两侧 `(ref, version)` 身份，要求
   成对 PUBLISHED，并支持同步内存或异步 SQL Registry；SQL 事务由组合根持有，不在
   注册器内隐式提交。
6. `sql_contract_binding.py` 提供 session-per-call Prompt/Schema readers；每次 resolve
   打开独立只读 SQL session，返回不可变资产后关闭，禁止把启动期 AsyncSession 长期
   保存在生产 binding 中。

## 结果与边界

- Prompt/Schema 内容不依赖 Provider SDK、业务域 ORM 或家庭运行数据，可被离线评测
  和回放固定引用。
- 该工厂证明的是契约和测试 fixture，不等于真实生产 Prompt 已完成审批；外部知识、
  Soul、模型准入、DPIA 和运营发布签名仍需各自的治理证据。
- 注册预检不能消除并发竞态；SQL 组合根必须在一个事务中调用并处理唯一键/回滚，
  不能把“预检通过”当作发布审批凭证。
- Schema registry 当前校验结构与边界，Model Gateway 负责 Provider 外呼、Safety、
  Provenance 和 Human Gate；任何业务事实仍只能由 Named Action 写入。

## 验证

- `tests/intelligence/experience/test_standard_assets.py`
- `tests/intelligence/experience/test_standard_asset_registration.py`
- `tests/apps/family_api/test_production_experience_wiring.py`
- `tests/intelligence/experience/test_contract_binding.py`
- `uv run pytest tests/intelligence/experience -q`
