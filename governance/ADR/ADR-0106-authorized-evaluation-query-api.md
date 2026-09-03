# ADR-0106：授权的评测证据查询 API

- 状态：Accepted
- 日期：2026-08-30
- 范围：`backend/intelligence/evaluation`、`backend/apps/family_api`

## 决策

为已归档的多模态 benchmark 报告与切片提供内部只读查询端点：

- `/internal/ai/evaluations/reports`
- `/internal/ai/evaluations/slices`

端点必须由组合根注入 `AuthorizedEvaluationQueryService`。服务通过外部
`OperatorIdentityPort` 解析身份，只接受 `ai.evaluation.read` scope，并校验
`staging`/`production` 环境一致性。未注入服务时保持 503 fail-closed；scope
不足返回 403。

## 数据边界

响应只返回 report/slice 的聚合元数据与已由 archive 递归校验的安全 payload，
不接受家庭标识，不返回 prompt、模型原文、媒体字节、凭据或任何家庭事实。
评测证据不挂在 `/families` 路径下，也不参与家庭总分、排名或业务状态写入。

## 取舍与后续

查询上限由 API 与 archive 双重约束（report 50、slice 100），避免无界导出。
Dashboard、分页游标、审计事件落库、保留/删除 worker 与真实身份服务接入仍由
后续部署批次完成；本 ADR 不把内部查询端点误称为运营产品。

