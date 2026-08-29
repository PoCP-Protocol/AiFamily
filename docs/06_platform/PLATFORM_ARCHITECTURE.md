---
id: PLT-ARCH-001
title: 平台内核架构总览
type: platform
status: current
version: 1.0
owner: chief-architect
created: 2026-08-29
updated: 2026-08-29
canonical: true
supersedes: null
superseded_by: null
---

# 平台内核架构总览 (Platform Kernel Architecture)

**本文件描述的是代码里已经存在的东西，不是目标态。** 每条断言都从 `backend/platform/**` 与 `tests/platform/**` 反向读出来；写不出代码证据的部分一律进"已知缺口"节，不写成"将会"。

> 状态口径：截至 **2026-08-29**。`backend/platform/persistence/session.py` 与 `backend/platform/audit/` 在本文件成稿时正被并发任务（T-03 Alembic / T-07 读取留痕）改动，本文件记录的是当时磁盘上的最新状态；两处已在对应文档里显式标注。

---

## 1. platform 与 domain 的区别（最关键的一条）

```text
platform  = 共享技术能力（谁在操作、允不允许、有没有同意、留不留痕、会不会重放、事务边界）
domain    = 业务真相（家庭是什么、成长是什么、什么算一次评估、什么算一次履约）
```

判据（三问，全部为"是"才属 platform）：

1. **它对业务语义无知吗？** `PolicyEngine` 不知道 `family` 与 `order` 有什么不同，它只见 `resource_type: str`。`ConsentGate` 不知道 `assessment` 是什么，它只比对 `ConsentPurpose` 枚举。反例：判断"家长能否看 14 岁以上孩子的数据"需要年龄与监护关系语义 → 属 domain，不属 platform。
2. **换一个业务域它一字不改还能用吗？** `ActorContext` / `IdempotencyKey` / `UnitOfWork` 是。
3. **它不做业务决策，只提供做决策的手段吗？** `ActorContext.is_ai` **只报告事实**，不决定 AI 能不能写；决定在 `PolicyEngine`（`human_only=True`），而 `human_only` 该挂在哪些 action 上是 domain 的事。

**反向红线**：platform 目录里不得出现家庭/成长/订单语义。目录职责见 `docs/12_governance/DOCUMENT_GOVERNANCE.md` §2（`docs/06_platform/` 放"平台内核规格"，不放"业务规则、Domain 语义"）。

## 2. 六项内核清单与真实成熟度

| 内核 | 代码 | 测试 | 文档 | Registry status |
|---|---|---|---|---|
| identity | `backend/platform/identity/context.py` | `tests/platform/identity/` 6 测 | `IDENTITY.md` | `IMPLEMENTED_TESTED` |
| authorization | `backend/platform/authorization/policy.py` | `tests/platform/authorization/` 5 测 | `AUTHORIZATION.md` | `IMPLEMENTED_TESTED` |
| consent | `backend/platform/consent/{models,gate}.py` | `tests/platform/consent/` 6 测 | `CONSENT.md` | `IMPLEMENTED_TESTED` |
| audit | `backend/platform/audit/{models,recorder}.py` | `tests/platform/audit/` | `AUDIT.md` | `IMPLEMENTED_TESTED` |
| idempotency | `backend/platform/idempotency/keys.py` | `tests/platform/idempotency/` 4 测 | `IDEMPOTENCY.md` | `IMPLEMENTED_TESTED` |
| persistence | `backend/platform/persistence/{session,unit_of_work}.py` | `tests/platform/persistence/` 4 测 | `PERSISTENCE.md` | `IMPLEMENTED_TESTED` |

**`IMPLEMENTED_TESTED` 的含义（见 `governance/CAPABILITY_REGISTRY.yaml` 的 `enums.status`）**：有代码、有测试、**但未承载任何生产流量**。六项全部处于这一档，无一项达到 `PRODUCTION`。任何"平台内核已就绪"的说法必须附上这个限定 —— 它们是可运行的原语，不是被真实业务验证过的基础设施。

## 3. 六项如何协作（一次假想的写操作）

以下是六项内核**被设计成**如何串联的调用序列。**注意：这条完整链路目前没有任何生产调用方** —— AiFamily 尚无业务 API（`docs/00_system/CURRENT_SYSTEM_BASELINE.md`）。唯一真实接线的只有第 6 步的一个退化用法：`/ready` 端点调 `SqlAlchemyUnitOfWork.ping()`（`backend/apps/family_api/routes.py:29`）。

```text
1. identity      构造 ActorContext(actor_id, actor_type, tenant_id, correlation_id)
                 └─ 不可变。correlation_id 在此确定，后续每一步复用同一个值

2. authorization PolicyEngine.check(actor, action, resource_type) → Decision
                 └─ 未注册 = DENY。human_only 的 action 对 is_ai actor 无条件 DENY

3. consent       ConsentGate.check(subject_id, purpose, grants)
                 └─ grants 必须是调用方**刚读出来的**；Gate 自身不持有任何状态

4. idempotency   IdempotencyStore.check_and_reserve(IdempotencyKey(...))
                 └─ 返回 False = 这次操作已经发生过，不要重复副作用

5. persistence   async with SqlAlchemyUnitOfWork() as uow:  ← 事务边界从这里开始
                     ...domain 写入...
                     audit 写入          ← 与 domain 写入同一事务（R6 的前置条件）
                     await uow.commit()

6. audit         AuditEvent(action_kind=MUTATION, before=..., after=..., reason=...,
                            correlation_id=<第1步同一个值>)
                 └─ 当前只落 AuditRecorder 的内存 buffer，**尚未真的进第 5 步的事务**
```

**这条链上最关键的未闭合处**：第 5 步与第 6 步应当共享一个事务，但 `AuditRecorder` 目前只写内存 list，`flush()` 是 no-op（见 `AUDIT.md`）。也就是说 **R6"无审计不得改状态"目前在机制上还不成立** —— 域写入可以成功而审计记录随进程退出而消失。这是六项内核里最严重的单点缺口。

**顺序不可交换的地方**：
- 2 在 3 之前：连操作权限都没有的 actor，不该有机会去读 consent 状态（读 consent 本身就泄露信息）。
- 4 在 5 之前：幂等预留必须先于产生副作用，否则重放会在预留成功前就写完了。
- 1 的 `correlation_id` 贯穿全程：这是 audit 记录能被串成一次操作的唯一凭据。

## 4. 六项内核的公共设计约定

从代码里读出来的、六项一致遵守的三条：

1. **值对象一律 `@dataclass(frozen=True, slots=True)`**。`ActorContext` / `TenantContext` / `ConsentGrant` / `AuditEvent` / `IdempotencyKey` / `Decision` / `PolicyRule` 全部如此。理由写在 `identity/context.py:46`：后台任务要"升级成 system actor"必须**新建实例**，不能翻某个字段 —— 否则审计链无法诚实回答"谁真的发起了这次操作"。
2. **不变量在 `__post_init__` 里，不在调用方**。空 `actor_id`、空 `tenant_id`、空 `correlation_id`、空 `consent_id`、空 `IdempotencyKey.value` 一律构造即 `ValueError`。设计意图是"不合规的记录构造不出来"，而不是"构造出来以后再校验"。
3. **纯内存、无 I/O 的模块不持有状态**。`ConsentGate.check` 是 `@staticmethod`，`PolicyEngine` 只持规则不持决策缓存。理由写在 `consent/gate.py:6`：撤回必须立即生效，而"没有任何东西能过期"的最强保证是"根本不存东西"。

## 5. 平台内核共同的已知缺口

按严重度排序，逐条附代码证据：

1. **audit 未持久化 → R6 目前不成立**。`AuditRecorder.flush()` 返回计数、不写库、不清 buffer（`audit/recorder.py:107-115`）。见 `AUDIT.md` §缺口。
2. **六项内核之间没有任何"必须按序调用"的强制**。第 3 节的序列是设计意图，代码里**没有编排层**：没有一个 `CommandHandler`/中间件强制"写操作必先过 authorization 再过 consent 再留 audit"。domain 代码完全可以绕过全部六项直接开 session 写库。这不是理论风险 —— 编排层不存在，就没有护栏（R14）。
3. **`TenantContext` 是孤立的**。`ActorContext.tenant_id` 是裸 `str`，与 `TenantContext.tenant_id` 之间没有任何代码强制两者一致；`TenantContext.is_active`（suspended/archived 租户）当前**无任何调用方**。也就是说"暂停的租户不能操作"目前不是被执行的规则。
4. **没有行级租户隔离**。`SqlAlchemyUnitOfWork` 不注入 tenant filter，无 RLS。多租户隔离目前完全依赖 domain 层自己在每条查询里手写 `where tenant_id = ...`，而这一点没有任何测试或检查器覆盖。
5. **`IdempotencyStore` 只有内存实现**（`idempotency/keys.py:48`），进程重启即失忆。见 `IDEMPOTENCY.md`。
6. **`docs/06_platform/` 与代码的同步无机械检查**。`DOCUMENT_GOVERNANCE.md` §7 要求授权规则变更同步本目录，但该检查未在 CI 实现（同文件 §9 待办 4）。本目录的准确性目前只靠人工。

## 6. Registry 与治理对应关系

| 内核 | `governance/CAPABILITY_REGISTRY.yaml` capability | `governance/DOMAIN_REGISTRY.yaml` domain |
|---|---|---|
| identity | `resolve_actor_context` | `platform/identity` |
| authorization | `authorize_action` | `platform/authorization` |
| consent | `check_consent` | `platform/consent` |
| audit | `record_audit_event` | `platform/audit` |
| idempotency | `reserve_idempotency_key` | `platform/idempotency` |
| persistence | `unit_of_work_transaction` | `platform/persistence` |

**已发现的 registry 漂移（本任务未修，属他人范围）**：`CAPABILITY_REGISTRY.yaml` 的 `record_audit_event` 条目 `known_gaps` 仍写"《未成年人网络保护条例》第36条要求读取访问也须留痕，尚未实现"，但代码已经实现（`AuditActionKind.READ` + `AuditRecorder.record_read`，T-07 产出）。该条 `known_gaps` 应删或改写。见 `AUDIT.md`。

上位约束：`governance/REPOSITORY_CONSTITUTION.md` R6（审计）/ R7（不直连模型供应商）/ R9（AI 不写 canonical 事实）；`docs/12_governance/COMPLIANCE_HARD_CONSTRAINTS.md` §5 / §8。
