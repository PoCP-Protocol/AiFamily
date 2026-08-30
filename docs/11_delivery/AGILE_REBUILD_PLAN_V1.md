---
id: AGILE-REBUILD-PLAN-001
title: Family 家庭需求平台敏捷重建计划
type: delivery-plan
status: current
version: 0.6
owner: chief-architect
created: 2026-08-30
updated: 2026-08-30
canonical: false
---

# Family 家庭需求平台敏捷重建计划

## 1. 目标

以家庭教育为第一个可验收的需求闭环，逐步扩展为围绕家庭需求提供产品、服务和组合
解决方案的平台。第一阶段不追求一次性完成所有 34 UI，而是先证明一条真实路径，并让
孩子、家长、家庭关系的记忆体在同一条链路中可控地积累：

```text
家庭表达/测评
  → 需求澄清
  → 教育解决方案草案
  → 家庭确认
  → 21 天小行动
  → 反馈/过程证据
  → 记忆候选/家庭确认
  → 下一步服务需要
```

平台精神贯穿每个 Sprint：**We are 伐木累！We are family！**

## 2. 敏捷运行规则

- 以 1 周为一个 Sprint；每个 Sprint 只承诺可验收的纵向切片。
- 任务必须绑定业务场景、流程节点、权威数据对象、应用入口和测试证据。
- 34 UI 只是视觉/迁移/回归基线，不是产品上限；新增、合并、拆分或淘汰页面必须由用户
  场景和体验证据驱动，并保留迁移映射和回归证据。
- UI 必须支持多模态演进：文字、语音、图片、音频、视频和互动卡片按场景接入；测试环境
  只替换合成媒体和适配器，不删除模态能力或失败/删除路径。
- Agent 只能修改自己的战场；跨战场问题通过交付说明报告，不顺手修改。
- 每个任务使用分支和 pathspec 提交，不使用 `git add -A`、`git add .` 或 `git commit -a`。
- 每轮结束必须执行：目标范围测试、架构测试、范围 Ruff、全量 Ruff/pytest 结果登记。
- 设计、路由、fixture 或 SQL 存在不等于能力完成；完成必须有可调用路径和拒绝路径。

## 3. 团队与战场

| 角色/编号 | 责任 | 本 Sprint 战场 | 不得修改 |
|---|---|---|---|
| Lead/ARCH-1 | 目标、切片、Family API 集成、评审和发布闸门 | `docs/11_delivery/`、`backend/apps/family_api/` 集成文件 | Agent 的专属实现文件 |
| AAIR-2 | Experience/Recommendation AI 技术契约 | `backend/intelligence/experience/`、对应 tests | `backend/intelligence/principal/`、治理 YAML |
| ADOM-2 | Family Need 领域模型和策略 | `backend/domains/family_need/`、`tests/domains/family_need/`、DOMAIN_REGISTRY 登记 | `backend/apps/`、`backend/intelligence/` |
| AFE-1 | 移动端 UI-03/05/09 纵向体验和 API 对接 | `frontend/mobile/app/ui/`、对应 `lib/` 和 tests | `backend/`、其他 Agent 文件 |
| QA gate | 由 Lead 集成执行；后续 Sprint 单独派 QA | `tests/architecture/`、CI 结果 | 未授权业务实现 |

## 4. Sprint 0：契约和团队启动

### 目标

把“家庭需求平台”从战略表述变成四个可独立开发的契约：需求事实、体验事件、需求入口和
孩子/家长/家庭关系记忆候选。记忆候选未经家庭或人工确认不得成为长期记忆。

### Backlog

| ID | 任务 | Owner | 验收 |
|---|---|---|---|
| S0-01 | ExperienceEvent/RecommendationDecision/FeedbackSignal 契约 | AAIR-2 | 数据边界、幂等、provenance、租户/语言字段测试 |
| S0-02 | FamilyNeed/NeedSignal/NeedProfile 领域对象、策略和端口 | ADOM-2 | 正常、拒绝、跨租户、主体范围测试；registry 同步 |
| S0-03 | `POST /families/{id}/needs/signals` 需求入口路由与应用集成 | Lead | DTO、错误码、授权/同意前置、路由级测试；接入 Agent 契约 |
| S0-04 | Principal `experience_curator` Registry/路由设计评审 | Lead + AAIR-2 | 不进入生产运行；补 Registry/ADR/contract test 清单 |
| S0-05 | UI-03/05/09 接入需求/方案/行动 API 与多模态契约 | AFE-1 + Lead | 不再读取假成功 fixture；加载/错误/拒绝/确认/媒体失败状态可验收 |
| S0-06 | 集成检查和 Sprint Review | Lead | 目标测试通过；偏差和债务登记 |
| S0-07 | Child/Guardian/Relationship Memory 候选与检索合同 | AAIR-2 + ADOM-2 | M0-M3 生命周期、同意/确认/纠正/删除证明、跨家庭拒绝和多模态派生测试 |

### Sprint 0 完成定义

- 三个 Agent 交付均有实际测试输出和变更文件清单；
- 前端 UI-03/05/09 与后端接口在同一轮可联调，成功和拒绝状态一致；
- 不新增容器目录 `__init__.py`；不直连模型供应商；不写家庭事实的旁路；
- dev/test/prod 的接口、状态机、错误码和闸门契约一致；
- 三类记忆体只能经候选→同意→确认形成；检索带最小范围和审计；删除覆盖媒体派生物、缓存与 Embedding；
- 全量架构测试只允许已有债务失败，不能新增错误。

### Sprint 0 当前看板

| 任务 | 状态 | 当前负责人 | 集成依赖 |
|---|---|---|---|
| S0-01 体验事件/推荐技术契约 | COMPLETED | AAIR-2 | 143 intelligence tests；生产运行时接入仍在后续 Sprint |
| S0-02 Family Need 领域契约 | COMPLETED | ADOM-2 | N0→N1、13 个领域测试 + 4 个 API 适配测试 |
| S0-03 需求入口 API | COMPLETED | Lead/ARCH-1 | `POST /families/{id}/needs/signals` 已挂载；dev/test 合成适配器同构 |
| S0-04 experience_curator 路由评审 | COMPLETED | Lead + AAIR-2 | Registry/ADR/contract 清单完成；未进入生产 Agent 运行时 |
| S0-05 UI-03/05/09 联调 | COMPLETED | AFE-1 + Lead | 27 个 Vitest + `pnpm check` 通过；R9 与多模态状态守住 |
| S0-06 集成与 Review | IN_PROGRESS | Lead | 目标测试已通过；等待全量架构/Ruff 结果登记 |
| S0-07 记忆体合同与审计 | COMPLETED（适配器级） | AAIR-2 + ADOM-2 | Child/Guardian/Relationship、M0-M3、确认/撤回/检索/删除证明；耐久存储待后续 |

## 5. Sprint 1：家庭教育需求纵向切片

```text
UI-03 测评解释/需求澄清
  → UI-05 教育方案草案
  → UI-09 一个小行动
  → 家庭确认
  → Named Action
  → FeedbackSignal
```

交付包括：PrincipalApplicationFacade、ContextSnapshot 只读投影、教育 SolutionBlueprint
草案、ActionProposal→确认桥接、记忆候选→家庭确认桥接、审计/Outbox、成功/拒绝/暂停/重放/
删除测试和 dev/test/prod 功能等价证明。

## 6. Sprint 2：资源组织与高质量服务

接入 FGCN 的 ServiceCase、ServiceTask、Assignment、DeliveryRecord、QualityDecision 和
Contribution。先做到“资源不足可解释、任务责任明确、交付可验收、失败可补救”，再扩大
专家、教师、管家和服务产品目录。

## 7. Sprint 3：产品、服务和解决方案目录

把教育方案抽象为 `SolutionBlueprintVersion`，接入 Product、Service 和 Solution 三种
供给形态，完成组件、模式、编译、模拟、人工发布和交付反馈闭环。

## 8. Sprint 4+：商业增长、社区和全球化

在情绪价值和成长证据稳定后，接入会员、复购、邀请、案例传播、社区和区域 Cell；同步
完成多语言、租户隔离、删除、容量、灾备和三环境 parity。不得以商城先行替代需求闭环。

## 9. 每个任务卡必须包含

```text
编号/角色/战场
业务场景与流程节点
输入/活动/输出/规则/异常
权威数据对象和禁止写入边界
API/Command/Event/Job/Human Task
成功/拒绝/重放/超时/删除测试
三环境差异（只允许数据和外部适配器差异）
实际命令输出和未解决债务
```

## 10. 项目健康指标

- 纵向切片完成数，而不是文档或目录数量；
- 每个场景的成功/拒绝/人工升级/重放覆盖率；
- 情绪价值：首次被理解时间、主动返回、暂停后安全返回；
- 成长价值：家庭确认、行动证据、质量验收；
- 经济价值：家长主动服务意向、复购和推荐；
- 平台健康：租户隔离、删除完成、投诉、人工 SLA、成本和区域可用性；
- 质量债：全量 Ruff/pytest 和外部适配器失败演练。

## 11. 本轮退出条件

Sprint 0 未完成前，不进入支付、自动续费、未成年人商业推荐或大规模基础设施建设；
Sprint 1 未完成前，不宣称“法咪莉校长已上线”或“家庭需求平台已完成”。

## 12. 架构对齐闸门

每个实现任务合并前必须提交一条可追踪链：

```text
商业目标/六引擎/平台精神
  → 业务能力/业务场景
  → L0-L5 流程节点（输入/活动/输出/规则/异常）
  → 主数据/业务数据/AI 技术数据/事件
  → Application Service/API/Command/Event/Projection
  → Principal capability/Knowledge/Safety/Human Gate
  → 34 UI 或运营入口
  → 成功/拒绝/重放/删除/环境 parity 测试
```

缺任一层只能标 `DESIGN_ONLY` 或 `PARTIAL`。不能以“模型能回答”“页面能打开”“数据库
有表”“fixture 有数据”作为完整能力证明；不能为了本 Sprint 进度绕过既有 ADR、宪章或
`docs/00_system/ARCHITECTURE_BENCHMARK_REVIEW_V3.md`。

### 12.1 UI 体验闸门

新增或改造 UI 必须同时证明：

1. 它解决一个真实家庭需求或运营职责，而不是复制已有页面；
2. 它绑定 N0-N8 流程节点、权威投影和 Named Action；
3. 它覆盖情绪承接、选择、暂停、错误、拒绝和确认状态；
4. 它保留多语言、租户、隐私、无障碍和环境等价能力；
5. 它为适用场景提供文字、语音、图片、音频、视频或互动卡片的多模态入口/输出，并覆盖
   同意、解析失败、低带宽、替代文本和删除；
6. 它通过交互测试后，才可替换或合并原 34 UI 基线页面。

## 13. Sprint 0 Review（2026-08-30）

### 已交付

- `VS-01`：Family Need N0→N1 已通过 Family API 可调用；成功、跨家庭、缺同意、缺幂等和
  重放路径均有测试。
- Experience 闭环合同已冻结，覆盖 N0-N8、推荐解释、反馈、六种模态和四类 locale。
- Child/Guardian/Relationship Memory 的 M0-M3 候选、确认、撤回、最小检索和删除证明适配器
  已完成；AI 不直接写入记忆事实。
- UI-03/05/09 已接入真实 API 状态和多模态合同；UI-03 已移除总分、排名、雷达图语义。

### 验证记录（阶段复盘复测）

```text
uv run pytest -q                         819 passed, 44 skipped, 2 known gate failures
uv run pytest tests/architecture -v       108 passed, 1 skipped, 2 known gate failures
uv run pytest tests/intelligence -q        229 passed
uv run pytest tests/apps/family_api -q      17 passed, 1 skipped
pnpm exec vitest run（UI-03/05/09）          27 passed
pnpm check                                  passed
```

### 仍未完成（不宣称生产就绪）

- `family_need` 仍使用 Fake 仓储和 dev/test 合成身份/同意；需要 PostgreSQL、真实身份、同意
  存储和 FGCN 适配器。
- N1→N8 的需求澄清、画像、方案、资源分派、交付、验收和回流 API 尚未完成。
- Memory adapter 还未接入 Principal/Context Broker、Family API、持久化表和删除 Worker。
- `experience_curator` 目前只有 Registry/合同设计，未开启生产 Agent 或模型供应商调用。
- L0 现状文档中的历史断言（例如“零业务 API”“Memory ABSENT”）尚未完成与本 Sprint
  证据的同步；在同步前不得把旧基线当作当前实现清单。
- 全量 Ruff 的错误均来自并发 WIP 文件；本轮未改动这些文件，避免吞并他人工作区。

## 14. Sprint 1 并行开发评审（2026-08-30）

### 已交付的三条战线

- **S1-A Principal AI + 知识库**：Principal 作为 AI 控制平面完成能力路由、知识检索、
  Model Gateway 结构化生成和不可提升的 `DRAFT` 输出；24 个 Principal/knowledge 测试、
  18 个架构测试通过。真实 Context Broker、Human Gate、持久化和生产模型仍保持 `PLANNED`。
- **S1-B Family Need N1→N2**：完成需求澄清、需求画像、Solution Draft 和资源缺口；
  `SupplyReferencePort` 只读解析 Product/Service 引用，不写 canonical 事实；20 个领域测试通过。
- **S1-C 服务/产品体验**：新增服务/产品发现体验，保留 UI-13/14/19/20/31 基线，支持
  多模态和 loading/empty/denied/error/synthetic 状态；专项 Vitest 4 个通过、`pnpm check` 通过。

### 集成阻塞与下一步

- S1-B 的 N1→N2 应用服务已接入 Family API 路由和 dev/test 合成依赖；仍缺 PostgreSQL
  持久化和真实身份/同意存储，不能把合成适配器当成生产能力。
- S1-A 的 Principal 运行时尚未接入 Context Broker、Human Gate、Action Bridge、审计与
  Outbox；当前只能标记 `PARTIAL`，不能宣称“法咪莉校长已上线”。
- 架构测试另发现并发 WIP 新增 `backend/intelligence/product_management/` 尚未在
  `MIGRATION_MANIFEST.yaml` 登记；该目录不属于本 Sprint 三条战线，待其 owner 处理。

### 14.1 复盘新增的质量债

- FGCN 持久化 WIP 的两条契约测试已由 ADOM-3 修复，并通过 17 条领域/持久化测试；真实
  Postgres migration 0004 尚未在本地执行，仍不得标记生产就绪。
- 并发 WIP 新增 `backend/intelligence/product_management/` 未登记到
  `governance/MIGRATION_MANIFEST.yaml`；由其 owner 单独登记，Lead 不越界修改。
- 全量 Ruff 当前由并发 WIP 产生 6 个错误（`family/domain/entities.py`、`intelligence/experience/`
  及其测试）；本轮未改动这些文件，避免吞并他人工作区。
- 当前分支的测试数量与并发 WIP 会随工作区写入变化，所有数字以本轮实际命令输出为准，不能把
  缓存报告当成验收证据。

## 15. Sprint 2：平台能力与服务协作 P0（进行中）

本 Sprint 仍以“可验证的闭环能力”为单位，不以目录数量或 UI 数量作为完成标准：

| 任务 | Owner | 独占战场 | 验收目标 |
|---|---|---|---|
| ADOM-3 / FGCN 持久化 | ADOM-2 | `backend/domains/service/fgcn/**`、`tests/domains/service/fgcn/**`、P0 migration | ServiceCase/Task/Delivery/Quality/Contribution 可持久化；终态不可逆；贡献只来自已验证交付 |
| AAIR-3 / Context Broker | AAIR-2 | `backend/intelligence/context_engine/**` 及其测试 | 租户/家庭/主体/用途/同意/数据分类/来源/过期/删除约束；最小只读投影；拒绝越权和撤回数据 |
| AAIR-4 / Principal 上下文接线 | AAIR-2 | `backend/intelligence/principal/runtime.py`、上下文集成测试 | 路由→Context Broker→知识→Model Gateway 链路；只读投影入模；越权/过期/删除在模型调用前拒绝 |
| AFE-2 / 跨端能力适配 | AFE-1 | `frontend/mobile/lib/platform-capabilities/**`、专项 Vitest | Android/iOS/HarmonyOS/小程序共享 capability contract；媒体、通知、分享、支付、存储通过 adapter 隔离平台差异 |
| Lead / 集成与治理 | ARCH-1 | `docs/11_delivery/**`、集成测试、发布脚本 | 不吞并并发 WIP；复测全量闸门；补登记/债务；提交并推送功能分支 |

### Sprint 2 完成定义

- FGCN 通过成功、拒绝、重放、幂等和终态不可逆测试；
- Context Broker 通过跨租户、过期、撤回、删除和不可变投影测试；
- 移动端 capability contract 通过四平台矩阵和不可用/拒绝/降级状态测试；
- dev/test/prod 接口、错误码、状态机和安全闸门相同，只有数据和外部适配器配置可不同；
- 全量架构测试与 Ruff 不新增错误；所有未解决债务进入本计划，不以“fixture 有数据”宣称完成。

### 15.1 Sprint 2 当前复核（阶段性交付）

- **ADOM-3 FGCN：PARTIAL**。领域引擎、SQLAlchemy 持久化映射、终态不变量、交付证据和
  贡献溯源已通过定向测试；PostgreSQL migration 0004 与真实事务/ORM 演练仍待执行。
- **AAIR-3 Context Broker：PARTIAL**。租户/区域/家庭/主体/用途/同意/数据分类/来源/过期/
  删除约束和只读投影已通过 14 条测试；尚未接入 Principal、持久化表和删除 Worker。
- **AFE-2 跨端能力：PARTIAL**。Android/iOS/HarmonyOS/小程序共用六项 capability contract，
  合成适配器覆盖不可用、拒绝、低带宽、回退和宿主确认；真实原生桥接仍按平台单独实现。
- **AAIR-4 Principal 上下文接线：PARTIAL**。注入 ContextBroker 时已按路由决定构造完整作用域，
  只读 projection 在模型调用前完成边界校验；未注入 broker 的兼容路径显式返回
  `CONTEXT_PROJECTION_UNAVAILABLE`，真实持久化 Broker、Human Gate 和删除 Worker 仍待接入。
- 本轮复测：全量 `819 passed, 44 skipped, 2 known gate failures`；架构 `108 passed, 1 skipped,
  2 failures`；AI `229 passed`；Family API `17 passed, 1 skipped`；移动端 `pnpm check` 通过。
  两个闸门失败均为并发 WIP 的 Ruff 债务和未登记 `product_management` 目录，不由本 Sprint 越界吸收。

## 16. Sprint 2.1：可观测闭环与删除安全（进行中）

本微迭代只增加只读投影、删除编排和体验状态模型，不改变既有事实模型：

| 任务 | Owner | 独占战场 | 验收目标 |
|---|---|---|---|
| ADOM-4 / FGCN 进度投影 | ADOM-2 | 新增 `backend/domains/service/fgcn/read_model.py` 及专项测试 | 只读展示任务、交付、质量和已验证贡献；跨租户拒绝；无家庭总分/排名/金额结算 |
| AAIR-5 / Context 删除 Worker | AAIR-2 | 新增 `backend/intelligence/context_engine/deletion.py` 及专项测试 | 删除命令可重试、幂等、有审计状态；级联观测和快照；不伪造外部删除完成 |
| AFE-3 / 能力健康 ViewModel | AFE-1 | 新增 `frontend/mobile/lib/platform-capabilities/health-view-model.ts` 及专项测试 | 将四端 capability 状态映射为可访问、多语言 UI 状态；保留 retryable/externalEffect |
| Lead / 迁移与生产接线 | ARCH-1 | 测试数据库、migration、Family Need durable wiring | 执行 0004/0005/0006；验证真实 ORM/UoW；清除 R3/Ruff 闸门债务 |

### Sprint 2.1 完成定义

- 三个新增切片均通过成功、失败、重放、租户隔离和删除/降级测试；
- 所有投影不写 canonical 事实，不产生家庭总分、排名或未经验证的贡献；
- 删除状态必须能回放并留下审计链，外部存储未确认时只能标记待处理；
- 测试数据库执行 migration 后，dev/test/prod 使用同一 API 与状态机，仅适配器和数据来源不同。

### 16.1 当前集成阻塞

- 已启动 `docker-compose.dev.yml` 的 disposable Postgres，但首次 `alembic upgrade head` 暴露真实
  迁移问题：`0005_fgcn_assignment_request_idempotency` 的 revision 字符串超过历史
  `alembic_version.version_num VARCHAR(32)`，在更新版本号时失败；迁移 owner 必须在不破坏历史
  版本链的前提下改为不超过 32 字符并验证 0004→0006 全链路。
- 未设置 `DATABASE_URL` 时 Alembic 会落到 SQLite，而基线包含 Postgres 专用 SQL；这不是可接受的
  测试降级，开发规范必须要求显式 Postgres URL 后再执行 migration。

## 17. 外部审查整合与项目助理机制（2026-08-30）

本节吸收 Manus 审查报告，但报告只作为待核验输入；当前代码、注册表、测试命令和运行日志
才是交付判断依据。审查中指出的“代码存在”不得自动升级为“能力完成”，也不得因为当前处于
测试环境而删除生产功能。开发、测试、生产必须共享同一 API、状态机、权限、同意、审计、删除、
多模态和错误处理契约，只允许数据来源与外部适配器配置不同。

### 17.1 已核验的本轮结果

- **AFE-4 UI 体验重构：已交付**。服务列表不再渲染 `UI-19` 等内部编号；内部 ID 仅用于
  registry 导航，用户看到语义图标、服务阶段、可暂停提示和轻量家庭成就。专项 Vitest 5
  tests passed，`pnpm check` passed；仍需后续接入真实进度投影与多语言资源。
- **ADOM-5 迁移链路：已验证切片**。`0005` revision 已收敛到不超过 32 字符，并新增真实
  Postgres disposable database 的 0004→0005→0006 升级、降级和版本落库测试；0004 及后续
  迁移仍需随其 owner 的 WIP 一并完成提交，不能只凭测试文件宣称全量 migration head 已完成。
- **外部审查中的 P0 风险仍未关闭**：开发会话端点仍在应用工厂中无条件导入，默认环境仍可能
  回落到 development；真实身份/同意/家庭绑定/持久化、OpenAPI 契约自动比对和分支保护仍是
  发布前阻断项。报告中关于具体测试数量、旧目录和旧提交的历史数字不作为当前统计。

### 17.2 项目助理（Project Assistant）职责

新增专门的项目助理 Agent，作为 ARCH-1 的常驻质量与架构对齐角色，维护
`docs/11_delivery/MANUS_REVIEW_INTEGRATION_V1.md` 与 `PROJECT_ASSISTANT_CHARTER_V1.md`。
它每轮必须：

1. 对照核心商业蓝图（家庭成长操作系统、增长/分发/服务/长期陪伴、FGCN 协作网络和
   “We are 伐木累！We are family！”）核验新增能力是否有业务场景、分级流程节点、数据对象、
   应用入口和 AI/人工闸门；
2. 对照业务、流程、数据、应用、AI 技术五层架构，抽查代码路径、API/OpenAPI、迁移、测试和
   注册表；不接受“页面能打开、fixture 有数据、模型能回答”作为完成证据；
3. 每轮记录成功、拒绝、人工升级、重放、超时、删除、跨租户和三环境 parity 证据，并指出
   新增债务；发现阻断项时提出纠偏任务，不能以文档覆盖代码缺口；
4. 维护发布闸门：P0 安全/数据合规、P1 真实持久化与契约一致性、P2 体验/AI 增强。闸门未通过
   时只允许发布到受控开发/测试环境，并明确 `PARTIAL`，不得对外宣称生产就绪；
5. 与各 Agent 保持独占战场；项目助理可以直接修改自己负责的交付计划、审查和质量文档，
   跨战场代码问题通过任务卡和验收证据转交 owner，不覆盖他人 WIP。

### 17.3 外部审查转化的下一批任务

| 编号 | 优先级 | 任务 | Owner | 完成证据 |
|---|---|---|---|---|
| PA-SEC-01 | P0 | 生产配置下隔离 dev auth；统一 `AIFAMILY_ENV`，空值/拼写错误 fail-closed | ARCH-1 + APLT | 生产 OpenAPI 不含 `/auth/account-session`；负向启动和 404 测试 |
| PA-QUAL-01 | P0 | 清理/隔离并发 Ruff 债务，恢复 CI 绿灯和分支保护 | AQA-1 | `ruff check .` 清零；架构/全量测试为 required checks |
| PA-DATA-01 | P1 | 真实 Identity、Tenant–Family、Consent store、Postgres UoW 与审计持久化 | APLT + ADOM | 真实数据库完成认证、同意撤回、跨家庭拒绝和审计查询 |
| PA-API-01 | P1 | 从 FastAPI OpenAPI 生成并校验移动端 API 契约 | AAPI + AFE | CI 能检测动词、路径、参数、schema 和状态码漂移 |
| PA-AI-01 | P1 | Context Broker → Principal → Human Gate → Named Action → Outbox 的可回放链路 | AAIR | 首个低风险场景仅产出 draft，人工确认后才写事实 |
| PA-UX-01 | P1 | 将 AFE-4 的语义图标/成就反馈推广到其余服务与成长入口 | AFE | UI 不显示研发编号；多模态、暂停、拒绝、删除和无障碍测试齐全 |
| PA-OPS-01 | P2 | 明确 Node/Express/tRPC 模板层边界并补 SPDX/素材权属说明 | ARCH-1 + GOV | ADR、构建排除证明、许可证和第三方清单齐全 |

### 17.4 两周滚动节奏

每个 Sprint 开始由项目助理出具“架构对齐清单”，中途检查一次阻断项，结束时发布一页
“事实复盘”：代码/迁移/测试/运行证据、已关闭债务、未关闭债务、下一轮任务和可发布环境。
任何新任务必须挂接到商业目标 → 场景 → 分级流程 → 数据 → 应用 → AI/人工控制 → UI/运营
入口 → 验收测试链；缺链的任务只能进入设计 backlog。

## 18. Sprint 2.1 复核结果（项目助理驱动，2026-08-30）

- **DB-01：CONTRACTED / PARTIAL**。`tests/database/test_alembic_baseline_applies.py` 已将历史
  baseline（0001，152/7/60）与 0004-0008 additive head（0008，159/7/60）分层，并对当前
  未登记的 0009 WIP 只做显式 `160` allow-list；Fresh Postgres baseline 3 passed、FGCN chain
  2 passed、Ruff 通过。0009 仍需 ADR、MIGRATION_MANIFEST、ORM/迁移对象清单和 owner 提交，未知
  head 必须失败。
- **AAIR-6：CONTRACTED / adapter-only**。新增 durable deletion queue 的端口、租约、重试、DLQ、
  幂等、租户隔离和 TEXT/MEDIA/VECTOR/CACHE/DERIVED 回执合同；定向删除测试 13 passed、Ruff
  通过。当前实现仍是 `InMemoryDurableDeletionStore`，没有 Postgres/outbox、跨进程 lease 或真实
  五类 projection，保持 `RELEASE BLOCKED`，不得标记生产删除完成。
- **AFE-4：PARTIAL**。服务列表已用语义图标、步骤和家庭小成就替换可见 UI 编号，专项 5 tests
  与 `pnpm check` 通过；全量移动端仍 5 failures，`family-screen-list.tsx`、通用 `[id]` 路由和
  UI-05/UI-09 旧文案仍存在可见内部编号，需另开 UX-01 返工。
- **PMA-1：常驻审查**。项目助理已对以上交付发送反向意见，并将 P0/P1 任务写入审查报告和
  章程；当前发布判定仍为 `NO-GO`，原因是生产 dev_auth/环境默认、身份/同意持久化、架构与
  Ruff 闸门、全量移动端契约漂移等未关闭。

### 18.1 当前可复现闸门

```text
uv run pytest tests/architecture -q                 106 passed, 1 skipped, 4 failed
uv run ruff check . --output-format concise          1 E501（并发 WIP family/entities.py）
uv run pytest tests/database/test_alembic_baseline_applies.py -q  3 passed
uv run pytest tests/database/test_fgcn_migration_chain.py -q      2 passed
cd frontend/mobile; pnpm test -- --run              247 passed, 1 skipped, 5 failed
cd frontend/mobile; pnpm check                       passed
```

上述失败必须被项目助理逐轮复核；不得用抬高基线、删除测试、把 0009 WIP 偷换为已完成或将
synthetic adapter 当真实依赖来“修绿”。
