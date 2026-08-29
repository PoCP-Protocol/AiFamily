# AGENTS.md — 非 Claude Agent 入口（Codex 等）

**详细规则见根目录 `CLAUDE.md`。本文件只讲最低门槛与并发安全。** 两份文件规则一致，冲突时以 `CLAUDE.md` 为准。

## 这是多 Agent 协作环境

本仓库同时可能有多个 AI Agent 会话与人类在工作。你**看到的工作区状态不一定全是你造成的**，也不全归你处置。

## 并发安全规则（硬性）

1. **只改自己负责的文件。** 动手前先 `git status`，看清哪些改动不是你的。别人的 WIP 一律不碰、不"顺手修复"、不格式化。
2. **禁止 `git add -A` / `git add .` / `git commit -a`。** 会吞掉协作者已 staged 的 WIP。
3. **提交必须带 pathspec**：`git add <你明确改的文件>` 然后 `git commit -m "..." -- <同一批文件>`。误提交别人文件用 `git reset HEAD~1` 退回，别 force push。
4. **走功能分支 + PR**，不直接推 main。只推你自己分支上你自己的提交历史。
5. **源仓库 `D:\family-ai` 只读**（内有其他并发会话未提交的 WIP）。禁止任何写操作。
6. **不要相信缓存/上一轮产物**（`latest.json`、`.pytest_cache`、上次测试输出）。要结论就重跑。

## 开工前必读（顺序）

1. `docs/00_system/SYSTEM_MANIFEST.md` —— 哪些文档算真相
2. `docs/00_system/CURRENT_SYSTEM_BASELINE.md` —— 系统现状含未完成项
3. `governance/REPOSITORY_CONSTITUTION.md` —— 14 条工程宪章
4. 涉 AI 加读 `docs/05_ai/AI_NATIVE_PRINCIPLES.md`；涉数据加读 `docs/12_governance/COMPLIANCE_HARD_CONSTRAINTS.md`

## 最容易违反的 5 条

- **不给 `backend/`、`backend/domains/`、`backend/packages/`、`backend/intelligence/` 加 `__init__.py`** —— 会触发 R3 架构测试失败（纯容器目录不该有 manifest 条目）。Python 3.12 命名空间包不需要。
- **迁入代码把 `from packages.contracts.*` 改成 `from backend.packages.contracts.*`**（R12），且代码/注释里不得出现 `50_开发_dev` 或 `D:\family-ai` 字面量。
- **不做家庭总分/家庭排名**（R9 红线）；**AI 输出不直写事实**；**领域不直连模型供应商**（R7，一律经 `backend/intelligence/model_gateway`）。
- **Bash 工具禁用 `cp`/`tar`/`robocopy`**，复制用 Python `shutil`；中文路径用 Python `pathlib` 处理，别拼 bash 一行流。
- **改结构必跑** `uv run pytest tests/architecture -v`（当前基线 12 passed）+ `uv run ruff check .`。

## 治理登记

- 加 domain 代码 → 先查/改 `governance/DOMAIN_REGISTRY.yaml`（R2）
- 从旧仓库迁入 → 先查/改 `governance/MIGRATION_MANIFEST.yaml`（R3，无登记不得入仓）
- 架构决策 → 先写 `governance/ADR/ADR-NNNN-<slug>.md`，禁止在实现 PR 里改宪章
- `governance/CAPABILITY_REGISTRY.yaml` 与 `governance/AI_USE_CASE_REGISTRY.yaml` **尚未建立**（另有任务在建）；存在后即为强制前置检查。

面向用户的回复用中文，代码与标识符用英文。如实报告缺口——"迁移进来了" ≠ "能力存在"。
