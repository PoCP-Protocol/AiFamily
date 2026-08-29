---
id: RES-TECH-004D
title: 4d — Model Gateway 容错：超时、重试、降级与成本控制
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

# 4d — 超时/重试/降级的具体策略，与成本控制

**被检验的对象**：`docs/00_system/CURRENT_AI_ARCHITECTURE.md` 判定 Model Gateway 为 REIMPLEMENT（Python 侧零实现）；`AI_ARCHITECTURE.md` §4.3 规定凭据只由 Model Gateway 读取。T-06（Model Gateway）是"一切 AI 能力的前置"。本节为 T-06 的设计选择提供外部依据。

---

## 1. 哪些错误可重试，哪些不可——具体到状态码

### 声明 4d.1｜可重试集合是明确且有限的：连接错误、408、409、429、≥500；4xx（除 429）不可重试
**置信度：high（一手，Anthropic SDK 文档 + 错误码参考）**

官方错误码表（一手）：

| 码 | 错误类型 | 可重试 | 常见原因 |
|---|---|---|---|
| 400 | `invalid_request_error` | **否** | 请求格式/参数非法 |
| 401 | `authentication_error` | **否** | key 无效或缺失 |
| 403 | `permission_error` | **否** | key 无权限 |
| 404 | `not_found_error` | **否** | 端点或 model id 非法 |
| 413 | `request_too_large` | **否** | 超出大小限制 |
| 429 | `rate_limit_error` | **是** | 限流 |
| 500 | `api_error` | **是** | 服务端问题 |
| 529 | `overloaded_error` | **是** | 服务过载 |

SDK 行为（一手）："The SDK auto-retries connection errors, 408, 409, 429, and ≥500 with exponential backoff (default 2 retries)."；`max_retries=0` 关闭。

429 时应读 `retry-after` 头（秒）与 `x-ratelimit-limit-*` / `x-ratelimit-remaining-*`。

**关键的可 falsify 断言（回答任务卡"为什么有的团队选 retry=0"）**：官方明确 **"Client errors (4xx except 429) should not be retried"**。因此 retry=0 的正确解读不是"团队保守"，而是：
- **在 SDK 已自带重试的前提下，应用层再叠一层重试是错误的**——会造成 2×N 的放大。官方原文即提示："The SDK automatically retries rate limit (429) and server errors (5xx) with exponential backoff... **Only implement custom retry logic if you need behavior beyond what the SDK provides.**"
- 对 400/401/403/404/413 这类确定性错误，重试**必然重复失败**并线性放大成本与延迟

**推论（对 AiFamily Model Gateway 的直接约束）**：网关必须**按错误类型分流**，而非统一重试策略；且必须明确"重试发生在哪一层"（SDK 层还是网关层），二者不能同时开启。这是一条可写成测试的规格。

### 声明 4d.2｜错误分类必须用类型化异常，禁止字符串匹配错误消息
**置信度：high（一手，SDK 文档明确列为反模式）**

官方给出正例/反例对照，并明确 "**Always use the SDK's typed exception classes** instead of checking error messages with string matching."；错误对象另暴露 `.type` 字段（`"invalid_request_error"` / `"rate_limit_error"` / `"overloaded_error"` / `"billing_error"` 等）用于比 HTTP 码更细的分类——例如 **`billing_error` 与 `permission_error` 都映射到 403**，只有 `.type` 能区分。

**含义**：这是一条可机械检验的规则（符合 R14）。AiFamily 的 Model Gateway 若用字符串匹配判断错误类型，就会把"欠费"当成"权限不足"处理，降级路径完全走错。可写成 lint/架构测试：禁止在 gateway 代码中对异常消息做 `in` / `includes` 匹配。

---

## 2. 超时：最容易踩的坑是"超时不是墙钟超时"

### 声明 4d.3｜HTTP 客户端的 timeout 是**逐块读超时**，不是总时长上限；缓慢滴流的响应可以无限期挂住
**置信度：high（一手，平台文档明确警告）**

原文警告（多处重复，说明是常见事故）：

> "don't rely on `requests` or `httpx` timeouts as wall-clock caps — they're **per-chunk** read timeouts, reset every time a byte arrives. A trickling response (heartbeats, a wedged chunked-encoding body, a misbehaving proxy) can keep the call blocked indefinitely even with `timeout=(5, 60)` or `httpx.Timeout(120)`. Neither library has a 'total wall-clock' timeout built in."

正确做法（原文）：在循环层记录 `time.monotonic()` 并显式 bail，或用 `asyncio.wait_for()` 包裹。

SDK 默认值（一手）：默认请求超时 **10 分钟**；超时抛 `APITimeoutError` 并按 `max_retries` 重试。可传 float 或 `httpx.Timeout` 做粒度控制。

### 声明 4d.4｜大 `max_tokens` 的非流式请求会被 SDK 主动拒绝，因为连接会被空闲断开
**置信度：high（一手）**

原文："**Large `max_tokens` without streaming raises `ValueError`** — The SDK refuses non-streaming requests it estimates will exceed ~10 minutes (idle connections drop)."；建议 `max_tokens > ~16000` 一律流式。

**含义（对 AiFamily 的具体参数建议）**：非流式默认 `max_tokens` 应控制在 ~16000 以内；需要长输出（如生成 21 天计划全文）必须走流式并用 `.get_final_message()` 取完整结果——**流式在这里不是 UX 选择，是超时防护手段**。

---

## 3. 降级

### 声明 4d.5｜529 过载的官方建议降级路径是**换模型层级**，而非直接失败
**置信度：high（一手，错误码文档）**

529 `overloaded_error` 的修复建议原文："Retry with exponential backoff. **Consider using a different model (Haiku is often less loaded)**, spreading requests over time, or implementing request queuing."

**含义**：这为 AiFamily 的降级策略提供了一条有依据的形态——**同供应商内的模型层级降级 + 请求排队**，而不是必须做多供应商切换。这一点对 R7/R10（唯一 AI Runtime、领域不直连供应商）有利：降级逻辑收敛在 Model Gateway 内部，领域侧无感。

**但必须配一条 AiFamily 特有约束**：降级换模型意味着**输出质量变化**。对于会产出 Recommendation/Hypothesis 的用例，降级后的输出必须**在 provenance 中标注实际使用的模型**，否则 R9 要求的可溯源性被破坏——降级会静默改变结论质量而无痕迹。这是本研究提出的、外部文档未涵盖的推论。

### 声明 4d.6｜切换模型会使 prompt 缓存失效——降级不是零成本操作
**置信度：high（一手，prompt caching 文档；缓存作用域按模型）**

失效层级表（一手）：

| 变更 | tools 缓存 | system 缓存 | messages 缓存 |
|---|:---:|:---:|:---:|
| 工具定义变更（增删/改序） | 失效 | 失效 | 失效 |
| **模型切换** | **失效** | **失效** | **失效** |
| `speed` / web-search / citations 开关 | 保留 | 失效 | 失效 |
| system 内容变更 | 保留 | 失效 | 失效 |
| `tool_choice` / images / `thinking` 开关 | 保留 | 保留 | 失效 |
| message 内容变更 | 保留 | 保留 | 失效 |

**含义**：模型降级会让整条缓存前缀重建。因此"过载就降级"这条策略在**高频、长上下文**的场景（正是 Family Context 注入后的场景）成本反而可能上升。降级策略需要在网关内做成本感知，而不是无条件降级。

---

## 4. 成本控制的具体手段（含硬数字）

### 声明 4d.7｜prompt 缓存的经济学有明确盈亏平衡点，且最小可缓存前缀是**按模型不同的硬阈值**
**置信度：high（一手，prompt caching 文档）**

- 缓存读成本 ≈ 基础输入价的 **0.1×**
- 缓存写成本：5 分钟 TTL **1.25×**，1 小时 TTL **2×**
- 盈亏平衡：5 分钟 TTL 下**两次请求**即回本（1.25× + 0.1× = 1.35× vs 2× 未缓存）；1 小时 TTL 需**至少三次**（2× + 0.2× = 2.2× vs 3×）
- 每请求最多 **4 个** `cache_control` 断点
- **最小可缓存前缀（低于此值静默不缓存、无报错，`cache_creation_input_tokens: 0`）**：

| 模型档 | 最小 token |
|---|---:|
| Opus 4.8 / 4.7 / 4.6 / 4.5、Haiku 4.5 | 4096 |
| Sonnet 4.6、Haiku 3.5 / 3 | 2048 |
| Sonnet 4.5 / 4.1 / 4、Sonnet 3.7 | 1024 |

原文警示例："A 3K-token prompt caches on Sonnet 4.5 but silently won't on Opus 4.8."

验证手段（一手）：`usage.cache_read_input_tokens`；若重复同前缀请求该值恒为 0，则存在静默失效因子。且 **`input_tokens` 只是未缓存的余量**：总 prompt 大小 = `input_tokens + cache_creation_input_tokens + cache_read_input_tokens`。

### 声明 4d.8｜缓存的静默失效因子清单是可审计的、且都是常见写法
**置信度：high（一手，官方反模式表）**

| 反模式 | 为何破坏缓存 |
|---|---|
| system 提示里 `datetime.now()` / `Date.now()` / `time.time()` | 每次请求前缀都变 |
| 内容早段出现 `uuid4()` / request id | 同上 |
| `json.dumps(d)` 未加 `sort_keys=True`、或迭代 `set` | 序列化不确定 → 前缀字节不同 |
| 把 session/user id f-string 进 system 提示 | 变成 per-user 前缀，跨用户无法共享 |
| 条件化 system 段（`if flag: system += ...`） | 每种 flag 组合都是独立前缀 |
| `tools=build_tools(user)` 按用户变化 | 工具渲染在位置 0，跨用户完全无法缓存 |

渲染顺序（一手）：`tools` → `system` → `messages`。另有 **20 个内容块回溯窗口**：每个断点向后最多回溯 20 个内容块寻找已有缓存条目；单轮若新增超过 20 块（agent 循环里大量 tool_use/tool_result 对很常见），下一次请求的断点找不到上次缓存而**静默 miss**。并发时序：缓存条目只有在首个响应**开始流式输出之后**才可读，N 个并行同前缀请求全部按全价计费。

**对 AiFamily 的直接含义（这是本文档最可操作的部分）**：
1. **把 `family_id` 或家长姓名拼进 system 提示会让缓存按家庭碎片化** —— 这正是 AiFamily 最自然会犯的错。Family Context 必须注入在**最后一个缓存断点之后**（messages 尾部），而不是 system 头部。
2. Agent 循环里工具往返容易突破 20 块窗口 → 长会话需要中途插入断点。
3. `governance/AI_USE_CASE_REGISTRY.yaml`（待建）里的 `allowed_tools` 若按用例/角色动态构造，会让工具集随请求变化并**彻底摧毁缓存**。工具集必须确定性排序且尽量稳定。

### 声明 4d.9｜批处理与 token 预算是两条独立的成本杠杆，各有硬参数
**置信度：high（一手）**

- **Batches API**：按标准价 **50%** 计费；单批最多 **100,000** 请求或 **256 MB**；多数 1 小时内完成，**最长 24 小时**；结果保留 **29 天**。支持全部 Messages 功能（含 vision、tools、caching）
- **Task Budgets**（beta，header `task-budgets-2026-03-13`）：`output_config: {task_budget: {type: "tokens", total: N}}`，告知模型整个 agent 循环可用 token 总量，模型看到倒计时并自我节制；**最小 20,000**。与 `max_tokens` 本质不同——后者是强制的**单响应上限且模型不知情**
- **Token 计数**：必须用 `messages.count_tokens`（按模型计数），官方明确 **"Do not use `tiktoken`"** —— 它是 OpenAI 的分词器，对 Claude 在普通文本上低估约 **15–20%**，在代码或非英文输入上偏差更大

**对 AiFamily 的直接含义**：中文内容为主的产品，用 `tiktoken` 估算成本会**系统性低估**。任何成本看板必须走 `count_tokens`。这条可直接写进 `docs/09_operations/` 的成本控制规格。

---

## 5. 未获证据支持

1. **"有的团队选 retry=0"的具体案例**：任务卡要求找出这类团队及其理由。本轮**未找到任何具名团队的公开说明**。但如声明 4d.1 所述，官方文档本身给出了比二手案例更强的依据（SDK 已自带重试，应用层叠加是错误的；4xx 除 429 不应重试）。**"某团队因 X 原因选择 retry=0"未获证据支持，不作断言。**
2. **多供应商网关的容错对比数据**：未找到可信的跨供应商可用性/故障率对比数据。因此"是否需要多供应商冗余"**未获证据支持**，不能据此建议 AiFamily 做多供应商切换。
3. **AiFamily 场景的实际成本量级**：无外部证据。必须用 `count_tokens` 对真实 prompt 实测。

---

## 6. 建议走 ADR 的结论

| 结论 | 依据 | 影响文档 |
|---|---|---|
| Model Gateway 必须按错误类型分流：仅连接错误/408/409/429/≥500 可重试；4xx（除 429）一律不重试。且必须明确重试只发生在一层，禁止 SDK 层与网关层叠加 | 4d.1 | Model Gateway 规格（`docs/06_platform/` 待建）、T-06 |
| 错误分类必须用类型化异常 + `.type` 字段；禁止字符串匹配错误消息（403 下 billing 与 permission 必须可区分）。可落架构测试 | 4d.2 | 同上 + `tests/architecture/` |
| 超时必须在网关层用单调时钟实现**墙钟上限**；不得依赖 httpx/requests 的逐块读超时 | 4d.3 | 同上 |
| 非流式 `max_tokens` 上限约 16000；超过一律流式 | 4d.4 | 同上 |
| 降级采用同供应商模型层级降级 + 请求排队；**降级必须写入 provenance**（否则 R9 可溯源性被破坏）；降级需成本感知（会清空缓存前缀） | 4d.5、4d.6 | 同上 + `docs/05_ai/AI_ARCHITECTURE.md` §4.3 |
| Family Context 必须注入在最后一个缓存断点**之后**；严禁把 family_id/家长姓名拼入 system 前缀 | 4d.8 | `docs/05_ai/AI_ARCHITECTURE.md` §2、Model Gateway 规格 |
| `allowed_tools` 必须确定性排序且稳定；按用例动态构造工具集会摧毁缓存 | 4d.8 | `governance/AI_USE_CASE_REGISTRY.yaml`（待建） |
| 成本核算一律用 `count_tokens`；禁用 tiktoken 类估算（中文场景系统性低估） | 4d.9 | `docs/09_operations/` |
| 非延迟敏感的批量 AI 任务走 Batches（50% 成本） | 4d.9 | 同上 |

---

## 7. 声明汇总

| # | 声明 | 置信度 | 来源类型 |
|---|---|---|---|
| 4d.1 | 可重试集合明确有限；4xx（除 429）不可重试；SDK 已自带重试，勿叠加 | high | 一手 |
| 4d.2 | 必须用类型化异常；403 下 billing 与 permission 需靠 `.type` 区分 | high | 一手 |
| 4d.3 | HTTP timeout 是逐块读超时非墙钟；需单调时钟自行兜底 | high | 一手 |
| 4d.4 | 大 max_tokens 非流式请求被 SDK 拒绝；>~16000 须流式 | high | 一手 |
| 4d.5 | 529 官方降级路径是换模型层级 + 排队 | high | 一手 |
| 4d.6 | 模型切换使三层缓存全部失效——降级非零成本 | high | 一手 |
| 4d.7 | 缓存读 0.1×、写 1.25×/2×；5min TTL 两次回本；最小前缀 1024/2048/4096 按模型 | high | 一手 |
| 4d.8 | 静默失效因子清单；渲染顺序 tools→system→messages；20 块回溯窗口；并发首请求全价 | high | 一手 |
| 4d.9 | Batches 50% 成本/10 万请求/24h 上限；Task Budgets 最小 20,000；禁用 tiktoken（低估 15–20%） | high | 一手 |
