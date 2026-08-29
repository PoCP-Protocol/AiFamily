# design_copilot — STRUCTURE_ONLY

本目录是 Batch 7(Design/Product Blueprint/Service Blueprint/Curriculum Design/Content
Generation/Design Experiment,见 `architecture/FAMILY_AI_PYTHON_ONLY_MIGRATION_PLAN_V1.md`
§8)已预留位置的骨架实现,状态 = `STRUCTURE_ONLY`。

- `compiler.py` 的 12 项检查全部 `raise NotImplementedError`,未接入任何真实校验逻辑。
- `simulation.py` 的 `SimulationLab.run()` 未实现;`SimulationResult.provenance.level` 硬编码为
  `"simulated"`,`promote_to_pilot()` 拒绝任何非真实证据的晋级请求——这是"模拟结果不能自证"护栏,
  与 `domains/product_strategy/domain/entities.py` 里的同类护栏是故意冗余的两个独立实施点。
- 未接入任何 app/路由/workflow。
- 禁止在真实业务代码中 import 本目录内容,直到 Batch 7 被正式授权。

背景:`architecture/FAMILY_PRODUCT_INTELLIGENCE_PLATFORM_TARGET_ARCHITECTURE_DRAFT_001.md`。
