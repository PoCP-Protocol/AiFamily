---
id: DATA-FAMILY-MEMORY-001
title: Family 孩子、家长与家庭关系记忆体架构
type: data-architecture
status: draft
version: 0.1
owner: chief-architect
created: 2026-08-30
updated: 2026-08-30
canonical: false
---

# Family 孩子、家长与家庭关系记忆体架构

## 1. 记忆体目标

平台要能随着家庭共同经历的增加，更懂孩子、更懂家长、更懂家庭关系，但“更懂”必须
来自授权、可见、可纠正的成长证据，而不是无限采集、隐性画像或监控。

```text
家庭表达/行动/服务交互
  → 明确目的与同意
  → 记忆候选
  → 家庭/人工确认
  → 分层存储和过期策略
  → 最小必要检索
  → 个性化陪伴和方案
  → 反馈/纠正/删除
```

记忆是平台的长期能力，也是家庭的可控资产；任何记忆都必须能回答“来源、目的、范围、
谁可见、保存多久、如何修改、如何删除”。

## 2. 三类记忆体

### 2.1 孩子记忆体（Child Memory）

记录孩子在明确授权范围内的兴趣表达、学习节奏、行动反馈、偏好和被确认的成长观察。
不记录诊断标签、性格定论、隐性情绪分数或可用于商业营销的脆弱性标签。

### 2.2 家长记忆体（Guardian Memory）

记录家长主动确认的目标、沟通偏好、可用时间、服务偏好、已知边界和对建议的采纳/改写
习惯。家长可以查看、修改、撤回和限定用途。

### 2.3 家庭关系记忆体（Relationship Memory）

记录家庭共同确认的互动节奏、共同约定、已完成的小行动、修复尝试、支持方式和家庭故事。
它描述“关系如何共同经历”，不对家庭成员进行相互排名或贴标签。

## 3. 记忆分层

| 层级 | 内容 | 默认生命周期 | 使用边界 |
|---|---|---:|---|
| M0 会话记忆 | 当前对话、临时语音/图片/视频引用 | 会话期/短 TTL | 当前请求 |
| M1 主动偏好 | 家庭或家长确认的语言、节奏、沟通偏好 | 可撤回、有 TTL | 同一家庭/目的 |
| M2 成长上下文 | 评估证据、行动记录、服务交付和关系观察投影 | 按主体/目的留存 | 明确同意 + 最小必要 |
| M3 长期学习特征 | 脱敏后的阶段性模式、组件质量和服务改进信号 | 通过 DPIA 后启用 | 不回写家庭事实、不做商业画像 |

M3 不是默认能力；未完成 DPIA、删除演练、租户隔离和人工抽检前不得启用。Embedding、
摘要、缓存和评估副本都继承源记忆的主体、目的、区域和删除引用。

## 4. 数据对象和关系

```text
MemoryCandidate
  → MemoryConsent
  → MemoryConfirmation（家庭/人工）
  → ChildMemory / GuardianMemory / RelationshipMemory
  → MemoryRetrieval
  → PrincipalResponse / SolutionDraft
  → MemoryFeedback / Correction / DeletionProof
```

建议对象/表：

- `memory_candidates`：AI/系统提出的候选，不代表已记住；
- `memory_consents`：用途、主体、可见范围、区域和版本；
- `child_memory_items`：孩子记忆体；
- `guardian_memory_items`：家长记忆体；
- `family_relationship_memory_items`：家庭关系记忆体；
- `memory_retrievals`：谁在什么目的下读取了什么；
- `memory_corrections`：家庭/人工的改写、撤回和纠错；
- `memory_deletion_jobs` / `memory_deletion_proofs`：级联删除和完成证明。

已有 `context_snapshots`、`principal_sessions` 和 `principal_model_runs` 继续作为运行时
上下文和审计对象；不另建第二套模型运行追踪表。上述记忆对象只保存引用、结构化观察和
确认状态，不直接保存未经处理的完整媒体或模型散文。

## 5. 记忆写入与读取规则

### 写入

1. 明确采集目的、主体、同意版本、数据分类、区域和过期时间；
2. AI 只能产生 `MemoryCandidate`，不能直接写三类记忆体；
3. 家庭或授权工作人员确认后，才形成可检索的记忆事实/偏好；
4. 记录来源、证据、版本、确认者、可见范围和删除引用；
5. 记忆与原始事实分离，原始事实删除时所有派生记忆级联处理。

### 读取

1. 只读取当前目的、租户、区域、家庭和主体范围内的最小记忆；
2. 孩子记忆默认由家长授权和可见性策略控制，不能被商业流程直接读取；
3. 家庭关系记忆需要家庭范围授权，不能被单个服务商带出家庭；
4. 每次读取生成 `MemoryRetrieval` 审计，展示“为什么使用这条记忆”；
5. 不支持的语言、区域或政策不得用错误记忆回退。

## 6. 让平台“越来越懂”的合法方式

- 把完成、跳过、改写、暂停和投诉当作反馈信号，而不是简单正/负标签；
- 把家庭确认的偏好用于下一次沟通和节奏调整，而不是跨目的广告；
- 把交付验收和质量证据用于组件/方案改进，不把满意度等同于成长结果；
- 把多次共同经历沉淀为关系故事和可解释的下一步，不生成家庭总分；
- 允许家庭看到、纠正、撤回和删除，删除后的派生索引、缓存、Embedding 和评估副本必须
  有完成证明。

## 7. 多模态记忆

语音、图片、音频和视频形成 `MediaAsset`；转写/OCR 形成派生 `MediaTranscript`；只有
经授权、脱敏和确认的内容才可形成记忆候选。原始媒体、转写、摘要、Embedding 和引用
分别保存 provenance、locale、data_class、retention 和 deletion_ref，不能把家庭影像
直接塞入长期记忆或公共知识库。

## 8. AI 与应用边界

法咪莉校长负责解释“我记得什么”和提出下一步记忆候选；Context Broker 负责最小检索；
Human Gate/家庭确认负责高影响记忆；Named Action 或 Memory Confirmation Service 负责
形成记忆事实。任何模型、Agent 或 UI 都不能绕过确认直接修改 Child/Guardian/Relationship
Memory。

## 9. 验收标准

- 同一家庭跨会话能复用已确认偏好，但跨家庭/租户/区域读取必然拒绝；
- 家庭能查看、纠正、撤回和删除三类记忆；
- 未授权未成年人数据不进入商业推荐、排名或公共知识；
- 记忆引用可追溯到 `source → consent → confirmation → retrieval → response`；
- 删除演练覆盖原文、快照、记忆、媒体派生物、缓存、Embedding、评估副本和供应商回执；
- dev/test/prod 的记忆状态机、权限、错误码、闸门和删除路径相同，测试只替换合成数据。
