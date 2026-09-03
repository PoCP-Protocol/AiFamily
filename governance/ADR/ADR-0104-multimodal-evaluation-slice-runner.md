# ADR-0104：多模态评测切片 Runner

## 状态

Accepted — 2026-08-30

## 决策

`MultimodalSliceRunner` 复用同一个 `MultimodalEvalRunner`，按 `modality`、`locale` 和
合成 `age_band` 对 Gold Set 分组并分别生成报告。混合模态 case 会同时进入其包含的
每个 modality 切片；这表示覆盖关系，不是重复计数总报告。切片仅使用 synthetic/anonymous
case 的契约元数据，不产生家庭或未成年人画像。

切片维度必须显式、唯一且有界；每个切片保留 case IDs 与完整的 schema/safety/
provenance/latency/cost 指标，禁止把切片结果写成教育效果或家庭比较排名。

## 证据

- `backend/intelligence/experience/slice_runner.py`
- `backend/intelligence/experience/multimodal_eval.py`
- `tests/intelligence/experience/test_slice_runner.py`
