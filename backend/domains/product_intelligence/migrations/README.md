# product_intelligence — raw SQL migrations (provisional, pre-Alembic)

三个文件按原样迁自 family-ai(`0058`/`0059`/`0060`),原生 SQL,不是 Alembic revision。

AiFamily 的 Alembic baseline 尚未建立(见 `docs/00_system/CURRENT_SYSTEM_BASELINE.md` §3,
阻塞在四组文件名重号 0022/0023/0024/0053 未线性化),因此这三个文件暂放这里作为
`backend/domains/product_intelligence/tests/test_postgres_integration.py` /
`test_zone_postgres_integration.py` 两个真实 Postgres 集成测试的执行依据,不代表
本域已经有正式的 Alembic migration。

一旦 Alembic baseline 建立,这三个文件的内容需要被转成对应的 Alembic revision,
本目录随之退役——不要把这个目录当作长期的 migration 存放约定。
