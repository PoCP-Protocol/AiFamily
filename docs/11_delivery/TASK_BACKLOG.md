---
id: DELIVERY-BACKLOG-001
title: AiFamily 任务分派台账
type: delivery
status: current
version: 1.0
owner: chief-architect
created: 2026-08-29
updated: 2026-08-30
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

## 0.0 商业能力建设规则（替代已撤销的 FREEZE-001）

> **FREEZE-001 已撤销（2026-08-30）。** COMMERCE 属于 Batch 6，批次只规定交付顺序，
> 不禁止在测试环境建设完整功能，也不允许用“真实支付尚未接入”作为删减业务流程的理由。
>
> **建设范围**：商品目录、订单、支付、积分、会员、权益兑换、退款、续购、返佣/结算和
> 相应的 API、数据模型、状态机、权限、Consent、Audit、幂等、失败与补偿路径，均须按生产
> 形状建设。开发/测试使用 synthetic data、支付 sandbox、fake payout adapter 和故障注入；
> 生产再切换真实商品、支付、返佣、库存和通知渠道。
>
> **不可放宽的验收项**：正式积分 ledger 替代 UI-17 的 `pointsBalance ?? 1280`；积分和
> 权益流程必须有能真实失败的 guardrail，禁止基于画像向未成年人自动化商业营销；家庭总分、
> 家庭排名、AI 自动写入事实等红线在所有环境都保持相同的拒绝、审计和人工处理路径。
>
> **执行原则**：上述验收项约束实现质量、数据真实性和生产准入，不是 COMMERCE 的开发
> 阻塞条件。若外部真实供应商尚未获准，先用等价适配器完成并验收完整流程。

## 0.1 已发生的计划偏离（项目经理自查记录）

如实记录，因为不记录就会重复发生：

| # | 偏离 | 后果 | 处置 |
|---|---|---|---|
| 1 | COMMERCE 超前推进且验收项未完成 | loyalty_points 1984 行进入仓库时缺测试与合规守卫 | 已撤销全局冻结；补齐测试、guardrail、账本和适配器分层 |
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

## T-16 ｜ P0 ｜ 补 `ModelDraft` 的四处封印泄漏

**归属**：T-06 执行者。规格见 **ADR-0014 §2**（本卡由总架构师下发）。

`contracts.py:20-25` 的 docstring 记录了作者朝「让 R9 成为类型层属性」努力的推理，
推理是对的，**但只覆盖了一个字段**。对当前落盘代码实测（`uv run python`，2026-08-29）：

```text
LEAK-1  ModelDraft(output={}, provenance=p, status="APPROVED").status → "APPROVED"
        Literal 是 typing-only，且 ModelDraft 整个类没有 __post_init__
LEAK-2  dataclasses.replace(d, status="CONFIRMED").status → "CONFIRMED"
        作者为 may_mutate 点名防住的危险，原样落在 status 上
LEAK-3  d.output["injected"] = "fact" → 成功（frozen 不深冻结 payload，dict 是可变别名）
LEAK-4  class Evil(ModelDraft) 覆盖 property → True（slots 不阻止继承）
```

**修法**：LEAK-1/2 → 加 `__post_init__` 校验 `status == "DRAFT"`（`replace` 也走它，一处修两个）；
LEAK-3 → `output` 存 `MappingProxyType(deepcopy(raw))`，注解改 `Mapping`；
LEAK-4 → `__init_subclass__` 抛 `TypeError`。
**并修 docstring**：`:53-57` 的「no gateway-side transition out of it」对 gateway 成立、
对类型不成立，两件事要分开写，否则读者以为类型已封死。

`test_ai_runtime_isolation.py::test_model_gateway_output_type_cannot_mutate_business_state`
已断言 `may_mutate_business_state` 不是 dataclass 字段——**LEAK-4 说明该断言不足以证明封印**，
补 `__init_subclass__` 后应追加子类化抛错的断言。

**验收**：四处各有测试；**必须验证会咬人**（逐条植入→失败→移除），提交说明贴过程。

---

## T-17 ｜ P1 ｜ assessment 域接 `ActorContext` + `PolicyEngine`

**归属**：T-05 执行者。**等 T-01 格式化落地后再动**，否则语义变更会混进格式 diff，review 时分不清。
规格见 **ADR-0014 §Context 2 / §6**。

**这是当前唯一一处正在生效的 R9 漏洞**：
`service.py` 全域收 `actor_id: str` 而**不用 `ActorContext`**——而 `context.py:66-75` 的
`ActorContext.is_ai` 是 R9 唯一密封缝（该文件 docstring `:11-17` 自述它是「每个上层必须使用的 seam」）。
该域也**不用 `PolicyEngine`**；`api.py:53-59` 的 `actor()` 只校验 Bearer token 与 family 匹配，
**不问 actor 类型**。于是 `decide()` 能把 hypothesis 置为 `CONFIRMED`，
而**没有任何东西阻止一个 AI actor 确认一个假设**。
它还骗过了护栏：`test_compliance_constraints.py` 那条「晋升函数须有人类 actor 形状参数」
的判据是**参数名形状**，被一个叫 `actor_id` 的 `str` 骗过。

**范围**：① `actor_id: str` → `ActorContext`；② CONFIRM 过 `PolicyEngine.check()`，
规则注册 `human_only=True`（`policy.py:100-105` 在任何 allow 之前无条件拒 AI）；
③ **照 `membership/api/routes.py:85-107` 的 `_authorize` 抄**，不要发明第二种接入模式（R10 伤疤）；
④ `generate_hypothesis()` 现返回硬编码中文句「家庭可以从一次可观察的沟通实验开始。」，
属 `AI_NATIVE_PRINCIPLES.md` §4 反面清单第 1/3 条且**已挂生产路由**——改为经 `model_gateway`，
**未配置时 fail-closed，不返回罐头文案**。

**已知会破**：`tests/domains/assessment/test_acceptance_chain.py`（位置实参 + 事件计数断言）、
`tests/apps/family_api/test_assessment_routes.py`（hypothesis 端点 200 → 503）。同步更新，别删。

**验收**：AI actor 尝试 CONFIRM 被拒且产生 `AuditEvent`。

---

## T-18 ｜ P1 ｜ `Value Architecture` + `StateObservation` 领域模型（PR-003）

**归属**：PR-003 执行者。**动手前必读 ADR-0015 全文**（规格在 §1 / §2 / §4 / §5）。

project-owner 定调 Family Growth Intelligence OS，四层价值要真进代码。链条变为
`Problem → Hypothesis → Contradiction → Value Architecture → Strategy`，
`Value Architecture` 是 `Strategy` 的**必填输入**（先回答该获得什么价值，再选干预，不得反过来）。

**三条硬边界（违反即撞 R9 或 ADR-0006）**：
1. **家庭侧永不出现分数。** 三层只表达方向（`Emotional: from→to`、`Action: next_action_ref`、
   `Growth: changed_dimension_ref`），**只有 Economic 可量化**，且量化对象是时间/金钱/试错次数**而非家庭**。
   六个 Value Score 只在 Product Intelligence 侧作为**队列级**指标存在，永不写回家庭对象。
2. **State 是「带来源与有效期的观察」，不是主体上的列。** `StateObservation` 必填
   `evidence_refs` / `provenance` / `expires_at` / `retention_policy`——`expires_at` 是
   「非永久人格标签」（R9 FELS 表 `legacy_tag.*`）的执行机制。
   `observed_value` **不得**注解 `float`/`int`/`Decimal`（序数标签可以，数值分数不行）。
3. **`risk` 维度观察不得触发任何自动动作**（R9：`legacy_alert.risk_score` → 非阈值、非自动动作），
   只产出 Human Gate 待办。

**同批必须落的断言**（否则三条退化为意图，R14）：四必填字段反射断言；
`observed_value` 类型注解检查；`Strategy` 构造器的 `value_architecture` 参数**无默认值**
（照 `backend/packages/contracts/evidence.py:50` 的 `Provenance.level` 手法）。

`tests/architecture/test_r9_value_layer_boundary.py`（已落地）会在你写出
`class FamilyValueScore` 或 `FamilyProfile.emotional_value_score` 时咬你。

---

## T-19 ｜ P2 ｜ 执行三份边界 ADR 的 registry / manifest 同步

> **编号说明**：本卡与 T-16/T-17/T-18 原取号 T-11~T-14，与并发会话在 commit 消息中
> 已使用的 T-11（audit 持久化）/ T-12（PolicyEngine R9 绕过修复）撞号，故重编为 T-16~T-19。
> T-15 由项目经理预留给 Batch 2 SERVICE。**编号严格顺序分配、永不复用**（沿用
> `governance/ADR/README.md` 的编号规则）；下一个可用编号 = T-21。

---

## T-20 ｜ P1 ｜ 补 membership V2 生命周期对象的 Alembic revision

**背景**：`backend/domains/membership` 的 `domain/entities.py` 与
`infrastructure/sqlalchemy_models.py` 已经定义了四个 V2 对象——
`MembershipTierDefinition`、`MembershipPeriod`、`MembershipTierTransition`、
`BenefitReservation`——但从源仓库延续至今**从未有过 DDL**。`database/baseline/
0036_family_membership_entitlement_objects.sql`（legacy 0033 的线性化重命名）
只覆盖 `plans` / `benefit_definitions` / `subscriptions` / `benefit_grants` /
`benefit_ledger` 五张表，四个 V2 表在源仓库里就不存在，不是遗漏搬运。

这正是 `governance/DOMAIN_REGISTRY.yaml` → `membership` 条目 `known_gaps` 第 (3)
条："数据库迁移未落地——AiFamily 选定 Alembic，但…ORM 模型当前只靠测试里的
`metadata.create_all` 建表"。T-02 的 guardrail 测试落地后（`MIGRATED_TESTED`，
18 passed）这是 membership 剩下三个已知缺口里**唯一纯 schema 性质、不涉业务逻辑
判断**的一条，适合独立领取。

**范围**：
1. 新增 Alembic revision `database/migrations/versions/000X_membership_lifecycle_v2.py`
   （`down_revision` 接当前 head；建 revision 前先 `alembic heads` 确认，别假设还是
   `0002_platform_audit_events_worm`——治理并发环境里 head 可能已被其他任务推进）。
2. 用 `op.create_table`（照抄 `0002_platform_audit_events_worm.py` 的写法，不是
   `op.execute` 整段手写 SQL；baseline 之后的规则是"新 schema 用 SQLAlchemy 操作
   表达"，见 `docs/07_data/DATA_ARCHITECTURE.md` §1.3 第4条）建四张表，字段与
   `infrastructure/sqlalchemy_models.py` 的 `MembershipTierDefinitionRow` /
   `MembershipPeriodRow` / `MembershipTierTransitionRow` / `BenefitReservationRow`
   **逐列对齐**（表名分别是 `family_membership_tier_definitions` /
   `family_membership_periods` / `family_membership_tier_transitions` /
   `family_membership_benefit_reservations`，ORM 里已经写死，不要另起名字）。
3. 需要新建 4 个 Postgres enum 类型（`tier_code`=M0_FREE/M1_GROWTH/M2_ANNUAL、
   `transition_direction`=UPGRADE/DOWNGRADE/LATERAL/INITIAL、
   `period_status`=ACTIVE/CLOSED、`reservation_status`=HELD/RELEASED/CONSUMED/EXPIRED）；
   `scope_type`/`status`（tier_definitions 上的）复用 baseline 已建的
   `family_membership_scope` / `family_membership_plan_status`，不要新建重复枚举。
4. **`activation_source_type` 必须是数据库层 CHECK 白名单**（不是应用层校验一处、
   DB 层放行的双重标准）：允许值取 `domain/value_objects.py` 的
   `ACTIVATION_SOURCE_TYPES` 七个（`FAMILY_ACCOUNT_CREATED` /
   `GROWTH_PRODUCT_ACTIVATED` / `ANNUAL_MEMBERSHIP_ACTIVATED` /
   `ANNUAL_MEMBERSHIP_RENEWED` / `ADMIN_MANUAL_GRANT` /
   `MEMBERSHIP_PERIOD_EXPIRED` / `SUBSCRIPTION_CANCELLED`）。同模块的
   `FORBIDDEN_ACTIVATION_SOURCE_TYPES`（积分/AI/社群角色/裂变草稿/家庭分数排名）
   不需要单独 CHECK 排除它们——白名单本身已经排除了一切不在名单上的值，这是
   T-02 guardrail 测试覆盖不到的部分（那条测试反射字段名，不反射 CHECK 约束的值域）。
5. `fixture_only`/`external_effect` 两列在其余 membership 表都是 DB 级 CHECK 锁定
   为 `true`/`false`（0033/0036 原文），V2 四张表如果保留这两列（`periods` /
   `tier_transitions` / `benefit_reservations` 的 ORM 模型里确实有），同样要锁。
   `tier_definitions` 没有 `external_effect`（它是目录主数据，不是家庭事实）。

**不在范围**：不写这四张表的 SQLAlchemy 仓储/应用层代码（那部分 ORM 模型层已经
存在，仓储层是否需要新方法属 T-02 之外的 membership 后续任务，不与本卡混）；
不解决 `known_gaps` 剩下两条（真实 Postgres 集成测试覆盖 CHECK 约束、HTTP 路由挂载）。

**验收**：
- `alembic upgrade head` 在空 Postgres 上成功建出四张表；`alembic downgrade -1`
  可回退到上一个 revision（本卡的 `downgrade()` 只需 drop 自己建的对象，不做
  legacy baseline 那种"扫描 catalog"的通用回滚）。
- 至少一个真实 Postgres 集成测试对着这四张表插入一行合法数据成功、插入一行
  `activation_source_type='AI_RECOMMENDATION'` 的数据被 CHECK 拒绝（验证约束真的
  在数据库层生效，不只是 ORM/domain 层）。
- 完成后更新 `governance/DOMAIN_REGISTRY.yaml` → `membership.known_gaps`，删除
  已解决的第 (3) 条，保留另外两条。

三项互不依赖，可拆三个 PR。**`MIGRATION_MANIFEST.yaml` 与 `ADR/README.md` 正被并发会话修改，
动手前先 `git status` 并按 §0.1 的并发写作纪律留 `registration_note`。**

1. **ADR-0012（`growth_plan` → RETIRE 并入 `journey`）**：在 `journey` 域开工的同一个 PR 内做，
   不要单独开 PR 造一个空 journey 目录。5 个异常类迁入 `journey/domain/errors.py`，
   类名 `GrowthPlan*` → `Journey*`，**`code` 字面量不变**（API 可观测行为）。
   **⚠ 删目录需 project-owner 二次确认**——见 ADR-0012 §Decision 2 与本文件 §0.1 偏离 #3
   （同类删除刚发生过一次并被回滚）。未取得确认时只降级 registry、**保留目录**。
   执行前先读源仓库 `journey-plan.service.ts` 确认它管一件事；若确为两个能力，回来推翻 ADR。
2. **ADR-0011（identity/tenancy 边界）**：`auth_identity` 的 `canonical_path` 改
   `backend/domains/identity`；manifest 中**删除不存在的 `backend/platform/tenant`** target；
   租户聚合归 `backend/domains/tenancy`。**趁 `auth_identity` 还是 `NOT_STARTED`，
   这是零成本改登记的最后时刻。**
3. **ADR-0013（`frontend_web`）**：disposition → `ARCHIVE`、status → `NOT_MIGRATING`、
   从 `review_required_index` 移除；新增 `test_oracle_web_route_contracts` 把那 24 个 spec
   收割为 **T-04 的第二契约来源**（两来源不一致处即契约真实歧义点）。
   **不得把 spec 本体复制进仓**（R3）。

---

## T-20 ｜ P0 ｜ 给 `outbox_events` 一个平台级所有者 + `DomainEvent` 类型 + relay

**归属**：可独立领取。**这张卡是 P0 不是因为它阻塞谁，而是因为它有时间窗——
现在只有 1 个域写 outbox，拦得住；到第三个域就拦不住了。**

### 实测现状（`grep`，2026-08-29）

| 环节 | 实况 |
|---|---|
| `outbox_events` 表 | **已存在**，`database/baseline/0002_platform_foundation.sql`。真正的通用领域事件 outbox（`aggregate_type` / `aggregate_id` / `event_name` / `event_version` / `event_id` UNIQUE / `correlation_id` / `payload` jsonb / `occurred_at` / `published_at` / `retry_count` + `WHERE published_at IS NULL` 部分索引） |
| 事务性写入 | **已存在**，但只有 `assessment`，经其 `application/ports.py:77` 的 `write_audit_and_outbox` |
| `DomainEvent` 类型 | **0 命中** |
| `backend/platform/outbox/` | **不存在**（平台 6 模块里没有它） |
| relay / publisher / projector | **全部不存在**，`published_at` 永远 NULL |

### 三个要解决的问题

**① 一张平台级共享表没有平台级所有者。**
`outbox_events` 被一个**域的** repository 方法写入。按 `docs/04_domains/DOMAIN_ARCHITECTURE.md`
§5，跨域共享的技术机制属平台层（对照 `platform/audit` 就是这么做的）。
**下一个需要事件的域会照抄一份 `write_audit_and_outbox`**——这正是 R10 伤疤
「源仓库只有一份网关实现，却有三套接入模式；重复的不是实现，是纪律」的形状。

**② 事件契约无类型可执行。** `DOMAIN_ARCHITECTURE.md` §4.3 规定的四条
（过去时命名 / 与状态变更同事务 / 载荷是自包含不可变快照 + provenance，**不得只放 id
让订阅方回查** / 订阅方必须幂等）**目前没有任何类型或测试在执行**。
按 R14，它们现在只是意图。

**③ 没有 relay 的 outbox 是只写日志。** 它**看起来**像事件驱动架构而实际什么都没连上。
这是静默失效——比机制缺失更危险，因为它会让人误判进度
（我自己就先误判为「outbox 不存在」，后又差点误判为「事件驱动已就绪」）。

### 范围

1. 建 `backend/platform/outbox/`：`DomainEvent`（frozen，必带 `event_name` 过去时校验、
   `occurred_at`、`correlation_id`、`payload`、provenance）+ `OutboxPort`（写入）
   + `SqlAlchemyOutbox`（与 UoW 同事务）。**照 `backend/platform/audit/` 的既有形状做**，
   不要发明第二种风格。
2. `assessment` 的 `write_audit_and_outbox` 改为经平台 port；**保留其现有行为与测试全绿**
   （`tests/domains/assessment/test_transactional_outbox_invariant.py` 是既有验收，不得回归）。
3. relay：**本卡只做到「可被消费」，不做 projector**。最小形态 = 一个能把
   `published_at IS NULL` 的事件取出并标记已发布的函数 + 幂等重试。
   **投影层归 ADR-0010，不在本卡范围**（避免一张卡吃掉两个批次）。
4. 治理登记：`DOMAIN_REGISTRY.yaml` / `CAPABILITY_REGISTRY.yaml` 加
   `platform_outbox` 条目；`MIGRATION_MANIFEST.yaml` 相应登记。

### 验收

- 新增架构测试**并验证会咬人**：`backend/domains/**` 下不得出现直接写 `outbox_events`
  的路径（必须经平台 port）。植入违规 → 失败 → 移除，提交说明贴过程。
- `DomainEvent` 的过去时命名校验有测试（`"HypothesisConfirmed"` 通过，
  `"ConfirmHypothesis"` 抛错）。
- relay 的幂等性有测试（同一 `event_id` 重复投递不产生重复效果）。
- **完成后回来更新 ADR-0010 的「2026-08-29 状态修正」块**——那里记录的阻塞点会因本卡而改变。

---

## T-21 ｜ P1 ｜ 落地 ADR-0016：R8 白名单闸门 + 人辅助输入溯源

**动手前必读 ADR-0016 全文。** 本卡有一个会导致全域拒绝的实现陷阱，见下。

### ① 闸门从「默认过闸」改为「R8 白名单过闸」

只对 R8 七类动作（类诊断输出 / 家庭计划变更 / 教师推荐 / 服务购买 / 对外沟通 /
会员升级 / 涉未成年人的敏感动作）注册 `human_only=True`；其余动作不过闸。

> **⚠ 陷阱：`PolicyEngine` 是 fail-closed**（`policy.py:94-98` 未注册即 DENY）。
> 所以「不过闸」**必须显式注册为允许 AI actor 的规则**，不能靠「不写规则」实现。
> 不注册的后果不是放行，是**全域拒绝**。

**验收**：断言 R8 七类动作名**各有一条** `human_only=True` 规则，缺一即失败
（这条是分级判据唯一的机械执行者，缺它则 ADR-0016 §1 只是意图）；
并验证会咬人——删掉其中一条规则 → 测试失败 → 恢复。

### ② `AiProvenance` 增加 `human_assist` 字段

规格见 ADR-0016 §3。要点：`assisted_by` 必填且 `is_ai` 必须为 `False`；
`assist_ref` 指向记录不内联原文；`assist_kind` 当前只有 `"INPUT_HINT"`
（`"OUTPUT_REVIEW"` 属 L3，不由本字段表达）。

**必须同时满足**：`StructuredRequest` 把人类提示作为**独立标注的输入**携带，
**不得合并进 `payload`**——合并即混掉，事后无法区分人机贡献。

**为什么这条是 P1 而不是 P3**：不是功能需求，是**归因需求**。
若提示不可见于溯源，证据库会混有「AI 自己推出的判断」与「人告诉它这么说的判断」
且无法区分 → 「越用越准」度量到的是那批辅助者而非系统 →
**为规模化撤掉辅助者时性能下降且无法解释原因**。
ADR-0015 的中心命题是「护城河在证据积累」，而**分不清人机贡献的证据库积累的是无法归因的混合物**。
今天近乎零成本，将来永远补不回来。

### ③ 与 T-16 / T-20 的关系

- ② 触及 `backend/intelligence/model_gateway/contracts.py`，与 **T-16**（四处封印）同一文件。
  **建议合并为一个 PR**，避免同文件两次改动互相冲突。
- **T-20 的 `causation_id`** 与 ② 是同一类问题（因果链只能在发生当时记下）。
  两张卡可由同一人领取，但**不要合并**——outbox 属平台层，provenance 属 gateway，
  合并会让一个 PR 跨两个所有权边界。

### ④ 不在本卡范围（避免一张卡吃掉三个批次）

Handoff 机制本体、风险分级的**具体阈值**（ADR-0016 §Consequences 已注明需真实数据，
当前无数据，**边界情形一律上调一级处理**）、Intervention Library
（ADR-0015 §3 与 `AI_ARCHITECTURE.md` §3.3 的「不建目录 / 增量优先」纪律仍适用）。

---

## 已由总架构师完成（列出以免重复劳动）

- **ADR-0010 ~ ADR-0015 六份**：裁决了 `TARGET_ARCHITECTURE.md` §6 全部 5 项开放项
  + 采纳 Family Growth Intelligence OS 与价值层三条边界。
- **`tests/architecture/test_r9_value_layer_boundary.py`**：闭合一个**实测漏洞**——
  原判据（`test_compliance_constraints.py:140-146`）要求**字段名同时命中主体词与打分词**，
  因此 `emotional_value_score` 与 `class FamilyValueScore{emotional: float}` **都能完全通过**。
  新增两条判据（类名自身、类名×字段名）+ 一条防词表漂移断言。已验证会咬人（5 用例：2 植入咬、
  2 对照绿、1 豁免绿）。
- **CI**：删掉 Wave 0 遗留的 `find backend ... | grep -q .` 条件块，改为无条件 `uv run pytest -v`
  + 单独一步跑 `backend/domains/product_intelligence/tests`。此前 `tests/platform`(464 行)、
  `tests/domains`、`tests/apps`、`tests/intelligence` **从未在 CI 中运行过**。
  **R14 仍未满足**：远端仓库未创建（计划 `PoCP-Protocol/AiFamily`），需 project-owner 批准。
- **`docs/05_ai/AI_PLATFORM_FORWARD_ARCHITECTURE.md`**：前瞻架构目标态，
  `status: draft` / `canonical: false`，六项成熟度全部如实记为 `ABSENT`/`PARTIAL`。

## 总架构师发现但未修（属他人范围，按 AGENTS.md 报告不擅改）

| 问题 | 位置 | 归属 |
|---|---|---|
| `mark_primary()` 引用 `'APPROVED'` 但签名无人类 actor，**R9 晋升检查当前为红** | `product_intelligence/domain/entities.py:309` | T-06 / PR-003 |
| `test_capability_registry` 的两条路径存在性检查**当前为红**（registry 与磁盘漂移） | `governance/CAPABILITY_REGISTRY.yaml` | 施工中会话 |
| `design_copilot/__pycache__/*.pyc` **已入仓**，R11 明文禁止 | — | 可顺手清 + 补 `.gitignore` |
| `CLAUDE.md:32` 与 `AGENTS.md:38` 称 `CAPABILITY_REGISTRY.yaml` 尚未建立，**它已存在且 318 行** | 两份入口文档 | 文档漂移 |
| `DOCUMENTATION_MAP.md` 称 `00_system/` 有 4 个文件，**磁盘上 8 个** | `docs/00_system/` | T-10 |

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
