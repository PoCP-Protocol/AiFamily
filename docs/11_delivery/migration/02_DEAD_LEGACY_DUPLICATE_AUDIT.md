# 02 — 死代码 / 孤儿 / 重复实现审计 (Dead, Legacy, Duplicate Audit)

- **审计对象**: `PoCP-Protocol/family-ai` @ `1ff168123d147f4d6a6eaaa677bc2f80986233d9`
- **判定标准**：本报告只收录"读过代码后有明确证据链"的条目。每条给出：判定类别（死代码/孤儿/重复/漂移/矛盾）、证据（具体文件+行号或具体缺失物）、影响范围、对 AIFAMILY-000 的行动建议。不下无证据的断言。

---

## 1. `waf-domain.service.ts` — 死代码

- **路径**: `apps/api/src/modules/family/../waf/waf-domain.service.ts`
- **判定**: 死代码
- **证据**:
  - 261 行，实现为纯内存 `Map`，零数据库交互
  - 全仓库 grep 引用，唯一消费者是它自己的 `.spec.ts` 文件——没有任何生产路由、controller、其他 service 导入它
  - `governance/MIGRATION_MANIFEST.yaml` 条目 `waf_domain_service`: `disposition: ARCHIVE`, `status: NOT_MIGRATING`
- **影响范围**: 无——这是判定为死代码的核心依据本身（无影响即证明无消费者）
- **行动建议**: 不迁移。若 `waf-contracts` 包（见第 8 条）有独立价值，需与本服务分开评估，不能因为名字相似而混为一谈。

---

## 2. `case-access-client.spec.js` — 逐字节重复文件

- **路径**: `apps/web/src/case-access-client.spec.js`
- **判定**: 重复（与同目录 `.spec.ts` 文件逐字节相同）
- **证据**:
  - 与同目录下的 `case-access-client.spec.ts` 内容逐字节相同（非"相似"，是完全相同）
  - 被 vitest 配置显式排除，从不参与测试运行
  - `MIGRATION_MANIFEST.yaml` 条目 `test_oracle_dead_duplicate`: `disposition: DELETE`
- **影响范围**: 无运行时影响，纯磁盘冗余
- **行动建议**: 不迁移，不作为 TEST_ORACLE 来源（`.ts` 版本已覆盖同等价值）。

---

## 3. `evals/*.contract.spec.ts` — 未被收集的契约测试

- **路径**: `evals/subject-isolation/subject-isolation.contract.spec.ts`、`evals/authorization-planes/authorization-planes.contract.spec.ts`
- **判定**: 孤儿（有价值但零执行证据）
- **证据**:
  - `evals/` 目录**不在** `pnpm-workspace.yaml` 内，因此不被任何 workspace 命令、任何 vitest/jest runner 收集
  - 断言逻辑是 spec 文件内联重实现业务规则，不是对真实生产代码路径的覆盖测试——即它验证的是"这份规格是否自洽"，不是"生产代码是否遵守规格"
  - `MIGRATION_MANIFEST.yaml` 条目 `test_oracle_excluded_contract_specs`: `disposition: MIGRATE`，但明确标注 `note: "作为需求规格迁移断言,不作为覆盖率证明"`
- **影响范围**: 中——这两份文件包含 subject 隔离与授权平面的规格意图，若被误当作"已验证的覆盖率"会造成虚假安全感
- **行动建议**: 迁移其**断言逻辑**作为 Python 侧的需求规格来源，但迁移时必须改写为针对真实生产代码路径的测试，不能原样搬运"测试测试自己"的结构。

---

## 4. `apps/ai-runtime` — 源码已删除的应用

- **路径**: `apps/ai-runtime`
- **判定**: 死代码 / 不可移植遗产
- **证据**:
  - git 从未跟踪该目录
  - `.py` 源码已从磁盘删除，只剩 `.pyc` 编译产物
  - `dist-info` 自述 "not wired into the default request path"
  - venv 内 `.pth` 文件硬编码绝对路径 `D:\family-ai\50_开发_dev\apps\ai-runtime\src`，不可移植到任何其他机器
  - `MIGRATION_MANIFEST.yaml` 条目 `ai_runtime_app`: `disposition: ARCHIVE`
- **影响范围**: 无生产影响（从未接入请求路径），但是 `REPOSITORY_CONSTITUTION.md` R11 的核心伤疤案例——"能力的唯一证据是编译产物"
- **行动建议**: 不迁移。若需要复原其能力意图，只能靠 `.pyc` 反编译或询问原作者，本次审计不建议投入此成本。

---

## 5. `apps/consumer-web`、`apps/ops-web` — 空壳目录

- **判定**: 空壳（非死代码，是从未出生）
- **证据**: 目录内仅有 `node_modules`，无 `package.json`，无任何源码文件
- **MIGRATION_MANIFEST.yaml**: `frontend_empty_scaffolds`, `disposition: DELETE`
- **行动建议**: 直接删除，不登记为迁移目标。

---

## 6. `factory/run-development-factory.mjs` — 内部引用已损坏

- **路径**: `factory/`
- **判定**: 疑似死代码/孤儿（引用链已断裂）
- **证据**: `run-development-factory.mjs` 内部引用的脚本路径在磁盘上不存在（脚本试图调用一个不存在的文件）
- **列入**: `MIGRATION_MANIFEST.yaml` 的 `review_required_index`: `"50_开发_dev/factory/"`
- **影响范围**: 未知——因为脚本本身无法运行，无法验证其原本设计要驱动什么。可能是"自驱开发工厂"这一更大构想（与 `family-devos-v1` 相关，见用户历史记忆）的早期原型，已废弛
- **行动建议**: **REVIEW_REQUIRED**，人工确认这是否与其他已知的 devops/family-devos-v1 工作重叠，避免重复建设。不建议在未确认前直接归档，因为它可能是某个更大平台构想的入口点残留。

---

## 7. `packages/program-runtime`、`packages/harness` — 未找到消费者

- **判定**: 孤儿（疑似）
- **证据**: 全仓库范围内未找到对这两个包的任何 import 消费者
- **列入**: `MIGRATION_MANIFEST.yaml` 的 `review_required_index`
- **行动建议**: **REVIEW_REQUIRED**。在判定为 ARCHIVE 前，需要确认是否是被规划为未来使用但尚未接入的基础设施（"预埋"），还是纯粹废弛。仅凭"未找到消费者"不足以下最终结论，本报告克制地标注为待裁决而非直接判死。

---

## 8. `products/famili-principal` — 纯文档树

- **判定**: 疑似孤儿（无代码）
- **证据**: 目录下只有文档，没有可执行代码
- **列入**: `MIGRATION_MANIFEST.yaml` 的 `review_required_index`
- **行动建议**: **REVIEW_REQUIRED**。需要人工判断这些文档是否是某个已实现能力（如 `principal_core`）的产品设计源，或是从未落地的独立提案。不与 `apps/api/src/modules/principal`（真实代码，2337 行）混为一谈——本报告未发现两者有明确引用关系。

---

## 9. 三份互相矛盾的"当前基线"文档 — 治理层面的重复/矛盾（最高优先级）

- **判定**: 矛盾（Contradiction），非死代码，但是治理风险最高的一项发现
- **证据**（三份文档，互不引用，各自自称"当前基线"）:

  | 文档 | 日期 | 声称的主线叙事 |
  |---|---|---|
  | `CURRENT_SPRINT.md` | 2026-08-29 | 记录 7 条项目所有者 Override，声称 Python-only 后端正按 `architecture/FAMILY_AI_PYTHON_ONLY_MIGRATION_PLAN_V1.md`（2026-08-28）推进 Batch 1-6 |
  | `governance/PROGRAM_STATUS_PLATFORM_V1.md` | 2026-08-16 裁定 | PR#36 / Principal-AI-Coach 为主线——与 Python 迁移完全不同的叙事 |
  | `architecture/FAMILY_PLATFORM_V3_BLUEPRINT.md` | 2026-08-16 冻结，自称架构 SSOT | 五引擎模型（Growth Need / Capability / Resource / Orchestration / Steward），术语体系与前两份完全不通 |

- **为什么判定为矛盾而非简单的"文档过期"**：三份文档日期相近（8月16日与8月29日），且**没有一份显式声明取代另外两份**。按 `REPOSITORY_CONSTITUTION.md` R13（"同一主题不得有两份都自称基线的文档"），源仓库自身已经违反了这条后来被 AiFamily 采纳的规则——这不是历史遗留，是审计时点仍然活跃的矛盾。

- **最关键的子发现**：源仓库自己已经存在一份 `architecture/FAMILY_AI_PYTHON_ONLY_MIGRATION_PLAN_V1.md`（2026-08-28），且 `CURRENT_SPRINT.md` 记录了 7 条项目所有者 Override 正在按它推进 Batch 1-6。**这意味着 AIFAMILY-000（本次清洁重建计划）可能是对同一个"迁到 Python"决定的重复下达**，而不是唯一在途的迁移工作。

- **影响范围**: 高。如果 AIFAMILY-000 与源仓库既有的 Python-only 迁移计划是同一决定被重复批准，会导致：
  1. 两条并行的 Python 迁移工作互相不知情，产生冲突的 canonical_path
  2. 人类决策者以为自己在批准一个新决定，实际是在重复批准一个已经在执行的决定
  3. 源仓库 Batch 1-6 中已经产生的产出（如果有）未被本次审计纳入，AiFamily 可能重新发明已经存在的东西

- **行动建议（已写入 `MIGRATION_MANIFEST.yaml` 的 `docs_current_baseline_CONTRADICTION` 条目，`status: BLOCKED`）**：
  **必须人工裁决**：AIFAMILY-000 与 `FAMILY_AI_PYTHON_ONLY_MIGRATION_PLAN_V1.md` 是同一决定的重复下达，还是两个并行/冲突的方案？在裁决前，AiFamily 不得假设自己是"唯一正在进行的 Python 迁移工作"。这是本次四份报告中优先级最高的单条待裁决事项，建议人类架构师第一时间处理，因为它决定了后续 Wave 2/3 的执行范围是否需要重新框定。

---

## 10. `FPAI_PROVIDER_REGISTRY.yaml` 治理漂移 — 声明与生成物不一致

- **判定**: 漂移（Drift），治理执行力空心化的具体实证
- **证据**:
  - `governance/FPAI_PROVIDER_REGISTRY.yaml` 声明 **3 个**供应商
  - 由它生成的运行时快照 `packages/principal-runtime/src/provider-registry.generated.ts` 只有 **2 个**（缺 `deepseek-chat`）
  - 生成器 `tools/build_provider_policy_snapshot.py --check` 在基线 commit 上执行结果为 **exit 1**
  - 全仓库唯一生效的 CI workflow（`family-35ui-alignment.yml`）的 path filter 未覆盖该生成器，因此这个失败态从未被 CI 拦截，被直接提交进了主线
- **影响范围**: 中高。这证明"写成 YAML 的策略"不等于"被执行的策略"——`REPOSITORY_CONSTITUTION.md` R14 直接以此为核心论据。任何依赖 `FPAI_PROVIDER_REGISTRY.yaml` 作为"当前供应商真相"的下游代码都可能拿到过期/不一致的数据。
- **行动建议**: 迁移 `FPAI_PROVIDER_REGISTRY.yaml` 本身（已登记为 `MIGRATE`），但迁移时必须同时迁移一个**会在 CI 中真正跑起来**的一致性检查，不能重复"写了检查脚本但没人跑"的错误。

---

## 11. 补充：本报告未能覆盖的目录

`agents`、`family-os`、`scaffold` 三个顶层目录未出现在本次七路审计的浓缩发现中。本报告不对其做死代码/孤儿判定，因为没有实际读码证据支撑——按任务要求，判定必须可追溯到具体文件路径，宁可留空待补充审计，不臆造结论。

---

## 12. 汇总表

| 条目 | 判定 | disposition | 是否阻塞 Wave 执行 |
|---|---|---|---|
| waf-domain.service.ts | 死代码 | ARCHIVE | 否 |
| case-access-client.spec.js | 重复 | DELETE | 否 |
| evals/*.contract.spec.ts | 孤儿(有价值) | MIGRATE(仅断言) | 否 |
| apps/ai-runtime | 死代码 | ARCHIVE | 否 |
| consumer-web/ops-web | 空壳 | DELETE | 否 |
| factory/run-development-factory.mjs | 孤儿(引用损坏) | REVIEW_REQUIRED | 建议裁决 |
| packages/program-runtime, harness | 孤儿(疑似) | REVIEW_REQUIRED | 建议裁决 |
| products/famili-principal | 孤儿(疑似) | REVIEW_REQUIRED | 建议裁决 |
| 三份矛盾"当前基线"文档 | 矛盾 | REVIEW_REQUIRED | **是，最高优先级** |
| FPAI_PROVIDER_REGISTRY 漂移 | 漂移 | MIGRATE(需配套CI) | 否，但需同PR补检查 |
