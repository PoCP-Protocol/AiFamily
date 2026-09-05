# AiFamily 仓库宪章 (Repository Constitution)

- **版本**: V1.0
- **状态**: ACTIVE — 本文件是 AiFamily 仓库的最高工程约束
- **生效**: 2026-08-29 (AIFAMILY-000)
- **迁移源基线**: `PoCP-Protocol/family-ai` @ `1ff168123d147f4d6a6eaaa677bc2f80986233d9`

---

## 0. 本宪章为何存在

AiFamily 不是 `family-ai` 的重构，是**重建**。`family-ai` 降格为历史资产库、迁移源、业务证据库与参考实现库。

本宪章的每一条不是抽象原则，而是从 AIFAMILY-000 对 `family-ai` 的资产审计中**实测到的具体故障**反向推出的护栏。每条规则都附带它要防止的真实事故（含源文件路径），以便后来者知道这条规则不是洁癖，是伤疤。

**审计结论摘要**：源仓库 `50_开发_dev` 下 2060 个受控文件中，存在 (a) 完全没有 Python 运行时入口却已有 5 个 Python 领域目录、(b) 自我标注 `SYNTHETIC_DEV_ONLY` 却挂在生产路由上的服务、(c) 零测试却 2627 行的领域、(d) 治理 YAML 与生成代码的实时漂移、(e) 违反自身声明策略的直连模型供应商调用、(f) 源码已被删除只剩 `.pyc` 的应用、(g) 四组重号的数据库迁移。以上全部有据可查，见 `reports/migration/`。

---

## 1. 十四条规则

### R1 — 唯一后端真相 (Single Backend Truth)
AiFamily 的正式后端是 **Python / FastAPI / SQLAlchemy / PostgreSQL**，且只有一个。

不得出现第二个业务后端。NestJS 不作为长期第二后端保留。前端（Web / Mobile）**不要求**迁为 Python，可继续使用 TypeScript / React / React Native。

> **伤疤**：源仓库同时存在 NestJS 生产 API (`50_开发_dev/apps/api`)、5 个 Python 领域 (`50_开发_dev/backend/domains/*`)、一个源码已删只剩 `.pyc` 的 Python 应用 (`50_开发_dev/apps/ai-runtime`)、以及一个声明了 NestJS 依赖却根本没有 `@Module`/`NestFactory`、运行即打印一行 JSON 后退出的"应用" (`50_开发_dev/apps/fes-api/src/main.ts`)。四条后端血脉并存，没有一条是权威的。

### R2 — 唯一领域真相 (Single Domain Truth)
一个业务能力只允许有一个正式实现位置。禁止 `family` / `family_core` / `family_domain_v2` / `family_new` 并存。

正式位置由 `governance/DOMAIN_REGISTRY.yaml` 登记，一个能力一行，重复即违宪。架构测试强制执行。

### R3 — 无 Manifest 不得入仓 (No Legacy Import Without Manifest)
任何来自 `family-ai` 的文件、模块、契约、数据，默认状态为 `NOT_APPROVED`。

只有在 `governance/MIGRATION_MANIFEST.yaml` 中登记、且 disposition 被批准为 `MIGRATE` 或 `REIMPLEMENT` 的能力，才允许在 AiFamily 中出现对应实现。架构测试强制执行。

**禁止整体复制**：不得 `cp -R family-ai AiFamily`，不得"先全部迁入再删除"。

### R4 — 无测试不得称能力 (No Production Capability Without Tests)
任何声明为可用的业务能力，必须有 Python 验收测试，且测试须能在 CI 中真实运行。

代码行数不是成熟度。文档注释声明的测试不算测试。

> **伤疤**：`50_开发_dev/backend/domains/membership` 有 2627 行、含真实 SQLAlchemy 仓储与不变量策略层，是源仓库最大的 Python 领域；其 `infrastructure/sqlalchemy_repository.py:8-9` 的 docstring 明确写着"Tests run this same class against an in-memory SQLite engine (`tests/conftest.py`)"——而该 `tests/` 目录在磁盘上根本不存在。五个 Python 领域里只有 `product_intelligence` 有测试。

### R5 — 合成数据不得伪装为业务能力 (No Synthetic Data As Business Capability)
自我标注为合成/演示/夹具的产物，不得作为业务代码迁入，也不得挂载在生产路由上。

本条只约束**数据来源与生产暴露边界**，不允许被解释为“开发/测试环境可以少做功能”。开发、测试、生产必须使用同一套功能、流程、规则和路由；开发/测试只能把真实数据与外部副作用替换为隔离的合成数据、sandbox 或 fake adapter。详见 `docs/10_engineering/ENVIRONMENT_PARITY.md` 与 ADR-0020。

演示数据、种子脚本、UI 夹具属于测试资产，必须在路径与命名上与业务代码物理隔离。

> **伤疤**：`50_开发_dev/apps/api/src/modules/family/dev-platform-surfaces.service.ts:26-33` 与 `dev-core-growth.service.ts:43-60` 在自己的返回体里写明 `data_source: 'SYNTHETIC_DEV_ONLY'`、`model_gateway: 'NOOP_NOT_INVOKED'`，内容是 24 张硬编码 UI 卡片和一本中文文案字典，却通过 `family.controller.ts:280,295,313,326` 挂在生产 HTTP 路由 `/:familyId/dev/*` 上对外提供。前端因此渲染的是假数据。

### R6 — 无审计不得改状态 (No State Mutation Without Audit)
任何对权威业务状态的写入，必须产生 `AuditEvent`，至少记录 actor / tenant / action / resource / before / after / reason / correlation_id / timestamp。

### R7 — 领域不得直连模型供应商 (No Direct Model Provider Calls)
任何领域模块、应用服务、工作流，不得直接调用 OpenAI / Anthropic / DeepSeek / Gemini 等供应商的 SDK 或 HTTP 端点，也不得直接实例化会发起外部请求的网关类。

一律经由 `backend/intelligence/model_gateway`。凭据只由 Model Gateway 读取。架构测试强制执行。

> **伤疤**：源仓库自己在 `50_开发_dev/packages/ai-gateway/src/index.ts:544-560` 声明了 `AI_GATEWAY_POLICY = { business_module_direct_provider_call: 'forbidden' }`；而 `50_开发_dev/apps/api/src/modules/orchestration/llm-gateway/family-llm-gateway.service.ts:58-63` 在业务服务方法内部直接 `new OpenAICompatibleAiGateway({...})` 并调用，绕过 DI、绕过 fail-closed 工厂、绕过 `AttemptRecordingGateway` 审计。**策略写成了常量，但没有任何东西执行它**。这就是 R14 存在的原因。

### R8 — 高影响行为必须过闸 (No High Impact Action Without Policy)
以下行为必须经过对应的 Human Gate，且闸门决策必须落库可审计：类诊断输出、家庭计划变更、教师推荐、服务购买、对外沟通、会员升级、涉未成年人的敏感动作。

### R9 — AI 输出不得自动成为事实 (AI Output Never Becomes Fact)
`Fact` ≠ `Perspective` ≠ `Recommendation` ≠ `Action`。AI 推断只能生成 `Perspective` / `Recommendation`，永不得直接写入家庭权威事实。

从 `family-ai` 的 FELS 参考实现中继承以下**否定语义**为一等约束（原文见 `50_开发_dev/legacy-system/architecture/FELS_LM1_SEMANTIC_MAPPING_V1.md:19,44-53`）：

| 旧世界对象 | 迁移规则 | 红线 |
|---|---|---|
| `legacy_profile.family_score` | **RETIRE** | 永不入 Family / 非 GrowthState (M036) |
| `legacy_profile.ranking` | **RETIRE** | 永不入 Family / 无家庭排行 (M035) |
| `legacy_checkin` | TRANSFORM | 打卡 ≠ GrowthActionCompletionFact ≠ Outcome (M014) |
| `legacy_tag.*` | LEGACY_ANNOTATION | 非永久人格标签 / 非诊断 |
| `legacy_ai_report.ai_conclusion` | HISTORICAL_AI_HYPOTHESIS | 非 Fact / 非诊断 / 非疗效承诺 |
| `legacy_assessment_score.score` | HISTORICAL_EVIDENCE | 非 GrowthState |
| `legacy_advisor_note.note_text` | PERSPECTIVE | 非 Fact |
| `legacy_alert.risk_score` | SAFETY_SIGNAL_SOURCE | 非阈值 / 非自动动作；高风险须 Human Gate |

**AiFamily 不计算、不存储、不暴露家庭总分与家庭排行。**

### R10 — 唯一 AI Runtime (Single AI Runtime)
所有 AI 能力收敛于 `backend/intelligence/`。禁止出现 `family_ai_service` / `growth_llm_service` / `assessment_gpt_service` / `teacher_ai_service` 各自调模型。

Model Gateway / Context Engine / Agent Runtime / Tool Runtime / Prompt Registry / Safety / Human Gate / Evaluation / Trace / Cost / Audit 各一份。

> **伤疤**：源仓库只有一份网关**实现**（`packages/ai-gateway`），但有三套互不相同的**接入模式**：`principal.module.ts:19-34`（DI 工厂 + fail-closed + AttemptRecording，最严）、`family/family-model-gateway.provider.ts:17-22`（DI + 双 env 门控）、`orchestration/llm-gateway/*`（裸 new，见 R7）。重复的不是实现，是纪律。

### R11 — 单一依赖管理 (Single Dependency Toolchain)
Python 依赖只用 **uv** + `pyproject.toml`。禁止 pip/poetry/pipenv/requirements.txt 并存。依赖必须可从版本控制完整复现。

禁止不可移植的环境产物入仓（绝对路径 `.pth`、已构建 venv、`.pyc`）。

> **伤疤**：源仓库全域**零个** `pyproject.toml`/`requirements*.txt`/`lock` 文件，却有两个 venv 躺在磁盘上，依赖集只能靠翻 `site-packages` 的 `.dist-info` 反推；`50_开发_dev/apps/ai-runtime/.venv/Lib/site-packages/_editable_impl_family_ai_runtime.pth` 里硬编码了绝对路径 `D:\family-ai\50_开发_dev\apps\ai-runtime\src`，换台机器即失效。同时 `apps/ai-runtime` 的 `.py` 源码已从磁盘消失，只剩 `.pyc`——**能力的唯一证据是编译产物**。

### R12 — 无隐式路径耦合 (No Implicit Layout Coupling)
禁止依赖进程 cwd、`sys.path` 注入、或目录深度来解析导入。所有内部包必须以真实可安装包的方式解析。

禁止在代码中硬编码仓库物理路径或目录名。

> **伤疤**：`50_开发_dev/backend/domains/*/...` 全部用 `from packages.contracts.evidence import Provenance` 这类裸顶层导入（如 `market_intelligence/domain/entities.py:22`、`membership/application/commands.py:17`），而 `packages/contracts` 既未安装、也无 `conftest.py`/`pyproject.toml` 声明 rootdir——只有把 cwd 钉在 `50_开发_dev/backend` 才能跑。更甚者 `product_strategy/domain/entities.py:17` 的注释直接在讨论字符串 `50_开发_dev/backend/` 这个物理布局。

### R13 — 历史文档不得充当当前真相 (No Historical Document As Current Truth)
`docs/00_foundation/CURRENT_*.md` 是唯一的当前真相。历史 Sprint、废弃 RFC、过期架构方案、旧版本文档一律进 `docs/archive/`，且必须标注被取代者。

`CURRENT` 与 `ARCHIVE` 之间不得存在歧义。同一主题不得有两份都自称基线的文档。

### R14 — 架构测试强制 (Architecture Tests Are Mandatory)
上述规则中可机械检验的部分，必须由 `tests/architecture/` 下的测试执行，且必须在 CI 中运行。

**写成常量或文档的策略等于没有策略。** R7 的伤疤是直接证据：源仓库把"禁止业务模块直连供应商"写成了一个导出常量，然后违反了它。凡新增一条可检验规则，同一 PR 必须新增对应架构测试。

> **伤疤（治理漂移）**：`50_开发_dev/governance/FPAI_PROVIDER_REGISTRY.yaml` 声明 3 个供应商，而由它生成的运行时快照 `packages/principal-runtime/src/provider-registry.generated.ts` 只有 2 个（缺 `deepseek-chat`）。生成器 `tools/build_provider_policy_snapshot.py --check` 在基线 commit 上就是 exit 1 —— **一个正在失败的不变量被提交进了主线**，因为 CI 没有跑它。源仓库全域只有一个真正生效的 CI workflow（`.github/workflows/family-35ui-alignment.yml`），且被 path filter 限定在 mobile/api/contracts 三处。

---

## 2. 强制执行状态

| 规则 | 可机械检验 | AIFAMILY-000 执行方式 |
|---|---|---|
| R2 唯一领域真相 | 是 | `tests/architecture/test_domain_registry.py` |
| R3 无 Manifest 不得入仓 | 是 | `tests/architecture/test_migration_manifest.py` |
| R7 领域不直连供应商 | 是 | `tests/architecture/test_no_direct_provider_calls.py` |
| R11 单一依赖管理 | 是 | `tests/architecture/test_single_toolchain.py` |
| R12 无隐式路径耦合 | 是 | `tests/architecture/test_no_layout_coupling.py` |
| R13 历史文档不充当真相 | 部分 | `tests/architecture/test_docs_truth_boundary.py` |
| R1 唯一后端真相 | 部分 | Wave 1 起补充（当前无运行时可检验） |
| R4 无测试不得称能力 | 部分 | Wave 1 起：DOMAIN_REGISTRY 中 `status: ACTIVE` 必须有测试路径 |
| R5 合成数据隔离 | 是 | Wave 1 起：路由层禁止 `SYNTHETIC` 标记产物 |
| R6 / R8 / R9 / R10 | 是 | Wave 1–5 逐步接入，随能力落地同 PR 补测试 |

**未被架构测试覆盖的规则，只是意图，不是护栏。** 上表右列必须随每个 Wave 收敛，任何一行长期停留在"部分"即为治理债务。

---

## 3. 修宪程序

本宪章的修改必须：
1. 通过 `governance/ADR/` 下的一份 ADR 提出，说明被推翻的是哪条规则、依据什么新证据；
2. 若削弱某条规则，必须说明对应的伤疤为何不再适用；
3. 同一 PR 更新第 2 节的执行状态表。

禁止在实现 PR 中顺手修改本文件。
