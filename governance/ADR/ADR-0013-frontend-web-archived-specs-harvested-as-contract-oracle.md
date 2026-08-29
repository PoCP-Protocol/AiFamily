# ADR-0013: `frontend_web` 不迁入（ARCHIVE），但其 24 个 spec 文件收割为后端契约参照

- **Status**: Accepted
- **Date**: 2026-08-29
- **Deciders**: chief-architect（本决定含产品面判断，**project-owner 可 override**）
- **Supersedes**: null
- **Superseded By**: null

## Context

`governance/MIGRATION_MANIFEST.yaml:471-475` 的 `frontend_web` 条目
`disposition: REVIEW_REQUIRED` / `status: BLOCKED`，并被列入
`review_required_index:613` 的待人工裁决清单。
`docs/00_system/TARGET_ARCHITECTURE.md` §6 把它列为等架构师裁决的第 1 项。本 ADR 是该裁决。

**实测证据（manifest:475 原文）**：源 `50_开发_dev/apps/web`
「无组件框架、无 bundler，build 脚本只是 `tsc --noEmit`；**24 个 spec 文件价值更多是后端路由的
契约参照，不是可部署 UI**」。

这条证据改变了问题的性质。待裁决的**不是**「要不要迁第二个前端」——按上述描述它从来不是一个可部署
前端（没有组件框架、没有打包器，build 等于只做一次类型检查）。真正待裁决的是：
**一个自称前端、实质是 24 份后端路由契约的目录，该怎么处置。**

必须与之区分开的相邻条目（避免串条目导致误判）：

- `frontend_empty_scaffolds`（manifest:483-487）= `apps/consumer-web` + `apps/ops-web`，
  `disposition: DELETE`，证据「目录内仅 node_modules，无 package.json，无源码」。
  **这两个与 `frontend_web` 是不同条目，已各自裁决完毕，不构成本 ADR 的证据。**
- `frontend_fes_web`（manifest:477-481）= `apps/fes-web`，已 ARCHIVE，「11 行单函数」。
- `frontend_mobile`（manifest:460-469）= 唯一被 project-owner override 明确要求迁入的前端，
  已迁入，`status: MIGRATED_PENDING_BACKEND_INTEGRATION`。

交付顺序上的硬事实：`frontend_mobile` 的 `blocking_action:469` 记
「Python FastAPI 必须先满足 mobile 依赖的端点清单，否则 34 个屏幕中最多 24 个会因缺 `/dev/*` 而白屏」。
`docs/00_system/CURRENT_PRODUCT_MAP.md` 的口径是 34 屏在 AiFamily 内可工作数量为 **0**。
另有三个 web 端（Teacher Workspace / Institution Console / Operations Console）在同文件 §4
为 `PLANNED_NO_CODE`——**它们将来是新建，不是从 `apps/web` 迁移**。

## Decision

拆成两个动作，不要用一个 disposition 同时处理两件不同性质的资产。

### 1. `apps/web` 作为**应用**：`ARCHIVE`，不迁入 AiFamily

`frontend_web` 条目 `disposition` 由 `REVIEW_REQUIRED` 改为 **`ARCHIVE`**，
`status` 由 `BLOCKED` 改为 **`NOT_MIGRATING`**，从 `review_required_index` 移除。
代码留在只读源仓库，AiFamily 内不建 `frontend/web`。

**重启条件（写进条目，不是口头约定）**：当 Teacher Workspace 或 Institution Console
真正立项时，按 `CURRENT_PRODUCT_MAP.md` §4 的 `PLANNED_NO_CODE` 定性**新建**，
并在新建前出 ADR 选定前端栈。**不得以「复用 `apps/web`」为由绕过该 ADR**——
一个没有组件框架和 bundler 的目录不构成可复用基础。

### 2. 24 个 spec 文件作为**契约证据**：收割为 `TEST_ORACLE`

新增 manifest 条目 `test_oracle_web_route_contracts`，
`disposition: TEST_ORACLE`（该词表值已在用，见 manifest:492 等），
`source: ["50_开发_dev/apps/web"]`，`status: PLANNED`，
note 记明其价值是**后端路由契约的第二来源**。

**这是本 ADR 的实质产出**：`TASK_BACKLOG.md` T-04（提取 34 个 UI 的完整 API 契约清单）
当前的主来源是 `frontend/mobile/lib/family/family-api-client.ts`，属**单一来源**。
这 24 个 spec 是同一批后端路由的独立第二来源——**两个来源不一致的地方，正是契约的真实歧义点所在**，
比任何一方单独可信。T-04 的领取者应把它列为交叉核对来源。

**约束**：按 R3，收割仅指「读取其内容作为契约参照」，**不得把 spec 文件本体复制进 AiFamily**
（它们是 TS 测试，`TEST_ORACLE` 的语义是「作为验收判据的来源」而非「迁入的资产」）。
按 R13/R5，由此产出的清单落 `contracts/openapi/`（T-04 已指定的输出位置），
并须自标数据来源，不得呈现为 AiFamily 自有契约。

## Alternatives Considered

### A. 迁入 `apps/web` 作为 AiFamily 的 web 端起点
**支持理由**：三个 web 端（教师/机构/运营）终究要建，有一个既存 TS 项目做起点看似省事；
24 个 spec 已经描述了路由形状，配上组件框架就能跑；且它是唯一覆盖非家庭端场景的前端资产。

**否决理由**：「有一个起点」在这里是错觉。**没有组件框架、没有 bundler 意味着要迁入的不是一个应用，
是一份 tsconfig 加一批测试**——真正的工作量（选框架、建构建链、写组件）一件都没被节省。
同时它会立刻违反交付顺序：34 个 mobile 屏幕当前可工作数为 0，
在第一个端做通之前开第二个端，等于把「零个可用产品」变成「两个不可用产品」。
按 `MIGRATION_PLAN_V2.md` 的批次原则（优先级 = 证据状态 × 三区区域），
一个 `BLOCKED` 且无部署形态的前端不可能排在 Batch 1/2。

### B. `DELETE`，与 `consumer-web` / `ops-web` 同等处置
**支持理由**：既然不是可部署 UI，且已有 mobile 作为唯一前端，简单删掉最干净，
减少一个需要维护判断的条目。

**否决理由**：**证据不支持同等处置。** 那两个的证据是「目录内仅 node_modules，无 package.json，
无源码」（manifest:487）——真正的零。`apps/web` 有 24 个 spec 文件，
且 manifest 自己判定它们「价值更多是后端路由的契约参照」。
按 `DELETE` 的定义（`MIGRATION_PLAN_V2.md` §1：确认零价值）它不满足条件。
把有契约价值的东西按零价值处置，会在 T-04 缺第二来源时才被发现——而那时源仓库可能已不便回查。

### C. 维持 `REVIEW_REQUIRED` / `BLOCKED`，推迟到 web 端立项时裁决
**支持理由**：那时才知道 web 端要什么，裁决质量更高；现在裁决不产生代码改动。

**否决理由**：它已经在 `review_required_index` 里占了一行**九个月都不会动的待办**，
而 `review_required_index` 的价值取决于其中每一项都是真的在等一个近期决定。
一份长期不动的待裁决项会稀释整张清单的信号——下一个人看到 9 项待裁决，
不会逐项判断哪些是真阻塞。更实际的代价是：**推迟裁决会连带推迟那 24 个 spec 的收割**，
而 T-04 现在就需要第二来源。

### D. 只做收割，不改 `frontend_web` 的 disposition
**支持理由**：改动更小，收割是纯增量。

**否决理由**：这会留下一个自相矛盾的登记——同一份源代码既是 `REVIEW_REQUIRED`（还没决定要不要迁）
又已被当作 `TEST_ORACLE` 消费。`SYSTEM_MANIFEST.md` §6 的五类信息区分
（Current Truth / Decision / Specification / Evidence / History）要求一份资产的定性是明确的；
「一半待裁决一半已消费」正是该规则要防的模糊态。

## Consequences

### 正面
- `review_required_index` 少一项长期不动的待办，清单信号变强。
- T-04 获得独立的第二契约来源，且**两来源的差异点被显式定位为契约歧义**，
  这比补充信息更有价值。
- 明确「三个 web 端将来是新建」，堵住「复用 `apps/web` 绕过选型 ADR」这条捷径。

### 负面 / 代价
- 若将来教师端立项，需从零选型建构建链，无既存项目可继承。这个代价是真实的，
  但按替代方案 A 的分析，它本来也没被节省。
- `MIGRATION_MANIFEST.yaml` 需改动（改 1 条 + 增 1 条 + 删 index 1 行），
  而该文件正被并发会话修改（`git status` 显示 modified）。**执行须与其协调。**

### 需要接受的风险
- **本 ADR 含产品面判断**（「不该在 mobile 做通前开第二个端」是交付顺序判断，不是纯技术结论）。
  依据是 `frontend_mobile.blocking_action` 与 34 屏可工作数为 0 这两条实测事实，
  但最终的产品优先级属 project-owner。**若 project-owner 决定优先建教师端，
  本 ADR §1 应被 override**；§2（收割 spec）不受影响，仍然成立。
- 「24 个 spec 是有效契约参照」这一判断我**未逐个读过那 24 个文件**（它们在只读的
  `D:\family-ai` 内），依据是 manifest:475 的既有审计结论。
  T-04 领取者若发现它们实际已严重过期，应回报并可推翻 §2。

## Enforcement

**当前仅为意图，无机械执行——如实记录。**

- 「不建 `frontend/web`」这一条**可机械检验且成本极低**：
  `tests/architecture/` 加一条断言 `frontend/web` 不存在于磁盘，
  或更一般地——`frontend/` 下的每个子目录必须对应 `MIGRATION_MANIFEST.yaml`
  中一条 `disposition: MIGRATE` 的条目（这同时守 R3）。**目前不存在此断言。**
- 「不得以复用 `apps/web` 为由绕过选型 ADR」不可机械检验，靠 review。
- 「spec 文件本体不得复制进仓」部分可检验：
  `test_no_layout_coupling.py` 已拦硬编码的 `50_开发_dev` / `D:\family-ai` 字面量，
  但它扫的是 `.py` 文件；若有人复制 `.spec.ts` 进来，现有护栏不会响。
  可考虑扩展为「AiFamily 内不得出现 `*.spec.ts`」——但这与 `frontend/mobile`
  的 35 个测试文件冲突，需先确认命名差异，本 ADR 不预先规定。

## References

- `governance/MIGRATION_MANIFEST.yaml:471-475`（`frontend_web` 条目与其证据）、`:613`（待裁决索引）
- `governance/MIGRATION_MANIFEST.yaml:483-487`（`frontend_empty_scaffolds`，须与本条区分）
- `governance/MIGRATION_MANIFEST.yaml:460-469`（`frontend_mobile` override 与 `blocking_action`）
- `docs/00_system/CURRENT_PRODUCT_MAP.md` §4（三个 web 端 `PLANNED_NO_CODE`）
- `docs/00_system/TARGET_ARCHITECTURE.md` §6 第 1 项
- `docs/11_delivery/migration/MIGRATION_PLAN_V2.md` §1（disposition 词表定义）、§4（批次优先级原则）
- `docs/11_delivery/TASK_BACKLOG.md` T-04（本 ADR §2 的直接下游）
- `governance/REPOSITORY_CONSTITUTION.md` R3、R5、R13
