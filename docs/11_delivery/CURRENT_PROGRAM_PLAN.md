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
- 当前总控分支本轮实测：文档真相专项 `4 passed`；全架构 `109 passed / 1 skipped / 1 failed`，唯一失败为并发 WIP 造成的 Ruff debt ratchet，不能抬高基线掩盖。
- 任何“完成”必须提交文件清单、实际命令输出、提交 SHA、未解决阻断和 ownership 说明；Fake 只替换外部依赖，不替换业务规则。

退出条件：每个 P0-P6 任务都能找到唯一 owner、非重叠文件范围、依赖关系和反向验收人；共享 WIP、真实 PostgreSQL、远端 CI 或治理登记未完成的部分保持 `OPEN`。

### P0 任务队列：先让家庭需求链真实可调用

| 任务 | 内容 | 文件边界 | 反向验收 |
|---|---|---|---|
| P0.1 | `GrowthIntent → Onboarding` Domain/Application/Fake/Postgres | 仅当前 Journey owner 已确认的新 onboarding 文件及对应专项测试 | 未确认 intent、AI actor、跨 tenant/family、无/撤回/过期 Consent、重复请求、审计/outbox 失败回滚 |
| P0.2 | Consent 与 tenant-family binding 语义等价 | Platform/Data owner 明确的 Consent adapter、测试和必要 migration；不擅改 baseline schema | Fake 与 Postgres 都拒绝无效窗口、撤回、跨租户和失效 binding；禁止只按 family/subject 查询 |
| P0.3 | tenant-scoped idempotency 与 canonical AuditEvent | Platform/Data owner 明确的 persistence/audit 接线和专项测试 | 同 key 跨 tenant 不相互污染；Audit 必含 actor/tenant/action/resource/reason/correlation/before/after；失败整体回滚 |
| P0.4 | family_api 正式挂载与 PostgreSQL E2E | API owner 的 `main.py`/wiring/HTTP 测试范围；Journey owner 不越界修改 | 从实际 composition root 走成功、503/拒绝、幂等、回读和重启；不能用孤立 route 或 dev 后门代替 |
| P0.5 | `0016` migration 生产形状审查 | migration owner 的 revision、升级/降级/含数据冲突测试与登记请求 | 空库升级、含数据升级、回滚、重启、重复约束和真实 PG 证据；未登记不晋升 |

P0 任一任务没有真实 PostgreSQL 或 HTTP 证据，Sprint 保持 `NOT_DONE`；FamilyNeed 与 Assessment 各自测试通过不能替代 GrowthIntent→Onboarding 的端到端证据。

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
