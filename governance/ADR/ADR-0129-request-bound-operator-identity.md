# ADR-0129：运维查询使用请求绑定的 Operator Identity

- 状态：Accepted（2026-08-31）
- 范围：内部 `/internal/ai/experience` 运维查询 API 与 operator identity adapter

## 背景

`AuthorizedExperienceOperationsQueryService` 已要求 operator 环境和 scope，但
如果 identity port 只使用静态 bootstrap token，审计记录无法证明是哪一个 HTTP
调用者发起了查询。运维 API 必须校验当前请求 bearer，同时不能把 bearer 复制到
业务对象、审计记录或日志。

## 决策

1. FastAPI 请求依赖只提取 `Authorization: Bearer ...`，将 token 放入请求上下文
   的短生命周期内存槽；缺失或格式错误返回 401，请求结束时清理上下文。
2. `HttpRequestOperatorIdentityPort` 通过注入的 HTTP client/mTLS 配置把该 bearer
   发送到 auth_identity 的 operator identity endpoint，仅解析 operator_id、
   authorization_ref、environment、scopes。
3. identity endpoint 的拒绝、超时、网络错误或非法响应统一转换为稳定的
   `OperatorIdentityError`，由 API 映射为 503；token 不进入异常文本或任何持久化表。
4. 原有 `HttpOperatorIdentityPort` 保留给服务到服务 bootstrap 场景；两者不能
   混用。测试通过同一路由注入 fake identity port，保持 dev/test 与 production
   功能 parity。

## 后果

- 运维访问审计能绑定真实请求授权结果，静态服务凭据不会伪装成操作者。
- 需要部署提供 auth_identity operator endpoint 与 mTLS/权限配置；没有这些依赖
  时 API 仍保持 fail-closed。
