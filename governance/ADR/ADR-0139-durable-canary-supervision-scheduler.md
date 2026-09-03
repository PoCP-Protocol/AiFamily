# ADR-0139：Canary 监督采用持久化有界调度与租约抢占

## 状态

Accepted — 2026-09-01

## 背景

ADR-0137/0138 已形成灰度观测、SLO 判定、预授权真人回滚与告警确认闭环，但持续运行还
缺少可重启的任务状态。若在应用进程内长期 sleep 或在事务内执行网络调用，进程故障会
丢失任务，多 worker 也可能重复观测和回滚。

## 决策

1. 新增 metadata-only `CanaryJob`，以 supervision key 唯一绑定 candidate 与 canary
   receipt 快照；不保存家庭标识、家庭内容、Prompt 正文或模型输出。
2. 任务状态为 `PENDING → LEASED → COMPLETED/FAILED`。到期 lease 可由其他 worker
   接管；claim 在短事务中提交后才调用观测、监督和部署端口，不跨网络调用持有数据库事务。
3. `CanaryScheduler.run_scheduled_tick` 每次只领取有界批次，不自行 sleep。持续触发属于
   部署层职责，以便 development/test/staging/production 使用同一 scheduler 代码路径。
4. 健康结果完成任务；样本不足按固定间隔重新排期；瞬时失败有限重试；预授权缺失、过期、
   scope 不一致等 fail-closed 错误进入终态，并保留关联 assessment 或稳定错误码。
5. assessment、alert、rollback control 与 job store 均通过 session-per-call 短事务访问；
   scheduler 不持有启动期 `AsyncSession`。
6. SQL job ledger 由 Alembic 0043 建立。测试环境不缩减状态机、安全闸门或持久化语义，
   只替换显式配置、凭据和模拟数据。

## 结果与边界

- worker 重启和 lease 超时后可恢复监督任务，稳定幂等键继续约束重复副作用。
- 四环境具备相同 enqueue、claim、supervise、retry/reschedule 与 terminal-state 契约。
- 外部定时触发器、真实 paging endpoint 和 PostgreSQL 多 worker 压测仍需部署环境验收；
  当前不能宣称持续灰度监控已生产上线。

## 验证

- `tests/intelligence/experience/test_canary_scheduler.py`
- `tests/apps/family_api/test_family_experience_canary_scheduler_wiring.py`
