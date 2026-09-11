---
id: RESEARCH-DOC-AUDIT-2026-09-11
title: AiFamily 文档体系复盘审计（2026-09-11）
type: research
status: draft
version: 1.0
owner: chief-architect
created: 2026-09-11
updated: 2026-09-11
canonical: false
supersedes: null
superseded_by: null
---

RESEARCH_ONLY — 本文档是调研/证据记录，不是决定。任何要据此改架构或归档
文档的行动，必须先按`docs/12_governance/DOCUMENT_GOVERNANCE.md`§8.2走
Research→Decision（ADR）→Canonical流程，不得直接引用本文档作为实施依据。

# AiFamily 文档体系复盘审计（2026-09-11）

## 一、本轮已修复的问题

### 1.1 我自己当天新建的三份AGI平台文档违反既有治理规范

`docs/12_governance/DOCUMENT_GOVERNANCE.md`明确规定"canonical: true 只能
出现在 status: current 的文档上"以及"禁止版本号作为文件名"，但
2026-09-11当天新建的三份文档（AGI平台战略蓝图、技术总架构、R2-R5建设
蓝图）全部违反：`status: draft` + `canonical: true`并存，文件名带
`V1`/`V1_1`版本号。已修复：

- `docs/01_strategy/FAMILY_AGI_PLATFORM_V1_BLUEPRINT.md` → 重命名为
  `docs/01_strategy/FAMILY_AGI_PLATFORM_BLUEPRINT.md`，`canonical`改为
  `false`
- `docs/00_system/FAMILY_AGI_PLATFORM_V1_1_TECHNICAL_ARCHITECTURE.md` →
  重命名为`docs/00_system/FAMILY_AGI_PLATFORM_TECHNICAL_ARCHITECTURE.md`，
  `canonical`改为`false`
- `docs/00_system/FAMILY_AGI_R2_R5_BUILD_BLUEPRINT.md` → 文件名本身不含
  版本号，未重命名；`canonical`改为`false`
- 三份文档之间的互相引用（`extends`/`relates-to`字段+正文引用）已同步
  更新为新文件名，全仓`grep`确认无残留旧文件名引用

### 1.2 `DOCUMENTATION_MAP.md`补入三份新文档条目

`docs/00_system/`与`docs/01_strategy/`两行的"当前内容"列已补上三份新
文档（用改名后的文件名），并加了一段2026-09-11补记，明确说明这只是
局部补充，全表其余内容仍是2026-08-29的快照，已知严重过时（见第二节）。

### 1.3 `DOCUMENT_GOVERNANCE.md`§9两处可验证过时的陈述已修正

- 原文"Manifest §5.1列出8份L0文档，实际只有4份存在（缺
  CURRENT_DOMAIN_MAP.md/CURRENT_PRODUCT_MAP.md/CURRENT_PROGRAM_STATUS.md）"
  ——实测三份文件均已存在，标记为"已解决"。
- 原文"governance/ADR/与governance/schemas/目前为空目录，尚无一份ADR"
  ——实测`governance/ADR/`有188份文件，`governance/schemas/`确实仍不
  存在，拆分成两句分别标注真实状态。
- 新增第8条债务："归档流程未定义如何处理被ADR/registry引用的文档"，
  这是本轮复盘过程中新发现的真实空白，见第三节。

## 二、`docs/00_system/SYSTEM_MANIFEST.md`§5.1清单与`TARGET_ARCHITECTURE.md`
## 的不一致（发现但未裁决）

`TARGET_ARCHITECTURE.md`自身frontmatter声明`canonical: true`、
`status: current`，但`SYSTEM_MANIFEST.md`§5.1的canonical L0清单（8份
文档）里**没有列出它**。这意味着：按`DOCUMENT_GOVERNANCE.md`的规则字面
理解，`TARGET_ARCHITECTURE.md`的canonical地位目前只是"自称"，没有被
最高权威清单正式确认。

**本轮未处理，原因**：把一份文档加入`SYSTEM_MANIFEST.md`§5.1清单，
本质是一次"裁定谁是canonical"的架构决定，不是"文档规范化"任务该单方面
做的事——即便这份文档内容早已被广泛引用、大概率理应在清单里。留给总
架构师裁决：(a) 把它正式加入§5.1清单，或(b) 判断它其实应该是
Specification类而非Current Truth类，改成`canonical: false`跟其它
Specification文档一致。

## 三、发现但本轮未处理的文档组（每项均说明为何不能直接归档/合并）

### 3.1 AI技术架构三文档组

- `docs/05_ai/AI_TECHNICAL_ARCHITECTURE.md`（`canonical:false`，
  frontmatter自己声明`superseded_by: AI_TECHNICAL_ARCHITECTURE_DEEP_
  DESIGN.md`）
- `docs/05_ai/AI_TECHNICAL_ARCHITECTURE_DEEP_DESIGN.md`（`supersedes`
  指回前者）
- `docs/05_ai/GENERATIVE_SYSTEM_ARCHITECTURE.md`（独立存在，内容是对
  "主要矛盾""FGCN"等概念出处的证据性质证，跟前两者角色不同，不建议
  合并）

**为什么本轮不直接归档`AI_TECHNICAL_ARCHITECTURE.md`**：尽管它自己
声明已被取代，实测它被4份**已接受**ADR（0024/0048/0049/0053）和3份
机器可读registry（`AI_USE_CASE_REGISTRY.yaml`/`DOMAIN_REGISTRY.yaml`/
`MIGRATION_MANIFEST.yaml`）按路径引用。`DOCUMENT_GOVERNANCE.md`§8.1的
归档流程（`shutil.move`到`99_archive/`）会改变文件路径，而该流程没有
规定"归档后如何处理引用它的旧ADR/registry路径"——本仓库迄今只归档过
1份文件（`2026/strategy/Family家庭教育成长平台实施方案_V1.1.txt`），
没有先例证明"归档一份被ADR引用的文档"是安全的。**建议**：先核实这4份
ADR和3份registry具体引用的是文档的哪部分内容（是否仍需要那部分内容、
还是仅作历史存档引用），再决定归档时是否需要给旧ADR加脚注或改用软链接
式的`superseded_by`路径记录，而不是直接移动文件。

### 3.2 2026-08-30批次三份探索性草稿

- `docs/00_system/ARCHITECTURE_ALIGNMENT_V2.md`
- `docs/00_system/ARCHITECTURE_BENCHMARK_REVIEW_V3.md`
- `docs/00_system/CORE_BLUEPRINT_GLOBAL_SCALE_ALIGNMENT.md`

三份均`canonical: false`、`status: draft`、创建于2026-08-30（仓库重建
后第二天的探索性架构笔记），内容在精神上已被`TARGET_ARCHITECTURE.md`
（创建于2026-08-29，更早但更权威）和今天新建的AGI平台三文档取代或吸收。

**为什么本轮不直接归档**：实测被3份**已接受**ADR（0026/0027/0030）和
1份`docs/11_delivery/`文档按路径引用。同3.1，没有先例证明这类归档
安全，本轮不动。

**注意跟`FAMILY_NEEDS_PLATFORM_TARGET_MODEL.md`的区别**：这份文件同样
`canonical:false status:draft`创建于2026-08-30，但**不建议归档**——
今天新建的`FAMILY_AGI_PLATFORM_BLUEPRINT.md`第十节明确把它列为"保留为
权威——N0-N8需求闭环...是孩子成长纵向场景的具体落地规范"，正在被主动
引用中，跟前面三份"已无人引用、内容被吸收"的情况不同，不应该混为一类
处理。

### 3.3 IPD相关五文档

- `docs/01_strategy/AIFAMILY_EVIDENCE_LED_IPD_REDESIGN_V2.md`
- `docs/01_strategy/AIFAMILY_IPD_PRODUCT_SYSTEM_REDESIGN_V1.md`
- `docs/01_strategy/IPD_PLATFORM_IMPLEMENTATION_BLUEPRINT_V1.md`
- `docs/03_product/IPD_PDM_PLM_COMPONENT_FACTORY_V1.md`
- `docs/03_product/IPD_AI_PRODUCT_FACTORY_21_90_DAY_V1.md`

**这组的"70-90%内容重叠"判断来自Explore子agent的报告，我本人尚未逐份
重读五份文档原文核实这个重叠度**——鉴于同一个子agent在这次调研里已经
犯过一次可验证的事实错误（声称`governance/ADR/`为空目录），这个具体的
重叠度数字在我亲自核实之前不能作为合并依据。此外这五份文件名全部带
版本号（`_V1`/`_V2`），本身也违反`DOCUMENT_GOVERNANCE.md`的命名规范，
但同样需要先确认有没有被ADR引用才能安全重命名/合并。**建议**：作为
独立的后续任务，先人工重读五份原文，再决定是否合并、合并成几份、以及
是否有ADR/registry引用需要同步处理。

### 3.4 `docs/04_domains/`只有1份文件，15个真实域缺边界文档

`docs/04_domains/`目前只有`DOMAIN_ARCHITECTURE.md`一份，而
`backend/domains/`下已有多个真实Python域（`family_need`已是正式N1-N8
Domain Aggregate，`product_intelligence`/`membership`/
`loyalty_points`等，具体数量需要重新核对`governance/DOMAIN_REGISTRY.yaml`
跟磁盘是否一致）。

**这不是清理/归档任务，是内容生产任务**——需要为每个真实存在的域写一份
边界文档（聚合、不变量、Command、Event、Port），工作量远超本轮"归整
现有文档"的范围，本轮不做，登记为独立的后续任务。

## 四、方法论备注：子agent报告不能直接采信

本轮用Explore子agent对`docs/`全树做初步盘点，其报告在"应合并/归档"的
判断上有相当的参考价值，但**报告里声称`governance/ADR/`是空目录，实测
188份文件**——这是一个可以用一条`ls`命令在几秒内验证的事实性错误。这
再次确认了本仓库已有的`AGENT-EVIDENCE`纪律（"Agent narrative is not
execution evidence"，见ADR-0167）不仅适用于代码任务，同样适用于文档
调研任务：子agent的结论必须逐条用真实文件系统/git查询核实，才能作为
归整决策的依据，不能直接采信汇总报告。

本轮对报告里的关键结论逐条做了独立核实（`ls`/`grep`/`head`直接读取
frontmatter和引用关系），核实过程中发现的、比"文档太多需要合并"更重要
的过程性教训是：**几乎所有表面上看起来"明显该归档"的文档，实际都被
历史ADR按路径引用**——这个发现本身比任何具体的合并/归档建议都更有
价值，已经作为`DOCUMENT_GOVERNANCE.md`§9新增的第8条债务记录下来。
