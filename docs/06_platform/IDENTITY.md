---
id: PLT-IDENTITY-001
title: 平台内核规格 — Identity
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

# Identity — ActorContext / TenantContext

**代码**：`backend/platform/identity/context.py`（99 行）
**测试**：`tests/platform/identity/test_context.py`（6 个测试）
**Registry**：`governance/CAPABILITY_REGISTRY.yaml` → capability `resolve_actor_context`（`status: IMPLEMENTED_TESTED`）
**Domain registry**：`governance/DOMAIN_REGISTRY.yaml` → `platform/identity`

本文件从代码反向记录实际契约。写不出代码证据的一律进"已知缺口"。总览与协作关系见 `PLATFORM_ARCHITECTURE.md`。

---

## 1. 实际提供什么

四个导出符号（`backend/platform/identity/__init__.py`）：`ActorContext` / `ActorType` / `TenantContext` / `TenantStatus`。

### 1.1 `ActorType`（StrEnum）

```text
HUMAN  = "human"     人
AI     = "ai"        AI 系统
SYSTEM = "system"    平台内部任务/调度
```

三值封闭。没有 `SERVICE` / `ANONYMOUS` / `UNKNOWN` —— 加第四值需要同时给出"它与这三个如何区分"的不变量。

### 1.2 `ActorContext`（frozen dataclass, slots）

| 字段 | 类型 | 约束 |
|---|---|---|
| `actor_id` | `str` | 非空，否则 `ValueError` |
| `actor_type` | `ActorType` | 无默认值，必须显式指定 |
| `tenant_id` | `str` | 非空，否则 `ValueError` |
| `correlation_id` | `str` | 非空，否则 `ValueError` |

三个只读属性：`is_ai` / `is_human` / `is_system`，各自等价于 `actor_type is ActorType.X`。

**`is_ai` 是 R9 的执行接缝。** 它本身**不做任何策略判断**，只诚实报告事实（`context.py:66-75` 的 docstring 明确说明这一点）。真正的"AI 不得写 canonical 事实"决策在 `backend/platform/authorization/policy.py` 的 `human_only` 机制里（见 `AUTHORIZATION.md`）。这个分工是有意的：报告事实的地方不该有策略，否则策略变更要改值对象。

### 1.3 `TenantContext`（frozen dataclass, slots）

| 字段 | 类型 | 约束 |
|---|---|---|
| `tenant_id` | `str` | 非空，否则 `ValueError` |
| `status` | `TenantStatus` | `ACTIVE` / `SUSPENDED` / `ARCHIVED` |

一个只读属性：`is_active`（等价于 `status is TenantStatus.ACTIVE`）。

## 2. 实际约束

1. **不可变**：`frozen=True` + `slots=True`。给 `ActorContext` 任一字段赋值抛 `FrozenInstanceError`（`tests/platform/identity/test_context.py:36`、`:63` 各自验证 `ActorContext` 与 `TenantContext`）。
   **为什么这一条重要**（`context.py:46-50` 的原文理由）：后台任务需要"升级为 system actor"时必须**新建实例**，不能翻现有实例的字段。否则审计链无法诚实回答"这次操作到底是谁发起的" —— 一个被翻过 `actor_type` 的 context 会让 R6 的审计记录说谎。
2. **零依赖、零 I/O**：模块只 import `dataclasses` 与 `enum`。不碰数据库、不发 HTTP、不调模型供应商（R7 天然满足）。
3. **构造即校验**：三个必填 str 字段任一为空（`""`）立刻 `ValueError`，不允许"先构造再检查"。`tests/platform/identity/test_context.py:50` 参数化覆盖三个字段各自的空值。
4. **`correlation_id` 是必填而非可选**。设计含义：任何 actor 上下文必须自带链路标识，否则 audit 无法把一次操作的多条记录串起来。这是 `PLATFORM_ARCHITECTURE.md` §3 那条调用链能成立的前提。

## 3. 已知缺口

按严重度：

1. **没有构造 `ActorContext` 的地方 —— 它没有真实生产调用方。** 全仓 grep：只有 `tests/platform/identity/`、`tests/platform/authorization/` 以及其它测试在构造它。也就是说"每个请求都带 ActorContext"目前**不是事实**，是设计意图。FastAPI 侧没有任何依赖注入把 HTTP 请求解析成 `ActorContext`。
2. **`ActorContext.tenant_id` 与 `TenantContext.tenant_id` 之间没有任何一致性强制**。前者是裸 `str`，两者可以不相等而不报错。没有 `ActorContext.tenant` 这样的组合字段，也没有任何校验函数。
3. **`TenantContext.is_active` 无任何调用方**。也就是说"暂停/归档的租户不能操作"这条规则目前**完全没有被执行**。`TenantStatus.SUSPENDED` 与 `ARCHIVED` 当前只是两个能被构造出来、但不影响任何行为的枚举值。
4. **没有身份来源（authentication）**。本模块只表达"已经确定的身份是什么"，不解决"如何确定身份"。JWT 校验、API Key、会话续期全部不在此处，也不在 `backend/platform/` 任何位置。`governance/DOMAIN_REGISTRY.yaml` 有一条 `auth_identity` 与本条共用 canonical_path，边界模糊（见 `docs/00_system/CURRENT_SYSTEM_BASELINE.md` §5 漂移表第 4 条）。
5. **`tenancy` 的 canonical path 与 manifest 声明不一致**：`MIGRATION_MANIFEST.yaml` 的 `platform_actor_tenant_context` 条目 target 写 `backend/platform/tenant`，该目录**不存在**；`TenantContext` 实际落在 `backend/platform/identity`（同上，漂移表第 3 条）。本任务未修（属 registry 范围）。
6. **无租户隔离执行**。`ActorContext.tenant_id` 存在，但没有任何机制保证查询会按它过滤 —— 无 RLS、无 session 级 filter（见 `PERSISTENCE.md`）。
