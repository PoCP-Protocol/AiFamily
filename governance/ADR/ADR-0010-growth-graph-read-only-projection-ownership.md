# ADR-0010: Family Growth Graph 的跨进程归属 —— 写入归业务域，AI 侧只读投影

- **Status**: Accepted
- **Date**: 2026-08-29
- **Deciders**: chief-architect（project-owner 可 override）
- **Supersedes**: null
- **Superseded By**: null

## Context

`docs/00_system/TARGET_ARCHITECTURE.md` §6 把「Family Growth Graph 归属拆分 —— 需更细的 Port
契约设计」列为等架构师裁决项，同文件已有的初步判断是「数据结构 → 业务域持久化层；
查询/推理 → `backend/intelligence/`」，但**未决的是这个拆分靠什么落地**。
`docs/00_system/CURRENT_AI_MAP.md` §5 记该独占区候选 `ABSENT`、「完全空白」，
并注明「归属分歧（是否需专门只读投影层跨进程）未裁决」。本 ADR 是该裁决。

约束该裁决的四条既有硬事实：

1. **AI Runtime 不得 import 业务域 repository。**
   来源：`governance/REPOSITORY_CONSTITUTION.md` R10；
   `docs/05_ai/AI_ARCHITECTURE.md` §4.3 引 `MIGRATION_PLAN_V2.md` §0 的 AI Runtime 隔离规则
   （`may_mutate_business_state=false`，「只能产出 Draft/Hypothesis/Explanation/Proposal，
   canonical 写入只能经业务域自己的 Named Action」）。
   `docs/11_delivery/TASK_BACKLOG.md` T-06 亦把它列为红线。
   **所以 AI 侧读取业务数据的通路必须被显式设计出来——不设计的后果不是「没有通路」，
   是「有人在某个 PR 里顺手 import 了一个 repository」。**

2. **Growth Graph 是 AI 原生的地基，不是可选增强。**
   `docs/05_ai/AI_NATIVE_PRINCIPLES.md` §3.3 定性它是判据 2（数据结构为 AI 理解而设计）
   与判据 4（越用越准）的载体，且「源仓库审计已确认完全空白，因此它们是新建，不是优化」。

3. **三进程划分是硬要求，且恰好是三个。**
   `AI_NATIVE_PRINCIPLES.md` §3.1：`family_api` / `ai_runtime` / `workflow_worker`，
   「缺任何一个，AI 原生都不成立」。这条同时是上界——第四个进程需要独立 ADR 论证。

4. **domain events 与 outbox 机制当前完全不存在。**
   `docs/00_system/CURRENT_SYSTEM_BASELINE.md` §4.8 记「源仓库全域 grep `DomainEvent`
   精确类名 = 0 命中」，AiFamily 侧同样不存在。**这是本 ADR 的真实前置缺口。**

5. 时序是这个图的本体，不是附属。`AI_NATIVE_PRINCIPLES.md` §3.3 要求
   「证据 / 假设 / 上下文快照 / 时序（T0→T1→T2→T3）是一等实体」。

## Decision

### 1. 写入真相归业务域聚合，Growth Graph **不是**一个域

Growth Graph 没有自己的写入端，也不登记为 `DOMAIN_REGISTRY.yaml` 的一个 capability
（否则它会成为第二个拥有成长真相的地方，直接违 R2）。
节点与边的权威来源是既有业务域各自的聚合：`family` / `assessment` / `journey` /
`action` / `outcome` / `service`。**Graph 是这些聚合的一个视图，不是它们的上级。**

### 2. AI 侧的唯一合法通路：独立只读投影 schema + 一个 Query Port

```
domains/*  --(DomainEvent → outbox)-->  projector  -->  graph_projection.*  (独立 PG schema)
                                                              ↑ SELECT only
                                  intelligence/*  --(GrowthGraphQueryPort)--┘
```

- 投影落**独立 PostgreSQL schema `graph_projection.*`**，与业务域 schema 物理分离
  （符合 `docs/07_data/DATA_ARCHITECTURE.md` 的分域 schema 目标设计）。
- **投影专用 DB role 只授 `SELECT`。** 这是本 ADR 最重要的一句：
  「AI 不能写业务真相」由此成为**数据库权限层的事实**，而不是代码约定。
  它在代码之外，因此任何静态检查被绕过、任何 review 疏漏，都不会使它失效。
- `intelligence/` 侧只见 `GrowthGraphQueryPort`（Protocol），
  **定义在 `backend/intelligence/` 内**，实现也在 `intelligence/` 内（读投影 schema）。
  它**不** import 任何 `backend.domains.*`。共享词汇（`Provenance` 等）走
  `backend/packages/contracts`——已是仓库唯一真正跨域共享的原语。
- 投影是**派生数据**。按 ADR-0006 与 `COMPLIANCE_HARD_CONSTRAINTS.md` §6，
  删除权覆盖派生数据，因此投影必须支持**按主体级联删除**，
  且删除路径必须与业务域删除同事务或有补偿。**这不是可选项，是法定义务。**

### 3. 不新建第四个进程

投影构建（projector）由 `workflow_worker` 承载，不单开进程。
`workflow_worker` 的既有定位是「AI 提议→人工确认→落库」这类跨时长流程
（`AI_NATIVE_PRINCIPLES.md` §3.1），异步投影构建与之同类。
在 `workflow_worker` 真正建立前，投影层**不实现**——见 §5。

### 4. 时序建模：投影按 `(subject, valid_from, valid_to)` 存，不做原地更新

Graph 的价值在 T0→T1→T2→T3 的变化轨迹。投影行**只追加不覆盖**
（与 `loyalty_points` 的 ledger 思路一致：`backend/domains/loyalty_points/domain/entities.py`
的 `PointsAccount` 无 `balance` 字段，余额永远由 entries 计算）。
**禁止**在投影上存任何聚合分值字段——R9 红线，且 `graph_projection.*`
必须与业务 schema 同受 `test_no_scoring_or_ranking_fields_anywhere` 覆盖。

### 5. 前置条件与施工顺序（本 ADR 不授权立即开工）

严格依赖链，**不得跳步**：

```
DomainEvent + outbox 机制（当前 0 命中，不存在）
  → 至少一个域产出真实事件（Batch 3 family/relationship/consent 是最早候选）
    → workflow_worker 进程建立
      → projector + graph_projection schema
        → GrowthGraphQueryPort
```

**在 `DomainEvent` 与 outbox 存在之前，本 ADR 描述的通路一行代码都不该写。**
在此期间 AI 侧若需要业务数据，唯一合法做法是：**由 `family_api` 侧的应用服务
把数据作为参数传给 gateway 请求**（即 domain 主动推，而非 AI 主动拉）——
这不需要投影层，也不违反隔离。

## Alternatives Considered

### A. AI Runtime 直接读业务域的 read-only repository（同库同 schema，只用只读连接）
**支持理由（不弱）**：不需要 outbox、不需要 projector、不需要第二套 schema，
没有投影延迟问题（AI 看到的永远是最新数据），实现成本低一个数量级。
「只读连接」在很多系统里是完全可接受的隔离手段。

**否决理由**：
- 这要求 `intelligence/` import `backend.domains.*.infrastructure`，**直接违反 R10 红线**。
  即使限定只读，import 一旦成立，隔离就只剩「大家记得别写」在守。
- 更实质的问题是**耦合方向**：AI 侧会依赖业务域的表结构，业务域每次改 schema
  都可能静默打断 AI 侧查询。投影层的价值不只是权限隔离，是**契约隔离**。
- 「只读连接」的只读性靠连接字符串配置，而配置可以被改；投影 schema 的只读性
  靠 DB role 的授权，且投影 schema 里**根本没有业务写入路径可用**。后者强得多。

### B. Growth Graph 登记为独立域 `backend/domains/growth_graph`，自己拥有写入
**支持理由**：图有自己的一致性规则（边的合法性、时序单调性），
有个域来守护这些规则符合 DDD 直觉；且 `docs/00_system/CURRENT_AI_MAP.md` §5
把它列为独占区候选，独占区有自己的域看起来合理。

**否决理由**：**它会成为第二个拥有成长真相的地方，直接违 R2。**
一个节点「孩子完成了某个 action」如果同时存在于 `action` 域的聚合与 `growth_graph` 的表里，
就必然出现两者不一致的时刻，而那时无法回答哪个是真的。
「独占区候选」说的是这个能力有商业独占价值，**不等于它必须拥有独立的写入真相**——
独占价值在查询与推理侧（从图里看出别人看不出的东西），那部分本 ADR 已经归给 `intelligence/`。

### C. 单开第四个进程 `graph_projector`
**支持理由**：投影构建的负载特征（批量、可重放、允许延迟）与 `workflow_worker`
的长流程编排确实不同，独立进程便于独立扩缩容与独立故障隔离。

**否决理由**：`AI_NATIVE_PRINCIPLES.md` §3.1 把三进程定义为 AI 原生的判据之一，
第四个进程需要推翻或扩展那份 `STATUS = BINDING` 的文档。
而当前 `workflow_worker` **本身还不存在**——在零个进程的情况下论证「第三个和第四个
应该分开」是纯粹的想象。若将来投影负载确实压垮 `workflow_worker`，
届时有真实指标再出 ADR 拆分，那时的论证会比现在强得多。

### D. 用 PostgreSQL 视图或物化视图代替应用层投影
**支持理由**：不需要 outbox 与 projector 代码，DB 原生维护一致性，物化视图可定时刷新。

**否决理由**：`docs/07_data/DATA_ARCHITECTURE.md` 已明确决定
「跨 schema 访问只经应用层 Query Port（不用 DB 视图）」。
本 ADR 不推翻该决定。理由亦成立：视图会把业务表结构直接暴露给 AI 侧
（契约耦合问题同替代方案 A），且视图无法承载 §2 要求的**按主体级联删除**——
派生数据删除是法定义务，需要可编程的删除路径，而视图没有自己的行可删。

## Consequences

### 正面
- 「AI 不能写业务真相」下沉到 DB 权限层，成为代码之外的事实。这是本决定的核心收益。
- 契约隔离：业务域改表不静默打断 AI 侧。
- 明确了在投影层存在**之前**的合法做法（domain 主动推参数），
  堵住「因为没有通路所以顺手 import repository」这条最可能的违规路径。
- 不新增进程，`AI_NATIVE_PRINCIPLES.md` §3.1 的三进程定义保持完整。

### 负面 / 代价
- 引入投影延迟。AI 侧看到的是最终一致数据。对「成长轨迹」这类分析场景可接受，
  但**任何需要强一致的 AI 判断都不能走投影**，必须走 domain 主动推参数的路径。
- 需要 outbox + projector 两套此前不存在的机制，工程量真实。
- 派生数据的级联删除是额外的持久化负担，且**必须从第一天就有**（法定义务，
  不能「先上线再补」）。
- 投影 schema 是一份数据冗余，存储与备份成本翻倍。

### 需要接受的风险
- **最大风险：本 ADR 的整条依赖链都建立在尚不存在的机制之上**（DomainEvent / outbox /
  workflow_worker 全为 0）。因此它是一份**长期有效但短期不可执行**的决定。
  这本身是危险的——一份描述了完整通路的 ADR，容易被误读为「通路已设计好可以用了」。
  缓释：§5 明确写了「在 DomainEvent 与 outbox 存在之前，一行代码都不该写」，
  且 `CURRENT_AI_MAP.md` 必须继续把 Growth Graph 记为 `ABSENT`——
  **有 ADR 不等于有能力**。
- 「投影 role 只授 SELECT」依赖部署时的 DB 权限配置正确。
  这是代码之外的强度来源，同时也意味着**代码里的测试无法验证它**——
  必须靠部署清单与一次真实的权限验证（见 Enforcement）。

## Enforcement

**部分可机械执行；最强的一层反而不在代码里——如实记录这个不对称。**

已可执行 / 应立即补的（代码层）：

1. **`backend/intelligence/**` 不得 import `backend.domains.*`** ——
   本批新增 `tests/architecture/test_ai_runtime_isolation.py` 执行。
   这是本 ADR §2 在代码层的主要护栏，**它存在与否决定本 ADR 是不是空话**。
2. `graph_projection.*` 的模型定义须与业务模型同受
   `tests/architecture/test_compliance_constraints.py::test_no_scoring_or_ranking_fields_anywhere`
   覆盖（该测试按 AST 扫字段名，投影模型落地后自动纳入，无需改测试）。
3. **可补但目前不存在**：断言 `graph_projection` 相关模块中不出现
   `INSERT` / `UPDATE` / `session.add` / `commit` 等写入符号。成本低，应与投影层同批落地。

**不在代码里、但强度最高的一层**：投影 DB role 只授 `SELECT`。
架构测试无法验证生产环境的 GRANT。它必须由
(a) Alembic 迁移中显式的 `GRANT SELECT ONLY` 语句 +
(b) 一次针对真实 Postgres 的集成测试（用投影 role 连接后尝试 INSERT，断言被拒）
共同保证。**(b) 是唯一能证明这层生效的手段，投影层落地时必须有它，否则 §2 退化为意图。**

完全不可机械检验的：
- 「哪些 AI 判断需要强一致因而不能走投影」是逐案的语义判断。
- 投影内容是否真的构成「越用越准」的学习闭环（`AI_NATIVE_PRINCIPLES.md` 判据 4）——
  §5 已注明这需要真实 eval 框架，不是靠声明。

## References

- `docs/00_system/TARGET_ARCHITECTURE.md` §6 第 2 项（本裁决的来源）
- `docs/00_system/CURRENT_AI_MAP.md` §5 / §5.1（Growth Graph `ABSENT`，归属分歧未裁决）
- `docs/05_ai/AI_NATIVE_PRINCIPLES.md` §3.1（三进程硬要求）、§3.3（地基不是增强）
- `docs/05_ai/AI_ARCHITECTURE.md` §4.3（AI Runtime 隔离规则原文）
- `docs/07_data/DATA_ARCHITECTURE.md`（分域 schema；跨 schema 只经应用层 Query Port）
- `docs/00_system/CURRENT_SYSTEM_BASELINE.md` §4.8（`DomainEvent` grep 0 命中）
- `docs/12_governance/COMPLIANCE_HARD_CONSTRAINTS.md` §6（删除权覆盖派生数据）
- `backend/domains/loyalty_points/domain/entities.py`（无 balance 字段的 ledger 先例）
- `governance/REPOSITORY_CONSTITUTION.md` R2 / R9 / R10；ADR-0005 §4；ADR-0006
- `docs/11_delivery/TASK_BACKLOG.md` T-06（红线原文）
