# ADR-0011: `backend/platform/identity` 与业务身份域的边界，以及 tenancy 的落点

- **Status**: Accepted
- **Date**: 2026-08-29
- **Deciders**: chief-architect（project-owner 可 override）
- **Supersedes**: null
- **Superseded By**: null

## Context

`docs/00_system/TARGET_ARCHITECTURE.md` §6 把「平台 `identity` 与业务身份域的边界」列为等架构师裁决项，
理由记为「两条 registry 条目共用一个 canonical path」。`governance/ADR/README.md:44` 亦将
「`platform_actor_tenant_context` 与 `auth_identity` 是否长期共用 `backend/platform/identity`」
列名为必须写 ADR 的触发。本 ADR 是该裁决。

**先纠正一个流传中的误读**：这不是一个 R2 违规。`DOMAIN_REGISTRY.yaml:43-49` 的
`platform_actor_tenant_context.r2_boundary_note` 已经把边界显式切开，并写明
「两个*不同* capability 有意共享一个目录属 manifest 级决定，不是 R2 违规；R2 禁止的是同一
capability 指向两个『真实位置』」。`tests/architecture/test_domain_registry.py::
test_no_capability_has_multiple_canonical_paths` 的 docstring 与此一致。
**待裁决的是「共享目录是否长期保留」这个开放项，不是一个待修的违规。**
把它当违规处理会导致一次不必要的搬迁。

实测现状：

1. `backend/platform/identity/` 磁盘上**只有** `context.py`（100 行）+ `__init__.py`。
   内容是 4 个纯值对象：`ActorType`（HUMAN/AI/SYSTEM，`context.py:26-31`）、
   `TenantStatus`（`:34-39`）、`ActorContext`（`:42-83`，frozen+slots）、
   `TenantContext`（`:86-99`）。模块 docstring `:1-18` 明确自述「pure value objects:
   no database access, no HTTP, no model provider calls」。
   **业务身份对象（Account / IdentitySession / OtpChallenge）一个都不存在。**

2. `auth_identity` 条目（`DOMAIN_REGISTRY.yaml:274-284`）`status: NOT_STARTED`，
   `scope` 声明它将拥有 Account / IdentitySession / OtpChallenge 与 4 个 `/auth/*` 端点，
   `known_gaps` 记「Mobile 硬依赖的 4 个 `/auth/*` 端点全部缺失」。
   **所以「共享」目前是名义上的：两条登记指向同一目录，但只有一条有代码。**

3. 那 4 个 `/auth/*` 端点当前**实际存在于 `backend/domains/assessment/api.py:68-154`**
   （`/auth/account-session`、`/auth/me`、`/auth/contexts`、`/auth/session/revoke`），
   token 存在 `AssessmentApiState.tokens` 这个进程内 dict 里（`api.py:40`）。
   **身份能力正寄居在 assessment 域内**——这是比「两条登记共享目录」严重得多的真实边界问题，
   而它没有出现在任何一份开放裁决清单里。

4. `platform_tenancy` 条目（`:89-103`）`canonical_path: backend/platform/identity`，
   `status: MIGRATED_STRUCTURE_ONLY`，其 `drift_correction:97-102` 已如实记录：
   `MIGRATION_MANIFEST.yaml` 的 target 写 `backend/platform/tenant`，**该目录不存在**；
   registry 按实况登记为 `identity`，并要求「租户成为独立聚合需先出 ADR」。

## Decision

### 1. 平台层与业务层按「是否含业务生命周期」切分，不按名字切分

`backend/platform/identity/` **长期保留**，且**永久限定**为不含业务语义的上下文原语：
`ActorType` / `ActorContext` / `TenantStatus` / `TenantContext` 及其后继值对象。
判据一条：**它不得拥有任何有生命周期状态机的对象，不得有 repository，不得四层分层。**
平台层的存在理由是让 authorization / audit / consent / idempotency 共享同一个「谁在作用于哪个租户」
的类型；一旦它开始拥有 Account 的注册/登录/注销流转，这个理由就不成立了。

### 2. 业务身份域落 `backend/domains/identity`，不再共用平台目录

`auth_identity` 的 `canonical_path` 由 `backend/platform/identity` 改为
**`backend/domains/identity`**（四层结构 `api/application/domain/infrastructure`，
遵 `docs/10_engineering/ENGINEERING_ARCHITECTURE.md` 的域四层约定）。
拥有 Account / IdentitySession / OtpChallenge / GuardianRelation 与 4 个 `/auth/*` 端点。

**裁决理由不是「共享目录违规」（它不违规），而是**：`auth_identity` 现在
`status: NOT_STARTED`，**是零成本改登记的最后时刻**。等它长出 2000 行再拆，
就是一次真实搬迁 + 一次 R12 导入路径重写。现在改一行 YAML，将来省一个 PR。
这类「趁还没写就把位置定对」的决定，是架构师在 NOT_STARTED 阶段最该做的事。

### 3. tenancy 的落点：删掉不存在的 `backend/platform/tenant`，业务侧归 `backend/domains/tenancy`

- `MIGRATION_MANIFEST.yaml → platform_actor_tenant_context` 的 target 列表中
  **删除 `backend/platform/tenant`**（该目录不存在且不会被创建），消除
  `drift_correction` 所记的漂移根源。
- `TenantContext` / `TenantStatus` 值对象**留在** `backend/platform/identity/context.py`，
  不为两个值对象单开一个平台目录。`platform_tenancy` 条目的 `canonical_path`
  保持 `backend/platform/identity`，与实况一致。
- 真实租户聚合（`Tenant` / `TenantFamilyBinding` / `TenantAccountMembership`
  及六层绑定链判定，见该条目 `test_oracle:103`）归 **`backend/domains/tenancy`**，
  与身份域并列。理由同 §2：租户生命周期与套餐是业务语义，不是平台原语。

### 4. 附带裁决：`/auth/*` 端点必须从 assessment 域迁出

现状（`assessment/api.py:68-154` + `:40` 的进程内 token dict）是 vertical slice 的合理产物，
但它使 assessment 域拥有了身份能力，构成实质的域边界越界。

**裁决**：`/auth/*` 四个端点与 token 存储在 `backend/domains/identity` 建立时迁出 assessment。
在迁出前，`assessment/api.py` 的这段代码**必须带一条指向本 ADR 的注释标注它是临时寄居**，
否则下一个读者会把它当作既定设计。这一条不阻塞 T-05，但 T-05 的领取者必须知道
它接手的 `api.py` 里有一段不属于该域的代码。

## Alternatives Considered

### A. 长期保留共享目录（`platform/identity` 同时住平台原语与业务身份）
**支持理由（不弱）**：registry 已经用 `r2_boundary_note` 把职责边界写清楚了，且架构测试确认
这不违 R2。共享目录减少一层目录嵌套，`ActorContext` 与 `Account` 天然相关，
放在一起读代码时上下文更连贯。且**零改动成本**——现在什么都不用做。

**否决理由**：`r2_boundary_note` 是一条只有人会读、机器不会执行的说明。
它现在有效是因为业务身份还没写；一旦 `Account` 落进同一目录，
「平台层不含业务语义」这条判据就只剩注释在守。更具体地：
`backend/platform/` 下六项内核**刻意都不四层分层**（`ENGINEERING_ARCHITECTURE.md` 明确区分
platform 与 domains 的分层约定），而业务身份域必须四层。
让一个目录同时是「不分层的平台原语」和「四层的业务域」，
会让任何针对目录结构的架构检查都无法表达。

### B. 把 `ActorContext` 也移进 `backend/domains/identity`，取消平台 identity
**支持理由**：只有一个 identity 位置，最简单，不需要维护「哪个是平台哪个是业务」的判断。

**否决理由**：`backend/platform/authorization/policy.py:25` 直接
`from backend.platform.identity.context import ActorContext, ActorType`。
audit / consent / idempotency 同样依赖它。若 `ActorContext` 住进业务域，
则**平台层将依赖业务域**——依赖方向反转，且 `backend/domains/identity` 会成为
所有平台模块的上游，任何域都无法在不拉入身份域的情况下使用授权。
这正是 `context.py:1-9` 的模块 docstring 所记的、要避免的失败模式
（源仓库的 `ActionContext` 私有于 membership 一个域）。

### C. 为两个值对象单开 `backend/platform/tenant`（即 manifest 原本写的那个目录）
**支持理由**：与 manifest 现有 target 一致，不需要改 manifest；且租户概念确实独立于 actor。

**否决理由**：该目录在磁盘上**从不存在**，manifest 写它是一次未落地的意图，
`drift_correction` 已经把这件事记为漂移。为 `TenantContext` + `TenantStatus`
两个 dataclass 建一个包，换来的是一个新的跨包导入；而 `ActorContext.tenant_id`
本就是必填字段（`context.py:55`），二者在类型层已经耦合。
**修漂移的正确方向是删掉那个不存在的 target，不是把目录建出来迎合它。**

## Consequences

### 正面
- `auth_identity` 在 `NOT_STARTED` 阶段就定对位置，避免将来一次真实搬迁 + R12 导入重写。
- 平台层「不含业务生命周期」有了可陈述的判据，而非只有一条 registry 注释。
- 消除 `backend/platform/tenant` 这个不存在目录带来的 manifest 漂移。
- 暴露并记录了一个此前没被列入任何清单的真实越界：`/auth/*` 寄居 assessment 域。

### 负面 / 代价
- `DOMAIN_REGISTRY.yaml` 与 `MIGRATION_MANIFEST.yaml` 均需改动，触及正被并发会话修改的
  `MIGRATION_MANIFEST.yaml`（`git status` 显示为 modified）。**执行必须与该会话协调**，
  不得在其 WIP 上直接改。
- 域数量增加：`backend/domains/identity` 与 `backend/domains/tenancy` 两个新登记。
  按 ADR-0005 的分类它们属**支撑域**，不要求 AI 原生。
- `/auth/*` 迁出是一次会破坏 `tests/apps/family_api/test_assessment_routes.py` 的改动，
  代价落在 T-05 或其后继任务上。

### 需要接受的风险
- 本 ADR 在两个域都还没有一行代码时就定了它们的位置。若 `auth_identity` 实际迁入时
  发现 Account 与 Tenant 的绑定链无法在两个域间干净切分（`test_oracle` 提到六层绑定链），
  可能需要合并为单一 `backend/domains/identity`。**这种情况下应推翻本 ADR §3 而非硬拆**。
- 「平台层不得有生命周期状态机」这条判据目前无机械执行（见 Enforcement）。

## Enforcement

**部分可机械执行，当前一条都未落地——如实记录。**

可机械检验且应补的（成本从低到高）：

1. **`backend/platform/**` 不得 import `backend.domains.*`**（守 §B 的依赖方向）。
   与本批新增的 `tests/architecture/test_ai_runtime_isolation.py` 同一模式，
   可合并进同一测试文件的第二个用例。**低成本，应尽快补。**
2. **`backend/platform/**` 下不得出现 `infrastructure/` 或 `api/` 子目录**
   （守「平台层不四层分层」）。纯路径检查，成本极低。
3. **status 为 `NOT_STARTED` 的条目，其 `canonical_path` 不得已存在代码**——
   可捕获「登记说没开始、磁盘上已经有了」这类漂移。

不可机械检验、只能靠 review 的：
- 「某个对象是否含业务生命周期」是语义判断。一个叫 `ActorContext` 的类
  完全可以被加上 `status` 字段和状态流转方法，而所有路径检查全绿。
  这条边界最终靠本 ADR 的判据 + code review。

## References

- `governance/DOMAIN_REGISTRY.yaml:34-49`（`platform_actor_tenant_context` 与 `r2_boundary_note`）
- `governance/DOMAIN_REGISTRY.yaml:89-103`（`platform_tenancy` 与 `drift_correction`）
- `governance/DOMAIN_REGISTRY.yaml:274-284`（`auth_identity`，`status: NOT_STARTED`）
- `backend/platform/identity/context.py:1-18, 26-99`
- `backend/platform/authorization/policy.py:25`（平台内部对 identity 的依赖）
- `backend/domains/assessment/api.py:40, 68-154`（`/auth/*` 寄居 assessment 的证据）
- `docs/10_engineering/ENGINEERING_ARCHITECTURE.md`（platform 与 domains 的分层约定差异）
- `docs/00_system/TARGET_ARCHITECTURE.md` §6 第 5 项；`governance/ADR/README.md:44`
- `governance/REPOSITORY_CONSTITUTION.md` R2、R12；ADR-0005 §2（支撑域不要求 AI 原生）
