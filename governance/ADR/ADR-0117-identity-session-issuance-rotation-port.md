# ADR-0117：Identity Session 签发与轮换端口

- 状态：Accepted
- 日期：2026-08-30
- 范围：`backend/platform/identity/session_port.py`

## 决策

AI 请求边界只消费已经认证的 Bearer session，不从 `external_ref` 或模型输入
推导身份。新增 provider-neutral `IdentitySessionPort`，由真实 `auth_identity`
服务负责会话签发、轮换和撤销；`HttpIdentitySessionPort` 通过显式注入的 HTTP
client/mTLS 配置访问该服务。

## 安全边界

- access token 只在签发响应中返回一次，数据类 `repr`/比较均不暴露 token；轮换与
  撤销把当前 session 放在独立传输头，不放进 JSON payload。
- bootstrap credential 只由组合根提供，adapter 不读取环境变量、不持久化秘密、不记录
  token；身份服务返回过期、畸形或非 2xx 响应时统一 fail-closed。
- staging/production 共用同一个 port；dev/test 仍使用现有合成会话实现，只替换
  identity adapter，不改变 AI scope、consent、Safety、Human Gate 或 Model Gateway
  状态机。

## 未完成项

真实 OTP、账号生命周期、数据库写入、密钥轮换和部署平台 endpoint 仍属于
`auth_identity` 迁移与部署 owner；本 ADR 只冻结 AI 组合根所依赖的最小端口。
