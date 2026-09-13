# ADR-0170: Runtime 收敛裁决——Accept ADR-0025+ADR-0167，冻结 Router/Executor/Gateway 三层模式

- **Status**: Accepted
- **Date**: 2026-09-13
- **Deciders**: project-owner（本次会话经 `AskUserQuestion` 显式确认批准，
  对应 `ADR-0167` 正文自述"需要 codex/总控确认后才能 Accepted"的前提条件；
  Agent 本身不自行拍板架构级决定）
- **Supersedes**: null（正式 Accept 两份此前停留在 `Proposed` 的 ADR，不推翻其
  内容）
- **Superseded By**: null

## Context

本次会话核实（真实读代码，非猜测）：AiFamily 存在三条都已接入真实 HTTP 路由、
都执行"调用模型产出 Draft"的 Runtime 路径——`backend/intelligence/agent_runtime/`
（`AgentRuntime`/`DurableAgentRuntime`）、`backend/intelligence/agi_vertical_*`
（`VerticalFamilyGrowthRuntime`，Child Growth Vertical Pack 的当前实现）、
`backend/intelligence/principal/`（`PrincipalRuntime`/`PrincipalCapabilityRouter`）。
`docs/00_system/CURRENT_AI_MAP.md`（2026-09-10）已经明确记录"不要默认假设三者
中任何一个是'唯一正确'入口，直到 ADR-0167 解决"，而 `ADR-0167` 自身第124行写明
"status继续Proposed——这是架构级决策，需要codex/总控确认后才能Accepted，不由
本次会话单方面拍板"。同时 `ADR-0025`（"Principal 是统一 AI 控制面"，
2026-08-30）也停留在 `status: proposed`，从未被批准。**两份该管这件事的 ADR
都没被 Accept，是收敛没有发生的直接原因**，不是"代码还没写"。

本次会话进一步逐行核实了两个真实调用点，结论出乎意料地清晰——**代码里已经
存在一个正确的模式，只是没被写成决定**：

1. **`backend/apps/family_api/growth_plan_ai_wiring.py`**（UI-05 GrowthPlan
   AI Draft Adapter）：`GrowthPlanAiDraftAdapter.generate()` 在
   构造 `AgentTask` 之前，先调用 `self._principal_router.resolve(...)`
   （第339-362行）拿到路由决定并**断言**其结果（`route.agent_id`/
   `route.output_type`/`route.human_gate`，第363-368行），**然后才**调用
   `runtime.execute(task, authorization, ...)`（第396-401行，`runtime` 是
   `agent_runtime.AgentRuntime`/`DurableAgentRuntime` 的具体实现）。也就是
   **Principal 负责治理路由决定，`agent_runtime` 负责实际执行**——两者不是
   互斥的平行入口，是"路由层→执行层"的正确分工。此前 Explore 阶段的报告
   把这误读成"两套契约并存、运行时到底走哪条路径不清晰"，逐行核实后证明
   是误读：这个文件的组合方式本身没有 bug。

2. **`backend/intelligence/agi_vertical_runtime.py`**（`VerticalFamilyGrowthRuntime`，
   Child Growth Vertical Pack 当前唯一的 AI 执行实现）：`__init__`
   （第257-268行）直接接收一个 `gateway: ModelGatewayPort`，`run()`
   方法内部两处（第480行、第684行）直接调用
   `self._gateway.generate_structured(...)`。**全文件零处 import 或调用
   `backend.intelligence.principal` 的任何契约**（`grep principal` 命中0处业务
   代码，只在文件头注释提到"existing ModelGateway port"）。这是与
   `growth_plan_ai_wiring.py` 模式**真实存在的不一致**：Child Growth
   Vertical Pack 的核心 AI 执行路径绕过了 Principal Capability Router，
   直接调用 Model Gateway。

这正是本次会话计划要核实的"三个真实问题"之一，现在有了具体到文件、行号的
证据，而不是"存在架构分歧"这种抽象判断。

## Decision

1. **正式 Accept `ADR-0025`**（Principal 是统一 AI 控制面）与 **`ADR-0167`**
   （Family AGI Runtime 分层坐标）——两者状态由 `Proposed` 改为 `Accepted`
   （本 ADR 是它们的批准记录，不改动其正文，按 README 写作纪律"不得原地重写
   已 Accepted 的 Decision"，批准动作走独立 ADR 而不是编辑原文件的 status
   字段本身也算"原地重写"）。

   > 澄清：严格来说，"接受一份 ADR"通常是编辑其 front matter 的 status 字段，
   > 不属于"重写 Decision"。本 ADR 同时更新 `ADR-0025`/`ADR-0167` 的
   > front matter `status` 字段为 `Accepted`（并记录 `accepted-by: ADR-0170`），
   > Decision 正文本身保持不变——这不是 README 禁止的"原地重写 Decision"，
   > 是所有 ADR 流程都需要的状态推进。

2. **冻结 Router / Executor / Gateway 三层模式为唯一 canonical 组合方式**，
   以 `growth_plan_ai_wiring.py` 的现有实现为参照实现（不是新设计，是把已经
   工作的代码模式升级为架构决定）：

   ```text
   Principal Capability Router   （治理路由：这个请求该用哪个 capability/
                                    agent_id、输出类型、Human Gate 要求）
            ↓ 路由决定（不执行模型调用）
   Agent/Tool Runtime            （agent_runtime.AgentRuntime/
   （执行层）                       DurableAgentRuntime：真正执行、鉴权、
                                    幂等、重放、持久化）
            ↓
   Model Gateway                 （唯一供应商边界，ADR-0025 已冻结）
   ```

   任何新增或既有的 AI 执行路径，**必须先经过 Principal Capability Router
   拿到路由决定**，才能调用 Agent/Tool Runtime 执行、最终触达 Model Gateway。
   跳过 Principal 直连 Model Gateway（无论是否经过 `agent_runtime`）视为违反
   `ADR-0025`。

3. **明确记录 `agi_vertical_runtime.py` 当前违反上述模式**（第257-268、480、
   684行，证据见 Context 段），**但本次不重写它**——按用户显式确认的方案：
   - 这是 Child Growth Vertical Pack（当前唯一真实验证中的业务纵切）的核心
     执行路径，改动影响面覆盖 UI-03/04（assessment→hypothesis）等已经在
     `frontend/web/e2e/family-growth-golden-path.spec.ts` 里被验证通过的
     真实链路，仓促重写有直接打断"已经跑通的一条闭环"的风险。
   - 按 `ADR-0169`"战略边界宽、产品边界窄"与用户材料第七/二十三节的纪律，
     本阶段目标是"证明 Child Growth 闭环真正工作"，不是"立刻让所有代码在
     架构上完美"——**先保住已验证的绿，再收敛**，收敛本身排入下一阶段独立
     任务（见 Enforcement 段）。

4. **`GrowthPlanAgentHandle` 协议（`growth_plan_ai_wiring.py:135-144`）确认
   为 Router→Executor 组合的正确参照实现**，后续任何新 Vertical Pack 接入
   AI 能力时，应复用这个协议形状（`resolve` 拿路由、`execute` 走执行），
   不应重新发明。

## Alternatives Considered

**A. 现在就重写 `agi_vertical_runtime.py`，让它接入 Principal Router。**
支持理由：一次性消除不一致，避免"文档说收敛了、代码还没收敛"的过渡态。
否决理由：`agi_vertical_runtime.py` 是当前唯一在生产验证路径（web E2E golden
path）上被真实跑通的 AI 执行代码，本次会话的更高优先级是"验证 Child Growth
闭环今天是否真的工作"（步骤3），在验证之前动它的核心依赖注入结构，一旦验证
失败无法区分是"本来就红"还是"这次改动引入的红"——违反用户材料强调的
"先证明闭环再扩张"纪律，且与本次会话的证据链完整性要求冲突。用户本次
`AskUserQuestion` 已显式选择这一否决，不选"批准但要求本次就整改"选项。

**B. 不写 ADR，只在 `CURRENT_AI_MAP.md` 里补一段"发现的不一致"记录。**
支持理由：改动最小。
否决理由：`ADR-0025`/`ADR-0167` 的 `Proposed` 状态本身就是本次要解决的问题
根源——不正式 Accept，任何后续人都可以合理地说"这还没定，我可以另建第四条
路径"，收敛永远无法真正发生。README"何时必须写 ADR"第2条（改变技术栈/部署
单元划分）与第7条（推翻或修改既有 ADR 的状态）都要求走 ADR，不能只更新
状态文档。

**C. 把 `agent_runtime` 判定为多余，长期只保留 Principal 一条路径（把执行逻辑
并入 Principal 内部）。**
支持理由：更简单，减少一个模块。
否决理由：`ADR-0025` 明确否决"把 Principal 做成万能超级 Agent"（其"被否决的
方案"第2条），Principal 的职责边界是路由与治理，不是执行——`agent_runtime`
承担的鉴权租约、幂等重放、durable 持久化职责如果并入 Principal，会让 Principal
重新变成一个臃肿的执行体，重犯 ADR-0025 已经否决过的错误。

## Consequences

### 正面
- 结束了 `ADR-0025`/`ADR-0167` 长期停留在 `Proposed` 的悬而未决状态，给后续
  任何"这个 AI 能力该怎么接"的问题一个有 Accepted 依据可以引用的答案。
- 用已经工作的代码（`growth_plan_ai_wiring.py`）作参照实现，而不是凭空设计
  新模式，降低了"决定和代码两条平行线"的风险。
- 精确定位了唯一一处真实违规（`agi_vertical_runtime.py`），给了下一阶段
  明确、有文件行号的整改目标，而不是笼统的"三线待收敛"。

### 负面 / 代价
- `agi_vertical_runtime.py` 的整改被推迟到下一阶段，在此之前它作为一个"已知
  违反 ADR-0025 但暂缓整改"的例外存在——需要在 `governance/DOMAIN_REGISTRY.yaml`
  或等价登记处记录这个例外，避免它被误读为"两种模式都行"。
- `ADR-0025` 第78行提到的"外部模型供应商合规准入完成前生产请求需显式降级"，
  本 ADR 未重新核实这条前提当前是否满足——不在本 ADR 范围内。

### 需要接受的风险
- 在整改 `agi_vertical_runtime.py` 之前，Child Growth Vertical Pack 的 AI
  草案产出没有经过 Principal 的 Human Gate/output_type 治理断言（对比
  `growth_plan_ai_wiring.py:363-368` 那种显式 route 断言），依赖它自身内部
  的 boundary 检查（如有）来防止越权输出——这是一个已知、被记录、非本次
  修复的风险敞口，不是被隐藏的风险。

## Enforcement

- **本 ADR 已执行**：更新 `ADR-0025`/`ADR-0167` front matter `status` 字段为
  `Accepted`（见对应文件本次改动）。
- 后续执行路径（不在本 ADR 授权范围内立即做，排入下一阶段）：
  1. 新增架构测试 `tests/architecture/test_ai_runtime_convergence.py`：断言
     任何调用 `ModelGatewayPort.generate_structured` 的代码路径，其调用栈上
     必须能追溯到一次 `PrincipalCapabilityRouter.resolve()` 调用——用于把
     本 ADR 第2条从判据变成可执行门槛，同时会立刻标红
     `agi_vertical_runtime.py` 的两处直连（第480、684行），是下一阶段的
     验收标准。
  2. 整改 `agi_vertical_runtime.py`，让它在 `run()` 内部先经
     `PrincipalCapabilityRouter` 拿路由决定——需要先确认整改后
     `frontend/web/e2e/family-growth-golden-path.spec.ts` 仍然绿，作为
     "闭环没被打断"的验收证据。
  3. 在 `governance/DOMAIN_REGISTRY.yaml`（或新建专门的 AI 运行时登记表）
     登记 `agent_runtime`/`principal`/`agi_vertical_*` 三者的职责边界，
     把本 ADR 第2条的图从文档变成可查询的登记项。

## References

- `governance/ADR/ADR-0025-principal-as-governed-ai-control-plane.md`（本次
  Accept）
- `governance/ADR/ADR-0167-family-agi-runtime-architecture.md`（本次 Accept）
- `docs/00_system/CURRENT_AI_MAP.md`（记录三线并存现状的既有文档）
- `backend/apps/family_api/growth_plan_ai_wiring.py:339-401`（Router→Executor
  参照实现的具体证据）
- `backend/intelligence/agi_vertical_runtime.py:257-268,480,684`（已识别的
  唯一真实违规点）
- `frontend/web/e2e/family-growth-golden-path.spec.ts`（下一阶段整改
  `agi_vertical_runtime.py` 时的回归验收基准）
- `docs/00_system/AIFAMILY_STRATEGIC_CONSTITUTION_V1.md` §15（AGI-native
  但不是超级 Agent 的技术纪律，与本 ADR 否决的替代方案C同一纪律）
