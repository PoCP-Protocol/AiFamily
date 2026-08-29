---
id: BIZ-CAPMAP-001
title: 业务能力地图
type: business
status: current
version: 1.0
owner: chief-architect
created: 2026-08-29
updated: 2026-08-29
canonical: true
supersedes: null
superseded_by: null
---

# 业务能力地图 (Business Capability Map)

- **状态**: 见上方 front matter `status: current` — 依据 `governance/REPOSITORY_CONSTITUTION.md` R13，本文件是本主题唯一当前真相
- **生效**: 2026-08-29 (AIFAMILY-000, Wave 0 结束时快照)

---

## 0. 范围声明

本文件只描述**经审计确认存在、且被 `governance/MIGRATION_MANIFEST.yaml` 批准为 MIGRATE 或 REIMPLEMENT（或标记为 REVIEW_REQUIRED 待裁决）的业务能力**。不描述任何"未来宏大架构"设想。Wave 0 (AIFAMILY-000) 结束时，AiFamily 仓库不包含任何业务代码——本文件是对现状与迁移判定的登记，不是实现说明。

判定来源统一为 `governance/MIGRATION_MANIFEST.yaml`；具体登记行见 `governance/DOMAIN_REGISTRY.yaml`。

---

## 1. 唯一被批准 REIMPLEMENT 的业务域：family_core

`family_core` 是当前唯一一个被判定为 **REIMPLEMENT** 的核心业务域（`MIGRATION_MANIFEST.yaml` 条目 `family_core`，目标路径 `backend/domains/family`）。

- 源：`50_开发_dev/apps/api/src/modules/family/family.service.ts`（2293 行，全仓库最大服务文件，真实 Postgres 持久化：`families`/`persons`/`consents`，60+ 路由，e2e/integration/spec 全覆盖）。
- 行为规格来源：`family-core-integration.e2e-spec.ts`（M1-E2E-01：family→parent→child→relationship→lifestage→consent 全链路）。
- REIMPLEMENT 而非 MIGRATE 的原因：源实现是 TypeScript/NestJS，而 R1（唯一后端真相）判定正式后端只能是 Python/FastAPI，因此行为规格保留、代码必须重译。

需同时处理的关联风险：`family_dev_surface_services`（`dev-platform-surfaces.service.ts` / `dev-core-growth.service.ts`）被判定为 **ARCHIVE / NOT_MIGRATING_AS_BUSINESS_CODE**——这两个服务自述 `data_source: 'SYNTHETIC_DEV_ONLY'`、`model_gateway: 'NOOP_NOT_INVOKED'`，本质是 24 张硬编码 UI 卡片，却挂在生产路由 `/:familyId/dev/*` 上，并被移动端 9+ 个真实屏幕（UI-10/11/12/22/23/25/27/28/29）消费。Wave 3 重建 family_core 时必须显式决定这些 UI 屏幕的数据来源，否则移动端切换后端后会出现空白页。

## 2. 唯一 MIGRATE 候选的 Python 域：product_intelligence（待补测试）

`product_intelligence` 是五个 Python 领域中**唯一有测试**的域，判定为 **MIGRATE**，状态 `APPROVED_PENDING_REVIEW`（`MIGRATION_MANIFEST.yaml` 条目 `product_intelligence`，目标 `backend/domains/product_intelligence`）。

- 源：`50_开发_dev/backend/domains/product_intelligence`，21 文件 / 1492 行，domain/application/infrastructure/api/tests 五层俱全。
- 实测缺陷（纠偏原计划的"已具备生产条件"结论）：
  - `api/routes.py` 自述未挂载到任何应用；
  - 无 Postgres 集成测试，只有 SQLite；
  - commit `2f9f6a1` 自称 V0.1；
  - `test_hypothesis_validation_guardrail.py` 含真实 TEST_ORACLE：AI actor 不能验证 hypothesis。
- 结论：仍判定为 MIGRATE，但**需补测试与挂载才算完成**，不是可直接搬运的成品。

## 3. membership 待裁决：REVIEW_REQUIRED

`membership` 是五个 Python 领域中代码量最大的（2627 行），`domain/policies.py` 含真实不变量（如 `assert_tier_transition_legal`），但判定为 **REVIEW_REQUIRED**，状态 `BLOCKED`（`MIGRATION_MANIFEST.yaml` 条目 `membership`）。

- 关键矛盾：`sqlalchemy_repository.py:8-9` 的 docstring 声称测试用 `tests/conftest.py` 在内存 SQLite 上跑，但该 `tests/` 目录在磁盘上**根本不存在**——文档与代码矛盾。
- `policies.py:24-28` 的 `FORBIDDEN_TIER_FIELD_TOKENS`（禁止 score/rank/level 字段）注释自称"由 guardrail test 强制"，该测试同样不存在。
- 阻塞动作（`blocking_action`）：**必须先写出 `FORBIDDEN_TIER_FIELD_TOKENS` 的 guardrail test，再决定 MIGRATE vs REIMPLEMENT**。这是审计中发现的最大单点风险：代码量大、不变量真实，但零测试。

## 4. 其他已判定业务能力（非本文件重点，登记于 DOMAIN_REGISTRY）

以下能力已有明确判定，不在本文件展开，详见 `governance/MIGRATION_MANIFEST.yaml` 与 `governance/DOMAIN_REGISTRY.yaml`：

- **product_strategy** — REIMPLEMENT（159 行，仅 domain+ports+fake repository，无真实持久化，无测试）。
- **market_intelligence** / **growth_plan_python_stub** — ARCHIVE / NOT_MIGRATING（占位/空壳）。
- **auth_identity** — MIGRATE（源 TS，1546 行，真实 Postgres）。
- **orchestration_core** / **principal_core** — MIGRATE（源 TS，明确设计为不写 Growth 权威表）。
- **model_provider_assessment** / **orchestration_llm_gateway_violation** — REVIEW_REQUIRED / BLOCKED（后者是 R7 违规先例，重建时不得重复）。

## 5. 与产品语言的一致性

四层区分（Fact≠Perspective≠Recommendation≠Action≠Outcome）与"不做 Family Total Score/Ranking"的产品语言约束适用于本文件列出的所有业务域，尤其是 family_core 与 membership（`FORBIDDEN_TIER_FIELD_TOKENS` 正是对 R9 中 score/rank 红线的域内呼应）。详见 `docs/03_product/PRODUCT_VISION.md`。
