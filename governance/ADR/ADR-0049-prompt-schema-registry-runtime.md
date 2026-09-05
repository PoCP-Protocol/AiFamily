---
id: ADR-0049
title: Prompt 与 Schema 采用绑定且不可变的运行时 Registry
status: accepted
date: 2026-08-30
decision_owner: project-owner
supersedes: null
superseded_by: null
---

# ADR-0049：Prompt 与 Schema 采用绑定且不可变的运行时 Registry

## 背景

`StructuredRequest` 目前只能保证 `prompt_version` 与 `schema_version` 非空，
无法证明版本真实存在、属于当前 `use_case/agent`，或仍在有效时间窗口内。这样会
让调用方以任意字符串伪造 provenance，也会让一个合法 JSON 对象绕过
`evidence_refs`、人工闸门和 R9 禁止字段约束。

## 决策

1. 在 `backend/intelligence/` 下分别建立 provider-neutral `prompt_registry` 与
   `schema_registry`。Registry 只保存不可变值对象，不导入领域 ORM、模型供应商或
   UI。版本身份分别由 `(prompt_ref, version)` 与 `(schema_ref, version)` 构成，重复
   注册一律拒绝。
2. PromptBundle 强制声明 use case、agent、system/safety policy、知识和输入/输出
   契约引用、作者/审核者、状态和生效时间。`resolve` 只返回 `PUBLISHED` 且在
   effective window 内并与 use case/agent 完全匹配的版本；缺失、过期、撤回或歧义
   均 fail-closed。
3. SchemaDefinition 强制声明 required fields、evidence refs 非空策略、forbidden
   fields、enum/boundary labels、human gate rule 和可校验 JSON Schema。SchemaValidator
   在结构校验前执行禁止字段与证据边界校验，任何不满足项均拒绝，不提供静默修复。
4. 生命周期转换创建新版本并保留旧对象用于审计/重放；不得原地修改已登记版本。
   该内存实现是首个运行时适配器，持久化版本库与发布审批由后续组合根接入。

## 后果

- Agent Runtime 可以在构造 Model Gateway 请求前取得真实、绑定的 Prompt/Schema，
  provenance 不再接受任意孤立字符串。
- Prompt/Schema 资产变更天然可回滚、可重放；历史版本不会被无声覆盖。
- 当前 adapter 尚未接入 SQL 持久化、运营发布工作流或统一治理 YAML loader；生产
  组合根必须显式注册审核后的版本，找不到版本时应拒绝调用模型。

## 约束依据

- `docs/05_ai/AI_TECHNICAL_ARCHITECTURE.md` §10–§11
- `docs/05_ai/AI_NATIVE_PRINCIPLES.md` §3.2–§3.5
- `governance/REPOSITORY_CONSTITUTION.md` R7、R8、R9、R10、R14

## Enforcement

- `backend/intelligence/prompt_registry/`
- `backend/intelligence/schema_registry/`
- `tests/intelligence/prompt_registry/`
- `tests/intelligence/schema_registry/`

