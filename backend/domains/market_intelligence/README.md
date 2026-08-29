# market_intelligence — STRUCTURE_ONLY

本目录是候选 Batch 9(Market Intelligence Engine)骨架,状态 = `STRUCTURE_ONLY`。

**与 `product_strategy` 的区别**:本域在 `FAMILY_AI_PYTHON_ONLY_MIGRATION_PLAN_V1.md` §8 的
Batch 划分里**没有预留位置**——是本次会话新增的范围,已在 `CURRENT_SPRINT.md` 记 Override 留痕,
但尚无 `governance/AUTHORIZATION_REGISTRY.yaml` 正式条目。

- 只有 `domain/entities.py`(`RawSignal`/`SignalCluster` 空壳,无方法、无护栏)+ `domain/errors.py`。
- 没有 P0/P1 已批准增量可对齐(不像 `product_strategy` 有 `primary_contradiction` 字段先例),
  因此本骨架比 `product_strategy` 更薄,不建 application/infrastructure/api 层占位。
- 禁止在真实业务代码中 import 本目录内容,直到对应 Batch 被正式授权。

背景:`architecture/FAMILY_PRODUCT_INTELLIGENCE_PLATFORM_TARGET_ARCHITECTURE_DRAFT_001.md` §3。
