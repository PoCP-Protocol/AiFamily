# ADR-0150: 需求闭环的跨域履约协调器 + 课程内容复用 product_intelligence 治理生命周期（事后补记）

- **Status**: Accepted（implemented and PostgreSQL-verified 2026-09-02）
- **Date**: 2026-09-02（补记；实际实现时间同日）
- **Deciders**: project-owner（明确授权跳过逐域事前 ADR 审批）
- **Supersedes**: null
- **Superseded By**: null

## Context —— 为什么是事后补记，不是事前审批

project-owner 在同一次会话内两次明确指示：（1）"按照业务场景驱动，全流程业务闭环尽快完成
系统的开发"；（2）在被问及"这次的进度 vs 合规流程（ADR 先写、registry 同步、严格按
R1–R14）应该怎么处理"时，明确选择"**跳过 ADR 流程，事后补记**"。这与仓库铁律 #8（无 ADR
不做架构决策）字面冲突，但铁律本身承认 project-owner override；本 ADR 是那次 override 的
事后记录，覆盖本次会话内实际做出的、原本需要事前 ADR 的两个架构决策。

背后的业务驱动是具体的：`docs/00_system/CURRENT_SYSTEM_BASELINE.md` 记的"零业务 API 可用"
状态，如果继续逐域走完整 ADR 审批再落地，闭环打通的速度会被流程拖慢；project-owner 判断
"先验证治理框架本身是否可用"这件事的时间价值高于"每一步都先审批"。

## 已完成的现状（ADR-0149 的产出，作为本 ADR 的前提）

`family_need` 域已有真实 PostgreSQL 仓储、`SqlAlchemyFamilyNeedActorResolver`、Triple P 式
`InterventionTier` 五级分级判断（`derive_intervention_tier`），并在真实 PostgreSQL（Docker
`docker-compose.dev.yml`，端口 55442）上验证过 round-trip、乐观锁冲突、幂等约束、跨租户隔离。

## Decision 1 —— 跨域履约协调器放在 composition root，不放进任一 domain

**决策**：新增 `backend/apps/family_api/orchestration/need_fulfillment_flow.py`，暴露
`fulfil_confirmed_draft()`：接收一个 `commercial_intent=true` 的 `SolutionDraft`，依次调用
`commerce.application.commands.submit_order_intent`（PRODUCT 组件）与
`service.application.commands.submit_booking_request` / `confirm_booking_request`
（SERVICE 组件），返回 `FulfillmentResult`（`order_intent_id` / `booking_id` /
`failed_step` / `failure_reason`）。

**为什么不放进 family_need**：`family_need` 的 `SupplyReferencePort` 存在的唯一理由就是让
该域永远看不到 `commerce`/`service` 的具体类型——只看到自己的 `SolutionComponentRef`。履约
（真的下单、真的预约）不同：它天然要求依次调用两个域的 application 层，把这段逻辑塞进
`family_need` 会让它对另外两个域产生编译期依赖，违反已有的端口隔离设计。放进 `commerce` 或
`service` 同样不对称——履约动作不"属于"任何单一域，它是三个域交汇的那一刻。

**一致性代价的明确记录（不隐藏）**：不做分布式事务补偿。PRODUCT 步骤成功、SERVICE 步骤失败时，
函数如实返回 `order_intent_id` 已填、`booking_id` 为空、`failed_step="service_booking"`，
不自动回滚已创建的订单意向。Commerce 订单意向按幂等键设计，重试履约调用是安全的，但本模块自身
不做重试或补偿——这是已知债务，不是被掩盖的缺陷。

## Decision 2 —— 课程内容复用 product_intelligence 治理生命周期，不新建 course 域

**决策**：课程/课件（`CourseContent`）作为 `backend/domains/product_intelligence/` 现有治理
生命周期（草稿 → Human Gate 审核 → 发布）下的新聚合，复用既有 `EvidenceClaim` 的
`CONTENT_ACCURACY` 分类与 `PUBLISH_COURSE_CONTENT` Named Action，不复用 `ProductComponent`
（纯商品元数据模型，无教学内容字段——章节/知识点/媒体资料等）。

**支撑依据**：
1. `ProductPackage`/`ProductComponent` 经代码核查（非文档核查）证实是"卖什么"的元数据模型，
   没有任何教学内容字段，硬塞进去会削得勉强。
2. `family_need` 的 `SupplyShape` 枚举里 `SOLUTION` 这个值此前定义了但从未有适配器实现——
   课程恰好落在这个位置，不需要新增枚举值去改 7 处已有的 exhaustive 白名单判断点
   （`wiring.py` 的路由字典、`policies.py` 的 if-elif、两个既有 adapter 的 `_SUPPORTED_SHAPES`）。
3. `product_intelligence` 的证据核验（十种 claim 类型、Receipt 结构化受理单据）与 Human Gate
   审核，正是课程"内容要过审才能发布"所需要的治理骨架，不必重新发明。

**新增能力**（`backend/domains/product_intelligence/`）：
- `domain/course_content.py`：`CourseContent` 聚合根，状态机 DRAFT → UNDER_REVIEW →
  PUBLISHED/RETIRED，九件套精简为 problem/assessment/goal/lessons/tool/ai_coach/
  review/outcome。
- `application/course_publication.py`：草稿创建/提交审核/人工决定/发布查询，接入
  `InMemoryHumanGate`。
- `application/course_completion.py`：`mark_course_completed_for_family`——刻意不是状态机，
  只有一个工厂函数；不做逐课时进度追踪（"标记整门课完成"是本次要证明闭环可行的最小动作，
  不是功能完整度声明）。
- `infrastructure/course_content_postgres_repository.py` + 迁移
  `database/migrations/versions/0056_course_content.py`：真实 PostgreSQL 持久化，已在
  disposable 数据库上验证 upgrade/downgrade/round-trip。
- `backend/domains/family_need/infrastructure/course_supply_adapter.py`：
  `CourseSupplyAdapter` 实现 `SupplyReferencePort`，`_SUPPORTED_SHAPES = {SOLUTION}`，
  只依赖 `list_published_courses` 只读可调用对象（`PublishedCourseContentQuery` Protocol），
  不 import 任何具体仓储类型。

**已知简化，明确记录**：
- 课程内容目前是单一共享目录（`CourseSupplyAdapter.resolve_component` 显式
  `del tenant_id, region, locale`），不按租户隔离——这与 `CourseSupplyAdapter` 注释里
  "not modelled by the course read model today" 的说法一致，是记录在案的简化，不是遗漏。
  `FulfillmentDeps.course_catalog_tenant_scope` 字段承载的是"课程目录的发布方租户"，不是
  "使用课程家庭的租户"——两者概念不同，混用会导致 `mark_course_completed_for_family` 找不到
  课程（本次实现过程中真实撞到过这个 bug，修复方式是把发布方租户作为独立字段显式传递，
  而不是猜测性地复用家庭的 `tenant_id`）。
- Human Gate 在生产环境全仓库范围内都没有 PostgreSQL 实现，因此课程发布路由的生产分支
  维持 fail-closed，不是本次要解决的范围。

## Consequences

- 需求闭环第一次端到端可运行：家长描述问题 → 系统判定干预强度 → 匹配到真人服务或已发布课程 →
  确认生成真实订单意向/预约 → 服务/课程完成 → journey 留下可查询的回访记录。全链路有
  `tests/apps/family_api/test_need_fulfillment_e2e.py` 覆盖，且核心持久化路径（family_need、
  course_content、alembic 全链）已在真实 PostgreSQL 上验证。
- 本次真实数据库验证过程中发现并修复了三个与本 ADR 决策本身无关但影响其可验证性的既有缺陷
  （测试用错 alembic `Operations.context()` API 导致所有网关式 PostgreSQL 集成测试从未真正
  跑过；`append_event` 遇到预期内的幂等冲突会毒化整个数据库事务；两处迁移链清单/对象计数表
  忘记登记新迁移）——这些修复已包含在同批交付中，不再单独开 ADR，因为它们是"让既有测试如实
  反映现状"而非新架构决策。

## Enforcement

- `governance/DOMAIN_REGISTRY.yaml` 与 `governance/MIGRATION_MANIFEST.yaml` 的
  `family_need_orchestration` 与新增 `course_content` 条目已在本次同批更新，known_gaps
  措辞与本 ADR 一致。
- 后续任何人接手 N3→N8 剩余端点、FGCN 分派、或课程按租户隔离，应先读本 ADR 与 ADR-0149，
  不应假设当前实现已覆盖这些范围。

## References

- ADR-0149（family_need 生产接线，本 ADR 的前提）
- `backend/apps/family_api/orchestration/need_fulfillment_flow.py`
- `backend/domains/product_intelligence/domain/course_content.py`
- `backend/domains/product_intelligence/application/course_completion.py`
- `backend/domains/family_need/infrastructure/course_supply_adapter.py`
- `backend/domains/family_need/api/fulfillment_dependencies.py`
  （`course_catalog_tenant_scope` 字段的设计说明）
- `tests/apps/family_api/test_need_fulfillment_e2e.py`
- `governance/DOMAIN_REGISTRY.yaml` → `family_need_orchestration`, `course_content`
- `governance/MIGRATION_MANIFEST.yaml` → `family_need_orchestration`, `course_content`
