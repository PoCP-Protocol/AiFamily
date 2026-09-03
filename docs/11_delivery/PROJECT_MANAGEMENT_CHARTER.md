---
id: DELIVERY-PM-CHARTER-001
title: AiFamily 项目管理章程（团队、场景、环境、节奏）
type: delivery
status: current
version: 1.0
owner: project-manager
created: 2026-08-29
updated: 2026-08-29
canonical: true
supersedes: null
superseded_by: null
---

# AiFamily 项目管理章程

> 本文件定义**怎么管**，不定义做什么（做什么见 `TASK_BACKLOG.md` 与
> `FUNCTIONAL_DECOMPOSITION.md`）。它存在的原因是此前的管理是临时派活式的：
> 有任务就派、派完就忘、不验证、不复盘。下面第 0 节如实记录那些失职，因为
> 章程若不写清它要防什么，就只是又一份没人执行的文档。

## 0. 已发生的管理失职（证据在，不美化）

| # | 失职 | 证据 | 本章程的对应机制 |
|---|---|---|---|
| 1 | **远端 CI 三次全红，我一次没看过** | `gh run list` 显示 33244397013 / 33244790062 / 33244977302 全 failure，因 398 个 ruff 错误。我每次推完就报告"已推送"，从不验证 | §5 交付门：推送后必须核 CI |
| 2 | T-01 把 ruff 清到 0，之后累积回 398 无人看管 | 同上。质量债无归属人 | §2 质量守护者角色 |
| 3 | T-14 建立后 pending 十余轮从未派发 | 任务看板与实际派发脱节 | §5 每轮必须对齐看板 |
| 4 | 三次请求裁决 GROWTH 四页，却从未读过其迁入后代码 | `GROWTH_SCREENS_DISPOSITION_PROPOSAL.md` §5 | §4 决策必须先自证据闭环 |
| 5 | 我亲自手改测试、追断言、还引入 null 字节自伤 | commit 8214f28 提交信息 | §2 我不写实现代码 |
| 6 | 按 agent 汇报标完成，事后才发现 auth 端点被丢、registry 被覆盖两次、两个域被误删 | commit 9101f9e / MIGRATION_MANIFEST 的 registration_note | §5 验证优先于采信 |
| 7 | 诊断停在表面症状（把 404 说成 item_ref 校验） | commit 45944ed 提交信息 | §5 派任务时给症状不给结论 |

## 1. 项目经理的职责边界

**做**：守计划与批次顺序、定义场景与验收标准、组建团队与分工、派任务、**验证**交付、逼决策闭环、发现偏离立即止损、阶段性复盘。

**不做**：写业务代码、改测试断言、手工调 lint、debug 具体报错。

**唯一例外**：跨切治理文件（`governance/*.yaml`、章程类文档）由我维护，因为它们是协调的载体而非实现产物。

## 2. Agent 项目团队与角色分工

九个常设角色。**角色是稳定的，任务是流动的**——派任务时指明角色，让 agent 带着该角色的约束与必读清单工作，而不是每次从零交代上下文。

| 角色 | 职责 | 战场（只改这些） | 必读 |
|---|---|---|---|
| **BA 业务分析** | 从战略/PPT/UI 反推场景与验收标准；维护场景库 | `docs/02_business/` `docs/03_product/` | 战略白皮书、新商业模式PPT、COMMERCIAL_VALUE_STRATEGY、FUNCTIONAL_DECOMPOSITION |
| **DOM 领域建模** | 业务域的四层实现（entities/policies/commands/repository） | `backend/domains/<域>/` + 对应 tests | ENGINEERING_ARCHITECTURE、membership 域（范本）、R2/R4/R12 |
| **PLT 平台内核** | identity/authorization/consent/audit/idempotency/persistence | `backend/platform/` + `tests/platform/` | `docs/06_platform/` 全部、R6/R9 |
| **AIR AI Runtime** | model_gateway、Context、Agent、Prompt、Eval | `backend/intelligence/` + 对应 tests | AI_NATIVE_PRINCIPLES、AI_ARCHITECTURE、R7/R9/R10、13_research 的 4a-4e |
| **DAT 数据与迁移** | Alembic、schema、ORM/迁移一致性 | `database/` `alembic.ini` + `tests/database/` | DATA_ARCHITECTURE、LINEARISATION_MAP、T-03 报告 |
| **API 契约对接** | 端点契约、前端对齐、OpenAPI | `contracts/` `backend/apps/family_api/` | UI_API_ENDPOINT_INVENTORY、DEV_SYNTHETIC_FIELD_ANALYSIS |
| **QA 质量守护** | **CI 必须绿**、lint 归零、测试策略、咬人验证抽查 | `tests/architecture/` `.github/workflows/` `pyproject.toml` | R14、ADR-0009、全部架构测试 |
| **CMP 合规** | 法定约束转检查器、DPIA、留存、未成年人红线 | `tests/architecture/test_compliance_constraints.py` `docs/12_governance/` | COMPLIANCE_HARD_CONSTRAINTS、ADR-0006 |
| **GOV 治理** | registry 与磁盘一致、文档 front matter、traceability | `governance/` `docs/00_system/` `tools/architecture/` | REPOSITORY_CONSTITUTION、DOCUMENT_GOVERNANCE |

**跨角色纪律**（写进每个任务卡）：
- 只改自己战场的文件；发现他人文件有问题 → 报告，不擅自改
- 提交带 pathspec，禁止 `git add -A`
- 治理 YAML 是争用热点，改前先重读最新状态
- 新增检查器必须验证会咬人并贴实际输出
- 交付时贴**实际命令输出**，不接受"应该可以了"

## 3. 场景驱动的任务拆解

**替代此前的技术分层拆解。** 技术分层（先建平台、再建域、再接前端）的问题是：每层都"完成"了，但没有一个用户能走通一件事。场景驱动保证每个交付单元都是一条**用户能走完的路**。

### 场景来源
`BUSINESS_SCENARIOS_AND_PROCESSES.md` 的七阶段用户路径（触发→觉醒→行动→改变→长期→传播）× 六类业务闭环。

### 场景定义模板
每个场景必须写清：**谁**在**什么处境**下，做**什么**，看到**什么**，系统**记住什么**，以及**验收怎么判**。

### 首批场景（按依赖排序，非按域完整性）

| 编号 | 场景 | 跨越的闭环 | 依赖 | 状态 |
|---|---|---|---|---|
| **S-01** | 家长发现孩子沉迷手机 → 完成测评 → 看到假设解读 → 确认一个成长意图 | ASSESSMENT | 无 | **dev 环境已跑通**（5 HTTP 测试绿） |
| **S-02** | 家长带着已确认的意图 → 浏览专家服务 → 查看时段 → 提交预约 → 收到确认 | SERVICE | S-01 的 GrowthIntent | dev 已跑通（72 测试绿） |
| **S-03** | 家长获得 21 天计划 → 每日看到今日任务 → 打卡 → 看到过程回顾 | PLAN | S-01 | **未开工**（10 端点全无） |
| **S-04** | 家庭建档：创建家庭 → 添加家长/孩子 → 建立关系 → 授予同意 | FAMILY CORE | 无（但 S-01/02/03 都在假装已有家庭） | **未开工** |
| **S-05** | 家长在过程回顾里看到自己做过的事（非评分、非排名） | GROWTH | S-03 | 待批 `GROWTH_SCREENS_DISPOSITION_PROPOSAL` |

**S-04 的位置值得注意**：它逻辑上最靠前，但 S-01/S-02 已经在 dev 环境跑通了——靠 `dev_wiring` 合成家庭。这是**技术债而非能力**：真实家庭建档不存在，所有场景都建在一个假的家庭上。S-04 必须在进入测试环境之前完成，否则测试环境验证的是虚构数据上的行为。

## 4. 决策纪律

**我可以自行拍板的**：批次顺序、任务优先级、冻结与解冻（条件已明文时）、技术方案在既有 ADR 范围内的选择、测试数据与契约不匹配的处置。

**必须上呈 project-owner 的**（且必须带**我的建议方案**，不是开放式提问）：
- 推翻既有 ADR 或宪章条款
- 商业模式与产品边界（如 GROWTH 四页去向、loyalty_points 是否存在）
- 需法务/商务介入的（LLM 供应商"不得转委托"）
- 引入新技术栈依赖

**上呈前必须完成的自证据闭环**：先读代码/跑命令确认事实，再给建议。失职 #4 就是跳过这一步的后果。

## 5. 检查与纠偏节奏

### 每轮（每次我发言）必做四件事
1. **对齐任务看板** —— 不允许出现"某任务 pending 十余轮无人管"
2. **核实仓库状态** —— `uv run pytest -q` 与 `uv run ruff check .`
3. **核实远端 CI** —— `gh run list --limit 3`，红了必须处置或明确归属
4. **验证 agent 交付** —— 抽查其声称（尤其"咬人验证"），不采信汇报

### 交付门（Definition of Done，三层）
| 层级 | 标准 |
|---|---|
| **任务级** | 本地测试绿 + 该范围 lint 干净 + 咬人验证有实际输出 + registry 同步 |
| **场景级** | 该场景的端到端路径在 dev 环境可跑通 + 有 HTTP 层验收测试 |
| **环境级** | 见 §6 |

### 阶段性复盘
每完成一个场景或一个环境阶段，产出一份复盘，必须包含：**做对了什么 / 哪里偏离了计划 / 发现的真实缺陷 / 下阶段前置条件**。此前没有任何复盘，导致同类问题重复发生（registry 被覆盖两次、容器 `__init__.py` 踩两次）。

## 6. 三环境推进路线

**顺序不可跳过。** 每个环境有明确的进入条件与退出条件。

### 阶段一：开发环境（当前所在）

**目标**：单进程内业务链路可跑通，数据可以是合成的，但**行为必须是真实的**。

| 退出条件 | 当前状态 |
|---|---|
| CI 远端绿 | ❌ **三次全红**（398 ruff 错误） |
| 全量测试本地绿 | ⚠️ 当前 6 collection error（T-14 在途） |
| S-01 / S-02 dev 可跑通 | ✅ |
| S-04 家庭建档真实存在 | ❌ 未开工，所有场景建在合成家庭上 |
| 平台内核四缺陷修复 | 🔄 T-14 在途 |
| `docs/06_platform/` 与代码一致 | ⚠️ T-14 修完需同步 |

### 阶段二：测试环境

**进入条件**：阶段一全部退出条件满足。

**目标**：真实 Postgres、真实迁移、无 `dev_wiring`，用受控测试数据验证。

| 退出条件 |
|---|
| `alembic upgrade head` 后所有域的仓储测试通过（当前仅 membership/product_intelligence 有 Postgres 测试） |
| **移除 dev_wiring 依赖**：真实 identity（auth_identity 域）+ 真实 consent 存储 |
| ORM/迁移一致性检查覆盖所有域（当前仅 service 域有 `test_orm_matches_migrations`） |
| 前端 mobile 能连上后端跑通 S-01/S-02（当前 46 端点仅 11 实现） |
| 合规检查器覆盖读取留痕的业务路径（当前只有结构性检查） |

### 阶段三：生产环境

**进入条件**：阶段二全部退出条件满足 **且** 以下三项获 project-owner 批准：

1. **未成年人商业场景合规实现与批准**（FREEZE-001 已撤销；Batch 6 可用 sandbox/fake 完整建设，生产上线前仍须完成适用的权限、拒绝/非画像选项与消费限制验收）
2. **LLM 供应商"不得转委托"结论**（需法务；当前所有 provider `sub_delegates=None`，网关一律拒绝）
3. **DPIA 完成并留存**（PIPL 第55/56条，报告须留存 ≥3 年）

**生产环境的额外退出条件**：年度合规审计机制、读取访问留痕的真实业务路径覆盖、向量存储的按 subject 级联删除（若届时已有 Family Context）。

## 7. 本章程的执行状态

诚实标注：本章程的机制大部分**尚无机械执行**。§5 的四件事靠我自觉，§6 的环境门靠人判断。

按 R14 的立场，这意味着它现在只是意图。使其成为护栏的路径：
- §5 第3条（核 CI）可立即机械化 —— 已列入 QA 角色首个任务
- §6 环境门可做成 checklist 脚本
- 阶段性复盘无法机械化，只能靠纪律

**若发现我违反本章程，请直接指出**——失职清单第 1 条（CI 三次全红没看）正是你指出后我才去查的。
