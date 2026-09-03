# ADR-0105：多模态评测切片归档

## 状态

Accepted — 2026-08-30

## 决策

切片评测结果写入独立的 `ai_benchmark_report_slices` 表，与父 benchmark 报告在
同一 production archive transaction 中提交。唯一键为 `report_ref + dimension + value`，
重复归档幂等，内容或 dataset fingerprint 冲突 fail-closed。查询只返回 bounded
aggregate metadata，不能读取媒体、prompt、模型原文或家庭数据。

## 证据

- `backend/intelligence/evaluation/slice_archive.py`
- `database/migrations/versions/0035_ai_benchmark_report_slices.py`
- `backend/apps/family_api/production_evaluation_archive_wiring.py`
- `tests/intelligence/evaluation/test_slice_archive.py`
- `tests/apps/family_api/test_production_evaluation_archive_wiring.py`
