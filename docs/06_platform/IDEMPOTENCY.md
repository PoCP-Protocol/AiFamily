---
id: PLT-IDEMPOTENCY-001
title: 平台内核规格 — Idempotency
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

# Idempotency — IdempotencyKey / IdempotencyStore

**代码**：`backend/platform/idempotency/keys.py`（58 行 —— 六项内核里最小的一项）
**测试**：`tests/platform/idempotency/test_keys.py`（4 个测试）
**Registry**：`governance/CAPABILITY_REGISTRY.yaml` → capability `reserve_idempotency_key`（`status: IMPLEMENTED_TESTED`，自带 `known_gaps`）

本文件从代码反向记录实际契约。总览见 `PLATFORM_ARCHITECTURE.md`。

---

## 1. 实际提供什么

三个导出符号：`IdempotencyKey` / `IdempotencyStore` / `InMemoryIdempotencyStore`。

### 1.1 `IdempotencyKey`（frozen dataclass, slots）

两个**必填**字段：`tenant_id: str` 与 `value: str`，任一为空即 `ValueError`。另有只读属性 `scoped_value`，返回 `f"{len(tenant_id)}:{tenant_id}:{value}"` —— 这是 store 唯一应当索引的字符串。

**长度前缀不是装饰。** 裸 `f"{tenant_id}:{value}"` 有歧义：`(tenant="a", value="b:c")` 与 `(tenant="a:b", value="c")` 生成同一字符串，等于把要防的跨租户碰撞又请回来。租户 id 是不透明字符串，编码不得假设它不含分隔符（`test_tenant_and_value_boundary_cannot_be_confused_by_a_separator` 锁定）。

**为什么不直接用 `str`**（`keys.py:3-5`）：包一层是为了让"把 resource_id 或 correlation_id 传到需要幂等键的地方"至少需要**一次显式转换**才能发生。类型系统在这里的作用是制造摩擦，不是抽象。

### 1.2 `IdempotencyStore`（ABC）

唯一抽象方法：

```python
def check_and_reserve(self, key: IdempotencyKey) -> bool
```

契约（`keys.py:39-44`）：
- 返回 `True` = 这是该 key 的**首次**预留。
- 返回 `False` = 该 key 已被更早的调用预留过，**调用方必须视为"这次操作已经发生过，不要重复副作用"**。

注意方法是**同步**的（不是 `async`）。Postgres 实现要么走同步驱动，要么改签名 —— 见 §3 缺口 3。

### 1.3 `InMemoryIdempotencyStore`

`set[str]` 支撑。`check_and_reserve`：在集合里则返回 `False`，否则加入并返回 `True`。

自述定位（`keys.py:49`）："for tests and single-process dev use"。

## 2. 实际约束

1. **原子性是接口契约，不是实现细节。** `keys.py:7-9` 要求 `check_and_reserve` 从调用方视角看必须是原子的 —— "check 后 reserve"之间不能有窗口。`InMemoryIdempotencyStore` 在单线程下满足；在真实并发下**不满足**（见 §3 缺口 2）。文档里给出的持久化实现思路是"key 列上加唯一约束"，即把原子性交给数据库。
2. **单向、无释放。** 接口只有预留，没有 `release` / `delete` / `expire`。一旦预留就永久占用。
3. **key 之间完全独立**（`test_different_keys_are_independent` 验证），不存在前缀/命名空间语义；唯一的结构化维度是 tenant。
   **跨租户即两个 key。** 同一 `value` 由两个租户提交，两次首次预留都返回 `True`（`test_same_value_in_two_tenants_are_two_independent_reservations`），而租户内的重放仍被识别（`test_replay_is_still_detected_within_a_tenant_after_scoping` —— 隔离不得靠关掉重放检测换来）。
4. **不存储结果。** 这是个纯"是否首次"的判定，**不缓存首次调用的响应**。第二次请求得到 `False` 后，调用方只知道"发生过了"，拿不到"上次返回了什么"。真正的 HTTP 幂等语义（重放同一 `Idempotency-Key` 应返回同一响应体）**表达不了**。

## 3. 已知缺口

按严重度：

1. **只有内存实现，进程重启即失忆**（`keys.py:11-14` 自述，`CAPABILITY_REGISTRY.yaml` 的 `known_gaps` 亦记："仅有 InMemoryIdempotencyStore；持久化实现待 Batch 3"）。后果：任何跨进程重启或多副本部署的场景，幂等保证**完全不存在**。三进程架构（`family_api` / `ai_runtime` / `workflow_worker`）下，一个进程预留的 key 对另一个进程不可见。
2. **`InMemoryIdempotencyStore` 在并发下不原子。** `if key.value in self._seen` 与 `self._seen.add(...)` 是两步（`keys.py:55-57`），中间无锁。CPython GIL 在纯 CPython 字节码层面碰巧让这段很难交错，但这是实现细节而非保证；换 free-threaded Python 或加入 `await` 点即失效。接口声称的原子性在唯一现存实现里靠运气。**无测试覆盖并发场景。**
3. **接口是同步方法，与全栈 async 不一致。** `check_and_reserve` 是 `def` 而非 `async def`，而 persistence 全部是 `AsyncSession`。Postgres 实现要么在 async 路径里做阻塞 I/O（会卡事件循环），要么改接口签名（破坏现有唯一实现）。**这是一个已经存在的设计冲突，落地持久化时必须先解决。**
4. **无保留期/过期策略。** `keys.py:10-11` 明确写"retention policy ... not modeled yet in Wave 1"。内存实现的 `set` 无界增长；持久化实现若无 TTL 会让表无限膨胀。同时"多久之后同一个 key 可以被重新使用"这个语义问题也未回答。
5. **无真实生产调用方。** 全仓 grep：只有自身与 `tests/platform/idempotency/`。没有 FastAPI 中间件读取 `Idempotency-Key` 请求头，也没有任何命令处理器调它。也就是说 AiFamily 目前**没有任何幂等保护在生效**。
6. ~~**跨租户 key 碰撞会让一个租户的操作被误判为"已发生"—— 因为 `IdempotencyKey` 里没有 tenant 维度。**~~ **已修（T-14）**：`tenant_id` 现为必填字段，store 以 `scoped_value` 索引，且**没有留任何生成无租户 key 的旁路**（无兼容构造器、无默认值、无 classmethod）。原缺陷是双重问题：正确性（B 租户首次请求被当成重放而静默丢弃）+ 泄漏（该 `False` 完全源自 A 租户的活动，可被用于探测）。
   **仍未闭合的部分**：key 的**生成规范**依旧缺失 —— 谁生成、按什么组合（actor + action + payload hash？客户端自带？）仍未定义。持久化实现的唯一约束必须建在 `(tenant_id, value)` 上，不是 `value` 上。
   **值得注意的事实**：改这条**没有需要更新的生产调用方**。全仓 grep 确认 `IdempotencyKey` 在 platform 与 `tests/platform/` 之外零引用；membership 与 service 各自用裸 `str` + 自己的仓储查询，而那些查询签名**本来就是** `(tenant_id, family_id, key)`，即业务侧的幂等一直是租户内的。缺陷只存在于平台原语，未曾被业务域触发。
7. **不与 `UnitOfWork` 协同。** 预留成功但随后事务回滚时，key 仍被占用（无释放接口），该操作**永久无法重试**。正确设计需要预留与业务事务的关系被明确定义（同事务？两阶段？补偿？），当前完全未定义。
