# ADR-0103：生产评测报告归档组合根

## 状态

Accepted — 2026-08-30

## 决策

`ProductionEvaluationArchiveRuntime` 是 staging/production 的显式组合入口。每次
归档创建独立 SQL session/transaction，调用 `SqlAlchemyBenchmarkReportArchive` 保存
metadata-only benchmark payload，成功后提交，异常由调用方观察并回滚。测试、staging、
production 共享同一 archive port；差异仅是显式 session factory 和外部调度器。

本 ADR 不内置 scheduler、报告查询 API 或长期保留策略；这些仍由部署/运营层接入，
并且不得把家庭内容或模型原文写入报告归档。

## 证据

- `backend/apps/family_api/production_evaluation_archive_wiring.py`
- `tests/apps/family_api/test_production_evaluation_archive_wiring.py`
- `backend/intelligence/evaluation/report_archive.py`
