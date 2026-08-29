---
id: PLT-AUTHZ-001
title: 平台内核规格 — Authorization
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

# Authorization — PolicyEngine（fail-closed）

**代码**：`backend/platform/authorization/policy.py`（115 行）
**测试**：`tests/platform/authorization/test_policy.py`（5 个测试）
**Registry**：`governance/CAPABILITY_REGISTRY.yaml` → capability `authorize_action`（`status: IMPLEMENTED_TESTED`）
**Domain registry**：`governance/DOMAIN_REGISTRY.yaml` → `platform/authorization`
**参考实现**（不是复制来源，只参考其测试语义）：源仓库 `apps/api/src/modules/auth/family-authorization.policy.ts`

本文件从代码反向记录实际契约。总览见 `PLATFORM_ARCHITECTURE.md`。

---

## 1. 实际提供什么

三个导出符号：`PolicyEngine` / `PolicyRule` / `Decision`。

### 1.1 `Decision`（frozen dataclass）

`allowed: bool` + `reason: str`。两个工厂方法：`Decision.allow(reason=...)` / `Decision.deny(reason)`。

`reason` 是**必填的**（`deny` 无默认值）。设计含义：拒绝必须能解释为什么。测试 `test_unregistered_action_resource_pair_is_denied` 断言 `"fail-closed" in decision.reason`，`test_human_only_denial_reason_mentions_ai` 断言 reason 里同时出现 `"human_only"` 与 `"AI"` —— reason 文本是被测试锁定的契约，不是日志字符串。

### 1.2 `PolicyRule`（frozen dataclass）

| 字段 | 类型 | 默认 | 含义 |
|---|---|---|---|
| `action` | `str` | 必填 | 动作名，纯字符串，无枚举约束 |
| `resource_type` | `str` | 必填 | 资源类型名，同上 |
| `allowed_actor_types` | `frozenset[ActorType]` | 空集 | **空集 = 所有 actor type 都被本规则允许** |
| `human_only` | `bool` | `False` | `True` 时 AI actor 被拒 |

两个方法：`matches(action, resource_type)`（精确相等，无通配符）、`permits(actor)`。

### 1.3 `PolicyEngine`

- `register(rule)` —— 追加到内部 `list`（有序，见 §3 缺口 1）。
- `check(actor, action, resource_type) -> Decision`。

**只能注册 ALLOW 规则，没有注册 DENY 的机制。** 理由写在 `policy.py:80-82`：DENY 已经是默认值，再提供显式 DENY 只会变成"不小心把默认值遮掉"的途径。

## 2. 实际约束

### 2.1 Fail-closed 是这个模块存在的全部理由

`check` 的判定顺序：

```text
1. 没有任何 matches(action, resource_type) 的规则  → DENY（reason 含 "fail-closed"）
2. 遍历匹配的规则：
   a. 该规则 human_only 且 actor.is_ai        → DENY（立即返回）
   b. 该规则 permits(actor)                   → ALLOW（立即返回）
3. 全部匹配规则都不 permit                    → DENY
```

关键性质：**"未注册"与"被禁止"对调用方是同一种失败**（`policy.py:6-8`）。忘记注册规则不会意外放行。这是对宪章 R7 那道伤疤的直接反制 —— 源仓库有一条只存在于常量里、从未被执行的策略。

### 2.2 `human_only` 是 R9 的执行点

`ActorContext.is_ai`（见 `IDENTITY.md`）只报告事实；本模块的 `human_only=True` 才是"AI 不得写 canonical 事实"的决策。测试 `test_human_only_action_denies_ai_actor_even_if_generally_allowed` 验证：同一条规则对 HUMAN 放行、对 AI 拒绝。

注意 `permits()` 里 `human_only` 检查排在 `allowed_actor_types` **之前**（`policy.py:69-73`），所以即使有人手写 `allowed_actor_types={ActorType.AI}` 又设 `human_only=True`，AI 仍被拒。

### 2.3 纯内存、无 I/O

模块只依赖 `dataclasses` 与 `backend.platform.identity.context`。不查库、不读配置文件。规则从哪来、谁负责注册，本模块不回答。

## 3. 已知缺口

按严重度：

1. **`human_only` 的"无条件"实际上是顺序相关的 —— 这是一个真实的绕过路径。** `check` 遍历匹配规则时**遇到第一条 `permits` 就立即返回 ALLOW**（`policy.py:106`）。因此对同一 `(action, resource_type)`：
   ```python
   engine.register(PolicyRule(action="write", resource_type="fact"))                  # 宽松，先注册
   engine.register(PolicyRule(action="write", resource_type="fact", human_only=True)) # 严格，后注册
   engine.check(ai_actor, "write", "fact")   # → ALLOW，human_only 被跳过
   ```
   把两条注册顺序调换则 AI 被拒。docstring（`policy.py:16-18`、`:53-57`）声称 `human_only` 由引擎"无条件执行"，**代码实际做不到这一点**。现有 5 个测试没有一个注册两条同 key 规则，所以这条缺口不会被现有测试发现。
   **正确的实现应当先扫全部匹配规则里的 `human_only`，再判 permit。** 本任务只写文档不改代码，此项建议独立立项（涉及 R9，可能需要 ADR）。
2. **它没有真实生产调用方。** 全仓 grep `PolicyEngine`：只有 `backend/platform/authorization/` 自身与 `tests/platform/authorization/`。没有任何 FastAPI 依赖、中间件或 domain service 调它。也就是说 AiFamily 目前**没有在执行任何授权**（因为也还没有业务端点）。
3. **没有角色（Role）概念**。粒度只到 `ActorType`（human/ai/system）。`guardian` / `teacher` / `operator` / `child` 这些 `CAPABILITY_REGISTRY.yaml` 的 `enums.actor_type` 里列出的角色，在 PolicyEngine 里**无法表达**。而 `COMPLIANCE_HARD_CONSTRAINTS.md` §8 要求的"最小授权"以及第36条的"经负责人审批"都需要角色与审批态 —— 当前模型撑不起。
4. **没有资源实例级判定（ABAC）**。`resource_type` 是类型名，不是实例 id。"家长 A 能看自己孩子的档案、不能看家长 B 孩子的档案"这种归属判断**表达不了**，只能留给 domain 层手写。这是当前设计的明确边界（`policy.py:12-13` 自述"不试图做通用 RBAC/ABAC"），但意味着最重要的一类家庭数据授权目前无平台支撑。
5. **`action` / `resource_type` 是自由字符串，无注册表校验**。拼写错误（`"veiw"`）不会报错，只会静默 fail-closed 成 DENY —— 方向安全，但排障困难，且没有"列出全部已注册规则"的自省接口。
6. **规则来源无治理**。`DOCUMENT_GOVERNANCE.md` §7 要求"授权规则/角色变更"同步 `docs/06_platform/` 授权规格 + `governance/` 授权 registry，但**该 registry 尚不存在**（同文件 §7 标注"待建"）。当前无处登记"系统里有哪些 (action, resource_type) 规则"。
7. **无审计接线**。`check` 返回 DENY 不产生 `AuditEvent`。授权拒绝本身是应当留痕的安全事件，目前不留。
