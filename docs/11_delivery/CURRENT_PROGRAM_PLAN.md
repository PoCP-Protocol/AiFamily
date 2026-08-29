# 当前 Wave 计划 (Current Program Plan)

- **状态**: CURRENT — 依据 `governance/REPOSITORY_CONSTITUTION.md` R13，本文件是本主题唯一当前真相
- **生效**: 2026-08-29 (AIFAMILY-000)

---

## 警示（优先于以下所有内容阅读）

**下一 Wave 默认不自动开始，需人工批准。**

**且 `docs_current_baseline_CONTRADICTION` 待裁决前不得假设本计划是唯一进行中的迁移工作。**

源仓库 `50_开发_dev` 下同时存在三份互不引用、各自自称"当前基线"的文档（`CURRENT_SPRINT.md`、`governance/PROGRAM_STATUS_PLATFORM_V1.md`、`architecture/FAMILY_PLATFORM_V3_BLUEPRINT.md`），且源仓库自己已有一份 `architecture/FAMILY_AI_PYTHON_ONLY_MIGRATION_PLAN_V1.md`（2026-08-28），`CURRENT_SPRINT.md` 记录了 7 条项目所有者 Override 正按它推进 Batch 1-6。本计划（AiFamily/AIFAMILY-000 起）与该计划是同一决定被重复下达、还是两个并行/冲突的方案，**尚未裁决**。详见 `governance/MIGRATION_MANIFEST.yaml` 的 `docs_current_baseline_CONTRADICTION` 条目（`review_required_index` 首位，最高优先级）。

在此裁决完成前，本文件登记的 Wave 序列是**一份计划**，不是"唯一在推进的迁移工作"的宣称。

---

## Wave 序列

### Wave 0 — AIFAMILY-000（当前，已完成大部分）

**内容**：治理 + 审计。对源仓库 `family-ai`（baseline commit `1ff168123d147f4d6a6eaaa677bc2f80986233d9`）做七维资产审计，产出：

- `governance/REPOSITORY_CONSTITUTION.md`（十四条规则）
- `governance/MIGRATION_MANIFEST.yaml`（逐能力 disposition 判定）
- `governance/DOMAIN_REGISTRY.yaml`（唯一实现位置登记表）
- `docs/00_foundation/CURRENT_*.md`（本系列文档）
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
