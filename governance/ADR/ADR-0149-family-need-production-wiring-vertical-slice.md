# ADR-0149: family_need 的生产环境接线 —— 复用 Journey 的 PostgreSQL Actor Resolver 模式，退役 Fake 仓储的生产候选身份

- **Status**: Accepted（implemented and PostgreSQL-verified 2026-09-02; see ADR-0150 for
  the downstream cross-domain orchestration and course-content wiring this vertical
  slice enabled）
- **Date**: 2026-09-02
- **Deciders**: chief-architect（project-owner 可 override）；project-owner 于同日
  明确授权本次及后续关联任务跳过逐域事前 ADR 审批、改为事后补记（见 ADR-0150 Context）
- **Supersedes**: null
- **Superseded By**: null

## Context

`governance/DOMAIN_REGISTRY.yaml`（`family_need_orchestration` 条目，约第 402–418 行）记录
`status: MIGRATED_TESTED`，`known_gaps` 明确写着：

> "当前使用Fake仓储和dev/test合成身份/同意；PostgreSQL、真实身份/同意存储和FGCN分派仍待接线"

代码实况核对（本次调查）：

1. `backend/domains/family_need/api/dependencies.py` 两个依赖函数
   `get_family_need_actor()` / `get_family_need_service()` 均 `raise HTTPException(503)`，
   注释明确写"process entry point must inject a real actor resolver and a
   repository-backed application service"——这是**故意的** fail-closed 设计，不是遗漏。
2. `backend/domains/family_need/application/service.py`（617 行）的
   `FamilyNeedApplicationService` 编排逻辑（幂等、授权、同意校验、资源缺口判断）已完整，
   依赖三个 Port：`FamilyNeedRepositoryPort` / `FamilyNeedPolicyPort` / `SupplyReferencePort`。
3. `backend/domains/family_need/infrastructure/` 目前只有一个实现：
   `fake_repository.py`（内存字典存储），**零个 PostgreSQL 实现**。
4. `backend/apps/family_api/main.py` 第 212–217 行已 `include_router(family_need_router)`
   并注册异常处理器——路由已挂载、OpenAPI 可见，但依赖未接线，生产环境请求必得 503。

**本仓库已有可复用的先例**，不需要发明新模式：

- `backend/domains/journey/infrastructure/actor_resolver.py`
  `SqlAlchemyJourneyActorResolver` 通过 `identity_sessions → accounts →
  tenant_account_memberships → tenant_family_bindings → account_person_bindings →
  family_memberships` 六表链解析 Bearer token 到 `(actor_id, family_id)`，
  角色限定 `OWNER_GUARDIAN`/`GUARDIAN`，会话过期/撤销校验齐全。
- `backend/domains/journey/infrastructure/sqlalchemy_repository.py` /
  `sqlalchemy_policy.py` 提供了同域内 PostgreSQL 仓储与策略适配器的实现范式。
- `backend/apps/family_api/main.py` 的 `_mount_growth_onboarding()`（第 115–150 行）
  展示了条件挂载的标准写法：dev/test 走 fake runtime + fake actor resolver；生产环境
  仅当存在显式 PostgreSQL URL（`is_postgres_url(configured_url)`）才装生产适配器；
  否则保留路由的 503 默认值——**不静默降级成合成数据**。

这条先例同时是本 ADR 的边界：**只复用模式，不复用表**。`journey` 的六表链服务于其自身
的 `JourneyActor`；`family_need` 的 `FamilyNeedActor`（`api/dependencies.py` 第 19–28 行）
多出 `tenant_id` / `actor_type` / `region` / `environment` 四个字段，解析查询需要为
`family_need` 独立编写，不能直接 import journey 的 resolver（R2：一个 capability 一个
canonical 实现；且两个域是不同的 Port 契约，硬 import 会造成域间耦合）。

## Decision

1. **新增 `backend/domains/family_need/infrastructure/postgres_repository.py`**，
   实现 `FamilyNeedRepositoryPort`（签名以 `domain/ports.py` 现有定义为准），
   持久化 `NeedSignal` / `FamilyNeed` / `NeedProfile` / `SolutionDraft` 四个聚合根。
   落地前必须先在 `database/` 下补迁移文件（当前零个 family_need 表，需新增，
   字段对齐 `domain/entities.py` 与 `domain/value_objects.py` 已有的值对象），
   并跑 `alembic upgrade head` 验证。

2. **新增 `backend/domains/family_need/infrastructure/actor_resolver.py`**，
   `SqlAlchemyFamilyNeedActorResolver`，复用 journey 已验证的六表身份链**查询模式**
   （identity_sessions → accounts → tenant_account_memberships →
   tenant_family_bindings → account_person_bindings → family_memberships），
   补齐 `tenant_id` / `region` / `environment` 的来源字段，产出 `FamilyNeedActor`。

3. **在 `main.py` 新增 `_mount_family_need()`**，镜像 `_mount_growth_onboarding()` 的
   三分支结构：dev/test 装 fake（现有 `fake_repository.py` 原地保留，仅作为 dev/test
   适配器而非"唯一实现"）；生产环境仅当 `is_postgres_url(configured_url)` 为真才装
   `postgres_repository.py` + `actor_resolver.py`；否则维持现有 503 默认值。
   `create_app()` 需新增 `family_need_database_url` 等可选参数，与
   `growth_onboarding_database_url` 同构，供测试以 `dependency_overrides` 之外的方式
   注入真实/伪造依赖。

4. **前端联调选定 UI-02**（`family_need` 对应的第一个 N0→N1 屏幕，见
   `docs/.../APPLICATION_ARCHITECTURE.md` 第 6 行的 UI-02/03/05/09 对接点记录），
   验证真实 HTTP 往返一次（本地起服务 + 真实 PostgreSQL + 该屏幕发起一次
   `POST /families/{id}/needs/signals`），不在本 ADR 内扩展到 N1→N8 剩余端点。

5. **`FamilyNeedPolicyPort` / `SupplyReferencePort` 暂不落地真实实现**——本 ADR
   范围是"身份链 + 持久化 + 一个屏幕"，同意/授权策略与供给目录接线是独立缺口，
   留在 `known_gaps` 里如实记录，不在本次顺手做掉（避免切片膨胀成第二个"治理骨架
   铺完、业务为零"）。

## Alternatives Considered

- **继续横向新增 domain**：否决。会重复"文档完整、代码空壳"的既有模式，
  且不验证治理框架本身的可用性。
- **给 family_need 发明独立的多表身份解析**：否决。journey 的六表链已跑通并有测试，
  重新设计增加不必要的架构分叉；家庭/账户/租户绑定关系是平台级不变量，不应有
  两套并存的解析逻辑（否则未来两个域对"谁能代表这个家庭"给出不一致答案）。
- **直接 import journey 的 `SqlAlchemyJourneyActorResolver`**：否决。返回类型是
  `JourneyActor` 而非 `FamilyNeedActor`，字段不对齐；跨域 import 具体 infrastructure
  类也违反 R2 的"一个 capability 一个 canonical 实现"边界（会让 family_need 的身份
  解析能力实质上寄生在 journey 域里，未来 journey 重构会连带打断 family_need）。
- **一次性把 N1→N8 全部端点都接线**：否决。当前只有 N0→N1（capture）与 N1→N2
  （profile）有 API，其余端点不存在；本 ADR 只对"已存在但未接线"的部分负责，
  不在同一 PR 里新增业务端点（范围爬升，且需求本身未经产品裁决）。

## Consequences

- **正向**：产出仓库第一个"路由挂载 + 依赖真实注入 + PostgreSQL 持久化 + 前端一屏
  真实调用成功"的完整业务能力，验证治理框架（fail-closed 依赖、dev/test 与生产分支
  挂载、DOMAIN_REGISTRY 状态词表）本身是否可用，而不是继续假设它可用。
- **正向**：`known_gaps` 里"PostgreSQL、真实身份/同意存储...仍待接线"这一条可以
  被真实关闭（部分——同意/授权与 FGCN 分派仍留待后续 ADR）。
- **代价**：新增两个文件（`postgres_repository.py`、`actor_resolver.py`）+ 一份
  数据库迁移 + `main.py` 的 `_mount_family_need()`，触及 R3（MIGRATION_MANIFEST 需
  同步 `family_need_orchestration` 的 `known_gaps` 措辞）与可能的 R12（新迁移文件的
  导入路径需走 `backend.domains.family_need.*` 而非裸模块名）。
- **遗留缺口（如实记录，不在本 ADR 内关闭）**：`FamilyNeedPolicyPort` 同意/授权
  真实存储、`SupplyReferencePort` 供给目录接线、FGCN 分派、N1→N8 剩余端点。

## Enforcement

- 完工后 `governance/DOMAIN_REGISTRY.yaml` 与 `governance/MIGRATION_MANIFEST.yaml`
  的 `family_need_orchestration` 条目 `known_gaps` 必须同 PR 更新，移除已关闭的那句、
  保留未关闭的那句（禁止整条删除后不留痕迹）。
- 新增 PostgreSQL 集成测试须在真实数据库连接下运行（非 `metadata.create_all` 临时表，
  参照 CLAUDE.md 对 membership/product_intelligence 同类问题的已知批评）。
- `_mount_family_need()` 的生产分支必须有测试覆盖"无 `DATABASE_URL` 时维持 503"
  与"有 `DATABASE_URL` 时真实可用"两种路径，防止悄悄合并成"生产环境永远走 fake"。

## References

- `governance/DOMAIN_REGISTRY.yaml` → `family_need_orchestration`
- `governance/MIGRATION_MANIFEST.yaml` → `family_need_orchestration`
- `backend/domains/family_need/api/dependencies.py`
- `backend/domains/family_need/application/service.py`
- `backend/domains/journey/infrastructure/actor_resolver.py`
- `backend/apps/family_api/main.py`（`_mount_growth_onboarding`，第 115–150 行；
  `create_app`，第 153 行起）
- `docs/00_system/CURRENT_SYSTEM_BASELINE.md` §4.1
