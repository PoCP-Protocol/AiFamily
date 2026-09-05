---
id: PLT-LOCALE-001
title: Locale Context 与跨语言契约
type: platform
status: current
version: 1.0
owner: chief-architect
created: 2026-08-30
updated: 2026-08-30
canonical: true
supersedes: null
superseded_by: null
---

# Locale Context 与跨语言契约

本文件把源仓库 A3“多语言边界”的有效语义重译到 AiFamily：客户端使用
TypeScript，后端与 AI Runtime 使用 Python；两者只通过稳定的 JSON/OpenAPI
契约交互。源仓库原有的 TypeScript 业务后端和 Python sidecar 不迁入，避免
形成第二套业务真相。

## 1. 四维语言上下文

每次进入 API 或 AI Runtime 的请求都应携带以下四个彼此独立的维度：

| 字段 | 含义 | 不可替代的对象 |
|---|---|---|
| `user_locale` | 用户阅读与输入语言 | 内容、模型和政策语言 |
| `content_locale` | 知识与服务内容语言 | 用户 UI 语言 |
| `model_locale` | 模型能力支持的语言 | 模型是否能可靠处理政策语义 |
| `policy_locale` | 法规、风险和人工队列语言 | 普通 UI 翻译 |

传输契约位于 `contracts/schemas/locale-context.schema.json`，Python 运行时实现
位于 `backend/platform/localization/context.py`，HTTP 适配器位于
`backend/platform/localization/fastapi.py`，路由通过 `get_locale_context` 依赖读取已验证
上下文。这几个落点分别服务 TypeScript 客户端
和 Python API/AI Runtime，不能由某一端私自扩展字段语义。

`LocaleContext.as_dict()` / `LocaleContext.from_dict()` 以及
`LocalizedArtifact.as_dict()` / `LocalizedArtifact.from_dict()` 对应 JSON Schema 的
严格对象边界：缺字段、未知字段、错误数组类型和未支持的 locale 都会拒绝，不把
未声明的跨语言字段静默吞掉。

## 2. Fallback 与安全边界

- fallback 必须由请求显式按顺序提供，不能从进程环境或默认语言推断。
- `LocaleContext.resolve_reliable()` 只返回同时属于 `supported_locales` 与
  `reliable_locales` 的语言；没有可靠翻译就抛出 `*_UNAVAILABLE`，由上层转人工
  或明确不可用。
- 不允许把技术上可用的机器翻译当作政策、风险或敏感建议的可靠翻译。
- 知识检索连接 canonical `concept_id`，不以翻译文本作为唯一主键；家庭原话保留
  原语言，输出语言单独记录。

## 3. 当前成熟度与缺口

当前已完成不可变 LocaleContext、JSON Schema、显式 fallback、可挂载 HTTP middleware、
按 canonical concept_id 解析 reviewed locale artifact 的内存 catalog 和 deterministic
coverage gate，
和可靠性拒绝测试，
状态为 `IMPLEMENTED_TESTED`，但尚未承载生产流量。以下能力仍未完成：

- `family_api` 主入口尚未挂载 middleware；挂载后，`/principal` 与 `/ai` 路径会要求
  四维上下文，其他旧路径在未发送 locale 头时暂时兼容；
- Prompt、Knowledge Claim、Error Code、Human Gate 的持久化版本库、审核工作流尚未建立；
- 尚无语义质量评估、文化适配审核和人工升级队列；当前 coverage gate 只能证明条目
  齐全且已标记 `REVIEWED`，不能证明翻译质量；
- `PrincipalRouteRequest` 与各业务 DTO 仍有局部 locale 字段，后续应收敛到本契约，
  但不得在没有兼容迁移方案时直接破坏现有 API。

这项落地不改变 AiFamily 的 Python-only 后端决定，也不表示“多语言能力已完整可用”。
