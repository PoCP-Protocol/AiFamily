---
id: DELIVERY-BACKLOG-001
title: AiFamily 任务分派台账
type: delivery
status: current
version: 1.0
owner: chief-architect
created: 2026-08-29
updated: 2026-08-29
canonical: true
supersedes: null
superseded_by: null
---

# AiFamily 任务分派台账

> **用途**：总架构师在此定义任务，由其他 AI / 开发者领取执行。
> 每个任务是自包含的——领取者读完任务卡即可开工，不需要追问上下文。
>
> **领取前必读**：`CLAUDE.md`（铁律与本仓库特有的坑）→
> `docs/00_system/SYSTEM_MANIFEST.md`（系统边界与真相文档清单）→
> `governance/REPOSITORY_CONSTITUTION.md`（14 条工程宪章）。

## 0.0 生效中的冻结指令（FREEZE）

> **FREEZE-001 ｜ COMMERCE 方向新增实现 ｜ 2026-08-29 生效 ｜ 下达：项目经理**
>
> **范围**：`backend/domains/loyalty_points`、`backend/domains/membership/api`，
> 以及任何新增的商品目录 / 订单 / 支付 / 积分 / 权益兑换实现。
>
> **允许**：补测试、补合规守卫、修既有缺陷、写文档。
> **禁止**：新增业务能力、新增 API 端点、扩大数据模型。
>
> **依据（不是个人判断，是计划的明文要求）**：
> - `MIGRATION_PLAN_V2.md` 第4节：COMMERCE 闭环排在 **Batch 6**，当前是 Batch 1/2 阶段。
> - `MIGRATION_PLAN_V2.md` 第3节对 COMMERCE 行的明文前置条件：「迁移前**必须先**解决
>   UI-17 的硬编码积分和『未成年人商业场景权限规则不明确』的 Stop Condition」。
>   该 Stop Condition **至今未解决**。
> - `docs/12_governance/COMPLIANCE_HARD_CONSTRAINTS.md` 第3节：《未成年人网络保护条例》
>   第24条第3款是**绝对禁止**——不得通过自动化决策方式向未成年人进行商业营销。
>   积分体系正落在该禁止范围内，且当前**无任何检查器**在业务语义层面拦这件事。
>
> **解冻条件（三条全满足）**：
> 1. 项目所有者对 `loyalty_points`（约 1984 行、源仓库无对应物、零测试）是否应存在于
>    当前阶段做出裁决 —— 见 `governance/MIGRATION_MANIFEST.yaml` → `loyalty_points`
>    的 `review_required` 字段。
> 2. 存在一个能真实失败的 guardrail 测试，证明积分/权益流程无法以孩子为营销对象。
> 3. UI-17 的硬编码积分兜底值（`pointsBalance ?? 1280`）的处置已确定。
>
> **为什么下这条冻结**：项目经理在 2026-08-29 复读迁移计划时确认，COMMERCE 工作已
> 超出既定批次顺序推进，而同期计划要求提前的 **Batch 2 SERVICE 预约子链 6 个端点
> 全部 MISSING、无人在做**（见 `contracts/openapi/UI_API_ENDPOINT_INVENTORY.md`）。
> 优先级实际是反的。冻结不是否定 COMMERCE 的价值，是恢复计划顺序。

## 0.1 已发生的计划偏离（项目经理自查记录）

如实记录，因为不记录就会重复发生：

| # | 偏离 | 后果 | 处置 |
|---|---|---|---|
| 1 | COMMERCE 超前推进，Stop Condition 未解决 | loyalty_points 1984 行零测试进仓 | FREEZE-001 |
| 2 | 计划要求提前的 Batch 2 SERVICE 无人分派 | 已验证的付费主力闭环价值悬空 | 提为下一优先，见 T-15 |
| 3 | 已提交的 `market_intelligence`/`product_strategy` 被删除，无二次确认记录 | 违反 project-owner「先把所有 Python 代码都迁移过来」指示；违反计划第1节 `DELETE` 需二次确认 | 已从 git 恢复 |
| 4 | 治理文件编辑被并发会话覆盖两次（loyalty_points 登记、assessment 合并） | registry 与磁盘反复漂移 | 见下方「并发写作纪律」补充 |

**并发写作纪律补充（针对偏离 #4）**：治理 YAML（`governance/*.yaml`）是多会话高频争用点。修改前必须先重读文件最新状态；发现自己的条目消失时，**先查是否被覆盖再重写**，并在条目里留下 `registration_note` 记录这是第几次登记。不要假设自己上次的编辑还在。

## 0. 当前系统状态（截至 2026-08-29）

```text
测试        96 passed / 1 skipped
Lint       383 ruff errors（全部来自新增业务代码，见 T-01）
架构护栏     28 个架构测试，含 8 个合规检查器
可运行 API   /health /ready /auth/* /families/{id}/assessments/*（进程内内存实现）
数据库       无 Alembic baseline，无真实 Postgres 接入
前端        frontend/mobile 34 个 UI 已迁入，因后端 API 不足而全部不可用
```

## 1. 任务优先级说明

| 级别 | 含义 |
|---|---|
| **P0** | 阻塞其他工作，或正在产生债务累积 |
| **P1** | 关键路径，Batch 1/2 交付所必需 |
| **P2** | 重要但可并行推迟 |
| **P3** | 改善类，有余力再做 |

**并发纪律**（所有任务共同遵守）：
- 源仓库 `D:\family-ai` **只读**，其中有其他会话的未提交 WIP
- 提交必须带 pathspec，禁止 `git add -A`
- 只改自己任务范围内的文件；发现他人文件有问题 → 报告，不擅自改
- 完成前必须跑 `uv run pytest -q` 与 `uv run ruff check .`，不得让仓库变红

---

## T-01 ｜ P0 ｜ 清理 383 个 ruff 错误

**背景**：新增的 assessment / membership API / product_intelligence zone 代码引入了 383 个 lint 错误（主要是 E501 行过长、I001 导入未排序）。这些不是功能问题，但会让后续所有 PR 的 diff 里混入无关的格式噪声，也会让 `ruff check` 失去信号价值——它现在总是红的，于是没人再看它。

**范围**：
- `uv run ruff check . --fix` 处理可自动修的 37 个
- 剩余手工处理，优先 `backend/` 下的业务代码
- **不要**动 `frontend/`（已在 `pyproject.toml` 的 ruff `exclude` 里，那是刻意保持与源仓库逐字一致）

**注意**：如果某个 E501 是因为一行里塞了多个语句（如 `identity = actor(...); key = mutation_key(...)`），拆成两行而不是加 `# noqa`。`backend/domains/assessment/api.py` 有多处这种写法。

**验收**：`uv run ruff check .` 输出 `All checks passed!`，且 `uv run pytest -q` 仍为 96 passed。

---

## T-02 ｜ P0 ｜ 补 membership FORBIDDEN_TIER_FIELD_TOKENS guardrail 测试

**背景**：`backend/domains/membership/domain/policies.py:27` 定义了 `FORBIDDEN_TIER_FIELD_TOKENS`（禁止 score/level/rank/grade/percentile/progress_pct 出现在会籍实体上），注释自称"Enforced by a guardrail test that reflects over every model in `entities.py`"——**该测试从未存在**，从源仓库延续至今。

已有一个仓库级检查器 `tests/architecture/test_compliance_constraints.py::test_no_scoring_or_ranking_fields_anywhere`，但它检查的是"家庭/孩子主体 + 评分动词"的组合（R9 语义），**不等价于** membership 自己声明的字段白名单约束。两者都需要。

已发现有人开始写 `tests/domains/membership/test_tier_field_guardrail.py`，请先检查该文件当前状态再动手，避免重复。

**范围**：写一个反射测试，遍历 `backend/domains/membership/domain/entities.py` 中所有 pydantic 模型的字段名，断言无一命中 `FORBIDDEN_TIER_FIELD_TOKENS`。

**验收**：
- 测试真实通过
- **必须验证它会咬人**：临时给某个实体加一个 `tier_score: float` 字段，确认测试失败，然后移除。在提交说明里写明你做了这个验证。
- 完成后把 `governance/DOMAIN_REGISTRY.yaml` 与 `governance/CAPABILITY_REGISTRY.yaml` 里 membership 的 `status` 从 `MIGRATED_UNTESTED` 升为 `MIGRATED_TESTED`，并删除对应的 `status_rationale`/`known_gaps` 条目

---

## T-03 ｜ P1 ｜ 建立 Alembic baseline 与真实 Postgres 接入 —— ✅ 已完成（2026-08-29）

**交付物**：
- `database/migrations/LINEARISATION_MAP.md` —— 62 行映射 + 4 组重号逐组排序理由与实测证伪
- `database/baseline/*.sql` —— 62 个线性化文件，sha256 与源文件一致
- `alembic.ini` + `database/migrations/{env.py, script.py.mako, versions/0001_legacy_schema_baseline.py}`
- `docker-compose.dev.yml` —— 一次性 Postgres（127.0.0.1:55442）
- `tests/support/postgres.py`、`tests/database/`、`tests/apps/family_api/test_ready_against_postgres.py`
- `database/README.md`

**实测口径修正**（下方"背景"的数字有误，保留原文以便追溯）：源目录实为 **62** 个 `.sql` 文件（"58" 是最大编号，非文件数）；4 组重号**组内全部无依赖**（逐组交换后 62 个文件仍全部应用成功且 schema 等价），唯一硬依赖是跨组的 `test_experience_workflows` → `family_growth_page_objects`；`growth_profiles` 两代列**不是死列**而是活的双写列。详见 LINEARISATION_MAP.md §0/§3/§4。

**新发现、待裁决**：`product_intelligence` 域本地 `0058` SQL 副本比 baseline 多 `validated_by`/`validated_at`/`validation_reason` 三列，而该域 ORM 要求这三列 —— 在只跑过 `alembic upgrade head` 的库上该域会失败；现有集成测试因自己读本地 SQL 建库、绕开 baseline 而未暴露。处置建议见 `backend/domains/product_intelligence/migrations/README.md`，落地属 T-05。

**未做（刻意）**：按域分 schema（`identity.*`/`family.*`/…）与每域独立 DB role 仍是目标态 —— `docs/07_data/DATA_ARCHITECTURE.md` §5 要求 baseline PR 只做忠实快照，不夹带目标态重设计。T-05 已解除阻塞。

---

**背景**：源仓库有 58 个手写 SQL 迁移（`0001`–`0058`），且**4 组文件名重号**（0022/0023/0024/0053 各有两个不同内容的文件），必须先线性化才能生成 Alembic 初始 revision。当前 AiFamily 所有测试跑在 SQLite 内存库上，`backend/platform/persistence/session.py` 的 Postgres 路径从未验证。

参考：`docs/07_data/DATA_ARCHITECTURE.md`（含重号清单与按域分 schema 目标设计）。

**范围**：
1. 解决 4 组重号：读两个同号文件的内容，按实际依赖关系重排为线性序，产出一份映射表记录"原文件名 → 新序号"
2. 生成 Alembic baseline revision
3. 让 `product_intelligence` 与 `membership` 的仓储测试能对真实 Postgres 跑（docker-compose 起库）
4. `/ready` 端点接真实 Postgres 连接检查

**不在范围**：不要迁移业务数据，只建 schema。

**验收**：`alembic upgrade head` 在空库上成功；至少一个域的仓储测试对真实 Postgres 通过；SQLite 测试路径保留（快速反馈用）。

---

## T-04 ｜ P1 ｜ 提取 34 个 UI 的完整 API 契约清单

**背景**：`frontend/mobile` 的 34 个 UI 屏幕已迁入但全部不可用——它们需要 ~40+ 后端端点 + 4 个 `/auth/*`。目前 Python 后端只实现了 assessment 那一段。**在契约清单出来之前，后端会凭空设计出前端不需要的 API。**

**范围**（只读 `frontend/mobile`，不改前端代码）：
1. 穷尽提取端点：主来源 `frontend/mobile/lib/family/family-api-client.ts`，但**必须**逐个检查 `app/ui/UI-*.tsx` 与 `app/(tabs)/index.tsx`（即 UI-01），找出绕过 client 直接 fetch 的调用
2. 每个端点记录：方法 / 完整路径（含路径参数）/ 调用它的 UI 编号 / 请求体关键字段 / 响应体关键字段（从 TS 接口定义提取）
3. 按八组分类：ASSESSMENT / PLAN / GROWTH / SERVICE / COMMERCE / COMMUNITY / AUTH / DEV_SYNTHETIC
4. **最有价值的一步**：`/dev/*` 合成路由的**字段级拆解**。已知 9+ 屏幕（UI-10/11/12/22/23/25/27/28/29）消费 `/dev/core-growth` 与 `/dev/platform-surfaces`，而源仓库这两个服务自述 `data_source: 'SYNTHETIC_DEV_ONLY'`。逐字段判断：这个字段的真实数据源应该是什么？（有些可能是纯前端文案，根本不需要后端；有些如任务完成状态必须来自真实 DB）
5. 标注 R9 红线风险端点：涉及家庭总分/排名/成长效果断言/成果证明的，明确写"Python 后端不应原样实现，需产品侧先裁决"

**输出**：`contracts/openapi/UI_API_CONTRACT_INVENTORY.md`

**验收**：端点总数与分组统计；`/dev/*` 字段级真需求 vs 假需求判断；施工优先级建议（Batch 1 与 Batch 2 各需实现哪些端点才能让对应屏幕真正可用）。每条断言给文件路径+行号。

---

## T-05 ｜ P1 ｜ Assessment 域重构为四层结构 + 落 Postgres

**背景**：`backend/domains/assessment/` 当前是 `api.py` + `service.py` 两个模块 + 内存 repository，不是四层结构。它作为 vertical slice 验证 HTTP 链路是合理的，但要成为 Batch 1 交付物必须落地。

**依赖**：T-03（Alembic baseline）必须先完成。

**范围**：
1. 按 `docs/10_engineering/ENGINEERING_ARCHITECTURE.md` 重构为 `api/` `application/` `domain/` `infrastructure/` 四层
2. 建模 `AssessmentSession` / `AssessmentTool` / `AssessmentResponse` 实体
3. SQLAlchemy 仓储 + Alembic 迁移
4. 保留现有 HTTP 测试全绿（`tests/apps/family_api/test_assessment_routes.py`）

**红线**：
- AI 解读路径**不得**原样搬迁源仓库的 `claude_interpretation.py`。按 R7 必须经 `backend/intelligence/model_gateway` 重写；该模块目前不存在，所以本任务范围内只做确定性解读路径
- Hypothesis 初始 status 必须是 DRAFT，且不得有任何代码路径自动置为 VALIDATED（架构测试会检查）

**验收**：四层结构 + Postgres 仓储测试通过 + 原有 HTTP 测试不回归；更新 `DOMAIN_REGISTRY.yaml` 的 assessment 条目，删除已解决的 known_gaps。

---

## T-06 ｜ P2 ｜ 建 Model Gateway（AI 能力的前置基础设施）

**背景**：`backend/intelligence/` 下目前只有 `design_copilot`（全是 `NotImplementedError`）。**没有 Model Gateway，任何 AI 能力都无法合规落地**——R7 要求领域不得直连供应商，而合规约束（不得转委托）要求供应商准入必须集中管控。

参考实现：源仓库 `50_开发_dev/packages/ai-gateway/src/index.ts`（894 行，Routing/Timeout/Admission/FailClosed/Provenance 均真实存在）。**作为设计参考重译，不搬 TS 代码。**

**范围**：
- Provider 注册与准入（含合规字段：是否转委托、是否允许未成年人数据）
- Routing / Timeout / Retry 策略（注意源仓库刻意设 `automatic_retry: 0` + fail-closed，理解其理由后再决定是否沿用）
- AI Provenance：model / model_version / prompt_version / context_snapshot / confidence 强制记录
- 所有输出标记为 Draft，`may_mutate_business_state = False`

**红线**：`backend/intelligence/` 下的代码**不得** import 任何业务域的 repository。

**验收**：至少一个真实 provider + 一个 FakeProvider；fail-closed 行为有测试；架构测试 `test_no_direct_provider_sdk_outside_model_gateway` 仍绿。

---

## T-07 ｜ P2 ｜ 补合规约束的剩余执行机制

**背景**：`docs/12_governance/COMPLIANCE_HARD_CONSTRAINTS.md` 的六条法定硬约束中，已有 8 个检查器覆盖了可机械检验的部分。**仍有三条只是意图**：

1. **读取访问留痕**（《未成年人网络保护条例》第36条）：当前 `backend/platform/audit/` 只覆盖状态变更（R6），法规要求**读取**未成年人个人信息也须留痕并经审批。需要扩展 `AuditEvent` 支持 READ 动作 + 对应检查器。
2. **DPIA 记录留存 ≥3 年**（PIPL 第55/56条）：需要机制而非一次性文档。
3. **留存期限绑定**：每个存储未成年人数据的字段须有明示留存期限与到期处理方式（《儿童个人信息网络保护规定》第10/12条）。可考虑用模型元数据 + 检查器强制。

**范围**：至少完成第 1 条（读取留痕），另两条产出设计方案。

**验收**：新检查器必须验证会咬人（植入违规 → 失败 → 移除），并在提交说明里写明验证过程。

---

## T-08 ｜ P2 ｜ Traceability 断链检查器

**背景**：`tools/architecture/` 目录当前**完全为空**。`docs/12_governance/DOCUMENT_GOVERNANCE.md` 定义了目标追溯链：

```text
Strategy → Business Capability → Product Capability → Domain
         → Command/Event → API → Code → Test → Metric
```

`governance/CAPABILITY_REGISTRY.yaml` 已经承载了 Domain→Command→API→Code→Test 这一段，且已有测试校验路径真实存在。缺的是**上游**（Strategy/Business Capability 到 Capability 的映射）与**断链报告**。

**范围**：写一个检查器，报告：哪些 capability 没有上游业务能力归属、哪些 API 没有对应 capability 登记、哪些代码目录未被任何 capability 覆盖。

**验收**：检查器可运行并产出可读报告；先做成"报告模式"（不失败 CI），确认信噪比可接受后再考虑转为强制。

---

## T-09 ｜ P3 ｜ 重跑 deep-research 主题 3 与主题 4

**背景**：此前一轮 deep-research 中，主题 3（贝壳 ACN 机制可迁移性）与主题 4（成熟 AI 平台架构范式）**零条声明通过对抗性核验**。这意味着：
- FGCN 设计目前只有内部文档自证，缺外部证据支撑其可行性
- AI Runtime 设计缺乏成熟平台的实践与踩坑经验参照——而主题 4 本来是要用来校正 `docs/05_ai/AI_ARCHITECTURE.md` 的

**范围**：重新设计更聚焦的检索角度后重跑。建议把主题 4 拆成独立子问题分别研究（Agent Runtime 状态管理 / Context 与 Memory 工程 / guardrail 工程实现 / Model Gateway 容错 / eval 体系），不要一次问五个方面。

**验收**：结论进入 `docs/13_research/`，**必须**带 `RESEARCH_ONLY` / `NOT_CANONICAL` 标记（架构测试会检查）。若要影响正式设计，须先走 ADR。

---

## T-10 ｜ P3 ｜ 补齐文档 front matter 与空目录说明

**背景**：`docs/` 下多份既有文档缺 YAML front matter（`docs/00_system/CURRENT_TECHNOLOGY_BASELINE.md` 等用的是行内 `- **状态**:` 写法），与 `DOCUMENT_GOVERNANCE.md` 定的规范不一致。另有若干目录为空（`docs/04_domains/`、`docs/06_platform/`、`docs/08_experience/`、`docs/09_operations/`）。

其中 **`docs/06_platform/` 为空是最实质的缺口**——`backend/platform/` 六项内核都有真实代码与测试，但规格文档完全没回写。

**范围**：
1. 给所有 canonical 文档补 front matter，`status` 只用 `draft|review|current|deprecated|archived`
2. 为 `backend/platform/` 六项内核补写 `docs/06_platform/` 规格文档（从代码反向记录实际契约，不要写愿望）

**验收**：`docs/00_system/DOCUMENTATION_MAP.md` 的空目录标注同步更新。

---

## 2. 任务依赖关系

```text
T-01 (lint)  ─────────────────────────────► 独立，尽早做
T-02 (guardrail) ─────────────────────────► 独立
T-03 (Alembic) ──┬──► T-05 (Assessment 四层)
                 └──► T-07 第1条(读取留痕，需真实 audit 表)
T-04 (API 契约) ─────► 所有后续端点实现的输入
T-06 (Model Gateway) ─► 一切 AI 能力的前置
T-08 (traceability) ──► 依赖 T-04 产出的 API 清单更完整
T-09 (research) ─────► 影响 T-06 的设计选择，但不阻塞
T-10 (docs) ─────────► 独立
```

**建议并行分配**：T-01 / T-02 / T-04 / T-10 可立即并行（互不重叠）。T-03 完成后解锁 T-05。T-06 独立启动。

## 3. 每个任务完成时必须回报

```text
1. 改了哪些文件（路径清单）
2. 测试结果（uv run pytest -q 的实际输出行）
3. Lint 结果（uv run ruff check . 的实际输出）
4. 如果新增了检查器：验证它会咬人的过程
5. 发现但未修的问题（属于他人范围或需裁决的）
6. 是否更新了对应的 registry / canonical 文档
```

**不接受**："应该可以了"、"测试大概能过"。要贴实际输出。
