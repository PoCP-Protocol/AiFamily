---
id: RES-TECH-004B
title: 4b — 长期记忆工程：pgvector 的实际适用边界
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

# 4b — pgvector 的实际适用边界，与"退回结构化检索"的条件

**被检验的对象**：`docs/05_ai/AI_ARCHITECTURE.md` §2.1 已核实"embedding/pgvector 完全不存在于代码"，三层画像完成度为 0；`COMMERCIAL_VALUE_STRATEGY.md` §8.2 把 Family Context 列为独占区候选，其技术路径隐含向量检索。本节要回答：**pgvector 在 AiFamily 的实际使用形态下会不会失效？**

**为什么这个问题对 AiFamily 特别关键**：AiFamily 的每一次检索**必然带 `family_id` 过滤**（家庭数据隔离是硬约束，不是可选优化）。这不是一般 RAG 场景，而是"高选择性过滤 + 向量检索"的组合——恰好是 pgvector 最脆弱的形态。

---

## 1. 硬性技术限制（一手，官方 README）

### 声明 4b.1｜pgvector 的过滤在**索引扫描之后**执行，这会导致带过滤的查询静默少返回结果
**置信度：high（一手，pgvector 官方 README 原文）**

来源：`https://github.com/pgvector/pgvector`（README，Filtering 与 Troubleshooting 章节）。原文关键句：

> "filtering is applied **after** the index is scanned"

官方给出的量化示例：若过滤条件匹配约 10% 的行，在 HNSW 默认 `hnsw.ef_search = 40` 的情况下，**平均只有约 4 行会匹配**。

Troubleshooting 章节对应条目：
- HNSW："Results are limited by the size of the dynamic candidate list (`hnsw.ef_search`)"
- IVFFlat："The index was likely created with too little data for the number of lists"，且结果数还会被 `ivfflat.probes` 限制

**这条声明为什么是本文档最重要的一条**：它是一个**可 falsify 的机制性缺陷**，而不是性能调优建议。它意味着"`WHERE family_id = ? ORDER BY embedding <=> ? LIMIT 10`"这种在 AiFamily 里最自然的查询形态，**会静默返回不足 10 条，且不报错**。在一个"家庭长期上下文检索"的产品里，静默漏检就是 AI 引用了不完整的家庭历史——这属于正确性问题，不是延迟问题。

### 声明 4b.2｜官方给出的四种应对手段，各自都有明确适用条件
**置信度：high（一手，README + CHANGELOG）**

| 手段 | 官方原文/要点 | 适用条件 |
|---|---|---|
| 在过滤列上建索引（走精确检索） | "A good place to start is creating an index on the filter column."；"Exact indexes work well for conditions that match a **low percentage of rows**." | 过滤命中行占比**低**时有效 |
| 迭代索引扫描 | `SET hnsw.iterative_scan = strict_order;`（严格按距离序）或 `relaxed_order`（略微乱序，召回更好）；`hnsw.max_scan_tuples` 默认 **20,000**（"approximate and does not affect the initial scan"） | pgvector **0.8.0（2024-10-30）**起提供（CHANGELOG："Added support for iterative index scans"）。最新版 0.8.6（2026-07-29） |
| 部分索引（partial index） | "If filtering by only a **few distinct values**, consider partial indexing." | 过滤值**种类少** |
| 分区（partitioning） | "If filtering by **many different values**, consider partitioning." | 过滤值**种类多** |

### 声明 4b.3｜对 AiFamily 而言，官方推荐路径明确指向**按 family_id 分区**，而非单一大索引
**置信度：medium-high（推论，但直接套用 4b.2 的官方判据）**

`family_id` 的取值种类随家庭数增长，属于 "filtering by many different values" → 官方明确建议 **partitioning**。同时它是高选择性过滤（每个家庭只占总行数极小比例）→ 也满足"exact indexes work well for conditions that match a low percentage of rows"。

**推论（两条路都通，且都不是"单张大表 + 一个 HNSW 索引"）**：
1. **小规模阶段**：单个家庭的记忆条数量级不大时，`family_id` 上的普通 B-tree 索引 + **精确**向量距离排序即可，**根本不需要 ANN 索引**。这是官方"a good place to start"的路径。
2. **规模化阶段**：按 `family_id`（或其 hash）分区，每分区内再建 HNSW。

**这条推论对 `COMMERCIAL_VALUE_STRATEGY.md` §8.2 的直接影响**：把 Family Context 的技术风险定位为"embedding/pgvector 不存在于代码"其实定位偏了——真正的风险不是"没接 pgvector"，而是**接了 pgvector 却用成单表大索引 + 后置过滤，从而静默漏检家庭历史**。前者是工作量问题，后者是正确性问题。

### 声明 4b.4｜维度与内存的硬上限
**置信度：high（一手，README）**

- 可索引维度：`vector` 最多 **2,000 维**；`halfvec` 最多 **4,000 维**；`bit` 最多 **64,000 维**；HNSW 另支持 `sparsevec` 最多 **1,000 个非零元素**
- 仅存储（不建索引）：`vector` / `halfvec` 最多 **16,000 维**
- 构建内存："Indexes build significantly faster when the graph fits into `maintenance_work_mem`"；内存不足时会告警 "hnsw graph no longer fits into maintenance_work_mem after 100000 tuples"；并警告 "Do not set `maintenance_work_mem` so high that it exhausts the memory on the server"
- **NULL 向量不被索引**（cosine 距离下零向量同样不被索引）

**含义**：2,000 维上限对常见 embedding 模型（768/1024/1536 维）够用，**不是 AiFamily 的约束点**。真正的坑是"NULL 向量不被索引"——若某条家庭记忆的 embedding 生成失败落成 NULL，它会**从检索结果中静默消失**，而行仍然存在于表里。这需要在数据层用 NOT NULL 约束或显式状态字段挡住，属于 `docs/07_data/` 的设计责任。

### 声明 4b.5｜索引不被使用的条件是明确的、易踩的
**置信度：high（一手，README）**

原文："The query needs to have an `ORDER BY` and `LIMIT`, and the `ORDER BY` must be the result of a distance operator"。反例（不会用索引）：`ORDER BY 1 - (embedding <=> '[3,1,2]') DESC LIMIT 5;`

**含义**：把距离包装成"相似度分数"再降序排（一种很常见的写法）会**直接失去索引**。这是可写成测试断言的（`EXPLAIN` 中出现 Index Scan），符合宪章 R14 的"可机械检验则必须落测试"。

### 声明 4b.6｜relaxed_order 的严格排序补偿写法有 Postgres 版本依赖
**置信度：medium-high（一手 README，但为具体写法建议）**

官方给出用 materialized CTE 恢复严格排序的写法，并注明 `+ 0` 在 **Postgres 17+** 是必需的：

```sql
WITH relaxed_results AS MATERIALIZED (... ORDER BY distance LIMIT 5)
SELECT * FROM relaxed_results ORDER BY distance + 0;
```

对带距离过滤的查询，官方建议"use a materialized CTE and place the distance filter **outside** of it for best performance"，并把其他过滤放进 CTE 内部，理由是 "current behavior of the Postgres executor"。

**交叉核实（本轮额外做的一步）**：查阅 PostgreSQL 官方文档 `queries-with.html` 确认——CTE 若**只被引用一次**，默认会被 inline 折叠进父查询；`MATERIALIZED` 是**强制阻止**该折叠的手段。因此 pgvector 这条建议里 `MATERIALIZED` 关键字是**语义必需**而非风格偏好：去掉它，单次引用的 CTE 会被折叠，过滤会被下推回索引扫描内部，从而**重新触发 4b.1 的后置过滤问题**。

---

## 2. "退回结构化检索"的证据状况

### 声明 4b.7｜"团队公开写过从向量检索退回结构化检索"这一命题——**未获证据支持**
**置信度：n/a（无证据）**

任务卡要求寻找"有哪些团队公开写过从向量检索退回到结构化检索的经验"。**本轮未能获得任何可采信的一手工程博客**。原因如实记录：

- WebSearch 工具在当前模型组不可用（`tool type 'web_search_20250305' is not supported`）
- DuckDuckGo（含 html/lite 端点）返回 CAPTCHA 反爬页
- Bing 返回与查询无关的结果
- Brave Search 可用但在本轮检索中途返回 HTTP 429 限流，针对该问题的两次检索均未拿到结果

**因此本文档不对"业界是否普遍退回结构化检索"作任何断言。** 这与任务卡的要求一致：没找到可靠证据就如实写"未获证据支持"，不用推测填充。

**但需要指出**：官方 README 自身（声明 4b.2）已经给出了一条比二手经验更强的证据——**pgvector 官方就把"在过滤列上建索引走精确检索"列为首选起点**（"A good place to start"），且明确说明它在低命中率过滤下表现良好。也就是说，"先用结构化过滤 + 精确检索，不要一上来就 ANN"**本身就是官方推荐路径**，无需外部团队经验来支撑。这条替代证据的强度高于任何工程博客。

---

## 3. 平台侧长期记忆的另一条路线（一手，非向量）

### 声明 4b.8｜主流 agent 平台的持久记忆实现是**文件系统 + 路径寻址 + 版本审计**，而非向量检索
**置信度：high（一手，Anthropic Managed Agents 平台文档）**

要点：
- 记忆存储（memory store）以**文件目录**形式挂载进容器（`/mnt/memory/<store-name>/`），agent 用普通文件工具（`read`/`write`/`edit`/`glob`/`grep`）读写，**没有专用 memory 检索工具**
- 单条记忆是按 `path` 寻址的文本文档，**每条 ≤ 100KB，官方明确建议"prefer many small files"**
- 访问控制在**文件系统层**强制：`access: "read_only"` 使挂载只读
- 每次变更产生**不可变版本快照**（`operation` ∈ created/modified/deleted），记录 `created_by` актор（session/api/user），并支持 `redact` 清除历史版本内容但**保留审计痕迹**（actor + 时间戳）
- 支持乐观并发：`precondition: {type: "content_sha256", ...}`，不匹配返回 409

**对 AiFamily 的直接含义（这是本文档对 `AI_ARCHITECTURE.md` §2 最实质的修正建议）**：`AI_ARCHITECTURE.md` §2.1 把三层画像的缺口归结为"embedding/pgvector 完全不存在于代码"，隐含假设"长期记忆 = 向量检索"。但一个成熟平台的长期记忆实现里，**向量检索不是必需组件**；载荷是结构化路径 + 小文件 + 不可变版本 + 显式 actor 归属 + 可 redact。

后四项恰好正面命中 AiFamily 的合规硬约束：
- **不可变版本 + actor 归属** → 直接支撑 R6（AuditEvent）与 R9（AI 输出可溯源、不得静默变成 Fact）
- **可 redact 但保留审计痕迹** → 直接支撑未成年人数据删除权与 PIPL 下的删除请求，同时不破坏审计链
- **read_only 挂载** → 支撑 `may_mutate_business_state: false`（`MIGRATION_PLAN_V2.md` 第 0 节 AI Runtime 隔离规则）

**推论**：Family Context 的 P0 最小可用检索层，**优先级最高的不是接 embedding，而是把"结构化路径 + 版本审计 + actor 归属"这套地基先建对**。向量检索是之后的召回增强，不是地基。

---

## 4. 未获证据支持

1. **"pgvector 在什么规模下不够用"的具体阈值**：官方文档给出机制与参数（`ef_search`=40、`max_scan_tuples`=20,000、2,000 维），但**不给出行数量级阈值**。本轮亦未获得任何可信的独立基准测试。因此"pgvector 在 N 行以上不够用"**未获证据支持**，不作断言。
2. **从向量退回结构化的公开团队经验**：见声明 4b.7，检索工具受限，无证据。
3. **家庭长期上下文场景的召回率要求**：无外部证据说明这类场景需要多高召回率。这必须由 AiFamily 自己用真实数据界定。

---

## 5. 建议走 ADR 的结论

| 结论 | 依据 | 影响文档 |
|---|---|---|
| Family Context 检索层**不得**采用"单表 + 单一 HNSW 索引 + 后置 family_id 过滤"形态（会静默漏检家庭历史） | 4b.1、4b.3 | `docs/07_data/DATA_ARCHITECTURE.md`、`docs/05_ai/AI_ARCHITECTURE.md` §2 |
| P0 阶段应走"`family_id` 结构化过滤 + 精确距离排序"，ANN 索引延后到有实测需求；规模化时按 `family_id` 分区 | 4b.2、4b.3、4b.7 | 同上 |
| 长期记忆地基应先建"结构化路径 + 不可变版本 + actor 归属 + 可 redact"，向量检索是后续增强而非前置条件 | 4b.8 | `docs/05_ai/AI_ARCHITECTURE.md` §2.1/§2.2、`docs/07_data/` |
| embedding 列必须 NOT NULL（或有显式状态字段），否则记忆会静默从检索中消失 | 4b.4 | `docs/07_data/` + `database/migrations/` |
| 增加架构测试：向量查询必须走 `ORDER BY <距离运算符> ... LIMIT`；禁止"相似度分数降序"写法 | 4b.5 | `tests/architecture/` |
| 若采用 `relaxed_order`，`MATERIALIZED` 关键字为语义必需（防 CTE inline 导致过滤下推） | 4b.6 | 同上 |

---

## 6. 声明汇总

| # | 声明 | 置信度 | 来源类型 |
|---|---|---|---|
| 4b.1 | 过滤在索引扫描之后执行；10% 命中 + ef_search=40 → 平均仅约 4 行 | high | 一手（pgvector README） |
| 4b.2 | 四种应对手段各有适用条件；迭代扫描自 0.8.0 起 | high | 一手（README + CHANGELOG） |
| 4b.3 | AiFamily 的 family_id 过滤形态指向分区 / 精确检索，而非单一大索引 | medium-high | 推论（套用官方判据） |
| 4b.4 | 维度上限 2,000（vector）/4,000（halfvec）；NULL 向量不被索引 | high | 一手（README） |
| 4b.5 | 索引仅在 `ORDER BY <距离运算符> ... LIMIT` 下被使用 | high | 一手（README） |
| 4b.6 | relaxed_order 的严格排序补偿需 MATERIALIZED；`+0` 需 PG17+ | medium-high | 一手（README）+ PostgreSQL 官方文档交叉核实 |
| 4b.7 | "团队公开退回结构化检索"的经验 | **未获证据支持** | 检索工具受限 |
| 4b.8 | 成熟平台的长期记忆 = 文件路径 + 小文件 + 不可变版本 + actor + redact，非向量 | high | 一手（Anthropic 平台文档） |
