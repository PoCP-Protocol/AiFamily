---
id: PLT-AUDIT-001
title: 平台内核规格 — Audit
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

# Audit — AuditEvent / AuditRecorder

**代码**：`backend/platform/audit/models.py`（181 行）、`backend/platform/audit/recorder.py`（116 行）
**测试**：`tests/platform/audit/test_recorder.py`（12 个测试）+ `tests/architecture/test_compliance_constraints.py` 三个第36条检查器
**Registry**：`governance/CAPABILITY_REGISTRY.yaml` → capability `record_audit_event`（`status: IMPLEMENTED_TESTED`）
**上位约束**：`governance/REPOSITORY_CONSTITUTION.md` R6、`docs/12_governance/COMPLIANCE_HARD_CONSTRAINTS.md` §8（第36/37条）

> **并发注意**：本模块在 2026-08-29 被 T-07（读取留痕）改动过，本文件记录的是**当日改动落地后**的磁盘状态。若 T-07 后续继续演进（如接入真实 audit 表），本文件需同步。

---

## 1. 实际提供什么

三个导出符号：`AuditEvent` / `AuditActionKind` / `AuditRecorder`。

### 1.1 `AuditActionKind`（StrEnum，两值 —— 判别式）

```text
MUTATION = "mutation"   状态变更（R6）
READ     = "read"       读取访问（《未成年人网络保护条例》第36条）
```

**为什么是一个带判别式的类型而不是两个兄弟类型**（`models.py:15-33` 的原文论证）：读操作没有 before/after，写操作没有 purpose/approval。若共用一个无判别式的记录类型，两者都能靠"字段留 None"表达 —— 而"留 None"正是"一次读取未成年人数据的记录"退化成"一次无前态的创建"的方式。判别式把区分变成**类型层事实**。

### 1.2 `AuditEvent`（frozen dataclass, slots）

七个必填字段（任一为空即 `ValueError`，`models.py:96-108` 一次性列出全部缺失字段名）：

```text
actor_id  tenant_id  action  resource_type  resource_id  reason  correlation_id
```

这七项对应 R6 条文要求的 actor / tenant / action / resource / reason / correlation_id。

可选字段：

| 字段 | 默认 | 适用 kind |
|---|---|---|
| `before` / `after` | `None` | 仅 MUTATION |
| `action_kind` | `MUTATION` | — |
| `subject_person_id` | `None` | 仅 READ（**必填**） |
| `subject_is_minor` | `False` | 仅 READ |
| `accessed_fields` | `()` | 仅 READ（**非空必填**） |
| `access_purpose` | `None` | 仅 READ（**必填**） |
| `approval_ref` | `None` | READ 且 `subject_is_minor=True` 时**必填** |
| `timestamp` | `datetime.now(UTC)` | — |

`action_kind` 默认 MUTATION，是为了让 T-07 之前写的每一处 R6 调用点保持有效（`models.py:61-63`）。

两个属性：`is_read` / `is_mutation`。

### 1.3 `AuditRecorder`

| 方法 | 行为 |
|---|---|
| `record(event)` | 追加到内存 list |
| `record_read(**kwargs) -> AuditEvent` | 唯一读取留痕入口，全部第36条要素为 keyword-only 必填；返回构造出的 event |
| `all_events()` | 返回全部事件的 tuple |
| `events_for_resource(type, id)` | 按资源过滤 |
| `read_events_for_subject(person_id)` | 只返回该 person 的 READ 事件（第36/37条报表需要的查询形状） |
| `async flush() -> int` | **no-op**，返回 buffer 里的事件数，**不清空 buffer** |

## 2. 实际约束

### 2.1 READ 的不变量（`models.py:117-144`）

READ 事件构造时强制：
- `before` / `after` 必须为 `None` —— 读不改状态。
- `subject_person_id` 必填 —— 第36条记录的是"对某个人的信息的访问"，人必须被指名。
- `accessed_fields` 必须非空 —— "记录了某人读了某个东西"不构成访问记录。`"*"` 允许但不鼓励。
- `access_purpose` 必填 —— 没有声明目的，"最小授权"不可验证。
- `subject_is_minor=True` 时 `approval_ref` 必填 —— **第36条的审批要求被表达成不变量而不是约定**。

后果（`models.py:31-33` 的原话）：「"一次对未成年人数据的读取没有留痕"变成一个可检验的断言，而"留痕了但没有审批"根本构造不出来。」

### 2.2 MUTATION 的不变量（`models.py:146-171`）

- 不得设置 `subject_person_id` / `access_purpose` / `approval_ref` / `accessed_fields` —— 「一次写入不是一次访问授权」。
- **故意不要求必须带 before/after**。理由写在 `models.py:147-154`：既有调用点（`backend/domains/membership/api/routes.py`）合法地记录 `<action>:denied` 与 `<action>:human_gate_passed` 这类无状态差的授权结果，硬塞一个 `after={}` 只会让记录更不诚实。若将来要区分 DECISION 这一类，需要自己的不变量与一份 ADR，不能悄悄给 MUTATION 加第三种含义。

### 2.3 `record_read` 是唯一入口，且这一点被架构检查器守着

`recorder.py:10-23` 说明为什么给 read 一个命名方法而不是让调用方自己拼 `AuditEvent(action_kind=READ, ...)`：
1. **可 grep**。"是否存在读取未成年人数据却不留痕的路径"变成可搜索的单一符号问题 —— 这是架构检查器能成立的前提。
2. **无法半途调用**。第36条四要素全为必填 keyword，不完整的调用在**调用点**就失败，而不是产出一条看着合规的记录。

三个架构检查器（`tests/architecture/test_compliance_constraints.py`）分别验证：`AuditEvent` 能表达读取访问、`AuditRecorder` 有读取留痕入口、未成年人读取不得省略审批。

### 2.4 `timestamp` 用 `datetime.now(UTC)`

时区显式。与 `ConsentGrant.granted_at`（无时区强制）不一致 —— 见 `CONSENT.md` 缺口 7。

## 3. 已知缺口

**缺口 1 是六项内核里最严重的单点问题。**

1. **`flush()` 是 no-op，真实 audit 表不存在 → R6 在机制上不成立。** `recorder.py:107-115`：返回 `len(self._events)`，不写库、**不清空 buffer**（docstring 明确要求调用方不得假设 flush 会清空内存）。测试 `test_flush_reports_buffered_event_count` 断言的正是这个"报数而不落库"的行为 —— 也就是说**当前行为是被测试锁定的、已知不完整的行为**。
   后果：域写入可以成功提交到数据库，而对应的审计记录随进程退出而消失。"无审计不得改状态"目前只是设计意图。
   `database/baseline/` 与 `database/migrations/` 下**没有 audit 表**（T-03 引入的 Alembic baseline 未含）。
2. **`AuditRecorder` 是进程内实例，没有共享/注入机制。** 每个 `AuditRecorder()` 各持一份独立 list。没有单例、没有 FastAPI 依赖、没有请求作用域绑定。也就是说"这次请求的审计记录"与"那次请求的"目前不在同一个地方，`all_events()` 只对同一个实例有意义。
3. **审计写入不与域写入共享事务。** `PLATFORM_ARCHITECTURE.md` §3 第 5/6 步应当同事务，但 `AuditRecorder` 完全不接触 `UnitOfWork`（`recorder.py` 不 import persistence 任何东西）。`unit_of_work.py:10-12` 声称"审计事件写入与域写入必须能共享一个事务边界"，**这条能力目前不存在**。
4. **事件不可篡改性无保证。** `AuditEvent` 自身 frozen，但 `AuditRecorder._events` 是普通 list —— 拿到 recorder 实例就能 `_events.clear()`。没有 append-only 存储、没有 hash 链、没有 WORM。第37条年度审计要求的证据完整性目前无技术支撑。
5. **`CAPABILITY_REGISTRY.yaml` 存在漂移（本任务未修）。** `record_audit_event` 条目的 `known_gaps` 仍写「当前只覆盖状态变更（R6）。《未成年人网络保护条例》第36条要求读取访问也须留痕，尚未实现」—— 但代码已经实现（`AuditActionKind.READ` + `record_read`）。该条应删除或改写为"结构已落地、持久化未落地"。属 registry 维护范围，建议由 T-07 或 registry owner 收口。
6. **无留存期限机制**。第56条要求 DPIA 记录留存 ≥3 年；审计记录本身的留存期限、归档与销毁策略在代码里完全不存在（连字段都没有）。
7. **`access_purpose` 是自由 `str`，与 `ConsentPurpose` 无类型绑定。** `models.py:88-90` 声明它"必须与 consent purpose 分类对齐"，但类型上是裸字符串，没有任何校验或转换。两个模块之间这条语义关联**只存在于注释里**。
8. **`AuditActionKind` 缺 EXPORT/DELETE 等类**。枚举故意只留两值（`models.py:46-51`），但导出与删除也是需要留痕的高风险操作。加值需先补相应不变量。
