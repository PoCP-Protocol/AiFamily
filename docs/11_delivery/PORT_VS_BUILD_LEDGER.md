---
id: DELIVERY-PORTBUILD-001
title: AiFamily 移植 vs 自研分类台账
type: delivery
status: current
version: 1.0
owner: project-manager
created: 2026-08-29
updated: 2026-08-30
canonical: true
supersedes: null
superseded_by: null
---

# AiFamily 移植 vs 自研分类台账

> 本文件补 `PROJECT_MANAGEMENT_CHARTER.md` 缺的一块：**从 family-ai 移植的代码**与
> **AiFamily 自研的代码**混在一起管，导致两类完全不同的风险被同一套验收标准放过。
>
> - 移植类要验**语义是否忠实**，风险是"把旧世界缺陷一起搬过来"，**可对照源仓库**
> - 自研类要验**设计是否正确**，风险是"没有参照物、无人复核"，**无从对照**
>
> 判定方法：先读 `governance/MIGRATION_MANIFEST.yaml` 的 `source` 字段，
> 再到源仓库 `D:\family-ai\50_开发_dev\` 只读核实。**不只信 manifest**——
> 本次核实发现 5 处仍需治理的 registry 与磁盘/源仓库不符，另有 1 处已在本轮清理中解决（见 §6）。源仓库全程只读，未做任何写入或 git 操作。

## 0. 分类判据

| 类别 | 判据 |
|---|---|
| `PORTED_FAITHFUL` | 源仓库有对应物，语义忠实迁移（差异仅限 ruff 格式化、`from backend.*` 导入路径改写、Python 3.12 语法现代化） |
| `PORTED_DIVERGED` | 源仓库有对应物，但 AiFamily 版本已实质偏离（新增/删除行为、schema 要求与 baseline 不一致） |
| `REBUILT` | 源仓库有对应概念但 AiFamily 重新设计（`disposition=REIMPLEMENT`，参照 TS/YAML 规格重译） |
| `NATIVE` | AiFamily 自研，源仓库任一分支与工作树均无对应物 |
| `UNCLEAR` | 无法判定，需人工裁决 |

---

## 1. 一页总览

### 1.1 五类分布（含代码目录，实测行数）

| 类别 | 模块数 | 代码行数 | 占比 |
|---|---|---|---|
| `PORTED_FAITHFUL` | 8 | 20,462 | 66.0% |
| `PORTED_DIVERGED` | 4 | 15,282 | — (与上行部分重叠，见注) |
| `REBUILT` | 8 | 3,644 | 11.8% |
| `NATIVE` | 5 | 3,725 | 12.0% |
| `UNCLEAR` | 0 | 0 | 0% |
| **合计（去重）** | **27** | **31,001** | 100% |

> **注**：`PORTED_DIVERGED` 不是与 `PORTED_FAITHFUL` 并列的第六列，而是移植类中偏离的
> 子集，其行数已计入移植总量。移植类合计 12 个模块 / 20,462 行，其中 4 个模块偏离。

行数实测命令（不估算）：

```bash
find <dir> -name '*.py' -not -path '*__pycache__*' -exec cat {} + | wc -l
```

### 1.2 全仓库代码量（实测）

| 区域 | 文件数 | 行数 |
|---|---|---|
| `backend/domains/*` | 154 | 21,999 |
| `backend/platform/*` | 17 | 1,674 |
| `backend/intelligence/*` | 15 | 2,130 |
| `backend/packages/contracts` | 9 | 797 |
| `backend/apps/family_api` | 4 | 479 |
| `tests/*`（仓库级） | 63 | 10,845 |
| `backend/domains/product_intelligence/tests`（域内） | 16 | 5,637 |
| `database/baseline/*.sql` | 62 | 4,337 |
| `database/migrations/versions/*.py` | 3 | 677 |
| `frontend/mobile`（ts/tsx，排除 node_modules） | 167 | 15,799 |
| `tools/architecture` | 1 | 599 |

### 1.3 测试与 CI 事实

- `uv run pytest -q` → **524 passed / 39 skipped**（skip 全因 `AIFAMILY_TEST_DATABASE_URL` 未设，真实 Postgres 路径未跑）
- `uv run pytest tests/architecture -q` → **58 passed / 1 skipped**

---

## 2. 逐模块台账表

### 2.1 `backend/domains/*`

| 模块路径 | 类别 | 源仓库对应物（只读核实） | 有无测试 | 风险 | 依据 |
|---|---|---|---|---|---|
| `backend/domains/assessment` (3,263行) | **PORTED_DIVERGED** | ✅ `50_开发_dev/backend/domains/assessment`，**仅存在于未合并分支** `feat/python-assessment-domain-p0-001` | ✅ `tests/domains/assessment` 12文件/1,803行 | 中：源在未合并分支，family-ai 若继续演进即漂移；新增两文件无源可对 | 源文件清单 `git ls-tree -r feat/python-assessment-domain-p0-001`；AiFamily 多出 `api/dev_auth.py`、`domain/knowledge_grounding.py`，少 `infrastructure/claude_interpretation.py`（R7 正确排除） |
| `backend/domains/product_intelligence` (10,201行) | **PORTED_DIVERGED** | ✅ `50_开发_dev/backend/domains/product_intelligence`，源 main 仅 1,492 行(V0.1)；完整版在未合并分支 `fix/product-zone-engine-v0-closure` | ✅ 域内 `tests/` 16文件/5,637行 | **高**：私藏 SQL 副本被本地改写，与 `database/` 不一致；见 §3.1 | `backend/domains/product_intelligence/migrations/{0058,0059,0060}.sql` 存在；`backend/domains/product_intelligence/migrations/README.md` 自报漂移 |
| `backend/domains/membership` (3,240行) | **PORTED_DIVERGED** | ✅ `50_开发_dev/backend/domains/membership`（源 main 已跟踪，2,627行） | ✅ `tests/domains/membership` 3文件/833行 | 中：`SAME_TIER_ALLOWED_SOURCES` 为 AiFamily 新增（修源缺陷，方向正确）；4 张 ORM 表无 SQL 支撑，见 §3.3 | `backend/domains/membership/domain/policies.py:31-51` 新增常量并自述理由；`infrastructure/sqlalchemy_models.py` 9 张表 vs `database/baseline/0036` 只有 5 张 |
| `backend/domains/service` (3,060行) | **REBUILT** | ⚠️ 无 Python 源；源为 SQL `50_开发_dev/database/migrations/0032`（本仓库 baseline `0035`） | ✅ `tests/domains/service` 3文件/1,246行，含唯一 `test_orm_matches_migrations.py` | 低：本域是 SQL→Python 重译，非代码移植；schema 卫生最好 | `find backend/domains/service -name '*.sql'` = 0 命中；`database/baseline/0035_family_service_booking_objects.sql` 存在；`database/migrations/versions/0003_service_booking_additions.py` 存在 |
| `backend/domains/loyalty_points` (1,984行) | **NATIVE** | ❌ **家庭-ai 全部 46 个分支 + 工作树均零命中** | ⚠️ `tests/domains/loyalty_points` 2文件/867行（manifest 称"零测试"已过时），但**合规 guardrail 缺失** | **高**：见 §4.1 | `git ls-tree -r <每个分支> \| grep -i loyalty` 全部 0 命中；`find 50_开发_dev -iname '*loyalty*'` 0 命中 |
| `backend/domains/product_strategy` (162行) | **PORTED_FAITHFUL**（已 RETIRE） | ✅ `50_开发_dev/backend/domains/product_strategy`（159行） | ❌ 零测试 | 低：`RETIRED_CANONICAL_CONFLICT`，无引用方 | 逐文件 diff：`ports.py`/`errors.py`/`fake_repository.py` 0 差异，`domain/entities.py` 21 行差异（全为 ruff 格式化） |
| `backend/domains/market_intelligence` (52行) | **PORTED_FAITHFUL**（已 RETIRE） | ✅ `50_开发_dev/backend/domains/market_intelligence`（52行） | ❌ 零测试 | 低：同上 | `domain/entities.py` 4 行差异（格式化），`errors.py` 0 差异 |
| `backend/domains/growth_plan` (37行) | **PORTED_FAITHFUL** | ✅ `50_开发_dev/backend/domains/growth_plan`（37行，单文件） | ❌ 零测试 | 中：R2 与未来 `journey` 域语义重叠（registry 已登记为未解决风险） | `domain/errors.py` 0 差异；`DOMAIN_REGISTRY.yaml → growth_plan_python_stub.r2_overlap_risk` |

### 2.2 `backend/platform/*` — 全部 REBUILT

源仓库**零个** Python 平台原语。逐类名核实（`grep -rl "class <N>" --include=*.py --include=*.ts`，排除 node_modules）：
`ActorContext` = 0、`TenantContext` = 0、`UnitOfWork` = 0、`ConsentGate` = 0、`AuditRecorder` = 0。
行为规格来自 TS/YAML 参考实现，均已核实存在于源仓库。

| 模块路径 | 类别 | 源仓库对应物（只读核实） | 有无测试 | 风险 | 依据 |
|---|---|---|---|---|---|
| `backend/platform/identity` (211行) | **REBUILT** | ⚠️ 规格参考 `apps/api/src/modules/auth/`（14文件，已核实存在） | ✅ `tests/platform/identity` 2文件 | 中：`platform_actor_tenant_context` 与 `auth_identity` 共用目录（registry 已声明为有意决定）；`auth_identity` 业务对象 = `NOT_STARTED` | `ls 50_开发_dev/apps/api/src/modules/auth/` 已确认；`DOMAIN_REGISTRY.yaml` 两条 `r2_boundary_note` |
| `backend/platform/authorization` (211行) | **REBUILT** | ⚠️ `apps/api/src/modules/auth/family-authorization.policy.ts` + `family-scope.guard.ts` 已核实存在 | ✅ `tests/platform/authorization` 2文件 | 中：TS 侧 `family-scope.integration.spec.ts` 的 6 层绑定链 DENY 矩阵尚未迁为 Python 断言 | 源文件存在；`MIGRATION_MANIFEST.yaml → test_oracle_tenant_isolation` = `PLANNED` |
| `backend/platform/consent` (131行) | **REBUILT** | ⚠️ `specs/ontology/consent.schema.yaml` 已核实存在 | ✅ `tests/platform/consent` 1文件 | 中：只有内核 `ConsentGate`，**同意记录本体（业务域）未开工**，无 `ConsentQueryPort` 生产实现 | `DOMAIN_REGISTRY.yaml → platform_consent.scope` |
| `backend/platform/audit` (722行) | **REBUILT** | ⚠️ `apps/api/src/audit/audit.service.ts`（22行，极薄） | ✅ `tests/platform/audit` 2文件 + Alembic `0002_platform_audit_events_worm.py` | 低：AiFamily 版本远超源；`platform_audit_events` 表有 Alembic revision 支撑 | 源路径**实为** `apps/api/src/audit`，manifest 写 `apps/api/src/modules/audit`（路径漂移，见 §6.5） |
| `backend/platform/idempotency` (122行) | **REBUILT** | ⚠️ 源仅有字段级 `_by_idempotency_key`，无抽象 | ✅ `tests/platform/idempotency` 1文件 | 低 | `MIGRATION_MANIFEST.yaml → platform_idempotency.evidence` |
| `backend/platform/persistence` (277行) | **REBUILT** | ⚠️ 源 `membership/infrastructure/sqlalchemy_repository.py` 的手写 `commit()/_stage()` | ✅ `tests/platform/persistence` 3文件 | 低 | 同上 |

### 2.3 `backend/intelligence/*`

| 模块路径 | 类别 | 源仓库对应物（只读核实） | 有无测试 | 风险 | 依据 |
|---|---|---|---|---|---|
| `backend/intelligence/model_gateway` (1,970行) | **REBUILT** | ⚠️ 规格参考 `packages/ai-gateway/src/index.ts`（实测 **893** 行，manifest 写 894） | ✅ `tests/intelligence/model_gateway` 5文件/1,409行 + `tests/architecture/test_ai_runtime_isolation.py` | 中：**零个外部供应商可调用**（全部 `sub_delegates=None`，`admit()` 一律拒绝，待法务）；**零业务调用方** | `wc -l packages/ai-gateway/src/index.ts` = 893；`DOMAIN_REGISTRY.yaml → model_gateway.known_gaps` |
| `backend/intelligence/design_copilot` (160行) | **PORTED_DIVERGED** | ✅ `50_开发_dev/backend/intelligence/design_copilot` | ❌ 零专属测试（仅 1 个文件提及） | 低：能力本身不存在（全 `NotImplementedError`），但 import 目标已被本地改写 | `compiler.py` 28 行差异 / `simulation.py` 44 行差异；`MIGRATION_MANIFEST.yaml → design_copilot.note` 自述改了 `ProductDefinition` 的 import 来源 |

### 2.4 `backend/packages/*` 与 `backend/apps/*`

| 模块路径 | 类别 | 源仓库对应物（只读核实） | 有无测试 | 风险 | 依据 |
|---|---|---|---|---|---|
| `backend/packages/contracts` (684行) | **PORTED_FAITHFUL** | ✅ `50_开发_dev/backend/packages/contracts` 的共享契约子集 | ⚠️ 无自有测试，5 个测试文件间接引用 | 低：两个重复 domain truth 文件已删除，仅保留共享 evidence/versioned/learning/gamification/UI/value contracts | `product_strategy.py` / `product_factory.py` 已于 2026-08-30 删除；剩余 7 个文件与 manifest 保留清单一致 |
| `backend/apps/family_api` (479行) | **NATIVE** | ❌ 源仓库**零个** `FastAPI()`/`uvicoren.run()`/首方 `include_router()` | ✅ `tests/apps/family_api` 4文件/549行 | 中：`product_intelligence`（8 文件 api 层）与 `loyalty_points` 的 router **未挂载**；`dev_wiring.py` 是合成家庭 | `grep -n include_router backend/apps/family_api/main.py` → 仅 root/assessment/dev_auth/membership/service 五处 |

### 2.5 `database/`、`tests/`、`tools/`、`frontend/mobile`

| 模块路径 | 类别 | 源仓库对应物（只读核实） | 有无测试 | 风险 | 依据 |
|---|---|---|---|---|---|
| `database/baseline/` (62文件/4,337行) | **PORTED_FAITHFUL** | ✅ `50_开发_dev/database/migrations/*.sql` 逐字节线性化 | ✅ `tests/database/test_baseline_linearisation.py`（sha256 校验） | 低：忠实快照本身可信 | 抽验 `0036` vs 源 `0033`：`CREATE TABLE` 五张完全一致 |
| `database/migrations/versions/` (3文件/677行) | **NATIVE** | ❌ 源仓库无 Alembic（手写 SQL + `tools/migrate.mjs`） | ✅ `tests/database` 2文件/322行 | **高**：只有 3 个 revision，**11 张 ORM 表无 SQL 支撑**；见 §3 | 全 ORM `__tablename__` 扫描（41 项）对 `database/` 逐表核实，11 项 MISSING |
| `tests/architecture/` (13文件/2,178行) | **NATIVE** | ❌ 源仓库无等价治理护栏（`evals/` 契约 spec 未被任何 config 收集） | 自身即测试，58 passed | 中：R3 覆盖检查**只扫 `backend/`**，`tools/` 不受约束 | `tests/architecture/test_migration_manifest.py:54` `backend_dir = repo_root / BACKEND_RELATIVE_PATH` |
| `tests/` 其余（domains/platform/intelligence/apps/support，50文件/8,667行） | **NATIVE** | ❌ 源仓库对应域**零测试目录**（membership/product_strategy/market_intelligence/growth_plan）；assessment/product_intelligence 分支的测试未逐文件移植 | 自身即测试 | 低 | 源 `membership` 无 `tests/`（`find` 已核实） |
| `tools/architecture/check_traceability.py` (599行) | **NATIVE** | ❌ 源仓库无等价 traceability 检查器 | ✅ `tests/architecture/test_traceability_checker.py` | 中：不在 R3 覆盖范围内 | 同上 |
| `frontend/mobile` (167文件/15,799行 ts/tsx) | **PORTED_FAITHFUL** | ✅ `50_开发_dev/apps/mobile` | ✅ 35 测试文件（源仓库 CI `family-35ui-alignment.yml`） | **高**：46 端点仅 11 已实现；9+ 屏幕依赖 `/dev/*` 合成路由，Python 侧不存在 | 文件集 diff 唯一差异是源侧构建产物 `./dist/index.js`；`MIGRATION_MANIFEST.yaml → frontend_mobile.blocking_action` |
| `_superseded_assessment_v1_backup/` | **DELETED** | assessment 四层重构前的旧版备份 | — | 2026-08-30 经复核确认无引用、无测试收集、无独立业务价值，已删除 | 本节 §5.2 |

---

## 3. PORTED_DIVERGED 清单（含具体差异与爆发场景）

**共 4 个模块。** 共同模式：**AiFamily 版本要求/依赖某个东西，而源仓库或 `database/` baseline 里没有。**

### 3.1 `backend/domains/product_intelligence` — 最危险

已知案例的**全貌比原报告更严重**。三层问题：

**(a) `validated_by`/`validated_at`/`validation_reason` 三列（已知）**

| 位置 | 有这三列？ |
|---|---|
| `backend/domains/product_intelligence/infrastructure/sqlalchemy_models.py:186-188` | ✅ ORM **要求** |
| `backend/domains/product_intelligence/migrations/0058_...sql:150-152`（私藏副本） | ✅ 有 |
| `database/baseline/0062_product_intelligence_domain.sql:131-150` | ❌ **无** |
| `grep -rn "validated_by" database/` | ❌ **0 命中** |

**(b) PR-003 addendum：AiFamily 在"忠实快照"文件上做了本地修改（新发现的量级）**

私藏 `0058` = **321 行**，源仓库 `fix/product-zone-engine-v0-closure` 分支的 `0058` = **284 行**。
AiFamily 单方面追加：

- `product_intelligence_contradiction_models` 新增 `problem_id`（**NOT NULL** + FK→growth_problems）、`primary_rank`、`primary_marked_by`、`primary_marked_at`、`reviewed_by`、`reviewed_at`、`review_reason`；`status` CHECK 新增 `'REJECTED'`；`supporting_hypothesis_ids` 新增 `CHECK (jsonb_array_length(...) >= 2)`
- 新表 `product_intelligence_value_architectures`
- `product_intelligence_growth_strategies` 新增 `value_architecture_id`

baseline `0062:152-170` 的同名表**没有** `problem_id`、没有 `REJECTED`、没有那个 CHECK。

**(c) 三区引擎两张表在 `database/` 里完全不存在（最严重）**

`grep -rl "product_zone" database/` = **0 个文件**。

| 私藏 SQL 文件 | baseline 对应物 |
|---|---|
| `migrations/0058_product_intelligence_domain.sql` | 部分（`baseline/0062`，缺上述列） |
| `migrations/0059_product_zone_engine_v0.sql`（158行） | ❌ **无任何对应物** |
| `migrations/0060_product_zone_engine_canonical_cleanup.sql`（84行） | ❌ **无任何对应物** |

缺的对象：`product_intelligence_zone_policy_versions`、`product_intelligence_zone_assessments_v0`、
`uq_zone_policy_active_per_id`（**partial unique index**）、两个 tenant_scope/subject_ref 索引。

**爆发场景**（三个，按严重度）：

1. **`MIGRATION_MANIFEST.yaml → product_intelligence_v2.evidence` 第 6 条声称的"Active Policy 唯一性（应用层 fail-closed + DB partial unique index 双重保证）"在任何 `alembic upgrade head` 建出的库上只有单重保证**——那个 partial unique index 不存在。并发发布两个 ACTIVE policy 时，应用层竞态即可绕过。
2. 对只跑过 `alembic upgrade head` 的库，`product_intelligence_zone_*` 两张表根本不存在 → 整个三区引擎（六维打分、Portfolio 六桶）在测试/生产环境**全链路不可用**，不是"某列缺失"级别。
3. `validate_growth_hypothesis`、contradiction model 的 `problem_id` 写入在 baseline 化的库上报 `UndefinedColumn`。

**为什么现有测试看不见**：`tests/test_postgres_integration.py`、`test_zone_postgres_integration.py`
自己读**私藏 SQL 文件**建库，绕开 `database/`。测试库与 baseline 库是两份不同 schema。
本仓库唯一能看见这类漂移的测试 `test_orm_matches_migrations.py` 位于
`tests/domains/service/`，**只保护 service 域**。

**诚实说明**：这一整类问题（含 PR-003 addendum）已被 `backend/domains/product_intelligence/migrations/README.md`
逐条自报并给出建议，不是隐瞒。但**建议至今未执行**，且 README 的 §"已发现的 schema 矛盾"
只写了三列，未把"0059/0060 整体缺失"列为同等严重项。

### 3.2 `backend/domains/assessment`

| 差异 | 说明 |
|---|---|
| 源仅在未合并分支 | `feat/python-assessment-domain-p0-001`，不是 family-ai main |
| AiFamily 新增 `api/dev_auth.py` | 4 个 `/auth/*` 端点。这正是"四层重构丢掉端点后恢复"的案例——已修复，且 `dev_auth.py` 模块 docstring 完整记录了回归经过与错位理由，另有 `ADR-0010` |
| AiFamily 新增 `domain/knowledge_grounding.py` | 源分支无此文件，**无源可对照**，实为 NATIVE 成分 |
| AiFamily 删除 `infrastructure/claude_interpretation.py` | ✅ 正确（R7 直连 anthropic SDK 会被 `test_no_direct_provider_calls.py` 拦下） |
| 源分支 10 个域内测试文件未随代码进入域内 | AiFamily 改放 `tests/domains/assessment`（12文件），需人工核对断言是否等价迁移 |

**爆发场景**：源分支若在 family-ai 侧继续硬化，两仓库静默漂移，且 AiFamily 无机制发现
（与 `product_intelligence_v2` 的 `known_gaps` 第 2 条同型）。另：源分支有
`database/migrations/0040-0045`（含 `0045_ai_run_ledger.sql`），AiFamily 未迁入 → assessment
的 SQLAlchemy 仓储在 baseline 化的库上无表可用（当前靠内存 repository 掩盖）。

### 3.3 `backend/domains/membership`

| 差异 | 判定 |
|---|---|
| `domain/policies.py:31-51` 新增 `SAME_TIER_ALLOWED_SOURCES`（含 `ANNUAL_MEMBERSHIP_RENEWED`） | **改得对**。源版本 `from_tier == to_tier` 只豁免 `ADMIN_MANUAL_GRANT`，导致 `renew_membership_period()` 每次调用都 `tier_transition_is_noop` —— 年度续费永远失败。源仓库零测试所以没人发现。AiFamily 的 `test_annual_renewal_appends_a_new_period` 抓到了。这是移植类的**正面**案例：忠实移植会把 bug 一起搬进来，测试先行才发现 |
| AiFamily 新增 `api/routes.py` + 各层 `__init__.py` | 源仓库无 HTTP 层 |
| 其余 14 文件差异 2-146 行 | 抽查 `entities.py`（`timezone.utc`→`UTC`、`"Cls"`→`Cls`）、`value_objects.py`（注释对齐）均为 ruff 格式化与 3.12 语法现代化，无语义变更 |
| **4 张 ORM 表无任何 SQL 支撑** | `family_membership_tier_definitions`、`family_membership_periods`、`family_membership_tier_transitions`、`family_membership_benefit_reservations` 在 `grep -rn <表名> database/` 全部 **0 命中** |

**这 4 张表是继承的源仓库缺陷，不是 AiFamily 引入的**：源仓库
`database/migrations/0033_family_membership_entitlement_objects.sql` 同样只有 5 张表
（`plans`/`benefit_definitions`/`subscriptions`/`benefit_grants`/`benefit_ledger`），
全仓库 `grep -rln "family_membership_periods" --include=*.sql` = 0 命中。

**爆发场景**：`alembic upgrade head` 后跑 membership 仓储 → 4 张表 `UndefinedTable`。
现有测试用 `metadata.create_all` 建表（`DOMAIN_REGISTRY.yaml → membership.known_gaps (1)` 已承认），
结构上永远看不见这类漂移。而 `MembershipPeriod` 和 `TierTransition` 是本域的核心审计对象
——"周期续费"和"档位变更"两条链的落库都在这 4 张表上。

### 3.4 `backend/intelligence/design_copilot`

`compiler.py` 28 行差异 / `simulation.py` 44 行差异。manifest `note` 自述把
`ProductDefinition` 的 import 从 `backend.packages.contracts.product_factory` 改指向
`backend.domains.product_intelligence.domain.entities`。

**爆发场景**：低（方法体全是 `NotImplementedError`，零调用方）。其 `ProductDefinition`
import 已指向 `product_intelligence` 域；重复的 `contracts/product_factory.py` 已删除，
不再存在第二份业务实体入口。

---

## 4. NATIVE 复核缺口清单

自研代码**没有参照物**，风险是无人复核。逐模块列 有无测试 / 有无设计文档 / 有无第二人复核。

### 4.1 `backend/domains/loyalty_points`（1,984行）— 缺口最大

| 复核维度 | 状态 |
|---|---|
| 源仓库对应物 | ❌ **确认零对应物**：family-ai 全部 46 个分支 `git ls-tree \| grep -i loyalty` 均 0 命中；工作树 `find -iname '*loyalty*'` 0 命中。（讽刺的是当前 checkout 的分支名叫 `feat/membership-loyalty-points-python-v0-1`，但该分支里**没有** loyalty 代码——名字有、代码无） |
| 有无测试 | ⚠️ **manifest 的"零测试"已过时**：`tests/domains/loyalty_points` 现有 5 文件 / 867 行（`test_ledger_invariants.py` 495行、`test_acceptance_chain.py` 197行） |
| blocking_action (1) 台账不可变性测试 | ✅ 已满足（`test_ledger_invariants.py`） |
| blocking_action (2) **"积分流程无法以孩子为营销对象"的 guardrail** | ❌ **未满足——这是合规义务，不是可选项** |
| 有无设计文档 | ❌ 无 ADR、`docs/` 下无对应文档 |
| 有无第二人复核 | ❌ 无。由并发会话写入，manifest 条目是项目经理**事后补登记**（且"首次登记被并发会话的 manifest 编辑覆盖"） |
| registry 登记 | ❌ **`DOMAIN_REGISTRY.yaml` 与 `CAPABILITY_REGISTRY.yaml` 均无此域**（`grep -n loyalty` 双双 0 命中）→ R2 登记缺口 |
| ORM/schema | ❌ **5 张表全部无 SQL**：`family_loyalty_points_{earn_rules,redemption_items,accounts,ledger,redemptions}` 在 `database/` 全 0 命中 |
| 是否挂载 | ❌ `api/` 目录**只有 `__init__.py`**（manifest 称"后又新增 api 层"不实）；router 未挂载 |
| 批次顺序 | ⚠️ 属 COMMERCE 闭环（`MIGRATION_PLAN_V2` Batch 6），在 Batch 1 阶段提前出现 1,984 行；批次偏离要求补齐治理与验收，不构成禁止继续建设的理由 |

**合规缺口的具体证据**：`backend/domains/loyalty_points/domain/policies.py:63-73`
的 `assert_human_actor` 只检查 `actor.startswith(AI_ACTOR_PREFIX)`——它防的是"AI 悄悄改余额"，
**不防"孩子是营销对象"**。`application/commands.py:108` 的 `subject_person_id: str | None`
接受任意 person 引用，包含未成年人。全域 `grep -rn "minor\|age\|birth"` 无任何年龄/主体类型判定；
测试侧 `grep -rn "child"` 仅命中 `helpers.py:20` 的一个未被断言使用的常量 `CHILD`。

《未成年人网络保护条例》第 24 条第 3 款是**绝对禁止**（无例外、不限 14 岁以下）。
原 `FREEZE-001` 把 Batch 6 的顺序与未成年人营销 guardrail 混成了全局开发冻结，现已撤销。未成年人营销 guardrail、正式积分 ledger、真实失败测试和生产外部适配器仍是必须补齐的质量与准入项，但不阻止测试环境按生产形状建设完整 COMMERCE 流程。

### 4.2 `database/migrations/versions/`（3文件/677行）

| 复核维度 | 状态 |
|---|---|
| 源仓库对应物 | ❌ 源仓库无 Alembic（手写 SQL + `tools/migrate.mjs`） |
| 有无测试 | ✅ `tests/database` 2文件/322行（含 sha256 线性化校验） |
| 有无设计文档 | ✅ `docs/07_data/DATA_ARCHITECTURE.md` §5、`database/migrations/LINEARISATION_MAP.md` |
| 有无第二人复核 | ⚠️ 无独立复核，但 `0001_legacy_schema_baseline.py` 的设计（逐字节 replay 而非 `op.create_table`）是可机械验证的，自带反脆弱性 |
| **实质缺口** | ❌ **只有 3 个 revision，11 张 ORM 表无 SQL 支撑**（见 §3.1/§3.3/§4.1）。baseline 之后的 schema 演进整体缺位 |

### 4.3 `backend/apps/family_api`（479行）

| 复核维度 | 状态 |
|---|---|
| 有无测试 | ✅ `tests/apps/family_api` 4文件/549行 |
| 有无设计文档 | ⚠️ `contracts/openapi/UI_API_ENDPOINT_INVENTORY.md` 是契约侧，非本模块设计文档；无 ADR |
| 有无第二人复核 | ❌ 无 |
| 实质缺口 | `dev_wiring.py` 提供合成家庭（`PROJECT_MANAGEMENT_CHARTER.md` §3 已标为"技术债而非能力"）；product_intelligence 的 8 文件 api 层与 loyalty_points 均未挂载 |

### 4.4 `tests/architecture/`（13文件/2,178行）+ `tools/architecture/check_traceability.py`（599行）

| 复核维度 | 状态 |
|---|---|
| 有无测试 | ✅ 自身即测试（58 passed）；checker 有 `test_traceability_checker.py` |
| 有无设计文档 | ✅ `governance/REPOSITORY_CONSTITUTION.md` R1-R14 是其规格 |
| 有无第二人复核 | ⚠️ 部分：R14 要求"新增检查器必须验证会咬人"，`DOMAIN_REGISTRY.yaml → model_gateway.status_rationale` 记录了四个检查器的植入违规验证 |
| 实质缺口 | ❌ **R3 覆盖检查只扫 `backend/`**（`test_migration_manifest.py:54`）。`tools/`、`tests/`、`database/` 均不在 R3 约束内。护栏自己有覆盖盲区 |

### 4.5 `tests/` 其余（50文件/8,667行）

源仓库对应域**零测试**（membership/product_strategy/market_intelligence/growth_plan 均无 `tests/`），
故这些测试全是 AiFamily 自研。无设计文档、无第二人复核，但它们的价值恰在于抓到了
§3.3 的 membership 续费 bug——**自研测试是本项目目前最有效的复核机制**。

---

## 5. 清理裁决记录

本轮前的两项 `UNCLEAR` 均已按项目负责人授权完成清理；当前没有剩余的 `UNCLEAR` 代码目录。

### 5.1 `backend/packages/contracts` — 已解决

**事实**：`MIGRATION_MANIFEST.yaml → packages_contracts_provenance.note` 明确写：

> 2026-08-29 迁移 product_intelligence_v2 时**删除**本包内的 `product_strategy.py` /
> `product_factory.py` 两个文件：它们定义的 MarketSignal/GrowthProblem/GrowthHypothesis/
> Opportunity/ProductDefinition 等类型与 product_intelligence 域的 canonical 实体同名重复

**磁盘实况（2026-08-30）**：两个文件已删除；共享 contracts 仅保留 7 个非业务真相文件。

```text
backend/packages/contracts/product_strategy.py   → 已删除
backend/packages/contracts/product_factory.py     → 已删除
```

删除后，R2 禁止的“第二份 domain truth”已不在磁盘上，registry 记录与实际一致。
`test_domain_registry.py` 查不到这个——它校验 capability 与 canonical_path 的唯一性，
不校验"某个 package 里有没有与 domain 同名的实体类"。

历史记录中的“UNCLEAR”仅保留为审计背景；当前无代码 import 这两个文件，且
`product_intelligence` 域仍是唯一 canonical 业务实体入口。

### 5.2 `_superseded_assessment_v1_backup/` — 已删除

该根目录备份包含 `api.py` / `service.py` / `test_acceptance_chain.py` /
`__init__.py`，是 assessment 四层重构前的旧版快照。复核确认：

- 当前代码与测试没有任何 import 或路径引用；
- 目录不在 pytest 收集路径，也没有 `MIGRATION_MANIFEST` 条目；
- 当前实现已由 `backend/domains/assessment/` 承载，旧备份没有独立业务价值。

2026-08-30 按项目负责人“删除不需要的现有开发代码”的授权，将该目录四个文件从仓库删除。
若未来需要回溯，使用 git 历史恢复，不再在工作区保留第二套 assessment 源码。

---

## 6. registry 与实际不符之处（5 处当前不符，另 1 处已解决）

| # | 位置 | registry 说 | 磁盘/源仓库实况 | 严重度 |
|---|---|---|---|---|
| 1 | `MIGRATION_MANIFEST.yaml` 第 433 行与第 659 行 | 两条 `capability: assessment` | **YAML 键重复 + 内容互相矛盾**：前者 `disposition: REIMPLEMENT` / `status: MIGRATED_TESTED` / source=TS provider；后者 `disposition: MIGRATE` / `status: PLANNED` / source=Python 分支。同一 capability 两个 disposition、两个 status、两个 source。`python -c yaml.safe_load` 后 `Counter` 显示 54 entries 中唯一重复项 | **高**——`test_migration_manifest.py` 未检测 capability 唯一性（`test_domain_registry.py` 检测的是 DOMAIN_REGISTRY），R14 想防的正是这个 |
| 2 | `MIGRATION_MANIFEST.yaml → packages_contracts_provenance.note` | "删除本包内的 `product_strategy.py` / `product_factory.py` 两个文件" | **已于 2026-08-30 删除，磁盘与 manifest 一致**（见 §5.1） | **已解决** |
| 3 | `MIGRATION_MANIFEST.yaml → loyalty_points.evidence` | "零测试：`tests/` 下无任何 loyalty_points 相关文件" | `tests/domains/loyalty_points/` 5 文件 / 867 行 | 中——**低报**风险，方向是好的，但 registry 不该滞后 |
| 4 | `MIGRATION_MANIFEST.yaml → loyalty_points.evidence` | "application / domain / infrastructure 三层，**后又新增 api 层**" | `backend/domains/loyalty_points/api/` **只有 `__init__.py`**，无 routes/requests/responses | 中——**高报**，"api 层"不存在 |
| 5 | `MIGRATION_MANIFEST.yaml → platform_audit.evidence` 与 `DOMAIN_REGISTRY.yaml → platform_audit.source_reference` | 源路径 `apps/api/src/modules/audit` | 实为 `50_开发_dev/apps/api/src/audit/`（`find . -name audit.service.ts` 唯一命中）。`modules/` 下无 `audit` | 低——路径漂移，不影响判定 |
| 6 | `MIGRATION_MANIFEST.yaml → model_gateway.evidence` | `packages/ai-gateway/src/index.ts`「894行」 | `wc -l` = **893** | 极低——但它是被当作证据引用的数字 |

**另外两项不算"不符"，但需记录**：

- `CLAUDE.md` 铁律 4 与 5 称 `governance/CAPABILITY_REGISTRY.yaml` 与
  `governance/AI_USE_CASE_REGISTRY.yaml`「尚未建立」。**`CAPABILITY_REGISTRY.yaml` 已建立**
  （690 行，17 个 capability，`tests/architecture/test_capability_registry.py` 已强制）。
  `AI_USE_CASE_REGISTRY.yaml` 确实仍不存在（`ls governance/` 只有 ADR/CAPABILITY/DOMAIN/MIGRATION/CONSTITUTION/schemas）。
  CLAUDE.md 的这条指引已过时，会让新 agent 走错分支。
- `DOMAIN_REGISTRY.yaml → database_schema.status: NOT_STARTED` 且 note 称"目录尚不存在于本仓库"。
  `database/` 已存在（62 baseline + 3 revision + alembic.ini），`MIGRATION_MANIFEST` 同一 capability
  写 `status: IN_PROGRESS`。两 registry 对同一 capability 不一致，且 DOMAIN_REGISTRY 一侧与磁盘矛盾。

---

## 7. 对管理章程的建议

`PROJECT_MANAGEMENT_CHARTER.md` §5 的交付门（任务级/场景级/环境级）三层标准对移植与自研
**一视同仁**。建议在**任务级**下按类别分叉，各加一组额外验收标准。

### 7.1 建议在 §2 角色表增加"类别"字段

派任务时除角色外必须声明 `PORT` 或 `BUILD`，因为两者的必读清单不同：
`PORT` 必读源仓库对应文件路径（任务卡里写死，不让 agent 自己找）；
`BUILD` 必读对应 ADR 或要求先写 ADR。

### 7.2 移植类（PORT）额外验收标准

| # | 标准 | 为什么（本次台账的证据） |
|---|---|---|
| P1 | **交付必须贴出源仓库精确坐标**：路径 + 分支/commit。源在未合并分支的，必须在 manifest 的 `known_gaps` 里写明漂移风险 | assessment 与 product_intelligence 的源都在未合并分支，两仓库无同步机制 |
| P2 | **必须贴出"文件集 diff"与"逐文件 diff 行数"**，并对每个 >0 的差异分类为：格式化 / 导入路径 / 语法现代化 / **语义变更**。语义变更必须逐条给理由 | membership 的 `SAME_TIER_ALLOWED_SOURCES` 是好的语义变更（修 bug），design_copilot 的 import 改写是有争议的语义变更——不做这一步无法区分 |
| P3 | **ORM/schema 一致性必须机械验证**：`test_orm_matches_migrations.py` 模式（拿 `alembic upgrade head` 建出的真实库比对 `Base.metadata`）**扩展到每个有 ORM 的域**，不是只有 service 域有 | 11 张 ORM 表无 SQL 支撑（product_intelligence 3 + membership 4 + loyalty_points 5 + value_architectures 1），全部因为其他域用 `metadata.create_all` 建表，结构上看不见漂移 |
| P4 | **禁止域内私藏 SQL**：`test_this_domain_keeps_no_private_sql_copy` 从 `tests/domains/service/` **提升为仓库级** `tests/architecture/` 检查器 | product_intelligence 的三个私藏 SQL 文件是本台账最严重问题的载体，而守它的检查器只保护另一个域 |
| P5 | **"忠实快照"文件禁止本地编辑**：`database/baseline/` 已有 sha256 校验，但域内 SQL 副本无。凡自称"原样迁自源仓库"的文件，必须有 checksum 断言 | AiFamily 在私藏 `0058` 上做了 PR-003 addendum（284→321 行），改的是一个自述"按原样迁自 family-ai"的文件 |
| P6 | **移植带入的已知缺口必须原样声明，且必须写成可执行的待办**：`known_gaps` 条目要有归属人与解除条件，不能只是散文 | membership 的 4 张缺表是继承的源缺陷，registry 承认了但没人负责；product_intelligence 的 `README.md` 给了正确建议，至今未执行 |
| P7 | **源仓库有测试的，测试必须一并移植并跑通**；源仓库零测试的，**测试先行**（先写测试再迁代码） | membership 源侧零测试所以年度续费 bug 从未被发现；AiFamily 的测试先行抓到了它。这条是本项目唯一被证明有效的移植质量机制 |

### 7.3 自研类（BUILD）额外验收标准

| # | 标准 | 为什么（本次台账的证据） |
|---|---|---|
| B1 | **无 ADR 不得开工**（铁律 8 已有，但需落到任务门）。自研没有参照物，ADR 是唯一的"设计被复核过"的证据 | loyalty_points 1,984 行、零 ADR、零 `docs/` 文档、由并发会话写入、事后补登记。它是"自研无复核"的教科书案例 |
| B2 | **必须有第二人复核记录**（另一 agent 或 owner），复核意见写入 PR 或 ADR。移植类可以拿源仓库当"第二双眼"，自研类没有 | loyalty_points 无任何第二人复核；`backend/apps/family_api` 同样无 |
| B3 | **开工前必须在三份 registry 全部登记**：`MIGRATION_MANIFEST`（R3）+ `DOMAIN_REGISTRY`（R2）+ `CAPABILITY_REGISTRY`。**当前只有 R3 有机械强制** | loyalty_points 在 MIGRATION_MANIFEST 有条目，但 `DOMAIN_REGISTRY.yaml` 与 `CAPABILITY_REGISTRY.yaml` **均无此域**——因为 R3 检查器只看 manifest 的 `target`，另两份没有等价的"backend 目录必须登记"检查 |
| B4 | **合规相关的 `blocking_action` 必须转成检查器才算关闭**，散文承诺不算 | loyalty_points 的 blocking_action (1) 台账不可变性已有测试；(2)「积分流程无法以孩子为营销对象」**没有**——而 (2) 是《未成年人网络保护条例》第 24 条第 3 款的绝对禁止，不是可选项 |
| B5 | **自研模块若提前于计划批次，必须登记批次偏离并补齐验收**；不得把批次顺序解释为功能冻结 | loyalty_points 属 COMMERCE（Batch 6），在 Batch 1 阶段出现 1,984 行，与既定顺序不符；应补 ADR/registry、账本 schema、合规 guardrail 和完整测试，而不是禁止建设 |

### 7.4 建议无条件立即执行的三条（与类别无关）

| # | 动作 | 理由 |
|---|---|---|
| G1 | **R3 覆盖检查从 `backend/` 扩展到 `tools/`、`database/`、仓库根目录的裸代码目录** | `test_migration_manifest.py:54` 只扫 `backend/`，`tools/`（599 行）仍完全在治理之外 |
| G2 | **`test_migration_manifest.py` 增加 capability 唯一性断言** | manifest 已有一个重复的 `assessment` 键，两条内容互相矛盾。这是 R14 点名的"registry 与磁盘漂移"的上游形态：registry 与**自己**矛盾 |
| G3 | **更新 `CLAUDE.md` 铁律 4**：`CAPABILITY_REGISTRY.yaml` 已建立（690 行 + 已有强制测试），当前措辞会让新 agent 走"退回双查"的错误分支 | `ls governance/` 已确认；`tests/architecture/test_capability_registry.py` 存在 |

---

## 8. 本台账的执行状态（诚实标注）

- §7 的 P1-P7 / B1-B5 目前**全部无机械执行**，与 `PROJECT_MANAGEMENT_CHARTER.md` §7 同一处境。
  其中 P3 / P4 / G1 / G2 是可立即机械化的（都是架构测试），建议派给 QA 角色。
- 本轮只执行了已获授权且证据充分的清理：删除根目录 superseded assessment 备份、零引用
  重复常量文件，以及 packages contracts 中重复的 domain truth 文件；未修改任何源仓库、业务 registry
  或当前 assessment 实现。§6 其余不符仍仅列出，
  不擅自改（`PROJECT_MANAGEMENT_CHARTER.md` §2：发现他人文件有问题 → 报告，不擅自改）。
- 本轮前的 `UNCLEAR` 项已按授权完成裁决并清理；§6 中剩余 5 项是独立的 registry/治理修正，
  应由对应 owner 在后续变更中处理。原 §5.2 旧备份已按本轮清理授权删除。
