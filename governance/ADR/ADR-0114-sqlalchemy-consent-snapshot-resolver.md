# ADR-0114：SQLAlchemy Consent Snapshot Resolver

- 状态：Accepted
- 日期：2026-08-30
- 范围：`backend/apps/family_api/trusted_experience_scope.py`

## 决策

新增 `SqlAlchemyConsentSnapshotResolver` 与
`SqlAlchemyFamilySubjectIdsResolver`，从基线 `persons`/`consents` 表读取家庭
主体和当前 consent rows，并转换为不可变 `ConsentSnapshot`/`ConsentGrant`。查询
按 trusted family、主体集合和 purpose 限定；consent version 由当前 grant 元数据
生成稳定摘要，删除句柄和 retention policy 显式写入 scope。

## Fail-closed 规则

- 空主体、未知枚举、非法时间或缺失 birth date 均拒绝或返回无 grant，随后由
  `ConsentGate` 阻断模型调用。
- guardian relation 从已存 guardian/subject 关系推导，未使用客户端字段；未满 14
  岁主体仍必须满足 guardian consent 约束。
- 适配器只读 canonical identity/consent 表，不写业务事实，不缓存撤回结果；每次
  scope resolve 都重新查询。
- PostgreSQL schema/权限、真实 request-auth principal 和并发/删除演练仍需部署验收。
