# ADR-0025: 法咪莉校长作为统一 AI 控制面

```yaml
id: ADR-0025
status: proposed
date: 2026-08-30
owners: [chief-architect, ai-product-and-governance]
scope: [business, process, data, application, ai-technical]
```

## 背景

平台同时需要家庭成长助手、服务产品设计、知识治理、运营洞察和真人协作。历史设计把
这些能力按页面或 Agent 分散描述，容易出现多个模型入口、多个知识库、多个审计链，
也会把“校长 IP”误做成一个聊天页面。源项目中的校长 Soul、结构化输出和安全策略已经
给出较好的产品边界，但尚未与本仓库的 Python AI Runtime、业务域和 34 UI 形成一体化运行时。

## 决策

### 1. Principal 是跨域控制面，不是业务域或模型

法咪莉校长负责 Persona/Soul、目的解释、能力路由、结果编排和用户体验；
`Family`、`Journey`、`Service`、`Commerce`、`Outcome` 等事实仍由原业务域拥有。
校长没有业务 ORM/repository，任何事实写入都必须经业务域 Named Action。

### 2. 所有平台 AI 能力经过同一条运行时

家庭端五个 Agent、服务产品设计 profile、知识管家 profile 和运营洞察 profile 共用：

```text
Consent → Context → Safety → Principal Soul → Capability Router
→ Knowledge → Agent/Tool Runtime → Model Gateway
→ Schema/Provenance → Human Gate → Named Action → Feedback/Evaluation
```

`backend/intelligence/model_gateway` 是唯一供应商边界；不得在领域、应用或 Principal
代码中直接调用模型 SDK。每次请求只选择一个主 profile，跨 profile 协作必须拆成有
`correlation_id/causation_id` 的工作流请求。

### 3. Soul 与方法继承、身份克隆分离

校长可以继承已审核的方法、价值和语言原则，但不得模拟真实教师身份、声音、外貌、
私人记忆或制造虚假亲密关系。Soul 以不可变版本发布，并与 Prompt、Schema、Knowledge、
Safety 和评估结果绑定。

### 4. AI 输出永远是草案或建议

Principal/Agent/Tool 的 `may_mutate_business_state` 固定为 `false`。输出只允许
`Perspective`、`Hypothesis`、`Draft`、`Recommendation`、`ActionProposal`、
`HumanTask` 或 `Explanation`。计划、行动、服务分派、验收、支付、会员和政策变化必须
由用户或人工 reviewer 通过业务域 Named Action 完成。

### 5. 服务产品设计 AI 是校长的内部 profile

服务产品设计平台不另建一套模型和知识库。`service_product_architect` profile 可以
调用 Product Intelligence、Component/Pattern Catalog、Compiler、Simulation 和
Knowledge Steward，但蓝图发布、回滚和 ServiceCase 创建必须经过人工发布闸门。
模拟结果不能证明真实效果，公共知识库不得写入家庭私有事实。

### 6. 开发、测试、生产功能等价

三环境必须使用同一接口、路由、状态机、Schema、Safety、Human Gate、错误码、审计和
删除路径。测试只替换合成数据、Fake/Deterministic Provider 和 sandbox/noop adapter；
不得因为没有真实数据而删除校长入口、失败路径、人工闸门或发布回滚。

## 影响

### 正面影响

- 34 个 UI、运营工作台、服务产品设计和知识治理可以共享同一个 AI 运行时与来源图。
- Soul、知识、模型和业务事实解耦，供应商替换不会改变业务域。
- 三个区的投入顺序可以落实：同质区保安全和成本，优势区做真人协作，独占区积累 Context、
  Growth Graph、Intervention 和 Blueprint 资产。

### 代价和限制

- 需要新增 Principal 技术表、路由契约、HumanTask、Eval 和删除作业；不能用一个聊天接口代替。
- 在外部模型供应商完成合规准入之前，生产请求只能显式降级为人工或不可用；FakeProvider
  的输出不得被当成生产能力。
- 源项目代码不能原样搬运；Python 侧必须重新实现契约，并保留其安全、结构化输出和
  Attempt 记录等可验证语义。

## 被否决的方案

1. **每个业务域各接一个模型**：会产生多套网关、凭据、策略和审计链，违反唯一 Runtime。
2. **把 Principal 做成万能超级 Agent**：无法区分家庭、产品和运营权限；改为单一主 profile + 显式工作流。
3. **让 AI 直接创建 GrowthAction/ServiceTask**：违反 R9 和事实边界；只允许待确认 ActionProposal。
4. **把源教师身份复制成数字人**：违反身份克隆边界；只继承方法与价值。
5. **测试环境删掉生产流程**：无法验证生产等价；测试只替换数据与适配器。

## 验证要求

- `tests/intelligence/test_principal_router.py` 验证能力路由、同意、主体范围、Soul 和只读边界。
- `tests/architecture/test_ai_use_case_registry.py` 验证 Principal、五个 Agent、服务产品和知识用例登记。
- 后续纵向切片必须补齐 Context→Gateway→Draft→Human Gate→Named Action→Feedback 的真实测试，
  以及主体删除、回滚、死信、超时和环境等价测试。

