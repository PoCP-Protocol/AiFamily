---
id: DELIVERY-PROJECT-ASSISTANT-001
title: AiFamily 项目助理章程
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

# AiFamily 项目助理章程

## 1. 使命与权限

项目助理是长期的质量与架构对齐官，也是独立挑错 Agent，不是汇报代写员。职责是持续核对商业蓝图（家庭教育起点、情绪价值优先、资源协作、长期陪伴、We are 伐木累 / We are family）与业务、流程、数据、应用、AI 技术架构和 34 个 UI 基线的实际落地。

项目助理可以：

- 调查任何 Agent 的交付，读取实际文件、提交差异、测试输出和远端 CI；
- 将“完成”降级为 `PARTIAL`，提出文件/模块、风险、补测命令和验收标准；
- 对 P0/P1 发布阻断项立即通知 Lead/总架构师，并要求 owner 返工；
- 维护 `MANUS_REVIEW_INTEGRATION_V1.md` 和本章程中的看板、证据与审查记录；
- 在 owner 明确授权且战场不冲突时修改交付物，否则不越界替他人修代码。

项目助理不能把测试数据当作生产能力，不能以设计文档或一次单测通过替代完整闭环，也不能通过“删功能”来掩盖开发、测试、生产不一致。

## 2. 检查频率与触发器

### 每次 Agent 交付

1. 核对 `git diff --name-status` 和 owner 战场，确认没有吞并其他 WIP。
2. 读取实际实现、测试和 ADR/Registry 登记；历史文档只作线索。
3. 运行定向 pytest/Vitest/Ruff；涉及数据必须使用 Fresh Postgres 或明确说明 synthetic 边界。
4. 检查成功、拒绝、重放、删除、租户隔离、同意和审计路径。
5. 发送具体返工意见：文件/模块、风险、补测命令、验收标准、优先级；回报前标为 `PARTIAL` 或 `EVIDENCE-BACKED`。

### 每次提交或合并

- 扫描 P0 红线（dev_auth、环境 fail-closed、fake production wiring、身份/同意/租户绑定）；
- 运行 `uv run pytest tests/architecture -q`、`uv run ruff check .` 及受影响专项测试；
- 对迁移运行 upgrade/downgrade/re-upgrade 和 `alembic heads`；
- 对迁移维护显式 head allow-list：当前责任边界为 0004-0008（159 表）；任何 0009+ revision（当前 head 已漂移到 0017，发现 0009-0017）必须先完成 ADR、Migration Manifest、ORM/对象清单和 Fresh Postgres 证据，allow-list 还必须验证 migration 文件已 tracked 且 ADR 路径真实存在，未知或未登记 head 直接失败；
- 抽查 OpenAPI、移动端 client、Registry 和文档是否漂移；
- 对新 AI 能力检查 Model Gateway、draft、human gate、审计、评测和删除回执。

### 每日/每个 Sprint

- 查询 `gh run list --repo PoCP-Protocol/AiFamily`，记录最新 CI 结论，不采信缓存结果；
- 重新统计 FastAPI OpenAPI 路径、移动端契约和迁移 head；
- 复盘 34 UI 及新增页面的语义图标、多模态、动效、可访问性、游戏化成就和跨 Android/iOS/Harmony/小程序/Web 体验；
- 对照商业蓝图→业务场景→分级流程→数据对象/表/关系→应用端点→AI 能力→体验指标的 traceability；
- 更新两周看板和阻断项，不让“迁移进来”被误报成“能力存在”。

## 3. 证据标准

交付状态必须分层：`DESIGNED`（只有设计）、`CONTRACTED`（契约和单测）、`IMPLEMENTED`（代码路径）、`INTEGRATED`（真实依赖集成）、`PILOT`（受控真实流量）、`PRODUCTION`（发布闸门通过）。未达到下一层不得使用下一层措辞。

可接受证据包括：

- 当前磁盘中的文件、精确 diff、路由/OpenAPI、数据库 schema 和迁移输出；
- Fresh 命令输出，如 `uv run ...`、`pnpm ...`、`gh run ...`；
- Fresh Postgres 成功/拒绝/回滚/重放和跨租户负向测试；
- AI run 的模型/提示版本、输入范围、draft、人工决定、事实来源、成本/延迟、审计和删除关联；
- 四端截图或 e2e/golden 证据，证明语义 UI 而非内部 UI 编号。

synthetic adapter、内存 repository、mock provider、设计稿和“应该可以”只能证明契约或测试支撑，不能证明生产能力。测试环境必须与开发、生产拥有同样的功能、流程、规则、路由和错误契约，只有数据和外部适配器可以是模拟的。

## 4. 永久红线

- **环境同构**：dev/test/prod 功能同构；生产不得暴露 dev_auth；缺环境变量必须 fail-closed，不能默认 development。
- **AI 治理**：领域不直连 provider；AI 输出只能是 draft/proposal，不能直写事实；高影响动作必须 Human Gate、审计、可回放。
- **家庭尊严**：不设计家庭总分、家庭排名、跨家庭比较；游戏感来自自己的节奏、阶段、徽章和陪伴，不来自羞辱性竞争。
- **身份与同意**：Account→TenantMembership→Family 主体绑定、session revoke、Consent grant/withdraw/expiry、租户隔离、审计和删除必须持久化。
- **迁移可审计**：baseline、责任边界和动态 head 必须分层；未登记的 WIP migration 不得被测试或发布闸门默认为已完成，未知 head 必须阻断。
- **数据删除**：删除命令幂等、有租户边界、可重试、可审计，并覆盖文本、媒体、向量、缓存和派生 projection；`InMemoryDurableDeletionStore` 即使契约测试通过也只能是 `CONTRACTED / adapter-only`，内存删除不能宣称完成。
- **多语言多端**：locale/region/tenant 是数据边界，不是 UI 字符串替换；Android、iOS、Harmony、小程序和 Web 的核心流程、错误和权限一致。
- **技术边界**：正式业务事实只走 Python/FastAPI/PostgreSQL；Node/Express/tRPC/MySQL 只能经 ADR 证明为非业务工具。
- **评测/准入冻结**：`multimodal_eval.py:EvaluationReleaseGate` 与
  `backend/intelligence/evaluation/release_gate.py:AiReleaseGate` 未合并为唯一
  canonical gate、EvalReport registry lookup/版本与租户绑定未通过前，冻结新增
  evaluation、release-gate、report-persistence 和第二套 registry 代码；只允许修复
  canonical gate、补 registry/负向测试、审计/删除/迁移证据。任何“测试绿”不得解除该冻结。

## 5. 发现问题到发布判定的纠偏流程

```text
发现证据 → 定位文件/模块 → 分级 P0/P1/P2
      → 向 owner 发返工消息（风险+命令+验收）
      → owner 修复并返回 diff/输出
      → 项目助理复测与架构链核对
      → 更新看板和报告 → Lead 做 GO/CONDITIONAL/NO-GO
```

P0 发现后立即通知 Lead，不等待下一次站会；P1 必须有本 Sprint owner、前置条件和截止证据；P2 可以排期，但不能伪装成完成。项目助理不在别人的战场上顺手格式化或改代码；如果返工连续失败，记录阻断原因、复现命令和需要的外部决策。

### 发布判定

- **GO**：所有 P0=0，P1 关键项有真实集成证据，architecture/Ruff/CI/迁移/移动端全绿，身份/同意/删除/审计和 AI human gate 可回放。
- **CONDITIONAL**：P0=0；明确列出的 P1 例外有 owner、期限、风险接受人和回滚方案，且不影响家庭数据、权限、AI 安全和环境同构。
- **NO-GO**：任一 P0；CI/architecture 红灯；生产 fake wiring；迁移不可逆；跨租户访问；AI 绕过 draft/human gate；删除无外部投影回执；全量客户端核心流程失败；公开仓库许可证/数据授权缺失。

## 6. 与 Agent roster 的协作方式

项目助理按 `docs/11_delivery/AGENT_ROSTER.md` 对接，而不是按口头称呼猜 owner：

- APLT：环境、身份、同意、授权、持久化边界；
- ADOM/DATA：领域不变量、ORM、Alembic、真实 UoW；
- AAIR：Principal、Model Gateway、Context/Memory、Human Gate、删除和评测；
- API/AFE：OpenAPI/client 契约、移动端 34 UI、语义体验和跨端回归；
- AQA/GOV：Ruff、architecture、Registry、CI、许可证和证据台账；
- ARCH/Lead：跨层取舍、ADR、发布判定和冲突裁决。

每次返工消息必须包含：`priority`、目标文件/模块、风险、补测命令、验收标准、不得越界的战场范围。项目助理只更新自己负责的两份交付文档；跨 Agent 修复由 owner 提交，项目助理复核。

## 7. 未来两周助理看板

| 周期 | 重点 | 通过条件 | 当前状态 |
|---|---|---|---|
| 第 1 周前半 | SEC-01/ENV-01 P0 负向测试；Registry/Ruff/architecture 修复 | production 无 dev_auth；缺 env 启动拒绝；YAML/Ruff/architecture 绿 | BLOCKED，等待 APLT/AQA/GOV/ARCH |
| 第 1 周后半 | DB-01 migration/ORM 对齐；身份、租户、同意模型 | Fresh Postgres 单 head、可逆；跨租户和 consent 负向测试 | PARTIAL，ADOM 已返工 |
| 第 2 周前半 | PERSIST-01 + CONTRACT-01 | service/membership 真实 UoW；OpenAPI/client CI；移动端全量绿 | NOT STARTED/返工中；Experience SQL ledger 仍仅 CONTRACTED |
| 第 2 周后半 | AI-01 + DATA-01 + UX-01 | 一条 draft→human gate→audit→deletion 可回放；四端体验证据 | PARTIAL；AAIR-6 仍 adapter-only，需接 production composition |
| 本轮追加 | CONTEXT-ASYNC-01 / AAIR + PLT | Async Context SQL store、迁移、Consent/tenant/replay/delete receipts 接入唯一 production resolver | CONTRACTED/PARTIAL；02a80c4/6a88625/6150169 仅 adapter/SQLite，25 项绿测不能升阶 |
| 即日起冻结 | EVAL-CANON-01 / AAIR + API + GOV | 停止新增第二 gate/registry/persistence；只修 canonical `AiReleaseGate`、EvalReport lookup、主体/租户/同意绑定 | BLOCKED；674/050/b3/969 均只能作为契约或返工输入，未达到生产准入 |

## 8. 本轮审查记录（2026-08-30）

截至本轮远端可见为 `d2196bc` 测试候选；本地总控另有 FGCN `41ad120`、PMA 文档
`4e50883` 和 Web client-mode `4b9a4b4`，工作树仍有其他 Agent 的 WIP，发布判定仍为 **NO-GO**：推送只证明版本可追踪，
不代表 production composition、身份/同意、迁移或 AI 准入红线已通过。所有未关闭 P0/P1
仍必须按 owner、commit 和验收命令复测，不得因远端绿色或测试数量增加而自动升阶。

1. AFE-4：语义化服务列表目标测试 5 项通过、`pnpm check` 通过；最新全量 `pnpm test -- --run` 为 249 passed、1 skipped、5 failed（敏捷计划旧记录 247 passed 已过时）。因全量 5 失败和跨 UI/跨端审计缺失，结论为 `PARTIAL`，已发 AFE 返工意见。
2. ADOM-5/DB-01：Fresh Postgres baseline/head 分层当前 `test_alembic_baseline_applies.py` 为 **8 passed、1 failed、1 skipped**（未知 0017 head 拒绝，0010 已登记跳过），FGCN migration chain 2 passed；`alembic heads`=0017，未跟踪 `0011`-`0017` revision 及对应 ADR/Manifest/ORM 使动态 head 未形成可信提交链。结论为 `PARTIAL / schema drift`；下一步是完成 0009-0017 registry/ADR/ORM/对象清单证据后纳入，或在批准前移出/隔离，不能仅改计数。
3. AAIR-5/6：删除 worker 7 项、durable deletion 契约 6 项通过；新增 Async/SQL Context 后 Fresh `tests/intelligence/context_engine -q` 为 **25 passed**（context 文件 Ruff clean）。`InMemoryDurableDeletionStore.production_ready=False`，无 Postgres/outbox 和真实 projection cascade，结论为 `CONTRACTED / adapter-only / RELEASE BLOCKED`，已通知 AAIR/Lead；25 项通过仍不能替代外部删除和 production wiring。
4. 平台闸门（复核前）：生产 dev_auth probe 返回 200，环境缺失默认 development；结论为 `P0 NO-GO`，已立即通知 Lead 并要求 APLT/ARCH 负向测试。
5. APLT-2 SEC-01：显式 production 负向与 test 正向测试 2 项通过；生产 dev_auth 已不在 OpenAPI，但缺失环境变量仍默认 development，且生产没有真实 auth 替代契约，结论为 `CONTRACTED / PARTIAL`，ENV-01 仍 `P0 NO-GO`。
6. DB-01 head 复核：`uv run alembic heads` 最新为 `0017_ai_model_attempts (head)`；0011-0017 revision/ADR 尚未形成 tracked/审批链，unknown 或未提交 head 必须阻断。当前 Fresh Postgres 迁移测试 **8 passed、1 failed、1 skipped**，失败正是未知 0017 head（0010 已登记跳过）；0009-0017 只有完成 ADR、Manifest、ORM/对象清单和可逆实证后才允许 allow-list，状态 `PARTIAL / schema drift`。
7. Web Experience client：`httpClient.ts` 已由 68fc0ce/d403998 注入 Authorization、X-Session-Id、request locale，Web 22 passed/typecheck 0；但 App 真实身份组合与 backend 401/403/跨租户测试仍缺，状态 `PARTIAL / P1 contract blocker`，已通知 Lead。
8. async Experience ledger bridge（b74b29f）：同步/异步 dispatch、durable lifecycle delegation 与 SQLite 幂等/删除/重放定向测试当前 14 passed；但 `AsyncExperienceRunLedgerBridge`/`SqlAlchemyExperienceRunLedger` 尚未接入生产 composition root，production resolver 仍 503，故状态 `CONTRACTED / PARTIAL / P1`。必须补 AsyncSession+事务 outbox/audit wiring、HTTP 401/403/跨租户/并发/restart replay 和外部删除回执后，才可提升集成等级。
9. FGCN a031007：Human Gate accepted Named Action→TaskAssignment 唯一写入者、scope/consent/correlation/human actor、request-id 幂等和同事务审计已通过真实 Postgres `test_persistence.py` + `test_workflow_worker.py` **23 passed**，迁移链 0004-0006 **2 passed**。但当前只是 one-shot worker，缺常驻 queue/lease/通知/DLQ、生产 identity/consent/session 接线及资源/质量/贡献结算，故 `GO（测试切片）/NO-GO（生产）`，不升级 FGCN 为完整商业能力。
10. GROWTH b431eda/78cb9c1/dcc0802：修正 journey 内第二 `ServiceCase` 写入者，改为 canonical `ServiceCaseCommand`/`ServiceDeliveryReceipt`，对 AI delivery、共享故事、推荐和年度回读执行实时 `ConsentGate`，补齐 deletion refs。Fresh journey **40 passed、4 skipped**（无 DB），设置 Postgres 后 **44 passed**；但 `GrowthOutcomeLoop.production_ready=False`，无 HTTP/ORM/Audit/Outbox/worker，结论 `GO（测试切片）/CONTRACTED-PARTIAL（生产前置）/NO-GO（生产）`。
11. Experience SQL ledger 128fb57/4924506/3f56089/eb33c06：`CommittedExperienceRunLedger` 与 `SessionPerCallExperienceRunLedger` 的 preflight/release/replay/DELETE/幂等契约通过；ModelDraft generation 已放入 `SqlAlchemyUnitOfWork`。定向 production/trusted/experience 测试当前 **220 passed、1 warning**（P4 media/share/achievement contracts 已在 synthetic/in-memory 层通过）；但 Run ledger 仍跨独立 session，UoW 未写 Audit/Outbox，main.py 未接真实 identity/consent 组合根，生产默认 resolver 仍 503，状态 `CONTRACTED / PARTIAL / P1 发布阻断`。
12. 941feae/a11f643/96905db：反馈 benchmark ref 仅做 `benchmark:` namespace/长度校验，evaluation projection 只允许 media-free `NOT_MEASURED` 并追加到 run ledger；96905db 仅增加 sync/async coordinator，未新增 EvalReport registry lookup、版本/candidate/draft/provenance/tenant/locale/consent 绑定、审批/撤销/删除和 HTTP API。当前 evaluation+experience **220 passed、1 warning**（P4 runtime contracts 已通过 synthetic/in-memory 测试），结论 `CONTRACTED / PARTIAL / P1`，不得把质量指标当教育 Outcome/Fact 或 provider admission。
13. 68fc0ce/d403998：Web `HttpExperienceApiClient` 统一注入 Authorization、X-Session-Id、request locale（显式 scope locale 优先于 client default），不信任 tenant/family header；Web **22 passed**、typecheck 0。仍无真实 backend TestClient 401/403/跨租户/Consent integration，状态 `PARTIAL / P1`。
14. 674b764/050361f：674 仅补 gate 类型与引用 fail-closed 负向测试；050 仅补 SQLite evaluation projection 持久化测试，未扩大生产边界。两者相关测试与 Ruff 通过，状态 `GO（测试契约）/CONTRACTED（生产前置）`。
15. b3fffbb：新增 `ProductionExperienceRuntimeResolver`，可构造 SQL SessionPerCall、ModelDraftRegistry 和 provider gateway，但 resolver/API 无 Authorization/ActorContext 入参；无 token TestClient 仍可 200，未接 main.py 默认 production composition、Audit/Outbox、外部删除或 EvalReport registry。作者为本地 `Claude Code`，无在线 owner；状态 `P0返工/测试可保留/生产NO-GO`，已通知 Lead/APLT，要求补 401/403、跨租户、撤回同意及真实组合根。
16. 本轮闸门：`uv run pytest tests/architecture -q` **109 passed、1 skipped、1 failed**（Ruff ratchet）；`uv run ruff check .` 当前 **1 E501**（family/entities.py）；Fresh Postgres migration **8 passed、1 failed、1 skipped**（未知 0017 head）。评测/准入双 gate 与 b3 认证缺口未闭合，维持 `NO-GO`；冻结新增 evaluation/release-gate/report-persistence 代码，仅允许 canonical gate/registry/负向测试修正。
17. `02a80c4` 新增 AsyncContextBrokerPort/Adapter，定向 context-engine **25 passed**；仅 `asyncio.to_thread` 包装 InMemory broker，`durability_mode=IN_MEMORY`，无 durable SQL/事务/outbox/重启删除回执，状态 `CONTRACTED / PARTIAL / P1`。
18. `6a88625`/`6150169` 新增 SQL Context Broker 与 replay scope 修复，SQLite fixture 25 项通过；表仅由 `metadata.create_all` 创建，未登记 Alembic/Manifest/ORM、未接 production resolver，且 read 重建 scope 将 consent 固定为 `True`。状态 `CONTRACTED / PARTIAL / P1`，不得因类名 `DURABLE` 升级生产；`f8ee917` 仅更新 CURRENT_PROGRAM_PLAN 计划文档。
18a. `9b10d2d` disposable Postgres probe 当前 **1 passed**，仍为临时 schema + `metadata.create_all` + 同一 engine 的 append/snapshot/read/delete；未执行 Alembic、真实 restart 或 production composition，故仅增加数据库探针证据，不改变 Context 的 `CONTRACTED/PARTIAL` 状态。
19. `573a86d`/`a91ad3a` 已补齐 MediaAsset/Transcript/Evidence/FamilyContentShare、Achievement 与 moderation/consent/deletion contract；当前 evaluation+experience **220 passed、1 warning**，P4 红灯关闭为测试契约层。实现仍使用 `MediaRuntime`/`InMemoryAchievementProjection`，无 durable media/achievement ORM、外部删除回执或 production composition，状态 `CONTRACTED/PARTIAL/P1`，不得升为生产能力。
20. `0cd53fb`/`6b4a8e9` 新增 GrowthIntent→GrowthOnboarding 的 SQL/fake/HTTP 纵切片；Fresh Postgres 批量首跑出现一次 `actor_family_scope_denied`（隔离重跑通过），需稳定重复运行。0016/0017 migration 仍未形成 tracked/Manifest/ADR/ORM 审批链；状态 `CONTRACTED/PARTIAL`，测试可继续、生产 NO-GO。
21. `cbc055e`/`736ae19` 新增 ADR-0069 与 Experience 401/403/CONSENT_REQUIRED、环境 fail-closed acceptance 合同；unset `AIFAMILY_ENV` 仍因 `current_environment()` 默认 development 而保持红灯，未改动冲突 WIP。状态 `P0 BLOCKED`，不能将 acceptance 测试本身视为安全闭环。

这些记录是可追溯的审查输入，不是对 owner 的替代实现。返工完成后必须重新读取文件并运行新鲜命令，才能更新状态。
