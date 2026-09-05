# ADR-0072: Durable, scoped AI memory reference store

- 状态：Accepted for experiment
- 日期：2026-08-30
- 范围：`backend/intelligence/memory`

## 背景

AiFamily 的 Memory 合约已经要求 M0–M3 的明确期限、家庭/主体作用域、同意版本、来源和删除级联，但此前只有进程内适配器。进程重启会丢失已确认记忆，无法满足测试环境与生产环境能力一致，也无法证明删除请求在重启后仍可审计。

## 决策

新增 `SqlAlchemyMemoryStore` 与 Alembic `0022_ai_memory_store`：

1. 只持久化 `MemoryRef` 引用和治理元数据，不写入原始提示词、媒体字节、embedding 或模型输出。
2. 写入按 `memory_id` + 稳定指纹幂等；同一 ID 不同内容拒绝，跨租户拒绝。
3. 读取继续复用 `MemoryRef.assert_readable_by`，严格校验租户、家庭、主体、purpose、consent 和 expiry。
4. 删除按 `deletion_ref` 级联 source/derived 引用，并留下 `MemoryDeletionProof`；过期清理走同一删除路径。
5. 该层不调用模型、不推断事实、不写入 Family/Journey/Commerce 权威表；模型生成仍必须经过 Model Gateway。

## 取舍与后续

当前实现是 durable reference store，不是向量检索引擎。后续如引入 embedding，必须新增独立 provider-neutral embedding port、可删除索引和人工/合规评审，不能绕过本 ADR 的作用域与保留期约束。
