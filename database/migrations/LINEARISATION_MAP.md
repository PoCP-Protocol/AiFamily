# 源仓库迁移线性化映射表 (Migration Linearisation Map)

- **状态**: CURRENT — 本文件是"源仓库 SQL 迁移 → AiFamily baseline 应用顺序"这一主题的唯一当前真相
- **生效**: 2026-08-29
- **产出任务**: `docs/11_delivery/TASK_BACKLOG.md` T-03
- **上游依据**: `governance/MIGRATION_MANIFEST.yaml` 条目 `database_schema`（`blocking_action`：Alembic 首个 revision 生成前必须先解决 4 组重号）、`docs/07_data/DATA_ARCHITECTURE.md` §1.1
- **消费者**: `database/migrations/versions/0001_legacy_schema_baseline.py`（Alembic baseline revision 按本表顺序执行 `database/baseline/*.sql`）

---

## 0. 先纠正两处上游文档口径

| 上游断言 | 实测 | 结论 |
|---|---|---|
| "58 个文件（0001-0058）" (`DATA_ARCHITECTURE.md` §1、`MIGRATION_MANIFEST.yaml`) | 源目录实为 **62 个 `.sql` 文件**，最大编号为 `0058` | "58" 是**最大编号**，不是文件数。4 组重号各多出 1 个文件，62 = 58 + 4。上游文档口径需修正 |
| `growth_profiles` 的 `subject_type`/`subject_ref_id` 是"死列" (`DATA_ARCHITECTURE.md` §1.2) | 源仓库 `apps/api/src/modules/family/family.service.ts:1427-1432` 的 `insert into growth_profiles(...)` **同时写入两代列**；`0045_family_memory_p0_subject_scope.sql:21` 的回填 `UPDATE` 以 `profile.subject_type = 'CHILD'` 为**读取谓词** | **不是死列，是活列**。详见第 4 节 |

## 1. 线性化规则

- 唯一改动是**文件名重编号**，SQL 内容**逐字节不变**（见第 5 节校验）。
- 新序号 = "源仓库 `tools/migrate.mjs` 的实际应用顺序位次"。`migrate.mjs:30-34` 用 `readdirSync().filter(.sql).sort()`，即**纯文件名字典序**——这就是源仓库真实经历过的 DDL 顺序，也是唯一可从制品重建的顺序证据。
- 58 个非重号文件的新序号 = 原编号 + 该编号之前出现过的重号"多出文件"个数（0022 前 0 个、0023 后 1 个、0024 后 2 个、0025 后 3 个、0054 后 4 个）。
- **本表不改变任何相对顺序**，只把"两个文件共享一个编号"这一歧义消除掉。理由见第 3 节：字典序在 4 组重号上恰好已满足全部真实依赖，所以"忠实快照"与"依赖正确"在此处不冲突，无需在 baseline 里引入任何顺序变更风险。

## 2. 完整映射表（62 行）

`**` 标记涉及重号的 8 个文件。

| 源文件名 (`50_开发_dev/database/migrations/`) | 新序号文件名 (`database/baseline/`) | 重号 |
|---|---|---|
| `0001_family_identity.sql` | `0001_family_identity.sql` | |
| `0002_platform_foundation.sql` | `0002_platform_foundation.sql` | |
| `0003_growth_foundation.sql` | `0003_growth_foundation.sql` | |
| `0004_relationship_symmetric_uniqueness.sql` | `0004_relationship_symmetric_uniqueness.sql` | |
| `0005_consent_active_uniqueness.sql` | `0005_consent_active_uniqueness.sql` | |
| `0006_perspective_evidence_contract_alignment.sql` | `0006_perspective_evidence_contract_alignment.sql` | |
| `0007_growth_profile_draft_confirmation.sql` | `0007_growth_profile_draft_confirmation.sql` | |
| `0008_m2_wave2_priority_intervention_action.sql` | `0008_m2_wave2_priority_intervention_action.sql` | |
| `0009_m2_wave3_observe_review.sql` | `0009_m2_wave3_observe_review.sql` | |
| `0010_m2_wave3_observation_refs_backfill.sql` | `0010_m2_wave3_observation_refs_backfill.sql` | |
| `0011_principal_runtime.sql` | `0011_principal_runtime.sql` | |
| `0012_principal_action_bridge.sql` | `0012_principal_action_bridge.sql` | |
| `0013_principal_review_workflow.sql` | `0013_principal_review_workflow.sql` | |
| `0014_principal_model_attempts.sql` | `0014_principal_model_attempts.sql` | |
| `0015_identity_sessions.sql` | `0015_identity_sessions.sql` | |
| `0016_otp_challenges.sql` | `0016_otp_challenges.sql` | |
| `0017_principal_handoff_confirmation.sql` | `0017_principal_handoff_confirmation.sql` | |
| `0018_account_family_membership.sql` | `0018_account_family_membership.sql` | |
| `0019_account_scoped_session.sql` | `0019_account_scoped_session.sql` | |
| `0020_growth_orchestration_v1.sql` | `0020_growth_orchestration_v1.sql` | |
| `0021_family_llm_gateway_audits.sql` | `0021_family_llm_gateway_audits.sql` | |
| `0022_family_dev_flow_events.sql` | `0022_family_dev_flow_events.sql` | ** |
| `0022_test_experience_workflows.sql` | `0023_test_experience_workflows.sql` | ** |
| `0023_family_growth_page_objects.sql` | `0024_family_growth_page_objects.sql` | ** |
| `0023_ui30_renewal_interest_operation.sql` | `0025_ui30_renewal_interest_operation.sql` | ** |
| `0024_expert_live_session_operation.sql` | `0026_expert_live_session_operation.sql` | ** |
| `0024_family_catalog_service_asset_objects.sql` | `0027_family_catalog_service_asset_objects.sql` | ** |
| `0025_tenant_master_data_foundation.sql` | `0028_tenant_master_data_foundation.sql` | |
| `0026_multimodal_control_and_facts.sql` | `0029_multimodal_control_and_facts.sql` | |
| `0027_oracle_style_reference_and_object_metadata.sql` | `0030_oracle_style_reference_and_object_metadata.sql` | |
| `0028_family_core_object_registry_seed.sql` | `0031_family_core_object_registry_seed.sql` | |
| `0029_oracle_style_read_views.sql` | `0032_oracle_style_read_views.sql` | |
| `0030_family_product_event_envelope.sql` | `0033_family_product_event_envelope.sql` | |
| `0031_family_commerce_intent_and_entitlement.sql` | `0034_family_commerce_intent_and_entitlement.sql` | |
| `0032_family_service_booking_objects.sql` | `0035_family_service_booking_objects.sql` | |
| `0033_family_membership_entitlement_objects.sql` | `0036_family_membership_entitlement_objects.sql` | |
| `0034_family_page_task_source_page_id.sql` | `0037_family_page_task_source_page_id.sql` | |
| `0035_family_90_day_journey_plan.sql` | `0038_family_90_day_journey_plan.sql` | |
| `0036_family_90_day_journey_actions.sql` | `0039_family_90_day_journey_actions.sql` | |
| `0037_family_operation_followups.sql` | `0040_family_operation_followups.sql` | |
| `0038_family_operation_followups_cleanup_cascade.sql` | `0041_family_operation_followups_cleanup_cascade.sql` | |
| `0039_vs00_tenant_trusted_context.sql` | `0042_vs00_tenant_trusted_context.sql` | |
| `0040_ui02_versioned_family_assessment.sql` | `0043_ui02_versioned_family_assessment.sql` | |
| `0041_ui03_growth_hypothesis_confirmation.sql` | `0044_ui03_growth_hypothesis_confirmation.sql` | |
| `0042_ui09_growth_action_execution_lifecycle.sql` | `0045_ui09_growth_action_execution_lifecycle.sql` | |
| `0043_ui35_growth_camp_lifecycle.sql` | `0046_ui35_growth_camp_lifecycle.sql` | |
| `0044_ui02_family_assessment_ai_capability_memory.sql` | `0047_ui02_family_assessment_ai_capability_memory.sql` | |
| `0045_family_memory_p0_subject_scope.sql` | `0048_family_memory_p0_subject_scope.sql` | |
| `0046_family_assessment_ai_runs.sql` | `0049_family_assessment_ai_runs.sql` | |
| `0047_family_growth_hypothesis_runtime.sql` | `0050_family_growth_hypothesis_runtime.sql` | |
| `0048_communication_21day_curriculum_subsystem.sql` | `0051_communication_21day_curriculum_subsystem.sql` | |
| `0049_t3_party_org_teacher_foundation.sql` | `0052_t3_party_org_teacher_foundation.sql` | |
| `0050_t3_provider_catalog_bridge.sql` | `0053_t3_provider_catalog_bridge.sql` | |
| `0051_t3_service_relationship_case_access.sql` | `0054_t3_service_relationship_case_access.sql` | |
| `0052_t3_party_case_read_runtime.sql` | `0055_t3_party_case_read_runtime.sql` | |
| `0053_communication_21day_admission_gate.sql` | `0056_communication_21day_admission_gate.sql` | ** |
| `0053_service_task_allocation_dev.sql` | `0057_service_task_allocation_dev.sql` | ** |
| `0054_communication_21day_admission_operation.sql` | `0058_communication_21day_admission_operation.sql` | |
| `0055_service_collaboration_allocation_policy.sql` | `0059_service_collaboration_allocation_policy.sql` | |
| `0056_service_case_allocation_basis_and_runs.sql` | `0060_service_case_allocation_basis_and_runs.sql` | |
| `0057_service_task_rework_and_reviewer_gate.sql` | `0061_service_task_rework_and_reviewer_gate.sql` | |
| `0058_product_intelligence_domain.sql` | `0062_product_intelligence_domain.sql` | |

## 3. 4 组重号的排序理由（逐组，含实测证伪）

方法：对每组两个文件，(a) 读内容找 `REFERENCES` / `ALTER TYPE` / `CREATE VIEW ... FROM` 级别的硬依赖；(b) 在真实 Postgres 16 上**交换该组两个文件的位置**重跑全部 62 个文件，看是否报错、结果 schema 是否等价。只有 (b) 报错的组才算存在真实依赖。

### 3.1 `0022` 组 —— 无组内依赖，但**跨编号**有硬依赖，因此顺序被约束

| 原文件 | 新序号 | 建立的对象 |
|---|---|---|
| `0022_family_dev_flow_events.sql` | `0022` | 表 `family_dev_flow_events` |
| `0022_test_experience_workflows.sql` | `0023` | 枚举 `test_experience_operation_kind` / `test_experience_operation_status`、表 `test_experience_operations` |

**组内**：两文件互不引用（`grep test_experience` 对前者 0 命中，`grep dev_flow` 对后者 0 命中）。实测交换二者，62 个文件全部应用成功，schema 等价。**按本组自身判断是任意序。**

**但组内顺序被下一组绑定**：`0023_family_growth_page_objects.sql`（映射到 `0024`）第 68 行
```sql
operation_ref uuid NULL REFERENCES test_experience_operations(operation_id),
```
引用了 `test_experience_workflows` 建的表。因此 `test_experience_workflows` 必须先于 `family_growth_page_objects`。字典序恰好满足（`0022_test...` < `0023_family...`），无需改动。

**实测证伪**：把 `0023_test_experience_workflows.sql` 与 `0024_family_growth_page_objects.sql` 对调后重跑：
```
EXPECTED FAILURE at 0024_family_growth_page_objects.sql
ERROR:  relation "test_experience_operations" does not exist
```
→ 这是本次线性化中**唯一一条被实测证实的硬依赖**。

### 3.2 `0023` 组 —— 有硬依赖，字典序即正确序

| 原文件 | 新序号 | 依赖 |
|---|---|---|
| `0023_family_growth_page_objects.sql` | `0024` | `REFERENCES test_experience_operations(operation_id)`（来自 `0023`）、`REFERENCES growth_intents`（`0020`）、`REFERENCES orchestration_plans`（`0020`）、`REFERENCES service_cases` |
| `0023_ui30_renewal_interest_operation.sql` | `0025` | `ALTER TYPE test_experience_operation_kind ADD VALUE 'MEMBERSHIP_RENEWAL_DRAFT'`（类型来自 `0023`） |

两者**互不依赖**（一个建表、一个改枚举，无交集），但都依赖 `0023_test_experience_workflows`。字典序把两者都排在 `0023` 之后，正确。

**如实写明：本组两文件之间没有依赖关系，任意序，按字母序保留原行为。**

实测交换 `0024` / `0025` 后，62 个文件全部应用成功，表数仍为 151。

### 3.3 `0024` 组 —— 无组内依赖，任意序，按字母序保留原行为

| 原文件 | 新序号 | 内容 |
|---|---|---|
| `0024_expert_live_session_operation.sql` | `0026` | `ALTER TYPE test_experience_operation_kind ADD VALUE 'EXPERT_LIVE_SESSION'` |
| `0024_family_catalog_service_asset_objects.sql` | `0027` | 建 3 张 catalog 表 + `CREATE OR REPLACE VIEW family_customer_asset_projection AS SELECT ... FROM test_experience_operations` |

两者**互不引用**：`0026` 不碰任何 catalog 表；`0027` 的视图只 `SELECT` 表列，不 `SELECT` 或过滤 `EXPERT_LIVE_SESSION` 这个枚举值（`grep EXPERT_LIVE_SESSION` 对 `0027` 0 命中）。

**如实写明：本组两文件之间没有依赖关系，任意序，按字母序保留原行为。**

实测交换后 62 个文件全部应用成功，且 `test_experience_operation_kind` 的枚举标签集与排序完全一致：
```
COMMERCE_INVITE / COMMERCE_GROUP / SERVICE_BOOKING / EVENT_REGISTRATION /
COMMUNITY_TEMPLATE_PUBLICATION / MEMBERSHIP_RENEWAL_DRAFT / EXPERT_LIVE_SESSION
```

**一处必须记录的陷阱**：`0026_expert_live_session_operation.sql` 的 `DO $$` 块以
```sql
IF EXISTS (SELECT 1 FROM pg_type WHERE typname = 'test_experience_operation_kind') AND NOT EXISTS (...)
```
为前置条件——如果该类型尚未存在，它会**静默 no-op 且不报错**。也就是说：把它排到 `0023_test_experience_workflows` **之前**，迁移会"成功"，但 `EXPERT_LIVE_SESSION` 这个枚举值永远不会存在。这是一条 fail-open 的依赖，**测不出来**，只能靠阅读发现。当前顺序（在类型创建之后）是正确的；未来任何重排都必须保持这个相对顺序。

### 3.4 `0053` 组 —— 无组内依赖，任意序，按字母序保留原行为

| 原文件 | 新序号 | 内容 | 归属域 |
|---|---|---|---|
| `0053_communication_21day_admission_gate.sql` | `0056` | 表 `family_growth_camp_admissions`（FK → `tenants` / `families` / `persons`） | communication / 21天沟通营 |
| `0053_service_task_allocation_dev.sql` | `0057` | 枚举 `service_task_status` / `task_assignment_status` / `task_quality_state`，表 `service_tasks` / `task_assignments` / `task_quality_reviews` / `service_contribution_allocations` | service / FGCN |

两者是**两条完全不同的业务链**，无任何交叉引用（`grep camp_admission` 对 `0057` 0 命中；`grep -E 'service_task|task_assignment|contribution'` 对 `0056` 0 命中）。

**如实写明：本组两文件之间没有依赖关系，任意序，按字母序保留原行为。**

下游约束（不影响组内顺序，但确认了两者都必须在此处）：
- `0058_communication_21day_admission_operation.sql` `ALTER TABLE family_curriculum_operations`（来自 `0051`），不碰 `0056` 的表；
- `0059_service_collaboration_allocation_policy.sql` `ALTER TABLE service_tasks` / `service_contribution_allocations` + 在 `task_assignments` 上建唯一索引 → **必须在 `0057` 之后**。字典序满足。

实测交换 `0056` / `0057` 后，62 个文件全部应用成功。

### 3.5 结论汇总

| 组 | 组内是否存在依赖 | 定序依据 |
|---|---|---|
| 0022 | 否 | 任意序，按字母序保留原行为（但 `test_experience_workflows` 必须先于 `0024`，字典序已满足） |
| 0023 | 否 | 任意序，按字母序保留原行为（两者都必须在 `0023` 之后） |
| 0024 | 否 | 任意序，按字母序保留原行为（`0026` 必须在类型创建后，见 3.3 的 fail-open 陷阱） |
| 0053 | 否 | 任意序，按字母序保留原行为 |

**唯一真实的硬依赖是跨组的 `0023_test_experience_workflows` → `0024_family_growth_page_objects`。** 4 组重号内部全部无依赖。因此 `DATA_ARCHITECTURE.md` §1.1 担心的"顺序错了会导致 baseline 与真实 DDL 顺序不一致"这一风险，实测边界比预想小：只要保持 `test_experience_workflows` 在 `family_growth_page_objects` 之前，任何组内顺序都产出等价 schema。

## 4. `growth_profiles` 两代列：不是死列，建议原样带入 baseline

`DATA_ARCHITECTURE.md` §1.2 与 `MIGRATION_MANIFEST.yaml` 都把 `subject_type`/`subject_ref_id` 描述为"被 `0007` 实质性替代但未删除"的死列，并推测"新代码大概率只读写 `profile_scope`/`subject_person_id`"。**这个推测与源码不符**：

1. **旧列是 `NOT NULL` 且无 DEFAULT**（`0003_growth_foundation.sql:15-16`）。`0007` 只做 `ADD COLUMN IF NOT EXISTS`（全部 nullable 或带 DEFAULT），**没有** `ALTER COLUMN ... DROP NOT NULL`。所以任何 INSERT 都**必须**提供 `subject_type` 与 `subject_ref_id`，否则被数据库拒绝。
2. **源仓库运行时同时写两代列**：`apps/api/src/modules/family/family.service.ts:1427-1432`
   ```
   insert into growth_profiles(
     family_id, subject_type, subject_ref_id, life_stage_code, confidence, version,
     effective_from, profile_scope, subject_person_id, subject_relationship_id, status, ...
   ```
3. **旧列被当作读取谓词**：`0048_family_memory_p0_subject_scope.sql:21` 的回填 `UPDATE` 用 `AND profile.subject_type = 'CHILD'` 筛选行——这是 P0 家庭记忆 subject scope 迁移的核心条件，删掉 `subject_type` 这条 SQL 就不成立。
4. `0007` 自身也仍在用 `subject_type`：`growth_profile_drafts` 表带 `subject_type growth_domain NOT NULL CHECK (subject_type IN ('PARENT','RELATIONSHIP'))`，且其一致性 CHECK 把 `profile_scope` 与 `subject_type` **绑在一起**校验（`0007:42-44`）。两代列不是替代关系，是**冗余共存的双写关系**。

**建议（待 owner 裁决）：baseline 原样带入两代列，不在本 PR 清理。** 理由：
- baseline 的定义应是"源仓库 schema 的忠实快照"，这也是 `DATA_ARCHITECTURE.md` §5 明确要求的（"该 PR 应该只做线性化+baseline 生成，不夹带任何 schema 层的目标态重设计"）。
- 更重要的是：**上游文档对这两列性质的判断是错的**，在错误前提上做清理会破坏 `growth_profile_drafts` 的 CHECK 约束语义和 `0048` 的回填逻辑。
- 真正的技术债不是"有死列"，而是"**同一语义有两套列在双写，没有单一真相**"（这本身是 R2 在数据层的违反）。它的正确解法是 T-05 在 Python 侧重建 assessment/growth 模型时，只暴露一代列语义、把另一代降级为 legacy 兼容字段，并配 ADR 记录退役路径——不是在 baseline 里 `DROP COLUMN`。

**需要 owner 裁决的点**：是否接受"baseline = 忠实快照（含双写债）"这一定义。若接受，`DATA_ARCHITECTURE.md` §1.2 的表述需按本节修正（"死列"→"双写冗余列"）。

## 5. 内容不变性校验

`database/baseline/*.sql` 与源文件逐字节相同，可复核：

```bash
uv run pytest tests/database/test_baseline_linearisation.py -v
```

该测试读取本文件第 2 节的映射表，对每一行核对：
1. 新序号文件存在；
2. 新序号文件与源文件的 SHA-256 一致（源仓库可达时；不可达时 skip 并报告，不伪装通过）；
3. 62 行映射覆盖 `database/baseline/` 下全部文件，无遗漏无多余；
4. 新序号连续无空洞。

源路径不写入可执行代码（R12）：由环境变量 `AIFAMILY_LEGACY_MIGRATIONS_DIR` 提供，未设置则 skip。
