# ADR-0152: 需求闭环补齐 N4/N6/N7/N8、FGCN 分派授权闸门、FGCN durable 持久化、AI Coach（事后补记）

- **Status**: Accepted（implemented and verified 2026-09-02/03；含真实 PostgreSQL 与真实
  DeepSeek 模型调用验证）
- **Date**: 2026-09-03（补记；实际实现分布在 2026-09-02 晚间至 2026-09-03）
- **Deciders**: project-owner（沿用 ADR-0150 已记录的"跳过逐域事前 ADR、事后补记"授权，
  本次为同一授权范围内的连续增量，不重复请示）
- **Supersedes**: null
- **Superseded By**: null

## Context

ADR-0149/ADR-0150 打通了 family_need 的 N0→N3 与 N5 的最小闭环（信号→澄清→分级→方案→
下单/预约→交付完成）。project-owner 随后连续给出四个方向指令，每个都在同一会话内完成并
验证，本 ADR 一次性补记这四个决策：

1. "完善 N4/N8 剩余环节"
2. "接 FGCN 真人教师分派授权"
3. "把 FGCN 从内存接到真实 PostgreSQL"
4. "接 AI Coach（Khanmigo 式引导式对话）"，并在过程中明确纠正："我们要的是真的生成式AI，
   不是手写的AI"——这条纠正是本 ADR 里 AI Coach 部分设计约束的直接来源。

## Decision 1 —— N4（资源组织）落成一等实体，不是隐藏在函数参数里的决策

新增 `AssignmentPlan`（`backend/domains/family_need/domain/entities.py`）：家长确认方案后，
在调用 `need_fulfillment_flow.fulfil_confirmed_draft` 之前，先由
`FamilyNeedApplicationService.create_assignment_plan` 落一条记录，`authorization_basis`
显式写明 `family_confirmed_draft:{draft_id}`——用文本承诺"这是家长自己批准的"，不是 AI
自己决定分配给谁。这只是决策记录层，不做真正的资源容量调度/并发争用处理（已有的
`SupplyReferencePort.check_resource_capacity` 继续承担容量判断，未重做）。

## Decision 2 —— N6/N7 二合一：家庭确认结果，AI/SYSTEM 身份被显式拒绝

新增 `FamilyConfirmedOutcome` + `FamilyOutcomeDecision`（HELPED/PARTIALLY_HELPED/
DID_NOT_HELP）。核心规则 `assert_family_outcome_confirmer` 在应用层最前面校验调用者
`actor_type`，AI 或 SYSTEM 身份直接 403——这是 R9"AI 不能自判结果"在代码里的真实落地，
不是文档描述。端点 `POST /outcomes/confirm` 的响应对负面结果（DID_NOT_HELP）如实展示，
不隐藏，只是附带一个诚实的 `recommended_next_action` 标记。

## Decision 3 —— N8：回流复用已有的信号捕获用例，不新建平行管道

DID_NOT_HELP 时，`confirm_family_outcome` 路由直接调用 `FamilyNeedApplicationService.
capture_signal`（与全新家庭请求完全相同的用例），带 `causation_id=原need_id`。**决策
依据**：N8 的本质是"这仍然是一个需要被理解的家庭需求"，不是一种新的数据类型——给它开一条
独立的"回流"代码路径，会制造出两套需求捕获逻辑长期漂移的风险。新信号的可见范围与原信号
完全一致（同一 tenant/family），不涉及跨家庭知识库写入。

## Decision 4 —— FGCN 分派授权闸门：只在有真实自助失败证据时触发，不强制所有预约

`backend/apps/family_api/orchestration/fgcn_assignment_flow.py`：SERVICE 组件预约前，
若能取到该 need 的 `FamilyConfirmedOutcome(DID_NOT_HELP)`，则先走 FGCN 的 S-01 场景
（唯一已注册场景，中文渲染 `render_s01_scenario("zh")`，其文案"家庭已反复尝试自助，但
无法平稳解决问题"与本场景天然契合）：开 case → 建 task → AI（ModelGateway + FakeProvider/
真实 provider）生成候选教师建议 → 家长在 Human Gate 上 `ACCEPT` → `execute_named_action`
产出真实 `TaskAssignment`。**没有该证据的普通预约不受影响**，直接走原有路径——这是刻意的
范围收紧：FGCN 是"升级"场景的授权强化，不是所有真人服务预约的强制前置关卡，避免把一个
为高风险/复发场景设计的治理机制,无差别套用到日常预约上制造摩擦。

**为什么不用 application.py 的 durable 版本作为唯一实现**：dev/测试环境延续本仓库一贯的
"dev 用内存/fake，生产用真实持久化"分层（`FGCNEngine` 同步内存版本用于 dev 分支），Decision
5 单独处理生产路径。

## Decision 5 —— FGCN 分派记录接入真实 PostgreSQL（Docker 验证）

新增 `authorize_real_teacher_assignment_durable`，使用已存在但此前未被family_need使用的
`application.py` 异步 durable 函数（`open_service_case`/`execute_task_assignment_named_action`）
+ `SqlAlchemyFGCNRepository`，真实写入 `service_cases`/`service_tasks`/`task_assignments`
三张表。**验证方式**：一个会话完成完整授权流程后关闭连接，用完全独立的新连接重新查询，
证明数据确实落在数据库，不是同进程内存的幻觉——在本机 Docker（`aifamily-dev-postgres`，
disposable schema/database 模式，与本仓库其他真实 PostgreSQL 测试一致）上验证通过。

**已知简化**：case_id/task_id 从内存版的字符串拼接（`"fgcn-case:xxx"`，PostgreSQL UUID 列
不接受）改为按 intent_ref 派生的真实 UUID5——这是修复而非新设计。provider 准入
（教师资质是否 admitted）本次未建表持久化，仍依赖调用方传入的 `AsyncProviderAdmissionQuery`，
如实记录为遗留缺口。

## Decision 6 —— AI Coach：生成式内容必须来自真实模型，治理边界靠 schema + 边界标注，不靠 Human Gate

**直接触发原因**：project-owner 明确纠正"我们要的是真的生成式AI，不是手写的AI"。据此确立
三条硬约束：
1. 引导话术的具体文字**只能**来自真实模型调用（`ModelGateway.generate_structured`），系统
   提示词只规定行为准则（苏格拉底式、先理解后提问、不诊断、不评判、中文），不允许任何
   if-elif/关键词匹配式的"伪装智能"。
2. 输出 JSON schema **故意不设 answer/solution 字段**——用结构本身、不是靠模型"自觉"，
   排除模型直接给方案的可能性；`reflection`+`guiding_question`+`boundary_note` 三字段
   缺一不可，缺字段即 fail-closed 拒绝。
3. **不经 Human Gate**：AI Coach 的回复是直接展示给家长看的 Perspective，家长自己怎么想
   是家长的事，不产生任何业务状态变更——这与 FGCN 分派建议（AI 建议要变成真实
   `TaskAssignment` 才需要 Human Gate 审批）性质不同,不应该被同一套机制不必要地拖慢。
   响应携带 `AI_PERSPECTIVE_NOT_FAMILY_FACT_GUIDANCE_NOT_ANSWER` 边界标注。

**验证方式（不接受用 FakeProvider 冒充"验证过生成式效果"）**：project-owner 提供真实
DeepSeek API Key（`AI_COACH_MODEL_BASE_URL`/`AI_COACH_MODEL_API_KEY` 环境变量，凭据只在
`build_openai_compatible_provider` 这一个点读取，R7），本人独立于实现该功能的会话之外，
重新执行一次调用并打印原始模型输出核实——回复内容逐字不同于任何提前写好的文案，且确实是
"先反映理解、再抛问题"的两段式结构。Key 只存在于本次会话的环境变量，未写入任何文件。

AI 用例治理文档：`docs/05_ai/AI_USE_CASES/family-ai-coach.md`（`AI_USE_CASE_REGISTRY.yaml`
尚未建立，按 CLAUDE.md 既定 fallback 规则写入该目录）。

## Consequences

- family_need 的 N0→N8 全链路首次都有可验证的真实实现，且 N6/N7 的"AI 不能自判结果"规则
  有测试断言其真的拒绝了 AI/SYSTEM 调用，不是文档层面的承诺。
- FGCN 从"接入过一次的孤立子系统"变成"family_need 真实复用的授权闸门"，且其分派记录
  第一次真正持久化，为后续把 FGCN 的其他能力（质量评审/贡献分账）接入 family_need 铺了路。
- AI Coach 是本仓库第一个"生产可用真实模型 provider 已验证跑通"的 AI 能力（此前的 AI 相关
  代码多数仍停留在 FakeProvider 验证阶段）。
- **遗留缺口（如实记录）**：N4 资源调度、N8 知识库回流、FGCN provider 准入持久化、AI Coach
  跨轮次记忆，均明确留待后续增量，不在本次范围内假装解决。

## Enforcement

- `governance/DOMAIN_REGISTRY.yaml` 的 `family_need_orchestration` 与
  `service_fgcn_collaboration` 两条 known_gaps 已同批更新，措辞与本 ADR 一致。
- `governance/MIGRATION_MANIFEST.yaml` 的 `family_need_orchestration` evidence/known_gaps
  已同批更新。
- 后续任何人接手 N4 资源调度、N8 知识库回流、FGCN provider 准入表、AI Coach 记忆接入，
  应先读本 ADR 与 ADR-0149/ADR-0150，不应假设当前实现已覆盖这些范围。

## References

- ADR-0149（family_need 生产接线）、ADR-0150（跨域履约协调器与课程内容）
- `backend/domains/family_need/domain/entities.py`（AssignmentPlan/FamilyConfirmedOutcome）
- `backend/domains/family_need/domain/policies.py`（assert_family_outcome_confirmer）
- `backend/apps/family_api/orchestration/fgcn_assignment_flow.py`
- `backend/domains/family_need/infrastructure/fgcn_case_entry_adapter.py`
- `backend/intelligence/experience/family_ai_coach.py`
- `backend/apps/family_api/ai_coach_wiring.py`
- `docs/05_ai/AI_USE_CASES/family-ai-coach.md`
- `tests/apps/family_api/test_need_fulfillment_e2e.py`
- `tests/domains/service/fgcn/test_family_need_durable_assignment_postgres.py`
- `tests/intelligence/experience/test_family_ai_coach_real_model.py`
- `governance/DOMAIN_REGISTRY.yaml` → `family_need_orchestration`, `service_fgcn_collaboration`
- `governance/MIGRATION_MANIFEST.yaml` → `family_need_orchestration`
