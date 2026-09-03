# ADR-0102：多模态 Benchmark 报告归档边界

## 状态

Accepted — 2026-08-30

## 决策

评测报告通过 `BenchmarkReportArchivePort` 归档到 InMemory 或 SQL adapter。归档键为
`report_ref`，并绑定 Gold Set fingerprint、case version、总用例数及 bounded aggregate
payload；重复归档幂等，fingerprint 或内容冲突 fail-closed。SQL adapter 只 `add/flush`，
由应用组合根负责事务提交/回滚。

归档 payload 仅包含 schema、安全、拒答、provenance、延迟、成本和 gate 结果等聚合
指标，禁止 prompt、模型原文、媒体、家庭数据和凭据，并限制大小。此记录是发布审计
证据，不是教育效果或家庭排名数据。

## 证据

- `backend/intelligence/evaluation/report_archive.py`
- `database/migrations/versions/0034_ai_benchmark_report_archive.py`
- `tests/intelligence/evaluation/test_report_archive.py`
