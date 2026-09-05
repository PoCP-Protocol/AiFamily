---
id: DELIVERY-FAMILY-GROWTH-EXECUTION-001
title: Family Growth Platform Execution Board V1
type: delivery
status: draft
version: 1.0
owner: product-delivery-pm
created: 2026-08-30
updated: 2026-08-30
canonical: false
supersedes: null
superseded_by: null
---

# 家庭成长平台执行板 V1

> **文档性质**：独立交付草案，不是当前系统真相、产品规格或架构决策。
> 本文件只用于组织团队、排定 P0-P3 纵向切片、定义生产等价测试与交付门。
> 本文件不修改任何 registry，也不把“代码已迁入”表述为“能力已具备”。

## 1. 执行边界

当前基线显示：业务 API 尚未形成可用闭环，34 个 Mobile 屏幕尚不能在 AiFamily 内真正工作；因此本板的交付对象是“可验证的真实用户路径”，不是页面数量、迁移数量或演示数据数量。

所有切片共同遵守以下边界：

- 家庭总分、家庭排名、把孩子变成绩效指标的成长评价不进入任何切片。
- AI 只产出 `Perspective`、`Hypothesis`、`Recommendation`、`Draft` 或 `ActionProposal`；不得直接写入权威事实。涉及计划确认、服务推荐、家庭状态变更和未成年人敏感动作时，必须有 Named Action、人工闸门、审计和可拒绝路径。
- 领域和应用服务不直连模型供应商；AI 调用统一通过 `backend/intelligence/model_gateway`，输出必须有 provenance 和版本信息。
- 开发、测试、生产使用同一套路由、契约、业务规则、状态机、权限、同意、审计、幂等和 Workflow；环境差异只允许来自数据集与外部适配器。
- 本板不把临床诊断、儿童端自动化商业营销、未获批准的真实支付或真实供应商接入作为交付前提。若流程包含这些边界，必须在所有环境保留完整拒绝、人工处理和审计路径。

### 1.1 横切产品原则（设计约束，非实现声明）

本节是跨切片的产品设计与验收约束，当前仅登记为 **`DESIGN_ONLY / NOT_IMPLEMENTED`**。它不表示现有代码、测试、runtime wiring 或数据链路已经实现，也不能改变 Sprint 1 的 `IN_PROGRESS / NOT_DONE` 状态。

| 横切原则 | 执行口径 | 当前状态与验收边界 |
|---|---|---|
| **成长陪伴闭环** | 多模态 `Context → AI Perspective/Draft → Human/Family confirmation → Action/Review → evidence-bound achievement → consented sharing`；AI 只提供可追溯的 Perspective/Draft，确认、行动、复盘、成就和分享必须分别有明确责任人、证据、权限与审计 | `DESIGN_ONLY / NOT_IMPLEMENTED`；不得用页面串联、AI 文案、单域测试或合成状态声称闭环完成。实现时须补齐生产等价 API、状态、持久化、人工确认、证据绑定、Consent/Audit 和回读证据 |
| **长期陪伴与生命周期** | 陪伴策略按年龄阶段、家庭处境和数据生命周期演进；阶段变化、主体权限、数据目的、保留/删除/撤回和派生数据清理必须可解释、可审计，不得把儿童成长固化为单一分数 | `DESIGN_ONLY / NOT_IMPLEMENTED`；没有年龄阶段迁移、生命周期矩阵、撤回/删除和回读证据前，不得宣称长期陪伴能力已实现 |
| **关系网络与供给角色** | 按家庭、学校、社会供给角色控制可见性与可操作范围；每次跨主体读取和分享均须有 tenant/family scope、目的化 Consent、最小权限、审计和人工升级边界 | `DESIGN_ONLY / NOT_IMPLEMENTED`；不得以共享 ORM、开放默认可见、静态角色名或页面权限开关冒充关系网络治理完成 |
| **明确禁止的产品方向** | 禁止家庭总分/排名、无证据成就、儿童商业推荐、无门槛开放专家市场；相关需求必须拒绝、降级为受治理的人工/资源流程，或保持未实现并记录原因 | `DESIGN_CONSTRAINT / ALWAYS_BLOCKED`；任何切片、实验、fixture、AI 输出或演示不得绕过这些禁区 |

## 2. 可执行团队分工

角色是稳定的，任务随切片流动。每个切片启动时必须指定一名 Lead 和一名 Gate Owner；没有明确负责人，不得进入开发中。

| 角色 | 主要责任 | 每个切片的硬性交付物 | 不负责/不得越界 |
|---|---|---|---|
| Product / Delivery PM | 维护范围、顺序、依赖、决策记录和退出门；核对实际证据 | 切片卡、依赖清单、风险更新、Gate 结论、复盘 | 不写业务实现、不修改测试断言、不以 Agent 汇报替代验证 |
| BA / UX | 把家庭处境转成用户路径、场景、字段语义和验收标准 | 场景契约、范围外清单、错误/拒绝矩阵、UI-API 映射 | 不把页面或 AI 文案当作业务能力，不定义家庭分数/排名 |
| Domain / Backend | 实现事实 Owner、聚合、不变量、Command、Query、状态机和领域事件 | 域模型、应用服务、仓储、HTTP 验收测试、审计/幂等接线 | 不直接调用模型供应商，不绕过平台内核，不跨域写事实 |
| Platform / Security | 提供身份、租户、权限、Consent、Audit、Idempotency、Persistence | 访问策略、同意记录、读写审计、幂等键、拒绝用例 | 不用测试后门替代正式身份、权限或同意流程 |
| AI Runtime | 提供 Model Gateway、Context、Agent/Tool 边界、Provenance、Human Gate 接口 | 输入输出 schema、DRAFT/PROPOSED 状态、模型调用审计、失败关闭测试 | 不持有业务事实、不直接写业务仓储、不把确定性 fallback 伪装成 AI |
| Data / Migration | 设计持久化边界、迁移、事件/Outbox、重启回读、删除和留存验证 | PostgreSQL 迁移、ORM 一致性、数据删除演练、回放/重试证据 | 不用 `create_all` 代替正式迁移，不将派生数据遗漏在删除链外 |
| API / Frontend | 对齐 API 契约、真实状态和家庭端可用路径 | OpenAPI/契约、移动端接线、加载/错误/拒绝态、端到端路径 | 不依赖 `SYNTHETIC_DEV_ONLY` 路由，不增加只有开发环境存在的业务分支 |
| Service / FGCN | 负责资源能力、案件、任务、分配、交付、质量和补救的事实边界 | `ServiceBlueprintVersion`、`ServiceCase`、`ServiceTask`、交付/验收证据 | 不让 AI 自动分派、关闭投诉或承诺供给；资源不足必须返回明确缺口 |
| QA / Quality Gate | 设计测试矩阵、执行咬人验证、核 CI/lint、验证环境等价 | 正向/拒绝/反向状态机测试、E2E、重启回读、故障注入、实际输出 | 不接受“应该可以”；不以截图、静态夹具或单元测试代替生产等价验收 |
| Compliance / Governance | 把未成年人保护、数据目的、留存、删除、读取审批和 registry 一致性纳入门禁 | 合规检查清单、DPIA 前置项、读写留痕核验、实现后的登记同步项 | 不在本草案中擅自改 registry；发现漂移先报告并建立明确处置人 |
| Release / Operations | 管理环境晋级、灰度、SLO、监控、回滚和运行手册 | 发布基线、Runbook、告警/人工升级、回滚演练、环境差异清单 | 不把未在测试环境验证过的业务分支带入生产 |

### 2.1 切片责任矩阵

| 切片 | Lead | 必须共同交付 | Gate Owner |
|---|---|---|---|
| P0 家庭建档与控制面 | Domain / Backend | Platform、Data、API / Frontend、QA、Compliance | Product / Delivery PM + QA |
| P1 测评到成长意图 | Domain / Backend | BA / UX、AI Runtime、Platform、Data、API / Frontend、QA | Product / Delivery PM + Compliance |
| P2 成长行动与复盘 | Domain / Backend | AI Runtime、Workflow / Data、Platform、API / Frontend、QA | Product / Delivery PM + QA |
| P3 服务协作与结果回流 | Service / FGCN | Domain、AI Runtime、Platform、Data、API / Frontend、QA、Operations | Release / Operations + Compliance |

Lead 对代码和测试的实际交付负责；Gate Owner 对是否满足完成定义负责。一个角色缺席时，应明确记录“缺席导致的未完成项”，不得默认为通过。

### 2.2 当前 Sprint 固定范围：Sprint 1 = GrowthIntent → Onboarding

**Sprint 1 Owner：James。执行状态：`IN_PROGRESS`；完成状态：`NOT_DONE`。** 本 Sprint 只交付“已确认的 `GrowthIntent` 进入 `Onboarding`”这一条确认后路径，不扩展为 Family Need、Service 或 FGCN 的全链路建设。

```text
已确认 GrowthIntent
  → 受授权的 Onboarding Named Action
  → Onboarding 持久化与可回读状态
```

Sprint 1 的范围边界：

- **纳入**：确认后的 `GrowthIntent` 作为输入；Onboarding 的正式 Domain/Application/API、持久化、可调用 runtime wiring、Consent、Audit、Idempotency、Outbox 和 HTTP/PostgreSQL 验收。
- **不纳入**：`FamilyNeed` 的生成或绑定、`ServiceCase`、FGCN Blueprint、21 天 Action、Service 资源匹配，以及对 Journey 现有 90 天计划事实源的替换或复制。
- **依赖**：确认 `GrowthIntent` 的现有 Named Action/事实源、家庭与主体授权、进入 main composition root 的正式 API route、正式数据库事务、同事务 Audit/Outbox、测试运行时和前端调用契约；另须完成 `0016` migration 治理登记、Fake/PostgreSQL Consent 契约等价性和共享 domain 文件 ownership 审核。

Sprint 1 只有同时满足以下“三件套”才能标记 `DONE`：

1. **代码存在**：有唯一的、可追溯的 `GrowthIntent → Onboarding` 正式实现，包含 Domain/Application/API 与持久化，不是文档、fixture 或页面占位。
2. **测试存在**：有该路径的 Domain/HTTP/拒绝矩阵测试，并至少有 PostgreSQL migration/持久化回读证据；单独的 Family Need VS-01 或 Assessment 定向测试不能替代本项。
3. **可调用 runtime wiring**：实际 `family_api` 入口能挂载并调用同一实现，测试环境不靠未挂载路由、`dev_wiring`、本地状态或测试专用后门。

三件套任一缺失，Sprint 1 保持 `NOT_DONE`。代码存在与测试通过只证明局部能力；只有从真实调用入口走到持久化回读的测试，才可证明该 Sprint 的跨层闭环。

**当前阻断项（全部保持 `OPEN`）**：

| 阻断项 | Owner | 证据命令 | 验收门槛 | 当前状态 |
|---|---|---|---|---|
| `Onboarding` route 未进入 main composition root，连带 API/runtime wiring/HTTP tests 未形成可调用证据 | James + API Contract Owner | `rg -n -i "onboarding|startGrowthOnboarding|include_router|main.*app|family_api" backend/apps backend/domains tests contracts` | 由实际 `family_api` main composition root 导入并挂载正式 route；HTTP 测试从该 root 覆盖成功、未授权、Consent 缺失、重复请求、错误和回读；不能只存在 Domain 代码、孤立 route 或契约文字 | `OPEN / BLOCKS DONE` |
| **P0 Consent tenant/effective-time：租户未收口且有效期不可判定** | **James + Platform / Data Owner** | `rg -n -i "consents|expires_at|effective_from|effective_to|valid_from|valid_to|tenant_family_bindings|subject_person_id|purpose|status" database/baseline database/migrations backend/platform backend/domains tests` | 要么采用现有 canonical consent 有效时间来源并明确语义，要么补正式 schema migration、有效期列/约束和回滚测试；查询必须经 `tenant_family_bindings` 做 tenant scope，并同时判断 effective window、status、撤回/过期，不得只按 `family_id/subject_person_id/purpose/status` | `OPEN / BLOCKS DONE` |
| `growth_journeys` 的 intent 绑定不可直接查询证明 | Growth / Journey Domain Owner | `rg -n -i "growth_journeys|intent_id|growth_intent_id|GrowthIntent|Onboarding" backend database tests contracts` | 提供可审计的直接查询/ReaderPort 证据，证明目标 `GrowthIntent` 与 `Onboarding` 的实际持久化引用、租户/家庭范围和版本一致；不能用推断字段或 fixture 代替 | `OPEN / BLOCKS DONE` |
| 尚无真实回滚与重启回读证据 | Data / Release Owner + QA | `rg -n -i "rollback|restart|recovery|readback|PostgreSQL|alembic" database backend tests docs/11_delivery` | 在正式 PostgreSQL migration 和真实 runtime wiring 上完成 rollback/rebuild、进程重启、重复请求恢复和持久化回读；提交实际命令输出与证据位置 | `OPEN / BLOCKS DONE` |

上述阻断项修复前，Sprint 1 不得标记 `DONE`。**下一 Integration Sprint 只处理 `FamilyNeed → GrowthIntent` 的真实绑定，不得把它或后续 Onboarding/Service/FGCN 闭环并入 Sprint 1 偷换验收。**

### 2.2.0 新增当前硬阻断：交付集成证据未闭环

以下事项均是 Sprint 1 的当前阻断，不是已完成项；每条都必须由对应 Owner 提供可复核证据。Product / Delivery PM 只维护记录，不替代 Owner 修改代码、migration、registry 或共享 WIP。

| 当前阻断 | Owner | 依赖 | 证据命令 | 验收门槛 | 真实状态 | 文件/提交边界 |
|---|---|---|---|---|---|---|
| **Onboarding route 未进入 main composition root** | James + API Contract Owner + Runtime Wiring Owner | Onboarding route/application service 的唯一实现、正式依赖注入、主 `family_api` 装配入口和 HTTP 测试 fixture 必须指向同一 runtime | `rg -n -i "onboarding|startGrowthOnboarding|include_router|mount|main.*app|family_api" backend/apps backend/domains tests contracts`；`D:\AiFamily\.venv\Scripts\python.exe -m pytest tests/apps/family_api tests/domains/journey -q -p no:cacheprovider` | 在生产等价的 main composition root 中实际 import/include route；通过该 root 的 HTTP 测试证明正向、未授权、Consent 拒绝、幂等/错误和回读；不得只证明孤立 route、compile 或 `dev_wiring` | `BLOCKED / NOT_CLOSED` | 仅 James/API/Runtime Owner 修改经确认的 Onboarding route、composition root、应用装配和对应 HTTP 测试；不借此扩展 `FamilyNeed`/Service/FGCN/21 天 Action；本看板不代为提交 |
| **`0016_growth_onboarding_intent_binding` migration 治理登记未闭环** | Migration Owner + Compliance / Governance Owner（James 提供业务范围核对） | 迁移 revision、父依赖、canonical scope、owner/status 与 `governance/MIGRATION_MANIFEST.yaml` 的登记必须一致；不得用临时数据库或 `create_all` 绕过登记 | `rg -n -i "0016_growth_onboarding_intent_binding|growth_onboarding_intent_binding|0016" database/migrations database/baseline governance tests`；`git status --short --untracked-files=all -- database/migrations/versions/0016_growth_onboarding_intent_binding.py governance/MIGRATION_MANIFEST.yaml`；`git diff -- governance/MIGRATION_MANIFEST.yaml` | 在不改写历史的前提下完成 canonical migration 登记、依赖/顺序/owner/status 可追溯；在真实 migration chain 上验证 fresh upgrade 与增量 upgrade；登记未闭环前不得将 `0016` 视为可交付证据 | `BLOCKED / NOT_CLOSED` | 本会话不修改 migration 或 registry；只有 Migration/Governance Owner 按既有流程处理登记并限定于 `0016` 及其登记项；不得删除 migration、绕过 migration 或把独立测试冒充治理闭环 |
| **Fake / PostgreSQL Consent 功能契约不等价** | Platform / Consent Owner + Data Owner；Arendt 负责门禁 | canonical Consent schema/有效期来源、`tenant_family_bindings` tenant scope、`ConsentGate` 撤回语义、Fake 与 PostgreSQL adapter 的同一 Port/错误语义和真实 migration chain | `rg -n -i "ConsentGate|consent|expires_at|effective_from|effective_to|valid_from|valid_to|revoke|revok|tenant_family_bindings|Fake|Postgres|SQLAlchemy" backend/platform/consent backend/domains tests database`；`D:\AiFamily\.venv\Scripts\python.exe -m pytest tests/platform/consent tests/domains/journey -q -p no:cacheprovider` | Fake 与 PostgreSQL 必须通过同一功能契约和同一矩阵：跨 tenant 拒绝、purpose/status、effective window、撤回即时失效、时间边界、旧数据兼容和错误语义；必须有真实 PostgreSQL migration/SQL 证据，已有 Fake adapter 或单域测试不能通过本阻断 | `BLOCKED / NOT_CLOSED` | 仅 Consent/Platform/Data Owner 修改已核准的 Consent contract/adapter/测试；如 canonical schema 确实不足，另行走正式 migration 与回滚流程；不得通过删除拒绝用例、放宽 baseline、伪造有效期或把 Fake 结果写成 PG 证据 |
| **共享 `backend/domains/journey/domain/models.py`、`errors.py` ownership 未确认** | Popper 负责 ownership 审核；Journey Domain Owner、Family/Integration Owner 待确认 | 必须先确认文件来源、事实 Owner、唯一 canonical contract、调用方和与当前共享未跟踪 WIP 的最小变更边界，才能进入 Sprint 1 runtime 集成 | `git status --short --untracked-files=all -- backend/domains/journey/domain/models.py backend/domains/journey/domain/errors.py backend/domains/family/domain`；`git log --all --oneline -- backend/domains/journey/domain/models.py backend/domains/journey/domain/errors.py`；`rg -n "domain\.(models|errors)|from .*models|from .*errors" backend/domains tests` | 形成书面 owner/source/范围确认；每个共享类型和错误码只有一个事实源，调用关系和最小 diff 可审计；Owner 确认前不得覆盖、格式化、重提交或把该 WIP 接入 Onboarding | `BLOCKED / OWNERSHIP_UNCONFIRMED` | 只由 Popper 组织归属确认；确认前任何 Agent 不修改这两个文件，也不把它们纳入 James 的 Onboarding 提交；PM 仅登记，不替代 ownership 决策 |

上述四项中任一项未关闭，均不计入“代码 + 测试 + wiring + 真实迁移证据”完成三件套；它们与 Family E501 质量轨道并行，但不能互相代验收。禁止删除未知 WIP、抬高 baseline、修改 `pyproject.toml`、增加 `# noqa`、绕过正式 migration，或用单域通过、Fake adapter、孤立 route 和静态登记冒充跨域闭环。

**Schema 核对更正（非阻断）**：完整 baseline 迁移链中的 `database/baseline/0044_ui03_growth_hypothesis_confirmation.sql:29-33` 已 `ADD COLUMN boundary`，因此 `gi.boundary` 在完整链上有字段；撤销“`growth_intents` 缺 `boundary`”及“必须新增 migration”的判断。不得为此新增或修改 migration，reader 也不得假造列名或静默改变 `OPEN` / confirmed 语义。

**角色执行约束**：

- **James** 负责按真实 canonical consent schema/有效期来源修正 adapter 和 domain contract；只有在现有来源确实不足时，才提出正式 consent schema migration、约束、回滚和旧数据兼容证据。不得为 `boundary` 新增或修改 migration。
- **Laplace** 将“Consent 未经 `tenant_family_bindings` 收口/有效时间不可判定”列为反向挑战；必须审查迁移前后 schema、旧数据、撤回、过期、时间边界和跨 tenant 矩阵。`growth_intents.boundary` 不再是阻断。
- **Arendt** 只接受真实 PostgreSQL migration chain 上的 Consent SQL 证据；compile、fake repository 或独立单域测试不能通过本阻断，也不能冒充 E2E。需覆盖 tenant scope、撤回和 effective-time 边界。
- **Popper** 维护本看板的 P0 状态与证据索引；未完成上述兼容性和有效期门禁前，保持 `NOT_DONE`。

禁止删除功能、抬高质量 baseline、修改 `pyproject.toml`、绕过正式 migration、为 `boundary` 新增/修改 migration、假造列名、静默改变 `OPEN`/confirmed 语义，或用两套独立测试通过冒充跨域 E2E。

### 2.2.1 Sprint 1 两条并行轨道

两条轨道可以并行推进，但不能互相代验收；任何一条未满足自己的阻断与验收门槛，Sprint 1 完成状态仍为 `NOT_DONE`。

| 轨道 | Owner | 当前阻断 | 验收命令 | 完成门槛 | 文件/提交边界 |
|---|---|---|---|---|---|
| **A：Family `entities.py` E501 独立修复** | Family Domain 负责人（真实 owner 待审核） | `backend/domains/family/domain/entities.py:331:101` 的 `E501`（102 > 100）阻断全局质量门；`212d560` 虽只触及一个路径，却新增 348 行且父提交没有该文件，不能视为“只改一处签名”或直接集成 | 定位：`D:\AiFamily\.venv\Scripts\ruff.exe check --no-cache D:\AiFamily\backend\domains\family\domain\entities.py --select E501`；提交审核：`git show --stat 212d560`、`git ls-tree -r --name-only 212d560^ -- backend/domains/family/domain/entities.py`、`git status --short --untracked-files=all -- backend/domains/family`；修复后才跑全局 Ruff 与 `D:\AiFamily\.venv\Scripts\python.exe -m pytest tests/architecture -q -p no:cacheprovider` | 先确认真实 owner/source，并给出相对当前共享 WIP 的最小 diff；只做函数签名最小换行，行为不变；在边界确认前不得把 `212d560` 当验收证据或质量门禁已关闭；不得继续处理其它 Ruff | 暂停 `212d560` 集成；若文件属于他人 WIP，不得覆盖/重提交。任何后续提交只能限定于经确认的最小文件 diff；禁止改 baseline、`pyproject.toml`、加 `# noqa`、删除/排除未知 WIP；本看板不代为提交 |
| **B：`GrowthIntent → Onboarding` API / wiring / Consent / schema / PostgreSQL 验收** | James + API Contract Owner + Platform/Data Owner + QA | 无可调用 Onboarding API/runtime wiring/HTTP tests；Consent 未证明 tenant scope、撤回和 effective window；尚无完整 migration chain、回滚和重启回读证据 | 现状核对：`rg -n -i "onboarding|startGrowthOnboarding|include_router|family_api|consent|tenant_family_bindings|expires_at|effective_from|effective_to" backend/apps backend/domains tests contracts database`；候选验收：`D:\AiFamily\.venv\Scripts\python.exe -m pytest tests/apps/family_api tests/domains/journey tests/database -q -p no:cacheprovider`；最终仍需全局 Ruff 与架构命令 | 代码 + 测试 + 可调用 runtime wiring 三件套；正式 API/HTTP 成功与拒绝矩阵；Consent 经 `tenant_family_bindings` 收口并判断有效期/撤回；真实 PostgreSQL migration chain、回滚、重启回读、幂等和 Audit/Outbox 证据；单域测试或已有 adapter 不能通过本轨道 | 仅允许 James/对应 Owner 修改已核准的 GrowthIntent/Onboarding、Consent、API/wiring 与测试文件；如 canonical consent schema 确实不足，才可另提正式 consent migration 及回滚；禁止触碰 `growth_intents.boundary` 或 `0044` migration，禁止扩展 FamilyNeed/Service/FGCN/21 天 Action，禁止复制或改写 Journey 90 天计划事实源；本看板不代为提交 |

**轨道关系与验收口径**：轨道 A 通过只表示质量债减少；轨道 B 的单域测试、Fake adapter 或编译通过只表示局部证据。只有轨道 B 从实际 `family_api` 入口完成 `GrowthIntent → Onboarding`，并在真实 PostgreSQL 上证明 tenant/Consent/effective-time、事务写入、回滚与重启回读，才可将对应的 `cross_domain_loop_pass` 置为 `true`；否则保持 `false`，Sprint 1 保持 `NOT_DONE`。

**反向核验（Laplace）**：Family Need VS-01 + Assessment 定向测试虽有 **54 passed**，但它们是两个独立测试闭环；`rg` 已确认当前没有证据证明 `FamilyNeed` 被实际生成并绑定到 `GrowthIntent`、`ServiceCase` 或 FGCN Blueprint。因此该结果只能登记为“单域/定向测试通过”，不得登记为“跨域集成通过”。

**验收加严（Arendt）**：验收记录必须分别填写 `single_domain_pass` 与 `cross_domain_loop_pass`。两套独立测试各自通过、没有同一事务/事件链上的真实记录引用和端到端回读时，`cross_domain_loop_pass` 必须为 `false`。

### 2.2.2 `212d560` 提交边界审核：暂停集成

**状态：`BLOCKED / OWNERSHIP_REVIEW`。** 只读核验显示：`212d560` 的 stat 虽只触及 `backend/domains/family/domain/entities.py` 一个路径，但新增 **348 行**；其父提交没有该文件；当前共享工作区的 `backend/domains/family/` 仍包含并发未跟踪 WIP。因此不能把该提交描述为“只改一处签名”，也不能直接 cherry-pick 到共享分支。

| 责任 | Owner | 必须执行/核验 | 通过条件 | 当前约束 |
|---|---|---|---|---|
| 真实 owner/source 与最小 diff | Family Domain 负责人 | `git show --stat --oneline 212d560`；`git ls-tree -r --name-only 212d560^ -- backend/domains/family/domain/entities.py`；`git diff 212d560^ 212d560 -- backend/domains/family/domain/entities.py`；`git status --short --untracked-files=all -- backend/domains/family` | 确认文件真实 owner/source，并相对当前共享 WIP 给出最小 diff；若属于他人 WIP，明确转交且不得覆盖/重提交 | 暂停提交集成；不得继续处理其它 Ruff；不得用 commit stat 推断已完成 |
| 业务范围隔离 | James | 检查 Sprint 1 的提交/变更清单与 `GrowthIntent → Onboarding` 范围 | `212d560` 不纳入 Onboarding 实现，也不纳入总提交；仅经 owner 审核后的最小变更才可重新排队 | 不得 cherry-pick `212d560`，不得借此扩展 Family/Onboarding 业务范围 |
| 质量与提交边界审查 | Arendt | 同时检查父提交 tree、`git show --stat`、当前工作树和文件内容；不能只看 `git diff --name-only` 或 name-only 列表 | 报告标记为“路径隔离通过但提交边界未确认”；只有 ownership、来源和最小 diff 确认后，才可重跑相关质量门 | `212d560` 不计入质量门禁已关闭，不得以单文件路径隔离通过替代提交边界证明 |
| 看板与集成状态 | Popper | 维护本节状态、证据命令和后续决策记录 | ownership 审核完成前保持 `BLOCKED`，并从“已关闭质量门禁”统计中排除 | 本次只更新看板；不覆盖共享 WIP、不重提交、不修改业务代码 |

本审核与两条 Sprint 1 并行轨道分离：Family E501 轨道仍只能由真实 owner 产生最小 diff；`GrowthIntent → Onboarding` 轨道不得吸收 `212d560` 或借其扩大范围。质量报告必须区分“路径隔离通过”与“提交边界确认通过”。

### 2.3 后续 Sprint 及其边界

| 计划 | Owner | 固定范围 | 前置依赖 | 当前状态 |
|---|---|---|---|---|
| **Sprint 2：21 天 Action** | Journey Domain Owner + Data/QA | 21 天 Action API、正式持久化、今日行动/完成/跳过/暂停/补救、重启回读与状态机 | Sprint 1 三件套；Journey 现有 90 天计划事实源可读取且不被复制 | `PLANNED / NOT_STARTED`，不得提前并入 Sprint 1 |
| **下一 Integration Sprint** | **Popper**（Integration Owner） | 只验证 `FamilyNeed → GrowthIntent` 的真实生成、事件/reader port 引用、事务边界和回读；不提前接入 Onboarding、ServiceCase 或 FGCN Blueprint | `FamilyNeed` 与 `GrowthIntent` 各自事实源可读；事件、reader port、事务边界、Consent/Audit/Outbox 契约先冻结；Fake + PostgreSQL E2E 可复核 | `PLANNED / NOT_STARTED`，独立于 Sprint 1 |

Sprint 2 必须沿用 Journey 已有 **90 天计划事实源**，不得另建第二套计划真相；21 天 Action 是后续交付形态，不得反向改变 Sprint 1 的 `GrowthIntent → Onboarding` 范围。

下一 Integration Sprint 的最低设计约束由 Popper 负责落入后续任务卡；ServiceCase/FGCN 等更晚的跨域协作不得借本 Sprint 提前纳入：

- **事件/reader port**：用版本化领域事件通知跨域事实变化；通过只读 `ReaderPort` 获取被授权的事实，不跨域写对方聚合，不用共享 ORM 或隐式 import 拼接闭环。
- **事务边界**：每个 Domain 只在自己的事务内写权威事实；本域事实、Audit 和 Outbox 在同一事务提交；跨域消费以 `event_id`、幂等键和 correlation ID 去重，不假设分布式事务。
- **Consent / Audit / Outbox**：每次跨域读取按主体、目的和可见范围校验 Consent 并留读取审计；每次状态写入留变更审计；事件必须与事实写入原子落库。
- **Fake + PostgreSQL E2E**：同一业务流程分别使用可审计 Fake adapter 和正式 PostgreSQL 跑完整 E2E，验证真实记录引用、拒绝路径、重启回读、重复投递和失败补偿；两组独立单域测试不得代替该 E2E。

### 2.4 当前共享 WIP 的文件归属

以下是交付追踪中的归属边界，不是修改授权。各 Owner 只处理自己负责的文件；未知或临时 WIP 保持原样，不因质量扫描而删除。

| 共享 WIP 文件/范围 | 归属 Owner | Sprint 1 处理方式 |
|---|---|---|
| `backend/domains/family/domain/entities.py`（含 `:331`） | Family Domain 负责人（真实 owner/source 待确认） | 当前为共享未跟踪 WIP；`212d560` 的路径隔离可核对，但提交边界未确认。James 只登记 Sprint 1 依赖；不得覆盖/重提交该文件，本看板不改代码 |
| `backend/domains/journey/domain/models.py` | Journey Domain Owner / Integration Owner（真实 owner/source 待确认） | 当前为共享未跟踪 WIP；ownership、canonical 类型边界和最小 diff 未确认。不得被 James 纳入 Onboarding 提交，不得覆盖/格式化/重提交 |
| `backend/domains/journey/domain/errors.py` | Journey Domain Owner / Integration Owner（真实 owner/source 待确认） | 当前为共享未跟踪 WIP；错误码/异常事实源与调用方 ownership 未确认。不得被 James 纳入 Onboarding 提交，不得覆盖/格式化/重提交 |
| `backend/domains/journey/**`、`frontend/mobile/app/journeys/**`、`frontend/mobile/app/actions/today.tsx`、`tests/domains/journey/**` | Journey Domain Owner | 保留现有 90 天计划事实源；21 天 Action 留到 Sprint 2，不在 Sprint 1 改动或复制 |
| `backend/domains/service/**`、`tests/domains/service/**`、`tests/apps/family_api/test_fgcn_routes.py` | Service / FGCN Owner | ServiceCase、FGCN Blueprint 和协作闭环留给后续 Integration Sprint；Sprint 1 不扩文件范围 |
| `backend/intelligence/**`、`tests/intelligence/**`、`database/migrations/versions/0014_tool_action_outbox.py` | AI Runtime / Platform Owner | 作为 AI/治理共享 WIP 记录；只有满足 Sprint 1 runtime wiring 依赖时才由对应 Owner 处理，不由 James 顺手修改 |
| `frontend/mobile/lib/family/**`、`backend/apps/family_api/**`、`contracts/openapi/UI_API_ENDPOINT_INVENTORY.md` | API Contract + Frontend Owner | 只核对 endpoint 漂移；不以页面可导航、fixture 或删除调用来消除缺口 |
| `.codex-tmp/pytest-of-Lenovo/pytest-0/test_axis_separation_negative_0/bad.py` | **归属未确认；QA 质量守护牵头识别生成来源** | 只记录 F401 和访问边界；不得删除、清理或擅自加入排除项 |

### 2.5 单域通过与跨域闭环通过的登记格式

所有 Sprint 报告必须使用以下区分：

| 证据类型 | 可以声称 | 不可以声称 |
|---|---|---|
| 单域/定向测试通过（例如 VS-01 + Assessment `54 passed`） | 该测试范围内的规则或投影通过 | `FamilyNeed → GrowthIntent → Onboarding → Service/FGCN` 已打通 |
| 跨域闭环通过 | 同一条真实调用链完成事件/reader port、事务、Consent、Audit、Outbox、Fake + PostgreSQL E2E 和回读 | 其它未覆盖的域、事件或生产供应商已完成 |
| 代码存在 + 测试存在但无 runtime wiring | 局部实现已落盘 | 可调用能力、生产等价能力或 Sprint 完成 |

## 3. P0-P3 纵向切片

每个切片均须从家庭端入口走到持久化、审计、错误处理和可回读结果；切片之间不以“先把所有层做完”作为完成条件。

### P0｜家庭建档与安全控制面

**用户结果**：一个真实测试家庭能够创建家庭、加入家长与孩子、建立关系、按目的授予或拒绝同意，并在重启后保持正确的身份、权限和同意状态。

**纵向路径**：

```text
创建家庭 → 添加家庭成员 → 建立亲子关系
  → 选择具体处理目的并同意/拒绝 → 读取家庭上下文
  → 撤回同意或删除请求 → 看到明确结果与审计记录
```

**必须交付**：

- family / identity / relationship 的正式 API、持久化和错误码；测试环境不再以进程内合成家庭充当真实建档能力。
- `ActorContext`、`TenantContext`、最小权限、家庭隔离、目的化 Consent、读取与状态变更 Audit、Idempotency 全部接入同一条路径。
- PostgreSQL 正式迁移、重启回读、撤回后的立即失效，以及面向孩子主体的删除/派生数据清除接口契约。
- 移动端能呈现成功、拒绝、无权限、撤回后失效和重试状态；不存在开发专用业务路由。

**退出证据**：S-04 在测试环境使用 PostgreSQL 跑通；跨租户、非家庭成员、缺失同意、重复请求、撤回后访问均有拒绝测试；没有把同意或家庭关系硬编码进 fixture 以外的业务代码。

**P0 阻断条件**：真实 identity / consent 存储未接线；Alembic 迁移与 ORM 不一致；读取未成年人数据无审批与访问记录；使用 `dev_wiring` 才能完成路径。

### P1｜测评、AI 假设解读与成长意图确认

**用户结果**：家长能够表达一个具体家庭困境，完成测评，看到可解释的 AI 假设解读，并确认一个成长意图；AI 不把假设写成事实。

**纵向路径**：

```text
家庭困境/测评输入 → 证据归档 → AI 生成 Hypothesis / Perspective
  → 展示依据、限制与不确定性 → 家长接受/拒绝/修订
  → Named Action 确认 GrowthIntent → 事件、审计与 provenance 落库
```

**必须交付**：

- Assessment 的 evidence / hypothesis / interpretation 分层及其 API、数据库和验收链；`Hypothesis` 初始状态为 `DRAFT` 或 `PROPOSED`。
- provider-neutral Model Gateway、Context Snapshot、Prompt/Schema 版本、模型版本、置信度和人工辅助来源等 provenance。
- 人工复核、可解释、可拒绝、重新生成和失败关闭路径；AI 只能提出成长意图草案，不能直接确认家庭事实或计划。
- 前端从测评开始到意图确认的完整链路，包括超时、空结果、拒绝和人工升级状态。

**退出证据**：同一份测试场景在 FakeProvider 与获准 provider adapter 下通过同一业务规则；模型不可用时，系统返回可解释的失败/人工处理状态而不是硬编码“智能结果”；确认后的事实可追溯到 actor、purpose、provenance、correlation ID 和 AuditEvent。

**P1 阻断条件**：没有 Model Gateway 或调用绕过 Gateway；AI 输出可直接置为 `VALIDATED` / `APPROVED`；没有人工复核/退出；模型输入未通过家庭与未成年人 Consent；把结果展示为诊断、疗效或家庭总分。

### P2｜成长计划、行动证据与私有复盘

> 本节对应后续 Sprint 2 及更晚的交付，不属于当前 Sprint 1；Sprint 2 的 21 天 Action 不得改变 Journey 现有 90 天计划事实源。

**用户结果**：家长从已确认的成长意图获得一个可调整的 21 天行动计划，家庭成员完成日常行动并留下证据，随后看到基于事实的私有过程复盘和下一步建议。

**纵向路径**：

```text
GrowthIntent → AI 生成 Plan Draft → 家长确认计划
  → 今日行动 → 完成/跳过/暂停/补救
  → Evidence / Reflection → 私有复盘 → 下一步 Recommendation
```

**必须交付**：

- Journey / GrowthPlan / Action / OutcomeEvidence 的事实边界、状态机、版本和事件；计划变更产生新版本，不静默覆盖历史。
- workflow worker 负责到期、重试、人工升级和补救；Outbox / relay / projector 具备幂等和回放能力。
- AI 生成计划与复盘时只读取获准的最小上下文，只输出 Draft / Recommendation；家长确认计划、暂停行动和标记结果均是受审计的 Named Action。
- “过程回顾”只呈现已发生的行动、证据、家庭自述和局限，不计算或暴露家庭总分、家庭排名或无证据的成长效果断言。

**退出证据**：完整跑通至少一个 21 天中的可缩短测试时钟版本，但 Workflow、状态迁移、重试和人工升级与生产一致；重复投递、乱序事件、进程重启、任务暂停/恢复、删除家庭成员派生数据均有测试；复盘内容能回溯到证据而非模型臆测。

**P2 阻断条件**：没有持久化 Workflow 载体；测试环境用同步函数替代生产 Workflow；计划或复盘直接写成长事实；证据、快照、embedding 或缓存不在撤回/删除链中；前端仍依赖合成成长卡片。

### P3｜服务协作、交付验收与需求回流

**用户结果**：当家庭需求超出自助行动时，家长能够看到受治理的服务/资源建议，提交请求，获得案件与任务跟踪，完成交付和质量验收，并把未解决项回流为新的家庭需求。

**纵向路径**：

```text
未解决 Need → AI 生成资源/方案 Recommendation
  → 家长查看适用条件与缺口 → Named Action 提交服务请求
  → ServiceCase → ServiceTask / Assignment
  → DeliveryRecord → QualityDecision（通过/返工/补救/争议）
  → OutcomeEvidence / NextNeed
```

**必须交付**：

- `ServiceBlueprintVersion`、`ServiceCase`、`ServiceTask`、`TaskAssignment`、`DeliveryRecord`、`QualityDecision` 的版本、责任人、SLA、验收和补救规则。
- 资源能力、可用性、区域、语言、资质和供给缺口的可解释查询；资源不足返回 `RESOURCE_GAP`，不得伪造供给。
- AI 只解释匹配并提出方案草案；服务分派、价格/订单、对外承诺、质量验收和投诉关闭均由业务 Owner 或人工完成并审计。
- 交付质量、贡献记录和下一需求回流可查询；家庭私有事实不得未经授权写入公共知识或资源质量资料。

**退出证据**：至少一个轻量 FGCN 案例在测试环境完成从请求到交付验收的全链路；任务责任人唯一、分配幂等、改派/暂停/失败补救/争议路径可回放；服务人员和家庭两侧均能看到与权限相符的状态；生产发布不新增未在测试环境验证的业务分支。

**P3 阻断条件**：ServiceCase 与 GrowthIntent / Need 没有可追溯引用；AI 自动分派或关闭投诉；没有交付凭证与质量决定；仅有预约页面而没有案件、任务、SLA、补救和验收链。

## 4. 生产等价测试要求

### 4.1 等价原则

测试环境必须证明“功能相同、依赖可替换”，而不是证明“测试专用功能能跑”。下列内容必须与生产相同：

- 路由、API schema、成功/拒绝/超时/幂等/错误语义；
- Domain 聚合、业务规则、状态机、Named Action、事件、重试、补偿和人工闸门；
- identity、tenant、家庭成员权限、Consent、未成年人保护、Audit 和数据目的；
- AI Runtime 的上下文边界、输入输出 schema、provenance、限制、失败关闭和人工确认；
- 服务案件、任务、分派、交付、质量、补救、贡献和争议规则；
- 前端可见状态和完整用户路径。

仅允许替换数据库实例/数据集、模型/支付/通知供应商适配器、密钥、时间/队列控制、容量与日志采样。所有 synthetic 数据必须显式标识为 `data_class=SYNTHETIC`，且只能经生产同样的 Port / Adapter 接口注入。

### 4.2 每个切片的强制测试包

| 测试包 | 必须证明的内容 | 最低证据 |
|---|---|---|
| 契约与 HTTP | 正向、校验失败、拒绝、超时、重试、幂等和错误码与前端一致 | OpenAPI/契约测试 + HTTP 验收测试 |
| 领域与状态机 | 合法迁移、反向迁移、重复命令、并发/过期版本、补救和历史不可变 | Domain 测试 + 状态转移矩阵 |
| 权限与合规 | 跨租户/跨家庭隔离、最小权限、目的化 Consent、撤回即时失效、未成年人读取审批 | 读写 Audit 断言 + 拒绝矩阵 + 删除/留存测试 |
| AI 治理 | Model Gateway 统一入口、provider 失败关闭、provenance 完整、DRAFT/PROPOSED 初始态、人工闸门和可拒绝 | FakeProvider/获准 adapter 同套验收 + 架构检查 + 人工闸门测试 |
| 数据与迁移 | 正式 migration 可建库，ORM 与 schema 一致，进程重启后可回读，派生数据按主体删除 | `alembic upgrade head` + PostgreSQL 持久化/重启测试 + 删除演练 |
| Workflow 与事件 | Outbox 写入、relay 重试、重复投递幂等、乱序/断点续跑、人工任务和补偿 | Worker 集成测试 + 故障注入 + replay 记录 |
| 端到端场景 | 家庭端从入口到最终结果可完成，真实状态可查询，数据来源和外部副作用可解释 | 每个切片至少一条完整 E2E；测试环境无 `dev_wiring` 依赖 |
| 发布与运行 | 监控、告警、人工升级、降级、停止、回滚可执行 | Runbook + 回滚演练 + 运行日志/trace/correlation ID |

### 4.3 明确禁止的测试捷径

- `if environment == test` 跳过权限、Consent、Audit、幂等、人工闸门或状态机。
- 测试环境独有业务路由、万能写入后门、开发按钮或同步 Workflow 假实现。
- 用硬编码金额、积分、会员、成长结果、服务记录或 AI 文案冒充正式数据。
- 因真实 LLM、支付、通知供应商未准入而删掉完整业务路径；必须使用同接口、同规则、可审计的 sandbox / fake adapter。
- 只跑 SQLite 内存库而宣称 PostgreSQL 生产等价；只测截图或页面渲染而不测 HTTP、持久化、权限和拒绝路径。

## 5. 完成定义（Definition of Done）

### 5.1 任务级完成

- 场景、Owner、范围外清单、数据目的、接口/事件、测试用例和回滚动作已关联；
- 代码与测试落在唯一约定的战场，未引入第二个业务后端、重复 Domain 或测试专用业务路径；
- 相关测试真实通过；质量门以 `D:\AiFamily\.venv\Scripts\ruff.exe check --no-cache D:\AiFamily` 为准，架构检查使用 `D:\AiFamily\.venv\Scripts\python.exe -m pytest tests/architecture -q -p no:cacheprovider`；两者的实际输出、失败项和跳过原因均已记录；
- 正向与拒绝路径均通过，Audit、Consent、Idempotency、provenance 和 correlation ID 可查；
- 失败不是“未发现”，而是有责任人、补救动作、重新验证时间和是否阻断 Gate 的明确记录。

### 5.2 切片级完成

一个 P0-P3 切片只有同时满足以下条件，才可标记 `DONE`：

1. 家庭端完整路径在开发环境与测试环境均可走通，且测试环境不依赖 `dev_wiring`、开发专用路由或硬编码结果；
2. 同一套业务验收套件覆盖成功、拒绝、权限/Consent、幂等、超时、重试、重启回读、删除和人工升级；
3. PostgreSQL 正式迁移和回滚/重建路径通过；至少一条 PostgreSQL 重启回读测试通过；
4. AI 参与的切片具备 Model Gateway、Context/Provenance、DRAFT/PROPOSED、Human Gate 和人工拒绝/接管路径；非 AI 支撑流程不为“塞 AI”而改变边界；
5. 没有家庭总分/排名、临床诊断、儿童端自动化商业营销、AI 自动写事实或供应商直连；
6. QA、Compliance、Domain Owner、Product / Delivery PM 和 Release Owner 对证据包完成签字式确认；
7. 运行手册包含监控、人工升级、限流/停止、数据修复边界和回滚点；生产只需切换已获准的数据/外部适配器，不需补做新的业务分支。

### 5.3 阶段级完成

阶段完成不是四个切片“都开发过”，而是：

- 本阶段所有阻断风险已关闭或获明确书面接受，且不允许以“后续优化”掩盖红线缺口；
- 测试环境通过同一套生产等价验收套件，CI 可重复运行；
- 发布基线冻结代码、数据库迁移、配置、模型/Prompt/Schema 版本、测试证据、SLO、Runbook 和回滚点；
- 对未完成能力保留 `NOT_STARTED` / `IN_PROGRESS` 等真实状态，不用页面存在、代码迁入或演示成功替代生产能力证明。

### 5.4 当前质量闸门与共享 WIP 追踪

本节是当前 Sprint 的门禁快照，不是完成声明。质量状态以仓库内 Ruff 0.16.5 的无缓存命令为准；`uv run` 入口遇到本机 uv cache、`.venv` 或 `.ruff_cache` 权限问题时，只记录为环境问题，不把该入口失败当作代码失败，也不以它替代仓库 Ruff 证据。

最终质量扫描命令：

```text
D:\AiFamily\.venv\Scripts\ruff.exe check --no-cache D:\AiFamily
```

当前追踪口径为 **2 个真实红项**：

1. `backend/domains/family/domain/entities.py:331:101` — `E501`，102 > 100；
2. `.codex-tmp/pytest-of-Lenovo/pytest-0/test_axis_separation_negative_0/bad.py:1:60` — `F401`，临时 fixture，生成来源与质量扫描归属待确认。

| 当前记录 | Owner | 证据命令 | 验收门槛 | 状态/禁止事项 |
|---|---|---|---|---|
| P0：Family `entities.py:331` E501 | Family Domain 负责人 | `D:\AiFamily\.venv\Scripts\ruff.exe check --no-cache D:\AiFamily` | 仅对 `subject_age_years` 签名做最小换行；不得改变行为或扩大文件范围。完成后必须重跑全局 Ruff 与架构测试，并报告精确文件、输出和提交状态 | `BLOCKED`。禁止抬高 baseline、修改 `pyproject.toml`、增加 `# noqa`；本看板不修改业务代码 |
| P0：`.codex-tmp` fixture F401 | QA 质量守护（牵头确认生成来源）+ 生成该 fixture 的测试责任人 | 同上；定点路径：`.codex-tmp/pytest-of-Lenovo/pytest-0/test_axis_separation_negative_0/bad.py` | 先确认生成来源、生命周期和归属；另行提出质量扫描隔离/临时目录处理方案，再以无缓存 Ruff 复核 | `OPEN`。撤销清理/排除要求；不得删除任何临时文件或未知 WIP，不得用临时 `--exclude` 或 baseline 变更假装通过 |

**已不作为当前门禁问题的记录**：

- `backend/intelligence/tool_runtime` 两个 `I001`：`D:\AiFamily\.venv\Scripts\ruff.exe check --no-cache D:\AiFamily\backend\intelligence\tool_runtime --select I001`，已通过；仅移出当前门禁，不代表 AI Runtime 闭环完成。
- `0013` migration：`D:\AiFamily\.venv\Scripts\python.exe -m pytest tests/database/test_alembic_baseline_applies.py -q -p no:cacheprovider` 当前相关检查通过；数据库其它迁移、生产 schema 和业务持久化仍按各自 Gate 验收。
- `DOMAIN_REGISTRY` YAML 语法错误：不再列为当前质量门禁问题；其它治理/登记缺口仍保持 `NOT_CLOSED`，不得由本条“已解除”推导为治理完成。

**架构证据**：

```text
D:\AiFamily\.venv\Scripts\python.exe -m pytest tests/architecture -q -p no:cacheprovider
109 passed, 1 skipped, 1 failed
失败：tests/architecture/test_lint_debt_ratchet.py::test_ruff_error_count_never_regresses
```

上述架构结果保持 `NOT_CLOSED`。修复后必须重新执行：

```text
D:\AiFamily\.venv\Scripts\ruff.exe check --no-cache D:\AiFamily
D:\AiFamily\.venv\Scripts\python.exe -m pytest tests/architecture -q -p no:cacheprovider
git status --short -- backend/domains/family/domain/entities.py docs/11_delivery/FAMILY_GROWTH_PLATFORM_EXECUTION_BOARD_V1.md
```

除执行看板外，本 Sprint 不产生本会话提交；质量门禁不得通过删除未知 WIP、抬高 baseline、修改 `pyproject.toml` 或添加 `# noqa` 解决。

### 5.5 业务反向核验与未闭环记录

Family Need VS-01 + Assessment 定向测试的 **54 passed** 只能登记为单域/定向测试通过。以下 `rg` 核验显示，当前没有可采信的真实调用链证明 `FamilyNeed` 被生成并绑定到 `GrowthIntent`、`ServiceCase` 或 FGCN Blueprint：

```text
rg -n -i "FamilyNeed|GrowthIntent|ServiceCase|FGCN|ServiceBlueprint" backend tests contracts
```

该结果与 54 passed 必须分开记录：它们是两个独立闭环，不是跨域端到端能力。Laplace 负责将其作为反向挑战项；Arendt 负责在验收单中强制填写 `single_domain_pass` 与 `cross_domain_loop_pass`，后者没有真实事件/reader port 链路和 E2E 时必须为 `false`。

| 未闭环项 | Owner | 证据命令 | 验收门槛 | 状态/禁止事项 |
|---|---|---|---|---|
| `GrowthIntent → Onboarding` 的 Sprint 1 三件套 | James | `rg -n -i "GrowthIntent|Onboarding|startGrowthOnboarding|confirmGrowthIntent" backend tests contracts` + 运行时入口/HTTP 测试 | 代码存在、测试存在、可调用 runtime wiring 三者齐全；确认后的 `GrowthIntent` 经正式 Named Action、Consent、Audit、Outbox 持久化并可回读 | `NOT_DONE` 直至三件套证据齐全；不扩 FamilyNeed/Service/FGCN 文件范围 |
| FamilyNeed → GrowthIntent / ServiceCase / FGCN Blueprint 真实绑定 | Laplace（反向挑战）+ Popper（后续集成负责人） | `rg -n -i "FamilyNeed|GrowthIntent|ServiceCase|FGCN|ServiceBlueprint|ReaderPort|outbox" backend tests contracts` | 后续 Integration Sprint 用真实事件/reader port、明确事务边界、Consent/Audit/Outbox 及 Fake + PostgreSQL E2E 证明记录引用和回读 | `NOT_CLOSED`；54 passed 不得转写为跨域通过 |
| 21 天 Action API/持久化与 `REVIEW_DUE` 推进 | Journey Domain Owner + Workflow/Data Owner | `rg -n -i "growth/actions/today|GrowthAction|JourneyTask|REVIEW_DUE|review.*due|workflow_worker" backend tests contracts` | 进入 Sprint 2 后，使用 Journey 现有 90 天计划事实源，补正式 Action 持久化、worker 推进、重试、幂等、重启回读和人工升级 | `PLANNED / NOT_CLOSED`；不得在 Sprint 1 改造或复制 90 天计划事实源 |
| 前后端 endpoint 漂移 | API Contract Owner + Frontend Owner | `rg -n -i "MISSING|startGrowthOnboarding|confirmGrowthIntent|growth/actions/today|/growth/" contracts/openapi/UI_API_ENDPOINT_INVENTORY.md frontend/mobile/lib backend/apps/family_api backend/domains` | 冻结单一 contract；每个调用有正式 route、错误/拒绝/超时/幂等语义和 HTTP E2E | `NOT_CLOSED`；页面可导航或 endpoint 清单存在不等于可调用 runtime |
| AI Runtime 治理缺口 | AI Runtime Owner + Compliance | `rg -n -i "Model Gateway|Context|Provenance|Human Gate|DRAFT|PROPOSED|may_mutate_business_state" backend/intelligence tests docs/05_ai` | P1 前满足 Gateway、最小 Context、Provenance、Draft-only、Human Gate、人工拒绝/接管和 Eval；AI 不直写事实 | `NOT_CLOSED`；不得以 fallback、删除测试或登记来伪造完成 |
| 治理/登记与架构门禁缺口 | GOV Owner + QA | `D:\AiFamily\.venv\Scripts\python.exe -m pytest tests/architecture -q -p no:cacheprovider` | 架构测试全绿，治理登记与实际代码一致；保留所有未知 WIP 和失败证据直到明确归属 | `NOT_CLOSED`；禁止抬高 baseline、删 WIP、改他人登记或把权限不可见当作通过 |

## 6. 依赖与推进条件

### 6.1 关键依赖链

```text
P0 家庭建档与控制面
  → P1 测评/假设/成长意图
  → P2 计划/行动/证据/复盘
  → P3 服务协作/交付/质量/需求回流
```

并行但必须在相应切片前完成的横向依赖：

- **平台依赖**：identity、tenant、authorization、Consent、Audit、Idempotency、Persistence；P0 未稳定前，后续切片只能做契约草案，不能宣称可用。
- **数据依赖**：PostgreSQL 分域边界、正式 Alembic migration、ORM 一致性、主体级删除、留存/目的绑定；P2 前必须有事件/Outbox 与派生数据清除方案。
- **AI 依赖**：Model Gateway、Context Snapshot、Prompt/Schema Registry、Provenance、Human Gate、Evaluation；P1 前没有这些能力，就不能把 AI 解读接到家庭业务路径。
- **Workflow 依赖**：`workflow_worker`、重试/补偿/人工任务、relay/projector；P2 前没有就不能以同步函数替代计划和行动流程，P3 也不能验收案件 SLA。
- **契约依赖**：家庭端 UI、OpenAPI、错误码和状态可见性必须按切片同步；UI 迁入不代表后端契约已满足。
- **治理依赖**：实现新 Domain / capability / AI use case 时，须在实现前核对并在交付前同步对应治理登记；本草案不代替该前置检查。
- **发布依赖**：CI 远端执行、测试环境数据与外部适配器隔离、Runbook、监控、回滚和人工值守；没有这些，只能停留在开发/测试级完成。

### 6.2 可并行与不可并行

- 可并行：BA/UX 编写切片契约，Data 设计迁移，QA 准备拒绝矩阵，AI Runtime 准备 provider-neutral 接口，API / Frontend 先对齐 schema；但各自产物必须指向同一切片 ID。
- 不可跨越：P1 不能绕过 P0 的真实家庭、权限和 Consent；P2 不能绕过 P1 的已确认 GrowthIntent；P3 不能绕过 P0 的主体/授权和 P2 的需求/证据引用。
- 不可将“平台地基全部完成”设为唯一前置：平台工作必须随切片形成可运行闭环；也不可把某个页面完成当作切片完成。

## 7. 风险登记与处置

| 风险 | 触发信号 | 影响 | 预防/处置 | 阻断级别 |
|---|---|---|---|---|
| 迁移代码被误报为业务能力 | 只有文件/页面，无 Python API、PostgreSQL 读写或 HTTP 验收 | 交付状态失真，后续排期建立在假设上 | 以切片 E2E、持久化、拒绝矩阵和实际命令输出为唯一证据 | P0 |
| 合成家庭掩盖真实建档缺口 | 依赖 `dev_wiring` 或 fixture 直接注入家庭/Consent | 测试环境无法证明真实主体与授权链 | P0 先完成 S-04；测试环境移除 dev wiring，synthetic 仅作为 adapter 数据 | P0 |
| AI 越权写事实或产生伪诊断 | AI 输出直接 `VALIDATED`/`APPROVED`、无 provenance 或无人工退出 | 家庭事实污染、自动化决策与合规风险 | Draft-only、Human Gate、Named Action、R9 架构测试、人工复核和可拒绝 | P1 |
| 未成年人数据处理不合规 | 无目的/期限、撤回后仍可读、派生向量未删除、读取无审批 | 敏感数据与下架风险 | 目的化 Consent、读取/变更 Audit、主体级级联删除、DPIA 前置和年度审计准备 | P0/P1 |
| Workflow / Outbox 缺失导致假闭环 | 测试通过同步函数，生产才计划接 worker | 重试、补偿、人工任务和回放不可用 | P2 前交付真实 worker、relay、幂等、故障注入和重启回读 | P2 |
| 域边界或 registry 漂移 | 新代码落在重复 Domain，登记状态与磁盘不一致 | R2/R4/R14 失败，事实 Owner 不清 | 实现前核对登记，交付前做 GOV/QA gate；本草案不直接改 registry | P0 |
| 数据库 baseline 与 ORM 不一致 | 只在 `create_all` 测试通过，`alembic upgrade head` 后失败 | 生产启动或域读写失败 | 每个切片均用正式 migration + PostgreSQL；增加 schema/ORM 一致性测试 | P0/P2 |
| 供应商/外部副作用不可用 | LLM、通知、支付或服务供给尚未获准/不稳定 | 团队删减路径或把 fallback 冒充能力 | 使用同 Port/Adapter 的 sandbox/fake，保留完整规则、审计、失败与人工接管；法务未决不得上线真实数据 | P1/P3 |
| 并行会话造成文件或测试污染 | status、registry、测试输出与当前工作不一致 | 错误归因、误覆盖、无法复现 | 每次开工先看 status；只改自己的文件；路径级提交；以重跑命令和当前快照为准 | 全阶段 |
| CI 未执行导致本地绿假象 | 仅本地通过、远端无运行记录或 workflow 被过滤 | 不能满足 R4/R14 的生产准入证据 | QA/Release 负责远端 CI、全量测试、lint 和架构测试记录；无记录不晋级 | 全阶段 |

## 8. Gate 运行规则

1. 每个切片开始前，由 PM 发布切片卡：用户结果、路径、Owner、范围外、依赖、风险、测试包和退出证据。
2. 每次声称完成前，QA 重新运行 `D:\AiFamily\.venv\Scripts\ruff.exe check --no-cache D:\AiFamily`、架构/合规检查和至少一条完整 E2E；不采信缓存、旧报告、权限不可见路径或口头汇报。
3. 任一红线风险、生产等价测试缺失、未解决的跨家庭/Consent/Audit 问题，均保持 `BLOCKED`，不得通过“先合并后补测试”解决。
4. Gate 通过后冻结切片版本、迁移、契约、模型/Prompt/Schema、配置和回滚点；任何逆向变更必须形成 Change Request 并重新验收。
5. 本板只是一份执行草案。要将其中的切片变成正式产品/架构/治理承诺，须分别回写相应的产品、领域、数据、AI、工程文档和 registry，并保留证据链。
