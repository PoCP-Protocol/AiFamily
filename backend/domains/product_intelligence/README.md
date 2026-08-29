# product_intelligence — PR-001R, hardened (chief-architect review on PR #27)

状态 = 真实实现,非 `STRUCTURE_ONLY`。这是 Signal→Insight→...→ProductConcept 这条产品智能链**唯一**的
canonical 业务 Domain(`domains/market_intelligence`/`domains/product_strategy` 及重复的
`packages/contracts/product_strategy.py`/`product_factory.py` 已在 PR-001R 清理删除)。
授权记录:project-owner Override #6(PR-001)+ chief-architect PR-001R review(PR #27)+
`governance/AUTHORIZATION_REGISTRY.yaml` capability `PRODUCT_INTELLIGENCE_DOMAIN_V0_1_PR001`。

- **全链路**:`MarketSignal → CustomerInsight → Opportunity → GrowthProblem → GrowthHypothesis → GrowthStrategy → ProductConcept`
  真实创建 + 可追溯查询,SQLAlchemy 模型 + 原生 SQL migration(`0058_product_intelligence_domain.sql`)、
  FastAPI 路由(`api/routes.py`)。测试 21/21 全绿:Fake repository + SQLite-backed SQLAlchemy + **真实 Postgres 集成测试**
  (`tests/test_postgres_integration.py`,含数据库层 CHECK 约束负面测试)+ 自动化 FastAPI TestClient 覆盖
  (`tests/test_api_endpoints.py`)。
- **Actor/Tenant 信任边界**:`created_by`/`tenant_scope`/actor 身份只能来自 `application/context.py::ActorContext`,
  客户端请求体不再携带这些字段(`api/requests.py`)。每个 `load_*` 都按 tenant 过滤,跨租户引用统一报
  `NotFoundError`(不暴露"存在但无权"与"不存在"的区别)。`api/dependencies.py::get_actor_context` 尚未接真实鉴权,
  fail-closed 抛 `RuntimeError`,等未来 identity/auth PR 落地后替换其实现。
- **AI Provenance 契约**:`context.actor_type == "AI"` 时,`model_ref`/`prompt_use_case_version`/`confidence` 必须一起提供
  (`application/commands.py::_require_ai_provenance_if_ai_actor`);`confidence` 结构性限定 `[0,1]`
  (`domain/entities.py::_AiProvenanceFields`,pydantic validator,"all-or-none" 独立于 actor_type 再校验一层)。
- **Human Gate 状态机**:`GrowthHypothesis.mark_validated(actor_id, actor_type, reason)` 要求 `actor_type=="HUMAN"`,
  只允许从 `DRAFT`/`UNDER_REVIEW` 转 `VALIDATED`(`UNDER_REVIEW` 目前是预留的不可达状态,本 PR 无路径产生它),
  记录 `validated_by/validated_at/validation_reason` 并递增 `version`。
- **Persistence 基础**:所有时间字段 timezone-aware UTC;`SqlAlchemyProductIntelligenceRepository.save_*` 只
  `merge()`+`flush()`,不自行 `commit()`——事务提交交给 `infrastructure/unit_of_work.py::SqlAlchemyUnitOfWork`,
  由调用方(未来的 API 依赖/多聚合原子操作)统一控制。
- **未实现**(仍不在本 PR 范围,需各自单独授权):Component/Pattern/FPDL/Compiler 真实逻辑、AI Use Case Registry、
  Simulation Runner、任何 app 挂载(`routes.py` 未被任何 FastAPI app 实例 include,因为 `apps/family_api` 还不存在)。
