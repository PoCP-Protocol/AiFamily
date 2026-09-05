---
id: DELIVERY-ROSTER-001
title: AiFamily Agent 团队花名册
type: delivery
status: current
version: 1.1
owner: project-manager
created: 2026-08-29
updated: 2026-08-30
canonical: true
supersedes: null
superseded_by: null
---

# Agent 团队花名册

> 编号是为了**可追责与可追踪**。此前派活不编号，导致三个后果：
> 同一 agent 的历史无法串联、失败无法归属、我自己都记不清谁在改什么。
>
> 规则：**编号绑角色，不绑单次任务。** 同一角色的后续派活复用同一编号，
> 便于查"这个角色历史上交付过什么、踩过什么坑"。

## 1. 编号规则

```text
A<角色码>-<序号>
```

- 角色码见 `PROJECT_MANAGEMENT_CHARTER.md` §2（BA/DOM/PLT/AIR/DAT/API/QA/CMP/GOV）
- 序号在同一角色内递增。同角色可并行多实例（如 `ADOM-1` 做 service 域、`ADOM-2` 做 family 域），但**战场必须互不重叠**
- 编号一旦分配**永不复用**，即使该实例已完成或失败

## 2. 在役 Agent

| 编号 | 角色 | 当前任务 | 战场 | 状态 |
|---|---|---|---|---|
| **APLT-1** | 平台内核 | T-14 修复平台内核四缺陷 | `backend/platform/` `tests/platform/` | 🔄 在途 |
| **AGOV-1** | 治理 | 移植 vs 自研分类台账 | `docs/11_delivery/PORT_VS_BUILD_LEDGER.md` | 🔄 在途 |
| **AQA-1** | 质量守护 | 修 CI 红（398 ruff）+ 建防复发机制 | `.github/workflows/` `pyproject.toml` + lint 清理 | 🔄 在途 |
| **PMA-1** | 项目助理 | 持续进度/质量检查、五层架构对齐、外部审查整合、纠偏与发布闸门 | `docs/11_delivery/MANUS_REVIEW_INTEGRATION_V1.md`、`PROJECT_ASSISTANT_CHARTER_V1.md` | 🔄 常驻 |

### 7.1 Sprint 2 并行派工（2026-08-30）

| 编号 | 角色 | 当前任务 | 独占战场 | 状态 |
|---|---|---|---|---|
| **ADOM-3** | 领域建模 | FGCN P0 持久化与终态不变量 | `backend/domains/service/fgcn/`、对应测试、P0 migration | ✅ 已交付（迁移待验） |
| **AAIR-3** | AI Runtime | Context Broker 最小只读投影 | `backend/intelligence/context_engine/` 及对应测试 | ✅ 已交付 |
| **AAIR-4** | AI Runtime | Principal 接入 Context Broker 只读投影 | `backend/intelligence/principal/runtime.py`、上下文集成测试 | ✅ 已交付 |
| **AFE-2** | 体验工程 | 四端 capability adapter contracts | `frontend/mobile/lib/platform-capabilities/`、专项测试 | ✅ 已交付（原生桥接待实现） |
| **ARCH-1** | 总设计/集成 | 阶段复盘、闸门复测、治理登记与推送 | `docs/11_delivery/`、集成检查 | 🔄 在途 |

### 7.2 Sprint 2.1 微迭代派工（2026-08-30）

| 编号 | 角色 | 当前任务 | 独占战场 | 状态 |
|---|---|---|---|---|
| **ADOM-4** | 领域建模 | FGCN 进度/贡献只读投影 | 新增 `backend/domains/service/fgcn/read_model.py` 及专项测试 | 🔄 在途 |
| **AAIR-5** | AI Runtime | Context 删除 Worker 契约 | 新增 `backend/intelligence/context_engine/deletion.py` 及专项测试 | 🔄 在途 |
| **AFE-3** | 体验工程 | 跨端能力健康 ViewModel | 新增 `frontend/mobile/lib/platform-capabilities/health-view-model.ts` 及专项测试 | 🔄 在途 |
| **ARCH-1** | 总设计/集成 | migration/ORM/环境闸门验证 | 测试数据库与 `docs/11_delivery/` | 🔄 在途 |

## 3. 已完成 Agent 履历

按角色归档，便于查该角色的历史交付与教训。

### PMA-1 反向审查驱动的当前状态（2026-08-30）

| 任务 | 状态 | 证据/阻断 |
|---|---|---|
| AFE-4 语义服务体验 | `PARTIAL` | 专项 5 tests + `pnpm check` 通过；全量移动端仍 5 failures，其他基线页面仍需语义编号扫描 |
| ADOM-5 / DB-01 migration acceptance | `PARTIAL` | baseline/0008 分层 3 passed、FGCN chain 2 passed；未登记 0009/0010 使 head 漂移，unknown head 必须阻断 |
| AAIR-6 durable deletion boundary | `CONTRACTED` | context-engine 18 passed；InMemory adapter 明确非生产，缺 Postgres/outbox/真实 projection |
| APLT-2 SEC-01 production dev auth gate | `PARTIAL` | production route 不再广告或可调用 `/auth/account-session`；ENV-01 默认 development、真实 auth 替代和环境同构仍是 P0 |
| PMA-1 project assistant | `ACTIVE` | 每次交付独立读取 diff/测试/架构链并向 owner 发返工意见；发布结论当前 `NO-GO` |

### DAT 数据与迁移
| 编号 | 任务 | 交付 | 值得记住的 |
|---|---|---|---|
| **ADAT-1** | T-03 Alembic baseline + Postgres | 62 个 SQL 线性化、baseline revision、docker-compose、Postgres 门控测试 | ① 纠正了我"58个文件"的口径错误（实为62，58是最大编号）② 用实测**推翻**了我"死列"的判断（旧列 NOT NULL 无 DEFAULT，是双写冗余）③ 发现 `product_intelligence` 私藏 SQL 比 baseline 多三列，测试因自建 schema 而未暴露 |

### DOM 领域建模
| 编号 | 任务 | 交付 | 值得记住的 |
|---|---|---|---|
| **ADOM-1** | T-15 SERVICE 预约子链（重派） | 18 文件、72 测试、6 端点、Alembic revision | ① 建了本仓库**第一个 ORM/迁移漂移检查**（`test_orm_matches_migrations`）② ConsentGate 检查置于任何供给读取**之前**——被拒的预约不留痕迹 ③ 13 条拒绝路径逐条断言错误码而非只断言抛异常 |
| **ADOM-0** | T-15 首次尝试 | 仅 domain 层部分文件，**卡死** | 只写到 `policies`/`value_objects`，缺 `entities.py`。教训：任务卡应要求"先打通最小闭环再扩展" |

### PLT 平台内核
| 编号 | 任务 | 交付 | 值得记住的 |
|---|---|---|---|
| **APLT-0** | Wave 1 平台内核骨架 | 六项内核 + FastAPI 入口，49 测试 | 发现并主动上报"容器目录加 `__init__.py` 会触发 R3 失败"这个坑，写进了 CLAUDE.md |
| **APLT-2** | T-11 审计持久化（R6 失守） | `store.py`、19 测试、Postgres WORM trigger 门控测试 | 连接中断未能汇报，但**工作实际完成**。教训：agent 无汇报 ≠ 无交付，必须核实磁盘 |
| **APLT-3** | T-12 授权 R9 绕过 | deny-overrides、14 测试（原 5） | ① 咬人验证做得最好：还原旧实现后 4 个测试失败并贴了实录 ② 发现 membership 域此前只是**恰好安全**（没人注册重复 key），修后变为结构性保证 |

### AIR AI Runtime
| 编号 | 任务 | 交付 | 值得记住的 |
|---|---|---|---|
| **AAIR-1** | T-06 Model Gateway | 8 模块、106 测试、4 个隔离检查器 | ① `sub_delegates` 三态设计：`None`（未确立）与 `True` **等价禁止**——"还没问厂商"在第16条下不是抗辩 ② 结果是 shipped registry **零个外部供应商可调用**，这是诚实的治理状态而非占位 ③ 主动**收窄**了自己的红线：查文档确认规则原文是禁 repository 而非 entity，全面禁会奖励重复定义（反 R2） |

### CMP 合规
| 编号 | 任务 | 交付 | 值得记住的 |
|---|---|---|---|
| **ACMP-1** | T-07 合规执行机制 | AuditEvent 的 MUTATION/READ 判别式、第36条四要素、DPIA 与留存两份设计 | ① `subject_is_minor=True` 时 `approval_ref` **必填**——审批要求成为构造期不变量，"记录了但没审批"写不下来 ② DPIA 绑定"处理活动"而非代码提交：第55条最典型触发是**用途扩展**，那不产生任何代码变更 ③ 主动**拒绝**写"必要性论证长度>50字符"这类自欺测试 |

### GOV 治理
| 编号 | 任务 | 交付 | 值得记住的 |
|---|---|---|---|
| **AGOV-0** | T-08 Traceability 检查器 | `check_traceability.py`、断链 55→24、8 测试 | ① 选"加显式 `business_capability` 字段"而非从 domain 推导——推导出的归属是同义反复，**永远不会断链也就永远证明不了任何事** ② 路由提取用 AST 静态扫描而非 import app，因为**未挂载的 router 恰是要猎的孤儿** ③ 主动建议 CODE_GAP 永久保持报告态，硬门会逼人写假条目 |
| **AGOV-2** | Registry 漂移修复 + 6 份 ADR | DOMAIN_REGISTRY 22→27 条、ADR-0001~0006 | 刻意**不给 membership 标 TESTED** 尽管 6 测试全绿，因 guardrail 未覆盖 |

### QA 质量守护
| 编号 | 任务 | 交付 | 值得记住的 |
|---|---|---|---|
| **AQA-0** | T-01 清理 388 ruff | 388→0，零 noqa，未改 pyproject | ① 自己写 AST 比对脚本验证 `ruff format` 没偷改语义 ② 主动升报"混合格式化态是三态里最差"，拒绝自行决定是否固化——直接催生了 ADR-0009 |
| **AQA-2** | T-17 assessment 链路测试适配 | 5 测试全绿，464 passed | **纠正了我的诊断**：真实失败不是 item_ref 校验（`item-1` 本就在题库里），而是链路第三步 404——测试请求的 POST 端点不存在，hypothesis 是 GET 投影 |

### BA 业务分析
| 编号 | 任务 | 交付 | 值得记住的 |
|---|---|---|---|
| **ABA-1** | 商业/业务/AI 架构文档 | 3 份架构文档 | 指出 GROWTH 闭环的真实张力：商业增长设计想要的成果展示，恰是宪章第一条红线主动禁止的 |
| **ABA-2** | 四级功能分解书（超时零产出） | 无 | 教训：文档类大任务易超时，应拆小或我自己写 |

### API 契约
| 编号 | 任务 | 交付 | 值得记住的 |
|---|---|---|---|
| **AAPI-1** | T-04a 端点清单 | 46 端点、11 已实现（23.9%） | 发现 `/orchestration/test-loop/*` 一个路径段承载 COMMERCE+SERVICE 全部 9 端点，疑触 R5 |
| **AAPI-2** | T-04b `/dev/*` 字段拆解 | 字段级真需求判定 | **消解了两难**：实测前端手写窄化 TS 接口，24 张硬编码卡片**一个字段都没被消费**（死负载），后端根本不需要移植 |

## 4. 失败与教训台账

| 编号 | 失败形态 | 根因 | 已采取的对策 |
|---|---|---|---|
| ADOM-0 | 卡死在 domain 层 | 任务范围过大、未要求增量验证 | 重派时加"先打通最小闭环再扩展"约束 |
| ABA-2 | 流超时零产出 | 文档类任务上下文消耗大 | 拆小；或由我直接写 |
| AAPI-0 | 流超时零产出（T-04 首次） | 一个任务塞了端点提取+字段拆解+状态核对三件事 | 拆成 T-04a / T-04b |
| APLT-2 | 连接中断无汇报 | 环境问题 | **核实磁盘而非依赖汇报** |
| AAIR-0 | 战略解读任务超时 | 同 ABA-2 | 未重派，改由我直接读 |

## 5. 派活时必须给 Agent 的东西

从上表教训反推出的清单：

1. **编号与角色** —— 让它知道自己的战场边界
2. **必读清单**（3-8 份，按顺序） —— 不给它自由探索
3. **战场范围**（只改哪些路径） —— 并发安全的前提
4. **给症状不给结论** —— AQA-2 与 ADAT-1 都纠正了我的诊断，我的结论会误导它
5. **咬人验证要求**（若涉及检查器） —— 并要求贴实际输出
6. **本仓库特有的坑** —— 容器 `__init__.py`、反斜杠字面量、Bash 禁用 cp
7. **并发警告** —— 谁在改什么、提交带 pathspec
8. **验收标准要贴实际命令输出** —— 不接受"应该可以了"

## 6. 我对 Agent 交付的验证义务

**不采信汇报，验证声明。** 已发生的教训：

- APLT-2 说"未能汇报"，实际交付完整 → 必须查磁盘
- 某会话声称 assessment 有 `AssessmentSession` 实体，实测**不存在** → 必须查文件
- 某会话把 registry 里我的登记**覆盖两次** → 必须重读治理文件
- 两个已提交的域被删除且无二次确认记录 → 必须核 git 状态

## 7. Sprint 1 并行派工（2026-08-30）

本轮由 Lead/ARCH-1 统筹，三个 Agent 使用互斥战场并行开发；跨战场需求只通过交付说明
回传，不直接改动他人目录。

| 角色 | Sprint 1 任务 | 独占战场 | 交付门 |
|---|---|---|---|
| AAIR-2 | Principal AI + 知识库运行时纵向切片 | `backend/intelligence/principal/`、`backend/intelligence/knowledge/` 及对应测试/架构文档 | model gateway、知识检索、memory/experience 草案边界；AI 不直写事实 |
| ADOM-2 | Family Need N1→N2 与资源匹配 | `backend/domains/family_need/` 及对应测试 | solution/service draft、幂等、同意、租户/主体隔离、资源缺口 |
| AFE-1 | 服务/产品发现与行动体验 | `frontend/mobile/app/services/`、`frontend/mobile/app/catalog/` 及新增专项测试 | 情绪价值优先、多模态、暂停/拒绝/错误状态、无排名 |
| Lead/ARCH-1 | 集成、治理、环境 parity 与发布评审 | `docs/11_delivery/`、集成测试与验收脚本 | 架构链路可追踪；dev/test/prod 功能同构；全量测试结果真实登记 |

每个交付必须带：变更文件清单、成功/拒绝/重放/删除测试、定向 Ruff/pytest 或 Vitest
输出，以及未完成项。未满足任一层时只能标记 `PARTIAL`，不得宣称平台能力已完成。

验证方式写进章程 §5：每轮核 `pytest` / `ruff` / `gh run list` / 抽查咬人验证。
