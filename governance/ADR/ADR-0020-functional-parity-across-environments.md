# ADR-0020: 开发、测试、生产环境功能完全等价

- **Status**: Accepted
- **Date**: 2026-08-30
- **Deciders**: project-owner / chief-architect
- **Supersedes**: ADR-0017 的“环境差异可包含能力可用性”误读；不推翻其数据准入与合规门槛

## Context

此前文档把“开发/测试使用合成数据、生产接入真实数据”错误地延伸成了“开发/测试可以只提供部分功能”。这会导致 UI、API、状态机和交付流程在真实数据接入前没有被完整验证，生产上线时反而第一次运行真正的业务路径。

商业蓝图要求的是一套可交付的家庭成长系统，而不是三套逐步加功能的系统。开发环境、测试环境和生产环境必须运行同一套产品功能，才能证明从场景、节点到闭环的完整性。

## Decision

### 1. 三环境功能集合完全相同

三环境必须具有完全相同的 UI 功能、路由、API 契约、Domain 规则、状态机、Named Action、事件、投影、权限、Consent、Privacy、Audit、Idempotency、Workflow、AI Human Gate、服务协作、订单和续购流程。

### 2. 只允许数据和外部依赖不同

开发/测试可以使用 `SYNTHETIC` 数据、隔离 PostgreSQL、确定性 AI adapter、支付 sandbox、通知 fake、可控时钟和故障注入。生产使用真实数据和获准的外部供应商。替换必须发生在 Port/Adapter 层，不能进入 Domain 分支。

### 3. 功能完整不等于数据准入放开

ADR-0017 的数据准入规则继续有效：开发/测试不得使用未经批准的真实未成年人数据，生产真实数据仍需 DPIA、同意、删除、解释和人工复核等前置条件。

```text
功能等价：三环境相同
数据准入：三环境可不同
外部副作用：三环境可用 sandbox/fake 替换
```

### 4. 禁止环境分支改变业务行为

禁止 `if environment == test/development` 跳过业务校验、权限、Consent、Audit、幂等、Human Gate、Workflow、失败、取消、重试或恢复路径；禁止测试专用后门、静态结果和隐藏 UI 功能。环境变量只能选择数据集、适配器、凭据、基础设施地址、容量和故障注入策略。

### 5. 晋升门定义

能力只有在开发环境和测试环境已通过完整业务 E2E、失败矩阵、重启回读、权限/Consent/Audit/幂等和外部依赖替身测试后，才允许申请生产数据准入。生产准入不是“补上缺失功能”，而是“把已验证功能接到真实数据和真实供应商”。

## Consequences

- 所有 `DEV/TEST-only`、`仅开发可用`、`生产不提供该功能` 的表述，若实际想表达的是模拟数据，必须改成“功能全量、数据为 fixture/sandbox”。
- `fixture_only`、`TEST_NOOP_ADAPTER`、`SYNTHETIC` 只能描述数据或外部副作用来源，不能成为业务能力状态机的替代品。
- `dev_wiring.py`、Commerce fixture、Service fake repository 是过渡适配器；它们必须执行生产形状的流程，并逐步替换为完整 PostgreSQL 测试环境和可审计 fake adapter。

## Enforcement

- 规范正文：`docs/10_engineering/ENVIRONMENT_PARITY.md`；
- Agent 规则：`.cursor/rules/environment-parity.mdc`；
- 架构测试：`tests/architecture/test_environment_parity.py`；
- 每个 capability 的完成证明必须同时报告“功能完整度”和“数据/外部依赖适配器状态”，不得用后者掩盖前者。
