---
id: DELIVERY-MANUS-REVIEW-001
title: Manus 审查建议吸收与执行对齐
type: delivery
status: current
version: 1.0
owner: project-assistant
created: 2026-08-30
updated: 2026-08-30
canonical: false
supersedes: null
superseded_by: null
---

# Manus 审查建议吸收与执行对齐

## 1. 结论先行

Manus 报告指出的主风险仍然有效，但报告中的历史数字不能作为当前现状。当前代码已经形成若干可测试的垂直切片（包括 FGCN 迁移链、Principal/Context/Human Gate 契约、语义化移动端体验列表），但还没有形成可以安全发布的生产闭环。

本轮结论：**NO-GO**。当前远端可见为 `d2196bc` 测试候选；本地总控另有待推送的
FGCN `41ad120`、Web client-mode `4b9a4b4` 和 PMA 文档 `4e50883`/`eccdb1b`/`bffe2a8`/
`2f5aedc`/`b8f0eea`，工作树仍包含其他
Agent 的 WIP。提交可追踪不代表生产就绪。以下 P0 必须先清零：生产环境仍可暴露开发登录；
缺少环境变量时会默认开发 wiring；身份、租户、家庭绑定和同意存储仍未持久化；测试闸门当前
红灯。任何 synthetic adapter 通过测试都不等于生产能力。

证据采集日期为 2026-08-30。工作区有其他 Agent 的未提交 WIP，本文件只记录从当前磁盘、Fresh Postgres、Fresh 测试命令和远端 CI 重新取得的证据。

## 2. 报告结论逐项核验

状态含义：

- **仍成立**：风险在当前代码中可以复现。
- **部分成立**：原问题的一部分已改善，剩余部分仍阻断交付。
- **已过时**：报告的具体数字或文件状态已被当前实现改变；不代表能力已生产化。
- **证据不足**：当前没有足够证据声称已完成。

| Manus 结论 | 当前状态 | 当前证据与判断 | 后续动作 |
|---|---|---|---|
| dev_auth 无条件挂载、可任意签发会话 | **部分成立，P0 仍阻断** | APLT-2 已在 `backend/apps/family_api/main.py` 用 `is_dev_environment()` 保护挂载；`AIFAMILY_ENV=production` 的 OpenAPI 已无 `/auth/account-session`，请求 404，test 环境仍 200。可是 `dev_wiring.py:current_environment()` 缺省仍为 `development`，unset 环境仍暴露 synthetic auth；生产也没有真实 auth/session 等价替代。 | APLT/ARCH：缺失/拼写错误环境必须 fail-closed；补真实身份会话与负向测试，保持三环境功能集合一致。 |
| 环境默认 development、APP_ENV 与 AIFAMILY_ENV 不一致 | **仍成立，P0** | `backend/apps/family_api/dev_wiring.py:115-120` 缺少 `AIFAMILY_ENV` 时返回 `development`；仅设置 `APP_ENV=production` 仍为开发环境。 | APLT/ARCH：统一变量；缺失、拼写错误或未允许值必须 fail-closed；启动和路由负向测试。 |
| Ruff 398、CI 红、无分支保护 | **仍成立（历史数字已过时），P1** | 当前 `uv run ruff check . --output-format concise` 为 **1 error**（`backend/domains/family/domain/entities.py:E501`）；`uv run pytest tests/architecture -q` 为 **109 passed、1 skipped、1 failed**（Ruff ratchet）；历史“398”不再是当前计数，CI/分支保护仍需独立复核。 | AQA/GOV/ARCH：修复 lint debt、登记漂移；CI 必跑并启用分支保护。 |
| 文档、Registry 与代码漂移 | **仍成立，P1** | `governance/DOMAIN_REGISTRY.yaml:452-453` 当前 YAML 缩进错误；`product_management` 和 `__pycache__` 触发未登记检查；`CURRENT_SYSTEM_BASELINE.md` 仍写“zero business APIs”，与当前 FastAPI unset/test 61、production 57 条路径不符。 | GOV/ARCH：修复语法和登记，建立源代码/Registry/文档快照校验；历史文档降级为非事实来源。 |
| 移动端 46 API 与后端契约不一致 | **仍成立（46/11 数字已过时），P1** | 当前 FastAPI OpenAPI 有 **61（unset/test）/57（production）** 条路径；移动端 client 仍包含 dev/test 路径。`pnpm check` 通过，但全量 Vitest **249 passed、1 skipped、5 failed**（Registry 数量、旧 service query/body、UI-02 旧文案）。尚无 OpenAPI 导出与 client 方法、路径、JSON schema 的持续兼容检查。 | API/AFE/ARCH：生成规范并在 CI 对比 client；更新或删除陈旧库存；全量移动端绿灯。 |
| AI 只有基础设施、没有业务能力 | **已过时代码描述，风险仍成立** | 当前已有 `backend/intelligence/principal`、`human_gate`、`experience`、`knowledge` 和多项契约测试；Principal 仍输出 `DRAFT`，Model Gateway 没有获准外部 provider，`AI_USE_CASE_REGISTRY.yaml` 全部为 `PLANNED`，Context/Memory 与 Human Gate 尚未形成生产持久化和正式 HTTP 闭环。 | AAIR/ARCH：先完成一个低风险、可回放、人工确认的生产候选闭环，再把 registry 状态改为 evidence-backed。 |
| Node/Express/tRPC/MySQL 模板越过 Python 后端边界 | **仍成立，P2** | `frontend/mobile/package.json` 和 `server/_core` 仍有 Express、tRPC、Drizzle、mysql2。它们是否是可删除模板尚未有 ADR 和边界测试；R1 规定正式业务后端为 Python/FastAPI/PostgreSQL。 | ARCH/API：做 ADR；删除或明确仅本地 UI 工具，禁止承载正式业务事实。 |
| 公共仓库缺许可证 | **仍成立，P2** | 根目录没有 LICENSE/COPYING/SPDX，`pyproject.toml` 无许可证字段；公开远端仓库仍可访问。 | GOV/LEGAL：补 SPDX/许可证与第三方资产清单，或在发布前改私有并记录授权。 |
| Alembic 基线/迁移链失败 | **部分成立，当前有新增 WIP** | 原报告的 `0005` 长度问题已由 `0005_fgcn_assignment_idempotency` 修复；Fresh Postgres 下 0004→0008 `test_fgcn_migration_chain.py` 2 passed。当前 `alembic heads` 已漂移到 **0017**；未跟踪 `0011`-`0017` revision 及对应 ADR/Manifest/ORM；Fresh Postgres `test_alembic_baseline_applies.py` 当前 **8 passed、1 failed、1 skipped**（未知 0017 head 拒绝，0010 已登记跳过），不得视为完成。 | ADOM/AAIR/ARCH：保留 0004-0008=159 固定边界；0009-0017 仅在 migration/ADR/Manifest/ORM/对象清单已提交且 Fresh Postgres 可逆后 allow-list；未知 head 必须失败。 |
| 身份、同意、租户/家庭绑定及持久化不完整 | **仍成立，P0/P1** | service/membership/commerce production dependencies 仍在 session factory、actor/context、tenant directory 或 repository 未配置时拒绝；identity 只有 `DenyAllTenantDirectory`/`InMemoryTenantDirectory`；consent 只有无状态 gate，没有 grant store；family_need 仅 fake repository。 | PLT/DOM/DATA：实现 Account→TenantMembership→Family、Consent store、审计和真实 UoW；任何生产路由不得落到 fake。 |

## 3. 本轮独立反向审查（已发 owner，等待返工）

项目助理不采信“完成”口头汇报，逐项核查交付物。以下意见已通过协作消息发给对应 owner，并同步给 Lead；在返工证据返回前标记为 **PARTIAL**：

### 3.1 AFE-4 服务体验列表

- **证据**：`frontend/mobile/components/family/family-experience-list.tsx` 使用语义图标、阶段和成就文案，未把 `UI-xx` 渲染为可见标签；`family-experience-list.test.ts` 定向 5 项通过，`pnpm check` 通过。最新全量 `pnpm test -- --run` 为 249 passed、1 skipped、5 failed（55 files）。
- **缺口/风险**：仅覆盖 services surface；全量移动端仍有 5 个失败，UI-19～34 其它列表和 `family-screen-list.tsx` 未完成跨端视觉/语义编号扫描。敏捷计划先前记录的 247 passed 已过时。
- **补测与验收**：`cd frontend/mobile; pnpm check; pnpm test -- --run` 必须 0 failures；新增 app/components 可见文本扫描和 Android/iOS/Harmony/web golden/e2e；内部 ID 只能留在 registry/导航。

### 3.2 ADOM-5 FGCN 迁移链

- **证据**：DB-01 的 Fresh Postgres baseline/head 分层与 FGCN chain 当前分别为 **8 passed、1 failed、1 skipped** 与 **2 passed**；失败为未知 0017 head（0010 已登记跳过）。0001 baseline、0008 固定边界与动态 head 已分层，0008=159 表；当前 `alembic heads`=0017，未跟踪 `0011`-`0017` revision 及对应 ADR/Manifest/ORM，不能把 manifest 工作树行视为已完成。
- **缺口/风险**：迁移测试固定 0008→159，并只对完成审批、tracked 文件和 manifest/ADR 的 0009+ head 放行，未知 head 会失败；当前 0017 仍不满足审批条件，不能把测试通过或 WIP 文件当成发布能力。ORM、迁移对象、AI draft/AgentRun 数据保留/删除和生产 wiring 尚未完成。
- **下一步与验收**：ADOM/AAIR/ARCH 必须二选一并留证：①补 ADR、`governance/MIGRATION_MANIFEST.yaml`、ORM/表/索引/CHECK 对象清单、Fresh Postgres upgrade/downgrade/re-upgrade 后再纳入 0009→0017；或 ②在批准前移出/隔离 0009-0017，恢复 0008=159 责任边界。两种路径都要求单 head、未知 head 失败，不能简单改常数。

### 3.3 AAIR-5 Context 删除 Worker

- **证据**：`backend/intelligence/context_engine/deletion.py` 与 `test_deletion_worker.py` 定向 7 项通过；具备租户隔离、幂等冲突、失败重试和审计事件。
- **缺口/风险**：`_jobs`/`_audit` 和 `ContextBroker` 为进程内存，重启丢作业；没有 durable queue/outbox/lease/DLQ，也没有媒体、向量、缓存等外部投影删除回执。因此不能声称完成生产删除或外部 provider deletion。
- **补测与验收**：增加 Postgres job/outbox、抢占租约、重启恢复、DLQ、全 data-class projection cascade 和审计关联测试；在此之前明确 `adapter-only/RELEASE BLOCKED`。

### 3.4 AAIR-6 Durable Deletion 返工复核

- **证据**：新增 `backend/intelligence/context_engine/durable_deletion.py` 和 `tests/intelligence/context_engine/test_durable_deletion.py`；durable 子集 6 项通过，新增 Async/SQL Context 后整个 `tests/intelligence/context_engine` Fresh 结果为 **25 passed**（旧 worker/durable + async/sql context），Ruff 对 context 文件通过。此前敏捷计划记录的“13/18 passed”已过时，不改变能力等级。契约覆盖 lease、retryable/dead-letter、租户幂等、五类 projection receipt 和未确认回执拒绝。
- **状态**：`CONTRACTED / adapter-only`，不是 `INTEGRATED` 或 `PRODUCTION`。`InMemoryDurableDeletionStore.production_ready = False`，job/audit/dead-letter 仍在内存；没有 Postgres/outbox、跨进程抢占、真实文本/媒体/向量/缓存/derived adapters，也没有生产 wiring。
- **风险与验收**：重启仍会丢队列状态，外部删除只能由注入 port 自行保证。AAIR 必须提供 SQLAlchemy/Postgres store、事务 outbox、lease/重试/DLQ、每类 projection 的真实删除回执和审计关联，或在发布清单中保持 `RELEASE BLOCKED`。在此之前不能把 6 项测试通过描述为删除能力已上线。

### 3.5 APLT-2 SEC-01 生产 dev_auth 复核

- **证据**：`backend/apps/family_api/main.py` 已改为只在允许的 dev/test 环境挂载 `dev_auth_router`；`tests/apps/family_api/test_production_dev_auth_gate.py` 2 项通过。`AIFAMILY_ENV=production` 时 OpenAPI 不含 `/auth/account-session`，POST 返回 404；`AIFAMILY_ENV=test` 仍保持 synthetic 合同并返回 200。
- **结论**：SEC-01 的“生产不暴露 dev_auth”切片为 `CONTRACTED/PARTIAL`，未越界修改其它战场；但不能升为 P0 已关闭。未设置 `AIFAMILY_ENV` 时仍因 `current_environment()` 默认 `development` 而挂载 dev_auth，ENV-01 仍是 P0。
- **功能同构风险**：生产现在返回 404，而 dev/test 使用 `/auth/account-session`，尚无真实认证替代端点。安全负向测试正确，但必须由 ARCH/PLT 明确同路径真实认证契约或 ADR 记录端点差异；“删除生产功能”不能作为测试/生产阉割。
- **附带质量债**：创建 app 时仍出现 service journey duplicate operation ID warning，应由 API/ARCH 纳入 OpenAPI 契约闸门。

### 3.6 DB-01 最新 head 漂移：0011-0017 Agent、Task 与成长扩展

- **证据**：当前 `uv run alembic heads` 输出 `0017_ai_model_attempts (head)`；`0011_ai_human_task_claims.py` 至 `0017_ai_model_attempts.py` 均为工作树 revision，尚未形成 tracked/审批链。0010 已登记并在本轮测试跳过，0011-0017 分别改变 Human Gate/AgentRun、授权租约、工具 outbox、成就投影、成长入营和模型尝试数据所有权与删除语义。
- **当前闸门**：DB-01 测试已显式允许 0008→159，0009+ 只有 migration 文件已 tracked 且 ADR/manifest 审批完成才可 allow-list；对未追踪或未知 head 必须失败，不能 skip。当前 Fresh Postgres 为 **8 passed、1 failed、1 skipped**，失败为未知 0017 head。
- **风险与验收**：不能把当前 head=0017 或测试通过描述为 schema 完成。ADOM/AAIR/ARCH 必须完成 ADR、manifest capability、ORM/表/索引/CHECK/回滚/留存删除对象清单和 Fresh Postgres upgrade/downgrade/re-upgrade；或在批准前移出/隔离 0009-0017。让 allow-list 同时验证 tracked 文件和 registry 状态；未知 head 必须失败。

### 3.7 Web Experience Client 身份契约复核

- **证据**：`frontend/web/src/api/httpClient.ts` 的 68fc0ce/d403998 已为请求注入 `Authorization`、`X-Session-Id` 和 request locale（scope.locale 优先），Web Vitest **22 passed**、typecheck 0；但 `frontend/web/src/App.tsx` 的真实登录/身份组合仍未接线。后端 dev resolver（`backend/apps/family_api/dev_wiring.py:_dev_experience_runtime_resolver`）从 Bearer 解析账户/家庭，production resolver 应同样完成身份、租户和同意校验。
- **缺口/风险**：现有 Web tests 只用 fake fetch，未断言 Authorization；真实受保护运行时会 401/503。请求 body 正确剥离 scope/provider 控制字段，但仅靠 URL family_id 不能证明调用者身份，当前纵向切片与功能同构/租户红线未闭合。
- **补测与验收**：用 synthetic app dependency + TestClient 验证无 token=401、有 token=成功、跨 family=403；Web client 22 项测试已断言 token/session/locale，但仍需 backend 真实 401/403/撤回同意；OpenAPI/client schema parity 通过。不能恢复把 tenant/provider/scope 放回客户端 body 的旧做法。

这些意见已分别发送给 ADOM-2、AFE-1，并由 Lead 转交 APLT-1、AQA-1、AGOV-1、AAIR-5。未收到返工命令和新鲜输出前，不更新为 DONE。

### 3.8 GROWTH S05→S08→年度/续购闭环复核

`ccd3d87` 的原始 journey 切片曾在 journey 内创建第二个 `ServiceCase` 聚合，并以非空
字符串代替共享故事/服务交付的实时同意。`b431eda`、`78cb9c1` 和 `dcc0802` 已将输出改为
`ServiceCaseCommand`→canonical service port 与 `ServiceDeliveryReceipt`，补 human actor、
ConsentGate（story/recommendation/annual/delivery）和完整 deletion refs。新鲜测试：无 DB
`tests/domains/journey -q` **40 passed、4 skipped**；带 Fresh Postgres URL **44 passed**。

结论是 **GO（测试分支契约）/CONTRACTED-PARTIAL（生产前置）**：`GrowthOutcomeLoop` 仍
`production_ready=False`，全部状态/idempotency 在内存，未挂 Journey HTTP、ORM、同事务
Audit/Outbox、跨进程 worker、真实 Account/Membership/Family/ConsentRecord。ServiceCase
command 也尚无真实 sink，不能把 REQUESTED/DELIVERED 值对象当成 FGCN 履约、质量、争议或
贡献结算。该切片不改变 S07/S08 在应用 ledger 中的 PARTIAL/NOT_IMPLEMENTED，生产仍 NO-GO。

### 3.9 Experience SQL ledger 与 composition hook 复核

`128fb57`/`4924506` 新增 `CommittedExperienceRunLedger`、`SessionPerCallExperienceRunLedger`
和 preflight/finalize/replay 的 session 边界；`3f56089` 仅允许 `create_app` 接受显式的
非-synthetic resolver，并拒绝 SyntheticRuntimeResolver。新鲜 `tests/intelligence/experience`
与 wiring 测试合计 **220 passed、1 warning**，说明 SQLite/适配器契约部分通过，P4
runtime contract 已在 synthetic/in-memory 层通过；session close、幂等、DELETE scrub
和 replay 可运行。

但 `main.py`/`experience_wiring.py` 没有创建 SQL `AsyncSession` factory、真实
Account→Tenant→Family/ConsentGate、Audit/Outbox 或 provider policy；生产不传 resolver 时
仍 503，dev/test 继续使用进程内 synthetic ledger。尚无 FastAPI+Postgres 的 401/403、跨租户、
并发幂等、回滚、重启 replay、外部删除回执证据，故状态 **CONTRACTED/PARTIAL，P1 发布阻断**。

`941feae` 仅校验 feedback 中 benchmark ref 的 namespace，`a11f643` 才把 media-free
evaluation projection 追加到 durable run ledger，并强制 `education_outcome_status` 为
`NOT_MEASURED`；`96905db` 新增 sync/async `persist_evaluation_projection` coordinator，
仍只调用 Run ledger。当前 ref 仍未 lookup EvalReport registry、未绑定 case/model/candidate/
provenance/tenant/locale/consent，且无独立 HTTP endpoint；质量指标不得作为教育 Outcome/Fact
或 provider admission。`69f6508` 的 `EvaluationReleaseGate` 虽增加阈值闸门，但与已有
`backend/intelligence/evaluation/release_gate.py:AiReleaseGate` 重复，前者不查 ProviderRegistry；
当前 `uv run pytest tests/intelligence/evaluation tests/intelligence/experience -q` **220 passed、1 warning**
（P4 media/share/achievement runtime contracts 已在 synthetic/in-memory 层通过）不代表唯一准入真相。该部分保持 **CONTRACTED/PARTIAL，P1**，需合并为唯一 gate，并补
unknown/mismatch/revoked/deleted/跨租户/replay 拒绝与审计删除回执。

`674b764` 仅强化 gate 输入 fail-closed（可进测试分支）；`050361f` 仅补 SQLite projection
持久化测试；`b3fffbb` 引入 production resolver 但其 API resolver 仍无 Authorization/ActorContext
入参，新增 TestClient 无 token 仍可 200。`3a455ed` 只收紧 staging/production 环境，`4b2273b`
只验证 provider failure 后 preflight 可重试，均不等于真实生产身份、PG、Audit/Outbox 或删除闭环。
`5df865e` 新增请求级 principal/trusted family/ConsentGate 组合 resolver，3 项单测通过，但
尚未接到 route/main.py 的 request auth dependency，故只能 `CONTRACTED/PARTIAL`。`eb33c06`
再将 ModelDraft generation 放入 `SqlAlchemyUnitOfWork`，同一 session 的 commit/rollback 更
清晰；但 Run ledger 仍为独立 SessionPerCall，UoW 未写 Audit/Outbox，Draft+Run 不是原子事务。
相关 production/trusted/experience 定向测试为 **220 passed、1 warning**，仍不足以证明生产闭环；
P4 media/share/achievement contracts 虽已通过 synthetic/in-memory 测试，仍没有 durable 生产实现。
这些提交作者均为本地 `Claude Code`，无可识别在线 owner；在 canonical gate/registry/production
composition 验收前冻结新增 evaluation/release-gate/report-persistence 代码。

### 3.10 ENV-01 owner 与冲突 WIP

APLT 复核确认 `backend/apps/family_api/dev_wiring.py` 含 commerce/family_need/experience/
tenant 等他人未提交 WIP，无法安全接手或在其中直接修 unset 环境默认值。当前
`current_environment()` 缺失变量仍默认为 development，real auth/session/tenant/consent
等价能力也未指定 owner；该 P0 记录为 **BLOCKED（owner 未明确/战场冲突）**，不是已完成。
原 WIP owner 必须先收口，再提交 unset/prod/test 负向启动、OpenAPI/401/403 和三环境 parity
证据；在此之前任何 dev_auth 404 切片不得关闭 ENV-01。

### 3.11 02a80c4/6a88625/6150169 Context 异步与 SQL 适配器

`02a80c4` 新增异步 Context port/线程适配器，`6a88625` 新增 SQL observation/snapshot
三表模型，`6150169` 修复跨会话 replay 的 scope 元数据；Fresh
`uv run pytest tests/intelligence/context_engine -q` 当前 **25 passed**，新增文件 Ruff clean。
`9b10d2d` 的 disposable Postgres probe 当前 **1 passed**，但仍以 `metadata.create_all` 临时
schema 和同一 engine 验证 append/snapshot/read/delete，不包含 Alembic、应用重启或 production
composition 证据。
这些提交改善了 Context/Memory 的应用边界，但 SQL 表仅在测试 fixture 通过
`metadata.create_all` 创建，尚无 Alembic/Manifest/ORM 登记、production resolver/main 接线、
跨 store 事务、ConsentRecord 撤回版本、Audit/Outbox 或媒体/向量/缓存删除回执；`read()`
重建 scope 仍固定 `consent_granted=True`。结论为 **CONTRACTED/PARTIAL，P1**，不能将
`durability_mode=DURABLE` 或 25 项测试解读为生产权利履行。验收需 Fresh Postgres migration、
restart/concurrency/replay、401/403/撤回同意、audit/outbox 与完整删除收据后再提升等级。

### 3.12 P4 多模态分享/成就合同红灯

当前 `tests/intelligence/experience/test_p4_media_contract.py` 与相关实现已纳入工作树，
`uv run pytest tests/intelligence/evaluation tests/intelligence/experience -q` 当前 **220 passed、1 warning**；
`573a86d`/`a91ad3a` 已补齐 `MediaAsset`、`MediaTranscript`、`MediaEvidence`、
`FamilyContentShare` 及 `Achievement.basis/visibility/comparison_scope/commercial_reward`，并通过
synthetic/in-memory contract tests。P4 红灯已关闭为测试契约层，但没有 durable media/achievement
ORM、外部删除回执或 production composition，状态仍 **CONTRACTED/PARTIAL/P1**，不能升为生产。

### 3.13 0ca62d2 会员权益/贡献经济合同复核

`0ca62d2 feat(membership): harden entitlement lifecycle contracts` 为会员权益生命周期补充
租户/家庭作用域、幂等冲突、人工 actor 和 repository/UoW 合同。Fresh Postgres 下
`uv run pytest tests/domains/membership -q`（含 security contract）当前 **50 passed、1 warning**，
证明合同和 SQL 适配器测试层可运行；但尚无 production API/main 组合根、真实 Account→Membership→Family
身份链、Consent/审计/outbox/退款与删除回执，不能将会员/贡献经济蓝图的 DESIGN_ONLY 提升为生产商业能力。
状态为 **CONTRACTED/PARTIAL，P1**；下一步必须补真实 HTTP+Postgres、跨租户/撤回同意/重放和结算审计，
同时保持贡献账、权益账、现金账分离，禁止家庭总分/排名或未经验证的贡献写入。

### 3.14 0cd53fb/6b4a8e9 Growth Onboarding HTTP/PG 纵切片复核

`0cd53fb` 新增 GrowthIntent→GrowthOnboarding 领域、fake/SQL repository 与同事务 audit/outbox/idempotency；
`6b4a8e9` 新增 Family API route 和显式 dev/production 安装器，路由不在 handler 内创建 adapter。
无 DB 的 journey/route 定向测试可运行，Fresh Postgres 批量首跑曾出现一次
`actor_family_scope_denied`（43 项通过后失败），同一用例隔离重跑通过，说明测试/fixture 隔离仍需稳定性证据。
此外 `growth_onboarding_intent_binding` 对应 migration 0016 和 0017 目前未形成 tracked/Manifest/ADR/ORM 审批链。

结论：**GO（契约测试）/CONTRACTED-PARTIAL（测试候选）/NO-GO（生产）**。HTTP 默认依赖 fail-closed 503，
显式生产安装器才使用 PostgreSQL identity resolver；main.py 的环境挂载仍受未收口的
`is_dev_environment()` 默认值影响。必须补三环境无 token=401、跨租户=403、撤回 consent=403、非法 UUID=400，
重复 PG 稳定运行与 0016/0017 migration 审批后，方可提升状态。

### 3.15 cbc055e/736ae19 安全验收契约复核

`cbc055e` 的 ADR-0069 和 auth error mapping 测试锁定了 AIFAMILY_ENV 显式 allow-list、
Experience 401/403/CONSENT_REQUIRED 语义；`736ae19` 允许不安全环境在启动时以异常 fail-closed，
但当前 unset `AIFAMILY_ENV` 仍会落入 development，因此 acceptance 用例按设计保持红灯直到 ENV-01 owner 收口。
这些仅是独立验收合同，未修改 `dev_wiring.py`/`production_experience_wiring.py`，未证明真实 auth/session/tenant/consent。
状态 **CONTRACTED/PARTIAL，P0 BLOCKED**；生产仍 NO-GO。

## 4. P0/P1/P2 执行清单

验收证据必须是可复现命令输出、实际文件或 Fresh Postgres 结果；设计文档、synthetic adapter、单元测试通过只能标记契约阶段。

### P0（发布阻断）

| ID / owner | 任务与前置条件 | 验收证据 | 架构层 |
|---|---|---|---|
| SEC-01 / APLT-1 + ARCH-1 | 移除生产 dev_auth；先统一真实会话/身份端口，再保留 dev/test synthetic 适配器。 | production `app.openapi()` 无 `/auth/account-session`；POST 返回 404/403；任意 external_ref 不可换 token；dev/test 功能路径仍同构。 | 平台安全、应用、数据治理 |
| ENV-01 / APLT-1 + 原 WIP owner（未明确） | 统一 `AIFAMILY_ENV`（或 ADR 指定唯一变量），缺失/拼写错误/非法值 fail-closed，启动时拒绝错误 wiring。当前 `dev_wiring.py` 有并发 WIP，项目助理不能越界接手。 | 未设置或 `APP_ENV` 单独设置时启动失败；production wiring 不含 fake；dev/test 明确 synthetic data_class；环境 parity 测试通过。owner 未明确前保持 BLOCKED。 | 平台、部署、治理 |
| ID-01 / PLT + DOM | 实现 Account→TenantMembership→Family 绑定、会话撤销、tenant 状态和主体授权；接入 Consent grant store、withdraw/expiry 即时生效。 | Fresh Postgres CRUD、跨租户负向测试、撤销/过期测试、审计记录；所有生产依赖不再 RuntimeError/DenyAll。 | 身份、租户、业务数据、合规 |
| EXP-AUTH-01 / APLT + API + AAIR（owner 待明确） | 将 `AuthenticatedExperienceScopeResolver` 接入 `ProductionExperienceRuntimeResolver` 和 FastAPI request auth；区分未认证 401 与已认证跨租户/撤回 403；补 durable consent/version/revocation。 | no-token/invalid-token=401；cross-family/withdrawn=403；同一 scope/error parity across dev/test/prod；Fresh Postgres identity+consent+replay/deletion；b3/5df/ff/ebae 仅契约，不关闭 P0。 | 平台身份、应用、AI、数据 |
| DB-01 / ADOM + DATA + AAIR | 处理 migration 0004-0008 与未跟踪 0009-0017 的边界；补 ORM/迁移清单和回滚契约。 | upgrade/downgrade/re-upgrade、单 head；baseline/0008 测试全绿（0008=159）；0009-0017 新计数只有在 manifest/ADR/模型清单登记后才可作为 head，未知/未登记 head 失败。当前 head=0017，Fresh Postgres 8 passed/1 failed/1 skipped。 | 数据、领域、交付、AI |

### P1（本迭代必须完成）

| ID / owner | 任务与前置条件 | 验收证据 | 架构层 |
|---|---|---|---|
| QA-01 / AQA + GOV | 修 DOMAIN_REGISTRY YAML、lint debt、未登记源目录；CI 加 architecture/ruff/migration gate。 | `uv run pytest tests/architecture -q`、`uv run ruff check .` 绿；CI required checks 绿；main branch protection 生效。 | 治理、质量 |
| CONTRACT-01 / API + AFE | 从 FastAPI 生成 OpenAPI，校验移动端/Web client 方法、路径、认证头、参数/错误 schema；重建 endpoint inventory。 | CI 兼容检查；55 条路径与 client 逐项有 owner/状态，受保护请求含统一 session/token；移动端全量 Vitest 0 failures。 | API、应用、体验、安全 |
| PERSIST-01 / DOM + DATA | service/membership/commerce/family_need repository/UoW 接入 Postgres、同意、actor、tenant 解析。 | 每域成功/拒绝/重放/删除/审计 Fresh Postgres 测试；生产路径无 fake fallback。 | 数据、领域、应用 |
| AI-01 / AAIR + PLT | Principal→reviewed knowledge→Model Gateway→Draft→Human Gate 完成一个低风险用例；持久化 run/context/gate。 | 不直接写事实；draft/review/approve/reject/replay 可追踪；provider admission 和成本/质量记录；registry 仅凭证据升阶。 | AI、平台、合规 |
| DATA-01 / AAIR + DATA | 将 AAIR-6 的 adapter-only durable deletion 升级为 Postgres/outbox durable job；定义文本、媒体、向量、缓存、derived projection 的级联回执。 | 重启恢复、租户隔离、幂等、租约重试、DLQ、审计 correlation 的集成测试；未完成项显式阻断。当前 `InMemoryDurableDeletionStore` 仅 CONTRACTED。 | 数据、AI、合规 |
| UX-01 / AFE + QA | 扫描 34 个基线及新增语义路由，移除所有可见内部编号，补四端视觉/动效/可访问性回归。 | 全量 check/test 绿；无 `UI-xx` 可见文本；Android/iOS/Harmony/小程序/Web 证据；情绪价值优先且无家庭总分/排名。 | 体验、应用、治理 |
| GROWTH-01 / GROWTH + DOM + API | 将 S07 行动事实→S08 结果→年度复盘/续购接入 canonical service port、Journey ORM/API、Audit/Outbox。 | 当前 contract 40/4（Postgres 44）仅可进测试；需 HTTP/PG/replay/consent/deletion/worker 和 UI vertical e2e，保持无分数/排名。 | 业务、流程、数据、应用、AI |
| EXPERIENCE-01 / AAIR + API + PLT | 将 SQL run ledger/session adapter 接入 production-like composition root，统一身份、租户、同意、审计和删除。 | 当前 experience+wiring **220 passed、1 warning**，仍为契约（P4 contracts 仅 synthetic/in-memory green）；需 FastAPI+Postgres 401/403、并发幂等、重启 replay、audit/outbox、五类 deletion receipts。 | AI、应用、数据、平台 |
| EVAL-REF-01 / AAIR + API | 合并 `multimodal_eval.py:EvaluationReleaseGate` 与既有 `backend/intelligence/evaluation/release_gate.py:AiReleaseGate` 为唯一 canonical gate，并为 benchmark feedback/evaluation projection 接入 EvalReport registry lookup、审批和版本/主体绑定。 | 当前 941feae/a11f643/96905db 只校验 namespace、`NOT_MEASURED`；674/69 双 gate 与 coordinator 测试使 evaluation+experience **220 passed、1 warning**，但未证明唯一准入。需 unknown/mismatch/revoked/deleted/跨租户拒绝、provenance/locale/consent/audit/replay，禁止写 Outcome/Fact。 | AI、数据、治理 |
| CONTEXT-ASYNC-01 / AAIR + PLT | 将 `AsyncSqlContextBroker` 从 SQLite fixture 提升为生产 Context/Memory store，接入 Consent/tenant、migration、audit/outbox、删除回执。 | 当前 02a80c4/6a88625/6150169 context-engine 25 passed 仅 adapter；需 Fresh Postgres upgrade/downgrade/restart、撤回/跨租户/并发 replay、媒体/向量/缓存 deletion receipts，且 production resolver/main wiring 可追踪。 | AI、数据、平台、合规 |

### P2（发布前或规模化前）

| ID / owner | 任务与前置条件 | 验收证据 | 架构层 |
|---|---|---|---|
| NODE-01 / ARCH + API | ADR 决定 Node/Express/tRPC/MySQL 模板删除或严格限定为 UI 工具。 | 边界测试证明正式事实只走 Python/FastAPI/Postgres；无 MySQL 写入生产业务。 | 技术、应用 |
| LEGAL-01 / GOV | 添加 SPDX/许可证、第三方依赖和 UI/媒体资产授权清单。 | 根目录 license、`pyproject` SPDX、CI license scan、公开仓库授权说明。 | 治理、合规 |
| OBS-01 / AAIR + QA | 统一 AI trace、评测集、成本、延迟、拒答/人工门通过率和数据删除观测。 | 可回放 trace、模型/提示版本、质量阈值、告警和审计查询。 | AI、运维、数据 |
| SCALE-01 / PLT + DATA | 多租户、多语言、多区域、配额和灾备设计落到分区/缓存/路由策略。 | 租户越权压测、locale fallback、区域隔离、配额/成本预算、RTO/RPO 演练。 | 平台、数据、全球化 |

## 5. 未来两周项目助理看板建议

### 第 1 周：先恢复发布闸门

1. SEC-01、ENV-01：生产负向 OpenAPI/404/启动测试，P0 每日复验。
2. QA-01：修 Registry 语法和登记，清零 Ruff/architecture 红灯，启用 CI required checks。
3. DB-01：明确 baseline/0008/head，Fresh Postgres 迁移可逆；冻结未经登记的 schema 改动，特别是 `0009_ai_model_drafts.py`、`0010_experience_run_interactions.py`、`0011_ai_human_task_claims.py`、`0012_ai_agent_runs.py`、`0013_ai_authorization_leases.py`、`0014_tool_action_outbox.py`、`0015_ai_achievement_projections.py`、`0016_growth_onboarding_intent_binding.py` 与 `0017_ai_model_attempts.py`。
4. ID-01 起步：会话、tenant、family、consent 数据模型和审计事件；禁止用 fake 结果替代接口。
5. AFE/AAIR 返工验收：全量移动端测试和删除 worker adapter-only 声明。

### 第 2 周：打通一条可审计生产候选闭环

1. PERSIST-01：至少 service + membership 两域连接真实 UoW、同意和租户绑定。
2. CONTRACT-01：OpenAPI/client/schema CI 和 endpoint inventory 一次生成。
3. AI-01 + DATA-01：一个 Principal 低风险草案经 Human Gate，run/context/gate/deletion 全链路可回放；Experience SQL ledger 仅在真实 composition 接线后升阶。
4. UX-01：语义 UI、游戏化成就、动效/多模态和四端回归证据。
5. GROWTH-01：以当前 44 项 Postgres journey 契约为起点，补 ServiceCase canonical sink、Journey HTTP/ORM、Audit/Outbox、consent/replay/deletion 和 UI vertical e2e。
6. 周末评审：逐项把 PARTIAL 变为 EVIDENCE-BACKED，仍有 P0 即 NO-GO；P1 例外必须有 owner、期限和风险接受记录。

## 6. 不可接受的发布阻断项

- 生产 OpenAPI 可见或可调用 dev_auth、任意 external_ref 换 token，或 token 是硬编码未来日期。
- 环境变量缺失时默认 development，或 production wiring 可落到 fake/in-memory/synthetic adapter。
- 无持久化 Account→TenantMembership→Family、Consent grant/withdraw/expiry、session revoke、租户隔离和审计。
- migration 无法在 Fresh Postgres upgrade/downgrade/re-upgrade，存在多 head、ORM/迁移清单未解释漂移。
- architecture/Ruff/CI 红灯，或 branch protection 未生效却声称可发布。
- AI 直接写业务事实、绕过 Model Gateway、没有 draft/human gate/audit/replay，或把 provider 未获准当作已上线。
- 删除能力只能删内存，不能证明文本/媒体/向量/缓存等投影级联和审计回执。
- 可见 UI 内部编号、家庭总分/家庭排名、跨端核心流程不一致，或移动端全量测试失败。
- 公开仓库没有许可证/资产授权，或多租户、多语言、区域数据边界未定义而开始真实用户迁移。

## 7. 与当前敏捷计划对齐

本文件不是替代业务、流程、数据、应用或 AI 架构，而是把它们变成 delivery gate：商业蓝图的家庭测评→AI 诊断→方案→21/90 天交付→结果沉淀，对应业务流程、持久化事实、应用端点、Principal/Context/Human Gate 和移动端体验。每个 Sprint 必须带成功、拒绝、重放、删除、租户隔离、审计和四端体验证据。

当前敏捷计划中的 Sprint 2/2.1 垂直切片可以继续，但在 P0 未清零前只能标记“契约/测试环境完成”，不能标记生产完成。下一阶段以本文件 P0→P1 顺序进入 Sprint 3：先环境与身份闸门，再真实持久化和 API 兼容，最后扩大 AI 与 34 UI 的游戏化体验。任何新增场景必须同时更新业务/流程/数据/应用/AI traceability，不得脱离总设计单独堆 UI。
