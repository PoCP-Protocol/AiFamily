# product_intelligence — raw SQL migrations (provisional, pre-Alembic)

三个文件按原样迁自 family-ai(`0058`/`0059`/`0060`),原生 SQL,不是 Alembic revision。

## 2026-08-29 更新（T-03）：Alembic baseline 已建立，但本目录尚未退役

本 README 原先写着"一旦 Alembic baseline 建立,这三个文件的内容需要被转成对应的
Alembic revision,本目录随之退役"。baseline 现已建立
(`database/migrations/versions/0001_legacy_schema_baseline.py`),但**退役尚未发生**,
如实说明原因,不假装已完成。

### 三个文件与 baseline 的关系（逐个）

| 文件 | 是否已在 baseline 内 | 说明 |
|---|---|---|
| `0058_product_intelligence_domain.sql` | **部分**——见下方"已发现的 schema 矛盾" | 源仓库 `database/migrations/0058` 是被线性化的最后一个迁移,成为 `database/baseline/0062_product_intelligence_domain.sql`。但本目录这一份**与它不等价** |
| `0059_product_zone_engine_v0.sql` | 否 | 诞生于源仓库 `fix/product-zone-engine-v0-closure` 分支(见 `governance/MIGRATION_MANIFEST.yaml` 条目 `product_intelligence_v2`),不在被线性化的那批 `database/migrations/*.sql` 里 |
| `0060_product_zone_engine_canonical_cleanup.sql` | 否 | 同上 |

`0059`/`0060` 按 Alembic 的规矩应该成为 baseline **之后**的 revision,不能塞进 baseline——
baseline 的定义是"源仓库那批迁移应用后的 schema 状态",混进去就破坏了这个定义。

### 已发现的 schema 矛盾（需裁决，T-03 只报告不擅自修改）

本目录的 `0058_product_intelligence_domain.sql` 与 baseline 里的
`database/baseline/0062_product_intelligence_domain.sql` **内容不等价**。忽略行尾差异
(本目录这份是 CRLF,源文件是 LF)后,唯一实质差异是
`product_intelligence_growth_hypotheses` 表多了三列:

```sql
  validated_by varchar(160),
  validated_at timestamptz,
  validation_reason text
```

事实核对:
- 源仓库 `database/migrations/0058_product_intelligence_domain.sql` 里 grep `validated_by` = **0 命中**。
  即这三列**不属于**被 baseline 忠实快照的那份权威 SQL。
- AiFamily 的 ORM 模型**要求**这三列:`infrastructure/sqlalchemy_models.py:186-188`。
- `tests/test_postgres_integration.py` 的 docstring 自述这三列是"the 0058 migration to close the
  gap this test originally discovered"——也就是说,它们是在 AiFamily(或源仓库某个分支)里
  **补进这份副本**的,补的位置是一个"忠实快照"文件,而不是一个新迁移。

**后果**:对一个只跑过 `alembic upgrade head` 的库,`product_intelligence_growth_hypotheses`
**没有**这三列,而 ORM 期望有。`validate_growth_hypothesis` 会在真实 baseline 化的库上失败。
两个真实 Postgres 集成测试现在**没有**暴露这个问题,因为它们自己读本目录的 SQL 文件建库,
绕开了 baseline——测试和生产用的是两份不同的 schema。

**建议(待 owner 拍板)**:新增一个 baseline 之后的 Alembic revision,内容为
`ALTER TABLE product_intelligence_growth_hypotheses ADD COLUMN validated_by / validated_at /
validation_reason`,并把 `0059`/`0060` 一并写成 revision;然后让这两个集成测试改为经
`alembic upgrade head` 建库,本目录随之删除。**不建议**把这三列补进 `database/baseline/`——
那会让 baseline 不再等于源仓库快照,`tests/database/test_baseline_linearisation.py` 的
sha256 校验也会失败(这正是该校验存在的意义)。

这项工作属于 T-05 范围(该任务要落 Alembic 迁移),不在 T-03 的"只做线性化+baseline"范围内——
`docs/07_data/DATA_ARCHITECTURE.md` §5 明确要求 baseline PR 不夹带其它 schema 变更。

在那之前,本目录仍是 `test_postgres_integration.py` / `test_zone_postgres_integration.py`
两个真实 Postgres 集成测试的执行依据,**不要**把这个目录当作长期的 migration 存放约定。
