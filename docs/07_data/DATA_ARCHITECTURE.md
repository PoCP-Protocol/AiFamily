---
id: DATA-ARCH-001
title: 数据架构
type: data
status: current
version: 1.0
owner: chief-architect
created: 2026-08-29
updated: 2026-08-29
canonical: true
supersedes: null
superseded_by: null
---

# 数据架构 (Data Architecture)

- **状态**: 见上方 front matter `status: current` — 依据 `governance/REPOSITORY_CONSTITUTION.md` R13，本文件是本主题唯一当前真相
- **生效**: 2026-08-29
- **上游依据**: `governance/MIGRATION_MANIFEST.yaml` 条目 `database_schema`、`governance/REPOSITORY_CONSTITUTION.md` R9、`docs/01_strategy/COMMERCIAL_VALUE_STRATEGY.md` §8.2、`docs/14_reference/legacy_audits/FAMILY_UI_BACKEND_SCENARIO_CONSISTENCY_AUDIT_V1.md`

## 1. 数据库现状：真实技术债，不回避

> **2026-08-29 T-03 实测更新（本节三处口径已被证据修正）**
>
> 1.1–1.3 的阻塞项**已完成**，`database_schema` 能力已从 `PLANNED` 转 `IN_PROGRESS`。完成物：
> `database/migrations/LINEARISATION_MAP.md`（62 行映射 + 逐组排序理由与实测证伪）、
> `database/baseline/*.sql`（62 个线性化文件，sha256 与源文件一致）、
> `database/migrations/versions/0001_legacy_schema_baseline.py`（Alembic baseline）。
> `alembic upgrade head` 在空 Postgres 16 上成功产出 151 表 / 7 视图 / 60 枚举，
> up→down→up 循环可重复。
>
> 三处需要读者注意的口径修正（详细证据见 LINEARISATION_MAP.md §0、§3、§4）：
>
> | 本节原断言 | T-03 实测 |
> |---|---|
> | 源目录 "58个文件（0001-0058）" | 实为 **62 个 `.sql` 文件**。"58" 是最大编号不是文件数；4 组重号各多出 1 个，58+4=62 |
> | 1.1：4 组重号的顺序信息丢失，须靠考古重建，"顺序错了会叠加错误变更" | 4 组重号**组内全部无依赖**：逐组交换后 62 个文件仍全部应用成功且 schema 等价。唯一硬依赖是**跨组**的 `test_experience_workflows` → `family_growth_page_objects`，而文件名字典序（即 `migrate.mjs` 的真实应用顺序）恰好已满足它。风险边界比本节预想小得多 |
> | 1.2：`subject_type`/`subject_ref_id` 是"死列"，"新代码大概率只读写新列" | **不是死列**。旧列 `NOT NULL` 且无 DEFAULT；源仓库 `apps/api/src/modules/family/family.service.ts:1427` 的 `insert` 同时写两代列；`0045` 迁移以 `profile.subject_type='CHILD'` 为读取谓词。已按"忠实快照"原样带入 baseline。真正的债不是"有死列"，是"同一语义双写、无单一真相"，退役路径待 T-05 随 ADR 给出 |

源仓库唯一权威 schema 来源是 `50_开发_dev/database/migrations/*.sql`，**实测62个文件（编号 0001-0058），手写SQL，非TypeORM/Prisma**，经 `tools/migrate.mjs` 顺序应用（`readdirSync().sort()`，即纯文件名字典序），配合 `schema_migrations` 追踪表记录已应用版本。`governance/MIGRATION_MANIFEST.yaml` 条目 `database_schema` 判定为 **MIGRATE**，原列出的阻塞项如下（均已由 T-03 解除，保留原文以便追溯当时的判断）：

### 1.1 四组文件名重号（必须先线性化才能生成 Alembic baseline）

`0022`、`0023`、`0024`、`0053` 四个编号**各有两个不同内容的文件**同名共存于源仓库迁移目录。这不是同一份文件的两个版本，是**两份内容不同但编号相同的SQL**——这意味着"哪个先应用、哪个后应用"这一顺序信息在文件系统层面已经丢失，只能通过以下方式重建：

- 检查 `schema_migrations` 追踪表里记录的实际应用顺序（如果该表在某个可访问的数据库实例上还保留着历史记录）；
- 检查两份文件内容之间的依赖关系（如果文件B引用了文件A建的表，A必然先于B）；
- 检查 git 历史（如果两份文件是不同 commit 提交的，提交时间顺序是强证据，但不是唯一证据，因为手写SQL不保证提交顺序等于应用顺序）。

**Alembic 首个 revision 生成前必须先解决这4组重号并决定死列去留**（见1.2节），这是一次纯粹的历史考古工作，没有捷径，不能靠"随便选一个顺序"糊弄过去——顺序错了会导致 Alembic baseline 里的表结构和真实生产/DEV数据库实际经历过的DDL顺序不一致，未来任何依赖 `ALTER TABLE ... ADD COLUMN` 类迁移都可能在错误的基线上叠加错误的变更。

### 1.2 死列去留：`growth_profiles` 表的两代列共存

`growth_profiles` 表存在**两代列同时存在于表结构里**：`0003` 迁移建的 `subject_type`/`subject_ref_id`，被 `0007` 迁移追加的 `profile_scope`/`subject_person_id` **实质性替代但未删除旧列**。这是典型的"迁移历史遗留死列"——新代码大概率只读写 `profile_scope`/`subject_person_id`，但旧列仍占用存储空间、仍可能被遗留查询意外引用、仍在任何"select *"式的代码里造成困惑。

**Alembic baseline 生成时必须显式决定**：是把这两代列都原样带入 baseline（保留历史真实性但延续技术债），还是在生成 baseline 的同一个 PR 里加一个显式的"删除死列"迁移（把技术债还清但改变了"baseline=对源仓库schema的忠实快照"这一假设）。这个决定不该被本文档代为拍板——它影响的是"baseline 的定义是什么"这个更根本的问题，建议随 `database_schema` 能力从 `PLANNED` 转 `IN_PROGRESS` 时一并提交 ADR。

### 1.3 阻塞顺序（明确写出，不留歧义）

```text
1. 线性化 0022/0023/0024/0053 四组重号 → 确定58个文件的唯一应用顺序
2. 决定 growth_profiles 两代列的 baseline 处理方式（保留 or 清理）
3. 生成 Alembic 首个 revision（`alembic revision --autogenerate` 对齐到决定后的schema状态）
4. 之后的所有schema变更走正常 Alembic revision 流程，不再手写SQL
```

在完成上述 1-3 之前，任何"按域分schema"的目标设计（第2节）都只是**目标态**，不是可以立即执行 `CREATE SCHEMA` 的现状。

**1-3 已于 2026-08-29 由 T-03 完成，第 4 条起生效**：此后所有 schema 变更走 Alembic revision 流程，不再手写 SQL；`database/baseline/*.sql` 是只读历史制品，任何改动都必须是 baseline 之后的新 revision。第 2 节的按域分 schema 仍是**目标态**——baseline 刻意只做忠实快照（见第 5 节），151 张表目前全在 `public`，`CREATE SCHEMA identity/family/...` 与每域独立 DB role 都还没做，是后续独立 PR。

**T-03 发现的一处需裁决 schema 矛盾**：`backend/domains/product_intelligence/migrations/0058_product_intelligence_domain.sql` 与 baseline 里的同源文件**不等价**——它给 `product_intelligence_growth_hypotheses` 多加了 `validated_by`/`validated_at`/`validation_reason` 三列，而源仓库权威 SQL 里 grep 这三个名字为 0 命中。AiFamily 的 ORM 模型（`infrastructure/sqlalchemy_models.py:186-188`）要求这三列，所以在**只跑过 `alembic upgrade head` 的库上，该域会失败**；两个真实 Postgres 集成测试没有暴露它，因为它们自己读那份本地 SQL 建库、绕开了 baseline。处置建议见 `backend/domains/product_intelligence/migrations/README.md`（新增 baseline 之后的 revision，而**不是**改 `database/baseline/`）。

## 2. 按域分schema的目标设计

目标是每个业务域一个 PostgreSQL schema，每个schema配一个独立DB role，**跨schema只读投影允许，跨schema直写不允许**——这是 R2（唯一领域真相）在数据库层的具体化：如果两个域都能直写同一张表，"一个能力只有一个正式实现位置"这条规则在运行时层面就形同虚设。

| schema | 归属域 | 权限模型 |
|---|---|---|
| `identity.*` | 平台身份（Account/Session/OTP，对应源仓库 `identity_sessions`/`otp_challenges`/`accounts`） | 仅 `identity` role 可写；其它域通过 Query Port 读取 `ActorContext` 而非直查表 |
| `tenancy.*` | 租户/绑定链（对应源仓库6层绑定：Account→Person→FamilyMembership→TenantFamilyBinding→TenantAccountMembership→Session） | 仅 `tenancy` role 可写；这是 `test_oracle_tenant_isolation` 契约测试保护的核心表群 |
| `family.*` | Family/Person/Relationship/Consent核心聚合 | 仅 `family` role 可写；对应 `family_core`（disposition=REIMPLEMENT） |
| `consent.*` | ConsentGrant/ConsentPurpose（同意授权，独立于family聚合，因为撤回同意必须"立即生效"，见 `backend/platform/consent/gate.py` 设计） | 仅 `consent` role 可写；`family.*` 域通过Query读取当前生效的grants，绝不缓存 |
| `assessment.*` | 测评Tool/Session/Response/Evidence（UI-02对应对象） | 仅 `assessment` role 可写；已是唯一端到端验证过的域（矩阵001 `COMMERCIAL_SLICE_IMPLEMENTED_TESTED_DEV`），第一个落地Alembic revision的候选schema |
| `growth.*` | GrowthHypothesis/GrowthIntent/GrowthNeed/GrowthAction（UI-03/UI-09对应对象） | 仅 `growth` role 可写；**明确排除**家庭总分/排名字段（见第5节） |
| `journey.*` | JourneyPlan/JourneyPhase（21/90天计划节奏，UI-04/05对应） | 仅 `journey` role 可写；当前源仓库 `journey-plan.service.ts` 的 `pausePlan()`/`reviewCurrentPhase()` 是行为参照 |
| `program.*` | ServiceBlueprintVersion（发布后冻结的谋略/课程版本对象） | 仅 `program` role 可写；写操作极少（DRAFT→REVIEWED→PUBLISHED→RETIRED状态机），大量读 |
| `service.*` | ServiceCase/ServiceTask/TaskAssignment/BookingRequest/ServiceRecord/ServiceContribution/AllocationStatement（FGCN核心运行链） | 仅 `service` role 可写；对应 Batch 2（预约子链）+ Batch 7（完整FGCN） |
| `content.*` | ContentVersion/课程内容库 | 仅 `content` role 可写 |
| `ai_runtime.*` | Model Gateway调用记录、Provenance、Prompt Registry、Trace/Cost（AI侧的**自己的**审计与追溯数据，不是业务权威状态） | 仅 `ai_runtime` role 可写；这个schema存的是"AI做了什么"，不是"家庭发生了什么"——两者物理隔离，防止AI侧的写入路径意外获得对业务schema的写权限 |

**跨schema投影的实现方式**：不使用数据库层的跨schema视图（会隐藏权限边界），使用应用层的Query Port——一个域的 `application/queries` 显式调用另一个域暴露的只读查询接口，返回DTO，不返回ORM实体。这与第2节"通信方式"的Port定义一致（见 `TECH_ARCHITECTURE.md` §2.2）。

## 3. 表清单摘要（代表性表名，按域分组，非全量）

| 域 | 代表性表（源仓库证据） |
|---|---|
| identity/tenancy | `identity_sessions`、`otp_challenges`、`accounts`、`tenants` |
| family | `families`、`persons`、`consents`（源仓库 `family.service.ts` 60+路由背后的Postgres持久化对象） |
| assessment | `growth_profiles`（含1.2节提到的两代列技术债）、测评Tool/Session/Response/Evidence相关表 |
| service（服务预约子链，已在源仓库以 `0032_family_service_booking_objects.sql` 落地） | `ProviderProfile`/`ServiceOffering`/`AvailabilitySlot`/`BookingRequest`/`BookingServiceRecord`/`ProductEvent`（矩阵001"服务预约对象链实现记录"一节列出的实体） |
| 页面对象投影（`0023_family_growth_page_objects.sql`） | `family_profile_snapshots`、`family_support_report_snapshots`、`family_page_task_items`、`family_service_records` |
| commerce（层3，大部分GATE_BOUNDARY/GAP） | `family_product_offerings`、`family_order_intents`、`family_entitlements`（矩阵001确认这套DTO和后端服务"比预想成熟"，但被 `requireDevSyntheticTestLoop()`/`fixture_only=true` 限定在DEV/TEST合成环境，不接真实支付） |
| principal（AI Runtime侧） | `principal_*` 表群（源仓库 `principal_core`，2337行，disposition=MIGRATE） |

**排除声明**：本节列出的是"代表性表名"，不是全量清单。全量清单应在 `database_schema` 能力从 `PLANNED` 转 `IN_PROGRESS` 时，随 Alembic baseline 生成过程一并产出为附件，本文档不预先枚举58个SQL文件里的全部表（那是考古工作的产出，不是架构设计文档该做的事）。

## 4. 独占区候选的数据结构初步设想

### 4.1 Family Context——如实写明"待建"，不是"已有基础"

`FAMILY_COMMERCIAL_VALUE_STRATEGY_V2.md` §8.2 的技术现状调研已经明确：**`FamilyMemoryDialogueRuntime` 未接入任何调用方，embedding/pgvector 完全不存在于代码**。这是空白，不是"已有基础上的优化"，本文档如实记录，不臆造已有能力。

**初步存储形态设想（目标态，非现状）**：

- Family Context 的原始素材（家庭结构/关系/成长需要/目标/测评/行动/反馈/服务/重大事件/长期偏好）**本身不需要新的存储**——它们已经分布在 `family.*`/`assessment.*`/`growth.*`/`journey.*`/`service.*` 各域的权威表里。Family Context 层要建的不是"再存一份数据"，是一个**跨域只读检索层**：
  - 结构化部分：一个 `ai_runtime.family_context_index` 表（或视图），按 `family_id` 聚合各域Query Port返回的最新状态摘要，供 Model Gateway 调用时快速拼装 system context，**不是**权威数据源，只是检索层的物化缓存，源头永远是各业务域的表。
  - 非结构化/语义检索部分（如"这个家庭去年提到过的困扰"）：需要 embedding + 向量索引（pgvector 或独立向量库），**这部分当前完全不存在**，需要从零选型（pgvector vs 独立向量数据库）、从零设计"哪些文本字段需要embedding"（如测评的自由文本回答、AI假设解读的家庭确认留言），这是一次真正的新建工作，不是接入现成组件。
- **consent边界**：Family Context 检索层读取的每一类数据必须先过 `consent.*` 域的 `ConsentGate`——不能因为"AI Runtime需要更完整的上下文"就绕过同意校验，这与 R9（AI不得绕过业务规则直接读写）同构。

### 4.2 Family Growth Graph——时间序列图谱结构

目标结构（`FAMILY_COMMERCIAL_VALUE_STRATEGY_V2.md` §8.2 原文定义）：

```text
Family ─┬─ Parent ─┬─ Relationship ─── Child
         │           │
         └─ GrowthNeed ─── Goal ─── Behavior ─── Intervention ─── Outcome ─── Evidence

时间轴：T0(初始测评) → T1(21天节点) → T2(90天节点) → T3(长期/年度会员节点)
```

**当前现状（如实写明）**：`perspectives`/`evidence_records` 表严格限定在单次onboarding内查询，**从未跨会话检索**。这条能力也是空白，与Family Context同样是"目标态设计"而非"现有实现的扩展"。

**初步存储形态设想**：

- 节点表（各自归属对应业务域，不新建独立"图谱域"）：`Family`/`Parent`/`Child`/`Relationship` 归 `family.*`；`GrowthNeed`/`Goal`/`Behavior` 归 `growth.*`；`Intervention` 归 `service.*` 或 `growth.*`（取决于是AI推荐的干预还是真人服务的干预，需要Batch 4/7实际设计时区分）；`Outcome`/`Evidence` 归 `growth.*`。
- **图谱的"图"结构本身**（节点间的时间序列边）不建议用图数据库——现有PostgreSQL已经承载所有节点数据，边的语义（"T0的GrowthNeed在T1被这个Intervention响应，产生了这个Outcome"）可以用关系表建模（如 `growth.intervention_outcome_links` 记录 `intervention_id, outcome_id, evidence_id, observed_at, confidence`），除非未来出现"任意深度路径查询"这类关系数据库不擅长的真实需求，否则不提前引入图数据库这个新技术组件（呼应"大胆引进成熟技术但不重造轮子"的原则——先证明关系表不够用,再考虑图数据库）。
- **T0→T1→T2→T3 时间轴**：不是一张独立的"时间轴表"，是每个节点/边记录自带的 `observed_at`/`journey_phase` 字段，查询时按 `family_id + journey_phase` 聚合即可重建时间轴视图。

### 4.3 明确排除项（承接R9红线，会员积分体系不得重演UI-17）

**家庭总分/家庭排名**——宪章R9红线：

> AiFamily 不计算、不存储、不暴露家庭总分与家庭排行。

任何 schema 设计中，**禁止出现**以下字段模式：`family_score`、`ranking`、`rank`、`level`（作为家庭/成长的排序值）、跨家庭比较的聚合分数列。这不是命名建议，是硬性禁止——源仓库 `membership` 域的 `FORBIDDEN_TIER_FIELD_TOKENS` 不变量（`policies.py:24-28`，禁止 `score`/`rank`/`level` 字段）已经尝试用代码强制这条规则，但该不变量的 guardrail test 在源仓库不存在（`MIGRATION_MANIFEST.yaml` 条目 `membership` 明确指出这一缺口）。**AiFamily 侧的对应架构测试必须先补上这个 guardrail test，才能让 membership 域的迁移真正兑现"不复刻这条红线"的承诺，不能只在文档里写禁止**。

**会员积分体系不得复刻UI-17硬编码兜底值这个反面案例**——`FAMILY_UI_BACKEND_SCENARIO_CONSISTENCY_AUDIT_V1.md` §3b 核实的具体事实：源仓库 UI-17 积分商城页面里 `pointsBalance = membership?.dev_points?.balance ?? 1280` 有硬编码兜底值1280，且 `DAILY_TASKS`/`REWARDS` 数组的积分数值（`+50`/`99积分`/`200积分`）是页面内硬编码常量。这个反面案例说明的问题不是"1280这个数字不对"，是**积分/权益这类涉及真实价值的字段，一旦允许"没有真实ledger时用一个看起来合理的默认值顶上"，这个默认值就会在生产环境里被当成真实数据消费**——矩阵001已把UI-17标为`GATE_BOUNDARY`（"尚无积分ledger/兑换DTO"、"不得写真实权益/兑换"），本文档在数据架构层面的对应约束是：

- 积分/权益余额**没有真实ledger表支撑之前，API层不允许返回任何非null的默认余额**——宁可返回"暂无数据"的显式状态，也不允许 `?? 1280` 这类静默兜底值模式进入 Python 侧的任何 schema 或查询代码。
- 积分ledger落地时（Batch 6前置条件，见 `MIGRATION_PLAN_V2.md` §3 COMMERCE闭环处理），必须是独立的 `commerce.point_ledger_entries` 事件流表（每次积分变动一行，可追溯来源），不是一个可以被直接 `UPDATE` 的余额字段——余额永远是ledger的聚合结果，不是权威存储本身，这样才能杜绝"硬编码兜底值"这种问题的数据结构根源（可变余额字段天然诱使开发者在没有真实数据时填一个默认值；不可变事件流天然没有"默认值"这个选项，没有事件就是零，没有例外）。

## 5. 与 TECH_ARCHITECTURE.md / MASTER_BLUEPRINT.md 的关系

- 本文档的 schema 划分是 `TECH_ARCHITECTURE.md` §2"三进程职责边界"在存储层的具体化：`family_api` 进程写 `family.*`/`assessment.*`/`growth.*`/`journey.*`/`program.*`/`service.*`/`content.*`；`ai_runtime` 进程写且只写 `ai_runtime.*`（不直写业务schema，是R9的存储层落地）。
- 本文档第4节的独占区候选数据结构初步设想，对应 `MASTER_BLUEPRINT.md` §3 的进程归属判断——"数据归业务域、检索/推理归intelligence"这一判断在本文档体现为"节点表归业务域schema、检索索引/embedding归ai_runtime schema"。
- 第1节的技术债（58个SQL文件的重号与死列）是 Alembic baseline 生成前必须完成的独立工作项，建议作为 `database_schema` 能力从 `PLANNED` 转 `IN_PROGRESS` 的第一个PR，且该PR应该只做"线性化+baseline生成"，不夹带任何schema层的目标态重设计（第2节的按域分schema是后续PR的工作，不应该和baseline生成混在一次变更里，否则无法区分"迁移导致的行为变化"和"忠实搬运历史schema"两类风险）。
