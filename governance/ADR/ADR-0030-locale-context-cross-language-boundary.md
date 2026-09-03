---
id: ADR-0030
title: 统一 LocaleContext 与 TypeScript-Python 契约边界
status: proposed
date: 2026-08-30
deciders: [project-owner, chief-architect]
---

# ADR-0030：统一 LocaleContext 与 TypeScript-Python 契约边界

## 背景

源仓库记录了两种“多语言”设计：A3 的 TypeScript 业务层与 Python 知识层边界，
以及用户语言、内容语言、模型语言、政策语言四维 locale。源仓库没有可直接复制的
独立多语言运行时；AiFamily 又已通过 ADR-0001 冻结为 Python-only 后端。

## 决策

1. AiFamily 保留 TypeScript 仅作为客户端语言，Python 作为 API、业务域和 AI Runtime
   的唯一后端语言；不迁入旧 NestJS 业务后端，也不建立 Python sidecar 的第二套业务真相。
2. 用 `contracts/schemas/locale-context.schema.json` 作为客户端与 Python 运行时共享的
   transport contract。
3. 用 `backend/platform/localization/LocaleContext` 作为 Python 侧唯一四维 locale
   值对象；所有 fallback 必须显式传入，可靠性不足时 fail-closed。
4. locale 解析不是翻译服务。翻译、知识、政策和人工审核的版本化能力另行登记，不能
   通过默认 locale 或静默机翻补齐。

## 取舍

这会暂时保留一些业务 DTO 中的 locale 字段，并要求后续兼容收敛；换来的好处是不会
把用户语言误当作政策语言，也不会在迁移中重新引入 TS/Python 双业务后端。当前实现
只完成契约与值对象，不宣称 API Resolver、翻译目录或 locale Eval 已完成。

## 依据

- 源仓库：`50_开发_dev/reports/REPO_AUDIT_REPORT.md` §3 C-1、§4 A3 边界；
- 源仓库：`50_开发_dev/architecture/FAMILY_AI_PLATFORM_TECH_ARCHITECTURE_V4_1.md` §18–19；
- AiFamily：`governance/ADR/ADR-0001-python-only-backend.md`；
- AiFamily：`docs/00_system/CORE_BLUEPRINT_GLOBAL_SCALE_ALIGNMENT.md` §7.2。
