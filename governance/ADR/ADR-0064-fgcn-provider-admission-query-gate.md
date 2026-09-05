---
id: ADR-0064
title: FGCN 分派使用 provider admission 查询门槛
status: proposed
date: 2026-08-30
decision_owner: project-owner
---

# ADR-0064：FGCN 分派使用 provider admission 查询门槛

## 背景

总体设计把“资格/能力/容量/连续性/偏好匹配”放在服务需求进入 FGCN
之前，并要求“服务无合资格人员时进入待匹配，不虚构已安排”（
`docs/02_business/FAMILY_GROWTH_PLATFORM_MASTER_DESIGN_V1.md` §6.4、§11.2）。
目标架构同时明确：`service` 不拥有“哪个资源最适合这个任务”的判断，
判断属于 AI/查询侧；`Provider`、`Qualification`、`Admission` 仍属于尚未
完成的供给边界（`docs/00_system/TARGET_ARCHITECTURE.md` §4.2、
`docs/04_domains/DOMAIN_ARCHITECTURE.md` §2.2）。

当前 FGCN 已有 Human Gate、Named Action 和持久化 assignment，但此前只从
请求参数取 `provider_id`，没有在 assignment 写入前验证 provider 是否仍为
平台允许的 ACTIVE 资源、是否具备任务要求的能力或服务用途。治理登记也把
“资源准入硬门槛、真实 provider capability relation”列为已知缺口：
`governance/DOMAIN_REGISTRY.yaml` → `service_fgcn_collaboration.known_gaps`。

## 决策

1. FGCN 不拥有 provider 的资格、准入或能力事实；它只依赖一个只读
   `ProviderAdmissionQuery`（内存契约）或 `AsyncProviderAdmissionQuery`（持久化
   应用命令）查询端口。
2. 查询返回的快照必须与请求的 provider 和 assignee kind 一致，
   `admission_status` 必须为 `ACTIVE`，案件 purpose 必须在允许用途内，且任务的
   `required_capability_keys` 必须是快照能力集合的子集。缺失、格式错误、查询失败
   或任一条件不满足都 fail-closed，不创建 assignment、任务状态变化或业务审计。
3. 门槛位于 Human Gate 接受之后、`TaskAssignment` 写入之前；因此 AI 仍只能
   提出 Recommendation/ModelDraft，人工仍决定是否接受，provider admission 只
   是事实落地前的最终资格检查。
4. 未配置查询端口时使用拒绝型默认实现；不能因为测试或旧调用方没有传入端口而
   隐式放行。相同 `NamedActionRequest` 的已持久化幂等回放仍先返回原 assignment，
   不把状态已经成功落地的重放变成新的资格决策。
5. 任务能力要求复用既有 `service_tasks.required_capability_keys` 列，不增加
   第二套供给存储或新的迁移；领域 `ServiceTask` 在保存/加载时保持该字段。

## Alternatives Considered

### 只在 HTTP 提案端点检查

支持理由：可以尽早拒绝明显无效的候选，减少人工审核任务。

否决理由：内部 worker、重放和未来非 HTTP command 仍可能绕过门槛；提案时的
准入结果也可能在人工确认后过期。因此 HTTP 检查可以作为优化，但不能代替
拥有事实写入权的 application command 的最终检查。

### FGCN 直接 import provider/teacher repository

支持理由：实现路径短，能直接读取资格和能力表。

否决理由：违反领域边界和 R2；FGCN 会复制供给方事实所有权，并把未来 provider
域的存储方案固化到协作域。Query Port 保留了跨域最小读接口。

### 缺少准入数据时默认允许

支持理由：可以保持旧的内存测试和开发环境调用方不变。

否决理由：这会把“未接线”变成“已授权”，与 R8、R14 和“无合资格人员不虚构
已安排”的要求相冲突。默认拒绝，测试显式提供 fake，才能保持环境行为等价。

## Consequences

### 正面

- assignment 写入前具有可执行的 ACTIVE/用途/能力关系门槛；
- 同步内存契约、异步 durable command 和 worker 消费路径使用同一拒绝语义；
- 不新增 provider 事实存储，不触碰共享 Registry 或其他 domain 的 canonical path；
- 失败发生在业务写入之前，便于审计、重试和人工处理。

### 负面 / 代价

- 生产必须接入真实 provider admission 查询端口；未接线的 API 会继续拒绝；
- 现有测试和 fake 必须显式声明 ACTIVE provider、用途和能力，不能依赖隐式 allow；
- provider 准入快照仍可能在查询后变化，生产需要由拥有供给事实的边界提供合适的
  一致性/版本策略；本 ADR 不把查询快照升级为 provider 事实。

## Enforcement

- `backend/domains/service/fgcn/admission.py`
- `backend/domains/service/fgcn/contracts.py`
- `backend/domains/service/fgcn/application.py`
- `backend/domains/service/fgcn/engine.py`
- `backend/domains/service/fgcn/persistence.py`
- `backend/domains/service/fgcn/workflow_worker.py`
- `backend/domains/service/fgcn/api/dependencies.py`
- `backend/domains/service/fgcn/api/routes.py`
- `tests/domains/service/fgcn/test_fgcn_flow.py`
- `tests/domains/service/fgcn/test_persistence.py`
- `tests/domains/service/fgcn/test_workflow_worker.py`
- `tests/apps/family_api/test_fgcn_routes.py`

## References

- `docs/02_business/FAMILY_GROWTH_PLATFORM_MASTER_DESIGN_V1.md` §6.4、§11.1–§11.3
- `docs/00_system/TARGET_ARCHITECTURE.md` §4.2
- `docs/04_domains/DOMAIN_ARCHITECTURE.md` §2.2
- `governance/REPOSITORY_CONSTITUTION.md` R2、R8、R9、R14
