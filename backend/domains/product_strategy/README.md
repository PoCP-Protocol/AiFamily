# product_strategy — STRUCTURE_ONLY

本目录是 Batch 7/9候选(Product Strategy Engine)骨架,状态 = `STRUCTURE_ONLY`。

- 未接入任何 app/路由/依赖注入,`api/` 下没有 requests/responses/routes.py。
- `infrastructure/` 只有 Fake 实现,没有真实 SQLAlchemy repository、没有真实数据库集成测试。
- 所有需要真实数据校准的判断(信号权重、置信度排序具体数值)均未填入,`entities.py`/`ports.py` 只定义结构。
- 禁止在真实业务代码(app 路由、其他已授权 Batch 的 domain)中 import 本目录内容,直到对应 Batch 被 `governance/AUTHORIZATION_REGISTRY.yaml` 正式登记授权。

背景:`architecture/FAMILY_PRODUCT_INTELLIGENCE_PLATFORM_TARGET_ARCHITECTURE_DRAFT_001.md`,授权范围记录见 `CURRENT_SPRINT.md` Override(骨架搭建部分)。
