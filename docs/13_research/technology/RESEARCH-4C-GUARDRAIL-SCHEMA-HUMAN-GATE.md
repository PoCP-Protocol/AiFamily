---
id: RES-TECH-004C
title: 4c — guardrail 与 schema 校验的工程实现，及 human-in-the-loop 落地
type: research
status: draft
version: 1.0
owner: chief-architect
created: 2026-08-29
updated: 2026-08-29
canonical: false
supersedes: null
superseded_by: null
---

```text
STATUS: RESEARCH_ONLY
NOT_CANONICAL: TRUE
本文件是证据，不是决定。晋升须走 ADR（docs/12_governance/DOCUMENT_GOVERNANCE.md §8.2）。
```

# 4c — 如何保证 LLM 输出不污染业务事实

**被检验的对象**：`docs/05_ai/AI_ARCHITECTURE.md` §1.1（5 个 Agent 输出物必须被重新定性为 Recommendation/Proposal/Draft）、§4.3（canonical 写入只经 Named Action）、§4.4（R8 过闸清单）。这三节都是**制度性约束**，本节要回答的是：**工程层用什么机制强制它？**

---

## 1. Schema 强制：能保证什么，不能保证什么

### 声明 4c.1｜受约束解码（constrained decoding）可提供**schema 合规的硬保证**，无需重试
**置信度：high（一手，Anthropic 平台文档原文）**

来源：`https://platform.claude.com/docs/en/build-with-claude/structured-outputs.md`。原文：

> "Structured outputs guarantee schema-compliant responses through constrained decoding:
> * **Always valid:** No more `JSON.parse()` errors
> * **Type safe:** Guaranteed field types and required fields
> * **Reliable:** No retries needed for schema violations"

实现形态有两处：
- `output_config: {format: {type: "json_schema", schema: {...}}}` 约束响应格式
- 工具定义上 `strict: true` 约束工具入参

**这条声明为什么可 falsify 且重要**：它把"输出结构正确"从概率问题变成了机制保证。**推论：AiFamily 的 AI 输出结构不合法，不应该靠"重试 + 解析失败降级"处理，而应该用受约束解码从源头消除。** 这直接支持给 `AI_ARCHITECTURE.md` §1.1 的输出物定性表加一条工程强制手段。

### 声明 4c.2｜schema 保证有明确边界：一批 JSON Schema 特性不被支持，且**语义正确性完全不在保证范围内**
**置信度：high（一手，官方"Not supported"清单原文）**

不支持的特性（原文清单）：
- Recursive schemas（递归 schema）
- Complex types within enums
- External `$ref`（例 `'$ref': 'http://...'`）
- **数值约束**（`minimum`、`maximum`、`multipleOf`）
- **字符串约束**（`minLength`、`maxLength`）
- 数组约束超出 `minItems` 为 0 或 1 的部分
- `additionalProperties` 设为 `false` 以外的任何值

用了不支持的特性会返回 400 错误。

另有两处会破坏保证的情形（来自同一文档族）：
- **拒答**：`stop_reason: "refusal"` 时输出可能不符合 schema
- **截断**：`stop_reason: "max_tokens"` 时输出可能不完整
- 与 Citations **不兼容**（返回 400）；与消息 prefill 不兼容

语法编译与缓存特性：首次使用某 schema 有编译延迟；编译产物**缓存 24 小时**（自最后一次使用起）；schema 结构变更或**请求中工具集合变更**会使缓存失效，但**只改 `name` / `description` 不失效**。

**这是本文档最关键的一条**：schema 保证的是**形状**，不是**内容真伪**。一个 `{"hypothesis": "孩子有注意力缺陷", "confidence": 0.95}` 完全 schema 合规，但它是一个**类诊断输出**——R9 明令禁止、R8 要求过闸。

**推论（对 AiFamily 有直接约束力）**：
1. 数值约束不被支持 → **不能靠 schema 保证 `confidence` 落在 0..1**，必须在应用层校验。同理不能靠 schema 限制文本长度。
2. **schema 校验 ≠ 业务不变量校验**。R9（Perspective≠Fact）、R8（过闸清单）、"不做家庭总分/排名"这三条**无法用 JSON Schema 表达**，必须由领域层的显式校验器承担。
3. 缓存失效规则（工具集变更失效、name/description 变更不失效）意味着 Prompt Registry 与 Tool Registry 的**变更需要版本化管理**，否则成本与延迟会无声波动。

---

## 2. Human-in-the-loop 的生产落地形态

### 声明 4c.3｜生产级人工闸门是**阻塞式事件往返**，而非"记一条待审记录然后继续执行"
**置信度：high（一手，Anthropic Managed Agents 平台文档 + 客户端模式文档）**

机制（前文 4a.5 已引，此处补完整往返协议）：

1. 工具配 `permission_policy: {type: 'always_ask'}`
2. 该工具被调用时，发出 `agent.tool_use` 事件且 `evaluated_permission === 'ask'`，**会话进入 idle 等待裁决**
3. 客户端回送 `user.tool_confirmation`，携带 `tool_use_id`（**注意：该值是 `event.id`，通常形如 `sevt_...`，不是 `toolu_...`**）、`result: 'allow' | 'deny'`，deny 可带 `deny_message` 告知模型拒绝理由
4. 会话恢复 `running`

自定义（客户端执行）工具走另一条路：`agent.custom_tool_use` 事件 → 会话 idle → 你的应用执行 → 回送 `user.custom_tool_result` → 恢复。**自定义工具不适用权限策略，因为执行方就是你自己。**

平台文档还给出两个必须处理的工程细节（这类细节正是"闸门在生产里怎么落地"的实质内容）：

- **idle 不等于结束**：不能只凭 `session.status_idle` 就退出循环。idle 会**瞬态出现**——并行工具执行之间、等待 `tool_confirmation` 时、等待 custom tool result 时。正确判据是检查 `stop_reason.type`：`requires_action` 表示在等你，**必须 continue 而不是 break**；`end_turn` 与 `retries_exhausted` 才是终态
- **流无重放，断线会死锁**：SSE 流没有 replay。若在某个待裁决的 tool_use 悬空时流断开，会话会死锁（客户端断开 → 会话 idle → 重连 → 但没有任何一方送出裁决）。正确做法是每次（重）连接都先 `events.list()` 拉全量历史、按 event id 去重，再消费实时流

**对 AiFamily 的直接含义（`AI_ARCHITECTURE.md` §4.4 目前完全没有这一层）**：R8 说"闸门决策必须落库可审计"，但没有规定**闸门期间的执行语义**。上述证据表明，一个正确的人工闸门必须：
- **阻塞**待审动作（而不是先执行后审）
- 用**稳定的关联 id** 把裁决绑回具体动作
- 支持**拒绝理由回传**给 AI（否则 AI 无法调整，会重复提交同一被拒动作）
- 在连接中断时可**恢复而不死锁**

这四条是可写进规格与测试的，比"必须过闸"这句话可执行得多。

### 声明 4c.4｜否决理由回传给模型是平台一等公民，不是附加功能
**置信度：high（一手）**

`deny_message` 字段在平台文档中被明确描述为 "Use `deny_message` to tell the model *why* you denied — it gets surfaced back to the agent."

**含义**：AiFamily 的人工闸门若只记录"驳回"而不回传理由，AI 会重复提交同一被拒建议，服务管家的驳回工作会线性放大。这是一条低成本高收益的规格补充。

### 声明 4c.5｜工具执行的自动化程度是一个显式的架构选择，官方对"有副作用的工具"给出安全告警
**置信度：high（一手，Anthropic tool-use 文档）**

原文安全提示：tool runner 会在 Claude 请求时**自动执行**你的工具函数；对于有副作用的工具（发邮件、改数据库、金融交易），要在工具函数内校验入参并考虑对破坏性操作要求确认；**"Use the manual agentic loop if you need human-in-the-loop approval before each tool execution."**

**含义**：便捷的自动循环（tool runner）与人工闸门是**互斥选择**。AiFamily 若要满足 R8，在涉及过闸清单的动作上**不能使用自动 tool runner**，必须手写循环。这是一条应写入 `docs/05_ai/` 的实现约束。

---

## 3. 操作者指令通道：防注入的正确位置

### 声明 4c.6｜会话中途注入的操作者指令应走**独立的 system 角色通道**，而非塞进用户轮
**置信度：high（一手，Anthropic prompt-caching / migration 文档）**

机制：`{"role": "system", ...}` 可追加到 `messages[]`（beta header `mid-conversation-system-2026-04-07`），而不是改顶层 `system`。文档明确其安全属性：

> 这是"prompt-injection-safe operator channel"；两者缓存表现相同，但 `role: "system"` 是**不可伪造的操作者通道**，而放在 user/tool 内容里的文本"can be forged by anything that writes to user-visible input"

约束：必须跟在 user 消息之后，不能是 `messages[0]`；仅文本；不支持的模型返回 400。

文档还给出措辞要求：这类指令要写成**上下文而非命令**，避免 "ignore what the user said" / "regardless of the user's request" / "disregard the previous instruction" 这类覆盖式措辞——因为模型被训练成保护用户免受似乎对其不利的指令，该保护同样适用于 system 角色。

**对 AiFamily 的直接含义**：这条与 4a 的"外部内容隔离"是同一问题的两面。AiFamily 未来若要在对话中注入运行时状态（家庭当前 primary_contradiction、consent 状态、闸门结果），**注入位置本身是安全决策**：塞进用户轮 = 可被伪造 = 家长或孩子输入的文本可以冒充平台指令。这在涉及未成年人的产品里是实质风险，不是理论风险。

---

## 4. 未获证据支持

1. **guardrail 各方案的量化有效性对比**：本轮**未找到**任何可复现的基准，说明"输出 schema 校验 + 内容分类器 + 人工抽检"三者各自拦住多少比例的问题输出。OWASP（见 4a.3）也不提供此类数据。**"哪种 guardrail 组合更有效"未获证据支持。**
2. **人工闸门的运营负载数据**：未找到任何公开数据说明生产环境中 human gate 的实际审批量、平均延迟、驳回率。这直接影响 R8 过闸清单的运营可行性（7 类高影响行为全部过闸，管家的实际负载是多少？），但**无外部证据**，必须 AiFamily 自己实测。
3. **LLM 输出污染业务事实的具名事故案例**：未找到具名的、有复盘的"AI 输出被误当作权威事实写入生产数据库"事故。AiFamily 的 R9 目前仍是**基于源仓库自身伤疤**（`AI_ARCHITECTURE.md` §4.3 引 `family-llm-gateway.service.ts:58-63`）而非外部案例支撑。

---

## 5. 建议走 ADR 的结论

| 结论 | 依据 | 影响文档 |
|---|---|---|
| AI 结构化输出一律用受约束解码强制 schema，禁止"解析失败再重试"作为主路径 | 4c.1 | `docs/05_ai/AI_ARCHITECTURE.md` §1.1 |
| 明确写入"**schema 校验 ≠ 业务不变量校验**"：R8/R9/不做总分排名无法用 JSON Schema 表达，必须由领域层显式校验器承担；数值/长度约束亦须应用层校验 | 4c.2 | 同上 + `docs/04_domains/` |
| 人工闸门规格必须包含四要素：阻塞待审动作、稳定关联 id、驳回理由回传、断线可恢复不死锁 | 4c.3、4c.4 | `docs/05_ai/AI_ARCHITECTURE.md` §4.4、`docs/06_platform/`（待建 Human Gate 规格） |
| 涉 R8 过闸清单的动作**禁用自动 tool runner**，必须手写可拦截循环 | 4c.5 | 同上 |
| 运行时状态注入必须走独立 system 通道，禁止塞入用户轮（防伪造）；措辞用陈述而非覆盖式命令 | 4c.6 | 同上 + `docs/12_governance/COMPLIANCE_HARD_CONSTRAINTS.md` 交叉引用 |
| Prompt/Tool Registry 需版本化：工具集合变更会使 schema 编译缓存失效，影响成本与延迟 | 4c.2 | `docs/09_operations/`（成本）+ Model Gateway 规格 |

---

## 6. 声明汇总

| # | 声明 | 置信度 | 来源类型 |
|---|---|---|---|
| 4c.1 | 受约束解码提供 schema 合规硬保证，无需重试 | high | 一手 |
| 4c.2 | schema 保证有明确边界；数值/字符串约束不支持；拒答与截断会破坏保证；语义真伪完全不在保证范围内 | high | 一手 |
| 4c.3 | 人工闸门是阻塞式事件往返；idle 非终态需查 stop_reason；流无重放需去重恢复 | high | 一手 |
| 4c.4 | 驳回理由回传模型是一等公民 | high | 一手 |
| 4c.5 | 自动 tool runner 与逐次人工审批互斥，官方要求后者手写循环 | high | 一手 |
| 4c.6 | 中途操作者指令应走独立 system 通道，是防注入的正确位置 | high | 一手 |
