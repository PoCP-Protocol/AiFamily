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

本轮结论：**NO-GO**。以下 P0 必须先清零：生产环境仍可暴露开发登录；缺少环境变量时会默认开发 wiring；身份、租户、家庭绑定和同意存储仍未持久化；测试闸门当前红灯。任何 synthetic adapter 通过测试都不等于生产能力。

证据采集日期为 2026-08-30。工作区有其他 Agent 的未提交 WIP，本文件只记录从当前磁盘、Fresh Postgres、Fresh 测试命令和远端 CI 重新取得的证据。

## 2. 报告结论逐项核验

状态含义：

- **仍成立**：风险在当前代码中可以复现。
- **部分成立**：原问题的一部分已改善，剩余部分仍阻断交付。
- **已过时**：报告的具体数字或文件状态已被当前实现改变；不代表能力已生产化。
- **证据不足**：当前没有足够证据声称已完成。

| Manus 结论 | 当前状态 | 当前证据与判断 | 后续动作 |
|---|---|---|---|
| dev_auth 无条件挂载、可任意签发会话 | **仍成立，P0** | `backend/apps/family_api/main.py` 无条件 `include_router(dev_auth_router)`。设置 `AIFAMILY_ENV=production` 后，OpenAPI 仍有 `/auth/account-session`，POST 任意 `external_ref` 返回 200，令牌过期时间为 2099 哨兵值。 | APLT/ARCH：生产 OpenAPI 删除 dev route；生产请求 404/403；使用真实身份会话和负向测试。 |
| 环境默认 development、APP_ENV 与 AIFAMILY_ENV 不一致 | **仍成立，P0** | `backend/apps/family_api/dev_wiring.py:115-120` 缺少 `AIFAMILY_ENV` 时返回 `development`；仅设置 `APP_ENV=production` 仍为开发环境。 | APLT/ARCH：统一变量；缺失、拼写错误或未允许值必须 fail-closed；启动和路由负向测试。 |
| Ruff 398、CI 红、无分支保护 | **仍成立（历史数字已过时），P1** | 当前 `uv run ruff check .` 仍失败（本地 E501 1 项）；`uv run pytest tests/architecture -q` 为 106 passed、1 skipped、4 failed；远端最新 CI run `33291355462` 仍有 I001；GitHub main branch protection 返回 404。历史“398”不再是当前计数。 | AQA/GOV/ARCH：修复 YAML、lint debt、登记漂移；CI 必跑并启用分支保护。 |
| 文档、Registry 与代码漂移 | **仍成立，P1** | `governance/DOMAIN_REGISTRY.yaml:452-453` 当前 YAML 缩进错误；`product_management` 和 `__pycache__` 触发未登记检查；`CURRENT_SYSTEM_BASELINE.md` 仍写“zero business APIs”，与当前 FastAPI 55 条路径不符。 | GOV/ARCH：修复语法和登记，建立源代码/Registry/文档快照校验；历史文档降级为非事实来源。 |
| 移动端 46 API 与后端契约不一致 | **仍成立（46/11 数字已过时），P1** | 当前 FastAPI OpenAPI 有 55 条路径；移动端 client 仍包含 dev/test 路径。`pnpm check` 通过，但全量 Vitest 为 2 个文件、5 个失败（Registry 数量、旧 service query/body、UI-02 旧文案）。尚无 OpenAPI 导出与 client 方法、路径、JSON schema 的持续兼容检查。 | API/AFE/ARCH：生成规范并在 CI 对比 client；更新或删除陈旧库存；全量移动端绿灯。 |
| AI 只有基础设施、没有业务能力 | **已过时代码描述，风险仍成立** | 当前已有 `backend/intelligence/principal`、`human_gate`、`experience`、`knowledge` 和多项契约测试；Principal 仍输出 `DRAFT`，Model Gateway 没有获准外部 provider，`AI_USE_CASE_REGISTRY.yaml` 全部为 `PLANNED`，Context/Memory 与 Human Gate 尚未形成生产持久化和正式 HTTP 闭环。 | AAIR/ARCH：先完成一个低风险、可回放、人工确认的生产候选闭环，再把 registry 状态改为 evidence-backed。 |
| Node/Express/tRPC/MySQL 模板越过 Python 后端边界 | **仍成立，P2** | `frontend/mobile/package.json` 和 `server/_core` 仍有 Express、tRPC、Drizzle、mysql2。它们是否是可删除模板尚未有 ADR 和边界测试；R1 规定正式业务后端为 Python/FastAPI/PostgreSQL。 | ARCH/API：做 ADR；删除或明确仅本地 UI 工具，禁止承载正式业务事实。 |
| 公共仓库缺许可证 | **仍成立，P2** | 根目录没有 LICENSE/COPYING/SPDX，`pyproject.toml` 无许可证字段；公开远端仓库仍可访问。 | GOV/LEGAL：补 SPDX/许可证与第三方资产清单，或在发布前改私有并记录授权。 |
| Alembic 基线/迁移链失败 | **部分成立，当前有新增 WIP** | 原报告的 `0005` 长度问题已由 `0005_fgcn_assignment_idempotency` 修复；Fresh Postgres 下 0004→0008 `test_fgcn_migration_chain.py` 2 passed，upgrade/downgrade/re-upgrade 成功且单 head。当前工作区又出现未跟踪 `database/migrations/versions/0009_ai_model_drafts.py`（0008→0009），head 变为 0009、160 表；0009 尚未登记/提交，不得视为完成。 | ADOM/AAIR/ARCH：保留 0004-0008 的固定边界（159 表），head 只允许显式映射 0008→159 或已登记 0009→160；未知 head 必须失败。维护 ORM/迁移对象清单，不得只改数字掩盖漂移。 |
| 身份、同意、租户/家庭绑定及持久化不完整 | **仍成立，P0/P1** | service/membership/commerce production dependencies 仍在 session factory、actor/context、tenant directory 或 repository 未配置时拒绝；identity 只有 `DenyAllTenantDirectory`/`InMemoryTenantDirectory`；consent 只有无状态 gate，没有 grant store；family_need 仅 fake repository。 | PLT/DOM/DATA：实现 Account→TenantMembership→Family、Consent store、审计和真实 UoW；任何生产路由不得落到 fake。 |

## 3. 本轮独立反向审查（已发 owner，等待返工）

项目助理不采信“完成”口头汇报，逐项核查交付物。以下意见已通过协作消息发给对应 owner，并同步给 Lead；在返工证据返回前标记为 **PARTIAL**：

### 3.1 AFE-4 服务体验列表

- **证据**：`frontend/mobile/components/family/family-experience-list.tsx` 使用语义图标、阶段和成就文案，未把 `UI-xx` 渲染为可见标签；`family-experience-list.test.ts` 定向 5 项通过，`pnpm check` 通过。
- **缺口/风险**：仅覆盖 services surface；全量移动端仍有 5 个失败，UI-19～34 其它列表和 `family-screen-list.tsx` 未完成跨端视觉/语义编号扫描。
- **补测与验收**：`cd frontend/mobile; pnpm check; pnpm test -- --run` 必须 0 failures；新增 app/components 可见文本扫描和 Android/iOS/Harmony/web golden/e2e；内部 ID 只能留在 registry/导航。

### 3.2 ADOM-5 FGCN 迁移链

- **证据**：DB-01 提交 `981343b` 后 Fresh Postgres 下 `tests/database/test_alembic_baseline_applies.py` 3 passed、`tests/database/test_fgcn_migration_chain.py` 2 passed；0001 baseline、0008 固定边界与动态 head 已分层，0008=159 表。当前工作区新出现未跟踪 `database/migrations/versions/0009_ai_model_drafts.py`，head=0009、160 表；`governance/ADR/ADR-0045-durable-model-draft-provenance-registry.md` 与该 migration 均未正式提交，`MIGRATION_MANIFEST` 尚无 0009 capability 条目。
- **缺口/风险**：迁移测试显式允许 0008→159 或 0009→160，未知 head 会失败；但当前 allow-list 本身不验证 migration 文件是否已提交、ADR 是否已登记或 `MIGRATION_MANIFEST` 是否有 capability 条目，未登记的 0009 仍会改变动态 head，不能把测试通过或 WIP 文件当成发布能力。ORM、迁移对象、AI draft 数据保留/删除和生产 wiring 尚未完成。
- **下一步与验收**：ADOM/AAIR/ARCH 必须二选一并留证：①补 ADR、`governance/MIGRATION_MANIFEST.yaml`、ORM/表/索引/CHECK 对象清单、Fresh Postgres upgrade/downgrade/re-upgrade 后再纳入 0009→160；或 ②在批准前移出/隔离 0009，恢复 0008=159 责任边界。两种路径都要求单 head、未知 head 失败，不能简单改常数。

### 3.3 AAIR-5 Context 删除 Worker

- **证据**：`backend/intelligence/context_engine/deletion.py` 与 `test_deletion_worker.py` 定向 7 项通过；具备租户隔离、幂等冲突、失败重试和审计事件。
- **缺口/风险**：`_jobs`/`_audit` 和 `ContextBroker` 为进程内存，重启丢作业；没有 durable queue/outbox/lease/DLQ，也没有媒体、向量、缓存等外部投影删除回执。因此不能声称完成生产删除或外部 provider deletion。
- **补测与验收**：增加 Postgres job/outbox、抢占租约、重启恢复、DLQ、全 data-class projection cascade 和审计关联测试；在此之前明确 `adapter-only/RELEASE BLOCKED`。

### 3.4 AAIR-6 Durable Deletion 返工复核

- **证据**：新增 `backend/intelligence/context_engine/durable_deletion.py` 和 `tests/intelligence/context_engine/test_durable_deletion.py`；durable 子集 6 项通过，整个 `tests/intelligence/context_engine` 当前 Fresh 结果为 18 passed（旧 worker 7 + 其它 context 契约 5 + durable 6），Ruff 通过。此前敏捷计划记录的“13 passed”已过时，不改变能力等级。契约覆盖 lease、retryable/dead-letter、租户幂等、五类 projection receipt 和未确认回执拒绝。
- **状态**：`CONTRACTED / adapter-only`，不是 `INTEGRATED` 或 `PRODUCTION`。`InMemoryDurableDeletionStore.production_ready = False`，job/audit/dead-letter 仍在内存；没有 Postgres/outbox、跨进程抢占、真实文本/媒体/向量/缓存/derived adapters，也没有生产 wiring。
- **风险与验收**：重启仍会丢队列状态，外部删除只能由注入 port 自行保证。AAIR 必须提供 SQLAlchemy/Postgres store、事务 outbox、lease/重试/DLQ、每类 projection 的真实删除回执和审计关联，或在发布清单中保持 `RELEASE BLOCKED`。在此之前不能把 6 项测试通过描述为删除能力已上线。

### 3.5 APLT-2 SEC-01 生产 dev_auth 复核

- **证据**：`backend/apps/family_api/main.py` 已改为只在允许的 dev/test 环境挂载 `dev_auth_router`；`tests/apps/family_api/test_production_dev_auth_gate.py` 2 项通过。`AIFAMILY_ENV=production` 时 OpenAPI 不含 `/auth/account-session`，POST 返回 404；`AIFAMILY_ENV=test` 仍保持 synthetic 合同并返回 200。
- **结论**：SEC-01 的“生产不暴露 dev_auth”切片为 `CONTRACTED/PARTIAL`，未越界修改其它战场；但不能升为 P0 已关闭。未设置 `AIFAMILY_ENV` 时仍因 `current_environment()` 默认 `development` 而挂载 dev_auth，ENV-01 仍是 P0。
- **功能同构风险**：生产现在返回 404，而 dev/test 使用 `/auth/account-session`，尚无真实认证替代端点。安全负向测试正确，但必须由 ARCH/PLT 明确同路径真实认证契约或 ADR 记录端点差异；“删除生产功能”不能作为测试/生产阉割。
- **附带质量债**：创建 app 时仍出现 service journey duplicate operation ID warning，应由 API/ARCH 纳入 OpenAPI 契约闸门。

这些意见已分别发送给 ADOM-2、AFE-1，并由 Lead 转交 APLT-1、AQA-1、AGOV-1、AAIR-5。未收到返工命令和新鲜输出前，不更新为 DONE。

## 4. P0/P1/P2 执行清单

验收证据必须是可复现命令输出、实际文件或 Fresh Postgres 结果；设计文档、synthetic adapter、单元测试通过只能标记契约阶段。

### P0（发布阻断）

| ID / owner | 任务与前置条件 | 验收证据 | 架构层 |
|---|---|---|---|
| SEC-01 / APLT-1 + ARCH-1 | 移除生产 dev_auth；先统一真实会话/身份端口，再保留 dev/test synthetic 适配器。 | production `app.openapi()` 无 `/auth/account-session`；POST 返回 404/403；任意 external_ref 不可换 token；dev/test 功能路径仍同构。 | 平台安全、应用、数据治理 |
| ENV-01 / APLT-1 | 统一 `AIFAMILY_ENV`（或 ADR 指定唯一变量），缺失/拼写错误/非法值 fail-closed，启动时拒绝错误 wiring。 | 未设置或 `APP_ENV` 单独设置时启动失败；production wiring 不含 fake；dev/test 明确 synthetic data_class；环境 parity 测试通过。 | 平台、部署、治理 |
| ID-01 / PLT + DOM | 实现 Account→TenantMembership→Family 绑定、会话撤销、tenant 状态和主体授权；接入 Consent grant store、withdraw/expiry 即时生效。 | Fresh Postgres CRUD、跨租户负向测试、撤销/过期测试、审计记录；所有生产依赖不再 RuntimeError/DenyAll。 | 身份、租户、业务数据、合规 |
| DB-01 / ADOM + DATA + AAIR | 处理 migration 0004-0008 与未跟踪 0009 的边界；补 ORM/迁移清单和回滚契约。 | upgrade/downgrade/re-upgrade、单 head；baseline/0008 测试全绿（0008=159）；0009 只有在 manifest/ADR/模型清单登记后才可作为 head（0009=160），未知 head 失败。 | 数据、领域、交付、AI |

### P1（本迭代必须完成）

| ID / owner | 任务与前置条件 | 验收证据 | 架构层 |
|---|---|---|---|
| QA-01 / AQA + GOV | 修 DOMAIN_REGISTRY YAML、lint debt、未登记源目录；CI 加 architecture/ruff/migration gate。 | `uv run pytest tests/architecture -q`、`uv run ruff check .` 绿；CI required checks 绿；main branch protection 生效。 | 治理、质量 |
| CONTRACT-01 / API + AFE | 从 FastAPI 生成 OpenAPI，校验移动端方法/路径/参数/错误 schema；重建 endpoint inventory。 | CI 兼容检查；55 条路径与 client 逐项有 owner/状态；移动端全量 Vitest 0 failures。 | API、应用、体验 |
| PERSIST-01 / DOM + DATA | service/membership/commerce/family_need repository/UoW 接入 Postgres、同意、actor、tenant 解析。 | 每域成功/拒绝/重放/删除/审计 Fresh Postgres 测试；生产路径无 fake fallback。 | 数据、领域、应用 |
| AI-01 / AAIR + PLT | Principal→reviewed knowledge→Model Gateway→Draft→Human Gate 完成一个低风险用例；持久化 run/context/gate。 | 不直接写事实；draft/review/approve/reject/replay 可追踪；provider admission 和成本/质量记录；registry 仅凭证据升阶。 | AI、平台、合规 |
| DATA-01 / AAIR + DATA | 将 AAIR-6 的 adapter-only durable deletion 升级为 Postgres/outbox durable job；定义文本、媒体、向量、缓存、derived projection 的级联回执。 | 重启恢复、租户隔离、幂等、租约重试、DLQ、审计 correlation 的集成测试；未完成项显式阻断。当前 `InMemoryDurableDeletionStore` 仅 CONTRACTED。 | 数据、AI、合规 |
| UX-01 / AFE + QA | 扫描 34 个基线及新增语义路由，移除所有可见内部编号，补四端视觉/动效/可访问性回归。 | 全量 check/test 绿；无 `UI-xx` 可见文本；Android/iOS/Harmony/小程序/Web 证据；情绪价值优先且无家庭总分/排名。 | 体验、应用、治理 |

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
3. DB-01：明确 baseline/0008/head，Fresh Postgres 迁移可逆；冻结未经登记的 schema 改动，特别是 `0009_ai_model_drafts.py`。
4. ID-01 起步：会话、tenant、family、consent 数据模型和审计事件；禁止用 fake 结果替代接口。
5. AFE/AAIR 返工验收：全量移动端测试和删除 worker adapter-only 声明。

### 第 2 周：打通一条可审计生产候选闭环

1. PERSIST-01：至少 service + membership 两域连接真实 UoW、同意和租户绑定。
2. CONTRACT-01：OpenAPI/client/schema CI 和 endpoint inventory 一次生成。
3. AI-01 + DATA-01：一个 Principal 低风险草案经 Human Gate，run/context/gate/deletion 全链路可回放。
4. UX-01：语义 UI、游戏化成就、动效/多模态和四端回归证据。
5. 周末评审：逐项把 PARTIAL 变为 EVIDENCE-BACKED，仍有 P0 即 NO-GO；P1 例外必须有 owner、期限和风险接受记录。

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
