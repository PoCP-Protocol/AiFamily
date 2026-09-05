# ADR-0128：Experience 运维查询访问审计持久化

- 状态：Accepted（2026-08-30）
- 范围：`backend/intelligence/experience/operations_query.py`、
  `backend/intelligence/experience/operations_audit_persistence.py`、
  `database/migrations/versions/0037_ai_experience_operations_audit.py`

## 背景

Experience delivery 的运维查询只能返回投递状态 metadata，但 operator 的
allow/deny/identity-error 访问决定本身也需要在进程重启后可追溯。把事件写入
家庭域审计表会虚构 tenant/family/subject 关系，也容易把原始 outbox payload
带进审计链，因此需要独立的 platform-internal 表。

## 决策

1. 使用 `ai_experience_operations_audit` append-only 表，只保存 operator_id、
   authorization_ref、environment、operation、outcome、occurred_at。
2. `SqlAlchemyExperienceOperationsAuditSink.record()` 只 `add + flush`，不自行
   commit；事务由 family_api composition root/请求生命周期拥有。对于不共享
   业务 UoW 的 operator read，`SqlAlchemyExperienceOperationsAuditSessionSink`
   以注入的 `async_sessionmaker` 开启短事务并在查询返回前提交。写入失败时，
   `AuthorizedExperienceOperationsQueryService` fail-closed，不返回运维数据。
3. 表结构不包含 family_id、subject_id、payload、model output、token、secret
   或自由文本 error；查询审计只允许三种结果：`ALLOWED`、`DENIED`、
   `IDENTITY_ERROR`。
4. 运维查询 API 仍要求外部 operator identity 和 scope；durable sink 必须由
   生产组合根显式注入，未注入时保持 503，测试与生产路由不分叉。

## 后果

- 审计可跨进程、跨部署保留，且与业务家庭事实隔离；同一事务的失败方向
  保持可验证。
- 需要部署侧提供 session/commit 生命周期、数据库权限、WORM/保留策略和
  dashboard 读取权限；本 ADR 不授权任何 payload 级调试输出。
- FastAPI dependency override 必须使用闭包返回已组合 service，而不能把
  `async_sessionmaker` 放入 lambda 默认参数；否则框架的参数深拷贝会触发
  驱动模块不可 pickle，导致审计接线在请求解析阶段失败。
