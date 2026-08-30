---
id: DEL-PROGRAM-001
title: 当前 Wave 计划
type: delivery
status: current
version: 1.1
owner: chief-architect
created: 2026-08-29
updated: 2026-08-30
canonical: true
supersedes: null
superseded_by: null
---

# 当前 Wave 计划 (Current Program Plan)

- **状态**: 见上方 front matter `status: current` — 依据 `governance/REPOSITORY_CONSTITUTION.md` R13，本文件是本主题唯一当前真相
- **生效**: 2026-08-29 (AIFAMILY-000)

---

## 警示（优先于以下所有内容阅读）

**下方历史 Wave 默认不自动开始，需人工批准；当前执行计划按 2026-08-30 总控指令推进。**

**且 `docs_current_baseline_CONTRADICTION` 待裁决前不得假设本计划是唯一进行中的迁移工作。**

源仓库 `50_开发_dev` 下同时存在三份互不引用、各自自称"当前基线"的文档（`CURRENT_SPRINT.md`、`governance/PROGRAM_STATUS_PLATFORM_V1.md`、`architecture/FAMILY_PLATFORM_V3_BLUEPRINT.md`），且源仓库自己已有一份 `architecture/FAMILY_AI_PYTHON_ONLY_MIGRATION_PLAN_V1.md`（2026-08-28），`CURRENT_SPRINT.md` 记录了 7 条项目所有者 Override 正按它推进 Batch 1-6。本计划（AiFamily/AIFAMILY-000 起）与该计划是同一决定被重复下达、还是两个并行/冲突的方案，**尚未裁决**。详见 `governance/MIGRATION_MANIFEST.yaml` 的 `docs_current_baseline_CONTRADICTION` 条目（`review_required_index` 首位，最高优先级）。

在此裁决完成前，本文件登记的 Wave 序列是**一份计划**，不是"唯一在推进的迁移工作"的宣称。

---

## 当前执行计划（2026-08-30，总控指令）

本节把家庭成长平台的商业蓝图转换为当前可执行的项目航次。它在交付顺序上优先于下方历史 Wave 描述；下方 Wave 仍保留作为 AIFAMILY-000 的治理与迁移背景，不得被解释为当前代码已经完成。

新蓝图（Family Need OS、B2C/B2B2C/C2C、内容到行动、产品工厂、Principal 和全球 cell）的增量与当前证据，
统一见 [`ARCHITECTURE_ALIGNMENT_CHANGELOG_V2.md`](ARCHITECTURE_ALIGNMENT_CHANGELOG_V2.md)。该文档仍是
`draft/canonical:false` 的变更控制输入；在治理登记、ADR、Registry、owner sign-off 和契约测试完成前，
本计划的当前真相和 NO-GO 发布判定不变。
逐域五层执行矩阵和退出条件见 [`BLUEPRINT_ARCHITECTURE_EXECUTION_PLAN_V2.md`](BLUEPRINT_ARCHITECTURE_EXECUTION_PLAN_V2.md)。

### 总控责任与初心

总设计师、项目经理和总负责人对以下三件事负最终责任：**方向不偏、价值不虚、交付可验收**。

- **方向不偏**：始终以“孩子为价值圆心、家庭为服务和商业单元、AI 连接学校/社会/专业资源、帮助家庭成长和改善关系”为产品判断的第一原则。教育是入口，不把平台收缩成课程商城、广告流量场或单纯内容 App。
- **价值不虚**：每项商业模式都必须证明家庭获得了真实帮助、供给能够真实交付、会员/贡献/结算账目清楚、家庭关系没有被焦虑和排名破坏。没有真实证据，只能标记为假设、目标态或待验证。
- **交付可验收**：每项蓝图都必须转换成有 owner、文件边界、依赖、正向测试、反向挑战、PostgreSQL/HTTP 证据、指标和退出条件的任务。测试环境可以使用模拟数据和外部 sandbox，但业务功能、规则、权限、状态机、审计、回滚和恢复必须与生产等价。

总控每轮评审必须回答五个问题：

1. 这项能力是否让家庭更容易看见需要、采取行动、获得帮助或改善关系？
2. 它服务的是哪个家庭问题，谁授权、谁受益、谁交付、谁承担责任、谁付款？
3. 它是否能通过真实的业务链路、数据账本和 FGCN 履约证据，而不是页面、fixture 或口号证明？
4. 它是否引入了儿童商业化、家庭监控、排名焦虑、数据越权或 AI 越权？
5. 如果今天不能做完，最小可验收切片是什么，阻断它的真实原因是什么，下一步由谁完成？

任何任务若只能回答“能增加流量/收入”，却不能回答上述问题，不进入当前 Sprint；任何安全、隐私、未成年人保护和合规边界，不得被解释为阻碍开发而删除。

总转换链固定为：

```text
商业假设
  → 用户价值与付费理由
  → 业务能力
  → canonical Domain / API
  → 权威数据与分账
  → AI 位置与人工闸门
  → FGCN 交付/验收（适用时）
  → 正向/反向测试
  → 价值/质量/经营/平台健康/合规指标
  → ≤2 周 Sprint 退出证据
```

所有任务卡必须同时写明：目标、用户价值、前置依赖、owner 角色、**明确文件边界**、正向测试、反向测试、数据库/重启/回滚证据、退出条件和已知缺口。没有代码和测试证据的内容只能标为 `PLANNED` 或 `GAP`。

### 航次总览

| 航次 | 目标 | 最小纵向切片 | owner 角色 | 当前门槛 |
|---|---|---|---|---|
| P0 | 家庭需求到首次成长行动的真实闭环 | `GrowthIntent → Onboarding`，随后补 `FamilyNeed → GrowthIntent` | Journey + API/Platform + Data + QA | 先闭合 Consent、tenant 幂等、canonical AuditEvent、真实 PostgreSQL、HTTP wiring |
| P1 | 验证家长是否为真实帮助付费 | 成人授权家庭、一个服务、一个时段、预约、履约、反馈 | Service + Platform + QA | Fake/PostgreSQL/HTTP 同一状态机；未履约不产生贡献/现金 |
| P2 | 建立长期会员与贡献经济 | 会员生命周期、权益消费、成人贡献、积分/权益入账、退款逆转 | Membership + Loyalty + Project Manager | 四本账分离；不新增儿童商业营销；真实 PG 和迁移证据 |
| P3 | 让 AI 提升理解而不越权 | 多模态元数据 → Gateway → Draft/Recommendation → 人工复核 | AI Runtime + Governance | provenance、Human Gate、删除/留存、provider isolation 全有证据 |
| P4 | 建立家庭成长媒体和受控 C2C | 成人内容提交 → 审核 → 家庭可见 → 撤回/删除 | Experience + Content + Compliance | 儿童不计价、不带货、不拉新；媒体三层对象不可混淆 |
| P5 | 验证受控机构供给和 FGCN | 一个合资格 provider、冻结 Blueprint、单责任人任务、交付、人工验收 | FGCN/Service + Operations | 资质/容量/tenant scope；`RESOURCE_GAP`；未验收不贡献/结算 |
| P6 | 从教育扩展到家庭需要商品化 | 一个成人家庭解决方案的 offer → need → delivery → feedback 事件契约 | Business Planning + Finance/Product | 只测量支付意愿、供给成本、退款/返工和贡献毛利，不先扩张商品 API |

### 当前 Sprint 0：真相、ownership 和质量门

**状态：`IN_PROGRESS`。** 这是所有业务切片的共同前置，不是阻止开发的泛化审批层。

- 以当前总控分支、默认分支和各 worktree 的提交 SHA 分层记录证据；不把旧 `CURRENT_SYSTEM_BASELINE` 快照、默认分支测试结果或并发 WIP 汇报混成当前事实。
- `CURRENT_PROGRAM_PLAN.md` 与 `TASK_BACKLOG.md` owner 为 chief-architect；`FAMILY_GROWTH_PLATFORM_EXECUTION_BOARD_V1.md` 是独立 draft WIP，未授权 Agent 不得修改。
- 当前总控分支本轮实测：文档真相专项 `4 passed`；全架构 `109 passed / 1 skipped / 1 failed`，失败为 Ruff debt ratchet（当前 3 errors：1 E501 + 2 I001），不能抬高基线掩盖。
- 任何“完成”必须提交文件清单、实际命令输出、提交 SHA、未解决阻断和 ownership 说明；Fake 只替换外部依赖，不替换业务规则。

退出条件：每个 P0-P6 任务都能找到唯一 owner、非重叠文件范围、依赖关系和反向验收人；共享 WIP、真实 PostgreSQL、远端 CI 或治理登记未完成的部分保持 `OPEN`。

### Sprint 0 修订：六门 P0 阻断 + `VS-GROWTH-01` 业务验收

Sprint 0 不是纯技术准备阶段。六门技术闸门必须共同保护一条最小业务主线：家长进入平台→完成身份与目的化授权→确认一个家庭问题和一个主结果→获得 AI/Principal 的 Perspective/Hypothesis/Draft→家长确认后形成一个 Action→完成一次 Review。固定顺序为：

`问题/授权 → 内容/AI理解/家庭确认 → Action/Review →（必要时）Service/FGCN → 质量/经营门`。

编号治理已纠偏：场景目录中的 canonical S01 保留“内容/直播/活动触达与家庭进入”；`b37b1b6` 的
assessment signal→Perspective/Hypothesis→家庭确认→Action/Review 切片改用独立 ID
`VS-GROWTH-01`，横跨 S01+S04+S05+S07。在 ADR/场景目录登记前，不得把两者合并为 canonical S01，避免 API、数据表和测试追踪分裂。

| P0 门 | owner 角色与文件边界 | 依赖 | 正向/反向测试 | 退出证据 |
|---|---|---|---|---|
| ENV-01 | APLT + 原 `dev_wiring.py` WIP owner；`main.py`/`dev_wiring.py`/production composition/Actor/Session/Consent resolver，不覆盖并发 WIP | ADR-0069、trusted auth port | unset/非法 env fail-closed；无 token 401；跨 tenant 403；撤回 CONSENT_REQUIRED；三环境 route/error parity | TestClient/OpenAPI/启动日志+owner sign-off；当前 unset acceptance 仍 expected-red，BLOCKED |
| DATA-01 | ADOM/ARCH；migration 0011-0029、ORM、Manifest/ADR、对象清单 | DB-01、Fresh PG | up→down→up、重启、并发、unknown head fail；未设 `AIFAMILY_TEST_DATABASE_URL` 的 skip 不算通过 | Docker healthy 真实 PG：`test_full_chain_up_0016_down_and_rebuild` 154s，1 failed；0016→0025 升降通过，0025→0026 写入 40 字符 revision 时触发 `alembic_version VARCHAR(32)` `StringDataRightTruncationError`，0027/0029 同类；FULL_CHAIN 结构测试仍旧于 0024-0029；BLOCKED |
| IDP-01 | Platform/API；trusted ActorContext、ConsentResolver、tenant-scoped IdempotencyStore | ENV-01、DATA-01 | 同 key 跨 tenant 隔离；同输入 replay 同结果；冲突拒绝；撤回/过期/跨主体拒绝 | Fake/PG 同契约、删除后 replay 负向；当前 IdempotencyStore 仍 InMemory/无生产接线，BLOCKED |
| LEDGER-01 | Platform/AAIR；canonical AuditEvent、Outbox、worker/lease/DLQ/restart ports | IDP-01、DATA-01 | 命令与 audit/outbox 同事务；crash/retry 不重复；DLQ/补偿/重启可恢复 | PG 事务和 receipt；目前仅切片局部 evidence，跨域 composition 缺，BLOCKED |
| AI-01 | AAIR/GOV；唯一 `AiReleaseGate`、EvalReport registry、Principal/Context/Memory/Delete，冻结第二 gate | ENV-01、IDP-01、DATA-01 | benchmark unknown/revoked/deleted/mismatch、跨 tenant/locale；AI draft-only，Named Action 才写事实 | 单 gate architecture test、registry/version/provenance；当前双 gate/lookup 缺，BLOCKED |
| CLIENT-01 | AFE/APLT；Web clientFactory、mobile contracts、OpenAPI/error/locale/session；不改后端 WIP | ENV-01、IDP-01 | `DEV:false + fake` fail-closed；token/session/locale/idempotency；四端错误/重放一致 | `766c164` clientFactory 定向验收通过；生产 build 缺 `index.html`，lint 未配置且未进入默认检查，mobile 五失败归零、parity 未闭合，BLOCKED |

真实 PG URL 缺失、`skip`/`create_all`/disposable probe、Web lint 未配置、远端 push 443 失败均须写入证据表并保持阻断；不能以“本地测试绿”代替 Fresh PG/HTTP/remote 证据。

### Sprint 1-3 计划卡（每卡必须四区记录）

每张计划卡都要以 `Current Truth / Target / Planned / Evidence` 四区记录；Evidence 必须含 commit SHA、
remote ref、命令、原始摘要、数据集/`AIFAMILY_TEST_DATABASE_URL`、跳过项、失败项和反向测试，不接受“应该可以”。

| Sprint | owner 角色 | 文件边界 | 依赖与输入→活动→输出 | 正向/反向测试 | 退出门 |
|---|---|---|---|---|---|
| S0（当前，P0 阻断） | PMA 协调；APLT/Platform/ADOM/AAIR/AFE 各 gate owner | 仅各 owner 已声明文件；不覆盖 `dev_wiring.py` 等共享 WIP | 身份/授权问题→六门技术闸门→家长确认一个问题/主结果→`VS-GROWTH-01` contract | TestClient 三环境、Fresh PG up/down/up、tenant/consent/idempotency、audit/outbox crash/retry、AI gate、Web/mobile parity | 六门全绿且 `VS-GROWTH-01` 业务链可回读；任一缺失 `BLOCKED/NOT_DONE` |
| S1（`VS-GROWTH-01` 真实闭环） | Growth + AFE/API + AAIR | 独立 `s01_vertical_slice.py`、`api/s01_routes.py`、`infrastructure/s01_postgres.py` 与专测；不改 FGCN/Commerce writer | `b37b1b6`（基础契约）→`78fff77`（HTTP/PG seam）→`520e2ed`（replay hash）→`e5f7c41`（rollback test）→`c60729b`（consent subject-family binding）→`090976e`（canonical event name）；signal→Perspective/Hypothesis/Draft→家庭确认→GrowthIntent/ActionTask→Review，横跨 canonical S01+S04+S05+S07 | 独占 11 tests passed/1 warning；本轮全 journey 75 passed/15 skipped（PG URL 未设）；反向覆盖 AI actor/跨 tenant/撤回 consent/新 key replay/conflict/删除/回滚；仍需真实 Fresh PG/HTTP/并发/重启、多 locale | 当前路由未挂 `family_api`，`production_ready=False`；Hypothesis/Intent/Action/Review 未 durable，无 canonical Audit/Outbox/worker；下一阶段必须完成真实 FastAPI+Postgres+outbox+audit+deletion/replay，保持 `PARTIAL/NO-GO` |
| S2（`VS-GROWTH-01` 后续 FGCN） | FGCN/Service + Operations | FGCN admission/assignment/delivery/quality ports、worker；不新增第二 writer | `VS-GROWTH-01` 已确认 need→provider admission→case/task→delivery→quality/`RESOURCE_GAP` | capacity 并发、assignment 完成/撤回 replay、locale、reviewer/tenant/consent、worker restart/DLQ/争议 | Fresh PG/HTTP 常驻 worker、唯一 writer、quality/audit/outbox；否则 `PARTIAL` |
| S3（平台账与体验扩展，条件解冻） | Commerce/Community/B5/AFE | 保留生产形状契约；暂不开放真实流量/实验 | `VS-GROWTH-01`/FGCN 质量门→四本账、Content/Live、C2C/B2B2C、Product Factory | 订单/支付/退款/权益/结算/社区撤回/机构授权/多 Agent fail-closed；无家庭总分/排名/儿童营销 | 仅在 P0+S1+S2 全绿后；PG/HTTP/审计/回滚/重启/人工 gate/四端 parity 全绿 |
| S4（生产候选与全球 cell） | Chief Architect + PLT/GOV/AAIR | region/cell、容量、灾备、真实 adapters、PLM | S1-S3 稳定事实→生产身份/支付/模型/媒体/vector/运营事故→candidate release | failover、备份恢复、DPIA/删除、成本/配额、多语言四维、license/CI/事故演练 | 所有 P0/P1 关闭、unknown head 清零、architecture/Ruff/PG/HTTP/删除/审计全绿；才可 `PRODUCTION_CANDIDATE` |

冻结规则：S3 之前 Commerce/C2C/B2B2C/多 Agent 只允许维护未来生产形状的状态机、权限、Consent、tenant、幂等、
Audit/Outbox、回滚、重启、人工审核和支付/退款/结算契约；不允许真实运营、开放流量、商业实验或范围扩张。

每个 Sprint 还必须通过 **D10 质量/商业门**：家庭是否得到真实帮助，服务质量/安全/退款/返工/供给成本
是否可追踪和对账，商业动作是否发生在 E3 明确需要且经家长确认之后。点击、停留、家庭总分、排名、虚假
社会证明或合成收入都不能作为 D10 结果；D10 未通过，技术绿灯也只能标 `PARTIAL`。

### P0 任务队列：先让家庭需求链真实可调用

| 任务 | 内容 | 文件边界 | 反向验收 |
|---|---|---|---|
| P0.1 | `GrowthIntent → Onboarding` Domain/Application/Fake/Postgres | 仅当前 Journey owner 已确认的新 onboarding 文件及对应专项测试 | 未确认 intent、AI actor、跨 tenant/family、无/撤回/过期 Consent、重复请求、审计/outbox 失败回滚 |
| P0.2 | Consent 与 tenant-family binding 语义等价 | Platform/Data owner 明确的 Consent adapter、测试和必要 migration；不擅改 baseline schema | Fake 与 Postgres 都拒绝无效窗口、撤回、跨租户和失效 binding；禁止只按 family/subject 查询 |
| P0.3 | tenant-scoped idempotency 与 canonical AuditEvent | Platform/Data owner 明确的 persistence/audit 接线和专项测试 | 同 key 跨 tenant 不相互污染；Audit 必含 actor/tenant/action/resource/reason/correlation/before/after；失败整体回滚 |
| P0.4 | family_api 正式挂载与 PostgreSQL E2E | API owner 的 `main.py`/wiring/HTTP 测试范围；Journey owner 不越界修改 | 从实际 composition root 走成功、503/拒绝、幂等、回读和重启；不能用孤立 route 或 dev 后门代替 |
| P0.5 | `0016` migration 生产形状审查 | migration owner 的 revision、升级/降级/含数据冲突测试与登记请求 | 空库升级、含数据升级、回滚、重启、重复约束和真实 PG 证据；未登记不晋升 |

P0 任一任务没有真实 PostgreSQL 或 HTTP 证据，Sprint 保持 `NOT_DONE`；FamilyNeed 与 Assessment 各自测试通过不能替代 GrowthIntent→Onboarding 的端到端证据。

### 当前跨 Chat 交付矩阵（PMA-1 复核快照，2026-08-30）

以下矩阵把各 Agent 回传转换为可验收状态。`PASS` 仅表示该层测试证据通过，不能越级为
生产能力；`PARTIAL` 表示仍缺闭环；`BLOCKED` 表示发布闸门不可绕过。Fake、skip、设计稿
和单独的 fixture 不作为生产完成证据。

| Thread/标题 | Scope | Owner / commit | PASS 证据 | 当前状态 | 未闭合阻断与下一动作 |
|---|---|---|---|---|---|
| APLT-2 / security gate | 环境 fail-closed、Experience 401/403/Consent 错误码 | APLT / `cbc055e`、`736ae19`、`d2196bc` | 定向 7 passed/1 expected-red；非法环境与错误映射通过 | `PARTIAL/BLOCKED (P0)` | unset `AIFAMILY_ENV` 仍默认为 development；真实 auth/session/tenant/consent 未接线。原 WIP owner 收口后补三环境 TestClient 和 OpenAPI/404/401/403 |
| ADOM-5 / DB-01 migration | Alembic baseline/head、ORM/Manifest/ADR | ADOM/ARCH / `5a67a1b`；0011–0029 WIP | Docker healthy Fresh PG `test_full_chain_up_0016_down_and_rebuild` 154s：1 failed；0016→0025 升降通过，0025→0026 因 revision 40 字符超过 `alembic_version VARCHAR(32)` 失败；结构 FULL_CHAIN 仍旧于 0024–0029 | `PARTIAL/BLOCKED (P1)` | HEAD 仅追踪 0001–0010，0011–0029 未形成 tracked/审批链；0027/0029 同类长度风险。补 ADR/Manifest/ORM/对象清单、修复 revision 存储与可逆 Fresh PG，单 head 后才 allow-list |
| AAIR-6 / durable deletion | deletion queue、lease/retry/DLQ、五类回执 | AAIR / durable deletion slice | durable 子集 6 项；context-engine 25 passed | `CONTRACTED/adapter-only` | InMemory store、无 PG/outbox/跨进程 lease/真实 receipts；补 durable worker 与审计删除证明 |
| AFE-4 / UI experience | 34 UI 语义图标、成就、多模态、跨端 | AFE / UI slice、Web `4b9a4b4` | 专项 5 passed、mobile `pnpm check` passed；Web clientFactory 26 passed/typecheck 0 | `PARTIAL` | mobile 全量 249 passed/1 skipped/5 failed；修 UI-02、registry/service contract 与四端视觉/无障碍/locale parity；生产 `DEV:false + VITE_EXPERIENCE_CLIENT=fake` 必须 fail-closed/强制 HTTP |
| GROWTH / `VS-GROWTH-01` 主线 | `UI-03→UI-05→UI-09`：assessment signal→Perspective/Hypothesis draft→家庭确认→GrowthIntent/ActionTask→回读/ChallengeReview，横跨 canonical S01+S04+S05+S07 | growth owner / `b37b1b6`→`78fff77`→`520e2ed`→`e5f7c41`→`c60729b`→`090976e`（已在远端历史）→`089659a`（本地待同步；仍非生产完成） | VS seam 11 passed/1 warning（含 canonical event name 断言）；本轮全 journey 75 passed/15 skipped（PG URL 未设）；`089659a` 共享 errors.py 已可导入 | `CONTRACTED/PARTIAL (P0 业务主线)` | clean snapshot/远端同步与跨模块 composition 验收仍待完成；路由未挂 `family_api`、`production_ready=False`；Hypothesis/Intent/Action/Review 未 durable；legacy audit/outbox 非 canonical、无 worker/restart/deletion/replay 真实证据；下一阶段必须接真实 FastAPI+Postgres+outbox+deletion/replay，且绑定家长确认一个问题/主结果 |
| GROWTH / S05→S08 | Action→Outcome→Story→Recommendation→Annual/Renewal | growth_action_loop / `b431eda`、`78cb9c1`、`dcc0802` | journey 40/4；Fresh PG 44 | `CONTRACTED-PARTIAL` | 仅作为 `VS-GROWTH-01` 后续；无 Journey HTTP/ORM/常驻 worker/真实 sink；补 Audit/Outbox、consent/replay/deletion 与 UI e2e |
| GROWTH-ONBOARDING | Confirmed Intent→Onboarding HTTP/PG | growth owner / `0cd53fb`、`6b4a8e9` | route/domain 29 passed；PG 单跑 13 passed，但重复一轮 12 passed/1 failed | `CONTRACTED-PARTIAL` | `actor_family_scope_denied` 时序/时钟 flake；0016/0017 migration 未登记。修 fixture 时钟/隔离、非法 UUID=400、跨租户/撤回同意 |
| AAIR/PLT / Context | Async/SQL Context、scope/replay/delete | AAIR / `02a80c4`、`6a88625`、`6150169`、`9b10d2d` | context 25 passed；disposable PG probe 1 passed | `CONTRACTED-PARTIAL` | PG probe 仍 create_all/同 engine，无 Alembic/restart/production resolver；补 durable Consent、migration、Audit/Outbox、删除 receipts |
| AAIR/EVAL / Experience | SQL ledger/session、benchmark、唯一 AI gate | AAIR/API / `941feae`、`a11f643`、`96905db`、`69f6508`、`674b764`、`050361f`、`b3fffbb`、`5df865e`、`eb33c06` | evaluation+experience 220 passed/1 warning | `CONTRACTED-PARTIAL` | 双 gate、EvalReport registry、trusted ActorContext/Consent、PG transaction/Audit/Outbox 缺；冻结扩张并合并 canonical gate |
| MEMBERSHIP-01 / 三账 | entitlement、contribution、settlement | DOM / `0ca62d2` | Fresh PG membership 50 passed/1 warning | `CONTRACTED-PARTIAL` | 生产 API/身份/consent/退款争议/删除审计缺；保持贡献/权益/现金分账、无总分排名 |
| P1 服务垂直切片 / B2C service | ServiceOffering→Slot→预约→履约→反馈与 provenance | P1 service owner / `e99d499`→`d9a130b`（已推送） | 隔离 PostgreSQL 95 passed；共享库迁移仍漂移 | `PARTIAL/候选测试切片` | family_api provenance、Audit flush、worker/DLQ、FGCN bridge、共享库迁移一致性、Commerce 冻结边界未闭；补真实 auth/tenant/consent/deletion/audit 与 canonical migration 后再评估生产 |
| FGCN / service collaboration | admission→Human Gate→Named Action→TaskAssignment→delivery/quality/contribution | FGCN / `41ad120`→`e7cbb0b`→`31c95cb` | 本轮无 PG `uv run pytest tests/domains/service/fgcn -q` = 133 passed/3 skipped（真实 PG 用例跳过）；历史 Fresh PG 113 passed；`31c95cb` 补 quality rework replay；FGCN admission evidence/provenance 已绑定（仅在 `VS-GROWTH-01` 确认 need 后接入） | `GO (测试契约)/NO-GO (生产)` | reviewer/worker/action context 默认 RuntimeError；one-shot worker 无 queue/通知/DLQ；capacity reservation 非原子；gate/assignment 双事务 crash/retry；assignment 后续 COMPLETED/REVOKED 时同 request replay 可能误判 mismatch；场景校验硬编码英文、未接 locale registry；`family_request_ref`/失败次数缺 canonical 数据血缘与作用域验证；生产 identity/consent/duplicate operationId 待补 |
| 运营 Chat / 运营可观测性（只读回传） | S21/S24/O13 运营触达、S22/S23/O12/O14 运营服务与事故闭环 | 运营 Chat（未提供 commit/owner） | 79 passed/1 skipped/1 warning；唯一 skip 为真实 PG WORM；Onboarding 35/11 skipped | `PARTIAL/DESIGN_ONLY` | 主动欢迎/SLA/补救/回访、可信分享/组队、机构运营、发布/事故闭环均未实现；指派 owner，补真实 PG WORM、HTTP/租户/审计/删除/通知 worker 后再评估 |

**总闸门（快照）**：architecture `109 passed/1 skipped/1 failed`（Ruff ratchet）、全量 Ruff
`3 errors (1 E501 + 2 I001)`、Alembic Docker 真实 PG `test_full_chain_up_0016_down_and_rebuild` 1 failed/154s（0025→0026 revision 截断，0027/0029 同类；FULL_CHAIN 旧于 0024-0029）、mobile `249/1/5`，因此当前测试候选只能在受控环境继续；
生产发布明确 `NO-GO`。旧远端快照 `bd59c91` 已过时；本计划证据快照基线为 `82f038c`，其后
`7355ca5` 更新了本计划。`9eeb19a`（文档原子场景清单）、`b37b1b6`（`VS-GROWTH-01` slice）和 `e0c16d0`（场景计划）
均在分支历史，但仍缺真实 PG/HTTP/构建/主线合入证据，不能写成生产完成；工作树仍有其它 Agent WIP，禁止将其一并推送。

### P1-P6 的首个可实现任务

1. **P1.1 Service value slice**：一个成人授权家庭、一个合资格 `ServiceOffering`、一个 `Slot`、预约确认、履约记录和家庭反馈；支付可用 sandbox，但不能删除退款、取消、幂等、审计和错误路径。
2. **P2.1 Adult contribution ledger**：在既有 `loyalty_points` canonical domain 内完成成人贡献记录与不可变入账边界；贡献须经过 `SUBMITTED → REVIEWED → VERIFIED → HELD → RELEASED`，支持 `REJECTED/APPEAL/REVERSED`，不得把积分、FGCN 单位和现金合账。
3. **P2.2 Membership entitlement**：在现有 Membership WIP owner 完成生命周期、权益 reserve/consume、过期/退款/撤回反向处理；不修改其他 Agent 的 Membership 文件。
4. **P3.1 Multimodal runtime seam**：在既有 Experience 合同之上实现 `MediaAsset/MediaTranscript/MediaEvidence` 的最小 provider-neutral runtime 和 provenance；AI 只能产 Draft/Recommendation，敏感动作进入 Human Gate。
5. **P4.1 Controlled family media**：成人作者审核后家庭可见，支持撤回、删除、投诉和可见性；儿童表达默认非商业化，不建设儿童端带货或返佣。
6. **P5.1 FGCN delivery**：沿现有 FGCN owner 的 admission/contracts/engine/application 文件继续，冻结 Blueprint、建立 Case/Task/Delivery/Quality；资源不足返回 `RESOURCE_GAP`，不能另造开放专家市场。
7. **P6.1 Unit-economics instrumentation**：只建立事件和测量字段（支付意愿、供给工时、履约成本、退款/返工、贡献毛利、留存），不凭合成数据宣称真实商业有效性。

### 每轮强制反向挑战

- 商业：客户是在为真实帮助付费，还是被测评、焦虑、停留时长诱导？供给成本、退款和质量修复后是否仍成立？
- 关系：功能是否让家庭更容易沟通和协作，是否制造家庭内部监控、公开比较或对孩子的表演压力？
- 安全：跨租户/家庭/主体能否读取或写入？Consent 撤回、数据删除、过期、退款和争议后是否仍有效？
- AI：是否直写 Fact、自动派单、自动验收、自动结算、向儿童营销，或绕过 Named Action/Human Gate？
- 工程：Fake 是否仅替换外部依赖？PostgreSQL、HTTP、重启、回滚、并发、重复回调和 Outbox 是否与生产同形？

任何一项没有证据，就保留为 `OPEN`，不得通过文案、截图、fixture、skip 或“应该可以”关闭。

## Wave 序列

### Wave 0 — AIFAMILY-000（当前，已完成大部分）

**内容**：治理 + 审计。对源仓库 `family-ai`（baseline commit `1ff168123d147f4d6a6eaaa677bc2f80986233d9`）做七维资产审计，产出：

- `governance/REPOSITORY_CONSTITUTION.md`（十四条规则）
- `governance/MIGRATION_MANIFEST.yaml`（逐能力 disposition 判定）
- `governance/DOMAIN_REGISTRY.yaml`（唯一实现位置登记表）
- `docs/00_system/CURRENT_*.md`（系统真相层文档）
- `reports/migration/`（详细审计报告）
- `tests/architecture/`（架构测试骨架）

**不含**：任何业务代码。这是本仓库当前唯一真实状态。

**DoD（Definition of Done）**：
1. 十四条宪章规则全部写明，每条附伤疤证据（源文件路径 + 行号）；
2. MIGRATION_MANIFEST.yaml 覆盖审计中识别出的全部能力，每条有明确 disposition；
3. DOMAIN_REGISTRY.yaml 与 MIGRATION_MANIFEST.yaml 的 MIGRATE/REIMPLEMENT 条目一一对应，无遗漏无重复；
4. CURRENT_*.md 六份文档全部落地，且每条断言可追溯到 MIGRATION_MANIFEST.yaml 或 REPOSITORY_CONSTITUTION.md 的具体条目；
5. `docs_current_baseline_CONTRADICTION` 与其余 `review_required_index` 条目已登记为待裁决，未被误判为已解决。

---

### Wave 1 — AIFAMILY-001：Python 平台内核

**内容**：FastAPI 运行时入口 + Actor/Tenant Context + Authorization + Consent + Audit + Idempotency + UnitOfWork。

对应 `governance/MIGRATION_MANIFEST.yaml` 中全部标注"Wave 1 平台内核"的条目（`platform_actor_tenant_context`、`platform_authorization_policy`、`platform_consent`、`platform_audit`、`platform_idempotency`、`platform_persistence_uow`、`model_gateway`、`fastapi_runtime_entrypoint`），全部 disposition = REIMPLEMENT，因为源仓库 Python 侧对这些平台原语**零对应实现**。

**DoD**：
1. `backend/apps/family_api` 存在真实 `FastAPI()` 应用入口并可被 uvicorn 启动；
2. Actor/Tenant Context、Authorization、Consent、Audit、Idempotency、UnitOfWork 各自有独立模块，且每个模块有 Python 验收测试（R4）；
3. R7（禁止领域直连供应商）与 R12（无隐式路径耦合）对应的架构测试在本 Wave 落地并接入 CI；
4. `governance/DOMAIN_REGISTRY.yaml` 中对应条目 status 由 NOT_STARTED 更新为 ACTIVE，且更新的同一 PR 必须补齐测试路径。

---

### Wave 2 — AIFAMILY-002 治理内核落地 + AIFAMILY-003 product_intelligence 准入

**内容**：
- **AIFAMILY-002**：R2/R3/R7/R11/R12/R13 对应的架构测试从骨架变为在 CI 中真实运行且通过；`docs_governance_enforced_subset`（`MERGE_AUTHORIZATIONS.yaml`、`AUTHORIZATION_REGISTRY.yaml`、`FPAI_PROVIDER_REGISTRY.yaml`）迁移落地。
- **AIFAMILY-003**：`product_intelligence` 域准入——补齐 Postgres 集成测试、挂载 `api/routes.py` 到 Wave 1 建立的 FastAPI 入口、解决其 V0.1 状态遗留问题。

**DoD**：
1. `tests/architecture/` 下 R2/R3/R7/R11/R12/R13 对应测试全部绿，且在 `.github/workflows/` 中被真实触发（不是存在即可，必须在 CI 跑）；
2. `product_intelligence` 有 Postgres 集成测试（不再只有 SQLite），`api/routes.py` 被真实挂载，`MIGRATION_MANIFEST.yaml` 中 status 由 `APPROVED_PENDING_REVIEW` 更新为可验证的下一状态；
3. `membership` 域的裁决前置条件（`FORBIDDEN_TIER_FIELD_TOKENS` 的 guardrail test）如在本 Wave 处理，必须先完成该测试才能改变其 disposition。

---

### Wave 3 — AIFAMILY-010：Family Core 重实现

**内容**：`family_core` 域按 REIMPLEMENT 判定重建，行为规格来自 `family-core-integration.e2e-spec.ts`（M1-E2E-01 全链路）与 `family.e2e-spec.ts`（E2E-M2-101~105）。

**DoD**：
1. Family → Parent → Child → Relationship → Lifestage → Consent 全链路的 Python 验收测试通过，测试断言与源仓库 e2e 规格中的否定推断守卫一致（不得从 relationship 推断 consent、不得从 birthdate 推断 lifestage）；
2. "确认 profile 产生零 AI/Model 事件"的否定断言在 Python 侧同样有测试覆盖；
3. `family_dev_surface_services`（合成数据服务）的替代方案已明确决定并记录，移动端消费的 9+ 屏幕不因后端切换而白屏；
4. R6（无审计不得改状态）与 R9（AI 输出不得自动成为事实）对应的运行时检查已接入本域。

---

### 后续 Wave

按 `governance/MIGRATION_MANIFEST.yaml` 剩余条目展开，包括但不限于：`auth_identity`（MIGRATE）、`orchestration_core`（MIGRATE）、`principal_core`（MIGRATE）、`database_schema`（MIGRATE，需先解决 4 组文件名重号）、`packages_contracts_ts`（REIMPLEMENT，含真实投影函数需当逻辑重译）、`design_copilot`（CONTRACT_ONLY）。具体排期在对应 Wave 启动时另行制定，本文件不预先排定后续 Wave 的编号与内容，避免在裁决前锁定一份可能与源仓库既有计划冲突的路线图。

---

## 待裁决索引（影响本计划排期的开放项）

以下条目摘自 `governance/MIGRATION_MANIFEST.yaml` 的 `review_required_index`，裁决结果可能改变本文件的 Wave 划分：

- `docs_current_baseline_CONTRADICTION`（最高优先级，见本文件顶部警示）
- `membership`（最大零测试 Python 域，影响 Wave 2/3 排期）
- `model_provider_assessment`
- `orchestration_llm_gateway_violation`
- `frontend_web`
- `50_开发_dev/packages/program-runtime`（未找到消费者，可能是孤儿）
- `50_开发_dev/packages/harness`（同上）
- `50_开发_dev/products/famili-principal`（纯文档树，无代码）
- `50_开发_dev/factory/`（内部脚本引用已损坏）

在这些条目裁决前，任何 Wave 2 及以后的启动都需要重新核对本计划是否仍然成立。
