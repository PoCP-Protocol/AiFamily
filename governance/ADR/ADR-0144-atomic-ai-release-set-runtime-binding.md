# ADR-0144：原子 AI ReleaseSet 与运行时发布证据绑定

- 状态：Accepted（能力仍为 EXPERIMENT）
- 日期：2026-09-01
- 决策者：project-owner / AI architecture

## 背景

单独批准模型、Prompt 或路由版本，不能证明一次真实外呼使用的就是被评测和人工批准的完整配置。首选与备用模型若分别切换，也可能形成从未整体评测过的组合。测试环境若绕过发布状态机，则无法验证未来生产行为。

## 决策

1. 以内容寻址的 `FamilyExperienceReleaseSet` 原子绑定 provider→Bundle 顺序、Prompt、Schema、Safety、Knowledge refs、路由、价卡和预算策略的版本及内容摘要。
2. 只有 `ACTIVE` 或指向历史 `ACTIVE` 目标的 `ROLLBACK` receipt 能成为有效运行配置；CANARY 不授权普通在线流量。
3. 生产运行时每次从 SQL 解析有效 ReleaseSet，并校验完整配置摘要；测试/开发使用相同值对象和校验状态机，只替换为隔离的 FakeProvider 与内存适配器。
4. `ModelReleaseBinding` 必须传播到 Budget Reservation、Model Attempt 与 Provenance；每个 fallback provider 记录自己的 Bundle。
5. AI 输出继续保持 DRAFT-only、不得写家庭事实，关键动作仍经人工闸门。
6. 以 scope 唯一的活动发布投影保存单调 deployment sequence；Gateway 必须在 adapter I/O 紧前取得持久化 invocation fence claim。发布若先推进，旧绑定拒绝；claim 若先提交，该次调用被视为已获准的 in-flight 调用。
7. 发布服务必须在任何外部副作用前独立提交 scope 唯一的 `PREPARED` transition。外部 ACK 后，receipt、活动投影和 `COMMITTED` 在同一事务完成；超时或进程不确定结果保留为 `UNKNOWN/PREPARED`，阻止不同幂等键越过，恢复只能复用原幂等键。
8. 外部发布端口必须接收并回显 `transition_id/control_id/expected_effective_sequence`；HTTP adapter 将三者同时放入 header 与 metadata-only body，ACK 任一字段错配均不得激活 ReleaseSet。
9. Prompt 引用的 System Policy 与 Knowledge 必须从服务端材料注册表解析；只有已审核、已发布、在生效窗口内的材料可以组成 `PromptExecutionPlan`。Knowledge 仅允许 `SHARED` 内容，不允许把家庭私有内容登记为执行知识。
10. ReleaseSet 的 `asset_digest` 同时覆盖 Prompt template、Schema、System Policy digest 与有序 Knowledge digests；adapter 仅使用解析后的正文和来源/许可/证据元数据，客户端不能提交或覆盖执行材料。
11. PREPARED、UNKNOWN 与 ACKNOWLEDGED 由有界 reconciler 扫描，使用带过期时间的 durable worker lease 与指数退避。reconciler 只能消费原真人签名 control：APPLIED 需要外部平台精确回显 fencing tuple；PENDING、ABSENT、FAILED 不能自动解除 scope 锁或生成新发布授权；已持久化 ACK 可直接恢复本地提交而不重复外部调用。

## 数据与迁移

- 0045：Bundle 绑定 routing/rate-card/budget policy 版本。
- 0046：持久化不可变 ReleaseSet。
- 0047：记录带单调序列的 ReleaseSet APPLY/ROLLBACK receipt，并以组合约束拒绝非法 operation/phase/target。
- 0048：把 ReleaseSet、Bundle 与 deployment receipt 引用传播到 Attempt/Budget 证据链。
- 0049：持久化签名 ReleaseSet 控制事件，部署端口调用前校验 exact transition 与期望有效序列。
- 0050：持久化活动发布投影和幂等 invocation fence claim，并允许对未出网的预算预留记录 `RELEASED`。
- 0051：持久化 pre-external ReleaseSet transition 状态机与 scope 排他发布权。
- 0052：持久化内容寻址的 System Policy 与 SHARED Knowledge execution materials。
- 0053：为不确定 ReleaseSet transition 增加 reconciliation lease、attempt 和 backoff 状态。

## 后果

- 同版本内容漂移、部分 fallback 发布、缺失 Bundle、CANARY 冒充 ACTIVE、运行中发布切换均 fail-closed。
- 开发/测试不再以“模拟数据”为由绕过合同与发布绑定；模拟只发生在数据、Provider 和持久化适配器层。
- 生产可替换模型仍受供应商合规准入限制；当前没有可处理家庭真实数据的外部供应商，因此能力保持 EXPERIMENT。

## 尚未关闭的风险

- ReleaseSet 部署服务已要求回读 0049 append-only 签名控制事件；0051 在外部端口前持久化排他 transition，且 ACK 后 receipt、0050 活动投影与 COMMITTED 同事务提交。0053 reconciler 已覆盖 PREPARED/UNKNOWN/ACKNOWLEDGED 崩溃窗口和多 worker 租约。真实 PostgreSQL 已验证同 scope 只有一个发布越过外部栅栏、同 transition 只有一个 worker 获租。外部端口仍必须真正实现幂等键并接入真实发布平台 fencing token。
- 获批 Prompt、System Policy 与 SHARED Knowledge 已通过 server-owned `PromptExecutionPlan` 进入真实 adapter 请求；缺材料、未审核、未生效、内容摘要篡改或有序 refs 漂移均在网络调用前拒绝。
- Gateway 已在实际 adapter invoke 紧前校验完整活动投影 tuple 并落幂等 claim；deployment sequence 与 control id 已贯穿 Attempt/Budget/Provenance，claim id 已进入 Provenance，release-bound Attempt START 持久化失败会在出网前拒绝并释放预算。仍需把 claim id 直接写入 Attempt/Budget，形成无需组合键的四表关联。
- ReleaseSet/Bundle 规范化成员外键、生产证据非空约束和并发部署 CAS 仍需后续迁移。

## 验证

- `tests/intelligence/experience/test_release_set.py`
- `tests/intelligence/experience/test_release_set_deployment.py`
- `tests/intelligence/experience/test_release_set_deployment_postgres.py`
- `tests/intelligence/experience/test_release_set_control.py`
- `tests/intelligence/experience/test_runtime_release_binding.py`
- `tests/intelligence/experience/test_synthetic_runtime.py`
- `tests/apps/family_api/test_production_experience_wiring.py`
- `tests/intelligence/model_gateway/test_budget_gateway.py`
- `database/migrations/versions/0050_ai_release_projection_invocation_fence.py`
- `database/migrations/versions/0051_ai_release_transition_state_machine.py`
- `tests/intelligence/experience/test_execution_materials.py`
- `database/migrations/versions/0052_ai_execution_materials.py`
- `tests/intelligence/experience/test_release_set_reconciliation.py`
- `database/migrations/versions/0053_ai_release_transition_reconciliation.py`
