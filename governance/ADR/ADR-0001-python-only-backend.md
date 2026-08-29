# ADR-0001: 后端单轨 Python（不保留 NestJS 作为第二后端）

- **Status**: Accepted
- **Date**: 2026-08-29
- **Deciders**: project-owner / chief-architect
- **Supersedes**: null
- **Superseded By**: null

## Context

AiFamily 的迁移源 `PoCP-Protocol/family-ai` @ `1ff168123d147f4d6a6eaaa677bc2f80986233d9`（本机 `D:\family-ai`）在 `50_开发_dev` 下的 2060 个受控文件里，**同时存在四条后端血脉，没有一条是权威的**：

1. **NestJS 生产 API** — `50_开发_dev/apps/api`。真实 PostgreSQL、60+ 路由，最大服务文件 `src/modules/family/family.service.ts` 2293 行，e2e / integration / spec 覆盖完整（`family-core-integration.e2e-spec.ts` 含 M1-E2E-01 全链路）。这是唯一真正在跑的后端。
2. **5 个 Python 领域** — `50_开发_dev/backend/domains/{product_intelligence,membership,product_strategy,market_intelligence,growth_plan}`。合计数千行，但**全仓库零个 `FastAPI()` / `uvicorn.run()` / `include_router()` 首方调用**；唯一的 `APIRouter`（`product_intelligence/api/routes.py`）在自己的注释里写着 "Not mounted into any app yet"。也就是说：有领域层，没有进程。五个域里只有 `product_intelligence` 有测试。
3. **源码已删只剩 `.pyc` 的 Python 应用** — `50_开发_dev/apps/ai-runtime`。git 从未跟踪；`.py` 源文件已从磁盘消失，能力的唯一证据是编译产物；其 `dist-info` 自述 "not wired into the default request path"。
4. **声明 NestJS 依赖却不是 Nest 应用的"应用"** — `50_开发_dev/apps/fes-api`。`package.json` 里有 NestJS 依赖，但全模块无 `@Module`、无 `NestFactory`、无 controller；`src/main.ts` 运行即打印一行 JSON 后退出，**从未真正监听端口**。

补充实测：`50_开发_dev/apps/api/src/modules/model/family-assessment-model.provider.ts` 所在的目录名叫 `modules/model`，但它根本不是一个 Nest module，只是一个裸 provider——连"NestJS 侧结构一致"这个假设也不成立。

四条血脉并存的代价不是"技术栈多样"，而是**没有任何一个问题有唯一答案**：某个业务规则的真相在 TS 还是 Python？某个能力已实现还是只有目录？源仓库自己回答不了。

## Decision

AiFamily 的正式后端是 **Python / FastAPI / SQLAlchemy / PostgreSQL，且只有一个**。

- 不保留 NestJS 作为长期第二后端。`apps/api` 的价值被重新定义为**行为规格与 TEST_ORACLE 来源**：它的 e2e/integration spec 是 Python 实现的验收口径，其 TS 运行时代码不迁入。
- `apps/ai-runtime`、`apps/fes-api` 处置为 `ARCHIVE` / `NOT_MIGRATING`（见 `governance/MIGRATION_MANIFEST.yaml`）。
- **前端不在本决定的约束范围内**：Web / Mobile 继续使用 TypeScript / React / React Native。`apps/mobile` 已按 project-owner override 全量迁入（34 个 UI 已成熟）。"后端单轨"不等于"全栈单语言"。
- TS→Python 的转换是**重写（REIMPLEMENT）而非搬运（MIGRATE）**：`family_core` / `platform_authorization_policy` 等条目的 disposition 均为 REIMPLEMENT，业务规则重译，代码不翻译。

本决定写入 `governance/REPOSITORY_CONSTITUTION.md` **R1 — 唯一后端真相**。

## Alternatives Considered

### A. 保留 NestJS 作为主后端，放弃 Python 领域层
**支持理由（不弱）**：`apps/api` 是四条血脉里唯一真实运行、真实连库、测试覆盖完整的一条。5 个 Python 域连进程入口都没有。纯按"哪个是可工作的软件"判断，应该保 NestJS。

**否决理由**：
- 平台的核心方向是 AI 原生（见 ADR-0005）。AI Runtime 的生态重心（模型 SDK、向量、评估、agent 框架、科学计算栈）在 Python；用 TS 做主干意味着 AI 主路径长期跨语言跨进程，而 AI 恰恰是核心域的主路径而非旁路。
- `apps/api` 的"真实"里混着必须清理的东西：`dev-platform-surfaces.service.ts` 与 `dev-core-growth.service.ts` 自述 `data_source: 'SYNTHETIC_DEV_ONLY'`、`model_gateway: 'NOOP_NOT_INVOKED'`，却经 `family.controller.ts:280,295,313,326` 挂在生产路由 `/:familyId/dev/*` 上被 9+ 个真实 Mobile 屏幕消费。保留 NestJS 会连这套合成数据一起继承。
- `orchestration/llm-gateway/family-llm-gateway.service.ts:58-63` 在业务服务内部裸 `new OpenAICompatibleAiGateway`，绕过 DI、绕过 fail-closed 工厂、绕过审计包装——违反 `packages/ai-gateway/src/index.ts:544-560` 自己声明的 `AI_GATEWAY_POLICY.business_module_direct_provider_call: 'forbidden'`。要在保留的代码库里重建纪律，成本不低于重写。

### B. 双轨并行（NestJS 守事实与权限，Python 承载 AI）
**支持理由**：各用其长，NestJS 侧不必推倒。

**否决理由**：这正是源仓库当前的形态，而它已经失败了——不是因为技术不可行，而是因为**同一个业务概念在两侧各有一份定义，且没有机制保证两份一致**。双轨必然要求跨语言契约的机器化同步，而源仓库已经证明它守不住机器化同步：`governance/FPAI_PROVIDER_REGISTRY.yaml` 声明 3 个供应商，其生成物 `packages/principal-runtime/src/provider-registry.generated.ts` 只有 2 个（缺 `deepseek-chat`），生成器 `--check` 在基线 commit 上就是 exit 1。**在一个单仓库内的 YAML→TS 生成都漂了，跨两个后端的领域模型同步没有理由更成功。**

### C. Python-only（采纳）
代价明确且已接受：`apps/api` 2293 行的 family 服务与 5519 行的 orchestration 必须重写，且重写期间没有可用后端。这个代价被接受，理由见 Consequences。

## Consequences

### 正面
- "业务真相在哪"有唯一答案，可由 `governance/DOMAIN_REGISTRY.yaml` 一行一能力机械登记（R2）。
- AI 主干与业务事实同语言同进程边界内协作，无跨语言契约层。
- 迁移过程强制逐条重新判断"这段代码到底该不该存在"，而不是把源仓库的债务整包继承（这也是 ADR-0003 的前提）。

### 负面 / 代价
- **重写量大**：`family.service.ts` 2293 行 + `orchestration` 5519 行 + `principal` 2337 行 + `auth` 1546 行，全部必须在 Python 重建，且不能翻译式重写（否则连结构性问题一起搬）。
- **过渡期无可用后端**：AiFamily 当前 `backend/apps/family_api` 只有 `/health` `/ready`，零业务路由。34 个 Mobile 屏幕中依赖 `/dev/*` 与 `/auth/*` 的部分在 Python 侧补齐前会白屏——这不是可以推迟发现的问题，`MIGRATION_MANIFEST.yaml` → `frontend_mobile.blocking_action` 已显式记录。
- 丢掉 NestJS 侧成熟的 e2e 基础设施，Python 侧的集成测试栈要从零建。

### 需要接受的风险
- 重写引入源实现里不存在的新缺陷。缓释手段是把 TS 的 e2e/spec 当验收口径而非参考（`MIGRATION_MANIFEST.yaml` 中 6 条 `disposition: TEST_ORACLE` 条目），但**口径的翻译本身也可能出错**，这个风险无法通过流程消除。
- `apps/mobile` 已迁入而后端未就绪，形成"前端等后端"的单向阻塞。若 Python 后端进度不及预期，Mobile 会长期停在不可运行状态。

## Enforcement

**当前部分执行，且这是已知治理债务。**

- `governance/REPOSITORY_CONSTITUTION.md` 第 2 节的执行状态表把 R1 标为"部分：Wave 1 起补充（当前无运行时可检验）"。
- 间接护栏：`tests/architecture/test_migration_manifest.py`（R3）保证 `backend/` 下任何含文件的目录都必须能追溯到 manifest 的 `target`；`tests/architecture/test_no_direct_provider_calls.py`（R7）覆盖模型调用纪律。
- **尚无测试禁止有人在仓库里新建一个 TS 后端**（例如 `apps/api/`）。R1 的"不得出现第二个业务后端"目前只是意图。补齐路径：加一个架构测试，断言仓库根下除 `frontend/` 外不存在含 `package.json` + 服务端框架依赖的目录。这条应在下一个治理 PR 中落地。

## References

- `governance/REPOSITORY_CONSTITUTION.md` R1（含伤疤段）、R7、R10、R14
- `governance/MIGRATION_MANIFEST.yaml` → `ai_runtime_app`、`fes_api`、`family_core`、`orchestration_core`、`principal_core`、`frontend_mobile`
- `docs/11_delivery/migration/01_REPOSITORY_INVENTORY.md`、`03_TS_TO_PYTHON_CAPABILITY_MATRIX.md`
- `docs/00_system/CURRENT_TECHNOLOGY_BASELINE.md`
- ADR-0003（精选式迁移）、ADR-0005（AI 原生定位）
